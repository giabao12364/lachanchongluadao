"""
T-022 — Lưu lượt tra cứu số điện thoại (FR-02.8, BR-02-5)

Ghi vào scan_request (input_type=PHONE) + scan_result — dùng lại đúng 2
bảng của FR-01, KHÔNG tạo bảng phone_lookup riêng, để lượt tra số hiện
chung màn lịch sử FR-06 (Chốt mục treo #5 trong spec).
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db_models import (
    Device,
    InputType,
    RiskLevel,
    ScanRequest,
    ScanResult,
    ScanStatus,
)
from app.services.phone.lookup_service import PhoneLookupResult

# Điểm đại diện cho từng risk_level khi lưu final_score (spec không quy định
# công thức cụ thể cho FR-02 — BR-02-5 nói "risk_level do nhánh blacklist
# quyết định", nên chọn giá trị đại diện đúng khoảng của BR-01-3).
_REPRESENTATIVE_SCORE: dict[RiskLevel, int] = {
    RiskLevel.AN_TOAN: 0,
    RiskLevel.NGHI_NGO: 50,
    RiskLevel.NGUY_HIEM: 100,
}


def persist_phone_lookup(
    db: Session,
    device: Device,
    raw_phone: str,
    result: PhoneLookupResult,
) -> ScanRequest:
    """
    Lưu 1 lượt tra cứu vào scan_request + scan_result.

    Không commit — router (T-023) chịu trách nhiệm commit sau khi gọi hàm này,
    theo đúng pattern get_db() hiện có (không tự commit trong service layer).
    """
    now = datetime.utcnow()

    scan_request = ScanRequest(
        device_id=device.id,
        user_id=device.user_id,
        input_type=InputType.PHONE,
        raw_content=raw_phone,
        normalized_text=result.phone,
        status=ScanStatus.COMPLETED,
        completed_at=now,
    )
    db.add(scan_request)
    db.flush()  # cần scan_request.id trước khi tạo ScanResult (FK)

    scan_result = ScanResult(
        scan_request_id=scan_request.id,
        risk_level=result.risk_level,
        final_score=_REPRESENTATIVE_SCORE[result.risk_level],
        rule_score=result.rule_score,
        ai_score=result.ai_score,
        ai_available=result.ai_available,
        has_hard_override=result.has_hard_override,
        recommended_action=result.recommended_action,
    )
    db.add(scan_result)
    db.flush()

    return scan_request