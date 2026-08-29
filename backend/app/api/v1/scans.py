import base64
import hashlib
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Path, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import (
    ScanRequest, ScanResult, ScanSignal, ScanEntity, ScoringRule, BlacklistEntity, Device, AppUser,
    InputType, ScanStatus, EntityType, SignalSource, RiskLevel,
)
from app.services.pipeline import execute_scan_pipeline

router = APIRouter()


class CreateScanPayload(BaseModel):
    input_type: str = Field(..., pattern="^(TEXT|URL|PHONE|FILE)$")
    content: str = Field(..., min_length=1)
    user_id: Optional[str] = None


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


def map_risk_level(level) -> str:
    if level is None:
        return "AN_TOAN"
    s = str(level).upper()
    if s in ("HIGH", "CRITICAL", "NGUY_HIEM"):
        return "NGUY_HIEM"
    if s in ("MEDIUM", "CANH_BAO", "NGHI_NGO"):
        return "NGHI_NGO"
    return "AN_TOAN"


def _to_enum_or_value(enum_cls, value, default=None):
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value).upper())
    except Exception:
        return default


def extract_entities(db: Session, content: str, input_type: str) -> List[ScanEntity]:
    entities: List[ScanEntity] = []
    import re

    phone_pattern = r"(\+?84|0)(3[2-9]|5[2689]|7[06789]|8[1-689]|9[0-46-9])[0-9]{7}"
    url_pattern = r"https?://[^\s]+"
    bank_pattern = r"(stk|số? tài khoản)\s*[:#]?\s*(\d{8,16})"

    def _find_blacklist(entity_type, normalized):
        return db.query(BlacklistEntity).filter(
            BlacklistEntity.entity_type == _to_enum_or_value(EntityType, entity_type, EntityType.OTHER),
            BlacklistEntity.normalized_value == normalized,
            BlacklistEntity.is_active == True
        ).first()

    if input_type in ("PHONE", "TEXT"):
        for m in re.finditer(phone_pattern, content):
            raw = m.group(0)
            digits = re.sub(r"\D", "", raw)
            if digits.startswith("84"):
                normalized = "+" + digits
            elif digits.startswith("0"):
                normalized = "+84" + digits[1:]
            elif raw.startswith("+"):
                normalized = raw
            else:
                normalized = "+84" + digits
            bl = _find_blacklist("PHONE", normalized)
            entities.append(ScanEntity(
                id=uuid.uuid4(),
                entity_type=EntityType.PHONE,
                raw_value=raw,
                normalized_value=normalized,
            ))

    if input_type in ("URL", "TEXT"):
        for m in re.finditer(url_pattern, content):
            raw = m.group(0)
            normalized = raw.strip().rstrip(".,;:!?)]}")
            bl = _find_blacklist("URL", normalized)
            entities.append(ScanEntity(
                id=uuid.uuid4(),
                entity_type=EntityType.URL,
                raw_value=raw,
                normalized_value=normalized,
            ))

    if input_type == "TEXT":
        for m in re.finditer(bank_pattern, content, re.IGNORECASE):
            raw = m.group(2)
            normalized = raw
            entities.append(ScanEntity(
                id=uuid.uuid4(),
                entity_type=EntityType.BANK_ACCOUNT,
                raw_value=raw,
                normalized_value=normalized,
            ))

    return entities


def ensure_device(db: Session, device_uid: str, platform: str = "web") -> Device:
    device = db.query(Device).filter(Device.device_uid == device_uid).first()
    if device:
        return device
    device = Device(
        id=uuid.uuid4(),
        device_uid=device_uid,
        platform=platform or "web",
        user_id=None,
    )
    db.add(device)
    db.flush()
    return device


def _risk_str_to_enum(risk: Optional[str]):
    if not risk:
        return RiskLevel.AN_TOAN
    r = str(risk).upper()
    if r in ("NGUY_HIEM", "CRITICAL", "HIGH"):
        return RiskLevel.NGUY_HIEM
    if r in ("NGHI_NGO", "CANH_BAO", "MEDIUM"):
        return RiskLevel.NGHI_NGO
    return RiskLevel.AN_TOAN


