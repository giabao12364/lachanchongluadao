import logging
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

logger = logging.getLogger(__name__)

DEVICE_UID_HEADER = "X-Device-Uid"

_CONFIG_CACHE_TTL = 30  # giây
_config_cache: dict[str, tuple[int, float]] = {}

# ---------------------------------------------------------------------------
# QUYẾT ĐỊNH (đưa ra khi PM chưa kịp duyệt, ghi lại để review lại sau — xem
# giải thích đầy đủ trong PR description / chat với PM):
#
# 1) window KHÔNG configurable qua app_config, quay về hằng số.
#    Lý do: tên các key L4.4 đã mã hoá sẵn đơn vị thời gian
#    (ratelimit.*_HOURLY, otp.max_send_per_10MIN). Một "ratelimit.window_
#    seconds" dùng chung cho mọi scope vừa không khớp tên key, vừa là 1 núm
#    vặn chung nguy hiểm (đổi cho OTP sẽ vô tình đổi luôn cả scan/report).
#    Nếu sau này thực sự cần window configurable per-scope, phải tách thành
#    nhiều key riêng (vd ratelimit.scan_window_seconds, .report_window_
#    seconds), không dùng lại 1 key chung như bản cũ.
#
# 2) check_report_rate_limit() dùng FAIL-OPEN khi Redis/DB lỗi (giống
#    RateLimitMiddleware), thay vì fail-closed (500) ở bản trước đó.
#    Lý do: đồng bộ với tiền lệ BR-01-6/L3.7 (hạ tầng phụ trợ lỗi không
#    được chặn chức năng chính). Giá trị phòng thủ của rate-limit 5/h/user
#    thấp (BR-04-2 đã chặn trùng entity độc lập với rate-limit; thao túng
#    DD-06 cần ≥3 tài khoản khác nhau, rate-limit theo user không chặn được
#    kịch bản đó dù bật hay tắt) — trong khi fail-closed chặn nhầm người
#    dùng thật mỗi khi Redis chớp tắt, ảnh hưởng trực tiếp mục tiêu sản
#    phẩm (khuyến khích báo cáo kịp thời — L1.3).
#
# Cả 2 điểm này CẦN PM xác nhận lại 
# ---------------------------------------------------------------------------

HOURLY_WINDOW_SECONDS = 3600  # dùng chung cho mọi rule "_hourly" (scan, report)

# Các tiền tố đường dẫn ĐƯỢC LOẠI TRỪ khỏi Global Rate Limit:
# - Các route đọc công khai (scam-patterns EP-05/EP-10)
# - Các route có rate-limit riêng (reports T-033, sau này là auth/otp FR-05)
EXCLUDED_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/reports",
    "/api/v1/scam-patterns",
)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Lua script đảm bảo tính ATOMIC tuyệt đối 100% trên Redis Engine.
# Tương thích với MỌI phiên bản Redis (kể cả < 7.0) mà không cần cờ EXPIRE NX.
_RATELIMIT_LUA_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""
_ratelimit_script = redis_client.register_script(_RATELIMIT_LUA_SCRIPT)


def _query_config_int_sync(key: str, default: int) -> int:
    db = SessionLocal()
    try:
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        return int(row.value) if row else default
    finally:
        db.close()


def _get_config_int_sync_cached(key: str, default: int) -> int:
    now = time.monotonic()
    cached = _config_cache.get(key)
    if cached is not None and (now - cached[1]) < _CONFIG_CACHE_TTL:
        return cached[0]
    value = _query_config_int_sync(key, default)
    _config_cache[key] = (value, now)
    return value


async def _get_config_int(key: str, default: int) -> int:
    return await run_in_threadpool(_get_config_int_sync_cached, key, default)


def _get_device_uid(request: Request) -> str | None:
    device_uid = getattr(request.state, "device_uid", None)
    if device_uid:
        return device_uid
    return request.headers.get(DEVICE_UID_HEADER)


def _check_and_increment(bucket_key: str, limit: int, window_seconds: int) -> int | None:
    """
    Atomic INCR + EXPIRE + TTL qua Redis Lua Script (EVALSHA).
    Đảm bảo 100% thread-safe/process-safe ở mức cơ sở dữ liệu.
    """
    redis_key = f"ratelimit:{bucket_key}"
    res = _ratelimit_script(keys=[redis_key], args=[window_seconds])
    current, ttl = res[0], res[1]

    if current > limit:
        return ttl if ttl and ttl > 0 else window_seconds

    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path == "/" or path.startswith(EXCLUDED_PREFIXES):
            return await call_next(request)

        try:
            user_id = get_current_user_id(request)

            if user_id is not None:
                bucket_key = f"user:{user_id}"
                limit = await _get_config_int("ratelimit.user_hourly", default=100)
            else:
                device_uid = _get_device_uid(request)
                if not device_uid:
                    client_ip = request.client.host if request.client else "unknown"
                    bucket_key = f"ip:{client_ip}"
                else:
                    bucket_key = f"device:{device_uid}"
                limit = await _get_config_int("ratelimit.anonymous_hourly", default=20)

            retry_after = await run_in_threadpool(
                _check_and_increment, bucket_key, limit, HOURLY_WINDOW_SECONDS
            )
        except Exception:
            # Fail-open: Redis/DB lỗi không được làm sập cả API (T-006).
            logger.warning(
                "[rate_limit] bỏ qua kiểm tra rate limit do lỗi hạ tầng (Redis/DB)",
                exc_info=True,
            )
            return await call_next(request)

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


def check_report_rate_limit(user_id: str) -> int | None:
    """
    T-033 — BR-04-3: Tối đa ratelimit.report_hourly (mặc định 5) report/giờ/user.

    Độc lập với RateLimitMiddleware: bucket key riêng (report:<user_id>) và
    config key riêng (ratelimit.report_hourly) -> không trừ chung quota
    ratelimit.user_hourly. Route /api/v1/reports đã nằm trong EXCLUDED_PREFIXES
    nên không bị RateLimitMiddleware xử lý trùng.

    CHỈ gọi từ route khai `def` (sync, đúng quy ước toàn repo: scans.py,
    phones.py...) — FastAPI tự chạy trong threadpool. KHÔNG gọi hàm này
    trực tiếp trong `async def` mà không bọc run_in_threadpool, vì đây là
    hàm blocking (Redis + DB đồng bộ).

    Fail-open khi Redis/DB lỗi (xem khối QUYẾT ĐỊNH ở đầu file) — trả None
    (không chặn), chỉ log cảnh báo. Nếu PM chốt ngược lại (fail-closed),
    đổi nhánh except bên dưới thành raise HTTPException(500, ...).
    """
    try:
        limit = _get_config_int_sync_cached("ratelimit.report_hourly", default=5)
        bucket_key = f"report:{user_id}"
        return _check_and_increment(bucket_key, limit, HOURLY_WINDOW_SECONDS)
    except Exception:
        logger.warning(
            "[check_report_rate_limit] Redis/DB lỗi khi kiểm tra report rate "
            "limit cho user %s — bỏ qua rate-limit, KHÔNG chặn report.",
            user_id,
            exc_info=True,
        )
        return None