@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Build TJ Nearby v0.4.4 Windows EXE

where py >nul 2>nul
if not errorlevel 1 (set "PY_CMD=py -3") else (set "PY_CMD=python")
set "VENV=%~dp0.venv-build-windows"

if not exist "%VENV%\Scripts\python.exe" %PY_CMD% -m venv "%VENV%"
if errorlevel 1 goto :fail
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%VENV%\Scripts\python.exe" -m pip install ".[windows,windows-build]"
if errorlevel 1 goto :fail

rmdir /S /Q build-windows >nul 2>nul
rmdir /S /Q dist-windows >nul 2>nul
"%VENV%\Scripts\pyinstaller.exe" --noconfirm TJNearby.spec
if errorlevel 1 goto :fail

echo.
echo Build selesai:
echo %~dp0dist-windows\TJ Nearby\TJ Nearby.exe
echo.
pause
exit /b 0

:fail
echo Build gagal. Lihat error di atas.
pause
exit /b 1
