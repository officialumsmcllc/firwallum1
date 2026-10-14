@echo off
title OFFICIALUM1 — Reset Client Proxy
echo ================================================================
echo       OFFICIALUM1 // RESET CLIENT PROXY (DIRECT WI-FI)
echo ================================================================
echo.
echo Disabling proxy script and restoring direct Wi-Fi...

powershell -Command "Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name AutoConfigURL -ErrorAction SilentlyContinue; Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Value 0" >nul 2>&1

echo.
echo [SUCCESS] Client proxy removed! You are now on direct Wi-Fi.
echo ================================================================
pause
