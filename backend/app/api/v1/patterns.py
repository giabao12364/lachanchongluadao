import base64
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Path, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db_models import ScamPattern

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


@router.get("/scam-patterns", summary="[EP-05] Danh sách mẫu cảnh báo")
def list_scam_patterns(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(ScamPattern).filter(ScamPattern.is_active == True)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (ScamPattern.title.ilike(like)) |
            (ScamPattern.description.ilike(like))
        )

    if category:
        query = query.filter(ScamPattern.category == category)

    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.filter(
            (ScamPattern.created_at < cursor_created_at) |
            ((ScamPattern.created_at == cursor_created_at) & (ScamPattern.id < cursor_id))
        )

    items = (
        query
        .order_by(ScamPattern.created_at.desc(), ScamPattern.id.desc())
        .limit(limit + 1)
        .all()
    )

    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    result_items = []
    for p in items:
        result_items.append({
            "id": str(p.id),
            "title": p.title,
            "category": p.category,
            "image_url": p.image_url,
            "description": p.description
        })

    return {
        "items": result_items,
        "next_cursor": next_cursor
    }


@router.get("/scam-patterns/{id}", summary="[EP-10] Chi tiết mẫu cảnh báo")
def get_scam_pattern_detail(
    id: str = Path(...),
    db: Session = Depends(get_db)
):
    try:
        pattern_id = UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID không đúng định dạng")

    pattern = db.query(ScamPattern).filter(
        ScamPattern.id == pattern_id,
        ScamPattern.is_active == True
    ).first()

    if not pattern:
        raise HTTPException(status_code=404, detail="Mẫu cảnh báo không tồn tại")

    return {
        "id": str(pattern.id),
        "title": pattern.title,
        "category": pattern.category,
        "image_url": pattern.image_url,
        "signs": pattern.signs,
        "example_content": pattern.example_content,
        "recommended_action": pattern.recommended_action,
        "created_at": pattern.created_at.isoformat() + "Z" if pattern.created_at else None
    }
