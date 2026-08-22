@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title 🔥 Lachan - Fix Hoan Toan (them PyJWT + wait-for-db + rebuild sach se)

echo.
echo ================================================================
echo   LACHA CHONG LUA DAO - FIX TOTAL REBUILD (sau khi tim ra nguyen nhan)
echo ================================================================
echo.

cd /d "%~dp0"

echo [0] Kiem tra Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo     ❌ LOI: Mo Docker Desktop truoc roi chay lai file nay!
    pause
    exit /b 1
)
echo     ✅ Docker dang chay.
echo.

echo [1/9] XOA SACH container cu (bao gom ca nhung container cu khong dung ten):
echo     - Xoa compose stack cu
docker compose down 2>nul
echo     - Xoa nhung container le cach day
docker rm -f lachan_fasta lachan_fastapi lachan_postgres lachan_redis 2>nul
docker rm -f lachan_postgres_5433 lachan_redis_6379 2>nul
echo     - Xoa image backend cu (dam bao build lai HOAN TOAN)
docker rmi -f backend-web backend 2>nul
echo     ✅ Xong.
echo.

echo [2/9] Build image BACKEND MOI (them PyJWT, entrypoint wait-for-db):
echo     Luu y: Lan dau build se tu 1-3 phut, vui long cho...
echo.
docker compose build
if errorlevel 1 (
    echo.
    echo     ❌ LOI BUILD! Hay gui anh loi o tren de fix tiep.
    pause
    exit /b 1
)
echo.
echo     ✅ Build thanh cong image BACKEND.
echo.

echo [3/9] Start stack: Postgres :5433  +  Redis :6379  +  FastAPI :8000
docker compose up -d
echo.
echo     Cho container khoi dong...
timeout /t 6 /nobreak >nul

echo.
echo [4/9] Trang thai containers sau 6s:
echo -----------------------------------------------------------------
docker compose ps
echo -----------------------------------------------------------------
echo.

echo [5/9] Cho them 18s va kiem tra lai (entrypoint cho DB roi khoi dong uvicorn):
echo     (Trong container dang chay: cho DB + init DB tables + seed data)
timeout /t 18 /nobreak >nul

echo.
echo [6/9] Kiem tra trang thai cuoi:
echo -----------------------------------------------------------------
docker compose ps
echo -----------------------------------------------------------------
echo.

echo [7/9] TEST KET NOI BACKEND:
set "HC="
for /f "delims=" %%i in ('powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -TimeoutSec 15 -UseBasicParsing; Write-Output $r.StatusCode; $script:body = $r.Content } catch { Write-Output 'FAIL|'$_.Exception.Message }"') do set "HC=%%i"
echo     Health check / : !HC!
if /i "!HC:~0,4!"=="FAIL" (
    echo.
    echo     ⚠️  BACKEND CHUA CHAY. DANG XEM LOG DE TIM LOI:
    echo     ============================================================
    docker compose logs --tail=80 web
    echo     ============================================================
    echo.
    echo     [Goi y fix]:
    echo     1. Neu thay ModuleNotFoundError: No module named 'jwt'
    echo        =^> Chac chan file RUN_THIS_FIX.cmd chay [2/9] Build lai image?
    echo     2. DB connection errors: Co the Postgres chua san sang.
    echo     3. Neu khong hieu loi, chup lai phan log tren gui anh fix tiep.
    echo.
    pause
    exit /b 1
)
echo.

echo [8/9] TEST OpenAPI (de dam bao Swagger UI /docs hoat dong):
for /f "delims=" %%i in ('powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 10 -UseBasicParsing; if ($r.Content -match 'L[aá] Ch[aả]n') { Write-Output '✅ OK - Co API Schema Lá Chắn' } else { Write-Output '⚠️  Status: '$r.StatusCode', nhung content khong co title? Length: '$r.Content.Length } } catch { Write-Output '❌ FAIL: '$_.Exception.Message }"') do echo     OpenAPI JSON: %%i
echo.

echo [9/9] TEST Scam Patterns endpoint (test DB):
for /f "delims=" %%i in ('powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/scam-patterns?limit=3' -TimeoutSec 10 -UseBasicParsing; Write-Output '✅ OK - Tra ve: '$r.Content.Length ' bytes' } catch { Write-Output '⚠️  DB test: '$_.Exception.Message }"') do echo     ScamPattern API: %%i
echo.

echo.
echo ================================================================
echo   🎉 HOAN TAT - HE THONG DA SAN SANG!
echo ================================================================
echo.
echo   🔗 Swagger UI:      http://127.0.0.1:8000/docs
echo   🔗 Redoc:           http://127.0.0.1:8000/redoc
echo   🔗 OpenAPI JSON:    http://127.0.0.1:8000/openapi.json
echo   🔗 Health check:    http://127.0.0.1:8000/
echo.
echo   📦 Postgres local:  localhost:5433   (lachan_user / lachan_pass / lachan_db)
echo   📦 Redis local:     localhost:6379
echo.
echo   🛠️  Utilities:
echo       - Xem logs realtime:  03_show_logs.cmd
echo       - Kiem tra nhanh:     04_quick_check.cmd
echo       - Test local (venv):  01_test_local.cmd
echo.
echo     Mo Swagger UI ngay...
pause
start "" "http://127.0.0.1:8000/docs"