@router.post("/scans", summary="[EP-01] Tạo lượt quét mới")
def create_scan(
    payload: CreateScanPayload,
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    x_platform: Optional[str] = Header("web", alias="X-Platform", description="web | ios | android"),
    db: Session = Depends(get_db)
):
    device = ensure_device(db, x_device_uid, platform=x_platform or "web")
    raw_content = payload.content.strip()

    input_type_enum = _to_enum_or_value(InputType, payload.input_type, InputType.TEXT)

    pipeline_res = execute_scan_pipeline(raw_content, db)

    scan = ScanRequest(
        id=uuid.uuid4(),
        device_id=device.id,
        user_id=device.user_id,
        input_type=input_type_enum,
        raw_content=raw_content,
        normalized_text=pipeline_res.get("normalized_text", raw_content.strip()),
        status=ScanStatus.COMPLETED,
        completed_at=datetime.utcnow(),
    )
    db.add(scan)
    db.flush()

    pipe_entities = list(pipeline_res.get("extracted_entities") or [])
    if pipe_entities:
        for ent in pipe_entities:
            et = _to_enum_or_value(EntityType, str(ent.get("entity_type")).upper())
            if et is None:
                continue
            db_ent = ScanEntity(
                id=uuid.uuid4(),
                scan_request_id=scan.id,
                entity_type=et,
                raw_value=str(ent.get("raw_value") or "")[:500],
                normalized_value=str(ent.get("normalized_value") or "")[:500],
                created_at=datetime.utcnow(),
            )
            db.add(db_ent)
    else:
        legacy = extract_entities(db, raw_content, payload.input_type)
        for ent in legacy:
            ent.scan_request_id = scan.id
            db.add(ent)

    db_signals: List[ScanSignal] = []
    pipe_signals = list(pipeline_res.get("signals") or [])
    for sig in pipe_signals:
        rule_code = sig.get("rule_code")
        score_val = int(sig.get("score") or 0)
        source_str = (sig.get("source") or "RULE").upper()
        if source_str == "SYSTEM":
            source_enum = SignalSource.RULE
        else:
            source_enum = _to_enum_or_value(SignalSource, source_str, SignalSource.RULE)
        if source_enum == SignalSource.RULE and rule_code is None and source_str != "SYSTEM":
            rule_code = rule_code
        evidence = sig.get("evidence")
        if evidence is None:
            evidence = {"matched_substring": raw_content[:200]}
        reason_text = sig.get("reason_text") or "Lý do vi phạm"
        db_signals.append(ScanSignal(
            id=uuid.uuid4(),
            scan_request_id=scan.id,
            source=source_enum,
            rule_code=rule_code,
            score=min(100, max(0, score_val)),
            reason_text=reason_text,
            evidence=evidence,
        ))
    for s in db_signals:
        db.add(s)

    risk_enum = _risk_str_to_enum(pipeline_res["risk_level"])
    final_score = int(pipeline_res["final_score"] or 0)
    rule_score = int(pipeline_res.get("rule_score", final_score))
    result = ScanResult(
        id=uuid.uuid4(),
        scan_request_id=scan.id,
        risk_level=risk_enum,
        final_score=min(100, max(0, final_score)),
        rule_score=min(100, max(0, rule_score)),
        ai_score=pipeline_res.get("ai_score"),
        ai_available=bool(pipeline_res.get("ai_available", False)),
        has_hard_override=bool(pipeline_res.get("has_hard_override", False)),
        recommended_action=pipeline_res.get("recommended_action") or "",
    )
    db.add(result)

    scan.completed_at = datetime.utcnow()
    db.commit()

    reasons_out = []
    for sig in pipe_signals:
        reasons_out.append({
            "source": sig.get("source", "RULE"),
            "text": sig.get("reason_text", ""),
            "rule_code": sig.get("rule_code"),
            "score": int(sig.get("score") or 0),
            "evidence": sig.get("evidence"),
        })

    return {
        "scan_id": str(scan.id),
        "risk_level": pipeline_res["risk_level"],
        "final_score": min(100, max(0, final_score)),
        "rule_score": rule_score,
        "ai_score": pipeline_res.get("ai_score"),
        "ai_available": bool(pipeline_res.get("ai_available", False)),
        "has_hard_override": bool(pipeline_res.get("has_hard_override", False)),
        "extracted_entities": pipe_entities,
        "reasons": reasons_out,
        "recommended_action": pipeline_res["recommended_action"],
        "created_at": (scan.created_at.isoformat() + "Z") if scan.created_at else None,
        "completed_at": (scan.completed_at.isoformat() + "Z") if scan.completed_at else None,
    }


