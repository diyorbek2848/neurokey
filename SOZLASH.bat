@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title NeuroKey - Sozlash (Onboarding)
color 0E

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo.
  echo  [XATO] .venv topilmadi.
  echo  Avval: python -m venv .venv  va  pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   NEUROKEY - YANGI FOYDALANUVCHI SOZLAMASI
echo  ============================================================
echo   Bu birinchi marta ishlatishda kerak:
echo     1. Ismingiz
echo     2. Yuzingiz (kamera)
echo     3. Ovozingiz (mikrofon)
echo  ============================================================
echo.

"%VENV_PY%" "%~dp0onboarding.py"

echo.
echo  Sozlash tugadi. NeuroKey ni ishga tushiring: !NeuroKey.bat
echo.
pause
exit /b 0
