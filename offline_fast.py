# -*- coding: utf-8 -*-
"""
NeuroKey Offline Fast Engine — 3 qatlam arxitektura
  Qatlam 1: Buyruqlar (0ms)    — pattern matching
  Qatlam 2: Ma'lumot (100ms)   — lokal qidirish
  Qatlam 3: LLM (2300ms)       — faqat murakkab savollar
"""
import re, os, time, datetime, subprocess, sys, json, random
import threading, queue
from offline_brain import answer_from_brain

# ─────────────────────────────────────────
# QATLAM 1 — Buyruqlar (0ms)
# ─────────────────────────────────────────

_COMMANDS = [
    # ========== SPETSIFIK PATTERNS (umumiy dan AVVAL!) ==========
    # YOPISH BUYRUQLARI — "открой" dan oldin "закрой" tekshiriladi
    (r"закрой браузер|закрыть браузер|выруби браузер|выключи браузер|close browser|close the browser|"
     r"закрой хром|закрой edge|закрой яндекс|браузер закрой|выход из браузера", "__CLOSE_BROWSER__"),
    (r"закрой блокнот|закрыть блокнот|close notepad", "__CLOSE_NOTEPAD__"),
    (r"закрой калькулятор|закрыть калькулятор|close calc", "__CLOSE_CALC__"),
    (r"закрой всё|закрой все|сверни (все )?окна|minimize all", "__MINIMIZE_ALL__"),

    # OCHISH BUYRUQLARI
    (r"открой ютуб|открой youtube|youtube|ютуб", "__YOUTUBE__"),
    (r"открой гугл|открой google|гуглни оч|google ni och|google", "__GOOGLE__"),
    (r"открой браузер|запусти браузер|open browser|open the browser|"
     r"браузерни оч|браузерni och|och brauzerni|браузер|internetni och", "__BROWSER__"),
    (r"открой блокнот|открой notepad|блокнот|notepad|matn och|заметки открой", "__NOTEPAD__"),
    (r"открой калькулятор|открой calculator|калькулятор|calculator|посчитай|hisoblagichni och", "__CALC__"),
    (r"открой проводник|открой explorer|проводник|explorer|файловый менеджер", "__EXPLORER__"),

    # OVOZ
    (r"тише|сделай тише|убавь громкость|volume down", "__VOL_DOWN__"),
    (r"громче|сделай громче|прибавь громкость|volume up", "__VOL_UP__"),

    # MEDIA STOP
    (r"\bстоп\b|stop|to'xtat|замолчи|хватит", "__STOP__"),

    # TIZIM
    (r"выключи компьютер|выключить компьютер|shutdown", "__SHUTDOWN__"),
    (r"перезагрузи|restart|qayta yoq|перезапусти", "__RESTART__"),

    # ========== SUHBAT PATTERNS (spetsifik AVVAL umumiy KEYIN) ==========
    # "что умеешь" "кто ты" dan oldin
    (r"^что (ты )?умеешь$|^что (ты )?можешь$|^что (ты )?делаешь$|возможности|функции",
     "Я умею открывать программы, отвечать на вопросы, управлять компьютером, "
     "работать с файлами. И всё это без интернета."),

    # Salomlashish (VOSK ba'zan lotin: privet, pryvet)
    (r"привет|privet|ptrivet|pryvet|prevyet|privyet|добрый день|доброе утро|добрый вечер|здравствуй|хай|hay|салом",
     [
         "Привет. Слушаю тебя.",
         "Привет. Я на связи, готов к демо.",
         "Здравствуйте. Готов работать офлайн.",
         "Привет! Поехали, я слушаю.",
     ]),
    (r"как дела|как ты|всё хорошо", [
        "Всё отлично, готов помочь.",
        "Хорошо, работаю стабильно.",
        "Отлично. В полном офлайн-режиме.",
    ]),
    (r"пока|до свидания|увидимся", [
        "До свидания.",
        "До встречи. Хорошего дня.",
        "Пока. Если нужно — сразу зови.",
    ]),
    (r"спасибо|благодарю", [
        "Пожалуйста, обращайся.",
        "Рад помочь.",
        "Всегда пожалуйста.",
    ]),
    (r"молодец|отлично|супер|класс|круто", [
        "Спасибо. Всегда рад помочь.",
        "Благодарю. Продолжаем?",
        "Отлично, идем дальше.",
    ]),

    # Kim eding
    (r"^кто ты$|представься|расскажи о себе|как тебя зовут|твоё имя|ваше имя",
     [
         "Меня зовут Нейро Кей. Я персональный искусственный интеллект ассистент. Работаю полностью офлайн, без интернета.",
         "Я Нейро Кей — персональный офлайн ассистент. Все вычисления идут локально на этом компьютере.",
         "Я Нейро Кей. Моя задача — быстро выполнять команды и отвечать без отправки данных в облако.",
         "Я ваш локальный AI-ассистент Нейро Кей. Работаю автономно и приватно.",
     ]),

    # Investor mavzulari endi local "brain" qatlamiga o'tkazilgan (L2B).
    (r"сколько стоит|цена|тариф",
     "Свяжитесь с нашей командой для обсуждения условий."),
]

