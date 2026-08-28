@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   LOGS CONTAINER BACKEND WEB (lachan_fastapi)
echo   Nhan Ctrl+C de thoat xem log.
echo ============================================
echo.

docker compose logs -f --tail=100 web
