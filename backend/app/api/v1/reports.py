from fastapi import APIRouter, Header, Query, Depends
from typing import Optional

router = APIRouter()

# EP-06 — Gửi báo cáo lừa đảo
@router.post("/reports", summary="[EP-06] Gửi báo cáo lừa đảo (Auth Required)")
def create_report(
    payload: dict,
    x_device_uid: str = Header(..., alias="X-Device-Uid")
):
    return {
        "report_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
        "status": "PENDING",
        "message": "Gửi báo cáo thành công. Cảm ơn đóng góp của bạn!"
    }

# EP-09 — Báo cáo của tôi
@router.get("/reports", summary="[EP-09] Danh sách báo cáo của tôi (Auth Required)")
def get_my_reports(
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None)
):
    return {
        "items": [
            {
                "report_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
                "entity_type": "PHONE",
                "normalized_value": "+84912345678",
                "status": "PENDING",
                "created_at": "2026-07-16T09:12:33Z"
            }
        ],
        "next_cursor": None
    }