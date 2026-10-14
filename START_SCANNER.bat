@echo off
setlocal
chcp 65001 >nul
title Stock Scanner
cd /d "%~dp0"
set "UV_CACHE_DIR=%TEMP%\scaner-uv-cache"
set "UV_EXE=%~dp0.runtime\uv.exe"

if exist "%UV_EXE%" goto start_scanner

echo Перший запуск: готую сканер. Це може зайняти кілька хвилин...
if not exist ".runtime" mkdir ".runtime"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile '.runtime\uv.zip'; Expand-Archive -Path '.runtime\uv.zip' -DestinationPath '.runtime' -Force; Remove-Item '.runtime\uv.zip'"
if not %errorlevel%==0 goto failed

:start_scanner
echo Запускаю сканер...
"%UV_EXE%" sync --frozen
if not %errorlevel%==0 goto failed
"%UV_EXE%" run python open_scanner.py
goto end

:failed
echo.
echo Сканер не запустився. Зробіть фото цього вікна і надішліть мені.
pause

:end
endlocal
