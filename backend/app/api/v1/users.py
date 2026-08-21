from fastapi import APIRouter

router = APIRouter()

# EP-11 — Đổi tên hiển thị
@router.patch("/me", summary="[EP-11] Đổi tên hiển thị (Auth Required)")
def update_display_name(payload: dict):
    return {
        "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "phone_number": "+84912345678",
        "display_name": payload.get("display_name", "Người dùng")
    }