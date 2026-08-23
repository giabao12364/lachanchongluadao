import base64
import hashlib
import hmac
import os
import random
import re
import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import AppUser, OtpRequest, Device

router = APIRouter()

JWT_SECRET = os.getenv("JWT_SECRET", "lachanchongluadao-dev-secret-change-me")
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE_MIN = 60 * 24
REFRESH_TOKEN_EXPIRE_DAYS = 30
OTP_TTL_MINUTES = 5
OTP_TEST_FIXED = os.getenv("OTP_TEST_FIXED", "123456")


class OtpRequestPayload(BaseModel):
    phone_number: str


class OtpVerifyPayload(BaseModel):
    phone_number: str
    otp_code: str
    device_name: str | None = None
    platform: str | None = None
    os_version: str | None = None
    app_version: str | None = None


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("84"):
        return "+" + digits
    if digits.startswith("0"):
        return "+84" + digits[1:]
    if phone.startswith("+"):
        return phone
    return "+84" + digits


def hash_otp(code: str) -> str:
    return hashlib.sha256((JWT_SECRET + code).encode("utf-8")).hexdigest()


def create_tokens(user_id) -> tuple[str, str]:
    now = datetime.utcnow()
    sub_id = str(user_id)
    access = jwt.encode({
        "sub": sub_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MIN)).timestamp()),
    }, JWT_SECRET, algorithm=JWT_ALG)
    refresh = jwt.encode({
        "sub": sub_id,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
    }, JWT_SECRET, algorithm=JWT_ALG)
    return access, refresh


def make_otp_code(phone: str) -> str:
    if OTP_TEST_FIXED:
        return OTP_TEST_FIXED
    return str(random.randint(100000, 999999))


def ensure_device(db: Session, device_uid: str, user_id, meta: dict | None = None):
    device = db.query(Device).filter(Device.device_uid == device_uid).first()
    if device is None:
        device = Device(
            id=uuid.uuid4(),
            device_uid=device_uid,
            platform=(meta or {}).get("platform") or "web",
            user_id=user_id,
        )
    else:
        if user_id:
            device.user_id = user_id
        if (meta or {}).get("platform"):
            device.platform = meta["platform"]
    db.add(device)
    db.flush()
    return device


@router.post("/auth/otp/request", summary="[EP-07] Yêu cầu gửi mã OTP")
def request_otp(
    payload: OtpRequestPayload,
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    phone = normalize_phone(payload.phone_number)
    code = make_otp_code(phone)
    otp_hash = hash_otp(code)

    record = OtpRequest(
        id=uuid.uuid4(),
        phone_number=phone,
        otp_hash=otp_hash,
        purpose="REGISTER_OR_LOGIN",
        attempt_count=0,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
        consumed_at=None,
    )
    db.add(record)
    db.commit()

    return {
        "message": "Đã gửi mã xác thực",
        "otp_code_debug": code,
        "expires_at": (record.expires_at.isoformat() + "Z") if record.expires_at else None,
    }


@router.post("/auth/otp/verify", summary="[EP-08] Xác thực OTP & Đăng nhập")
def verify_otp(
    payload: OtpVerifyPayload,
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    phone = normalize_phone(payload.phone_number)
    otp_hash = hash_otp(payload.otp_code)

    record = (
        db.query(OtpRequest)
        .filter(
            OtpRequest.phone_number == phone,
            OtpRequest.consumed_at.is_(None),
            OtpRequest.expires_at > datetime.utcnow(),
        )
        .order_by(OtpRequest.created_at.desc())
        .first()
    )

    if record is None:
        raise HTTPException(status_code=400, detail="OTP không hợp lệ hoặc đã hết hạn")

    if not hmac.compare_digest(record.otp_hash, otp_hash):
        record.attempt_count = (record.attempt_count or 0) + 1
        db.commit()
        if (record.attempt_count or 0) >= 5:
            record.consumed_at = datetime.utcnow()
            db.commit()
            raise HTTPException(status_code=400, detail="OTP sai quá 5 lần, yêu cầu lấy mã mới.")
        raise HTTPException(status_code=400, detail="OTP không đúng")

    record.consumed_at = datetime.utcnow()
    record.attempt_count = (record.attempt_count or 0) + 1

    user = db.query(AppUser).filter(AppUser.phone_number == phone).first()
    is_new = False
    if user is None:
        is_new = True
        default_name = f"Người dùng {phone[-4:]}"
        user = AppUser(
            id=uuid.uuid4(),
            phone_number=phone,
            display_name=default_name,
            is_active=True,
        )
        db.add(user)
        db.flush()

    meta = {
        "platform": payload.platform,
        "os_version": payload.os_version,
        "app_version": payload.app_version,
    }
    device = ensure_device(db, x_device_uid, user.id, meta)

    db.commit()
    access, refresh = create_tokens(user.id)

    return {
        "access_token": access,
        "refresh_token": refresh,
        "is_new_user": is_new,
        "user": {
            "id": str(user.id),
            "phone_number": user.phone_number,
            "display_name": user.display_name,
            "is_active": bool(user.is_active),
            "created_at": (user.created_at.isoformat() + "Z") if user.created_at else None,
        },
        "device_id": str(device.id),
    }
