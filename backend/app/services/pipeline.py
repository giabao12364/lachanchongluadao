import logging
import re
import json
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.services.rule_engine import run_rule_engine
from app.services.scan.extractor import extract_entities
from app.services.scan.blacklist_checker import check_entities_against_blacklist
from app.models.db_models import AppConfig

logger = logging.getLogger(__name__)

_THRESHOLD_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "nghi_ngo": 30,
    "nguy_hiem": 70,
    "ai_weight": 0.6,
    "max_final_score": 100,
    "ai_timeout_seconds": 5,
    "ai_system_prompt": None,
}
_THRESHOLD_TTL_SEC = 60

_RISK_RANK = {"AN_TOAN": 0, "NGHI_NGO": 1, "NGUY_HIEM": 2}

_AI_MAX_RETRY_JSON = 2
_AI_SOFT_WARNING = "Hiện chưa phân tích sâu được nội dung, hãy thận trọng."


def _load_thresholds(db: Session) -> dict[str, Any]:
    import time
    now = time.time()
    if now - _THRESHOLD_CACHE["ts"] < _THRESHOLD_TTL_SEC:
        return _THRESHOLD_CACHE
    try:
        rows = db.query(AppConfig).all()
        m = {r.key: r.value for r in rows}
        _THRESHOLD_CACHE["nghi_ngo"] = int(m.get("threshold.nghi_ngo", "30"))
        _THRESHOLD_CACHE["nguy_hiem"] = int(m.get("threshold.nguy_hiem", "70"))
        _THRESHOLD_CACHE["ai_weight"] = float(m.get("ai.weight", "0.6"))
        _THRESHOLD_CACHE["max_final_score"] = int(m.get("pipeline.max_final_score", "100"))
        _THRESHOLD_CACHE["ai_timeout_seconds"] = int(m.get("ai.timeout_seconds", "5"))
        _THRESHOLD_CACHE["ai_system_prompt"] = m.get("ai.system_prompt")
        _THRESHOLD_CACHE["rec_an_toan"] = m.get(
            "recommended_action.an_toan",
            "Không thấy dấu hiệu lừa đảo. Nếu có ai yêu cầu chuyển tiền hoặc mã OTP, hãy dừng lại và hỏi người thân.",
        )
        _THRESHOLD_CACHE["rec_nghi_ngo"] = m.get(
            "recommended_action.nghi_ngo",
            "Có dấu hiệu đáng ngờ. Đừng bấm link và đừng cung cấp thông tin. Hãy hỏi lại người thân hoặc gọi số tổng đài chính thức.",
        )
        _THRESHOLD_CACHE["rec_nguy_hiem"] = m.get(
            "recommended_action.nguy_hiem",
            "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền, không cung cấp mã OTP. Hãy xóa tin nhắn và chặn số này.",
        )
        _THRESHOLD_CACHE["ts"] = now
    except Exception as e:
        logger.warning("[pipeline] Failed to load AppConfig, using cached defaults: %s", e)
    return _THRESHOLD_CACHE


def _ai_api_key_available() -> bool:
    try:
        import os
        key = os.environ.get("AI_API_KEY", "")
        return bool(key) and key not in ("your-secret-key-here", "", None)
    except Exception:
        return False


def _parse_ai_score(raw_response: str) -> Optional[int]:
    """Parse AI response to extract score. Returns None if parsing fails."""
    if not raw_response:
        return None
    text = raw_response.strip()
    if not text:
        return None
    cleaned = text.strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "score" in data and isinstance(data["score"], (int, float)):
            return max(0, min(100, int(data["score"])))
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r"\"score\"\s*:\s*(\d{1,3})", text)
    if m:
        try:
            return max(0, min(100, int(m.group(1))))
        except ValueError:
            return None
    m2 = re.search(r"\bscore\b[^\d]{0,10}(\d{1,3})", text, re.IGNORECASE)
    if m2:
        try:
            val = int(m2.group(1))
            if 0 <= val <= 100:
                return val
        except ValueError:
            pass
    return None


