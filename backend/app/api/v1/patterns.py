"""
FR-03 EP-05 + EP-10 — Quản lý mẫu cảnh báo (ScamPattern).
T-026 nâng cấp EP-05: tìm kiếm không dấu + filter category flexible + phân trang chuẩn + empty OK.
T-028 thêm Cache Redis + invalidation tự động khi insert/update/delete ScamPattern.
"""
import base64
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.cache import (
    cache_get_active_rows,
    cache_get_detail,
    cache_invalidate_all_pattern,
    cache_set_active_rows,
    cache_set_detail,
    register_scam_pattern_cache_events,
)
from app.core.database import get_db
from app.core.utils import normalize_category_token, strip_diacritics
from app.models.db_models import ScamPattern

router = APIRouter()
logger = logging.getLogger(__name__)

# Đảm bảo event listener cache invalidation được đăng ký (nếu module cache import
# order chưa kịp hook). Gọi nhiều lần vẫn an toàn (idempotent).
register_scam_pattern_cache_events()


# ============================================================
# CURSOR HELPERS
# ============================================================
def encode_cursor(created_at: datetime, pattern_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{str(pattern_id)}"
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


# ============================================================
# FIELD ACCESS HELPERS — hoạt động trên cả ORM object và cache dict
# ============================================================
def _f(obj: Any, key: str) -> Any:
    """Lấy field key từ ORM object (getattr) HOẶC cached dict (get)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _row_created_at(row: Any) -> Optional[datetime]:
    """Parse created_at từ cache dict (created_at_iso string) hoặc ORM (datetime)."""
    if isinstance(row, dict):
        iso = row.get("created_at_iso")
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso)
        except ValueError:
            return None
    return getattr(row, "created_at", None)


def _row_id(row: Any) -> Optional[UUID]:
    raw_id = _f(row, "id")
    if raw_id is None:
        return None
    if isinstance(raw_id, UUID):
        return raw_id
    try:
        return UUID(str(raw_id))
    except ValueError:
        return None


def _row_sort_key(row: Any):
    """Key dùng để sort DESC theo (created_at, id)."""
    ca = _row_created_at(row) or datetime.min.replace(tzinfo=None)
    pid = _row_id(row) or UUID(int=0)
    if ca.tzinfo is not None:
        ca = ca.replace(tzinfo=None)
    return (ca, pid)


# ============================================================
# SEARCH + CATEGORY FILTER — hoạt động trên cả ORM và cache dict
# ============================================================
def _matches_search(row: Any, q_normalized: str) -> bool:
    """
    T-026: Search không dấu token-based AND.
    q_normalized = strip_diacritics(q.lower())
    """
    if not q_normalized:
        return True
    tokens = [t for t in q_normalized.split() if t]
    if not tokens:
        return True
    title = _f(row, "title") or ""
    desc = _f(row, "description") or ""
    cat = _f(row, "category") or ""
    haystacks = [
        strip_diacritics(title).lower(),
        strip_diacritics(desc).lower(),
        normalize_category_token(cat),
    ]
    for tok in tokens:
        if not any(tok in h for h in haystacks):
            return False
    return True


def _matches_category(row: Any, cat_token: str) -> bool:
    if not cat_token:
        return True
    return normalize_category_token(_f(row, "category") or "") == cat_token


# ============================================================
# EP-05 — GET /scam-patterns (list + search + filter + paginate)
# ============================================================
@router.get(
    "/scam-patterns",
    summary="[EP-05] Danh sách mẫu cảnh báo (T-026: search + filter + phân trang | T-028: Redis cache)",
    responses={
        200: {"description": "items + next_cursor (header X-Cache: HIT/MISS cho biết cache status)"},
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

        # --- T-028 CACHE LAYER ---
        x_cache = "MISS"
        parsed_cursor = decode_cursor(cursor) if cursor else None

        all_active_rows: List[Any] = []
        cached = cache_get_active_rows()
        if cached is not None:
            all_active_rows = cached
            x_cache = "HIT"
        else:
            orm_rows = (
                db.query(ScamPattern)
                .filter(ScamPattern.is_active == True)  # noqa: E712
                .order_by(
                    ScamPattern.created_at.desc(),
                    ScamPattern.id.desc(),
                )
                .all()
            )
            cache_set_active_rows(orm_rows)
            all_active_rows = orm_rows
            x_cache = "MISS"

        # --- CURSOR FILTER (python-side trên in-memory list, đã sort DESC) ---
        rows_after_cursor: List[Any] = []
        if parsed_cursor is None:
            rows_after_cursor = all_active_rows
        else:
            cursor_ca, cursor_pid = parsed_cursor
            # strip tz for compare
            cc_naive = cursor_ca.replace(tzinfo=None) if cursor_ca.tzinfo else cursor_ca
            for row in all_active_rows:
                r_ca = _row_created_at(row) or datetime.min.replace(tzinfo=None)
                r_ca_n = r_ca.replace(tzinfo=None) if r_ca.tzinfo else r_ca
                r_pid = _row_id(row) or UUID(int=0)
                if (r_ca_n, r_pid) < (cc_naive, cursor_pid):
                    rows_after_cursor.append(row)

        # --- T-026 PYTHON-SIDE FILTER: search không dấu + category flexible ---
        filtered_rows: List[Any] = []
        for p in rows_after_cursor:
            if not _matches_search(p, q_norm):
                continue
            if not _matches_category(p, cat_token):
                continue
            filtered_rows.append(p)

        # --- T-026 PHÂN TRANG chuẩn ---
        window = filtered_rows[: limit + 1]
        has_next = len(window) > limit
        page_items = window[:limit]

        next_cursor = None
        if has_next and page_items:
            last = page_items[-1]
            last_ca = _row_created_at(last)
            last_pid = _row_id(last)
            if last_ca is not None and last_pid is not None:
                next_cursor = encode_cursor(last_ca, last_pid)

        # --- Map ra 5 fields EP-05 chuẩn ---
        result_items: List[Dict[str, Any]] = []
        for p in page_items:
            result_items.append({
                "id": str(_f(p, "id")) if _f(p, "id") is not None else None,
                "title": _f(p, "title"),
                "category": _f(p, "category"),
                "image_url": _f(p, "image_url"),
                "description": _f(p, "description"),
            })

        body = {
            "items": result_items,
            "next_cursor": next_cursor,
        }
        return JSONResponse(
            status_code=200,
            content=body,
            headers={"X-Cache": x_cache},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("EP-05 list_scam_patterns unexpected DB error: %s", e)
        # T-026: Không cho 500 lộ traceback, trả về message rõ ràng và empty-safe
        raise HTTPException(status_code=500, detail={
            "code": "INTERNAL_ERROR",
            "message": "Không thể truy xuất danh sách mẫu cảnh báo, vui lòng thử lại sau.",
        })


# ============================================================
# EP-10 — GET /scam-patterns/{id} (chi tiết)
# ============================================================
@router.get(
    "/scam-patterns/{id}",
    summary="[EP-10] Chi tiết mẫu cảnh báo (T-027: 400/404 ẩn nháp / 200 đủ 3 khối | T-028: Redis cache)",
    responses={
        200: {"description": "Đủ 3 khối signs / example_content / recommended_action nếu active. Header X-Cache: HIT/MISS."},
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

    # --- T-028: Cache detail trước ---
    cached_detail = cache_get_detail(pattern_id)
    if cached_detail is not None:
        return JSONResponse(
            status_code=200,
            content=cached_detail,
            headers={"X-Cache": "HIT"},
        )
    x_cache = "MISS"

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

    # --- T-028: Populate cache detail cho lần gọi sau ---
    try:
        cache_set_detail(pattern)
    except Exception:
        logger.exception("EP-10 cache_set_detail failed (non-fatal): id=%s", pattern_id)

    body = {
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
    return JSONResponse(
        status_code=200,
        content=body,
        headers={"X-Cache": x_cache},
    )
