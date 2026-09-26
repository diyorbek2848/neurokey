# -*- coding: utf-8 -*-
# NeuroKey organ — Tonight Engine + Growth Timeline (ovozli boshqaruv)
# Yaratildi: 2026-05-23
# Bu organ "o'zingni tahlil qil" deyilganda Tonight Engine ni ishga tushiradi.

import threading
_engine_lock = threading.Lock()


def organ_handle(text: str):
    """
    Foydalanuvchi "analyze yourself", "o'zingni yangiла", "tonight" kabi
    so'z aytganda Tonight Engine ishga tushadi.
    """
    t = (text or "").strip().lower()

    # === Growth timeline ===
    growth_kw = [
        "o'sish", "rost tarixi", "necha marta yangilagan", "growth",
        "timeline", "nechi marta yaxshilangan", "tarix", "qancha o'sgan",
        "how many times", "improvements",
    ]
    if any(k in t for k in growth_kw):
        try:
            import growth_timeline as gt
            return gt.get_summary()
        except Exception as e:
            return f"Growth timeline xato: {e}"

    # === Tonight engine ===
    tonight_kw = [
        "o'zingni tahlil qil", "o'zingni yangi", "analyze yourself",
        "tonight", "kechasi tahlil", "self improve", "upgrade yourself",
        "o'zingni yaxshila", "yangilik taklif qil", "nima yaxshilanadi",
        "o'zing kod yoz",
    ]
    if any(k in t for k in tonight_kw):
        if not _engine_lock.acquire(blocking=False):
            return "Tonight Engine allaqachon ishlayapti..."
        try:
            import threading
            def _run():
                try:
                    import tonight_engine
                    tonight_engine.run_tonight_engine()
                except Exception as e:
                    print(f"[TONIGHT] Xato: {e}")
                finally:
                    _engine_lock.release()
            threading.Thread(target=_run, daemon=True).start()
            return (
                "Tonight Engine ishga tushdi. "
                "Bugungi loglar tahlil qilinmoqda — birozdan so'ng taklif ko'rasiz."
            )
        except Exception as e:
            _engine_lock.release()
            return f"Tonight Engine xato: {e}"

    return None
