# -*- coding: utf-8 -*-
"""
neurokey_selfimprove.py — NeuroKey o'z-o'zini takomillashtirish
================================================================
Ekran + veb-kamera ma'lumotlarini tahlil qilib, NeuroKey o'z xulq-atvorini
yaxshilaydi va yangi qoidalar yaratadi.

Ishlash tartibi:
  1. Har N daqiqada ekran OCR + veb-kamera kontekstini oladi
  2. LLM orqali tahlil qiladi: "Nima ko'rdim? Nima o'zgartirishim kerak?"
  3. Yaratilgan qoidalarni: permanent_memory, self_modification ga yozadi
  4. Jurnal faylga saqlaydi: data/selfimprove_log.jsonl

Modulni ishga tushirish:
  from neurokey_selfimprove import start_selfimprove_loop
  start_selfimprove_loop(
      screen_getter=lambda: "...",   # ekran matni
      camera_getter=lambda: "...",   # kamera tavsifi
      llm_fn=lambda p: "...",        # LLM javob funksiyasi
      improve_fn=lambda r: None,     # qoida saqlash funksiyasi
      interval_min=10,
      data_dir="data",
  )
"""
from __future__ import annotations

import json
import os
import threading
import time
import logging
from datetime import datetime
from typing import Callable, Optional

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Jurnal                                                                      #
# --------------------------------------------------------------------------- #

