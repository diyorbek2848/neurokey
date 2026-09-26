# -*- coding: utf-8 -*-
""" .env va OPENAI_API_KEY tekshirish. Ishga tushirish: python check_env.py """
import os
import sys

# Loyiha papkasi
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

env_path = os.path.join(ROOT, ".env")
print("Papka:", ROOT)
print(".env fayl:", env_path)
print(" .env mavjud:", os.path.isfile(env_path))
print()

# python-dotenv bilan o'qish
try:
    from dotenv import load_dotenv
    load_dotenv(env_path)
except Exception as e:
    print("dotenv xato:", e)

key = (os.getenv("OPENAI_API_KEY") or "").strip()
if not key:
    print("[XATO] OPENAI_API_KEY .env da yo'q yoki bo'sh.")
    print("  .env ni oching, qator qo'shing: OPENAI_API_KEY=sk-proj-...")
    print("  = dan keyin bo'sh joy QO'YMANGLIK, qo'shtirnoq QO'YMANGLIK.")
    sys.exit(1)

# Kalitni chiqarmaymiz, faqat uzunlik va bosh harflar
mask = key[:7] + "..." + key[-4:] if len(key) > 15 else "***"
print("[OK] OPENAI_API_KEY yuklandi (uzunlik:", len(key), ", masalan:", mask, ")")
if not key.startswith("sk-"):
    print("[!] Ogoh: kalit odatda sk- bilan boshlanadi. Noto'g'ri bo'lishi mumkin.")
if len(key) < 20:
    print("[!] Kalit juda qisqa — noto'g'ri bo'lishi mumkin.")
print()
print("Agar OpenAI 401 beresa: platform.openai.com da yangi kalit yarating va .env ni yangilang.")
print("Tugadi.")