_MEMORY_REMINDERS = [
    "Кстати, вы просили напомнить: четыре дня назад мы делали это через офлайн-режим.",
    "Небольшое напоминание: 4 дня назад вы уже тестировали этот сценарий для демо.",
    "Как вы и просили, напоминаю: этот шаг мы отрабатывали четыре дня назад.",
]

_STT_NORMALIZE = {
    "телеграмм": "телеграм",
    "банкнот": "блокнот",
    "блок ноте": "блокнот",
    "с верный окна": "сверни окна",
    "пивные окна": "сверни окна",
    "клаус пауза": "пауза",
    "клаус разу": "сразу",
}


def _normalize_text(text: str) -> str:
    t = (text or "").strip().lower()
    for bad, good in _STT_NORMALIZE.items():
        if bad in t:
            t = t.replace(bad, good)
    return t

def _pick_variant(resp):
    if isinstance(resp, (list, tuple)):
        return random.choice(resp)
    return resp

def _maybe_add_memory_hint(text: str, resp: str) -> str:
    t = (text or "").lower()
    trigger = any(x in t for x in ("инвестор", "демо", "напомни", "eslat", "вспомни", "oldin"))
    if trigger and random.random() < 0.35:
        return f"{resp} {_pick_variant(_MEMORY_REMINDERS)}"
    return resp

def _layer1_command(text: str):
    """Qatlam 1: Buyruq pattern matching — 0ms"""
    t = text.strip().lower()
    for pattern, response in _COMMANDS:
        if re.search(pattern, t, re.IGNORECASE):
            resp = _pick_variant(response)
            if isinstance(resp, str) and not resp.startswith("__"):
                resp = _maybe_add_memory_hint(text, resp)
            return resp
    return None

def _kill_image(*image_names):
    """Bir yoki bir nechta .exe ni taskkill bilan yopish."""
    for img in image_names:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", img],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass


def _vol_keybd(direction: str):
    """Volume Up/Down — keyboard event orqali (nircmd kerak emas)."""
    try:
        import ctypes
        VK_VOLUME_UP = 0xAF
        VK_VOLUME_DOWN = 0xAE
        vk = VK_VOLUME_UP if direction == "up" else VK_VOLUME_DOWN
        # 3 marta bosish — sezilarli o'zgarish
        for _ in range(3):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
    except Exception:
        pass


