@echo off
setlocal enabledelayedexpansion
title OFFICIALUM1 — Stopping Hub

:: 1. Check for Admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo ================================================================
echo       OFFICIALUM1 // SAFE TERMINATION
echo ================================================================
echo Stopping OFFICIALUM1 Hub daemon and proxy ports...
taskkill /F /FI "WINDOWTITLE eq OFFICIALUM1_HUB*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8088 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8101 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*firwallum1*server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo ================================================================
echo  OFFICIALUM1 Hub has been stopped.
echo  All ports 8101-8110, 8088 and 53 are now released.
echo ================================================================
ping 127.0.0.1 -n 3 >nul
