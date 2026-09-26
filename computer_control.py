"""
computer_control.py — NeuroKey Kompyuter Nazorat Markazi

LLM dan kelgan [BUYRUQ: params] formatini parse qilib bajaradi.
NeuroKey miyya — kompyuter tana. Miya nima buyursa tana bajaradi.

Qo'llab-quvvatlanadigan buyruqlar:
  [FAYL: o'qi PATH]
  [FAYL: yoz PATH | MAZMUN]
  [FAYL: o'chir PATH]
  [FAYL: ro'yxat PATH]
  [FAYL: ko'chir SOURCE | DEST]
  [FAYL: ko'chir-nom SOURCE | DEST]
  [FAYL: qidir PATH | NAQSH]
  [DASTUR: boshlash NAME_OR_PATH]
  [DASTUR: to'xtat NAME.EXE]
  [DASTUR: ro'yxat]
  [OYNA: fokus SARLAVHA]
  [OYNA: yop SARLAVHA]
  [OYNA: kichrayt SARLAVHA]
  [OYNA: kattalayt SARLAVHA]
  [OYNA: ro'yxat]
  [EKRAN: bos "ELEMENT"]
  [EKRAN: yoz "MAYDON" | MATN]
  [EKRAN: o'ng-bos "ELEMENT"]
  [EKRAN: screenshot]
  [TUGMA: COMBO]
  [INTERNET: izla SO'ROV]
  [INTERNET: yukla URL | MANZIL]
  [CLIPBOARD: ol]
  [CLIPBOARD: qo'y | MATN]
  [SICHQON: ko'chir X Y]
  [SICHQON: bos X Y]
"""
from __future__ import annotations
import re, os, urllib.request, logging
from typing import Optional

log = logging.getLogger(__name__)

# Barcha buyruq nomlarini qo'llab-quvvatlash (o'zbek + rus)
_ACTION_NAMES = (
    "FAYL|FILE|ФАЙЛ"
    "|DASTUR|APP|PROCESS|ПРОЦЕСС|ПРИЛОЖЕНИЕ"
    "|OYNA|WINDOW|ОКНО"
    "|EKRAN|SCREEN|ЭКРАН"
    "|TUGMA|KEY|КЛАВИША|HOTKEY"
    "|INTERNET|WEB|ИНТЕРНЕТ"
    "|CLIPBOARD|BUFER|БУФЕР"
    "|SICHQON|MOUSE|МЫШЬ"
)

ACTION_RE = re.compile(
    r'\[(' + _ACTION_NAMES + r'):\s*([^\]]+)\]',
    re.IGNORECASE
)

# ─── Asosiy API ──────────────────────────────────────────────────────────────

def execute_actions(text: str) -> tuple[str, list[str]]:
    """
    LLM javobidan barcha buyruqlarni topib bajaradi.

    Returns:
        (clean_text, execution_results)
        clean_text  — buyruqlar olib tashlangan javob matni
        results     — har buyruq natijasi ["[FAYL] yozildi", ...]
    """
    results = []
    clean = text
    for m in ACTION_RE.finditer(text):
        raw_type = m.group(1).upper()
        params   = m.group(2).strip()
        action   = _normalize(raw_type)
        try:
            result = _dispatch(action, params)
        except Exception as e:
            result = f"XATO: {e}"
            log.warning(f"[CTRL] {action} xatosi: {e}")
        results.append(f"[{action}] {result}")
        clean = clean.replace(m.group(0), "")
        log.info(f"[CTRL] {action}: {params[:60]} → {result[:60]}")
    return clean.strip(), results


def has_actions(text: str) -> bool:
    """LLM javobida buyruq bormi?"""
    return bool(ACTION_RE.search(text))


# ─── Normallashtirish ────────────────────────────────────────────────────────

