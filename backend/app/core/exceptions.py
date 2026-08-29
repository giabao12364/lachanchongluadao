from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse


def register_exception_handlers(app: FastAPI) -> None:
    """
    Đăng ký exception handler để chuẩn hóa mọi lỗi trả về theo đúng
    Master Build-Spec L3.4 (Quy ước chung):
        { "code": string, "message": string, "extra": object | null }
    """

    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            content = {
                "code": exc.detail["code"],
                "message": exc.detail["message"],
                "extra": exc.detail.get("extra"),
            }
        else:
            content = {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail if isinstance(exc.detail, str) else "Đã có lỗi xảy ra.",
                "extra": None,
            }
        return JSONResponse(status_code=exc.status_code, content=content)

    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first_error = exc.errors()[0] if exc.errors() else None
        field = ".".join(str(loc) for loc in first_error["loc"] if loc != "body") if first_error else ""

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": f"Dữ liệu không hợp lệ ở trường '{field}'." if field else "Dữ liệu gửi lên không hợp lệ.",
                "extra": {"errors": exc.errors()},
            },
        )

    
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_ERROR",
                "message": "Hệ thống đang gặp sự cố. Vui lòng thử lại.",
                "extra": None,
            },
        )
