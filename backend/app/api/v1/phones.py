"""
EP-04 — Tra cứu số điện thoại (FR-02, T-023)
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.v1.scans import ensure_device  # tái dùng — tránh duplicate (lỗi #10 PM đã nêu)
from app.core.database import get_db
from app.services.phone.lookup_service import InvalidPhoneNumberError, lookup_phone
from app.services.phone.persistence import persist_phone_lookup

router = APIRouter()


def _ep04_error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@router.get(
    "/phones/{phone}",
    summary="[EP-04 / FR-02] Tra cứu số điện thoại",
)
def get_phone_lookup(
    phone: str = Path(..., description="Số điện thoại cần tra cứu"),
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    db: Session = Depends(get_db),
):
    """
    FR-02: Nhận số điện thoại -> chuẩn hóa E.164 (BR-01-9) -> xác định nhà
    mạng (BR-02-1/BR-02-2, T-020) -> đối chiếu blacklist (BR-02-3, T-012) ->
    trả risk_level + reasons + recommended_action. Đồng thời lưu lại lượt
    tra cứu vào scan_request/scan_result (BR-02-5, T-022) để hiện chung
    màn Lịch sử quét (FR-06).

    Không chạy Rule Engine / AI — số điện thoại không có "nội dung" ngữ
    nghĩa để chấm điểm, chỉ tra blacklist_entity (khác FR-01).

    Errors:
        422 EMPTY_CONTENT   — không truyền số điện thoại
        422 INVALID_PHONE   — số không đúng định dạng VN (BR-01-9)
    """
    if not phone or not phone.strip():
        raise _ep04_error("EMPTY_CONTENT", "Vui lòng nhập số cần tra cứu")

    device = ensure_device(db, x_device_uid)

    try:
        result = lookup_phone(db, phone)
    except InvalidPhoneNumberError:
        raise _ep04_error("INVALID_PHONE", "Số điện thoại không hợp lệ")

    scan_request = persist_phone_lookup(db, device, phone, result)
    db.commit()

    return {
        "scan_id": str(scan_request.id),
        "phone": result.phone,
        "carrier": result.carrier,
        "risk_level": result.risk_level.value,
        "reasons": result.reasons,
        "recommended_action": result.recommended_action,
    }