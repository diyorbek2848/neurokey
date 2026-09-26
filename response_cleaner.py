# -*- coding: utf-8 -*-
"""NeuroKey — LLM javoblarini tozalash. M5 + M6 yechimi.

Keraksiz frazalar olib tashlanadi.
Ikki marta boshlash muammosining oldini oladi.
"""

from __future__ import annotations

import re
from typing import Generator, Iterator


class ResponseCleaner:
    """
    LLM javoblaridan keraksiz narsalarni olib tashlaydi.
    Va ikki marta boshlash muammosini oldini oladi.
    """

    FILLER_STARTS = [
        r"^Albatta[!,.]?\s*",
        r"^Ha, albatta[!,.]?\s*",
        r"^Keling\s+ko'rib\s+chiqamiz[.,!]?\s*",
        r"^Keling[,.]?\s*",
        r"^Tushunarli[!,.]?\s*",
        r"^Zo'r savol[!,.]?\s*",
        r"^Qiziqarli[!,.]?\s*",
        r"^Xo'sh[,.]?\s*",
        r"^Demak[,.]?\s*",
        r"^Shunday qilib[,.]?\s*",
        r"^Aytishim kerakki[,.]?\s*",
        r"^Of course[!,.]?\s*",
        r"^Sure[!,.]?\s*",
        r"^Certainly[!,.]?\s*",
        r"^Great question[!,.]?\s*",
        r"^Конечно[!,.]?\s*",
        r"^Конечно же[!,.]?\s*",
        r"^Давайте[!,.]?\s*",
        r"^Итак[,.]?\s*",
        r"^Хорошо[,.]?\s*",
        r"^Понял[!,.]?\s*",
        r"^Понятно[!,.]?\s*",
        r"^Отлично[!,.]?\s*",
        r"^Разумеется[!,.]?\s*",
        r"^Без проблем[!,.]?\s*",
        r"^Сейчас[!,.]?\s*",
        r"^Сделаю[!,.]?\s*",
        r"^Выполняю[!,.]?\s*",
        r"^Принято[!,.]?\s*",
        r"^Ясно[!,.]?\s*",
        r"^Ок[,.]?\s*",
        r"^Подождите[!,.]?\s*",
        r"^Подожди[!,.]?\s*",
        r"^Смотрите[,.]?\s*",
        r"^Слушайте[,.]?\s*",
        r"^Да[,.]?\s+(?=\S)",
        r"^Нет проблем[!,.]?\s*",
        r"^С удовольствием[!,.]?\s*",
        r"^Рад помочь[!,.]?\s*",
        r"^Конечно помогу[!,.]?\s*",
        r"^Естественно[!,.]?\s*",
        r"^Безусловно[!,.]?\s*",
        r"^Минуту[!,.]?\s*",
        r"^Одну секунду[!,.]?\s*",
        r"^Ладно[,.]?\s*",
        r"^Хм[,.]?\s*",
        r"^Хорошо[,.]?\s*",
        r"^Хм-м[,.]?\s*",
        r"^Ну[,.]?\s+(?=\S)",
        r"^Что ж[,.]?\s*",
        r"^Так[,.]?\s+(?=\S)",
        r"^Давай[,.]?\s+(?=\S)",
        r"^Окей[!,.]?\s*",
        r"^OK[!,.]?\s*",
        r"^Hmm[,.]?\s*",
        r"^Well[,.]?\s*",
        r"^So[,.]?\s+(?=\S)",
        r"^Вообще[,.]?\s+(?=\S)",
        r"^Вообще-то[,.]?\s*",
        r"^По сути[,.]?\s*",
        r"^По сути дела[,.]?\s*",
        r"^В принципе[,.]?\s*",
        r"^Фактически[,.]?\s*",
        r"^Собственно[,.]?\s+(?=\S)",
        r"^Собственно говоря[,.]?\s*",
        r"^Короче[,.]?\s+(?=\S)",
        r"^Короче говоря[,.]?\s*",
        r"^В общем[,.]?\s+(?=\S)",
        r"^В общем-то[,.]?\s*",
        r"^Смотри[,.]?\s+(?=\S)",
        r"^Знаешь[,.]?\s+(?=\S)",
        r"^Знаете[,.]?\s+(?=\S)",
        r"^Послушай[,.]?\s*",
        r"^Послушайте[,.]?\s*",
    ]

    FILLER_ENDS = [
        r"\s*Yana savol bo'lsa[,.]?.*$",
        r"\s*Boshqa savollar[?]?.*$",
        r"\s*Qo'shimcha yordam kerak[?]?.*$",
        r"\s*Umid qilamanki.*$",
        r"\s*Ещё вопросы[?]?.*$",
        r"\s*Если нужна помощь.*$",
    ]

    RESET_SIGNALS = ["Aslida", "To'g'risi", "Aniqrog'i", "Qaytadan", "На самом деле", "Правильнее"]

    def clean(self, text: str, max_words: int = 500) -> str:
        """
        LLM javobini tozalaydi.
        1. Boshlanish fillerlarini o'chiradi
        2. Oxirgi keraksiz gaplarni o'chiradi
        3. Ikki bo'sh qatorni birga qisqartiradi
        4. max_words dan uzun bo'lsa — qisqartiradi (ovoz uchun)
        """
        if not text or not str(text).strip():
            return ""
        text = str(text).strip()
        for pattern in self.FILLER_STARTS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        for pattern in self.FILLER_ENDS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + "..."
        return text.strip()

    def _is_sentence_complete(self, text: str) -> bool:
        """Gap tugaganini aniqlash."""
        if not text or not text.strip():
            return False
        t = text.strip()
        return any(t.endswith(p) for p in (". ", "! ", "? ", ".\n", "!\n", "?\n", "..."))

    def prevent_double_response(
        self, response_tokens: Iterator[str], buffer_size: int = 10
    ) -> Generator[str, None, None]:
        """
        M6: Ikki marta boshlash muammosi.
        Reset signal topilsa — buffer tozalanadi.
        """
        buffer: list[str] = []
        for token in response_tokens:
            buffer.append(token)
            buf_text = "".join(buffer)
            if any(s in buf_text for s in self.RESET_SIGNALS) and len(buffer) < buffer_size:
                buffer = []
                continue
            if len(buffer) >= 3:
                yield buffer.pop(0)
        yield from buffer

    def split_for_tts(self, text: str, max_chars: int = 200) -> list[str]:
        """
        Uzun javobni TTS uchun qismlarga bo'ladi.
        Har qism = 1–2 gap = TTS darhol ayta oladi.
        """
        if not text or not text.strip():
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) + 1 < max_chars:
                current = (current + " " + s).strip() if current else s
            else:
                if current:
                    chunks.append(current)
                current = s
        if current:
            chunks.append(current)
        return chunks


_cleaner: ResponseCleaner | None = None


def get_response_cleaner() -> ResponseCleaner:
    """Singleton."""
    global _cleaner
    if _cleaner is None:
        _cleaner = ResponseCleaner()
    return _cleaner
