@echo off
setlocal
chcp 65001 >nul
title Remote Test Runner - Local Server
color 0A
cd /d "%~dp0"

set "RTR_PORT=8000"
if not "%~1"=="" set "RTR_PORT=%~1"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -HostAddress "0.0.0.0" -Port %RTR_PORT% -Bootstrap
set "RTR_EXIT=%ERRORLEVEL%"

if not "%RTR_EXIT%"=="0" (
    echo.
    echo 启动失败。请查看上方错误信息。
    echo 如果端口被占用，可以运行：start.bat 8001
    echo.
    pause
)
exit /b %RTR_EXIT%
