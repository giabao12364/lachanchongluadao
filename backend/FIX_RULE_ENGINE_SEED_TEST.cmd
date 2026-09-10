@echo off
REM ======================================================================
REM FIX_RULE_ENGINE_SEED_TEST.cmd - 1 Click fix lỗi 500 Rule Engine
REM Chức năng: Alembic downgrade base + upgrade head (re-seed 11 rule BR-01-10),
REM            Sau đó chạy test pipeline + yêu cầu khởi động lại backend
REM ======================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║  FIX: Rule Engine 500 - Alembic Re-seed ScoringRule (BR-01-10)   ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM ===========================================================
REM BƯỚC 1: ALEMBIC DOWNGRADE TO BASE + UPGRADE TO HEAD (re-seed sạch)
REM ===========================================================
echo [1/3] Alembic downgrade base → upgrade head (recreate schema + seed 11 rule BR-01-10)...
if exist "venv\Scripts\alembic.exe" (
    venv\Scripts\alembic.exe downgrade base
    venv\Scripts\alembic.exe upgrade head
    set INIT_RC=%ERRORLEVEL%
) else (
    alembic downgrade base
    alembic upgrade head
    set INIT_RC=%ERRORLEVEL%
)
if not "!INIT_RC!"=="0" (
    echo.
    echo ❌ LỖI: alembic thất bại (rc=!INIT_RC!). Kiểm tra lại Docker DB đang chạy? (postgresql ở localhost:5433)
    echo Gợi ý: chạy RUN_THIS_FIX.cmd trước để khởi động toàn bộ stack, rồi chạy lại script này.
    pause
    exit /b !INIT_RC!
)
echo.
echo ✅ Alembic migrate hoàn tất. Schema + seed đúng theo migrations.
echo.

REM ===========================================================
REM BƯỚC 2: CHẠY TEST PIPELINE (test_pipeline.py)
REM ===========================================================
echo [2/3] Chạy test_pipeline.py (test 4 test case theo BR-01-10)...
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe test_pipeline.py
    set TEST_RC=%ERRORLEVEL%
) else (
    python test_pipeline.py
    set TEST_RC=%ERRORLEVEL%
)
echo.
if "!TEST_RC!"=="0" (
    echo ✅ TẤT CẢ TEST CASE THÀNH CÔNG! Rule Engine hoạt động đúng spec BR-01-10.
) else (
    echo ⚠️  Một số test case thất bại. Xem chi tiết log ở trên. Kiểm tra lại DB/Pattern nếu cần.
)
echo.

REM ===========================================================
REM BƯỚC 3: Yêu cầu RESTART BACKEND để load model mới
REM ===========================================================
echo [3/3] ⚠️  QUAN TRỌNG: Cần RESTART Backend/Uvicorn Server để nhận Model + Rule Engine mới!
echo       Nếu bạn đang chạy bằng Docker (stack do RUN_THIS_FIX.cmd quản lý):
echo         cd /d "%~dp0"
echo         docker compose restart web
echo         docker compose logs --tail=40 -f web
echo       Nếu chạy local venv:
echo         Dừng Ctrl+C server, rồi chạy lại uvicorn app.main:app --reload
echo.
echo ======================================================================
echo   Xong. Sau khi restart backend, mở Swagger test lại POST /api/v1/scans:
echo   🔗 Swagger: http://127.0.0.1:8000/docs
echo   Header: X-Device-Uid: device-test-01
echo   Body mẫu (theo spec mẫu VIETCOMBANK T-013):
echo   {"input_type":"TEXT","content":"VIETCOMBANK: Tài khoản của bạn sẽ bị khóa trong 24h. Xác minh ngay tại bit.ly/vcb-xacminh"}
echo   Expected: risk_level=NGUY_HIEM, final_score=100, 4 lý do
echo             (R_IMPERSONATE_BANK 30 + R_ACCOUNT_THREAT 25 + R_URGENCY 20 + R_SHORT_URL 25 = 100)
echo   Quick check DB = 11 rule:
echo     docker compose exec db psql -U lachan_user -d lachan_db -c "select rule_code,score,pattern_type from scoring_rule order by score desc;"
echo ======================================================================
echo.
pause
