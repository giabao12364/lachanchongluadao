from fastapi import APIRouter, Header, Query, Path, Depends
from typing import Optional

router = APIRouter()

# EP-01 — Tạo lượt quét
@router.post("/scans", summary="[EP-01] Tạo lượt quét")
def create_scan(
    payload: dict,
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị")
):
    return {
        "scan_id": "8f3e...e21",
        "risk_level": "NGUY_HIEM",
        "final_score": 100,
        "reasons": [
            {"source": "RULE", "text": "Tin nhắn mạo danh ngân hàng.", "rule_code": "R_IMPERSONATE_BANK"}
        ],
        "recommended_action": "Rất có thể là lừa đảo. Không bấm link, không chuyển tiền.",
        "ai_available": True,
        "created_at": "2026-07-16T09:12:33Z"
    }

# EP-02 — Chi tiết một lượt quét
@router.get("/scans/{scan_id}", summary="[EP-02] Chi tiết lượt quét")
def get_scan_detail(
    scan_id: str = Path(..., description="ID lượt quét"),
    x_device_uid: str = Header(..., alias="X-Device-Uid")
):
    return {
        "scan_id": scan_id,
        "risk_level": "AN_TOAN",
        "final_score": 10,
        "entities": [],
        "reasons": [],
        "recommended_action": "Nội dung chưa thấy dấu hiệu lừa đảo nhưng vẫn cần cẩn trọng.",
        "ai_available": True,
        "created_at": "2026-07-16T09:12:33Z"
    }

# EP-03 — Lịch sử quét
@router.get("/scans", summary="[EP-03] Lịch sử quét")
def get_scan_history(
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None),
    x_device_uid: str = Header(..., alias="X-Device-Uid")
):
    return {
        "items": [
            {
                "scan_id": "8f3e...e21",
                "input_type": "TEXT",
                "preview": "Cảnh báo tài khoản Vietcombank...",
                "risk_level": "NGUY_HIEM",
                "created_at": "2026-07-16T09:12:33Z"
            }
        ],
        "next_cursor": None
    }