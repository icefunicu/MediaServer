@echo off
set PYTHONIOENCODING=utf-8
chcp 65001 >nul 2>&1

echo ========================================
echo   Local Media Server
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [Error] Virtual environment not found
    pause
    exit /b 1
)

if not exist "config\config.yaml" (
    echo [Warning] Config file not found, using default
)

echo [Info] Starting server...
echo [Info] Visit: http://localhost:8001
echo [Info] API Docs: http://localhost:8001/docs
echo [Info] Tip: set MEDIA_SERVER_RELOAD=1 to enable hot reload (dev only)
echo.

set RELOAD_FLAG=
if /I "%MEDIA_SERVER_RELOAD%"=="1" set RELOAD_FLAG=--reload

.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 %RELOAD_FLAG%

pause
