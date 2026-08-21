from fastapi import APIRouter, Header, Path

router = APIRouter()

# EP-04 — Tra cứu số điện thoại
@router.get("/phones/{phone}", summary="[EP-04] Tra cứu số điện thoại")
def lookup_phone(
    phone: str = Path(..., description="Số điện thoại định dạng E.164"),
    x_device_uid: str = Header(..., alias="X-Device-Uid")
):
    return {
        "scan_id": "3c9e...a11",
        "phone": phone,
        "carrier": "Viettel",
        "risk_level": "NGUY_HIEM",
        "reasons": [{"source": "BLACKLIST", "text": "Số điện thoại nằm trong danh sách đen lừa đảo"}],
        "recommended_action": "Cảnh báo! Số điện thoại này đã bị nhiều người báo cáo lừa đảo."
    }