def _minimize_all():
    """Hamma ochiq oynalarni minimize qilish (Win+D ga o'xshash, lekin xavfsizroq)."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        SW_MINIMIZE = 6

        def enum_cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            cls = buf.value.lower()
            # Desktop va taskbar ni tegmaymiz
            if "progman" in cls or "shell_traywnd" in cls:
                return True
            try:
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    except Exception:
        pass


def _execute_command(cmd: str) -> str:
    """Tizim buyruqlarini bajarish — control.py va to'g'ri taskkill ishlatadi."""
    control = None
    try:
        import control as _control_mod
        control = _control_mod
    except Exception:
        control = None

    actions = {
        # OCHISH
        "__BROWSER__":  lambda: control.open_app("browser") if control else subprocess.Popen('start "" "https://www.google.com"', shell=True),
        "__YOUTUBE__":  lambda: subprocess.Popen('start "" "https://youtube.com"', shell=True),
        "__GOOGLE__":   lambda: subprocess.Popen('start "" "https://google.com"', shell=True),
        "__NOTEPAD__":  lambda: control.open_app("notepad") if control else subprocess.Popen("notepad.exe"),
        "__CALC__":     lambda: control.open_app("calc") if control else subprocess.Popen("calc.exe", shell=True),
        "__EXPLORER__": lambda: control.open_app("explorer") if control else subprocess.Popen("explorer.exe"),

        # YOPISH — taskkill orqali
        "__CLOSE_BROWSER__": lambda: control.close_app("browser") if control else _kill_image(
            "msedge.exe", "chrome.exe", "firefox.exe", "opera.exe", "browser.exe", "brave.exe", "yandex.exe"
        ),
        "__CLOSE_NOTEPAD__": lambda: control.close_app("notepad") if control else _kill_image("notepad.exe"),
        "__CLOSE_CALC__":    lambda: control.close_app("calc") if control else _kill_image("CalculatorApp.exe", "Calculator.exe"),
        "__MINIMIZE_ALL__":  lambda: control.minimize_all_windows() if control else _minimize_all(),

        # OVOZ
        "__VOL_DOWN__": lambda: _vol_keybd("down"),
        "__VOL_UP__":   lambda: _vol_keybd("up"),

        # MEDIA / TIZIM
        "__STOP__":     lambda: None,
        "__SHUTDOWN__": lambda: subprocess.Popen(["shutdown", "/s", "/t", "30"], shell=True),
        "__RESTART__":  lambda: subprocess.Popen(["shutdown", "/r", "/t", "30"], shell=True),
    }
    labels = {
        "__BROWSER__":  "Открываю браузер.",
        "__YOUTUBE__":  "Открываю Ютуб.",
        "__GOOGLE__":   "Открываю Гугл.",
        "__NOTEPAD__":  "Открываю блокнот.",
        "__CALC__":     "Открываю калькулятор.",
        "__EXPLORER__": "Открываю проводник.",

        "__CLOSE_BROWSER__": "Закрываю браузер.",
        "__CLOSE_NOTEPAD__": "Закрываю блокнот.",
        "__CLOSE_CALC__":    "Закрываю калькулятор.",
        "__MINIMIZE_ALL__":  "Сворачиваю окна.",

        "__VOL_DOWN__": "Уменьшаю громкость.",
        "__VOL_UP__":   "Увеличиваю громкость.",

        "__STOP__":     "Остановлено.",
        "__SHUTDOWN__": "Выключаю компьютер через 30 секунд.",
        "__RESTART__":  "Перезагружаю через 30 секунд.",
    }
    try:
        if cmd in actions:
            actions[cmd]()
    except Exception as e:
        print(f"[L1] Buyruq xatosi: {e}", flush=True)
    return labels.get(cmd, "Выполнено.")


# ─────────────────────────────────────────
# QATLAM 2 — Ma'lumot (50-200ms)
# ─────────────────────────────────────────

def _layer2_info(text: str):
    """Qatlam 2: Lokal ma'lumot — soat, sana, tizim, demo savollari"""
    t = text.strip().lower()

    # Soat
    if re.search(r"врем|soat|time\b|час\b|сколько.*час|который час", t):
        now = datetime.datetime.now()
        return f"Сейчас {now.hour:02d}:{now.minute:02d}."

    # Sana
    if re.search(r"дата|какой.*день|число|bugun|сегодня|date\b|today|день недели", t):
        now = datetime.datetime.now()
        days = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
        months = ["января","февраля","марта","апреля","мая","июня",
                  "июля","августа","сентября","октября","ноября","декабря"]
        return f"Сегодня {days[now.weekday()]}, {now.day} {months[now.month-1]} {now.year} года."

    # Kompyuter nomi
    if re.search(r"имя.*компьютера|hostname|computer name", t):
        import socket
        return f"Имя компьютера: {socket.gethostname()}."

    # Tizim holati
    if re.search(r"\bcpu\b|процессор|память|ram\b|нагрузка|загрузка системы", t):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.2)
            ram = psutil.virtual_memory()
            return (f"Процессор загружен на {cpu:.0f}%. "
                    f"Оперативная память: {ram.used//1024//1024} МБ "
                    f"из {ram.total//1024//1024} МБ.")
        except Exception:
            return "Данные системы недоступны."

    # Ishlash vaqti
    if re.search(r"uptime|сколько.*работа|давно.*запущ|как долго", t):
        try:
            import psutil
            delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
            h = delta.seconds // 3600
            m = (delta.seconds % 3600) // 60
            return f"Компьютер работает {delta.days} дней, {h} часов {m} минут."
        except Exception:
            return "Данные о времени работы недоступны."

    # Offline rejimda internet yangiliklari yo'q — LLMga yubormaymiz (tezkor javob)
    if re.search(r"новост|какие новости|что нового в мире|свежие новости", t):
        return "В офлайн режиме онлайн-новости недоступны. Могу дать сводку из локальных данных или открыть сайт новостей."

    return None


# ─────────────────────────────────────────
# QATLAM 3 — Ollama LLM (2300ms)
# ─────────────────────────────────────────

# Knowledge base + user profile yuklanadi
def _load_system_prompt() -> str:
    try:
        from neurokey_knowledge import build_system_prompt
        return build_system_prompt()
    except Exception:
        return (
            "Ты Нейро Кей — офлайн AI ассистент владельца устройства. "
            "Отвечай ТОЛЬКО на русском. КОРОТКО: 1-2 предложения. "
            "Без списков. От первого лица. "
            "Сегодня 26 апреля 2026 года."
        )

