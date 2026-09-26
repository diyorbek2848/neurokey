# -*- coding: utf-8 -*-
"""Instant local voice control in Russian (no LLM roundtrip)."""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple


def _rest_after_prefix(text: str, prefixes) -> str:
    t = (text or "").strip()
    low = t.lower()
    for p in prefixes:
        if low.startswith(p):
            return t[len(p):].strip(" :,-")
    return ""


def _guess_file_path(raw: str) -> str:
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        return ""
    if os.path.isabs(s):
        return s
    if s.startswith("~"):
        return os.path.expanduser(s)
    if "\\" in s or "/" in s:
        return os.path.abspath(os.path.expanduser(s))
    return s


def try_handle(text: str, control) -> Tuple[bool, str]:
    t = (text or "").strip()
    low = t.lower()
    if not t:
        return False, ""

    # OPEN APP
    if any(x in low for x in ("открой телеграм", "открыть телеграм", "запусти телеграм")):
        return control.open_app("telegram")
    if any(x in low for x in ("открой браузер", "открыть браузер", "запусти браузер")):
        return control.open_app("browser")
    if any(x in low for x in ("открой youtube", "открой ютуб", "зайди на ютуб", "зайди в youtube")):
        return control.open_url("https://www.youtube.com")

    # CLOSE APP
    if any(x in low for x in ("закрой телеграм", "закрыть телеграм")):
        return control.close_app("telegram")
    if any(x in low for x in ("закрой браузер", "закрыть браузер")):
        return control.close_app("browser")

    # TYPE TEXT INTO ACTIVE FIELD
    msg = _rest_after_prefix(low, ("напиши ", "введи ", "печатай "))
    if msg:
        # Recover original casing by cutting from original string.
        original = t[len(t) - len(msg):]
        return control.send_keys(original)

    # SEND / ENTER
    if low in ("отправь", "отправить", "энтер", "enter") or any(
        x in low for x in ("отправь сообщение", "нажми enter", "жми enter")
    ):
        return control.send_hotkey("enter")

    # FILE OPEN
    fp = _rest_after_prefix(low, ("открой файл ", "открыть файл "))
    if fp:
        guessed = _guess_file_path(t[t.lower().index(fp):])
        if os.path.isfile(guessed):
            return control.open_file(guessed)
        ok, found = control.search_files(os.path.expanduser("~"), guessed, limit=1)
        if ok and "\n" in (found or ""):
            first = (found.splitlines()[1] if len(found.splitlines()) > 1 else "").strip()
            if first and os.path.exists(first):
                return control.open_file(first)
        return False, f"Файл не найден: {guessed}"

    # FILE DELETE
    dp = _rest_after_prefix(low, ("удали файл ", "удалить файл "))
    if dp:
        guessed = _guess_file_path(t[t.lower().index(dp):])
        return control.delete_file(guessed)

    # FOLDER OPEN
    folder = _rest_after_prefix(low, ("открой папку ", "открыть папку "))
    if folder:
        raw = t[t.lower().index(folder):]
        found = control.find_folder(raw)
        if found:
            return control.open_folder(found)
        return False, f"Папка не найдена: {raw}"

    # RUN COMMAND
    cmd = _rest_after_prefix(low, ("выполни ", "команда ", "запусти команду ", "cmd "))
    if cmd:
        original = t[len(t) - len(cmd):]
        return control.run_command(original, timeout_sec=20.0)

    return False, ""

