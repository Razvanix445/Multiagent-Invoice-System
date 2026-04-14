@echo off
title Invoice System — Stopping
color 0C

echo.
echo  Stopping Invoice Pipeline...
echo.

docker compose down
echo  ejabberd stopped.

taskkill /FI "WindowTitle eq Invoice Agents*" /F >nul 2>&1
taskkill /FI "WindowTitle eq Invoice Dashboard*" /F >nul 2>&1
echo  Agents and dashboard stopped.

echo.
echo  All stopped. Goodbye!
pause