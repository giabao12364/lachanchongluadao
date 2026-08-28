@echo off
chcp 65001 >nul
echo [INFO] Chuyen vao thu muc backend...
cd /d "%~dp0backend"
call run-seed.cmd