def _normalize(t: str) -> str:
    if t in ("FILE", "ФАЙЛ"):                return "FAYL"
    if t in ("APP", "PROCESS", "ПРОЦЕСС", "ПРИЛОЖЕНИЕ"): return "DASTUR"
    if t in ("WINDOW", "ОКНО"):              return "OYNA"
    if t in ("SCREEN", "ЭКРАН"):             return "EKRAN"
    if t in ("KEY", "КЛАВИША", "HOTKEY"):    return "TUGMA"
    if t in ("WEB", "ИНТЕРНЕТ"):             return "INTERNET"
    if t in ("BUFER", "БУФЕР"):              return "CLIPBOARD"
    if t in ("MOUSE", "МЫШЬ"):               return "SICHQON"
    return t


# ─── Dispatcher ──────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Unicode apostroflarni oddiyga o'zgartir, kichik harfga."""
    return s.replace("\u2019", "'").replace("\u2018", "'").lower().strip()


def _dispatch(action: str, params: str) -> str:
    if action == "FAYL":      return _file_action(params)
    if action == "DASTUR":    return _process_action(params)
    if action == "OYNA":      return _window_action(params)
    if action == "EKRAN":     return _screen_action(params)
    if action == "TUGMA":     return _hotkey_action(params)
    if action == "INTERNET":  return _internet_action(params)
    if action == "CLIPBOARD": return _clipboard_action(params)
    if action == "SICHQON":   return _mouse_action(params)
    return f"noma'lum amal: {action}"


# ─── Fayl amallari ───────────────────────────────────────────────────────────

def _file_action(params: str) -> str:
    parts = [p.strip() for p in params.split("|", 1)]
    tokens = parts[0].split(None, 1)
    op   = _norm(tokens[0]) if tokens else ""
    path = tokens[1].strip() if len(tokens) > 1 else ""
    extra = parts[1].strip() if len(parts) > 1 else ""

    try:
        from file_ops import read, write, delete, list_dir, copy, move
    except ImportError:
        return "file_ops moduli topilmadi"

    if op in ("o'qi", "read", "chita", "читай", "ochiq"):
        content = read(path)
        return (content[:500] + "…[kesildi]") if content and len(content) > 500 else (content or "bo'sh")

    if op in ("yoz", "write", "piши", "пиши"):
        write(path, extra)
        return f"yozildi ({len(extra)} belgi)"

    if op in ("o'chir", "ochir", "delete", "удали", "del"):
        delete(path)
        return "o'chirildi"

    if op in ("ro'yxat", "royxat", "list", "список", "ls"):
        try:
            items = list_dir(path)
        except Exception as e:
            return f"ro'yxat xatosi: {e}"
        if not items:
            return "bo'sh papka"
        return "\n".join(items[:30]) + (f"\n…yana {len(items)-30} ta" if len(items) > 30 else "")

    if op in ("ko'chir", "kochir", "copy", "копируй"):
        copy(path, extra)
        return f"ko'chirildi → {extra}"

    if op in ("ko'chir-nom", "kochir-nom", "move", "перемести"):
        move(path, extra)
        return f"ko'chirib-nomlandi → {extra}"

    if op in ("qidir", "search", "ищи", "find"):
        try:
            import glob as _glob
            pattern = extra or "*"
            found = _glob.glob(os.path.join(path, "**", pattern), recursive=True)
            if not found:
                found = _glob.glob(os.path.join(path, pattern))
        except Exception as e:
            return f"qidiruv xatosi: {e}"
        return "\n".join(found[:20]) + (f"\n…yana {len(found)-20}" if len(found) > 20 else "topilmadi")

    return f"noma'lum fayl amali: {op}"


# ─── Jarayon amallari ────────────────────────────────────────────────────────

