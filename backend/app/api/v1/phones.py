import hashlib
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, Header, Path, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import (
    BlacklistEntity, ScanRequest, ScanResult, ScanEntity, Device, AppUser,
    EntityType, RiskLevel, ScanStatus, InputType,
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
    device = db.query(Device).filter(Device.device_uid == device_uid).first()
    if device:
        return device
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
        device_uid=device_uid,
        platform="web",
        user_id=fallback.id,
    )
    db.add(device)
    db.flush()
    return device


@router.get("/phones/{phone}", summary="[EP-04] Tra cứu số điện thoại")
def lookup_phone(
    phone: str = Path(..., description="Số điện thoại định dạng E.164 hoặc bất kỳ"),
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    normalized = normalize_phone(phone)
    carrier = detect_carrier(normalized)

    bl_entry = db.query(BlacklistEntity).filter(
        BlacklistEntity.entity_type == EntityType.PHONE,
        BlacklistEntity.normalized_value == normalized,
        BlacklistEntity.is_active == True,
    ).first()

    device = ensure_device(db, x_device_uid)

    reasons: List[Dict[str, Any]] = []
    risk_level_str = "AN_TOAN"
    action = "Số điện thoại chưa có trong danh sách đen, nhưng vẫn cần cẩn trọng khi giao dịch."

    if bl_entry:
        risk_level_str = "NGUY_HIEM" if (bl_entry.confidence or 0) >= 70 else "CANH_BAO"
        rc = bl_entry.report_count or 1
        reasons.append({
            "source": "BLACKLIST",
            "text": f"Số điện thoại nằm trong danh sách đen lừa đảo. Số báo cáo: {rc}. Mức độ tin cậy: {bl_entry.confidence or 0}%.",
        })
        if bl_entry.note:
            reasons.append({"source": "BLACKLIST", "text": bl_entry.note})
        action = "Cảnh báo! Số điện thoại này đã bị nhiều người báo cáo lừa đảo. Tuyệt đối không chuyển tiền."

    scan = ScanRequest(
        id=uuid.uuid4(),
        device_id=device.id,
        user_id=device.user_id,
        input_type=InputType.PHONE,
        raw_content=normalized,
        normalized_text=normalized,
        status=ScanStatus.COMPLETED,
        completed_at=datetime.utcnow(),
    )
    db.add(scan)
    db.flush()

    scan_entity = ScanEntity(
        id=uuid.uuid4(),
        scan_request_id=scan.id,
        entity_type=EntityType.PHONE,
        raw_value=normalized,
        normalized_value=normalized,
    )
    db.add(scan_entity)

    final_score = 100 if bl_entry else 0
    risk_enum = RiskLevel.NGUY_HIEM if bl_entry else RiskLevel.AN_TOAN
    db.add(ScanResult(
        id=uuid.uuid4(),
        scan_request_id=scan.id,
        risk_level=risk_enum,
        final_score=final_score,
        rule_score=final_score,
        ai_score=None,
        ai_available=True,
        has_hard_override=False,
        recommended_action=action,
    ))
    db.commit()

    return {
        "scan_id": str(scan.id),
        "phone": normalized,
        "carrier": carrier,
        "risk_level": risk_level_str,
        "final_score": final_score,
        "reasons": reasons,
        "recommended_action": action,
    }
