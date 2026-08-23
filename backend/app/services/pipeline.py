from sqlalchemy.orm import Session
from app.services.rule_engine import run_rule_engine


def _resolve_risk(score: int) -> tuple[str, str]:
    if score >= 80:
        return "NGUY_HIEM", "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền. Gọi tổng đài chính thức của ngân hàng/cơ quan liên quan."
    if score >= 40:
        return "NGHI_NGO", "Nội dung có dấu hiệu nghi vấn. Hãy kiểm tra kỹ thông tin trước khi thao tác, không bấm link/nhập OTP tùy tiện."
    return "AN_TOAN", "Nội dung chưa ghi nhận dấu hiệu lừa đảo rõ ràng, nhưng vẫn cần cẩn trọng với thông tin cá nhân/tài khoản."


def execute_scan_pipeline(raw_content: str, db: Session) -> dict:
    normalized_text = (raw_content or "").strip()

    rule_res = run_rule_engine(normalized_text, db)
    rule_score = int(rule_res["rule_score"] or 0)
    reasons = list(rule_res["reasons"])

    ai_score = None
    ai_available = False
    try:
        from app.core.config import settings  # noqa: F401
        if hasattr(settings, "AI_API_KEY") and settings.AI_API_KEY and settings.AI_API_KEY not in ("", "your-secret-key-here", None):
            ai_available = True
    except Exception:
        ai_available = False

    final_score = rule_score
    if ai_score is not None:
        ai_contrib = int((ai_score or 0) * 0.6)
        final_score = min(100, rule_score + ai_contrib)

    risk_level, recommended_action = _resolve_risk(final_score)

    return {
        "normalized_text": normalized_text,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "final_score": final_score,
        "risk_level": risk_level,
        "reasons": reasons,
        "recommended_action": recommended_action,
        "ai_available": ai_available,
    }
