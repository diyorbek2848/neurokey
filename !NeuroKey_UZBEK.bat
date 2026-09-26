@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if /i "%~1"=="stop"  goto :STOP
if /i "%~1"=="yop"   goto :STOP
if /i "%~1"=="ochir" goto :STOP
goto :START

:STOP
title NeuroKey — YOPISH
color 0C
echo.
echo  NeuroKey to'xtatilmoqda...
call :KILL_ALL
reg delete "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v NeuroKey /f >nul 2>&1
schtasks /delete /tn "NeuroKey" /f >nul 2>&1
echo.
echo  [TUGADI] Hammasi o'chirildi. Qayta ochish: !NeuroKey.bat
echo.
pause
exit /b 0

:START
title NeuroKey
color 0B

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo.
  echo  [XATO] .venv topilmadi.
  echo  Birinchi marta:  python -m venv .venv
  echo  Keyin:           .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   NEUROKEY  —  faqat CMD (fon rejim YO'Q)
echo  ============================================================
echo   Ochish : !NeuroKey.bat
echo   Yopish : !NeuroKey.bat stop   yoki   F10
echo  ============================================================
echo.

echo  [0] Fon jarayonlar va avto-ishga tushirish o'chirilmoqda...
call :KILL_ALL
reg delete "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v NeuroKey /f >nul 2>&1
schtasks /delete /tn "NeuroKey" /f >nul 2>&1
timeout /t 1 /nobreak >nul
echo       Tayyor — faqat shu CMD oynasi orqali ishlaydi.
echo.

echo  [1] HUD...
start "NK-HUD" /max cmd /k "cd /d %~dp0 && %VENV_PY% neurokey_hud.py"
timeout /t 2 /nobreak >nul
echo.

rem ========== API ==========
set "OPENAI_BASE_URL=https://api.groq.com/openai/v1"
set "OPENAI_CHAT_MODEL=qwen/qwen3.6-27b"

rem ========== TIL / OVoz ==========
set "STT_LANGUAGE=uz"
set "NEUROKEY_UI_LANG=uz"
set "TTS_USE_EDGE_RUSSIAN=1"
rem Eslatma: avval tts_openai.py da "uz" tili uchun alohida ovoz tanlash yo'q edi
rem (faqat "en" va "rus" shoxobchalari bor edi), shuning uchun bu yerda o'zbekcha
rem ovoz "RUSSIAN_VOICE" o'zgaruvchisiga qo'yib qo'yilgan edi (ishlagan, lekin
rem chalkash edi). Endi tts_openai.py da haqiqiy "uz" shoxobchasi bor —
rem TTS_EDGE_UZBEK_VOICE to'g'ri o'zgaruvchi. RUSSIAN_VOICE shu yerda qoldirilgan
rem (zararsiz, endi ishlatilmaydi) — orqaga qarab moslik uchun.
set "TTS_EDGE_RUSSIAN_VOICE=uz-UZ-SardorNeural"
set "TTS_EDGE_UZBEK_VOICE=uz-UZ-SardorNeural"
set "TTS_SKIP_OPENAI=1"
set "TTS_SPEED=1.0"
set "TTS_VOLUME_GAIN=2.5"
set "NEUROKEY_TTS_MODE=chunk"
set "NEUROKEY_TTS_SIMPLE_PLAYBACK=1"
rem Naushnik/mikrofon avtomatik (noto'g'ri index = ovoz chiqmaydi)
set "AUTO_SELECT_AUDIO_DEVICE=1"
set "MIC_NAME_HINTS=fifine,microphone,микрофон"
set "SPEAKER_NAME_HINTS=headphone,headphones,науш,High Definition Audio"

rem ========== FON REJIM — BUTUNLAY O'CHIQ ==========
set "NEUROKEY_BG_AUTOTALK=0"
set "NEUROKEY_ADLF_ENABLED=0"
set "NEUROKEY_PROACTIVE_INTERVAL_SEC=0"
set "NEUROKEY_PROACTIVE_FIRST_DELAY_SEC=0"
set "NEUROKEY_PROACTIVE_SCREEN=0"
set "NEUROKEY_PROACTIVE_CURIO_OFF=1"
set "NEUROKEY_SELFIMPROVE_ENABLED=0"
set "NEUROKEY_SPONTANEITY_RATE=0"
set "ADLF_CYCLE_INTERVAL_SEC=0"
set "ADLF_ZERO_LATENCY_HOOKS=0"
set "NEUROKEY_SKIP_STARTUP_TTS=1"
set "NEUROKEY_STARTUP_MESSAGE="
set "NEUROKEY_STARTUP_FROM_LLM=0"

rem ========== Subtitr pastda YO'Q — faqat ovoz ==========
set "NEUROKEY_DISPLAY_OVERLAY=0"
set "NEUROKEY_SUBTITLE_PER_CHUNK=0"
set "NEUROKEY_VOICE_ONLY_UI=0"

rem ========== Demo shablonlari YO'Q ==========
set "NEUROKEY_DEMO_FRIENDLY=0"
set "NEUROKEY_INVESTOR_DEMO=0"
set "NEUROKEY_INSTANT_REPLIES=0"

rem ========== Sensorlar (ko'radi, lekin o'zi gapirmaydi) ==========
set "NEUROKEY_BG_SENSOR=1"
set "NEUROKEY_CAMERA_ENABLED=1"
set "NEUROKEY_CAMERA_INTERVAL_SEC=2.5"
set "NEUROKEY_FACE_GUARD=1"
set "SCREEN_CAPTURE_INTERVAL_SEC=3"
set "NEUROKEY_SCREEN_MONITOR=0"

rem ========== Suniy ong ==========
set "NEUROKEY_INNER_SPEECH=1"
set "NEUROKEY_BOSQICH3=1"
set "NEUROKEY_EMBODIMENT=1"
set "NEUROKEY_FREE_ENERGY=1"
set "NEUROKEY_GWT_INTEGRATION=1"
set "NEUROKEY_DREAM_CONSOLIDATION=1"
set "NEUROKEY_CURIOSITY_ENGINE=1"
set "NEUROKEY_BIOMETRIC_BLOCK=0"
set "NEUROKEY_ALWAYS_OWNER=1"
set "NEUROKEY_REQUIRE_WAKE_WORD=0"
set "NEUROKEY_OFFLINE_ONLY=0"
set "NEUROKEY_FORCE_WEB=1"
set "NEUROKEY_LATENCY_ZERO=1"
set "NEUROKEY_INTERRUPT_TTS_ON_SPEECH=1"
set "NEUROKEY_HUD_AFFECT_SYNC=1"
set "LLM_TEMPERATURE=0.35"
set "PYTHONWARNINGS=ignore"
set "PYTHONIOENCODING=utf-8"

echo  [2] NeuroKey ishga tushmoqda (ovoz + mikrofon)...
echo       Yopish: F10 yoki !NeuroKey.bat stop
echo.

"%VENV_PY%" "%~dp0main.py"

echo.
if errorlevel 1 (
  echo  [XATO] Yuqoridagi xabarni o'qing.
) else (
  echo  [TUGADI] NeuroKey to'xtadi.
)
echo.
pause
exit /b 0

:KILL_ALL
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%main.py%%'" get processid /format:list 2^>nul ^| find "="') do taskkill /PID %%i /F >nul 2>&1
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%neurokey_hud.py%%'" get processid /format:list 2^>nul ^| find "="') do taskkill /PID %%i /F >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq NK-HUD*" >nul 2>&1
exit /b 0
