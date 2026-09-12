"""
T-028 FR-03 — Cache Redis cho EP-05 list & EP-10 detail ScamPattern
=====================================================================
+ Cache 2 lớp:
  1. KEY_ACTIVE_ROWS — ALL rows is_active=true (list[dict]) → EP-05 dùng trực tiếp
  2. KEY_DETAIL(id)  — 1 bản chi tiết dict → EP-10 dùng trực tiếp

+ Auto invalidation bằng SQLAlchemy event listener:
   after_insert / after_update / after_delete trên Model ScamPattern
   → flush cache (CMS cập nhật thấy ngay, không chờ TTL)

+ TTL dự phòng: 300s (5 phút) để cache tự hết hạn nếu có sự cố event listener
  (hoặc DB bị mutate bên ngoài ORM).
"""
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import redis
from dotenv import load_dotenv
from sqlalchemy import event

from app.core.database import Base  # noqa: F401  (đảm bảo Base được load trước event)

if TYPE_CHECKING:
    from app.models.db_models import ScamPattern  # pragma: no cover


load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CACHE_VERSION = "v1"
KEY_PREFIX = f"cache:{CACHE_VERSION}:scam_patterns"
KEY_ACTIVE_ROWS = f"{KEY_PREFIX}:active_rows"
KEY_DETAIL_PREFIX = f"{KEY_PREFIX}:detail:"

ACTIVE_ROWS_TTL = 300
DETAIL_TTL = 300

_cache_client = redis.from_url(REDIS_URL, decode_responses=True)


def _detail_key(pattern_id: str | uuid.UUID) -> str:
    return f"{KEY_DETAIL_PREFIX}{str(pattern_id)}"


# ============================================================
# SERIALIZE — ScamPattern → JSON-safe dict (suitable cho Redis JSON)
# ============================================================
def serialize_active_row(p: "ScamPattern") -> Dict[str, Any]:
    """Tối đa hóa data lưu trong 1 dòng active để EP-05, EP-10 đều dùng được."""
    created_iso: Optional[str] = None
    if getattr(p, "created_at", None) is not None:
        created_iso = p.created_at.isoformat()
    return {
        "id": str(p.id),
        "title": p.title,
        "category": p.category,
        "image_url": p.image_url,
        "description": p.description,
        "signs": p.signs,
        "example_content": p.example_content,
        "recommended_action": p.recommended_action,
        "created_at_iso": created_iso,
    }


def serialize_detail(p: "ScamPattern") -> Dict[str, Any]:
    """Dict chính xác format EP-10 response để cache lấy ra return luôn."""
    created_z: Optional[str] = None
    if getattr(p, "created_at", None) is not None:
        created_z = p.created_at.isoformat() + "Z"
    return {
        "id": str(p.id),
        "title": p.title,
        "category": p.category,
        "image_url": p.image_url,
        "signs": p.signs,
        "example_content": p.example_content,
        "recommended_action": p.recommended_action,
        "created_at": created_z,
    }


# ============================================================
# GET / SET / INVALIDATE helpers
# ============================================================
def cache_get_active_rows() -> Optional[List[Dict[str, Any]]]:
    """Trả về list các active rows dict đã serialize (hoặc None = cache miss)."""
    raw = _cache_client.get(KEY_ACTIVE_ROWS)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        _cache_client.delete(KEY_ACTIVE_ROWS)
    return None


def cache_set_active_rows(all_active_rows: List["ScamPattern"]) -> None:
    """Lưu tất cả ScamPattern active vào cache."""
    data = [serialize_active_row(p) for p in all_active_rows]
    _cache_client.setex(
        KEY_ACTIVE_ROWS,
        ACTIVE_ROWS_TTL,
        json.dumps(data, ensure_ascii=False),
    )


def cache_invalidate_active_rows() -> None:
    _cache_client.delete(KEY_ACTIVE_ROWS)


def cache_get_detail(pattern_id: str | uuid.UUID) -> Optional[Dict[str, Any]]:
    raw = _cache_client.get(_detail_key(pattern_id))
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        _cache_client.delete(_detail_key(pattern_id))
    return None


def cache_set_detail(p: "ScamPattern") -> None:
    """Chỉ cache nếu is_active=true (EP-10 không public nháp)."""
    if not getattr(p, "is_active", False):
        return
    _cache_client.setex(
        _detail_key(p.id),
        DETAIL_TTL,
        json.dumps(serialize_detail(p), ensure_ascii=False),
    )


def cache_invalidate_detail(pattern_id: str | uuid.UUID) -> None:
    _cache_client.delete(_detail_key(pattern_id))


def cache_invalidate_all_pattern(pattern_id: Optional[str | uuid.UUID] = None) -> None:
    """Gọi khi có bất kỳ mutation nào (insert/update/delete) → CMS thấy ngay."""
    cache_invalidate_active_rows()
    if pattern_id is not None:
        cache_invalidate_detail(pattern_id)


# ============================================================
# SQLAlchemy EVENT LISTENERS — auto invalidation khi ORM mutate
# ============================================================
_EVENTS_REGISTERED = False


def _scampattern_after_insert(mapper, connection, target: "ScamPattern"):
    cache_invalidate_all_pattern(getattr(target, "id", None))


def _scampattern_after_update(mapper, connection, target: "ScamPattern"):
    cache_invalidate_all_pattern(getattr(target, "id", None))


def _scampattern_after_delete(mapper, connection, target: "ScamPattern"):
    cache_invalidate_all_pattern(getattr(target, "id", None))


def register_scam_pattern_cache_events() -> None:
    """
    Đăng ký 3 event listeners trên Model ScamPattern.
    Phải gọi sau khi app.models.db_models đã import (để class ScamPattern tồn tại).
    Import-safe: gọi nhiều lần vẫn chỉ đăng ký 1 lần.
    """
    global _EVENTS_REGISTERED
    if _EVENTS_REGISTERED:
        return

    from app.models.db_models import ScamPattern as _SPModel

    event.listen(_SPModel, "after_insert", _scampattern_after_insert)
    event.listen(_SPModel, "after_update", _scampattern_after_update)
    event.listen(_SPModel, "after_delete", _scampattern_after_delete)
    _EVENTS_REGISTERED = True


# Tự động đăng ký ngay khi cache module được import lần đầu.
# (main.py / patterns.py import cache → event listeners hoạt động.)
try:
    register_scam_pattern_cache_events()
except Exception:
    # Nếu Model chưa sẵn sàng (import order), sẽ gọi lại từ main.py ở app startup.
    _EVENTS_REGISTERED = False
