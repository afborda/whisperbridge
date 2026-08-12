@echo off
REM Launcher visivel so para debug. Uso normal: WhisperBridge.vbs (sem terminal)
cd /d "%~dp0"
if /I "%~1"=="-console" (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0WhisperBridge.ps1" -ShowConsole
  if errorlevel 1 pause
  exit /b %errorlevel%
)
wscript.exe //nologo "%~dp0WhisperBridge.vbs"