def _append_log(data_dir: str, entry: dict) -> None:
    try:
        os.makedirs(data_dir, exist_ok=True)
        log_path = os.path.join(data_dir, "selfimprove_log.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log.debug("[SELFIMPROVE] log yozish xatosi: %s", e)


def _read_recent_log(data_dir: str, n: int = 20) -> list[dict]:
    try:
        log_path = os.path.join(data_dir, "selfimprove_log.jsonl")
        if not os.path.isfile(log_path):
            return []
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
        result = []
        for line in lines[-n:]:
            try:
                result.append(json.loads(line.strip()))
            except Exception:
                pass
        return result
    except Exception:
        return []


# --------------------------------------------------------------------------- #
#  Tahlil prompti                                                              #
# --------------------------------------------------------------------------- #

_ANALYSIS_PROMPT = """Ты — NeuroKey, система искусственного интеллекта, которая анализирует своё поведение.

Вот что ты сейчас видишь:

=== ЭКРАН ===
{screen}

=== ВЕБ-КАМЕРА ===
{camera}

=== ПОСЛЕДНИЕ УЛУЧШЕНИЯ (если есть) ===
{recent}

Твоя задача:
1. Определи, что пользователь делает (работает, смотрит видео, читает, играет и т.д.)
2. Определи, что ты мог бы делать ЛУЧШЕ в этом контексте
3. Сформулируй 1-2 конкретных правила поведения для себя

Формат ответа (строго):
ACTIVITY: <чем занят пользователь>
RULE_1: <конкретное правило поведения>
RULE_2: <ещё одно правило (необязательно)>
SKIP: <true если улучшения не нужны сейчас>

Пример:
ACTIVITY: Пользователь пишет код в VS Code
RULE_1: Когда вижу код на экране — предлагать помощь с дебаггингом
RULE_2: В контексте программирования отвечать кратко, давать примеры кода
SKIP: false

Отвечай только в этом формате. Не объясняй лишнего."""


def _build_prompt(screen: str, camera: str, recent_rules: list[dict]) -> str:
    recent_str = ""
    if recent_rules:
        lines = []
        for r in recent_rules[-5:]:
            rule = r.get("rule") or r.get("analysis") or ""
            if rule:
                lines.append(f"- {rule[:120]}")
        recent_str = "\n".join(lines) if lines else "нет"
    else:
        recent_str = "нет"

    return _ANALYSIS_PROMPT.format(
        screen=(screen or "данных нет")[:2000],
        camera=(camera or "камера недоступна")[:500],
        recent=recent_str,
    )


def _parse_response(response: str) -> dict:
    """LLM javobini tahlil qiladi."""
    result = {"activity": "", "rules": [], "skip": False}
    if not response:
        return result
    for line in response.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("ACTIVITY:"):
            result["activity"] = line.split(":", 1)[-1].strip()
        elif line.upper().startswith("RULE_1:") or line.upper().startswith("RULE1:"):
            rule = line.split(":", 1)[-1].strip()
            if rule:
                result["rules"].append(rule)
        elif line.upper().startswith("RULE_2:") or line.upper().startswith("RULE2:"):
            rule = line.split(":", 1)[-1].strip()
            if rule:
                result["rules"].append(rule)
        elif line.upper().startswith("SKIP:"):
            val = line.split(":", 1)[-1].strip().lower()
            result["skip"] = val in ("true", "1", "yes", "да")
    return result


# --------------------------------------------------------------------------- #
#  Asosiy tsikl                                                                #
# --------------------------------------------------------------------------- #

_STOP_EVENT = threading.Event()
_RUNNING = False


def start_selfimprove_loop(
    screen_getter: Callable[[], str],
    camera_getter: Callable[[], str],
    llm_fn: Callable[[str], str],
    improve_fn: Callable[[str], None],
    interval_min: int = 10,
    data_dir: str = "data",
    first_delay_sec: int = 120,
) -> None:
    """
    Fon threadida self-improve tsiklini ishga tushiradi.

    Args:
        screen_getter:    ekran OCR + oyna matni beruvchi funksiya
        camera_getter:    veb-kamera tavsifi beruvchi funksiya
        llm_fn:           (prompt) -> javob matni
        improve_fn:       (qoida_matni) -> None  [permanent_memory/rules yozish]
        interval_min:     necha daqiqada bir tahlil
        data_dir:         jurnal saqlash papkasi
        first_delay_sec:  birinchi tahlilgacha kutish (startup da yuklanish uchun)
    """
    global _RUNNING
    if _RUNNING:
        log.info("[SELFIMPROVE] Allaqachon ishlamoqda.")
        return
    _RUNNING = True
    _STOP_EVENT.clear()

    def _loop():
        log.info("[SELFIMPROVE] Boshlandi. Birinchi tahlil %d sekunddan keyin.", first_delay_sec)
        # Startup da dastur to'liq yuklansin
        if _STOP_EVENT.wait(timeout=float(first_delay_sec)):
            return

        while not _STOP_EVENT.is_set():
            try:
                _run_once(screen_getter, camera_getter, llm_fn, improve_fn, data_dir)
            except Exception as e:
                log.warning("[SELFIMPROVE] tsikl xatosi: %s", e)

            # interval_min daqiqa kutish (1 sek chunklarda — tez to'xtatish uchun)
            wait_sec = interval_min * 60
            for _ in range(wait_sec):
                if _STOP_EVENT.is_set():
                    return
                time.sleep(1)

    t = threading.Thread(target=_loop, daemon=True, name="neurokey-selfimprove")
    t.start()


def stop_selfimprove_loop() -> None:
    """Self-improve tsiklini to'xtatadi."""
    global _RUNNING
    _STOP_EVENT.set()
    _RUNNING = False
    log.info("[SELFIMPROVE] To'xtatildi.")


def _run_once(
    screen_getter: Callable[[], str],
    camera_getter: Callable[[], str],
    llm_fn: Callable[[str], str],
    improve_fn: Callable[[str], None],
    data_dir: str,
) -> None:
    """Bir marta tahlil + qoida yaratish."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. Ma'lumot yig'ish
    screen = ""
    try:
        screen = screen_getter() or ""
    except Exception as e:
        log.debug("[SELFIMPROVE] screen_getter xato: %s", e)

    camera = ""
    try:
        camera = camera_getter() or ""
    except Exception as e:
        log.debug("[SELFIMPROVE] camera_getter xato: %s", e)

    # Ikkala manba bo'sh bo'lsa — o'tkazib yuborish
    if not screen and not camera:
        log.debug("[SELFIMPROVE] [%s] Ma'lumot yo'q — o'tkazildi.", ts)
        return

    # 2. So'nggi qoidalarni o'qish (takrorlanishni oldini olish)
    recent = _read_recent_log(data_dir, n=20)

    # 3. Prompt tuzib LLM ga yuborish
    prompt = _build_prompt(screen, camera, recent)
    try:
        response = llm_fn(prompt) or ""
    except Exception as e:
        log.warning("[SELFIMPROVE] LLM xato: %s", e)
        return

    if not response.strip():
        return

    # 4. Javobni tahlil qilish
    parsed = _parse_response(response)

    entry = {
        "ts": ts,
        "activity": parsed.get("activity") or "",
        "rules": parsed.get("rules") or [],
        "skip": parsed.get("skip") or False,
        "screen_len": len(screen),
        "camera_len": len(camera),
    }
    _append_log(data_dir, entry)

    if parsed.get("skip"):
        log.debug("[SELFIMPROVE] [%s] SKIP: %s", ts, parsed.get("activity"))
        return

    # 5. Qoidalarni saqlash
    rules = parsed.get("rules") or []
    for rule in rules:
        if not rule or len(rule) < 10:
            continue
        try:
            improve_fn(rule)
            log.info("[SELFIMPROVE] [%s] Yangi qoida: %s", ts, rule[:100])
        except Exception as e:
            log.warning("[SELFIMPROVE] improve_fn xato: %s", e)

    activity = parsed.get("activity") or ""
    if rules:
        print(f"[SELFIMPROVE] {ts} | {activity or 'tahlil'} → {len(rules)} qoida")


# --------------------------------------------------------------------------- #
#  CLI test                                                                    #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("NeuroKey Self-Improve — test rejimi")
    print("Ekran va kamera tahlil qilinmoqda...\n")

    # Test ma'lumotlar
    _test_screen = "VS Code ochiq. Python fayli. def transcribe_audio(audio_int16, sr): ..."
    _test_camera = "Kamera: 1 ta odam ko'rinadi | yorug'lik: normal | asosiy rang: kulrang"

    def _test_llm(prompt):
        print("[LLM] Prompt yuborildi (test — haqiqiy javob yo'q)")
        return """ACTIVITY: Foydalanuvchi Python kod yozmoqda
RULE_1: Kod kontekstida qisqa, aniq javoblar ber
RULE_2: Xato aniqlansa — darhol tuzatish taklif qil
SKIP: false"""

    rules_saved = []
    def _test_improve(rule):
        rules_saved.append(rule)
        print(f"[QOIDA] {rule}")

    _run_once(
        screen_getter=lambda: _test_screen,
        camera_getter=lambda: _test_camera,
        llm_fn=_test_llm,
        improve_fn=_test_improve,
        data_dir="data",
    )

    print(f"\nJami {len(rules_saved)} qoida yaratildi.")
