# -*- coding: utf-8 -*-
"""NeuroKey — Tush Konsolidatori (Dream Consolidator).

Inson miyasi uyquda o'rganadi — xotirani qayta ishlaydi, muhimini saqlaydi.
Bu modul — NeuroKey'ning "uyqu" jarayoni.

Har kecha soat 03:00 da (yoki qo'lda chaqirilganda):
1. Bugungi suhbatlarni tahlil qiladi
2. Muhim narsalarni ajratadi
3. Yangi qoidalar yozadi
4. Narrative self'ni yangilaydi
5. Eski keraksiz ma'lumotlarni tozalaydi
6. Ertangi kun uchun "niyat" belgilaydi

Bu 2026-yil suniy ong yaratishning eng muhim qismi.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

try:
    import episodic_memory as _ep_mem
except ImportError:
    _ep_mem = None

try:
    import continuous_learning as _cont_learn
except ImportError:
    _cont_learn = None

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DREAM_LOG_PATH = os.path.join(_BASE_DIR, "data", "dream_log.json")
_CONSOLIDATION_LOCK = threading.Lock()
_dream_thread: Optional[threading.Thread] = None
_running = False


def _load_dream_log() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(_DREAM_LOG_PATH):
            with open(_DREAM_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_dream_log(log_data: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(_DREAM_LOG_PATH), exist_ok=True)
        with open(_DREAM_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log_data[-30:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.debug("[Dream] log saqlash xato: %s", e)


def _extract_key_topics(turns: List[Dict]) -> List[str]:
    """Suhbatdan asosiy mavzularni ajratish."""
    word_freq: Dict[str, int] = {}
    stop_words = {
        "va", "bu", "men", "sen", "u", "biz", "bir", "ha", "yo'q",
        "the", "and", "is", "it", "to", "a", "an", "in", "of",
        "что", "это", "как", "для", "по", "на", "не", "да", "нет",
    }
    for turn in turns:
        for field in ("user", "assistant"):
            text = turn.get(field, "")
            for word in text.lower().split():
                word = word.strip(".,!?;:()[]{}\"'")
                if len(word) > 4 and word not in stop_words:
                    word_freq[word] = word_freq.get(word, 0) + 1

    # Eng ko'p uchraydigan 5 ta mavzu
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:5]]


def _analyze_reflections(reflections: List[Dict]) -> str:
    """Refleksiyalardan xulosa."""
    if not reflections:
        return ""
    thoughts = [r.get("thought", "") for r in reflections[-10:] if r.get("thought")]
    if not thoughts:
        return ""
    return "Bugungi fikrlar: " + "; ".join(thoughts[:3])


def _check_if_already_ran_today() -> bool:
    """Bugun konsolidatsiya o'tgan-o'tmaganini tekshirish."""
    dream_logs = _load_dream_log()
    if not dream_logs:
        return False
    last = dream_logs[-1]
    last_date = last.get("date", "")
    today = datetime.now().strftime("%Y-%m-%d")
    return last_date == today


def consolidate(force: bool = False) -> Dict[str, Any]:
    """Asosiy konsolidatsiya jarayoni.

    Args:
        force: True bo'lsa bugun allaqachon o'tgan bo'lsa ham qayta ishlaydi.

    Returns: natija dict
    """
    with _CONSOLIDATION_LOCK:
        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "success": False,
        }

        if not force and _check_if_already_ran_today():
            result["skipped"] = "Bugun allaqachon o'tdi"
            return result

        log.info("[Dream] Konsolidatsiya boshlanmoqda... %s", result["date"])

        # === 1-QADAM: Bugungi suhbatlarni o'qish ===
        cons_path = os.path.join(_BASE_DIR, "data", "consciousness.json")
        turns = []
        reflections = []
        inner_thoughts = []

        try:
            if os.path.exists(cons_path):
                with open(cons_path, "r", encoding="utf-8") as f:
                    cons_data = json.load(f)
                turns = cons_data.get("working_memory", [])
                reflections = cons_data.get("reflections", [])
                inner_thoughts = cons_data.get("inner_thoughts", [])
                result["steps"].append(f"✓ Ong ma'lumotlari: {len(turns)} turn, {len(reflections)} refleksiya")
        except Exception as e:
            result["steps"].append(f"✗ Ong o'qishda xato: {e}")

        # === 2-QADAM: Asosiy mavzularni ajratish ===
        topics = []
        try:
            topics = _extract_key_topics(turns)
            if topics:
                result["steps"].append(f"✓ Asosiy mavzular: {', '.join(topics)}")
        except Exception as e:
            result["steps"].append(f"✗ Mavzu ajratishda xato: {e}")

        # === 3-QADAM: Refleksiyalardan xulosa ===
        reflection_summary = ""
        try:
            reflection_summary = _analyze_reflections(reflections)
            if reflection_summary:
                result["steps"].append(f"✓ Refleksiya xulosasi: {reflection_summary[:80]}...")
        except Exception as e:
            result["steps"].append(f"✗ Refleksiya xulosasida xato: {e}")

        # === 4-QADAM: Rules.json ga yangi qoidalar ===
        try:
            from self_modification import add_rule
            # Suhbat bo'lsa — bir jadval
            if len(turns) >= 3:
                topics_str = ", ".join(topics[:3]) if topics else "umumiy mavzular"
                add_rule(
                    f"[{result['date']}] Bugun {len(turns)} suhbat, mavzular: {topics_str}",
                    rule_type="daily_log"
                )
                result["steps"].append("✓ Kunlik qoida yozildi")
        except Exception as e:
            result["steps"].append(f"✗ Qoida yozishda xato: {e}")

        # === 5-QADAM: Narrative self yangilash ===
        try:
            from narrative_self import add_experience, add_lesson, update_narrative_weekly
            if turns or topics:
                exp_summary = ""
                if topics:
                    exp_summary = f"{result['date']}: {len(turns)} suhbat, mavzular: {', '.join(topics[:4])}"
                if reflection_summary:
                    exp_summary = (exp_summary + ". " + reflection_summary[:100]).strip(". ")
                if exp_summary:
                    add_experience(exp_summary)
                    result["steps"].append("✓ Narrativ tajriba qo'shildi")
            # Inner thoughts dan darslar
            for it in inner_thoughts[-3:]:
                thought = it.get("thought", "")
                if thought and len(thought) > 20:
                    add_lesson(f"O'ylagan: {thought[:150]}")
            # Haftalik yangilash
            updated = update_narrative_weekly()
            if updated:
                result["steps"].append("✓ Haftalik narrativ yangilandi")
        except Exception as e:
            result["steps"].append(f"✗ Narrativ yangilashda xato: {e}")

        # === 6-QADAM: Eski ma'lumotlarni tozalash ===
        try:
            if os.path.exists(cons_path):
                with open(cons_path, "r", encoding="utf-8") as f:
                    cons_data = json.load(f)
                # 7 kundan eski turnlarni olib tashlash
                cutoff = time.time() - 7 * 24 * 3600
                old_turns = cons_data.get("working_memory", [])
                new_turns = [t for t in old_turns if t.get("t", 0) > cutoff]
                if len(new_turns) < len(old_turns):
                    cons_data["working_memory"] = new_turns[-16:]  # MAX_WORKING_MEMORY
                    with open(cons_path, "w", encoding="utf-8") as f:
                        json.dump(cons_data, f, ensure_ascii=False, indent=2)
                    result["steps"].append(
                        f"✓ Eski xotira tozalandi: {len(old_turns) - len(new_turns)} turn o'chirildi"
                    )
        except Exception as e:
            result["steps"].append(f"✗ Tozalashda xato: {e}")

        # === 7-QADAM: Ertangi kun "niyati" ===
        try:
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            intention = {
                "date": tomorrow,
                "intention": "Foydalanuvchiga yanada yaxshiroq yordam berish",
                "topics_to_revisit": topics[:3],
            }
            intention_path = os.path.join(_BASE_DIR, "data", "tomorrow_intention.json")
            with open(intention_path, "w", encoding="utf-8") as f:
                json.dump(intention, f, ensure_ascii=False, indent=2)
            result["steps"].append(f"✓ Ertangi niyat yozildi: {tomorrow}")
        except Exception as e:
            result["steps"].append(f"✗ Niyat yozishda xato: {e}")

        # === 7b-QADAM: Epizodik xotiradan muhim voqealarni qo'shish ===
        try:
            if _ep_mem is not None:
                ep_items = _ep_mem.get_recent_episodes(n=5)
                for ep in ep_items:
                    summary = ep.get("summary") or ep.get("content", "")
                    if summary and len(summary) > 20:
                        result["steps"].append(f"✓ Epizod saqlandi: {summary[:60]}")
                        break
        except Exception as e:
            result["steps"].append(f"✗ Epizodik xotira xato: {e}")

        # === 7c-QADAM: O'rganish progressini qayd etish ===
        try:
            if _cont_learn is not None:
                progress = _cont_learn.get_learning_progress()
                if progress:
                    result["learning_progress"] = progress
        except Exception as e:
            pass

        # === NATIJA ===
        result["finished_at"] = datetime.now().isoformat()
        result["success"] = True
        result["topics"] = topics
        result["turns_processed"] = len(turns)

        # Dream log ga qo'shish
        dream_log = _load_dream_log()
        dream_log.append(result)
        _save_dream_log(dream_log)

        log.info(
            "[Dream] Konsolidatsiya tugadi: %d qadam, %d turn qayta ishlandi",
            len(result["steps"]),
            len(turns),
        )
        return result


def get_last_dream_summary() -> str:
    """Oxirgi konsolidatsiya xulosasi — LLM uchun."""
    logs = _load_dream_log()
    if not logs:
        return ""
    last = logs[-1]
    date = last.get("date", "")
    topics = last.get("topics", [])
    turns = last.get("turns_processed", 0)
    if not date:
        return ""
    parts = [f"Последняя консолидация: {date}"]
    if turns:
        parts.append(f"Обработано бесед: {turns}")
    if topics:
        parts.append(f"Темы: {', '.join(topics[:3])}")
    return " | ".join(parts)


def _dream_scheduler_loop() -> None:
    """Har kecha soat 03:00 da konsolidatsiya."""
    while _running:
        now = datetime.now()
        # Soat 03:00 bo'lsa va bugun hali o'tmagan bo'lsa
        if now.hour == 3 and now.minute < 30:
            if not _check_if_already_ran_today():
                try:
                    log.info("[Dream] Tun konsolidatsiyasi boshlanmoqda...")
                    consolidate()
                except Exception as e:
                    log.error("[Dream] Konsolidatsiya xato: %s", e)
        time.sleep(60 * 15)  # 15 daqiqada bir tekshirish


def start_dream_scheduler() -> None:
    """Tun konsolidatsiyasi schedulerini ishga tushirish."""
    global _dream_thread, _running
    if _dream_thread and _dream_thread.is_alive():
        return
    _running = True
    _dream_thread = threading.Thread(
        target=_dream_scheduler_loop,
        name="dream_scheduler",
        daemon=True
    )
    _dream_thread.start()
    log.info("[Dream] Tun konsolidatsiyasi scheduler ishga tushdi (har kecha 03:00)")


def stop_dream_scheduler() -> None:
    global _running
    _running = False
