@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title NeuroKey - Setup
color 0B

echo.
echo  ============================================================
echo   NEUROKEY — noldan o'rnatish
echo  ============================================================
echo   Internet kerak. Birinchi marta 20-40 daqiqa.
echo   Python 3.10, "Add Python to PATH" bilan o'rnatilgan bo'lsin.
echo  ============================================================
echo.

echo  [1/6] Python...
where python >nul 2>&1
if errorlevel 1 (
  echo  [XATO] Python topilmadi.
  echo  https://www.python.org/downloads/release/python-31011/
  echo  O'rnatishda "Add Python to PATH" ni belgilang, keyin SETUP.bat ni qayta oching.
  start "" "https://www.python.org/downloads/release/python-31011/"
  pause
  exit /b 1
)
python --version
echo.

echo  [2/6] Virtual muhit...
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (
    echo  [XATO] venv yaratilmadi.
    pause
    exit /b 1
  )
)
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
"%VENV_PY%" -m pip install --upgrade pip -q
echo.

echo  [3/6] Kutubxonalar (requirements.txt)...
"%VENV_PY%" -m pip install -r requirements.txt
echo.

echo  [4/6] GPU bo'lsa torch CUDA...
where nvidia-smi >nul 2>&1
if not errorlevel 1 (
  "%VENV_PY%" -m pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
) else (
  echo       nvidia-smi yo'q — CPU torch qoladi.
)
echo.

echo  [5/6] Modellar yuklanmoqda (Vosk, Piper, Whisper, xotira)...
"%VENV_PY%" "%~dp0download_setup_models.py"
echo.

echo  [6/6] Kalit va litsenziya...
if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo.
  echo  .env yaratildi. GROQ_API_KEY ni yozing.
  echo  Bepul kalit: https://console.groq.com
  echo  Fayl: %~dp0.env
  echo.
  notepad ".env"
)
if not exist "data\license.key" (
  "%VENV_PY%" -c "from license_manager import activate_license; activate_license('NEUROKEY-TEAM', 3650)"
)
echo.
echo  ============================================================
echo   TAYYOR
echo   Ishga tushirish: !NeuroKey.bat
echo   Yo'riqnoma: YORIQNOMA.md
echo  ============================================================
echo.
pause
exit /b 0
