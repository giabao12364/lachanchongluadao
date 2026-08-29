from dataclasses import dataclass
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.services.rule_engine import run_rule_engine
from app.services.scan.extractor import extract_entities, ExtractedEntity
from app.models.db_models import AppConfig, BlacklistEntity, BlacklistSource


_THRESHOLD_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "nghi_ngo": 30,
    "nguy_hiem": 70,
    "ai_weight": 0.6,
    "max_final_score": 100,
    "hard_override_confidence": 90,
}
_THRESHOLD_TTL_SEC = 60


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
        _THRESHOLD_CACHE["hard_override_confidence"] = int(m.get("blacklist.hard_override_confidence", "90"))
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
    """
    Tầng 4 AI — stub gọi API (BR-01-6).
    - Đọc key từ env AI_API_KEY, nếu rỗng/"your-secret-key-here" -> trả None
    - HTTP POST timeout 3s; bất kỳ lỗi network/timeout -> trả None
    - Mong đợi response JSON {"score": 0..100}
    """
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
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )
        import urllib.error
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        except Exception:
            return None
        data = json.loads(body)
        score_str = None
        if isinstance(data, dict) and "score" in data and isinstance(data["score"], (int, float)):
            score_str = data["score"]
        elif isinstance(data, dict) and "choices" in data:
            try:
                content = data["choices"][0]["message"]["content"]
                first = content.strip()
                if first.startswith("```"):
                    first = first.strip("`")
                    if first.lower().startswith("json"):
                        first = first[4:].strip()
                sub = json.loads(first)
                if isinstance(sub, dict) and "score" in sub:
                    score_str = sub["score"]
            except Exception:
                import re
                m = re.search(r"\"score\"\s*:\s*(\d{1,3})", content or body)
                if m:
                    score_str = int(m.group(1))
        if score_str is None:
            return None
        s = int(score_str)
        return max(0, min(100, s))
    except Exception:
        return None


# =========================================================
# Tầng 2 — Blacklist check (BR-01-1, BR-01-1b, DD-01, DD-06)
# =========================================================
@dataclass
class BlacklistCheckResult:
    matched_entities: list[tuple[ExtractedEntity, BlacklistEntity]]
    has_hard_override: bool
    community_max_level: Optional[str]
    community_reason: Optional[str]
    hard_override_reason: Optional[str]


def _check_blacklist(
    entities: list[ExtractedEntity], db: Session, hard_confidence: int
) -> BlacklistCheckResult:
    matched: list[tuple[ExtractedEntity, BlacklistEntity]] = []
    has_hard_override = False
    hard_reason: Optional[str] = None
    community_hit = False

    if not entities:
        return BlacklistCheckResult([], False, None, None, None)

    normalized_values = {e.normalized_value for e in entities}
    entity_types = {e.entity_type.value for e in entities}
    rows = (
        db.query(BlacklistEntity)
        .filter(
            BlacklistEntity.is_active.is_(True),
            BlacklistEntity.normalized_value.in_(list(normalized_values)),
            BlacklistEntity.entity_type.in_(list(entity_types)),
        )
        .all()
    )
    by_key = {(r.entity_type.value, r.normalized_value): r for r in rows}

    for ent in entities:
        bl = by_key.get((ent.entity_type.value, ent.normalized_value))
        if not bl:
            continue
        matched.append((ent, bl))
        bl_src = bl.source.value if isinstance(bl.source, BlacklistSource) else str(bl.source)
        is_verified_source = bl_src in {BlacklistSource.PUBLIC_FEED.value, BlacklistSource.MANUAL.value}
        conf = int(bl.confidence or 0)
        if is_verified_source or conf >= hard_confidence:
            has_hard_override = True
            if ent.entity_type.value == "PHONE":
                hard_reason = "Số điện thoại này đã được xác nhận là lừa đảo."
            elif ent.entity_type.value in {"URL", "DOMAIN"}:
                hard_reason = "Đường link này đã được xác nhận là trang lừa đảo."
            elif ent.entity_type.value == "BANK_ACCOUNT":
                hard_reason = "Số tài khoản ngân hàng này đã được xác nhận là lừa đảo."
            else:
                hard_reason = f"Thông tin này đã được xác nhận là lừa đảo (nguồn {bl_src})."
            break
        elif bl_src == BlacklistSource.COMMUNITY.value and conf < hard_confidence:
            community_hit = True

    community_reason: Optional[str] = None
    community_level: Optional[str] = None
    if community_hit and not has_hard_override:
        ph = any(e[0].entity_type.value == "PHONE" for e in matched)
        ur = any(e[0].entity_type.value in {"URL", "DOMAIN"} for e in matched)
        bk = any(e[0].entity_type.value == "BANK_ACCOUNT" for e in matched)
        if ph:
            community_reason = "Số này đã bị một số người báo cáo là lừa đảo."
        elif ur:
            community_reason = "Đường link này đã bị một số người báo cáo là lừa đảo."
        elif bk:
            community_reason = "Tài khoản ngân hàng này đã bị một số người báo cáo là lừa đảo."
        else:
            community_reason = "Thông tin này đã bị một số người báo cáo là lừa đảo."
        community_level = "NGHI_NGO"

    return BlacklistCheckResult(matched, has_hard_override, community_level, community_reason, hard_reason)


