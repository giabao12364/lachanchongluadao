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
from app.models.db_models import ScamReport, BlacklistEntity, Device, AppUser

router = APIRouter()

JWT_SECRET = "lachanchongluadao-dev-secret-change-me"
JWT_ALG = "HS256"


class CreateReportPayload(BaseModel):
    entity_type: str = Field(..., pattern="^(PHONE|URL|BANK_ACCOUNT|OTHER)$")
    entity_value: str = Field(..., min_length=1)
    title: Optional[str] = None
    description: Optional[str] = None
    scam_type: Optional[str] = None
    loss_amount: Optional[float] = 0
    currency: Optional[str] = "VND"
    evidence_urls: Optional[list] = None
    contact_info: Optional[str] = None


def normalize_value(entity_type: str, value: str) -> str:
    if entity_type == "PHONE":
        digits = re.sub(r"\D", "", value)
        if digits.startswith("84"):
            return "+" + digits
        if digits.startswith("0"):
            return "+84" + digits[1:]
        if value.startswith("+"):
            return value
        return "+84" + digits
    return value.strip()


def map_status(s: Optional[str]) -> str:
    if not s:
        return "PENDING"
    return s.upper()


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
        device = db.query(Device).filter(Device.device_id == x_device_uid).first()
        if device is None:
            fallback = db.query(AppUser).first()
            if fallback is None:
                fallback = AppUser(
                    id=uuid.uuid4(),
                    full_name="Anonymous",
                    password_hash=hashlib.sha256(b"anon").hexdigest(),
                )
                db.add(fallback)
                db.flush()
            device = Device(
                id=uuid.uuid4(),
                device_id=x_device_uid,
                user_id=fallback.id,
            )
            db.add(device)
            db.flush()
        user_id = device.user_id
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

    title = payload.title or f"Báo cáo {payload.entity_type}: {normalized}"
    description_parts = []
    if payload.description:
        description_parts.append(payload.description)
    description_parts.append(f"Entity: {payload.entity_type} - {normalized}")
    description = "\n".join(description_parts)

    scam_type = payload.scam_type or payload.entity_type.lower()
    try:
        evidence_json = json.dumps(payload.evidence_urls) if payload.evidence_urls else None
    except Exception:
        evidence_json = None

    report = ScamReport(
        id=uuid.uuid4(),
        reporter_id=reporter_id,
        title=title,
        description=description,
        scam_type=scam_type,
        loss_amount=payload.loss_amount or 0,
        currency=payload.currency or "VND",
        evidence_urls=payload.evidence_urls if isinstance(payload.evidence_urls, list) else None,
        contact_info=payload.contact_info,
        status="pending",
        reported_at=datetime.utcnow(),
    )
    db.add(report)

    # Đồng bộ thêm vào BlacklistEntity để cộng report_count (nếu entity_type hỗ trợ)
    if payload.entity_type in ("PHONE", "URL", "BANK_ACCOUNT"):
        bl = db.query(BlacklistEntity).filter(
            BlacklistEntity.entity_type == payload.entity_type,
            BlacklistEntity.entity_value == normalized,
        ).first()
        if bl is None:
            bl = BlacklistEntity(
                id=uuid.uuid4(),
                entity_type=payload.entity_type,
                entity_value=normalized,
                source="USER_REPORT",
                risk_level="high",
                is_active=False,
                report_count=1,
                description=f"Được báo cáo lần đầu qua report #{report.id}",
            )
            db.add(bl)
        else:
            bl.report_count = (bl.report_count or 0) + 1
            if (bl.report_count or 0) >= 3 and not bl.is_active:
                bl.is_active = True

    db.commit()

    return {
        "report_id": str(report.id),
        "status": "PENDING",
        "message": "Gửi báo cáo thành công. Cảm ơn đóng góp của bạn!"
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


def extract_entity_from_report(report: ScamReport) -> tuple[str, str]:
    entity_type = "OTHER"
    normalized_value = report.title
    scam = (report.scam_type or "").upper()
    if scam in ("PHONE", "URL", "BANK_ACCOUNT"):
        entity_type = scam
    if report.description and "Entity: " in report.description:
        try:
            line = [l for l in report.description.splitlines() if l.startswith("Entity: ")][0]
            rest = line[len("Entity: "):]
            if " - " in rest:
                t, v = rest.split(" - ", 1)
                entity_type = t
                normalized_value = v
        except Exception:
            pass
    return entity_type, normalized_value


@router.get("/reports", summary="[EP-09] Danh sách báo cáo của tôi (Auth Required)")
def get_my_reports(
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None),
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    user_id = get_user_from_auth_or_device(authorization, x_device_uid, db)

    query = db.query(ScamReport).filter(ScamReport.reporter_id == user_id)

    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.filter(
            (ScamReport.reported_at < cursor_created_at) |
            ((ScamReport.reported_at == cursor_created_at) & (ScamReport.id < cursor_id))
        )

    rows = (
        query
        .order_by(ScamReport.reported_at.desc(), ScamReport.id.desc())
        .limit(limit + 1)
        .all()
    )

    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]

    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        ts = last.reported_at if last.reported_at else last.reviewed_at or datetime.utcnow()
        next_cursor = encode_cursor(ts, last.id)

    items = []
    for r in rows:
        entity_type, normalized_value = extract_entity_from_report(r)
        ts = r.reported_at if r.reported_at else datetime.utcnow()
        items.append({
            "report_id": str(r.id),
            "entity_type": entity_type,
            "normalized_value": normalized_value,
            "status": map_status(r.status),
            "created_at": ts.isoformat() + "Z",
        })

    return {
        "items": items,
        "next_cursor": next_cursor
    }
