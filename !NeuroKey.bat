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
echo   Yopish : !NeuroKey.bat stop   yoki   Ctrl+F10
echo   TIL    : RUS (STT+TTS+LLM) — shu fayl
echo   Ingliz : ..\juma_en\!NeuroKey.bat
echo  ============================================================
echo.

echo  [0] Fon jarayonlar va avto-ishga tushirish o'chirilmoqda...
call :KILL_ALL
reg delete "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v NeuroKey /f >nul 2>&1
schtasks /delete /tn "NeuroKey" /f >nul 2>&1
timeout /t 1 /nobreak >nul
echo       Tayyor — faqat shu CMD oynasi orqali ishlaydi.
echo.

rem echo  [1] HUD...
rem start "NK-HUD" /max cmd /k "cd /d %~dp0 && %VENV_PY% neurokey_hud.py"
rem timeout /t 2 /nobreak >nul
echo.

rem ========== API ==========
set "OPENAI_BASE_URL=https://api.groq.com/openai/v1"
rem Tez javob: 8b-instant (70b sekin). Katta model: set GROQ_FAST_MODEL=qwen/qwen3.6-27b
set "GROQ_FAST_MODEL=openai/gpt-oss-20b"
set "OPENAI_CHAT_MODEL=openai/gpt-oss-20b"

rem ========== TIL / OVoz ==========
set "STT_LANGUAGE=ru"
set "NEUROKEY_UI_LANG=ru"
set "TTS_USE_EDGE_RUSSIAN=1"
set "TTS_EDGE_RUSSIAN_VOICE=ru-RU-DmitryNeural"
set "TTS_SKIP_OPENAI=1"
set "TTS_SPEED=1.12"
set "TTS_VOLUME_GAIN=3.0"
set "NEUROKEY_HOTKEYS=0"
rem chunk = har jumla darhol ovoz (full = butun javobni kutadi, 8-10s jim)
set "NEUROKEY_TTS_MODE=chunk"
set "NEUROKEY_TTS_SIMPLE_PLAYBACK=1"
set "NEUROKEY_TTS_DUAL_FINISH=0"
set "STT_PAUSE_DURING_TTS=1"
set "NEUROKEY_INTERRUPT_TTS_ON_SPEECH=0"
rem Naushnik/mikrofon avtomatik (noto'g'ri index = ovoz chiqmaydi)
set "AUTO_SELECT_AUDIO_DEVICE=1"
set "MIC_NAME_HINTS=fifine,microphone,микрофон"
set "SPEAKER_NAME_HINTS=headphone,headphones,науш,High Definition Audio"

rem ========== RAM bo'yicha avtomatik tier (8GB=LITE, 16GB=STANDARD) ==========
set "NEUROKEY_AUTO_TIER=1"
rem To'liq og'ir rejim (15GB KB yo'li): set "NEUROKEY_BOOT_TIER=full" va set "NEUROKEY_USE_LARGE_KB=1"

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
set "NEUROKEY_SKIP_STARTUP_TTS=0"
set "NEUROKEY_STARTUP_MESSAGE="
set "NEUROKEY_STARTUP_FROM_LLM=0"

rem ========== Subtitr pastda YO'Q — faqat ovoz ==========
set "NEUROKEY_DISPLAY_OVERLAY=0"
set "NEUROKEY_SUBTITLE_PER_CHUNK=0"
set "NEUROKEY_VOICE_ONLY_UI=0"

rem ========== Demo shablonlari YO'Q ==========
set "NEUROKEY_DEMO_FRIENDLY=0"
set "NEUROKEY_INVESTOR_DEMO=0"
set "NEUROKEY_INSTANT_REPLIES=1"

rem ========== Sensorlar — boot_tier (LITE=off, STANDARD=bg only) ==========
rem set "NEUROKEY_BG_SENSOR=1"
rem set "NEUROKEY_CAMERA_ENABLED=1"
set "NEUROKEY_CAMERA_INTERVAL_SEC=2.5"
set "NEUROKEY_FACE_GUARD=0"
set "SCREEN_CAPTURE_INTERVAL_SEC=3"
set "NEUROKEY_SCREEN_MONITOR=0"

rem ========== Suniy ong — modullar SAQLANADI, boot_tier RAM bo'yicha yoqadi ==========
rem attention_router har savolda faqat KERAKLI modullarni chaqiradi (GWT-4).
rem Quyidagi qatorlar o'chirildi — NEUROKEY_AUTO_TIER + boot_tier.py boshqaradi.
rem Demo/investor uchun: NEUROKEY_BOOT_TIER=full NEUROKEY_USE_LARGE_KB=1
set "NEUROKEY_SPECULATIVE_RESPONSE=0"
set "NEUROKEY_INNER_SPEECH=1"
set "NEUROKEY_NARRATIVE_SELF=1"
set "NEUROKEY_GWT_INTEGRATION=1"
set "NEUROKEY_AFFECT_TO_DECISIONS=1"
set "NEUROKEY_HUD_AFFECT_SYNC=1"
set "NEUROKEY_BIOMETRIC_BLOCK=0"
set "NEUROKEY_ALWAYS_OWNER=1"
set "NEUROKEY_REQUIRE_WAKE_WORD=0"
set "NEUROKEY_OFFLINE_ONLY=0"
set "NEUROKEY_FORCE_WEB=1"
set "NEUROKEY_LATENCY_ZERO=1"
set "NEUROKEY_VOSK_STABLE_PARTIAL_MS=400"
set "NEUROKEY_INSTANT_RESPONSE=1"
rem Temperatura 0.6 — hayol, ijod, jonli javob (0.35 juda quruq edi)
set "LLM_TEMPERATURE=0.45"
set "LLM_MAX_TOKENS_DEFAULT=160"
set "STT_SILENCE_HOLD_SEC=0.65"
set "STT_WAIT_AFTER_TTS_MS=250"
set "NEUROKEY_HISTORY_LIMIT=6"
set "PYTHONWARNINGS=ignore"
set "PYTHONIOENCODING=utf-8"

echo  [2] NeuroKey ishga tushmoqda (ovoz + mikrofon)...
echo       Yopish: Ctrl+F10 yoki !NeuroKey.bat stop
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
