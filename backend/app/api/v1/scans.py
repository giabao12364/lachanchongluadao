import base64
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Header, Query, Path, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import (
    ScanRequest, ScanResult, ScanSignal, ScanEntity, Device,
    ScanStatus, RiskLevel,
)

router = APIRouter()


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
    if isinstance(level, RiskLevel):
        return level.value
    s = str(level).upper()
    if s in ("HIGH", "CRITICAL", "NGUY_HIEM"):
        return "NGUY_HIEM"
    if s in ("MEDIUM", "CANH_BAO", "NGHI_NGO"):
        return "NGHI_NGO"
    return "AN_TOAN"


def ensure_device(db: Session, device_uid: str, platform: str = "web") -> Device:
    device = db.query(Device).filter(Device.device_uid == device_uid).first()
    if device:
        return device
    device = Device(
        device_uid=device_uid,
        platform=platform or "web",
        user_id=None,
    )
    db.add(device)
    db.flush()
    return device


@router.get("/scans/{scan_id}", summary="[EP-02/XEM CHI TIẾT LỊCH SỬ] Chi tiết 1 lượt quét trong lịch sử")
def get_scan_detail(
    scan_id: str = Path(..., description="ID lượt quét (scan history)"),
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị (đảm bảo lịch sử của đúng người)"),
    db: Session = Depends(get_db),
):
    try:
        sid = UUID(scan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID không đúng định dạng UUID")

    device = ensure_device(db, x_device_uid)
    scan = db.query(ScanRequest).filter(ScanRequest.id == sid).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Lượt quét không tồn tại")

    if scan.device_id != device.id:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem lượt quét này")

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
            "evidence": s.evidence,
        })

    entities_out = []
    for e in entities:
        entities_out.append({
            "entity_type": str(e.entity_type.value) if hasattr(e.entity_type, "value") else str(e.entity_type),
            "raw_value": e.raw_value,
            "normalized_value": e.normalized_value,
        })

    risk = "AN_TOAN"
    score = 0
    rule_score = 0
    ai_score = None
    ai_available = False
    action = "Nội dung chưa thấy dấu hiệu lừa đảo nhưng vẫn cần cẩn trọng."
    has_hard_override = False
    if result:
        risk = map_risk_level(result.risk_level)
        score = int(result.final_score or 0)
        rule_score = int(result.rule_score or 0)
        ai_score = result.ai_score
        ai_available = bool(result.ai_available)
        has_hard_override = bool(result.has_hard_override)
        if result.recommended_action:
            action = result.recommended_action

    return {
        "scan_id": str(scan.id),
        "input_type": str(scan.input_type.value) if hasattr(scan.input_type, "value") else str(scan.input_type),
        "raw_content": scan.raw_content,
        "normalized_text": scan.normalized_text,
        "status": str(scan.status.value) if hasattr(scan.status, "value") else str(scan.status or ScanStatus.COMPLETED),
        "risk_level": risk,
        "final_score": score,
        "rule_score": rule_score,
        "ai_score": ai_score,
        "ai_available": ai_available,
        "has_hard_override": has_hard_override,
        "entities": entities_out,
        "reasons": reasons,
        "recommended_action": action,
        "created_at": (scan.created_at.isoformat() + "Z") if scan.created_at else None,
        "completed_at": (scan.completed_at.isoformat() + "Z") if scan.completed_at else None,
    }


@router.get("/scans", summary="[FR-06 / EP-03] Lịch sử quét")
def get_scan_history(
    limit: int = Query(20, le=50, ge=1, description="Số lượng dòng trả về / trang (tối đa 50)"),
    cursor: Optional[str] = Query(None, description="Token next_cursor trang trước đó"),
    risk_filter: Optional[str] = Query(None, pattern="^(AN_TOAN|NGHI_NGO|NGUY_HIEM)$", description="Lọc theo mức rủi ro (opt)"),
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    db: Session = Depends(get_db),
):
    device = ensure_device(db, x_device_uid)
    user_id = device.user_id

    query = db.query(ScanRequest).filter(
        (ScanRequest.device_id == device.id) | (ScanRequest.user_id == user_id)
    )

    if risk_filter:
        rl_map = {
            "AN_TOAN": RiskLevel.AN_TOAN,
            "NGHI_NGO": RiskLevel.NGHI_NGO,
            "NGUY_HIEM": RiskLevel.NGUY_HIEM,
        }
        enum_rl = rl_map.get(str(risk_filter).upper())
        if enum_rl is not None:
            query = query.join(
                ScanResult, ScanResult.scan_request_id == ScanRequest.id,
            ).filter(ScanResult.risk_level == enum_rl)

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

    items: List[dict] = []
    if rows:
        rids = [r.id for r in rows]
        results_map: dict = {
            s.scan_request_id: s
            for s in db.query(ScanResult).filter(ScanResult.scan_request_id.in_(rids)).all()
        }
    else:
        results_map = {}

    for scan in rows:
        result = results_map.get(scan.id)
        preview = (scan.raw_content or "")[:120]
        risk = "AN_TOAN"
        score = 0
        if result and result.risk_level is not None:
            risk = map_risk_level(result.risk_level)
            score = int(result.final_score or 0)
        items.append({
            "scan_id": str(scan.id),
            "input_type": str(scan.input_type.value) if hasattr(scan.input_type, "value") else str(scan.input_type),
            "preview": preview,
            "risk_level": risk,
            "final_score": score,
            "created_at": (scan.created_at.isoformat() + "Z") if scan.created_at else None,
            "completed_at": (scan.completed_at.isoformat() + "Z") if scan.completed_at else None,
        })

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_next": has_next,
        "limit": limit,
    }
