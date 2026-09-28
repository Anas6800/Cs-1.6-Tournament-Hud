@echo off
cd /d "%~dp0"
echo Starting CS Overlay Configuration Tool...

where python >nul 2>&1
if %errorlevel% equ 0 (
    python config_app.py
    exit /b 0
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py config_app.py
    exit /b 0
)

echo.
echo [ERROR] Python is not installed or not in PATH.
echo Please install Python and check "Add python.exe to PATH".
echo.
pause
