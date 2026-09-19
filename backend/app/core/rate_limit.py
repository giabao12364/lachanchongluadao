import os
import time

import redis
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse

from app.core.database import SessionLocal
from app.core.auth import get_current_user_id
from app.models.db_models import AppConfig

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# X-Device-Uid là header BẮT BUỘC ở mọi endpoint (L3.4 quy ước chung).
# Dùng làm fallback nếu middleware khác chưa kịp gán request.state.device_uid.
DEVICE_UID_HEADER = "X-Device-Uid"

# Cache app_config trong bộ nhớ để tránh query DB đồng bộ trên MỌI request
# (middleware chạy async, query sync sẽ chặn event loop nếu gọi trực tiếp).
# Vẫn tuân thủ KT-03 (đọc từ app_config, không hardcode) — chỉ trễ tối đa
# _CONFIG_CACHE_TTL giây khi admin đổi ngưỡng trên DB.
_CONFIG_CACHE_TTL = 30  # giây
_config_cache: dict[str, tuple[int, float]] = {}  # key -> (value, fetched_at)

EXCLUDED_PATHS = [
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
]

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def _query_config_int_sync(key: str, default: int) -> int:
    """Sync DB call — luôn chạy qua threadpool, không gọi trực tiếp trong async code."""
    db = SessionLocal()
    try:
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        return int(row.value) if row else default
    finally:
        db.close()


async def _get_config_int(key: str, default: int) -> int:
    now = time.monotonic()
    cached = _config_cache.get(key)
    if cached is not None and (now - cached[1]) < _CONFIG_CACHE_TTL:
        return cached[0]

    value = await run_in_threadpool(_query_config_int_sync, key, default)
    _config_cache[key] = (value, now)
    return value


def _get_device_uid(request: Request) -> str | None:
    device_uid = getattr(request.state, "device_uid", None)
    if device_uid:
        return device_uid
    # Fallback: đọc trực tiếp từ header nếu middleware set device_uid chưa
    # chạy trước RateLimitMiddleware, hoặc chưa tồn tại.
    return request.headers.get(DEVICE_UID_HEADER)


def _check_and_increment(bucket_key: str, limit: int, window_seconds: int = 3600):
    redis_key = f"ratelimit:{bucket_key}"
    current = redis_client.incr(redis_key)

    if current == 1:
        redis_client.expire(redis_key, window_seconds)

    if current > limit:
        ttl = redis_client.ttl(redis_key)
        return ttl if ttl and ttl > 0 else window_seconds

    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        user_id = get_current_user_id(request)

        if user_id is not None:
            bucket_key = f"user:{user_id}"
            limit = await _get_config_int("ratelimit.user_hourly", default=100)
        else:
            device_uid = _get_device_uid(request)
            if not device_uid:
                # Không có device_uid (client không gửi header, request.state
                # cũng chưa gán) -> KHÔNG bỏ qua rate limit (tránh bị lách),
                # dùng IP làm bucket dự phòng với cùng ngưỡng ẩn danh.
                client_ip = request.client.host if request.client else "unknown"
                bucket_key = f"ip:{client_ip}"
            else:
                bucket_key = f"device:{device_uid}"
            limit = await _get_config_int("ratelimit.anonymous_hourly", default=20)

        # redis_client là client đồng bộ (redis.from_url) -> cũng phải chạy
        # qua threadpool, tránh chặn event loop giống lý do với _get_config_int.
        retry_after = await run_in_threadpool(
            _check_and_increment, bucket_key, limit, 3600
        )

        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": "Bạn đã thao tác quá nhiều lần. Vui lòng thử lại sau ít phút.",
                    "extra": {"retry_after": retry_after},
                },
            )

        return await call_next(request)