import base64
import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

import jwt
from fastapi import APIRouter, Header, Query, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import (
    ScamReport, BlacklistEntity, Device, AppUser,
    EntityType, ReportStatus, BlacklistSource,
)

router = APIRouter()

JWT_SECRET = "lachanchongluadao-dev-secret-change-me"
JWT_ALG = "HS256"


class CreateReportPayload(BaseModel):
    entity_type: str = Field(..., pattern="^(PHONE|URL|BANK_ACCOUNT|EMAIL|OTHER)$")
    entity_value: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)


def normalize_value(entity_type: str, value: str) -> str:
    v = value.strip()
    if entity_type == "PHONE":
        digits = re.sub(r"\D", "", v)
        if digits.startswith("84"):
            return "+" + digits
        if digits.startswith("0"):
            return "+84" + digits[1:]
        if v.startswith("+"):
            return v
        return "+84" + digits
    return v


def map_status(s) -> str:
    if s is None:
        return "PENDING"
    return str(s).upper()


def _to_entity_type(v):
    try:
        return EntityType(str(v).upper())
    except Exception:
        return EntityType.OTHER


def get_user_from_auth_or_device(
    authorization: Optional[str],
    x_device_uid: str,
    db: Session,
) -> UUID:
    user_id: Optional[UUID] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG], options={"verify_exp": False})
            if payload.get("sub"):
                user_id = UUID(payload["sub"])
        except Exception:
            user_id = None

    if user_id is None:
        device = db.query(Device).filter(Device.device_uid == x_device_uid).first()
        if device is None:
            fallback = db.query(AppUser).first()
            if fallback is None:
                fallback = AppUser(
                    id=uuid.uuid4(),
                    phone_number="",
                    display_name="Anonymous",
                    is_active=True,
                )
                db.add(fallback)
                db.flush()
            device = Device(
                id=uuid.uuid4(),
                device_uid=x_device_uid,
                platform="web",
                user_id=fallback.id,
            )
            db.add(device)
            db.flush()
        if device.user_id:
            user_id = device.user_id
        else:
            fallback = db.query(AppUser).first()
            if fallback is None:
                fallback = AppUser(
                    id=uuid.uuid4(),
                    phone_number="",
                    display_name="Anonymous",
                    is_active=True,
                )
                db.add(fallback)
                db.flush()
            device.user_id = fallback.id
            db.flush()
            user_id = fallback.id
    return user_id


@router.post("/reports", summary="[EP-06] Gửi báo cáo lừa đảo (Auth Required)")
def create_report(
    payload: CreateReportPayload,
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    reporter_id = get_user_from_auth_or_device(authorization, x_device_uid, db)
    normalized = normalize_value(payload.entity_type, payload.entity_value)
    entity_type_enum = _to_entity_type(payload.entity_type)

    report = ScamReport(
        id=uuid.uuid4(),
        user_id=reporter_id,
        entity_type=entity_type_enum,
        normalized_value=normalized,
        description=payload.description,
        status=ReportStatus.PENDING,
    )
    try:
        db.add(report)
        db.commit()
    except Exception as exc:
        db.rollback()
        msg = str(exc).lower()
        if "uq_scam_report_user_entity_value" in msg or "unique" in msg:
            raise HTTPException(status_code=409, detail="Bạn đã báo cáo nội dung này trước đó.")
        raise HTTPException(status_code=400, detail=f"Không thể lưu báo cáo: {exc}")

    if payload.entity_type in ("PHONE", "URL", "BANK_ACCOUNT"):
        bl = db.query(BlacklistEntity).filter(
            BlacklistEntity.entity_type == entity_type_enum,
            BlacklistEntity.normalized_value == normalized,
        ).first()
        if bl is None:
            bl = BlacklistEntity(
                id=uuid.uuid4(),
                entity_type=entity_type_enum,
                normalized_value=normalized,
                source=BlacklistSource.USER_REPORT,
                confidence=50,
                report_count=1,
                is_active=False,
                note=f"Báo cáo lần đầu qua report #{report.id}",
            )
            db.add(bl)
        else:
            bl.report_count = (bl.report_count or 0) + 1
            if (bl.report_count >= 3) and not bl.is_active:
                bl.is_active = True
                bl.confidence = 70
        try:
            db.commit()
        except Exception:
            db.rollback()

    return {
        "report_id": str(report.id),
        "entity_type": str(report.entity_type.value) if hasattr(report.entity_type, "value") else str(report.entity_type),
        "normalized_value": report.normalized_value,
        "status": map_status(report.status),
        "message": "Gửi báo cáo thành công. Cảm ơn đóng góp của bạn! (Đủ 3 report độc lập sẽ auto-active vào blacklist)"
    }


def encode_cursor(created_at: datetime, id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{str(id)}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str):
    try:
        raw = base64.b64decode(cursor.encode("utf-8")).decode("utf-8")
        created_at_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(created_at_str), UUID(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Cursor không hợp lệ")


@router.get("/reports", summary="[EP-09] Danh sách báo cáo của tôi (Auth Required)")
def get_my_reports(
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None),
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    user_id = get_user_from_auth_or_device(authorization, x_device_uid, db)

    query = db.query(ScamReport).filter(ScamReport.user_id == user_id)

    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.filter(
            (ScamReport.created_at < cursor_created_at) |
            ((ScamReport.created_at == cursor_created_at) & (ScamReport.id < cursor_id))
        )

    rows = (
        query
        .order_by(ScamReport.created_at.desc(), ScamReport.id.desc())
        .limit(limit + 1)
        .all()
    )

    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]

    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        ts = last.created_at or datetime.utcnow()
        next_cursor = encode_cursor(ts, last.id)

    items = []
    for r in rows:
        etype = str(r.entity_type.value) if hasattr(r.entity_type, "value") else str(r.entity_type)
        ts = r.created_at or datetime.utcnow()
        items.append({
            "report_id": str(r.id),
            "entity_type": etype,
            "normalized_value": r.normalized_value,
            "status": map_status(r.status),
            "description": r.description or "",
            "created_at": ts.isoformat() + "Z",
        })

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
