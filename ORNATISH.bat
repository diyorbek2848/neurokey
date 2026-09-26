@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title NeuroKey - O'rnatish
color 0B

cls
echo.
echo  ##########################################################
echo  #                                                        #
echo  #              N E U R O K E Y                           #
echo  #          The Key to Your Mind                          #
echo  #                                                        #
echo  #          Avtomatik O'rnatish                           #
echo  #                                                        #
echo  ##########################################################
echo.
echo   Bu NeuroKey ni kompyuteringizga o'rnatadi.
echo   Faqat kuting - hamma narsa avtomatik bo'ladi.
echo.
pause

rem ============ 1. PYTHON ============
cls
echo.
echo  [1/4] Python tekshirilmoqda...
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo  Python topilmadi. Yuklab olish kerak.
  echo.
  echo  Brauzer ochilmoqda - Python 3.10 ni o'rnating.
  echo  MUHIM: o'rnatishda "Add Python to PATH" ni belgilang!
  echo.
  start "" "https://www.python.org/downloads/release/python-31011/"
  echo  Python o'rnatgandan keyin shu ORNATISH.bat ni qayta bosing.
  echo.
  pause
  exit /b 1
)
echo  [OK] Python topildi.
timeout /t 1 /nobreak >nul

rem ============ 2. VENV + KUTUBXONALAR ============
cls
echo.
echo  [2/4] Dasturlar o'rnatilmoqda...
echo        Bu 15-30 daqiqa olishi mumkin. Kuting, internet kerak.
echo.
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo        Virtual muhit yaratilmoqda...
  python -m venv .venv
)
echo        pip yangilanmoqda...
"%VENV_PY%" -m pip install --upgrade pip -q
echo        Kutubxonalar o'rnatilmoqda (torch, AI modellari)...
"%VENV_PY%" -m pip install -r requirements.txt
echo.
echo  [OK] Dasturlar o'rnatildi.
timeout /t 1 /nobreak >nul

rem ============ 3. .env (API kalit) ============
cls
echo.
echo  [3/4] Sozlamalar tekshirilmoqda...
echo.
if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul 2>&1
    echo  [DIQQAT] .env yaratildi - API kalitlarni kiriting!
    echo  Groq bepul kalit: https://console.groq.com
  ) else (
    echo  [DIQQAT] .env fayli yo'q - API kalitlar kerak bo'ladi.
  )
) else (
  echo  [OK] Sozlamalar bor.
)
timeout /t 2 /nobreak >nul

rem ============ 4. ONBOARDING (yuz/ovoz) ============
cls
echo.
echo  [4/4] Shaxsiy sozlash...
echo        Endi ism, yuz va ovozingizni ro'yxatdan o'tkazamiz.
echo.
pause
if not exist "%~dp0data\user_profile.json" (
  "%VENV_PY%" "%~dp0onboarding.py"
)

rem ============ DESKTOP YORLIQ ============
echo.
echo  Desktop yorlig'i yaratilmoqda...
set "LNK=%USERPROFILE%\Desktop\NeuroKey.lnk"
set "TARGET=%~dp0NeuroKey_START.bat"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0logo\neurokey_favicon.png'; $s.Save()" >nul 2>&1

cls
echo.
echo  ##########################################################
echo  #                                                        #
echo  #          O'RNATISH TUGADI!                             #
echo  #                                                        #
echo  ##########################################################
echo.
echo   NeuroKey tayyor!
echo.
echo   Ishga tushirish:
echo     - Desktop'dagi "NeuroKey" yorlig'ini bosing
echo     - yoki NeuroKey_START.bat
echo.
pause
exit /b 0
