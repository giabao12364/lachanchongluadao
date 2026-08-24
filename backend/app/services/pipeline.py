from typing import Optional
from sqlalchemy.orm import Session
from app.services.rule_engine import run_rule_engine
from app.models.db_models import AppConfig


_THRESHOLD_CACHE: dict = {
    "ts": 0.0,
    "nghi_ngo": 40,
    "nguy_hiem": 80,
    "ai_weight": 0.6,
    "max_final_score": 100,
}
_THRESHOLD_TTL_SEC = 60


def _load_thresholds(db: Session) -> dict:
    import time
    now = time.time()
    if now - _THRESHOLD_CACHE["ts"] < _THRESHOLD_TTL_SEC:
        return _THRESHOLD_CACHE
    try:
        rows = db.query(AppConfig).all()
        m = {r.key: r.value for r in rows}
        _THRESHOLD_CACHE["nghi_ngo"] = int(m.get("threshold.nghi_ngo", "40"))
        _THRESHOLD_CACHE["nguy_hiem"] = int(m.get("threshold.nguy_hiem", "80"))
        _THRESHOLD_CACHE["ai_weight"] = float(m.get("pipeline.ai_weight", "0.6"))
        _THRESHOLD_CACHE["max_final_score"] = int(m.get("pipeline.max_final_score", "100"))
        _THRESHOLD_CACHE["ts"] = now
    except Exception:
        pass
    return _THRESHOLD_CACHE


def _resolve_risk(score: int, t: dict) -> tuple[str, str]:
    nguy_hiem = int(t.get("nguy_hiem", 80))
    nghi_ngo = int(t.get("nghi_ngo", 40))
    if score >= nguy_hiem:
        return "NGUY_HIEM", "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền. Gọi tổng đài chính thức của ngân hàng/cơ quan liên quan."
    if score >= nghi_ngo:
        return "NGHI_NGO", "Nội dung có dấu hiệu nghi vấn. Hãy kiểm tra kỹ thông tin trước khi thao tác, không bấm link/nhập OTP tùy tiện."
    return "AN_TOAN", "Nội dung chưa ghi nhận dấu hiệu lừa đảo rõ ràng, nhưng vẫn cần cẩn trọng với thông tin cá nhân/tài khoản."


def _ai_api_key_available() -> bool:
    try:
        import os
        key = os.environ.get("AI_API_KEY", "")
        if key and key not in ("your-secret-key-here",):
            return True
    except Exception:
        return False
    return False


def execute_scan_pipeline(raw_content: str, db: Session) -> dict:
    normalized_text = (raw_content or "").strip()

    rule_res = run_rule_engine(normalized_text, db)
    rule_score = int(rule_res["rule_score"] or 0)
    reasons = list(rule_res["reasons"])

    ai_score: Optional[int] = None
    ai_available = _ai_api_key_available()

    thresholds = _load_thresholds(db)
    ai_weight = float(thresholds.get("ai_weight", 0.6))
    cap = int(thresholds.get("max_final_score", 100))

    final_score = rule_score
    if ai_score is not None:
        ai_contrib = int((ai_score or 0) * ai_weight)
        final_score = min(cap, rule_score + ai_contrib)
    final_score = min(cap, max(0, final_score))
    rule_score = min(cap, max(0, rule_score))

    risk_level, recommended_action = _resolve_risk(final_score, thresholds)

    return {
        "normalized_text": normalized_text,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "final_score": final_score,
        "risk_level": risk_level,
        "reasons": reasons,
        "recommended_action": recommended_action,
        "ai_available": ai_available,
        "has_hard_override": False,
    }
