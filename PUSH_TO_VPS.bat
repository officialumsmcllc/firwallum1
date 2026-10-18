@echo off
title OFFICIALUM1 -- Deploy to VPS (142.93.19.40)
color 0B
echo ===================================================================
echo     OFFICIALUM1 // 1-CLICK DEPLOY TO CLOUD VPS (142.93.19.40)
echo ===================================================================
echo.
echo VPS Target: root@142.93.19.40
echo Directory:  /opt/firwallum1
echo.
echo [1/3] Creating directory on VPS...
ssh -o StrictHostKeyChecking=no root@142.93.19.40 "mkdir -p /opt/firwallum1"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] SSH Connection failed. Please verify your password.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Uploading codebase to VPS...
scp -o StrictHostKeyChecking=no -r core data web scripts Dockerfile requirements.txt server.py deploy_vps.sh root@142.93.19.40:/opt/firwallum1/
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] File upload failed.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Running installer and starting 24/7 service on VPS...
ssh -o StrictHostKeyChecking=no root@142.93.19.40 "cd /opt/firwallum1 && chmod +x deploy_vps.sh && ./deploy_vps.sh"

echo.
echo ===================================================================
echo   [ALL DONE!] OFFICIALUM1 is now running on your VPS!
echo   Dashboard: http://142.93.19.40:8088
echo   Router DNS: 142.93.19.40
echo ===================================================================
echo.
pause
