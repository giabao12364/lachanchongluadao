from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Chào mừng bạn đến với hệ thống API Lá Chắn Chống Lừa Đảo!"
    }