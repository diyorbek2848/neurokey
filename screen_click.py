# -*- coding: utf-8 -*-
"""NeuroKey Screen Click — Ovoz bilan ekrandagi elementlarni topish va bosish.

Foydalanuvchi "u tugmani bos", "qidirish maydoniga klik qil", "Saqlash ni bos"
deydi — sistem:
  1. Ekrandan screenshot oladi
  2. GPT-4o Vision ga yuboradi: "Bu elementni top va koordinatalarini ber"
  3. Piksel koordinatalarini oladi
  4. pyautogui orqali klik qiladi

Qo'lda koordinata kerak emas — to'liq ovozli boshqaruv.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _cfg(name: str, default=None):
    try:
        import config as _c
        return getattr(_c, name, default)
    except Exception:
        return default


def _openai_client():
    """Lazy OpenAI client — screen_vision.py dagi kabi."""
    from openai import OpenAI
    api_key = (_cfg("OPENAI_API_KEY") or "").strip()
    base_url = (_cfg("OPENAI_BASE_URL") or "").strip() or None
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY bo'sh — .env da qo'ying.")
    return OpenAI(api_key=api_key, **({"base_url": base_url} if base_url else {}))


# ---------------------------------------------------------------------------
# Core: ekrandan element topish
# ---------------------------------------------------------------------------

def find_element_coords(description: str,
                        timeout_sec: float = 8.0) -> Optional[Tuple[int, int]]:
    """Ekrandan 'description' ga mos elementni topadi va markazining (x, y) ni qaytaradi.

    Args:
        description:  "qidirish tugmasi", "Saqlash knopkasi", "yopish X", "URL satri" va h.k.
        timeout_sec:  GPT-4o Vision so'rovi uchun maksimal kutish vaqti

    Returns:
        (x, y) piksel koordinatalari yoki None (topilmasa)
    """
    # 1. Screenshot
    img = None
    try:
        from screen_vision import grab_screen
        img = grab_screen()
    except Exception:
        pass
    if img is None:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
        except Exception:
            pass
    if img is None:
        return None

    w, h = img.size

    # 2. JPEG ga aylantiramiz (kichik hajm, tez yuklash)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # 3. GPT-4o Vision prompt — faqat JSON qaytarsin
    prompt = (
        f"Screenshot o'lchami: {w}x{h} piksel.\n"
        f"Quyidagi UI elementni top: \"{description}\"\n"
        f"Faqat JSON qaytargin (boshqa matn yo'q):\n"
        f'  agar topilsa → {{"x": <center_x>, "y": <center_y>}}\n'
        f'  agar topilmasa → {{"x": null, "y": null}}\n'
        f"x va y — elementning markaziy piksel koordinatalari (butun son)."
    )

    try:
        client = _openai_client()
        vision_model = _cfg("OPENAI_VISION_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        r = client.chat.completions.create(
            model=vision_model,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": "high"
                }},
                {"type": "text", "text": prompt},
            ]}],
            max_tokens=80,
            timeout=timeout_sec,
        )
        raw = (r.choices[0].message.content or "").strip()
    except Exception as e:
        return None

    # 4. JSON dan koordinatalarni ajratamiz
    # Qo'shimcha matn bo'lsa ham regex bilan olamiz
    m = re.search(r'"x"\s*:\s*(\d+)[^}]*"y"\s*:\s*(\d+)', raw)
    if not m:
        m = re.search(r'"y"\s*:\s*(\d+)[^}]*"x"\s*:\s*(\d+)', raw)
        if m:
            return int(m.group(2)), int(m.group(1))
    if m:
        x_val, y_val = int(m.group(1)), int(m.group(2))
        # Ekran chegarasi ichida ekanligini tekshiramiz
        if 0 <= x_val <= w and 0 <= y_val <= h:
            return x_val, y_val

    return None


def find_and_click(description: str,
                   button: str = "left",
                   double: bool = False) -> Tuple[bool, str]:
    """Element topib, ustiga klik qiladi.

    Args:
        description:  Elementning tavsifi (ovoz matnidan ajratilgan)
        button:       'left' | 'right' — klik turi
        double:       True — ikki marta klik

    Returns:
        (ok: bool, message: str)
    """
    coords = find_element_coords(description)
    if coords is None:
        return False, f"Экран на элемент «{description}» не нашёл."

    x, y = coords

    try:
        from input_sim import mouse_click, mouse_double_click
        if double:
            ok = mouse_double_click(x, y)
        else:
            ok = mouse_click(x, y, button=button)
    except ImportError:
        # Fallback: pyautogui to'g'ridan
        try:
            import pyautogui
            if double:
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.click(x, y, button=button)
            ok = True
        except Exception as e:
            return False, f"pyautogui xato: {e}"

    if ok:
        return True, f"Кликнул на «{description}» (x={x}, y={y})."
    return False, f"Кlik амали бажарилмади (x={x}, y={y})."


def find_and_right_click(description: str) -> Tuple[bool, str]:
    """O'ng tugma klik."""
    return find_and_click(description, button="right")


