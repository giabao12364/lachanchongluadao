"""
FR-03 EP-05 + EP-10 — Quản lý mẫu cảnh báo (ScamPattern).
T-026 nâng cấp EP-05: tìm kiếm không dấu + filter category flexible + phân trang chuẩn + empty OK.
"""
import base64
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Query, Path, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import strip_diacritics, normalize_category_token
from app.models.db_models import ScamPattern

router = APIRouter()
logger = logging.getLogger(__name__)


def encode_cursor(created_at: datetime, id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{str(id)}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str):
    try:
        raw = base64.b64decode(cursor.encode("utf-8")).decode("utf-8")
        created_at_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(created_at_str), UUID(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_CURSOR",
            "message": "Cursor phân trang không hợp lệ",
        })


def _matches_search(pattern: ScamPattern, q_normalized: str) -> bool:
    """
    T-026: Search không dấu trên title + description + category.
    q_normalized: keyword user đã strip_diacritics + lower.
    Match theo TOKEN-BASED (không phải substring):
      - Split query thành các token theo khoảng trắng.
      - MỌI token phải xuất hiện trong ít nhất 1 trong 3 field
        (đã normalize theo cùng cách).
    """
    if not q_normalized:
        return True
    tokens = [t for t in q_normalized.split() if t]
    if not tokens:
        return True
    haystacks = [
        strip_diacritics(pattern.title or "").lower(),
        strip_diacritics(pattern.description or "").lower(),
        normalize_category_token(pattern.category or ""),
    ]
    for tok in tokens:
        if not any(tok in h for h in haystacks):
            return False
    return True


def _matches_category(pattern: ScamPattern, cat_token: str) -> bool:
    """
    T-026: Filter category linh hoạt.
    Normalize cả 2 phía (user input + pattern.category) trước khi so sánh.
    """
    if not cat_token:
        return True
    return normalize_category_token(pattern.category or "") == cat_token


@router.get(
    "/scam-patterns",
    summary="[EP-05] Danh sách mẫu cảnh báo (T-026: search không dấu + filter category + phân trang)",
    responses={
        200: {"description": "Trả về items + next_cursor (có thể rỗng = hết trang)"},
        400: {"description": "cursor / limit không hợp lệ"},
    },
)
def list_scam_patterns(
    q: Optional[str] = Query(
        None,
        description="Từ khóa tìm kiếm (title / description / category) — hỗ trợ cả Tiếng Việt CÓ DẤU và KHÔNG DẤU.",
    ),
    category: Optional[str] = Query(
        None,
        description="Lọc theo category (linh hoạt: 'Mạo danh' / 'mao_danh' / 'Mao-Danh' đều match).",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=50,
        description="Số dòng / trang (1 - 50). Mặc định 20.",
    ),
    cursor: Optional[str] = Query(
        None,
        description="Token next_cursor từ response trang trước để lấy trang kế tiếp.",
    ),
    db: Session = Depends(get_db),
):
    try:
        # --- T-026 PRE-PROCESS input ---
        q_norm = ""
        if q and q.strip():
            q_norm = strip_diacritics(q.strip()).lower()

        cat_token = ""
        if category and category.strip():
            cat_token = normalize_category_token(category)

        # --- DB query: load TẤT CẢ active pattern (số lượng < 500 nên không vấn đề)
        #    + apply cursor (DB-side) để giới hạn data load
        query = db.query(ScamPattern).filter(ScamPattern.is_active == True)  # noqa: E712

        if cursor:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            query = query.filter(
                (ScamPattern.created_at < cursor_created_at)
                | (
                    (ScamPattern.created_at == cursor_created_at)
                    & (ScamPattern.id < cursor_id)
                )
            )

        # ORDER DB-side cho đúng thứ tự trước khi filter python
        rows = (
            query.order_by(
                ScamPattern.created_at.desc(),
                ScamPattern.id.desc(),
            )
            # Load nhiều hơn 1 chút để đảm bảo sau filter python vẫn đủ dữ liệu trang;
            # với T-026 (active pattern <500) limit 500 là safe
            .limit(500).all()
        )

        # --- T-026 PYTHON-SIDE FILTER: search không dấu + category flexible
        filtered_rows: List[ScamPattern] = []
        for p in rows:
            if not _matches_search(p, q_norm):
                continue
            if not _matches_category(p, cat_token):
                continue
            filtered_rows.append(p)

        # --- T-026 PHÂN TRANG chuẩn (giống EP-03 list scans)
        # Lấy limit+1 để phát hiện has_next
        window = filtered_rows[: limit + 1]
        has_next = len(window) > limit
        page_items = window[:limit]

        next_cursor = None
        if has_next and page_items:
            last = page_items[-1]
            if last.created_at is not None:
                next_cursor = encode_cursor(last.created_at, last.id)

        # --- Map ra 5 fields EP-05 chuẩn (id, title, category, image_url, description)
        result_items: List[Dict[str, Any]] = []
        for p in page_items:
            result_items.append({
                "id": str(p.id),
                "title": p.title,
                "category": p.category,
                "image_url": p.image_url,
                "description": p.description,
            })

        return {
            "items": result_items,
            "next_cursor": next_cursor,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("EP-05 list_scam_patterns unexpected DB error: %s", e)
        # T-026: Không cho 500 lộ traceback, trả về message rõ ràng và empty-safe
        raise HTTPException(status_code=500, detail={
            "code": "INTERNAL_ERROR",
            "message": "Không thể truy xuất danh sách mẫu cảnh báo, vui lòng thử lại sau.",
        })


@router.get(
    "/scam-patterns/{id}",
    summary="[EP-10] Chi tiết mẫu cảnh báo",
    responses={
        200: {"description": "Đủ 3 khối signs / example_content / recommended_action nếu active"},
        400: {"description": "ID sai định dạng UUID"},
        404: {"description": "Pattern không tồn tại / đang nháp is_active=false"},
    },
)
def get_scam_pattern_detail(
    id: str = Path(..., description="ID mẫu cảnh báo (UUID)"),
    db: Session = Depends(get_db),
):
    try:
        pattern_id = UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_ID",
            "message": "ID không đúng định dạng UUID",
        })

    try:
        pattern = db.query(ScamPattern).filter(
            ScamPattern.id == pattern_id,
            ScamPattern.is_active == True,  # noqa: E712
        ).first()
    except Exception as e:
        logger.exception("EP-10 get_scam_pattern_detail DB error: %s", e)
        raise HTTPException(status_code=500, detail={
            "code": "INTERNAL_ERROR",
            "message": "Không thể truy xuất chi tiết mẫu cảnh báo, vui lòng thử lại sau.",
        })

    if not pattern:
        raise HTTPException(status_code=404, detail={
            "code": "SCAM_PATTERN_NOT_FOUND",
            "message": "Mẫu cảnh báo không tồn tại",
        })

    return {
        "id": str(pattern.id),
        "title": pattern.title,
        "category": pattern.category,
        "image_url": pattern.image_url,
        "signs": pattern.signs,
        "example_content": pattern.example_content,
        "recommended_action": pattern.recommended_action,
        "created_at": (
            pattern.created_at.isoformat() + "Z" if pattern.created_at else None
        ),
    }
