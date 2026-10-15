@echo off
title OFFICIALUM1 — Zero-Touch Router Sync Daemon
echo ======================================================
echo    OFFICIALUM1 ZERO-TOUCH ROUTER AUTO-SYNC DAEMON
echo ======================================================
echo  Monitoring Huawei HG8245C (192.168.100.1)...
echo  Newly connected Wi-Fi devices will automatically sync
echo  to https://hub.officialum1.com without any links!
echo ======================================================
echo.
python sync_router_devices.py
pause
