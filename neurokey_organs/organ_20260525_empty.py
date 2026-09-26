# -*- coding: utf-8 -*-
# NeuroKey organ — Bo'sh suhbatni qayd qiladi
# Yaratildi: 2026-05-23 16:38
# Kalit so'zlar: suhbat, bo'lmadi, bo'sh
# Tonight Engine tomonidan avtomatik yozilgan.

# -*- coding: utf-8 -*-
def organ_handle(text):
    if 'suhbat' in text and ('bo\'lmadi' in text or 'bo\'sh' in text):
        return 'Bugun suhbat bo\'lmadi'
    return None