from typing import Any, Optional
from sqlalchemy.orm import Session

from app.services.rule_engine import run_rule_engine
from app.services.scan.extractor import extract_entities
from app.services.scan.blacklist_checker import check_entities_against_blacklist  
from app.models.db_models import AppConfig


_THRESHOLD_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "nghi_ngo": 30,
    "nguy_hiem": 70,
    "ai_weight": 0.6,
    "max_final_score": 100,
}
_THRESHOLD_TTL_SEC = 60

_RISK_RANK = {"AN_TOAN": 0, "NGHI_NGO": 1, "NGUY_HIEM": 2}


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
        _THRESHOLD_CACHE["ai_weight"] = float(m.get("pipeline.ai_weight", "0.6"))
        _THRESHOLD_CACHE["max_final_score"] = int(m.get("pipeline.max_final_score", "100"))
        _THRESHOLD_CACHE["ts"] = now
    except Exception:
        pass
    return _THRESHOLD_CACHE


def _ai_api_key_available() -> bool:
    try:
        import os
        key = os.environ.get("AI_API_KEY", "")
        return bool(key) and key not in ("your-secret-key-here", "", None)
    except Exception:
        return False


def _call_ai_stub(normalized_text: str) -> Optional[int]:
    import os
    key = os.environ.get("AI_API_KEY", "") or ""
    if not key or key == "your-secret-key-here":
        return None
    endpoint = os.environ.get("AI_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    system_prompt = (
        "Bạn là hệ thống phân tích nội dung lừa đảo tiếng Việt. "
        "Trả về duy nhất JSON {'score': X} với X là số nguyên 0..100, "
        "100 là chắc chắn lừa đảo, 0 là an toàn."
    )
    user_prompt = f"Đánh giá nội dung sau (0-100 điểm, chỉ số):\n\n{normalized_text}"
    try:
        import json
        import urllib.request
        import urllib.error
        payload = json.dumps({
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "user", "content": "Trả lời DƯỚI DẠNG JSON CHỈ CÓ key score là số nguyên 0-100. Ví dụ: {\"score\": 35}"},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            endpoint, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        except Exception:
            return None
        data = json.loads(body)
        score_val = None
        if isinstance(data, dict) and "score" in data and isinstance(data["score"], (int, float)):
            score_val = data["score"]
        elif isinstance(data, dict) and "choices" in data:
            try:
                content = data["choices"][0]["message"]["content"]
                first = content.strip().strip("`")
                if first.lower().startswith("json"):
                    first = first[4:].strip()
                sub = json.loads(first)
                if isinstance(sub, dict) and "score" in sub:
                    score_val = sub["score"]
            except Exception:
                import re
                m = re.search(r"\"score\"\s*:\s*(\d{1,3})", content or body)
                if m:
                    score_val = int(m.group(1))
        if score_val is None:
            return None
        return max(0, min(100, int(score_val)))
    except Exception:
        return None


def _resolve_risk(score: int, t: dict[str, Any]) -> tuple[str, str]:
    nguy_hiem = int(t.get("nguy_hiem", 70))
    nghi_ngo = int(t.get("nghi_ngo", 30))
    if score >= nguy_hiem:
        return (
            "NGUY_HIEM",
            "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền, không cung cấp OTP/mật khẩu. Gọi tổng đài chính thức của ngân hàng/cơ quan liên quan để xác minh.",
        )
    if score >= nghi_ngo:
        return (
            "NGHI_NGO",
            "Nội dung có dấu hiệu nghi vấn. Hãy kiểm tra kỹ thông tin trước khi thao tác, không bấm link/nhập OTP tùy tiện.",
        )
    return (
        "AN_TOAN",
        "Không phát hiện dấu hiệu lừa đảo phổ biến. Vẫn nên thận trọng nếu có yêu cầu chuyển tiền, bấm link lạ hoặc chia sẻ thông tin tài khoản/OTP.",
    )


def _build_signals(rule_reasons: list[dict[str, Any]], ai_score: Optional[int], ai_weight: float) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for r in rule_reasons:
        signals.append({
            "source": "RULE",
            "rule_code": r.get("rule_code"),
            "score": int(r.get("score") or 0),
            "reason_text": r.get("reason_text", ""),
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
    normalized_text = (raw_content or "").strip()
    thresholds = _load_thresholds(db)
    ai_weight = float(thresholds.get("ai_weight", 0.6))
    cap = int(thresholds.get("max_final_score", 100))
    nghi_ngo_thr = int(thresholds.get("nghi_ngo", 30))

    entities = extract_entities(normalized_text)


    blacklist_signals = check_entities_against_blacklist(db, entities)
    has_hard_override = any(s.has_hard_override for s in blacklist_signals if s.matched)
    blacklist_floor = "AN_TOAN"
    if has_hard_override:
        blacklist_floor = "NGUY_HIEM"
    elif any(s.matched and s.capped_risk_level == "NGHI_NGO" for s in blacklist_signals):
        blacklist_floor = "NGHI_NGO"

    rule_res = run_rule_engine(normalized_text, db)
    rule_score = _clamp(int(rule_res.get("rule_score") or 0), 0, cap)
    rule_reasons = list(rule_res.get("reasons") or [])

    ai_score: Optional[int] = None
    ai_call_ok = False
    if _ai_api_key_available():
        ai_score = _call_ai_stub(normalized_text)
        ai_call_ok = ai_score is not None
    ai_available = ai_call_ok

    ai_contrib = int(float(ai_score) * ai_weight) if ai_score is not None else 0
    final_score = _clamp(rule_score + ai_contrib, 0, cap)

    if (not ai_available) and rule_score > 0 and final_score < nghi_ngo_thr:
        final_score = nghi_ngo_thr

    risk_level, recommended_action = _resolve_risk(final_score, thresholds)


    if _RISK_RANK[blacklist_floor] > _RISK_RANK[risk_level]:
        risk_level = blacklist_floor
        ref_score = thresholds["nguy_hiem"] if risk_level == "NGUY_HIEM" else thresholds["nghi_ngo"]
        _, recommended_action = _resolve_risk(ref_score, thresholds)

    if (not ai_available) and risk_level != "NGUY_HIEM":
        suffix = " Hiện chưa phân tích sâu được nội dung, hãy thận trọng."
        if suffix.strip() not in recommended_action:
            recommended_action += suffix

    signals = _build_signals(rule_reasons, ai_score, ai_weight)
    for s in blacklist_signals:
        if s.matched and s.reason_text:
            signals.insert(0, {
                "source": "BLACKLIST",
                "rule_code": None,
                "score": None,
                "reason_text": s.reason_text,
                "evidence": {
                    "entity_type": s.entity.entity_type.value,
                    "normalized_value": s.entity.normalized_value,
                    "confidence": s.confidence,
                    "blacklist_source": s.source.value if s.source else None,
                },
            })

    if risk_level == "AN_TOAN" and not signals:
        signals.append({
            "source": "SYSTEM", "rule_code": None, "score": 0,
            "reason_text": "Không phát hiện dấu hiệu lừa đảo phổ biến. Vẫn nên thận trọng nếu có yêu cầu chuyển tiền hoặc chia sẻ thông tin tài khoản/OTP.",
            "evidence": None,
        })

    return {
        "normalized_text": normalized_text,
        "extracted_entities": [
            {"entity_type": e.entity_type.value, "raw_value": e.raw_value, "normalized_value": e.normalized_value}
            for e in entities
        ],
        "rule_score": rule_score,
        "ai_score": ai_score,
        "final_score": final_score,
        "risk_level": risk_level,
        "signals": signals,
        "reasons": [s["reason_text"] for s in signals],
        "recommended_action": recommended_action,
        "ai_available": ai_available,
        "has_hard_override": has_hard_override,
    }