@echo off
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\TJNearby\venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Jalankan Install Windows.bat terlebih dahulu.
  pause
  exit /b 1
)
"%VENV%\Scripts\python.exe" -m tj_nearby.windows_gui --demo
