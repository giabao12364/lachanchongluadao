@echo off
chcp 65001 >nul
title Seed Scam Patterns
cd /d "%~dp0"

echo.
echo ============================================
echo   Chay seed ScamPattern vao database
echo ============================================
echo.

if not exist ".\venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay venv. Hay tao venv truoc:
    echo   python -m venv venv
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

".\venv\Scripts\python.exe" app\db\seed_scam_patterns.py

echo.
echo -------------------------------------------
echo Kiem tra lai du lieu da vao DB chua...
echo.
curl -s -o NUL -w "" http://localhost:5433 >nul 2>&1
docker exec lachan_postgres psql -U lachan_user -d lachan_db -c "SELECT count(*) AS so_ban_ghi_scam_pattern FROM scam_pattern;"

echo.
pause
