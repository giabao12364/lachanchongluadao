import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

import jwt
from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import AppUser, Device

router = APIRouter()

JWT_SECRET = "lachanchongluadao-dev-secret-change-me"
JWT_ALG = "HS256"


class UpdateMePayload(BaseModel):
    display_name: Optional[str] = None


def get_current_user_id(
    authorization: Optional[str],
    x_device_uid: Optional[str],
    db: Session,
) -> UUID:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG], options={"verify_exp": False})
            if payload.get("sub"):
                return UUID(payload["sub"])
        except Exception:
            pass

    if x_device_uid:
        device = db.query(Device).filter(Device.device_uid == x_device_uid).first()
        if device is not None and device.user_id:
            return device.user_id

    raise HTTPException(status_code=401, detail="Không xác định được người dùng. Vui lòng đăng nhập hoặc cung cấp X-Device-Uid")


@router.get("/me", summary="[EP-10] Thông tin người dùng hiện tại")
def get_me(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_device_uid: Optional[str] = Header(None, alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(authorization, x_device_uid, db)
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    return {
        "id": str(user.id),
        "phone_number": user.phone_number,
        "display_name": user.display_name,
        "is_active": bool(user.is_active),
        "created_at": (user.created_at.isoformat() + "Z") if user.created_at else None,
        "updated_at": (user.updated_at.isoformat() + "Z") if user.updated_at else None,
    }


@router.patch("/me", summary="[EP-11] Đổi tên hiển thị (Auth Required)")
def update_display_name(
    payload: UpdateMePayload,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_device_uid: Optional[str] = Header(None, alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(authorization, x_device_uid, db)

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    changed = False
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="display_name không được rỗng")
        if len(name) > 100:
            raise HTTPException(status_code=400, detail="display_name tối đa 100 ký tự")
        user.display_name = name
        changed = True

    if changed:
        user.updated_at = datetime.utcnow()
        db.commit()

    return {
        "id": str(user.id),
        "phone_number": user.phone_number,
        "display_name": user.display_name,
        "is_active": bool(user.is_active),
        "updated_at": (user.updated_at.isoformat() + "Z") if user.updated_at else None,
    }