def _call_ai(normalized_text: str, timeout_sec: int, system_prompt: Optional[str]) -> Optional[int]:
    """
    Gọi OpenAI API với timeout, retry 2 lần cho JSON hỏng (AT-01-5).
    Trả về score 0-100 hoặc None nếu bất kỳ lỗi nào xảy ra (BR-01-6).
    Không bao giờ raise exception — fail-safe.
    """
    if not _ai_api_key_available():
        return None

    import os
    try:
        import httpx
    except ImportError:
        logger.warning("[ai] httpx not available, falling back to no-AI mode")
        return None

    key = os.environ.get("AI_API_KEY", "")
    endpoint = os.environ.get("AI_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")

    if system_prompt:
        sys_prompt = system_prompt
    else:
        sys_prompt = (
            "Bạn là chuyên gia phân tích lừa đảo trực tuyến tại Việt Nam. "
            "Đánh giá nội dung có dấu hiệu lừa đảo không. "
            "CHỈ trả về JSON: {\"score\": X, \"reasons\": [...]}. "
            "score: 0-100 (0=an toàn, 100=chắc chắn lừa đảo)."
        )

    user_prompt = f"Đánh giá nội dung sau (0-100 điểm, trả về JSON):\n\n{normalized_text}"

    last_score: Optional[int] = None
    last_error = None

    for attempt in range(1, _AI_MAX_RETRY_JSON + 1):
        try:
            payload = {
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
            with httpx.Client(timeout=timeout_sec) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "[ai] HTTP %s (attempt %s/%s): %s",
                        resp.status_code, attempt, _AI_MAX_RETRY_JSON,
                        resp.text[:200]
                    )
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < _AI_MAX_RETRY_JSON:
                        continue
                    return None

                body = resp.text
                try:
                    outer = json.loads(body)
                    if isinstance(outer, dict) and "choices" in outer:
                        content = outer["choices"][0]["message"]["content"]
                        score = _parse_ai_score(content)
                        if score is not None:
                            return score
                        if attempt < _AI_MAX_RETRY_JSON:
                            logger.info(
                                "[ai] JSON parse failed (attempt %s/%s), retrying...",
                                attempt, _AI_MAX_RETRY_JSON
                            )
                            continue
                        last_error = "JSON parse failed after retries"
                        return None
                    else:
                        score = _parse_ai_score(body)
                        if score is not None:
                            return score
                except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
                    last_error = f"Parse error: {e}"
                    if attempt < _AI_MAX_RETRY_JSON:
                        logger.info("[ai] Parse error (attempt %s/%s): %s", attempt, _AI_MAX_RETRY_JSON, e)
                        continue
                    return None

        except httpx.TimeoutException as e:
            logger.warning("[ai] TIMEOUT after %ss (attempt %s/%s): %s", timeout_sec, attempt, _AI_MAX_RETRY_JSON, e)
            last_error = f"Timeout {timeout_sec}s"
            if attempt < _AI_MAX_RETRY_JSON:
                continue
            return None
        except httpx.HTTPError as e:
            logger.warning("[ai] HTTP error (attempt %s/%s): %s", attempt, _AI_MAX_RETRY_JSON, e)
            last_error = f"HTTP error: {e}"
            if attempt < _AI_MAX_RETRY_JSON:
                continue
            return None
        except Exception as e:
            logger.error("[ai] Unexpected error (attempt %s/%s): %s", attempt, _AI_MAX_RETRY_JSON, e, exc_info=True)
            last_error = f"Unexpected: {e}"
            if attempt < _AI_MAX_RETRY_JSON:
                continue
            return None

    if last_error:
        logger.warning("[ai] All %s attempts failed. Last error: %s", _AI_MAX_RETRY_JSON, last_error)
    return last_score


