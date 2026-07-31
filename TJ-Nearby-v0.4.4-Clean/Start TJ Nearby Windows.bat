@echo off
setlocal
set "VENV=%LOCALAPPDATA%\TJNearby\venv"
if not exist "%VENV%\Scripts\pythonw.exe" (
  echo TJ Nearby belum dipasang. Menjalankan installer...
  call "%~dp0Install Windows.bat"
  exit /b %errorlevel%
)
start "" "%VENV%\Scripts\pythonw.exe" -m tj_nearby.windows_gui
exit /b 0
