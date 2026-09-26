@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if /i "%~1"=="stop"  goto :STOP
if /i "%~1"=="benchmark" goto :BENCH
goto :START

:STOP
call "%~dp0!NeuroKey.bat" stop
exit /b 0

:BENCH
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
"%VENV_PY%" "%~dp0benchmark_20.py"
pause
exit /b 0

:START
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [XATO] .venv topilmadi.
  pause
  exit /b 1
)

title NeuroKey AGI Yo'li
color 0A

echo.
echo  ============================================================
echo   NEUROKEY — AGI YO'LI (L1 to L2)
echo  ============================================================
echo   Benchmark: python benchmark_20.py
echo   Yopish   : !NeuroKey_AGI.bat stop
echo  ============================================================
echo.

rem --- AGI yo'li muhiti ---
set "NEUROKEY_AUTO_TIER=1"
set "NEUROKEY_USE_LARGE_KB=0"
set "NEUROKEY_KB_PREWARM=0"
set "NEUROKEY_AGENTIC_LOOP=1"
set "NEUROKEY_AGENTIC_MAX_STEPS=6"
set "NEUROKEY_GWT_INTEGRATION=1"
set "NEUROKEY_INNER_SPEECH=1"
set "NEUROKEY_NARRATIVE_SELF=1"
set "NEUROKEY_BG_AUTOTALK=0"
set "NEUROKEY_ADLF_ENABLED=0"
set "NEUROKEY_SELFIMPROVE_ENABLED=0"
set "NEUROKEY_CAMERA_ENABLED=0"
set "NEUROKEY_SCREEN_MONITOR=0"
set "NEUROKEY_CURIOSITY_ENGINE=0"
set "NEUROKEY_INSTANT_REPLIES=1"
set "NEUROKEY_LATENCY_ZERO=1"
set "NEUROKEY_HISTORY_LIMIT=6"
set "NEUROKEY_DISPLAY_OVERLAY=0"
set "NEUROKEY_HOTKEYS=0"
set "NEUROKEY_ALLOW_UNLICENSED=1"
set "PYTHONIOENCODING=utf-8"

rem --- Groq (online) — !NeuroKey.bat bilan bir xil ---
set "OPENAI_BASE_URL=https://api.groq.com/openai/v1"
set "GROQ_FAST_MODEL=openai/gpt-oss-20b"
set "OPENAI_CHAT_MODEL=openai/gpt-oss-20b"
set "STT_LANGUAGE=ru"
set "NEUROKEY_UI_LANG=ru"
set "TTS_USE_EDGE_RUSSIAN=1"
set "TTS_EDGE_RUSSIAN_VOICE=ru-RU-DmitryNeural"
set "TTS_SKIP_OPENAI=1"
set "NEUROKEY_TTS_MODE=chunk"
set "LLM_TEMPERATURE=0.45"
set "LLM_MAX_TOKENS_DEFAULT=160"
set "AUTO_SELECT_AUDIO_DEVICE=1"

echo  [1] AGI benchmark (20 vazifa)...
"%VENV_PY%" "%~dp0benchmark_20.py"
echo.
echo  [2] NeuroKey AGI rejimida ishga tushmoqda...
echo       Agent yoqilgan (xavfsiz allowlist). Mikrofon bilan gapiring.
echo.

"%VENV_PY%" "%~dp0main.py"

echo.
pause
exit /b 0