def find_and_double_click(description: str) -> Tuple[bool, str]:
    """Ikki marta klik."""
    return find_and_click(description, double=True)


def find_element_and_type(description: str, text_to_type: str) -> Tuple[bool, str]:
    """Element topib, unga fokus qo'yib, matn kiritadi.
    Misol: "qidirish maydoni" → klik → "python tutorial" yozadi.
    """
    ok, msg = find_and_click(description)
    if not ok:
        return False, msg
    time.sleep(0.3)  # Fokus o'rnatilguncha
    try:
        from input_sim import key_type
        typed = key_type(text_to_type)
        if typed:
            return True, f"«{description}» ga klik qilib «{text_to_type}» yozdim."
        return False, "Matn yozishda xato."
    except ImportError:
        try:
            import pyautogui
            pyautogui.write(text_to_type, interval=0.04)
            return True, f"«{description}» ga klik qilib «{text_to_type}» yozdim."
        except Exception as e:
            return False, str(e)


# ---------------------------------------------------------------------------
# Ovoz buyrug'idan element tavsifini ajratish
# ---------------------------------------------------------------------------

def extract_click_target(text: str) -> str:
    """Ovoz matnidan klik nishonini ajratadi.

    Misollar:
      "нажми на кнопку поиска"  → "кнопка поиска"
      "кликни по сохранить"     → "сохранить"
      "qidirish tugmasini bos"  → "qidirish tugmasi"
      "close button ni bos"     → "close button"
      "нажми закрыть"           → "закрыть"
      "click on the red button" → "red button"
    """
    t = (text or "").strip()
    low = t.lower()

    # Rus tilida prefixlarni olib tashlaymiz
    for prefix in (
        "нажми на кнопку ", "нажми на ", "кликни по кнопке ", "кликни по ",
        "нажми кнопку ", "нажми ", "кликни на ", "кликни ",
        "нажать на ", "щёлкни по ", "щёлкни на ", "щёлкни ",
        "открой ", "выбери ", "нажми кнопочку ",
    ):
        if low.startswith(prefix):
            return t[len(prefix):].strip().rstrip(".,")

    # O'zbek/ingliz prefixlari
    for prefix in (
        "tugmasini bos", " ni bos",
        "click on the ", "click the ", "click on ", "click ",
        "press ", "tap on ", "tap ",
    ):
        if prefix in low:
            idx = low.index(prefix)
            if idx == 0:
                return t[len(prefix):].strip().rstrip(".,")
            # "X ni bos" → X
            return t[:idx].strip().rstrip(".,")

    # "bos" so'zi oxirida bo'lsa
    if low.endswith(" bos") or low.endswith("ni bos") or low.endswith("ga bos"):
        return re.sub(r"\s*(ni|ga|da)?\s*bos$", "", t, flags=re.IGNORECASE).strip()

    # Qolgan hollarda butun matnni qaytaramiz
    return t