_SYSTEM_PROMPT = _load_system_prompt()

def _layer3_llm(text: str, on_token=None) -> str:
    """Qatlam 3: Ollama LLM streaming — bilim bazasi bilan"""
    try:
        import requests
        payload = {
            "model": os.getenv("OLLAMA_OFFLINE_MODEL", "gemma3:4b"),
            "prompt": f"[INST] {_SYSTEM_PROMPT}\n\nПользователь: {text}\nНейро Кей:[/INST]",
            "stream": True,
            "options": {
                "num_predict": 80,
                "temperature": 0.3,
                "num_ctx": 2048,       # kengaytirildi: knowledge base sig'adi
                "repeat_penalty": 1.1, # takrorlashni kamaytiradi
            }
        }
        r = requests.post("http://localhost:11434/api/generate",
                          json=payload, stream=True, timeout=25)
        if r.status_code >= 400:
            try:
                _err = (r.json() or {}).get("error", "") or ""
            except Exception:
                _err = ""
            if _err:
                return f"Ошибка локальной модели: {_err}"
            return f"Ошибка локальной модели (HTTP {r.status_code})."
        result = []
        for line in r.iter_lines():
            if line:
                d = json.loads(line)
                if d.get("error"):
                    return f"Ошибка локальной модели: {d.get('error')}"
                token = d.get("response", "")
                if token:
                    result.append(token)
                    if on_token:
                        on_token(token)
                if d.get("done"):
                    break
        out = "".join(result).strip()
        if not out:
            return "Локальная модель не дала ответ. Проверьте, запущен ли Ollama и установлена ли модель."
        return out
    except Exception as e:
        return f"Ошибка LLM: {e}"


# ─────────────────────────────────────────
# ASOSIY FUNKSIYA
# ─────────────────────────────────────────

def process_offline(text: str, on_response=None) -> str:
    """
    Matnni qayta ishlash — 3 qatlam.
    on_response(text, is_final) — streaming callback
    """
    t0 = time.monotonic()
    text = _normalize_text(text)

    # Qatlam 1 — buyruq?
    resp = _layer1_command(text)
    if resp:
        if resp.startswith("__"):
            resp = _execute_command(resp)
        ms = (time.monotonic() - t0) * 1000
        print(f"[L1] {ms:.0f}ms", flush=True)
        if on_response:
            on_response(resp, True)
        return resp

    # Qatlam 2 — ma'lumot?
    resp = _layer2_info(text)
    if resp:
        ms = (time.monotonic() - t0) * 1000
        print(f"[L2] {ms:.0f}ms", flush=True)
        if on_response:
            on_response(resp, True)
        return resp

    # Qatlam 2.5 — lokal "miya" (knowledge pack, serverga chiqmaydi)
    resp = answer_from_brain(text)
    if resp:
        ms = (time.monotonic() - t0) * 1000
        print(f"[L2B] {ms:.0f}ms", flush=True)
        if on_response:
            on_response(resp, True)
        return resp

    # Qatlam 3 — LLM
    print(f"[L3] LLM...", flush=True)
    buf = []

    def _on_token(tok):
        buf.append(tok)
        joined = "".join(buf)
        # Birinchi gap tugaganida — darhol chalish
        if on_response and re.search(r"[.!?]\s", joined):
            sentences = re.split(r"(?<=[.!?])\s+", joined.strip())
            if len(sentences) > 1:
                first = sentences[0]
                on_response(first, False)
                buf.clear()
                buf.append(" ".join(sentences[1:]))

    result = _layer3_llm(
        "Отвечай строго по вопросу пользователя. "
        "Если вопрос неясен, задай один уточняющий вопрос. "
        "Не используй приветствие, если тебя не приветствовали. "
        + text,
        on_token=_on_token,
    )
    ms = (time.monotonic() - t0) * 1000
    print(f"[L3] {ms:.0f}ms", flush=True)

    # Qolgan qism
    leftover = "".join(buf).strip() or result
    if on_response and leftover:
        on_response(leftover, True)
    return result


# ─────────────────────────────────────────
# TEST
# ─────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        "Привет!",
        "Сколько сейчас время?",
        "Какой сегодня день?",
        "Открой браузер",
        "Расскажи про искусственный интеллект",
    ]

    print("=== OFFLINE FAST ENGINE TEST ===\n")
    for q in tests:
        print(f"Savol: {q}")
        t0 = time.monotonic()
        resp = process_offline(q)
        ms = (time.monotonic() - t0) * 1000
        print(f"Javob: {resp[:80]}")
        print(f"Vaqt: {ms:.0f}ms\n")
