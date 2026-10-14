@echo off
title OFFICIALUM1 — 1-Click Client Setup
echo ================================================================
echo       OFFICIALUM1 // CLIENT AUTO-CONFIG (1-CLICK SETUP)
echo ================================================================
echo.
echo Connecting to OFFICIALUM1 Gateway at 192.168.100.158...

:: Configure Windows PAC URL in Current User Internet Settings
powershell -Command "Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name AutoConfigURL -Value 'http://192.168.100.158:8088/proxy.pac'; Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Value 0" >nul 2>&1

echo.
echo [SUCCESS] Windows Automatic Proxy is now active!
echo  - PAC Script: http://192.168.100.158:8088/proxy.pac
echo  - Hub will automatically recognize this laptop and assign its dedicated proxy.
echo.
echo To remove and go back to normal Wi-Fi, run RESET_CLIENT_LAPTOP.bat.
echo ================================================================
pause
