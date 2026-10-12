from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse

EXCLUDED_PATHS = [
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
]


class DeviceUidMiddleware(BaseHTTPMiddleware):
    """
    Middleware bắt buộc mọi request phải có header X-Device-Uid.
    Nếu thiếu, trả về lỗi 400 theo format JSON chuẩn {code, message}.
    """

    async def dispatch(self, request: Request, call_next):
        
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        device_uid = request.headers.get("X-Device-Uid")

        if not device_uid or device_uid.strip() == "":
            return JSONResponse(
                status_code=400,
                content={
                    "code": "MISSING_DEVICE_UID",
                    "message": "Thiếu header X-Device-Uid. Vui lòng gửi kèm định danh thiết bị.",
                    "extra": None,
                },
            )

        
        request.state.device_uid = device_uid

        response = await call_next(request)
        return response
