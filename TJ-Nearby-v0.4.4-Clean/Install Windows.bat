@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TJ Nearby v0.4.4 - Windows Installer

echo.
echo ==============================================
echo   TJ Nearby v0.4.4 - Windows Monitor Installer
echo ==============================================
echo.

where py >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.11 atau lebih baru belum ditemukan.
    echo Install Python dari python.org dan centang "Add Python to PATH".
    pause
    exit /b 1
  )
  set "PY_CMD=python"
)

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo TJ Nearby membutuhkan Python 3.11 atau lebih baru.
  pause
  exit /b 1
)

set "INSTALL_DIR=%LOCALAPPDATA%\TJNearby"
set "VENV=%INSTALL_DIR%\venv"
set "CONFIG_DIR=%USERPROFILE%\.tj-nearby"

echo [1/5] Menyiapkan folder aplikasi...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

if not exist "%VENV%\Scripts\python.exe" (
  echo [2/5] Membuat virtual environment...
  %PY_CMD% -m venv "%VENV%"
  if errorlevel 1 goto :fail
) else (
  echo [2/5] Virtual environment sudah ada.
)

echo [3/5] Memasang TJ Nearby dan dukungan Windows...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%VENV%\Scripts\python.exe" -m pip install --upgrade --force-reinstall ".[windows]"
if errorlevel 1 goto :fail

if not exist "%CONFIG_DIR%\config.yaml" (
  copy /Y "%~dp0config.example.yaml" "%CONFIG_DIR%\config.yaml" >nul
  echo Config baru dibuat di %CONFIG_DIR%\config.yaml
) else (
  echo Config lama dipertahankan: %CONFIG_DIR%\config.yaml
)
copy /Y "%~dp0assets\tj_nearby.ico" "%INSTALL_DIR%\tj_nearby.ico" >nul

(
  echo @echo off
  echo start "" "%VENV%\Scripts\pythonw.exe" -m tj_nearby.windows_gui
) > "%INSTALL_DIR%\Start TJ Nearby.cmd"

(
  echo @echo off
  echo "%VENV%\Scripts\python.exe" -m tj_nearby.windows_gui --demo
  echo pause
) > "%INSTALL_DIR%\Preview TJ Nearby.cmd"

echo [4/5] Membuat shortcut Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\TJ Nearby.lnk');" ^
  "$s.TargetPath='%VENV%\Scripts\pythonw.exe';" ^
  "$s.Arguments='-m tj_nearby.windows_gui';" ^
  "$s.WorkingDirectory='%INSTALL_DIR%';" ^
  "$s.IconLocation='%INSTALL_DIR%\tj_nearby.ico';" ^
  "$s.Save();" ^
  "$menu=[Environment]::GetFolderPath('Programs')+'\TJ Nearby.lnk';" ^
  "$s2=$ws.CreateShortcut($menu);" ^
  "$s2.TargetPath='%VENV%\Scripts\pythonw.exe';" ^
  "$s2.Arguments='-m tj_nearby.windows_gui';" ^
  "$s2.WorkingDirectory='%INSTALL_DIR%';" ^
  "$s2.IconLocation='%INSTALL_DIR%\tj_nearby.ico';" ^
  "$s2.Save();"

echo [5/5] Menjalankan aplikasi tanpa jendela CMD tambahan...
start "" "%VENV%\Scripts\pythonw.exe" -m tj_nearby.windows_gui

echo.
echo Instalasi selesai.
echo Saat diminta Windows, izinkan Location services untuk desktop apps.
echo TJ Nearby akan tetap aktif di system tray saat jendela ditutup.
echo.
pause
exit /b 0

:fail
echo.
echo Instalasi gagal. Lihat pesan error di atas.
pause
exit /b 1
