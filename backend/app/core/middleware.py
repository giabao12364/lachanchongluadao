import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse

ENV = os.getenv("ENV", "dev")

# Các đường dẫn tài nguyên Swagger/OpenAPI/health check:
# Bỏ qua check X-Device-Uid hoàn toàn (cho mọi môi trường)
EXCLUDED_PATH_PREFIXES = [
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
]

# Giá trị mặc định dùng khi ENV=dev và người dùng test trên Swagger UI
# không gửi header X-Device-Uid → tự gán để dev test nhanh, không bị 400.
DEFAULT_DEV_DEVICE_UID = "dev-swagger-default-device-0000"


def _is_excluded(path: str) -> bool:
    for prefix in EXCLUDED_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


class DeviceUidMiddleware(BaseHTTPMiddleware):
    """
    Middleware bắt buộc mọi request API phải có header X-Device-Uid.
    - Nếu ENV=dev và thiếu header → tự gán giá trị mặc định (dev/test tiện hơn).
    - Nếu ENV=prod và thiếu header → trả về 400 theo format chuẩn.
    - Các path Swagger / health check → luôn bỏ qua.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _is_excluded(path):
            return await call_next(request)

        device_uid = request.headers.get("X-Device-Uid")
        if not device_uid or device_uid.strip() == "":
            if ENV == "dev":
                device_uid = DEFAULT_DEV_DEVICE_UID
            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": "MISSING_DEVICE_UID",
                        "message": "Thiếu header X-Device-Uid. Vui lòng gửi kèm định danh thiết bị.",
                        "extra": None,
                    },
                )

        request.state.device_uid = device_uid
        return await call_next(request)