@router.get("/scans/{scan_id}", summary="[EP-02] Chi tiết lượt quét")
def get_scan_detail(
    scan_id: str = Path(..., description="ID lượt quét"),
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    try:
        sid = UUID(scan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID không đúng định dạng")

    scan = db.query(ScanRequest).filter(ScanRequest.id == sid).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Lượt quét không tồn tại")

    result = db.query(ScanResult).filter(ScanResult.scan_request_id == scan.id).first()
    entities = db.query(ScanEntity).filter(ScanEntity.scan_request_id == scan.id).all()
    signals = db.query(ScanSignal).filter(ScanSignal.scan_request_id == scan.id).all()

    reasons = []
    for s in signals:
        reasons.append({
            "source": str(s.source.value) if hasattr(s.source, "value") else str(s.source),
            "text": s.reason_text or "",
            "rule_code": s.rule_code,
            "score": int(s.score or 0),
        })

    entities_out = []
    for e in entities:
        etype = str(e.entity_type.value) if hasattr(e.entity_type, "value") else str(e.entity_type)
        bl = db.query(BlacklistEntity).filter(
            BlacklistEntity.entity_type == e.entity_type,
            BlacklistEntity.normalized_value == e.normalized_value,
            BlacklistEntity.is_active == True
        ).first()
        entities_out.append({
            "entity_type": etype,
            "raw_value": e.raw_value,
            "entity_value": e.normalized_value,
            "risk_level": map_risk_level("high" if bl else None),
            "in_blacklist": bl is not None,
            "report_count": (bl.report_count or 1) if bl else 0,
        })

    risk = "AN_TOAN"
    score = 0
    action = "Nội dung chưa thấy dấu hiệu lừa đảo nhưng vẫn cần cẩn trọng."
    rule_score = 0
    ai_score = None
    ai_available = True
    if result:
        risk = map_risk_level(result.risk_level)
        score = int(result.final_score or 0)
        rule_score = int(result.rule_score or 0)
        ai_score = result.ai_score
        ai_available = bool(result.ai_available)
        if result.recommended_action:
            action = result.recommended_action

    return {
        "scan_id": str(scan.id),
        "input_type": str(scan.input_type.value) if hasattr(scan.input_type, "value") else str(scan.input_type),
        "raw_content": scan.raw_content,
        "risk_level": risk,
        "final_score": score,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "ai_available": ai_available,
        "entities": entities_out,
        "reasons": reasons,
        "recommended_action": action,
        "created_at": (scan.created_at.isoformat() + "Z") if scan.created_at else None,
        "completed_at": (scan.completed_at.isoformat() + "Z") if scan.completed_at else None,
    }


@router.get("/scans", summary="[EP-03] Lịch sử quét")
def get_scan_history(
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None),
    x_device_uid: str = Header(..., alias="X-Device-Uid"),
    db: Session = Depends(get_db)
):
    device = ensure_device(db, x_device_uid)
    user_id = device.user_id
    if user_id is None:
        user_id = device.id

    query = db.query(ScanRequest).filter(
        (ScanRequest.device_id == device.id) | (ScanRequest.user_id == user_id)
    )

    if cursor:
        try:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            query = query.filter(
                (ScanRequest.created_at < cursor_created_at) |
                ((ScanRequest.created_at == cursor_created_at) & (ScanRequest.id < cursor_id))
            )
        except Exception:
            pass

    rows = (
        query
        .order_by(ScanRequest.created_at.desc(), ScanRequest.id.desc())
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
    for scan in rows:
        result = db.query(ScanResult).filter(ScanResult.scan_request_id == scan.id).first()
        preview = (scan.raw_content or "")[:100]
        risk = "AN_TOAN"
        if result and result.risk_level:
            risk = map_risk_level(result.risk_level)
        items.append({
            "scan_id": str(scan.id),
            "input_type": str(scan.input_type.value) if hasattr(scan.input_type, "value") else str(scan.input_type),
            "preview": preview,
            "risk_level": risk,
            "final_score": int(result.final_score or 0) if result else 0,
            "created_at": (scan.created_at.isoformat() + "Z") if scan.created_at else None,
        })

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
