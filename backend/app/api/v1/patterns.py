from fastapi import APIRouter, Query, Path
from typing import Optional

router = APIRouter()

# EP-05 — Danh sách mẫu cảnh báo
@router.get("/scam-patterns", summary="[EP-05] Danh sách mẫu cảnh báo")
def list_scam_patterns(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None)
):
    return {
        "items": [
            {
                "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "title": "Giả danh Công an, Viện kiểm sát đe dọa liên quan vụ án",
                "category": "mao_danh",
                "image_url": None,
                "description": "Kẻ gian giả danh cán bộ Công an..."
            }
        ],
        "next_cursor": None
    }

# EP-10 — Chi tiết mẫu cảnh báo
@router.get("/scam-patterns/{id}", summary="[EP-10] Chi tiết mẫu cảnh báo")
def get_scam_pattern_detail(id: str = Path(...)):
    return {
        "id": id,
        "title": "Giả danh Công an, Viện kiểm sát đe dọa liên quan vụ án",
        "category": "mao_danh",
        "image_url": None,
        "signs": "Dấu hiệu nhận biết...",
        "example_content": "Ví dụ thực tế...",
        "recommended_action": "Khuyến nghị xử lý...",
        "created_at": "2026-07-16T09:12:33Z"
    }