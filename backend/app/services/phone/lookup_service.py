"""
FR-02 — Tra cứu số điện thoại (T-021)

Logic tra cứu: chuẩn hóa E.164 (BR-01-9) + đối chiếu blacklist (BR-02-3)
+ ánh xạ risk_level + khuyến nghị (BR-02-6).

Khác FR-01: FR-02 KHÔNG chạy Rule Engine / AI (số điện thoại không có
"nội dung" ngữ nghĩa để chấm điểm), chỉ tra blacklist_entity.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.db_models import EntityType, RiskLevel
from app.services.phone.carrier_service import UNKNOWN_CARRIER, get_carrier
from app.services.scan.blacklist_checker import check_entity_against_blacklist
from app.services.scan.extractor import ExtractedEntity, normalize_phone_to_e164


class InvalidPhoneNumberError(ValueError):
    """Số điện thoại sai định dạng VN (BR-01-9) — tầng API dùng để trả 422 INVALID_PHONE."""

# BR-02-6 — Gợi ý hành động theo risk_level (dùng chung văn phong BR-01-11)
_RECOMMENDED_ACTION: dict[RiskLevel, str] = {
    RiskLevel.AN_TOAN: (
        "Không tìm thấy dấu hiệu lừa đảo. Nếu người gọi yêu cầu chuyển tiền "
        "hoặc mã OTP, hãy dừng lại và hỏi người thân."
    ),
    RiskLevel.NGHI_NGO: (
        "Số này có dấu hiệu đáng ngờ. Hãy thận trọng, không cung cấp thông tin "
        "hay chuyển tiền."
    ),
    RiskLevel.NGUY_HIEM: (
        "Rất có thể là lừa đảo. Không cung cấp thông tin cá nhân, không chuyển "
        "tiền, không cung cấp mã OTP."
    ),
}


@dataclass
class PhoneLookupResult:
    phone: str  # E.164
    carrier: str
    risk_level: RiskLevel
    reasons: list[dict[str, str]]
    recommended_action: str
    # BR-02-5 — dùng để ghi vào scan_result
    rule_score: int
    ai_score: int | None
    ai_available: bool
    has_hard_override: bool


def lookup_phone(db: Session, raw_phone: str) -> PhoneLookupResult:
    """
    Thực hiện tra cứu số điện thoại theo FR-02 (02.4, 02.5).
    Raises:
        InvalidPhoneNumberError: raw_phone không đúng định dạng VN (BR-01-9).
    """
    e164 = normalize_phone_to_e164(raw_phone)
    if e164 is None:
        raise InvalidPhoneNumberError(raw_phone)

    carrier = get_carrier(e164)

    entity = ExtractedEntity(
        entity_type=EntityType.PHONE,
        raw_value=raw_phone,
        normalized_value=e164,
    )
    signal = check_entity_against_blacklist(db, entity)

    # BR-02-3 — Ánh xạ kết quả từ Blacklist (áp BR-01-1 về độ tin cậy)
    if not signal.matched:
        risk_level = RiskLevel.AN_TOAN
    elif signal.has_hard_override:
        risk_level = RiskLevel.NGUY_HIEM
    else:
        risk_level = signal.capped_risk_level or RiskLevel.NGHI_NGO

    reasons: list[dict[str, str]] = []
    if carrier != UNKNOWN_CARRIER:
        reasons.append({"source": "CARRIER", "text": f"Nhà mạng: {carrier}"})
    else:
        reasons.append({"source": "CARRIER", "text": "Không xác định được nhà mạng"})

    if signal.matched and signal.reason_text:
        reasons.append({"source": "BLACKLIST", "text": signal.reason_text})
    elif risk_level == RiskLevel.AN_TOAN:
        # FR-02.5/.6: AN_TOAN luôn kèm nhắc thận trọng, không khẳng định tuyệt đối
        reasons.append({
            "source": "SYSTEM",
            "text": (
                "Không tìm thấy dấu hiệu lừa đảo với số này. Vẫn nên thận trọng "
                "nếu có yêu cầu chuyển tiền hoặc mã OTP."
            ),
        })

    return PhoneLookupResult(
        phone=e164,
        carrier=carrier,
        risk_level=risk_level,
        reasons=reasons,
        recommended_action=_RECOMMENDED_ACTION[risk_level],
        rule_score=0,       # BR-02-5: FR-02 không chạy Rule engine
        ai_score=None,      # BR-02-5: FR-02 không chạy AI
        ai_available=True,  # BR-02-5: cố định true (không phải "AI đang chạy")
        has_hard_override=signal.has_hard_override,
    )