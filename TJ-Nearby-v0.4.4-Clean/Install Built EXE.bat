@echo off
setlocal
cd /d "%~dp0"
set "SOURCE=%~dp0dist-windows\TJ Nearby"
set "TARGET=%LOCALAPPDATA%\TJNearbyApp"
if not exist "%SOURCE%\TJ Nearby.exe" (
  echo EXE belum ada. Jalankan Build Windows EXE.bat dulu.
  pause
  exit /b 1
)
rmdir /S /Q "%TARGET%" >nul 2>nul
xcopy /E /I /Y "%SOURCE%" "%TARGET%" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\TJ Nearby.lnk');" ^
  "$s.TargetPath='%TARGET%\TJ Nearby.exe';" ^
  "$s.WorkingDirectory='%TARGET%';" ^
  "$s.IconLocation='%TARGET%\TJ Nearby.exe';" ^
  "$s.Save();"
start "" "%TARGET%\TJ Nearby.exe"
echo EXE dipasang ke %TARGET%
pause
