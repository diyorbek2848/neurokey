# -*- coding: utf-8 -*-
"""NeuroKey — Agentic Loop (ko'rib-harakat qilib-yana ko'rish tsikli).

MUAMMO (asoschi so'roviga ko'ra, 2026-09-11): `planner.py` murakkab
vazifa kelganda BUTUN bosqichlar rejasini BIR MARTA, NATIJALARNI
KO'RMASDAN oldindan tuzadi ("1-qadam: qidir, 2-qadam: och, 3-qadam:
bos" — hammasi ko'zi yumuq). Bu internetda/kompyuterda ERKIN harakat
qilish uchun yetarli emas: chinakam erkin harakat — odam qiladigandek —
HAR safar avval KO'RIB, keyin nima qilishni HAL qilib, harakat qilib,
YANA ko'rib, yana hal qilishni talab qiladi. Kutilmagan narsa chiqsa
(sahifa boshqacha ko'rinsa, dastur ochilmasa) — tizim buni KO'RIB,
SHUNGA qarab qaror o'zgartirishi kerak, oldindan yozilgan ssenariyni
ko'r-ko'rona davom ettirmasligi kerak.

Bu modul aynan shu tsiklni amalga oshiradi:
    1. KO'RISH   — ekran holatini o'qish (screen_vision orqali)
    2. HAL QILISH — LLM'dan FAQAT BITTA keyingi amalni so'rash
                    (butun reja emas — har safar qaytadan, yangi
                    ko'rgan holatga qarab)
    3. HARAKAT   — amalni bajarish (executor.py orqali)
    4. Natijani tarixga qo'shib, 1-qadamga qaytish
    5. LLM "DONE" desa yoki max_steps'ga yetilsa to'xtash

XAVFSIZLIK (MUHIM — o'qib chiqing):
Bu tsikl AVTONOM — har bir qadamni odam ko'zi bilan kuzatib
turmaydi (ovozli yordamchi fon jarayonida ishlaydi). Shuning uchun
bu yerda LLM hech qachon quyidagilarni O'ZI hal qilib bajarolmaydi:
fayl o'chirish/yozish/ko'chirish, dasturni majburan yopish/o'chirish,
buyruq (shell/PowerShell) bajarish, kompyuterni o'chirish/qayta
yuklash. Bular ATAYLAB ruxsat etilgan amallar ro'yxatida YO'Q —
LLM ularni so'rasa ham, kod darajasida rad etiladi (faqat "bu yerda
ruxsat yo'q" deb aytiladi, tsikl davom etadi yoki to'xtaydi).

Nega bu muhim: ko'p-qadamli avtonom tsiklda LLM bitta noto'g'ri
taxmin qilsa (masalan "bu faylni o'chirsam yaxshiroq bo'lardi" deb
o'ylab qolsa), buni hech kim darhol to'xtata olmaydi — inson bu
qadamlarni jonli kuzatmayapti. Shuning uchun qaytarib bo'lmas /
zararli amallar bu tsikl uchun DOIM taqiqlangan — foydalanuvchi
ularni alohida, TO'G'RIDAN-TO'G'RI (ushbu tsikldan tashqarida)
so'rasa, ODATDAGI yo'l bilan bajariladi, xuddi avvalgidek.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# ── Xavfsizlik: ruxsat etilgan amallar RO'YXATI (denylist emas — allowlist,
# ya'ni ro'yxatda YO'Q narsa AVTOMATIK taqiqlangan bo'ladi, keyinchalik
# executor.py'ga yangi xavfli amal qo'shilib qolsa ham bu yerga ta'sir
# qilmaydi) ────────────────────────────────────────────────────────────────
ALLOWED_ACTIONS = frozenset({
    "open_app", "process_start",
    "mouse_move", "mouse_click", "mouse_double_click",
    "key_press", "key_type", "hotkey",
    "window_focus", "window_minimize", "window_maximize",
    "window_list", "window_by_title",
    "file_read", "file_search", "file_list", "file_exists",
    "clipboard_get", "clipboard_set",
})
# Kod darajasida qo'shimcha himoya — hatto ALLOWED_ACTIONS ro'yxatiga
# kimdir keyinchalik xato bilan qo'shib qo'ysa ham, bular HECH QACHON
# bu tsiklda bajarilmaydi.
_HARD_DENY = frozenset({
    "file_delete", "file_write", "file_append", "file_create",
    "file_copy", "file_move", "process_kill", "window_close",
    "run_command", "run_powershell", "shutdown_pc", "restart_pc",
    "logoff_user", "uninstall_app", "close_all_apps",
})

_MAX_STEPS_HARD_CAP = 10   # bundan ko'p qadam — chaqiruvchi qancha so'ramasin
_STEP_TIMEOUT_SEC = 20.0   # bitta LLM-qaror chaqiruvi uchun eng ko'p kutish


@dataclass
class AgenticStep:
    action_line: str
    result_ok: bool
    result_message: str


@dataclass
class AgenticResult:
    ok: bool
    final_message: str
    steps: List[AgenticStep] = field(default_factory=list)
    stopped_reason: str = ""  # "done" | "max_steps" | "error" | "denied_only"


def _perceive() -> str:
    """Hozirgi ekran holatini o'qish. Xato bo'lsa — bo'sh string
    (tsikl davom etaveradi, faqat "ko'rlik" bilan)."""
    try:
        from screen_vision import get_screen_context_safe
        ocr_txt, vision_desc = get_screen_context_safe()
        parts = []
        if vision_desc:
            parts.append(f"[Ko'rinish] {vision_desc[:1200]}")
        if ocr_txt:
            parts.append(f"[Ekrandagi matn] {ocr_txt[:1200]}")
        return "\n".join(parts)
    except Exception as e:
        log.debug("[AgenticLoop] perceive xato: %s", e)
        return ""


_ACTION_RE = re.compile(r"^\s*ACTION:\s*(\w+)\s*(.*)$", re.IGNORECASE)
_DONE_RE = re.compile(r"^\s*DONE:\s*(.*)$", re.IGNORECASE | re.DOTALL)


def _ask_next_step(task: str, history: List[AgenticStep], screen_text: str) -> str:
    """LLM'dan FAQAT bitta keyingi amalni so'raydi. Xom javob qatorini
    qaytaradi (parse qilinmagan) — chaqiruvchi buni parse qiladi."""
    hist_lines = []
    for i, s in enumerate(history[-6:], 1):  # oxirgi 6 qadam yetarli — token tejash
        status = "OK" if s.result_ok else "XATO"
        hist_lines.append(f"{i}. {s.action_line} -> {status}: {s.result_message[:150]}")
    hist_block = "\n".join(hist_lines) if hist_lines else "(hali qadam yo'q — bu birinchi)"

    prompt = (
        f"VAZIFA: {task}\n\n"
        f"OLDINGI QADAMLAR:\n{hist_block}\n\n"
        f"HOZIRGI EKRAN HOLATI:\n{screen_text[:2000] if screen_text else '(ekran o‘qilmadi)'}\n\n"
        "Endi FAQAT BITTA keyingi amalni tanla — butun rejani emas, faqat "
        "KEYINGI bitta qadamni, hozir KO'RGANINGGA qarab.\n\n"
        "Format — AYNAN shu ikki turdan BIRI, boshqa hech narsa yozma:\n"
        "  ACTION: <nom> <parametr(lar)>\n"
        "  DONE: <vazifa natijasi — bajarildimi, nima topding, yoki nega bajarib bo'lmadi>\n\n"
        "Ruxsat etilgan <nom>lar: open_app, mouse_click, mouse_double_click, "
        "mouse_move, key_type, key_press, hotkey, window_focus, window_list, "
        "window_by_title, file_search, file_read, file_list, clipboard_get, "
        "clipboard_set.\n"
        "Masalan: 'ACTION: open_app chrome' yoki 'ACTION: mouse_click 640 480' "
        "yoki 'ACTION: key_type python nima'.\n"
        "Vazifa bajarilgan yoki davom ettirib bo'lmaydigan bo'lsa — DONE yoz.\n"
        "FAQAT bitta qator qaytar."
    )
    try:
        from llm_router import answer as _ans
        out = _ans(prompt, brief=True) or ""
        return out.strip().splitlines()[0] if out.strip() else ""
    except Exception as e:
        log.debug("[AgenticLoop] LLM qaror xato: %s", e)
        return ""


def run_agentic_task(task: str, max_steps: int = 6) -> AgenticResult:
    """Asosiy tsikl. Har chaqiruvda BITTA to'liq (ko'rish->hal qilish->
    harakat) aylanish bajariladi, natijalar tarixga qo'shiladi.

    Hech qachon exception ko'tarmaydi — har doim AgenticResult qaytaradi
    (xato bo'lsa ok=False, stopped_reason="error")."""
    task = (task or "").strip()
    if not task:
        return AgenticResult(ok=False, final_message="Vazifa bo'sh", stopped_reason="error")

    max_steps = max(1, min(int(max_steps or 6), _MAX_STEPS_HARD_CAP))
    history: List[AgenticStep] = []

    try:
        from executor import execute_from_string
    except Exception as e:
        return AgenticResult(ok=False, final_message=f"executor yuklanmadi: {e}",
                              stopped_reason="error")

    for step_i in range(max_steps):
        screen_text = _perceive()

        t0 = time.monotonic()
        raw = _ask_next_step(task, history, screen_text)
        if (time.monotonic() - t0) > _STEP_TIMEOUT_SEC:
            log.warning("[AgenticLoop] LLM qarori juda sekin (%.1fs) — to'xtatildi",
                        time.monotonic() - t0)

        if not raw:
            history.append(AgenticStep(action_line="(bo'sh javob)", result_ok=False,
                                        result_message="LLM javob bermadi"))
            break

        m_done = _DONE_RE.match(raw)
        if m_done:
            final_msg = m_done.group(1).strip() or "Vazifa yakunlandi."
            return AgenticResult(ok=True, final_message=final_msg, steps=history,
                                  stopped_reason="done")

        m_act = _ACTION_RE.match(raw)
        if not m_act:
            # Format buzilgan — bitta imkoniyat beramiz, keyin to'xtatamiz
            history.append(AgenticStep(action_line=raw, result_ok=False,
                                        result_message="Format tushunilmadi (ACTION:/DONE: emas)"))
            continue

        act_name = m_act.group(1).strip().lower()
        act_line = f"ACTION: {act_name} {m_act.group(2).strip()}".strip()

        if act_name in _HARD_DENY or act_name not in ALLOWED_ACTIONS:
            log.info("[AgenticLoop] rad etildi (ruxsat yo'q): %s", act_name)
            history.append(AgenticStep(
                action_line=act_line, result_ok=False,
                result_message=(f"'{act_name}' bu avtonom rejimda ruxsat etilmagan "
                                 "(xavfsizlik cheklovi) — boshqa yo'l top yoki DONE de."),
            ))
            continue

        try:
            result = execute_from_string(act_line, retry=True)
            history.append(AgenticStep(action_line=act_line, result_ok=bool(result.ok),
                                        result_message=str(result.message or "")))
        except Exception as e:
            history.append(AgenticStep(action_line=act_line, result_ok=False,
                                        result_message=f"bajarish xatosi: {e}"))

    # max_steps tugadi, DONE kelmadi
    last_ok = history[-1].result_ok if history else False
    return AgenticResult(
        ok=last_ok,
        final_message=("Qadamlar chegarasiga yetildi — vazifa to'liq yakunlanmagan "
                        "bo'lishi mumkin. Oxirgi holat: " +
                        (history[-1].result_message if history else "hech narsa bajarilmadi")),
        steps=history,
        stopped_reason="max_steps",
    )
