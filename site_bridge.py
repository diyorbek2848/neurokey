# -*- coding: utf-8 -*-
"""NeuroKey — O'z saytini ovoz bilan boshqarish moduli.

Sayt: neurokey_sayt papkasi  (Next.js + Tailwind + Netlify)
GitHub: github.com/diyorbek2848/neurokey-sayt
Deploy: Netlify — push qilsak avtomatik yangilanadi

Nima qila oladi:
  - Matnlarni o'zgartirish (sarlavha, tavsif, tugma yozuvi va h.k.)
  - Ranglarni o'zgartirish (accent, background, border...)
  - Sahifa elementlarini yangilash
  - Git commit + push → Netlify avtomatik deploy

Buyruq misollari:
  "Sayt sarlavhasini o'zgartir — NeuroKey 2026"
  "Tugma rangini yashil qil"
  "Hero tavsifini yangilayr — endi yangi funksiyalar bor"
  "Saytni deploy qil"
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Dict, Optional, Tuple

_SITE_DIR = r"C:\Users\tymit\Documents\neurokey_sayt"
_MESSAGES_RU = os.path.join(_SITE_DIR, "messages", "ru.json")
_MESSAGES_EN = os.path.join(_SITE_DIR, "messages", "en.json")
_TAILWIND    = os.path.join(_SITE_DIR, "tailwind.config.ts")

# ── Rang nomlari (o'zbek/rus → CSS hex) ─────────────────────────────────────
_COLOR_MAP = {
    # O'zbek
    "yashil": "#22c55e", "ko'k": "#3b82f6", "moviy": "#22d3ee",
    "qizil": "#ef4444", "sariq": "#eab308", "to'q sariq": "#f97316",
    "binafsha": "#8b5cf6", "pushti": "#ec4899", "oq": "#ffffff",
    "qora": "#000000", "kulrang": "#6b7280", "to'q ko'k": "#1d4ed8",
    "och yashil": "#86efac", "to'q yashil": "#15803d",
    # Rus
    "зелёный": "#22c55e", "зеленый": "#22c55e",
    "синий": "#3b82f6", "голубой": "#22d3ee", "cyan": "#22d3ee",
    "красный": "#ef4444", "жёлтый": "#eab308", "желтый": "#eab308",
    "оранжевый": "#f97316", "фиолетовый": "#8b5cf6",
    "розовый": "#ec4899", "белый": "#ffffff", "чёрный": "#000000",
    "серый": "#6b7280", "тёмно-синий": "#1d4ed8",
    # English
    "green": "#22c55e", "blue": "#3b82f6", "cyan": "#22d3ee",
    "red": "#ef4444", "yellow": "#eab308", "orange": "#f97316",
    "purple": "#8b5cf6", "pink": "#ec4899", "white": "#ffffff",
    "black": "#000000", "gray": "#6b7280", "grey": "#6b7280",
}

# ── Matn kalitlari (so'z → JSON yo'l) ────────────────────────────────────────
_TEXT_KEYS = {
    # Sarlavha
    "sarlavha": ("hero", "title"),
    "заголовок": ("hero", "title"),
    "title": ("hero", "title"),
    # Tavsif
    "tavsif": ("hero", "description"),
    "описание": ("hero", "description"),
    "description": ("hero", "description"),
    # Subtitle
    "subtitle": ("hero", "subtitle"),
    "подзаголовок": ("hero", "subtitle"),
    # CTA tugma
    "tugma": ("hero", "cta"),
    "кнопка": ("hero", "cta"),
    "button": ("hero", "cta"),
    # Nav
    "boshlash": ("nav", "start"),
    "start nav": ("nav", "start"),
    "chat nav": ("nav", "chat"),
    # Footer
    "tagline": ("footer", "tagline"),
}

# ── Rang kalitlari ────────────────────────────────────────────────────────────
_COLOR_KEYS = {
    "accent": "accent", "акцент": "accent",
    "fon": "dark", "фон": "dark", "background": "dark",
    "karta": "card", "карточка": "card", "card": "card",
    "chegara": "border", "граница": "border", "border": "border",
    "yashil rang": "emerald", "зелёный акцент": "emerald",
    "glow": "glow",
}


def is_available() -> bool:
    return os.path.isdir(_SITE_DIR) and os.path.isdir(os.path.join(_SITE_DIR, ".git"))


# ── So'rovni aniqlash ────────────────────────────────────────────────────────

_TRIGGERS = [
    "sayt", "сайт", "site", "website",
    "sahifa", "страница",
    "deploy", "деплой", "опубликуй",
]

_CHANGE_WORDS = [
    "o'zgartir", "ozgartir", "yangilayr", "yangilansin", "qil", "yoz",
    "измени", "обнови", "поменяй", "напиши", "сделай",
    "change", "update", "set", "make",
]

_COLOR_WORDS = [
    "rang", "цвет", "color", "colour", "rangi", "цвета",
]

_DEPLOY_WORDS = [
    "deploy", "деплой", "опубликуй", "чиқар", "chiqar",
    "nashr", "publish", "push", "юклай", "yuklay",
]


def is_site_request(text: str) -> bool:
    low = text.lower()
    has_trigger = any(t in low for t in _TRIGGERS)
    has_action  = any(w in low for w in _CHANGE_WORDS + _DEPLOY_WORDS)
    return has_trigger and has_action


# ── Matn o'zgartirish ────────────────────────────────────────────────────────

def _load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data: Dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def change_text(key_hint: str, new_value: str, lang: str = "both") -> Tuple[bool, str]:
    """Matn qiymatini o'zgartirish.

    key_hint: 'sarlavha', 'tavsif', 'tugma' va h.k.
    lang: 'ru', 'en', 'both'
    """
    # JSON yo'lini aniqlash
    path_tuple = None
    low = key_hint.lower()
    for hint, pt in _TEXT_KEYS.items():
        if hint in low:
            path_tuple = pt
            break

    if not path_tuple:
        return False, f"'{key_hint}' uchun JSON kalit topilmadi"

    changed = []
    files = []
    if lang in ("ru", "both"):
        files.append((_MESSAGES_RU, "ru"))
    if lang in ("en", "both"):
        files.append((_MESSAGES_EN, "en"))

    for fpath, flang in files:
        if not os.path.exists(fpath):
            continue
        try:
            data = _load_json(fpath)
            section = data
            for key in path_tuple[:-1]:
                section = section.setdefault(key, {})
            section[path_tuple[-1]] = new_value
            _save_json(fpath, data)
            changed.append(flang)
        except Exception as e:
            return False, f"Xato ({flang}): {e}"

    if changed:
        return True, f"{' + '.join(path_tuple)} → '{new_value[:40]}' ({', '.join(changed)})"
    return False, "Fayl topilmadi"


# ── Rang o'zgartirish ─────────────────────────────────────────────────────────

def change_color(color_target: str, new_color: str) -> Tuple[bool, str]:
    """tailwind.config.ts da neuro.* rangini o'zgartirish.

    color_target: 'accent', 'dark', 'card', 'emerald' yoki o'zbek/rus nomi
    new_color: '#hex' yoki rang nomi ('yashil', 'синий', 'red' ...)
    """
    if not os.path.exists(_TAILWIND):
        return False, "tailwind.config.ts topilmadi"

    # Kalit aniqlash
    target_key = None
    low_target = color_target.lower()
    for hint, key in _COLOR_KEYS.items():
        if hint in low_target:
            target_key = key
            break
    if not target_key:
        target_key = "accent"  # default

    # Hex rang aniqlash
    hex_color = None
    low_color = new_color.lower().strip()
    if re.match(r"^#[0-9a-fA-F]{3,8}$", low_color):
        hex_color = low_color
    else:
        for name, hexval in _COLOR_MAP.items():
            if name in low_color:
                hex_color = hexval
                break
    if not hex_color:
        return False, f"'{new_color}' rang tushunilmadi. #hex yoki nom (yashil, ko'k...) yozing."

    try:
        content = open(_TAILWIND, "r", encoding="utf-8").read()
        # neuro.accent: '#22d3ee' → yangi rang
        pattern = rf"({target_key}:\s*['\"])([^'\"]+)(['\"])"
        new_content = re.sub(pattern, rf"\g<1>{hex_color}\g<3>", content, count=1)
        if new_content == content:
            return False, f"'{target_key}' kalit tailwind.config.ts da topilmadi"
        open(_TAILWIND, "w", encoding="utf-8").write(new_content)
        return True, f"neuro.{target_key}: '{hex_color}' ga o'zgartirildi"
    except Exception as e:
        return False, f"tailwind xato: {e}"


# ── Git commit + push (Netlify auto-deploy) ───────────────────────────────────

def git_commit_and_push(message: str = "NeuroKey ovoz buyrug'i bilan yangilandi") -> Tuple[bool, str]:
    """Barcha o'zgarishlarni git ga commit qilib Netlify ga push qiladi."""
    try:
        # Status tekshirish
        r = subprocess.run(
            ["git", "-C", _SITE_DIR, "status", "--short"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        if not r.stdout.strip():
            return True, "Hech qanday o'zgarish yo'q — deploy kerak emas"

        # Add all
        subprocess.run(
            ["git", "-C", _SITE_DIR, "add", "-A"],
            capture_output=True, timeout=15
        )
        # Commit
        r2 = subprocess.run(
            ["git", "-C", _SITE_DIR, "commit", "-m", message],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        if r2.returncode != 0 and "nothing to commit" not in r2.stdout:
            return False, f"Commit xato: {r2.stderr[:200]}"

        # Push
        r3 = subprocess.run(
            ["git", "-C", _SITE_DIR, "push"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
        )
        if r3.returncode != 0:
            return False, f"Push xato: {r3.stderr[:200]}"

        return True, "GitHub ga push qilindi. Netlify ~1-2 daqiqada yangilanadi."
    except subprocess.TimeoutExpired:
        return False, "Git timeout — internet yoki GitHub bilan muammo"
    except Exception as e:
        return False, f"Git xato: {e}"


# ── Asosiy handler ────────────────────────────────────────────────────────────

def _extract_new_value(text: str) -> str:
    """'— yangi matn' yoki ': yangi matn' ko'rinishidan yangi qiymatni ajratish."""
    # Tire yoki ikki nuqtadan keyin kela'digan matn
    m = re.search(r"[—\-–:]\s*(.{3,})", text)
    if m:
        return m.group(1).strip().strip('"\'')
    # Oxirgi vergul/nuqtadan keyingi qism
    parts = re.split(r"[,;]", text)
    if len(parts) > 1:
        return parts[-1].strip().strip('"\'')
    return ""


def handle_site_request(text: str, tts_say=None) -> Optional[str]:
    """main.py dan chaqirish uchun. Qaytaradi: javob matni yoki None."""
    if not is_site_request(text):
        return None
    if not is_available():
        return "neurokey_sayt papkasi topilmadi."

    def _say(msg):
        if tts_say:
            try:
                tts_say(msg)
            except Exception:
                pass

    low = text.lower()
    changes_made = []

    # ── Deploy buyrug'i ──────────────────────────────────────────────
    if any(w in low for w in _DEPLOY_WORDS):
        _say("Sayt GitHub ga yuklanmoqda, Netlify deploy boshlaydi...")
        ok, msg = git_commit_and_push("NeuroKey: deploy buyrug'i")
        _say(msg)
        return msg

    # ── Rang o'zgartirish ────────────────────────────────────────────
    if any(w in low for w in _COLOR_WORDS):
        # target: "accent rangini ko'k qil" → target=accent, color=ko'k
        target = "accent"
        for hint, key in _COLOR_KEYS.items():
            if hint in low:
                target = key
                break
        # Rang topish
        color_found = ""
        for cname in _COLOR_MAP:
            if cname in low:
                color_found = cname
                break
        if not color_found:
            m = re.search(r"#[0-9a-fA-F]{3,8}", text)
            if m:
                color_found = m.group(0)

        if color_found:
            ok, msg = change_color(target, color_found)
            if ok:
                changes_made.append(msg)
                _say(f"Rang o'zgartirildi: {msg}")
            else:
                _say(f"Rang xato: {msg}")
                return msg
        else:
            _say("Qaysi rang? 'Ko'k', 'yashil', '#3b82f6' kabi ayting.")
            return "Rang aniqlanmadi."

    # ── Matn o'zgartirish ────────────────────────────────────────────
    for hint in _TEXT_KEYS:
        if hint in low:
            new_val = _extract_new_value(text)
            if not new_val:
                _say(f"Yangi matnni ayting: masalan 'sarlavhani o'zgartir — NeuroKey 2026'")
                return "Yangi matn kiritilmadi."
            ok, msg = change_text(hint, new_val)
            if ok:
                changes_made.append(msg)
                _say(f"Matn o'zgartirildi: {msg}")
            else:
                _say(f"Matn xato: {msg}")
                return msg
            break

    if not changes_made:
        _say("Nima o'zgartirish kerak? Masalan: sayt sarlavhasini, tugma rangini...")
        return None

    # ── Avtomatik push ───────────────────────────────────────────────
    _say("O'zgarishlar GitHub ga yuklanmoqda...")
    commit_msg = "NeuroKey: " + "; ".join(changes_made)[:100]
    ok, push_msg = git_commit_and_push(commit_msg)
    _say(push_msg)

    result = "\n".join(changes_made) + "\n" + push_msg
    return result
