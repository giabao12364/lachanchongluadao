import hashlib
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, Header, Path, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import (
    BlacklistEntity, ScanRequest, ScanResult, ScanEntity, ScoringRule, Device, AppUser
)

router = APIRouter()


class PhoneLookupScanPayload(BaseModel):
    input_type: str = Field(default="PHONE")
    content: str


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("84"):
        return "+" + digits
    if digits.startswith("0"):
        return "+84" + digits[1:]
    if phone.startswith("+"):
        return phone
    return "+84" + digits


def detect_carrier(phone: str) -> str:
    p = re.sub(r"^\+?84", "0", re.sub(r"\D", "", phone))
    if not p.startswith("0") or len(p) < 3:
        return "Không xác định"
    prefix = p[:3]
    prefix3_map = {
        "086": "Viettel", "096": "Viettel", "097": "Viettel", "098": "Viettel",
        "032": "Viettel", "033": "Viettel", "034": "Viettel", "035": "Viettel",
        "036": "Viettel", "037": "Viettel", "038": "Viettel", "039": "Viettel",
        "070": "MobiFone", "079": "MobiFone", "077": "MobiFone", "076": "MobiFone",
        "078": "MobiFone", "089": "MobiFone", "090": "MobiFone", "093": "MobiFone",
        "088": "Vinaphone", "091": "Vinaphone", "094": "Vinaphone",
        "083": "Vinaphone", "084": "Vinaphone", "085": "Vinaphone",
        "081": "Vinaphone", "082": "Vinaphone",
        "092": "Vietnamobile", "056": "Vietnamobile", "058": "Vietnamobile",
        "099": "Gmobile", "059": "Gmobile",
        "052": "Itelecom",
    }
    return prefix3_map.get(prefix, "Không xác định")


def ensure_device(db: Session, device_uid: str) -> Device:
    device = db.query(Device).filter(Device.device_id == device_uid).first()
    if device:
        return device
    fallback = db.query(AppUser).first()
    if fallback is None:
        fallback = AppUser(
            id=uuid.uuid4(),
            full_name="Anonymous",
            password_hash=hashlib.sha256(b"anon").hexdigest(),
            phone_number=None,
            email=None,
        )
        db.add(fallback)
        db.flush()
    device = Device(
        id=uuid.uuid4(),
        device_id=device_uid,
        user_id=fallback.id,
    )
    db.add(device)
    db.flush()
    return device


@router.get("/phones/{phone}", summary="[EP-04] Tra cứu số điện thoại")
def lookup_phone(
    phone: str = Path(..., description="Số điện thoại định dạng E.164"),
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    normalized = normalize_phone(phone)
    carrier = detect_carrier(normalized)

    bl_entry = db.query(BlacklistEntity).filter(
        BlacklistEntity.entity_type == "PHONE",
        BlacklistEntity.entity_value == normalized,
        BlacklistEntity.is_active == True
    ).first()

    device = ensure_device(db, x_device_uid)

    reasons: List[Dict[str, Any]] = []
    risk_level = "AN_TOAN"
    action = "Số điện thoại chưa có trong danh sách đen, nhưng vẫn cần cẩn trọng khi giao dịch."

    if bl_entry:
        risk_level = "NGUY_HIEM" if (bl_entry.risk_level or "high").lower() in ("high", "critical") else "CANH_BAO"
        reasons.append({
            "source": "BLACKLIST",
            "text": f"Số điện thoại nằm trong danh sách đen lừa đảo. Số báo cáo: {bl_entry.report_count or 0}."
        })
        if bl_entry.description:
            reasons.append({"source": "BLACKLIST", "text": bl_entry.description})
        action = "Cảnh báo! Số điện thoại này đã bị nhiều người báo cáo lừa đảo. Tuyệt đối không chuyển tiền."

    # Tạo record scan để tracking lịch sử
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    scan = ScanRequest(
        id=uuid.uuid4(),
        user_id=device.user_id,
        scan_type="PHONE",
        raw_content=normalized,
        content_hash=content_hash,
        status="completed",
        completed_at=datetime.utcnow(),
    )
    db.add(scan)
    db.flush()

    scan_entity = ScanEntity(
        id=uuid.uuid4(),
        scan_request_id=scan.id,
        entity_type="PHONE",
        entity_value=normalized,
        risk_level=bl_entry.risk_level if bl_entry else "low",
        matched_blacklist_id=bl_entry.id if bl_entry else None,
    )
    db.add(scan_entity)

    db.add(ScanResult(
        id=uuid.uuid4(),
        scan_request_id=scan.id,
        total_score=100 if bl_entry else 0,
        risk_level=risk_level,
        summary=action,
        recommended_action=action,
        is_scam=bl_entry is not None,
        confidence=0.95 if bl_entry else 0.1,
    ))
    db.commit()

    return {
        "scan_id": str(scan.id),
        "phone": normalized,
        "carrier": carrier,
        "risk_level": risk_level,
        "reasons": reasons,
        "recommended_action": action
    }
