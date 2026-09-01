import base64
import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Header, Query, Path, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import (
    ScanRequest, ScanResult, ScanSignal, ScanEntity, Device,
    ScanStatus, RiskLevel, InputType, SignalSource, EntityType,
)
from app.services.pipeline import execute_scan_pipeline
from app.schemas.scan_schemas import (
    CreateScanRequest, CreateScanResponse, ScanEntityOut, ScanReasonOut,
)

logger = logging.getLogger(__name__)
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


def _to_signal_source(src_str: Optional[str]) -> SignalSource:
    s = (src_str or "SYSTEM").upper()
    if s == "BLACKLIST":
        return SignalSource.BLACKLIST
    if s == "RULE":
        return SignalSource.RULE
    if s == "AI":
        return SignalSource.AI
    if s == "COMMUNITY":
        return SignalSource.COMMUNITY
    return SignalSource.RULE


def _to_risk_level_enum(risk_str: str) -> RiskLevel:
    s = (risk_str or "AN_TOAN").upper()
    if s == "NGUY_HIEM":
        return RiskLevel.NGUY_HIEM
    if s == "NGHI_NGO":
        return RiskLevel.NGHI_NGO
    return RiskLevel.AN_TOAN


def _to_input_type_enum(itype: str) -> InputType:
    s = (itype or "TEXT").upper()
    if s == "URL":
        return InputType.URL
    if s == "PHONE":
        return InputType.PHONE
    if s == "IMAGE":
        return InputType.IMAGE
    return InputType.TEXT


