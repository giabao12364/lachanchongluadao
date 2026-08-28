from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.exceptions import register_exception_handlers
from app.core.middleware import DeviceUidMiddleware
from app.core.rate_limit import RateLimitMiddleware

app = FastAPI(
    title="La Chan Chong Lua Dao API",
    description="Hệ thống Backend phân tích và cảnh báo lừa đảo",
    version="1.0.0"
)

# Cấu hình CORS để React Native Client (Expo) có thể gọi API mà không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các nguồn trong môi trường phát triển
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(RateLimitMiddleware)
app.add_middleware(DeviceUidMiddleware)

# Dang ky exception handler (T-006) de chuan hoa moi loi tra ve
register_exception_handlers(app)


@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Chào mừng bạn đến với hệ thống API Lá Chắn Chống Lừa Đảo!"
    }