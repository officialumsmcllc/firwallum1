@echo off
setlocal enabledelayedexpansion
title OFFICIALUM1 — Multi-Device Gateway Launcher

:: 1. Check for Admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ================================================================
    echo  [ELEVATION REQUIRED] Requesting Administrator Privileges...
    echo ================================================================
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo ================================================================
echo       OFFICIALUM1 // MULTI-DEVICE SECURITY GATEWAY
echo ================================================================
echo [1/3] Ensuring Windows Defender Firewall rules for LAN devices...
netsh advfirewall firewall add rule name="OFFICIALUM1 DNS" dir=in action=allow protocol=UDP localport=53 >nul 2>&1
netsh advfirewall firewall add rule name="OFFICIALUM1 DASHBOARD" dir=in action=allow protocol=TCP localport=8088 >nul 2>&1
netsh advfirewall firewall add rule name="OFFICIALUM1 PROXY PORTS" dir=in action=allow protocol=TCP localport=8100-8110 >nul 2>&1

:: Stop any old instance
taskkill /F /FI "WINDOWTITLE eq OFFICIALUM1_HUB*" >nul 2>&1

echo [2/3] Starting OFFICIALUM1 Multi-Port Hub...
start "OFFICIALUM1_HUB" python server.py

echo [3/3] Opening Clean Web Dashboard...
timeout /t 2 /nobreak >nul
start http://localhost:8088

echo ================================================================
echo  OFFICIALUM1 is running!
echo  - Clean Dashboard:   http://localhost:8088
echo  - Dedicated Ports:   8101 - 8110
echo  - To stop safely, run STOP_HUB.bat
echo ================================================================
pause