@router.post("/scans", summary="[FR-01 / EP-01] Tạo lượt quét mới (AI pipeline + fail-safe BR-01-6)")
def create_scan(
    body: CreateScanRequest,
    x_device_uid: str = Header(..., alias="X-Device-Uid", description="Định danh thiết bị"),
    db: Session = Depends(get_db),
):
    """
    FR-01: Tạo lượt quét mới, chạy full pipeline (Extract → Blacklist → Rule → AI → Aggregate).
    Luồng trạng thái:
      PENDING → PROCESSING → COMPLETED (hoặc FAILED chỉ khi lỗi hạ tầng, KHÔNG dùng cho AI lỗi).
    BR-01-6: AI lỗi/timeout → vẫn trả kết quả Blacklist+Rule, ai_available=false,
    nếu rule_score>0 thì tối đa NGHI_NGO (cấm AN_TOAN), kèm cảnh báo mềm.
    """
    try:
        device = ensure_device(db, x_device_uid, body.platform)
    except Exception as e:
        logger.error("[create_scan][INFRA] ensure_device failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi hệ thống, vui lòng thử lại sau")

    scan_req = ScanRequest(
        device_id=device.id,
        user_id=getattr(device, "user_id", None),
        input_type=_to_input_type_enum(body.input_type),
        raw_content=body.raw_content,
        normalized_text=(body.raw_content or "").strip(),
        status=ScanStatus.PENDING,
    )
    db.add(scan_req)
    try:
        db.flush()
    except Exception as e:
        logger.error("[create_scan][INFRA] Cannot insert ScanRequest: %s", e, exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Lỗi hệ thống, không thể lưu yêu cầu quét")

    scan_req.status = ScanStatus.PROCESSING
    pipeline_result = None
    infra_error = None

    try:
        pipeline_result = execute_scan_pipeline(body.raw_content, db)
    except Exception as e:
        logger.error("[create_scan][INFRA] execute_scan_pipeline raised exception: %s", e, exc_info=True)
        infra_error = e

    if infra_error is not None:
        scan_req.status = ScanStatus.FAILED
        try:
            db.commit()
        except Exception as ce:
            logger.error("[create_scan][INFRA] commit FAILED status failed: %s", ce)
            db.rollback()
        raise HTTPException(status_code=500, detail="Lỗi xử lý quét, vui lòng thử lại sau")

    try:
        scan_req.normalized_text = pipeline_result.get("normalized_text") or (body.raw_content or "").strip()

        for ent in pipeline_result.get("extracted_entities", []):
            etype_str = ent.get("entity_type") or "URL"
            try:
                etype = EntityType[etype_str] if etype_str in EntityType.__members__ else EntityType.URL
            except Exception:
                etype = EntityType.URL
            se = ScanEntity(
                scan_request_id=scan_req.id,
                entity_type=etype,
                raw_value=ent.get("raw_value") or "",
                normalized_value=ent.get("normalized_value") or "",
            )
            db.add(se)

        risk_str = pipeline_result.get("risk_level", "AN_TOAN")
        result = ScanResult(
            scan_request_id=scan_req.id,
            risk_level=_to_risk_level_enum(risk_str),
            final_score=int(pipeline_result.get("final_score") or 0),
            rule_score=int(pipeline_result.get("rule_score") or 0),
            ai_score=pipeline_result.get("ai_score"),
            ai_available=bool(pipeline_result.get("ai_available", False)),
            has_hard_override=bool(pipeline_result.get("has_hard_override", False)),
            recommended_action=pipeline_result.get("recommended_action") or "",
        )
        db.add(result)

        for sig in pipeline_result.get("signals", []):
            src = _to_signal_source(sig.get("source"))
            raw_score = sig.get("score")
            safe_score = int(raw_score) if isinstance(raw_score, (int, float)) else 0
            ss = ScanSignal(
                scan_request_id=scan_req.id,
                source=src,
                rule_code=sig.get("rule_code") if src == SignalSource.RULE else None,
                score=safe_score,
                reason_text=sig.get("reason_text") or "",
                evidence=sig.get("evidence"),
            )
            db.add(ss)

        scan_req.status = ScanStatus.COMPLETED
        scan_req.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(scan_req)
        db.refresh(result)

    except Exception as e:
        logger.error("[create_scan][INFRA] Persist results failed → FAILED status: %s", e, exc_info=True)
        db.rollback()
        scan_req.status = ScanStatus.FAILED
        try:
            db.commit()
        except Exception as ce:
            logger.error("[create_scan][INFRA] commit FAILED status failed: %s", ce)
            db.rollback()
        raise HTTPException(status_code=500, detail="Lỗi lưu kết quả quét, vui lòng thử lại sau")

    entities_out = [
        ScanEntityOut(
            entity_type=e.get("entity_type"),
            raw_value=e.get("raw_value"),
            normalized_value=e.get("normalized_value"),
        )
        for e in (pipeline_result.get("extracted_entities") or [])
    ]

    reasons_out = [
        ScanReasonOut(
            source=s.get("source"),
            text=s.get("reason_text") or "",
            rule_code=s.get("rule_code"),
            score=int(s.get("score") or 0),
            evidence=s.get("evidence"),
        )
        for s in (pipeline_result.get("signals") or [])
    ]

    resp = CreateScanResponse(
        scan_id=str(scan_req.id),
        status=str(ScanStatus.COMPLETED.value),
        input_type=body.input_type,
        raw_content=body.raw_content,
        normalized_text=scan_req.normalized_text,
        risk_level=risk_str,
        final_score=int(pipeline_result.get("final_score") or 0),
        rule_score=int(pipeline_result.get("rule_score") or 0),
        ai_score=pipeline_result.get("ai_score"),
        ai_available=bool(pipeline_result.get("ai_available", False)),
        has_hard_override=bool(pipeline_result.get("has_hard_override", False)),
        entities=entities_out,
        reasons=reasons_out,
        recommended_action=pipeline_result.get("recommended_action") or "",
        created_at=(scan_req.created_at.isoformat() + "Z") if scan_req.created_at else None,
        completed_at=(scan_req.completed_at.isoformat() + "Z") if scan_req.completed_at else None,
    )
    return resp.model_dump()


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
