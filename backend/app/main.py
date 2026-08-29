from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.exceptions import register_exception_handlers
from app.core.middleware import DeviceUidMiddleware
from app.core.rate_limit import RateLimitMiddleware

# Import các Routers tương ứng với mã EP trong tài liệu API Contracts
from app.api.v1 import (
    scans,       # EP-01, EP-02, EP-03
    phones,      # EP-04
    patterns,    # EP-05, EP-10
    reports,     # EP-06, EP-09
    auth,        # EP-07, EP-08
    users        # EP-11
)

app = FastAPI(
    title="Lá Chắn Chống Lừa Đảo API",
    description="Hệ thống API backend theo chuẩn Master Build-Spec v2.0",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# T-007: Thu tu add_middleware RAT QUAN TRONG: add sau -> chay TRUOC
app.add_middleware(RateLimitMiddleware)
app.add_middleware(DeviceUidMiddleware)

# T-006: Dang ky exception handler de chuan hoa moi loi tra ve
register_exception_handlers(app)

# Khai báo các Routers gắn liền với Mã Endpoint (EP) trong Specs
app.include_router(scans.router, prefix="/api/v1", tags=["FR-01 & FR-06: Quét & Lịch sử (EP-01, EP-02, EP-03)"])
app.include_router(phones.router, prefix="/api/v1", tags=["FR-02: Tra cứu SĐT (EP-04)"])
app.include_router(patterns.router, prefix="/api/v1", tags=["FR-03: Mẫu cảnh báo (EP-05, EP-10)"])
app.include_router(reports.router, prefix="/api/v1", tags=["FR-04: Báo cáo lừa đảo (EP-06, EP-09)"])
app.include_router(auth.router, prefix="/api/v1", tags=["FR-05: Xác thực OTP (EP-07, EP-08)"])
app.include_router(users.router, prefix="/api/v1", tags=["FR-05: Thông tin cá nhân (EP-11)"])


@app.get("/", tags=["Health Check"])
def health_check():
    return {"status": "ok", "app": "Lá Chắn Chống Lừa Đảo Backend"}