# -*- coding: utf-8 -*-
# NeuroKey organ — Bo'sh suhbatni aniqlaydi
# Yaratildi: 2026-05-23 16:14
# Sabab: Bugun suhbat bo'lmaganligi uchun
# Kalit so'zlar: suhbat bo'lmadi, gap yo'q
# Bu fayl Tonight Engine tomonidan avtomatik yozilgan.

# -*- coding: utf-8 -*-
def organ_handle(text):
    if 'suhbat bo\'lmadi' in text or 'gap yo\'q' in text:
        return 'Suhbat bo\'lmadi'
    return None