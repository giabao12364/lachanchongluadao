from fastapi import APIRouter, Header

router = APIRouter()

# EP-07 — Yêu cầu OTP
@router.post("/auth/otp/request", summary="[EP-07] Yêu cầu gửi mã OTP")
def request_otp(
    payload: dict,
    x_device_uid: str = Header(..., alias="X-Device-Uid")
):
    return {"message": "Đã gửi mã xác thực"}

# EP-08 — Xác thực OTP
@router.post("/auth/otp/verify", summary="[EP-08] Xác thực OTP & Đăng nhập")
def verify_otp(
    payload: dict,
    x_device_uid: str = Header(..., alias="X-Device-Uid")
):
    return {
        "access_token": "eyJhbGciOiJIUzI1Ni...",
        "refresh_token": "eyJhbGciOiJIUzI1Ni...",
        "is_new_user": False
    }