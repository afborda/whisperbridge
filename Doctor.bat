@echo off
REM Duplo clique: so verifica o PC (nao instala)
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\doctor.ps1"
echo.
pause
exit /b %errorlevel%