def _resolve_risk(score: int, t: dict[str, Any]) -> tuple[str, str]:
    nguy_hiem = int(t.get("nguy_hiem", 70))
    nghi_ngo = int(t.get("nghi_ngo", 30))
    if score >= nguy_hiem:
        return (
            "NGUY_HIEM",
            t.get(
                "rec_nguy_hiem",
                "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền, không cung cấp mã OTP. Hãy xóa tin nhắn và chặn số này.",
            ),
        )
    if score >= nghi_ngo:
        return (
            "NGHI_NGO",
            t.get(
                "rec_nghi_ngo",
                "Có dấu hiệu đáng ngờ. Đừng bấm link và đừng cung cấp thông tin. Hãy hỏi lại người thân hoặc gọi số tổng đài chính thức.",
            ),
        )
    return (
        "AN_TOAN",
        t.get(
            "rec_an_toan",
            "Không thấy dấu hiệu lừa đảo. Nếu có ai yêu cầu chuyển tiền hoặc mã OTP, hãy dừng lại và hỏi người thân.",
        ),
    )


def _build_signals(
    rule_reasons: list[dict[str, Any]],
    ai_score: Optional[int],
    ai_weight: float,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for r in rule_reasons:
        signals.append({
            "source": "RULE",
            "rule_code": r.get("rule_code"),
            "score": int(r.get("score") or 0),
            "reason_text": r.get("text", r.get("reason_text", "")),
            "evidence": r.get("evidence"),
        })
    if ai_score is not None:
        signals.append({
            "source": "AI",
            "rule_code": None,
            "score": int(ai_score),
            "reason_text": f"Phân tích nội dung sâu bằng AI: {int(ai_score)}/100 điểm nghi vấn lừa đảo.",
            "evidence": {"ai_score": int(ai_score), "ai_weight": float(ai_weight)},
        })
    return signals


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def execute_scan_pipeline(raw_content: str, db: Session) -> dict[str, Any]:
    """
    FR-01 Pipeline scan: 5 tầng
    - Tầng 2: Trích xuất entity & Blacklist đối chiếu
    - Tầng 3: Rule engine chấm điểm
    - Tầng 4: AI (OpenAI) gọi với timeout, retry, fail-safe BR-01-6
    - Tầng 5: Tổng hợp, giới hạn mức rủi ro khi AI vắng mặt

    BR-01-6 (AT-06, AT-G2, AT-01-4, AT-01-5, EX-01-6):
    - AI lỗi/timeout → vẫn trả Blacklist+Rule, ai_available=false
    - Nếu AI vắng mặt VÀ rule_score > 0 → tối đa NGHI_NGO, KHÔNG bao giờ AN_TOAN
    - Thêm cảnh báo mềm: "Hiện chưa phân tích sâu được nội dung, hãy thận trọng."
    - Luôn trả kết quả (không bao giờ raise), lỗi hạ tầng mới là FAILED ở tầng endpoint.
    """
    normalized_text = (raw_content or "").strip()
    thresholds = _load_thresholds(db)
    ai_weight = float(thresholds.get("ai_weight", 0.6))
    cap = int(thresholds.get("max_final_score", 100))
    nghi_ngo_thr = int(thresholds.get("nghi_ngo", 30))
    ai_timeout = int(thresholds.get("ai_timeout_seconds", 5))
    ai_sys_prompt = thresholds.get("ai_system_prompt")

    entities = extract_entities(normalized_text)

    blacklist_signals = check_entities_against_blacklist(db, entities)
    has_hard_override = any(getattr(s, "has_hard_override", False) for s in blacklist_signals if getattr(s, "matched", False))
    blacklist_floor = "AN_TOAN"
    if has_hard_override:
        blacklist_floor = "NGUY_HIEM"
    elif any(getattr(s, "matched", False) and getattr(s, "capped_risk_level", None) == "NGHI_NGO" for s in blacklist_signals):
        blacklist_floor = "NGHI_NGO"

    rule_res = run_rule_engine(normalized_text, db)
    rule_score = _clamp(int(rule_res.get("rule_score") or 0), 0, cap)
    rule_reasons = list(rule_res.get("reasons") or [])

    ai_score: Optional[int] = None
    ai_available = False
    try:
        ai_score = _call_ai(normalized_text, ai_timeout, ai_sys_prompt)
        ai_available = ai_score is not None
    except Exception as e:
        logger.error("[pipeline] _call_ai raised unexpectedly; fail-safe BR-01-6 active: %s", e, exc_info=True)
        ai_score = None
        ai_available = False

    ai_contrib = int(float(ai_score) * ai_weight) if ai_score is not None else 0
    final_score = _clamp(rule_score + ai_contrib, 0, cap)

    risk_level, recommended_action = _resolve_risk(final_score, thresholds)

    if _RISK_RANK[blacklist_floor] > _RISK_RANK[risk_level]:
        risk_level = blacklist_floor
        ref_score = thresholds["nguy_hiem"] if risk_level == "NGUY_HIEM" else thresholds["nghi_ngo"]
        _, recommended_action = _resolve_risk(ref_score, thresholds)

    if not ai_available:
        if rule_score > 0 and _RISK_RANK[risk_level] < _RISK_RANK["NGHI_NGO"]:
            risk_level = "NGHI_NGO"
            _, recommended_action = _resolve_risk(nghi_ngo_thr, thresholds)
            if final_score < nghi_ngo_thr:
                final_score = nghi_ngo_thr

        if has_hard_override and risk_level != "NGUY_HIEM":
            pass
        elif rule_score > 0 and risk_level == "AN_TOAN":
            risk_level = "NGHI_NGO"
            _, recommended_action = _resolve_risk(nghi_ngo_thr, thresholds)
            if final_score < nghi_ngo_thr:
                final_score = nghi_ngo_thr

        if _AI_SOFT_WARNING not in recommended_action:
            recommended_action = recommended_action.rstrip() + " " + _AI_SOFT_WARNING

    signals = _build_signals(rule_reasons, ai_score, ai_weight)
    for s in blacklist_signals:
        if getattr(s, "matched", False) and getattr(s, "reason_text", None):
            signals.insert(0, {
                "source": "BLACKLIST",
                "rule_code": None,
                "score": 0,
                "reason_text": s.reason_text,
                "evidence": {
                    "entity_type": getattr(s.entity, "entity_type", None) and s.entity.entity_type.value,
                    "normalized_value": getattr(s.entity, "normalized_value", None),
                    "confidence": getattr(s, "confidence", None),
                    "blacklist_source": getattr(s, "source", None) and s.source.value,
                },
            })

    if risk_level == "AN_TOAN" and not signals:
        signals.append({
            "source": "SYSTEM", "rule_code": None, "score": 0,
            "reason_text": thresholds.get("rec_an_toan", "Không thấy dấu hiệu lừa đảo. Nếu có ai yêu cầu chuyển tiền hoặc mã OTP, hãy dừng lại và hỏi người thân."),
            "evidence": None,
        })

    reasons_list = [
        {
            "source": s.get("source"),
            "text": s.get("reason_text") or "",
            "rule_code": s.get("rule_code"),
            "score": int(s.get("score") or 0),
            "evidence": s.get("evidence"),
        }
        for s in signals
    ]

    return {
        "normalized_text": normalized_text,
        "extracted_entities": [
            {
                "entity_type": getattr(e, "entity_type", None) and e.entity_type.value,
                "raw_value": getattr(e, "raw_value", None),
                "normalized_value": getattr(e, "normalized_value", None),
            }
            for e in entities
        ],
        "rule_score": rule_score,
        "ai_score": ai_score,
        "final_score": final_score,
        "risk_level": risk_level,
        "signals": signals,
        "reasons": reasons_list,
        "recommended_action": recommended_action,
        "ai_available": ai_available,
        "has_hard_override": has_hard_override,
    }
