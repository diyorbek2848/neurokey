@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title NeuroKey

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

rem ===== Chiroyli yuklanish animatsiyasi (fon, 4 soniya) =====
if exist "%VENV_PY%" (
  start "" "%VENV_PY%" "%~dp0splash.py" 4
)

rem ===== Asosiy NeuroKey ni ishga tushirish (asosiy batga tegmaydi) =====
call "%~dp0!NeuroKey.bat"

exit /b 0
