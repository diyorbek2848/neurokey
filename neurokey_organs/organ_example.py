# -*- coding: utf-8 -*-
# NeuroKey organ — Recursive Self-Evolution
# Dynamic Organ Integration: bu fayl tizimga avtomatik ulanadi.
# organ_handle(text) -> str yoki None. None = boshqa handlerlar ishlaydi.

def organ_handle(text: str):
    """Misol: 'organ test' yoki 'organ ishlayaptimi' — tekshirish."""
    t = (text or "").strip().lower()
    if "organ test" in t or "organ ishlayaptimi" in t or "organ works" in t:
        return "Organ ishlayapti. Dynamic Integration faol."
    return None
