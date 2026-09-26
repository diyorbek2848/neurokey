# -*- coding: utf-8 -*-
"""
NeuroKey License Manager (DRM)
Qaroqchilikdan himoya qilish uchun litsenziya kalitini tekshiradi.
B2B va B2C foydalanuvchilari uchun offline/online obuna holatini boshqaradi.
"""
import os
import json
import time

LICENSE_FILE = os.path.join(os.path.dirname(__file__), "data", "license.key")

def _get_hwid():
    """Qurilmaning unikal apparat identifikatorini oladi."""
    try:
        import subprocess
        # Windows UUID ni olish
        output = subprocess.check_output('wmic csproduct get uuid', shell=True).decode()
        uuid = output.split('\n')[1].strip()
        if uuid:
            return uuid
    except:
        pass
    return "UNKNOWN_HWID"

def verify_license():
    """
    Litsenziyani tekshiradi. Agar yaroqsiz bo'lsa False qaytaradi.
    Tizim qulflanishi uchun main.py ushbu funksiyadan foydalanadi.
    """
    # 1. Kalit fayli bormi?
    if not os.path.exists(LICENSE_FILE):
        print("[License] Litsenziya fayli topilmadi!")
        return False
        
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        key = data.get("key")
        hwid = data.get("hwid")
        expiry = data.get("expiry_timestamp", 0)
        
        # 2. Qurilma HWID tekshiruvi (boshqa kompyuterga ko'chirib bo'lmasligi uchun)
        current_hwid = _get_hwid()
        if hwid and current_hwid != "UNKNOWN_HWID" and hwid != current_hwid:
            print("[License] Litsenziya boshqa qurilmaga tegishli!")
            return False
            
        # 3. Muddati tugaganligini tekshirish
        if time.time() > expiry:
            print("[License] Litsenziya muddati tugagan. Iltimos, obunani yangilang.")
            return False
            
        # 4. (Ixtiyoriy) Online server orqali tekshirish
        # try:
        #    import requests
        #    resp = requests.post("https://api.neurokey.uz/verify", json={"key": key, "hwid": current_hwid})
        #    if not resp.json().get("valid"):
        #        return False
        # except:
        #    pass # Offline rejimda ishlashda davom etadi
            
        return True
    except Exception as e:
        print(f"[License] Tekshirish xatosi: {e}")
        return False

def activate_license(key_string, duration_days=30):
    """Yangi litsenziya kalitini faollashtiradi va faylga yozadi."""
    os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
    hwid = _get_hwid()
    expiry = time.time() + (duration_days * 24 * 3600)
    
    data = {
        "key": key_string,
        "hwid": hwid,
        "expiry_timestamp": expiry,
        "activated_at": time.time()
    }
    
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"[License] Faollashtirildi! Muddat: {duration_days} kun.")

if __name__ == "__main__":
    # Test
    activate_license("DEMO-KEY-123", 30)
    is_valid = verify_license()
    print(f"Litsenziya holati: {'Yaroqli' if is_valid else 'Yaroqsiz'}")
