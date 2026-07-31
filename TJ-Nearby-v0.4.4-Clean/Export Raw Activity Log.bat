@echo off
setlocal EnableExtensions
set "LOG_DIR=%USERPROFILE%\.tj-nearby\logs"
set "SOURCE=%LOG_DIR%\tj-nearby-activity.log"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"
set "DEST=%USERPROFILE%\Desktop\tj-nearby-raw-activity-%STAMP%.txt"

if not exist "%SOURCE%" (
  echo Activity log belum ditemukan di:
  echo %SOURCE%
  echo Jalankan TJ Nearby v0.4.4 setidaknya satu kali terlebih dahulu.
  pause
  exit /b 1
)

copy /Y "%SOURCE%" "%DEST%" >nul
if errorlevel 1 (
  echo Gagal menyalin activity log.
  pause
  exit /b 1
)

echo Activity log berhasil diekspor ke:
echo %DEST%
pause