def _process_action(params: str) -> str:
    tokens = params.split(None, 1)
    op   = _norm(tokens[0]) if tokens else ""
    name = tokens[1].strip() if len(tokens) > 1 else ""

    try:
        from process_ops import start, kill, find_by_name, list_all
    except ImportError:
        return "process_ops moduli topilmadi"

    if op in ("boshlash", "start", "открой", "запусти", "run"):
        pid = start(name)
        return f"ishga tushdi (PID={pid})" if pid else "ishga tushmadi"

    if op in ("to'xtat", "toxtat", "stop", "kill", "останови", "закрой"):
        procs = find_by_name(name)
        if not procs:
            return f"topilmadi: {name}"
        kill(procs[0]["pid"])
        return f"to'xtatildi: {name}"

    if op in ("ro'yxat", "royxat", "list", "список", "ls"):
        procs = list_all()
        top = procs[:15]
        return "\n".join(f"{p.get('name','?')} (PID={p.get('pid','?')})" for p in top)

    return f"noma'lum jarayon amali: {op}"


# ─── Oyna amallari ───────────────────────────────────────────────────────────

def _window_action(params: str) -> str:
    tokens = params.split(None, 1)
    op    = _norm(tokens[0]) if tokens else ""
    title = tokens[1].strip() if len(tokens) > 1 else ""

    try:
        from window_ops import window_focus, window_close, window_minimize, window_maximize, window_list
    except ImportError:
        return "window_ops moduli topilmadi"

    if op in ("fokus", "focus", "фокус", "выбери", "old"):
        window_focus(title)
        return f"fokus: {title}"

    if op in ("yop", "close", "закрой", "yopish"):
        window_close(title)
        return f"yopildi: {title}"

    if op in ("kichrayt", "minimize", "свернуть", "kichik"):
        window_minimize(title)
        return "kichraytirildi"

    if op in ("kattalayt", "maximize", "развернуть", "katta"):
        window_maximize(title)
        return "kattalashtirildi"

    if op in ("ro'yxat", "royxat", "list", "список", "ls", "ko'rsat", "korsat"):
        try:
            wins = window_list()
        except Exception as e:
            return f"oyna ro'yxat xatosi: {e}"
        titles = [w.get("title","") for w in wins if w.get("title","").strip()]
        if not titles:
            return "ochiq oyna topilmadi"
        return "\n".join(titles[:20])

    return f"noma'lum oyna amali: {op}"


# ─── Ekran amallari ──────────────────────────────────────────────────────────

def _screen_action(params: str) -> str:
    parts = [p.strip() for p in params.split("|", 1)]
    tokens = parts[0].split(None, 1)
    op     = tokens[0].lower() if tokens else ""
    target = tokens[1].strip().strip('"') if len(tokens) > 1 else ""
    extra  = parts[1].strip() if len(parts) > 1 else ""

    if op in ("screenshot", "скриншот", "rasm"):
        try:
            from screen_vision import grab_screen
            import time
            path = os.path.join(os.path.expanduser("~"), "Desktop",
                                f"neurokey_{int(time.time())}.png")
            img = grab_screen()
            if img:
                img.save(path)
                return f"screenshot: {path}"
            return "screenshot olinmadi"
        except Exception as e:
            return f"xato: {e}"

    try:
        from screen_click import find_and_click, find_element_and_type, find_and_right_click
    except ImportError:
        return "screen_click moduli topilmadi"

    if op in ("bos", "click", "нажми", "кликни"):
        find_and_click(target)
        return f"bosildi: {target}"

    if op in ("yoz", "type", "напиши", "введи"):
        find_element_and_type(target, extra)
        return f"yozildi: '{extra}' → {target}"

    if op in ("o'ng-bos", "rclick", "right", "правый"):
        find_and_right_click(target)
        return f"o'ng-bosildi: {target}"

    return f"noma'lum ekran amali: {op}"


# ─── Tugma kombinatsiyalari ──────────────────────────────────────────────────