# =========================================================
# Tầng BR-01-3 — ánh xạ final_score -> risk_level
# 0-29  AN_TOAN
# 30-69 NGHI_NGO
# 70-100 NGUY_HIEM
# =========================================================
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


def _build_signals(
    rule_reasons: list[dict[str, Any]],
    bl: BlacklistCheckResult,
    ai_score: Optional[int],
    ai_available: bool,
    db: Session,
    ai_weight: float,
) -> list[dict[str, Any]]:
    """
    Hợp nhất tín hiệu từ 3 nguồn: BLACKLIST, RULE, AI.
    Lý do BLACKLIST đứng đầu (chốt chặn cứng BR-01-1 > suy đoán AI).
    """
    signals: list[dict[str, Any]] = []
    # (1) BLACKLIST (hard override)
    if bl.has_hard_override and bl.hard_override_reason:
        entities_info = []
        for ent, row in bl.matched_entities:
            bl_src = row.source.value if isinstance(row.source, BlacklistSource) else str(row.source)
            entities_info.append({
                "entity_type": ent.entity_type.value,
                "normalized_value": ent.normalized_value,
                "source": bl_src,
                "confidence": int(row.confidence or 0),
                "report_count": int(row.report_count or 0),
            })
        signals.append({
            "source": "BLACKLIST",
            "rule_code": None,
            "score": 100,
            "reason_text": bl.hard_override_reason,
            "evidence": {"matched_entities": entities_info},
        })
    # (1b) BLACKLIST community (chưa đủ confidence)
    if (not bl.has_hard_override) and bl.community_reason:
        entities_info = []
        for ent, row in bl.matched_entities:
            bl_src = row.source.value if isinstance(row.source, BlacklistSource) else str(row.source)
            if bl_src == BlacklistSource.COMMUNITY.value:
                entities_info.append({
                    "entity_type": ent.entity_type.value,
                    "normalized_value": ent.normalized_value,
                    "confidence": int(row.confidence or 0),
                    "report_count": int(row.report_count or 0),
                })
        if entities_info:
            signals.append({
                "source": "COMMUNITY",
                "rule_code": None,
                "score": 25,
                "reason_text": bl.community_reason,
                "evidence": {"matched_entities": entities_info},
            })
    # (2) RULE
    rule_total = 0
    for r in rule_reasons:
        rule_total += int(r.get("score") or 0)
        signals.append({
            "source": "RULE",
            "rule_code": r.get("rule_code"),
            "score": int(r.get("score") or 0),
            "reason_text": r.get("reason_text", ""),
            "evidence": r.get("evidence"),
        })
    # (3) AI
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
    Pipeline 5 tầng theo BR-01 series:
      0. Normalize -> extract entities
      1. Blacklist check (BR-01-1 hard override, BR-01-1b community cap NGHI_NGO)
      2. Rule engine (BR-01-10)
      3. AI stub gọi HTTP (timeout 3s, luôn có fallback) (BR-01-6)
      4. Tổng hợp -> risk_level / final_score theo BR-01-3, BR-01-7
    """
    normalized_text = (raw_content or "").strip()
    thresholds = _load_thresholds(db)
    hard_conf = int(thresholds.get("hard_override_confidence", 90))
    ai_weight = float(thresholds.get("ai_weight", 0.6))
    cap = int(thresholds.get("max_final_score", 100))
    nghi_ngo_thr = int(thresholds.get("nghi_ngo", 30))
    nguy_hiem_thr = int(thresholds.get("nguy_hiem", 70))

    # Tầng 0 — trích thực thể
    entities = extract_entities(normalized_text)

    # Tầng 2 — Blacklist (thực hiện TRƯỚC rule/AI vì DD-01: dữ liệu đã xác minh > suy đoán)
    bl = _check_blacklist(entities, db, hard_conf)

    # Tầng 3 — Rule engine (tính điểm rule lý thuyết; nếu hard override thì score chỉ là minh bạch)
    rule_res = run_rule_engine(normalized_text, db)
    rule_score = _clamp(int(rule_res.get("rule_score") or 0), 0, cap)
    rule_reasons = list(rule_res.get("reasons") or [])

    # Tầng 4 — AI stub (bắt mọi lỗi, timeout 3s)
    ai_score: Optional[int] = None
    ai_available_config = _ai_api_key_available()
    ai_call_ok = False
    if ai_available_config:
        ai_score = _call_ai_stub(normalized_text)
        ai_call_ok = ai_score is not None
    ai_available = ai_call_ok  # true chỉ khi thực sự gọi thành công (BR-01-6)

    # --- Tổng hợp điểm ---
    if bl.has_hard_override:
        # DD-01: AI KHÔNG ĐƯỢC HẠ MỨC khi đã hard override (NGUY_HIEM 100%)
        final_score = cap
        risk_level = "NGUY_HIEM"
        recommended_action = (
            "THÔNG TIN NÀY ĐÃ ĐƯỢC XÁC NHẬN LÀ LỪA ĐẢO. "
            "TUYỆT ĐỐI KHÔNG bấm link, KHÔNG chuyển tiền, KHÔNG cung cấp OTP/mật khẩu. "
            "Gọi 113 hoặc cơ quan chức năng gần nhất nếu đã bị lừa."
        )
    else:
        ai_contrib = 0
        if ai_score is not None:
            ai_contrib = int(float(ai_score) * ai_weight)
        final_score = _clamp(rule_score + ai_contrib, 0, cap)

        # BR-01-6: AI không khả dụng + rule_score > 0 -> tối đa NGHI_NGO, CẤM trả AN_TOAN
        if (not ai_available) and rule_score > 0 and final_score < nghi_ngo_thr:
            final_score = nghi_ngo_thr

        # BR-01-1b: blacklist COMMUNITY (chưa đủ 90) -> nâng tối đa NGHI_NGO, cấm xuống AN_TOAN
        if bl.community_level == "NGHI_NGO" and final_score < nghi_ngo_thr:
            final_score = nghi_ngo_thr

        risk_level, recommended_action = _resolve_risk(final_score, thresholds)

        # BR-01-7: Không có tín hiệu (rule 0, ai None hoặc <=29, không community) -> lý do mặc định nhắc thận trọng
        # _resolve_risk đã trả về đúng văn bản AN_TOAN thận trọng; nhưng bổ sung cảnh báo mềm nếu AI thiếu
        if risk_level == "AN_TOAN":
            any_signal = bool(rule_reasons) or bool(bl.community_reason) or (ai_score is not None and ai_score >= nghi_ngo_thr)
            if not any_signal:
                recommended_action = (
                    "Không phát hiện dấu hiệu lừa đảo phổ biến. "
                    "Vẫn nên thận trọng nếu có yêu cầu chuyển tiền, bấm link lạ, chia sẻ OTP hoặc thông tin tài khoản."
                )

        # BR-01-6 cảnh báo mềm khi AI không khả dụng
        if (not ai_available) and risk_level != "NGUY_HIEM":
            suffix = " Hiện chưa phân tích sâu được nội dung, hãy thận trọng."
            if suffix.strip() not in recommended_action:
                recommended_action = recommended_action + suffix

    # BR-01-1b chặn cứng mức: nếu chỉ có community signal, không được vượt NGHI_NGO dù cộng điểm
    if (not bl.has_hard_override) and bl.community_level == "NGHI_NGO" and risk_level == "NGUY_HIEM" and final_score >= nguy_hiem_thr:
        # Kiểm tra xem chỉ nhờ cộng điểm AI/Rule chạm trần hay không: nếu chỉ cộng từ community 25 -> giữ NGHI_NGO
        # (thực tế rule score luôn tính đúng ngưỡng; nhưng đảm bảo không ép NGUY_HIEM khi chỉ có báo cáo cộng đồng dưới 90)
        non_comm_sources = [r for r in rule_reasons if int(r.get("score") or 0) >= 10]
        if not non_comm_sources and (ai_score is None or ai_score < 50):
            risk_level = "NGHI_NGO"
            final_score = _clamp(final_score, nghi_ngo_thr, nguy_hiem_thr - 1)
            recommended_action = (
                "Nội dung có dấu hiệu nghi vấn (từ báo cáo cộng đồng chưa đủ độ tin cậy để xác nhận chắc chắn). "
                "Hãy kiểm tra kỹ thông tin trước khi thao tác, không bấm link/nhập OTP tùy tiện. Hiện chưa phân tích sâu được nội dung, hãy thận trọng."
                if not ai_available
                else "Nội dung có dấu hiệu nghi vấn (từ báo cáo cộng đồng chưa đủ độ tin cậy để xác nhận chắc chắn). Hãy kiểm tra kỹ thông tin trước khi thao tác."
            )

    # Build tín hiệu minh bạch (AT-03)
    signals = _build_signals(rule_reasons, bl, ai_score, ai_available, db, ai_weight)

    # BR-01-7: nếu AN_TOAN mà signals rỗng -> đảm bảo ít nhất 1 lý do mặc định để hiển thị (minh bạch AT-03)
    if risk_level == "AN_TOAN" and not signals:
        signals.append({
            "source": "SYSTEM",
            "rule_code": None,
            "score": 0,
            "reason_text": (
                "Không phát hiện dấu hiệu lừa đảo phổ biến. "
                "Vẫn nên thận trọng nếu có yêu cầu chuyển tiền hoặc chia sẻ thông tin tài khoản/OTP."
            ),
            "evidence": None,
        })

    return {
        "normalized_text": normalized_text,
        "extracted_entities": [
            {
                "entity_type": e.entity_type.value,
                "raw_value": e.raw_value,
                "normalized_value": e.normalized_value,
            }
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
        "has_hard_override": bl.has_hard_override,
    }
