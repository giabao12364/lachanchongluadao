from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    scans,
    patterns,
)

app = FastAPI(
    title="Lá Chắn Chống Lừa Đảo API",
    description=(
        "Backend: FR-01 (Tạo quét: POST /scans, EP-01 + EP-02 chi tiết), "
        "FR-03 (Mẫu cảnh báo: GET /scam-patterns, /scam-patterns/{id}), "
        "FR-06 (Lịch sử quét: GET /scans). Đã loại bỏ FR-02/FR-04/FR-05."
    ),
    version="3.0.0-ai",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    scans.router,
    prefix="/api/v1",
    tags=[
        "FR-01: Tạo & Chi tiết lượt quét (EP-01 POST /scans, EP-02 GET /scans/{id}) — AI pipeline + BR-01-6",
        "FR-06: Lịch sử quét (EP-03 — GET /scans)",
    ],
)
app.include_router(
    patterns.router,
    prefix="/api/v1",
    tags=["FR-03: Mẫu cảnh báo (EP-05 — GET /scam-patterns, EP-10 — GET /scam-patterns/{id})"],
)


@app.get("/", tags=["Health Check"])
def health_check():
    return {
        "status": "ok",
        "app": "Lá Chắn Chống Lừa Đảo Backend",
        "kept_features": [
            "FR-01: Scan (EP-01 POST /scans, EP-02 GET /scans/{id}) — AI pipeline + fail-safe BR-01-6",
            "FR-03: Scam Patterns (EP-05, EP-10)",
            "FR-06: Scan History (EP-03 GET /scans)",
        ],
        "removed_features": [
            "FR-02 Phone Lookup (EP-04)",
            "FR-04 Reports (EP-06 POST, EP-09)",
            "FR-05 Auth + Me (EP-07, EP-08, EP-11)",
        ],
    }