def _hotkey_action(params: str) -> str:
    try:
        from input_sim import hotkey, key_press
    except ImportError:
        return "input_sim moduli topilmadi"

    if "+" in params:
        keys = [k.strip() for k in params.split("+")]
        hotkey(*keys)
    else:
        key_press(params.strip())
    return f"bosildi: {params}"


# ─── Internet amallari ───────────────────────────────────────────────────────

def _internet_action(params: str) -> str:
    parts = [p.strip() for p in params.split("|", 1)]
    tokens = parts[0].split(None, 1)
    op    = tokens[0].lower() if tokens else ""
    value = tokens[1].strip() if len(tokens) > 1 else parts[0]

    if op in ("izla", "search", "найди", "ищи"):
        try:
            from web_tools import web_context
            result = web_context(value)
            return result[:400] + "…" if len(result) > 400 else result
        except ImportError:
            return "web_tools moduli topilmadi"

    if op in ("yukla", "download", "скачай", "загрузи"):
        url = value
        dest_base = parts[1] if len(parts) > 1 else os.path.join(
            os.path.expanduser("~"), "Downloads",
            url.rstrip("/").split("/")[-1] or "neurokey_download.bin")
        try:
            os.makedirs(os.path.dirname(dest_base) or ".", exist_ok=True)
            # Progress-siz oddiy yuklab olish
            urllib.request.urlretrieve(url, dest_base)
            size = os.path.getsize(dest_base)
            return f"yuklandi: {dest_base} ({size//1024}KB)"
        except Exception as e:
            return f"yuklab olish xatosi: {e}"

    if op in ("ochil", "open", "открой"):
        import webbrowser
        webbrowser.open(value)
        return f"brauzerda ochildi: {value}"

    return f"noma'lum internet amali: {op}"


# ─── Clipboard amallari ──────────────────────────────────────────────────────

def _clipboard_action(params: str) -> str:
    parts = [p.strip() for p in params.split("|", 1)]
    op = _norm(parts[0])

    try:
        from clipboard_ops import clipboard_get, clipboard_set
    except ImportError:
        return "clipboard_ops moduli topilmadi"

    if op in ("ol", "get", "получи", "взять", "read"):
        content = clipboard_get()
        if not content:
            return "clipboard bo'sh"
        return content[:300] + "…" if len(content) > 300 else content

    if op in ("qo'y", "qoy", "set", "put", "положи", "скопируй", "write"):
        text = parts[1] if len(parts) > 1 else ""
        clipboard_set(text)
        return f"qo'yildi ({len(text)} belgi)"

    return f"noma'lum clipboard amali: {op}"


# ─── Sichqoncha amallari ─────────────────────────────────────────────────────

def _mouse_action(params: str) -> str:
    tokens = params.split()
    op = tokens[0].lower() if tokens else ""

    try:
        from input_sim import mouse_move, mouse_click
    except ImportError:
        return "input_sim moduli topilmadi"

    try:
        if op in ("ko'chir", "move", "двигай") and len(tokens) >= 3:
            x, y = int(tokens[1]), int(tokens[2])
            mouse_move(x, y)
            return f"ko'chirildi: ({x},{y})"

        if op in ("bos", "click", "нажми") and len(tokens) >= 3:
            x, y = int(tokens[1]), int(tokens[2])
            mouse_click(x, y)
            return f"bosildi: ({x},{y})"
    except ValueError:
        return "koordinatalar son bo'lishi kerak"

    return f"noma'lum sichqon amali: {op}"


# ─── CLI test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    test_cases = [
        '[FAYL: ro\'yxat C:\\Users]',
        '[DASTUR: ro\'yxat]',
        '[OYNA: ro\'yxat]',
        '[CLIPBOARD: ol]',
    ]
    if len(sys.argv) > 1:
        test_cases = [" ".join(sys.argv[1:])]

    for test in test_cases:
        print(f"\nTest: {test}")
        clean, results = execute_actions(test)
        for r in results:
            print(f"  → {r[:200]}")
