@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title 🔥 Lachan - Fix Hoan Toan v2 (Rule Engine T-013 + Schema scoring_rule)

echo.
echo ================================================================
echo   LACHA CHONG LUA DAO - FIX TOTAL REBUILD (Rule Engine v2)
echo   Bao gom: Xoa PG volume + DROP scoring_rule cu + Seed BR-01-10
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

echo [1/10] XOA SACH container + image + PG DATA VOLUME (dam bao DB MOI 100%):
echo     - Xoa compose stack cu
docker compose down -v 2>nul
echo     - Xoa nhung container le cach day
docker rm -f lachan_fasta lachan_fastapi lachan_postgres lachan_redis 2>nul
docker rm -f lachan_postgres_5433 lachan_redis_6379 2>nul
echo     - Xoa image backend cu
docker rmi -f backend-web backend 2>nul
echo     - Xoa PG data volume (dam bao scoring_rule schema moi duoc tao tu scratch)
docker volume rm -f backend_lachan_pgdata lachan_pgdata 2>nul
echo     ✅ Xong. Stack + DB + volume da sach se.
echo.

echo [2/10] Build image BACKEND MOI (Model ScoringRule moi + Rule Engine 3 pattern_type):
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

echo [3/10] Start stack: Postgres :5433  +  Redis :6379  +  FastAPI :8000
docker compose up -d
echo.
echo     Cho container khoi dong va entrypoint chay alembic upgrade head (schema + seed)...
timeout /t 8 /nobreak >nul

echo.
echo [4/10] Trang thai containers sau 8s:
echo -----------------------------------------------------------------
docker compose ps
echo -----------------------------------------------------------------
echo.

echo [5/10] Cho them 25s (entrypoint cho DB + alembic migrate + seed 11 rule BR-01-10):
echo     (Trong container: wait-for-db → alembic upgrade head → uvicorn)
timeout /t 25 /nobreak >nul

echo.
echo [6/10] Kiem tra trang thai cuoi:
echo -----------------------------------------------------------------
docker compose ps
echo -----------------------------------------------------------------
echo.

echo [7/10] TEST KET NOI BACKEND / Health check:
set "HC="
for /f "delims=" %%i in ('powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -TimeoutSec 15 -UseBasicParsing; Write-Output $r.StatusCode } catch { Write-Output 'FAIL|'$_.Exception.Message }"') do set "HC=%%i"
echo     Health check / : !HC!
if /i "!HC:~0,4!"=="FAIL" (
    echo.
    echo     ⚠️  BACKEND CHUA CHAY. DANG XEM LOG DE TIM LOI:
    echo     ============================================================
    docker compose logs --tail=100 web
    echo     ============================================================
    echo.
    echo     [Goi y fix]:
    echo     1. Neu thay AttributeError: 'ScoringRule' object has no attribute 'condition_pattern'
    echo        =^> DB chua sync model moi. Kiem tra alembic upgrade head co chay?
    echo     2. DB connection errors: Co the Postgres chua san sang, cho them 10s roi refresh.
    echo     3. Neu khong hieu loi, chup lai phan log tren gui anh fix tiep.
    echo.
    pause
    exit /b 1
)
echo.

echo [8/10] TEST OpenAPI (de dam bao Swagger UI /docs hoat dong):
for /f "delims=" %%i in ('powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 10 -UseBasicParsing; if ($r.Content -match 'L[aá] Ch[aả]n') { Write-Output '✅ OK - Co API Schema Lá Chắn' } else { Write-Output '⚠️  Status: '$r.StatusCode', nhung content khong co title? Length: '$r.Content.Length } } catch { Write-Output '❌ FAIL: '$_.Exception.Message }"') do echo     OpenAPI JSON: %%i
echo.

echo [9/10] TEST Scam Patterns endpoint (test DB ket noi + ScamPattern seed):
for /f "delims=" %%i in ('powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/scam-patterns?limit=3' -TimeoutSec 10 -UseBasicParsing; Write-Output '✅ OK - Tra ve: '$r.Content.Length ' bytes' } catch { Write-Output '⚠️  DB test: '$_.Exception.Message }"') do echo     ScamPattern API: %%i
echo.

echo [10/10] TEST PIPELINE Rule Engine (BR-01-10) ben trong container:
echo     Chay test_pipeline.py: 4 test case (Spec VCB 100d, OTP, An toan, Job+STK)
echo -----------------------------------------------------------------
docker compose exec -T web python /app/test_pipeline.py
set PIPE_EXIT=%errorlevel%
echo -----------------------------------------------------------------
if %PIPE_EXIT% NEQ 0 (
    echo.
    echo     ⚠️  PIPELINE TEST THAT BAI (exit code %PIPE_EXIT%).
    echo     [Goi y]:
    echo       - Kiem tra scoring_rule count trong DB (phai = 11 rule):
    echo           docker compose exec db psql -U lachan_user -d lachan_db -c "select rule_code,score,pattern_type from scoring_rule order by score desc;"
    echo       - Neu 0 rule: alembic upgrade head chua hoan tat, thu cho them 10s va chay lai.
    echo       - Neu pattern_type sai: xoa volume PG roi build lai (buoc [1/10]).
    echo.
) else (
    echo     ✅ PIPELINE TEST THANH CONG 100% - Rule Engine hoat dong dung theo spec BR-01-10
    echo.
    echo     📌 Minh chung Spec T-013:
    echo       Input: VIETCOMBANK: Tai khoan cua ban se bi khoa trong 24h. Xac minh ngay tai bit.ly/vcb-xacminh
    echo       R_IMPERSONATE_BANK(30) + R_ACCOUNT_THREAT(25) + R_URGENCY(20) + R_SHORT_URL(25) = 100 (tran)
    echo       =^> risk_level=NGUY_HIEM, final_score=100, 4 ly do.
)
echo.

echo.
echo ================================================================
echo   🎉 HOAN TAT - HE THONG DA SAN SANG! (Rule Engine v2 da fix)
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
echo       - Test lai pipeline (trong container):
echo           docker compose exec web python /app/test_pipeline.py
echo       - Test local (venv, neu co):
echo           .\venv\Scripts\python.exe test_pipeline.py
echo       - Quick check 11 scoring_rule da dung chua:
echo           docker compose exec db psql -U lachan_user -d lachan_db -c "select rule_code,score,pattern_type from scoring_rule order by score desc, rule_code;"
echo.
echo     Mo Swagger UI ngay...
pause
