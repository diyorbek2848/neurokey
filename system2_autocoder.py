# -*- coding: utf-8 -*-
"""
NeuroKey - System-2 Auto-Coder (The ASI Prototype Loop)

Bu modul NeuroKey'ni oddiy savol-javob (System-1) rejimidan
chuqur tahlil qilib, o'zi kod yozib, o'zi tekshiradigan (System-2) rejimiga
olib o'tadi. Tree of Thoughts va Code Execution Sandbox mexanizmlarini o'z ichiga oladi.
"""

import os
import sys
import time
import subprocess
import logging
from typing import Tuple

import config as C
from llm_router import answer

log = logging.getLogger(__name__)

SANDBOX_DIR = os.path.join(C.APP_DIR, "sandbox")
os.makedirs(SANDBOX_DIR, exist_ok=True)

MAX_ITERATIONS = 3
TIMEOUT_SECONDS = 15

def run_in_sandbox(code: str, script_name: str = "temp_exec.py") -> Tuple[bool, str]:
    """Kodni xavfsiz sandbox muhitida ishga tushiradi."""
    script_path = os.path.join(SANDBOX_DIR, script_name)
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)
    except Exception as e:
        return False, f"Fayl yaratishda xato: {e}"

    try:
        # Xavfsizlik: Boshqa python muhitini chaqirish
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            encoding="utf-8"
        )
        
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip() or result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"Xato: Kod {TIMEOUT_SECONDS} soniyadan uzoq ishladi (Timeout)."
    except Exception as e:
        return False, f"Tizim xatosi: {e}"

def generate_and_critique_code(task: str, previous_error: str = "") -> str:
    """Muammo yechimi uchun kod yozadi yoki xatoni tahlil qilib tuzatadi (Tree of Thoughts)."""
    
    if not previous_error:
        prompt = (
            f"Vazifa: {task}\n\n"
            "Sen yuqori darajadagi ASI tizimisan. Yuqoridagi vazifani to'liq avtomatlashtirish "
            "va yechish uchun Python script yoz. Kod qat'iy ravishda hech qanday odam aralashuvisiz "
            "ishlashi kerak (masalan, input() ishlatma). "
            "Natijani print() orqali ekranga chiqar, chunki men stdout'ni o'qiyman.\n"
            "FAQATGINA ishlashga tayyor Python kodini yoz. Hech qanday Markdown (```python) yoki tushuntirish yozma. "
            "Kod importlardan boshlanishi kerak."
        )
    else:
        prompt = (
            f"Vazifa: {task}\n\n"
            f"Sening oldingi yozgan koding ishga tushganda quyidagi xatoni (Error) berdi:\n"
            f"--- ERROR BEGIN ---\n{previous_error}\n--- ERROR END ---\n\n"
            "Skeptik (Critic) sifatida bu xatoni chuqur tahlil qil va kodni 100% ishlashi uchun tuzatib qayta yoz.\n"
            "FAQATGINA ishlashga tayyor Python kodini yoz. Hech qanday Markdown yoki tushuntirish yozma."
        )

    log.info("[System-2] LLM ga kod yozish/tuzatish bo'yicha so'rov yuborilmoqda...")
    # LLM_router orqali xom kodni olish
    raw_code = answer(prompt, brief=False)
    
    # Koddagi markdownlarni tozalash (agar baribir yozib qo'ygan bo'lsa)
    cleaned_code = raw_code.strip()
    if cleaned_code.startswith("```python"):
        cleaned_code = cleaned_code[9:]
    elif cleaned_code.startswith("```"):
        cleaned_code = cleaned_code[3:]
    if cleaned_code.endswith("```"):
        cleaned_code = cleaned_code[:-3]
        
    return cleaned_code.strip()

def autonomous_solve(task: str) -> str:
    """To'liq System-2 tsikli: Muammoni o'zi kod yozib yechadi."""
    log.info(f"=== System-2 ASI Loop boshlandi: {task} ===")
    
    error_msg = ""
    for iteration in range(1, MAX_ITERATIONS + 1):
        log.info(f"--- Iteration {iteration}/{MAX_ITERATIONS} ---")
        
        # 1. Kod generatsiya / Xatoni tuzatish
        code = generate_and_critique_code(task, previous_error=error_msg)
        
        if not code:
            return "[System-2 Xatosi] LLM kod yoza olmadi."
            
        log.info(f"[System-2] Kod yozildi ({len(code)} belgi). Sandbox ga yuborilmoqda...")
        
        # 2. Kodni ishga tushirish (Sandbox)
        success, output = run_in_sandbox(code)
        
        # 3. Tekshirish
        if success:
            log.info(f"[System-2] Muvaffaqiyatli yakunlandi! Natija: {output[:100]}...")
            return (
                f"[SYSTEM-2 SUCCESS]\n"
                f"Vazifa: {task}\n"
                f"Kod ishga tushirildi va quyidagi natijani berdi:\n\n{output}"
            )
        else:
            log.warning(f"[System-2] Kod xato berdi: {output[:100]}...")
            error_msg = output
            
    # Agar tsikl tugasa-yu, yechim topilmasa
    return (
        f"[SYSTEM-2 FAILED]\n"
        f"Vazifa: {task}\n"
        f"Tizim {MAX_ITERATIONS} marta urinib ko'rdi, lekin kod xato ishladi.\n"
        f"Oxirgi xato:\n{error_msg}"
    )

if __name__ == "__main__":
    # Test uchun
    print("Testing System-2 Auto-Coder...")
    result = autonomous_solve("Menga 1 dan 10 gacha sonlar yig'indisini hisoblaydigan dastur yoz va natijani aniq raqam bilan chiqarginda to'xta.")
    print(result)
