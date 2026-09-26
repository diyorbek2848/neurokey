@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [XATO] .venv topilmadi. python -m venv .venv
  pause
  exit /b 1
)

title NeuroKey YENGIL — 8GB / Offline
color 0E

echo.
echo  ============================================================
echo   NEUROKEY YENGIL — 8 GB noutbuk / offline SLM
echo  ============================================================
echo   Tier: LITE (majburiy)
echo   Model: Ollama qwen2.5:1.5b
echo   Agent: o'chiq (xavfsizlik)
echo  ============================================================
echo.

set "NEUROKEY_BOOT_TIER=lite"
set "NEUROKEY_AUTO_TIER=0"
set "NEUROKEY_OFFLINE_ONLY=1"
set "OLLAMA_MODEL=qwen2.5:1.5b"
set "FASTER_WHISPER_MODEL=tiny"
set "NEUROKEY_USE_LARGE_KB=0"
set "NEUROKEY_KB_PREWARM=0"
set "NEUROKEY_AGENTIC_LOOP=0"
set "NEUROKEY_BG_AUTOTALK=0"
set "NEUROKEY_CAMERA_ENABLED=0"
set "NEUROKEY_SCREEN_MONITOR=0"
set "NEUROKEY_GWT_INTEGRATION=1"
set "NEUROKEY_DISPLAY_OVERLAY=0"
set "STT_LANGUAGE=ru"
set "NEUROKEY_UI_LANG=ru"
set "TTS_USE_EDGE_RUSSIAN=1"
set "TTS_SKIP_OPENAI=1"
set "NEUROKEY_HOTKEYS=0"
set "PYTHONIOENCODING=utf-8"
set "NEUROKEY_ALLOW_UNLICENSED=1"

echo  [1] Benchmark (tez)...
"%VENV_PY%" "%~dp0benchmark_20.py" --quick
echo.
echo  [2] NeuroKey yengil rejimda ishga tushmoqda...
echo       Ollama ishlayotganini tekshiring: ollama serve
echo.

"%VENV_PY%" "%~dp0main.py" --offline

echo.
pause
exit /b 0
