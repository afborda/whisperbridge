@echo off
REM Duplo clique: menu do doctor + instalador
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Doctor.ps1" -Menu
if errorlevel 1 pause
exit /b %errorlevel%
