@echo off
setlocal
set "INSTALL_DIR=%LOCALAPPDATA%\TJNearby"

echo Menghapus autostart TJ Nearby...
if exist "%INSTALL_DIR%\venv\Scripts\python.exe" (
  "%INSTALL_DIR%\venv\Scripts\python.exe" -c "from tj_nearby.windows_autostart import set_enabled; set_enabled(False)" >nul 2>nul
)

echo Menghapus shortcut...
del /Q "%USERPROFILE%\Desktop\TJ Nearby.lnk" >nul 2>nul
del /Q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\TJ Nearby.lnk" >nul 2>nul

echo Menghapus aplikasi...
rmdir /S /Q "%INSTALL_DIR%" >nul 2>nul

echo.
echo TJ Nearby dihapus. Config dan cache tetap disimpan di:
echo %USERPROFILE%\.tj-nearby
echo Hapus folder itu manual bila ingin reset total.
pause
