# -*- coding: utf-8 -*-
"""
tonight_engine.py — NeuroKey Kechasi O'zini Tahlil Qiladi
===========================================================
Har kun kechasi (yoki egasi "analyze yourself" deganda):

  1. Bugungi suhbat loglarini o'qiydi
  2. Nima so'raldi lekin javob berilmadi?
  3. LLM bilan tahlil qiladi -> eng foydali yangilik taklif etadi
  4. Egasiga: "Shuni qo'shsam maylimi?" — TASDIQ KUTADI
  5. Tasdiqlansa -> organ kodi yozadi -> sinab ko'radi -> qo'shadi
  6. growth_timeline.json ga yozadi

Bu investor oldida ishga tushiriladi. NeuroKey o'z kodini yozadi.
Hech bir boshqa AI bu qila olmaydi.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import importlib.util
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple

# ── Yo'llar ──────────────────────────────────────────────────────────────────
_BASE        = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH    = os.path.join(_BASE, "data", "neurokey_actions.log")
_ORGANS_DIR  = os.path.join(_BASE, "neurokey_organs")
_GROWTH_PATH = os.path.join(_BASE, "data", "growth_timeline.json")
_TONIGHT_LOG = os.path.join(_BASE, "data", "tonight_log.json")

# ── LLM client (to'g'ridan-to'g'ri Groq — kod yozish uchun ko'p token kerak) ─
def _groq_call(system: str, user: str, max_tokens: int = 1200) -> str:
    """Groq API ga to'g'ridan-to'g'ri murojaat."""
    try:
        from openai import OpenAI
        import config as C

        api_key  = os.environ.get("GROQ_API_KEY", "") or getattr(C, "GROQ_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "") or getattr(C, "OPENAI_BASE_URL", "")

        if not api_key:
            # .env dan qo'lda o'qish
            env_path = os.path.join(_BASE, ".env")
            if os.path.exists(env_path):
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("GROQ_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break

        if not base_url:
            base_url = "https://api.groq.com/openai/v1"

        client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        resp = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",   # kod yozish
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
            timeout=30,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"  [TONIGHT] LLM xato: {e}")
        return ""


# ── Log o'qish ────────────────────────────────────────────────────────────────
def _read_today_conversations() -> List[Dict[str, str]]:
    """Bugungi suhbatlarni o'qish (neurokey_actions.log formatidan)."""
    convs = []
    today_str = date.today().isoformat()  # "2026-05-23"

    if not os.path.exists(_LOG_PATH):
        return convs

    try:
        with open(_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Format: timestamp|user:...|assistant:...|result:
            # yoki: timestamp | action | detail
            parts = line.split("|")
            if len(parts) < 2:
                continue

            # Bugungi suhbatlar
            ts_part = parts[0].strip()
            is_today = today_str in ts_part

            # user: va assistant: bor bo'lsa — suhbat
            user_text = ""
            assistant_text = ""
            for part in parts[1:]:
                part = part.strip()
                if part.startswith("user:"):
                    user_text = part[5:].strip()
                elif part.startswith("assistant:"):
                    assistant_text = part[10:].strip()

            if user_text and is_today:
                convs.append({
                    "user": user_text,
                    "assistant": assistant_text,
                    "answered": bool(assistant_text and len(assistant_text) > 5),
                })

    except Exception as e:
        print(f"  [TONIGHT] Log o'qish xato: {e}")

    return convs


def _read_existing_organs() -> List[str]:
    """Mavjud organlar ro'yxati."""
    organs = []
    if os.path.isdir(_ORGANS_DIR):
        for fname in os.listdir(_ORGANS_DIR):
            if fname.startswith("organ_") and fname.endswith(".py"):
                organs.append(fname)
    return organs


# ── Tahlil ────────────────────────────────────────────────────────────────────
def analyze_and_propose() -> Optional[Dict[str, Any]]:
    """
    Bugungi loglarni o'qib, eng foydali yangilikni taklif qiladi.
    Returns: proposal dict yoki None (taklif yo'q)
    """
    sep = "=" * 60
    print(f"\n  {sep}")
    print("  NEUROKEY - KECHASI O'ZINI TAHLIL QILMOQDA")
    print(f"  {sep}")

    convs = _read_today_conversations()
    existing = _read_existing_organs()

    if not convs:
        # Bugun log bo'lmasa — oxirgi 3 kunni ko'r
        print("  Bugun suhbat yo'q — oldingi muvaffaqiyatsiz tahlillar ko'rilmoqda...")
        # improvement_plan.json dan o'qi
        plan_path = os.path.join(_BASE, "data", "improvement_plan.json")
        convs_summary = "Bugun suhbat bo'lmadi."
    else:
        # Javobsiz qolganlar
        unanswered = [c for c in convs if not c["answered"]]
        all_questions = [c["user"] for c in convs]

        # Takrorlanuvchilarni top
        from collections import Counter
        word_counter: Counter = Counter()
        for q in all_questions:
            for word in q.lower().split():
                if len(word) > 3:
                    word_counter[word] += 1

        top_words = [w for w, _ in word_counter.most_common(10)]

        convs_summary = (
            f"Bugun {len(convs)} ta savol bo'ldi. "
            f"Javobsiz: {len(unanswered)} ta. "
            f"Eng ko'p so'zlar: {', '.join(top_words[:5])}. "
            f"Oxirgi 5 ta savol: {'; '.join([c['user'][:40] for c in convs[-5:]])}"
        )

    print(f"  Bugungi tahlil: {convs_summary[:100]}...")
    print("  LLM tahlil qilmoqda...")

    existing_str = ", ".join(existing) if existing else "yo'q"

    system = """Sen NeuroKey — shaxsiy sun'iy ong tizimisan.
Sen o'zingning bugungi xatolaringni tahlil qilib, o'zingga yangi organ (funksiya) qo'shmoqchisan.

ORGAN NIMA: neurokey_organs/organ_XXX.py fayli. Faqat bitta funksiya: organ_handle(text) -> str yoki None.
Agar organ matni o'ziga tegishli deb bilsa — javob qaytaradi. Aks holda None.

QOIDALAR:
- Faqat BITTA aniq, foydali organ taklif qil
- Organ oddiy bo'lsin — 20-50 qator Python kodi
- Tashqi API ishlatma (internet shart emas)
- organ_handle(text) -> str yoki None
- Faylni organ_SANA_nom.py formatida nom ber
"""

    user = f"""Bugungi tahlil: {convs_summary}

Mavjud organlar: {existing_str}

Quyidagi JSON formatida javob ber (boshqa narsa yozma):
{{
  "organ_filename": "organ_20260523_nom.py",
  "description": "Bu organ nima qiladi (1 jumlada)",
  "reason": "Nima uchun kerak (bugungi muammoga asoslanib)",
  "trigger_keywords": ["kalit1", "kalit2", "kalit3"],
  "code": "# -*- coding: utf-8 -*-\\ndef organ_handle(text):\\n    ..."
}}

Faqat JSON, boshqa text yo'q."""

    raw = _groq_call(system, user, max_tokens=1500)
    if not raw:
        print("  [TONIGHT] LLM javob bermadi.")
        return None

    # JSON extract — robustly
    try:
        # ```json ... ``` ni olib tashlash
        raw_clean = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        # Birinchi { dan oxirgi } gacha
        start = raw_clean.find("{")
        end   = raw_clean.rfind("}") + 1
        if start == -1 or end == 0:
            print("  [TONIGHT] JSON topilmadi.")
            return None
        json_str = raw_clean[start:end]

        # 1. To'g'ridan-to'g'ri parse
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 2. "code" maydonini ajratib, keyinroq qo'yish
        # (LLM ba'zan code ichida buzuq escape qo'yadi)
        code_match = re.search(r'"code"\s*:\s*"(.*?)"(?=\s*[,}])', json_str, re.DOTALL)
        code_raw = ""
        if code_match:
            code_raw = code_match.group(1)
            # code ni placeholder bilan almashtirish
            json_no_code = json_str[:code_match.start()] + '"code": "__CODE__"' + json_str[code_match.end():]
        else:
            json_no_code = json_str

        try:
            proposal = json.loads(json_no_code)
            if code_raw:
                # escape larni tuzatish
                code_fixed = code_raw.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
                proposal["code"] = code_fixed
            return proposal
        except json.JSONDecodeError:
            pass

        # 3. Regex bilan maydonlarni qo'lda ajratish
        def _extract(key: str) -> str:
            m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', json_str)
            return m.group(1) if m else ""

        def _extract_list(key: str) -> list:
            m = re.search(rf'"{key}"\s*:\s*\[([^\]]*)\]', json_str)
            if not m:
                return []
            return [x.strip().strip('"') for x in m.group(1).split(",")]

        proposal = {
            "organ_filename": _extract("organ_filename"),
            "description":    _extract("description"),
            "reason":         _extract("reason"),
            "trigger_keywords": _extract_list("trigger_keywords"),
            "code": code_raw.replace("\\n", "\n").replace("\\t", "\t") if code_raw else "",
        }
        if proposal["description"] or proposal["organ_filename"]:
            return proposal

        print(f"  [TONIGHT] JSON parse xato — manual extract ham muvaffaqiyatsiz.")
        return None

    except Exception as e:
        print(f"  [TONIGHT] JSON xato: {e}")
        return None


# ── Egaga taklif ─────────────────────────────────────────────────────────────
def present_to_owner(proposal: Dict[str, Any]) -> bool:
    """Ekranda chiroyli ko'rsatib, egasidan rozilik so'raydi."""
    sep = "=" * 60
    print()
    print(f"  {sep}")
    print("  NEUROKEY - YANGILANISH TAKLIFI")
    print(f"  {sep}")
    print()
    print(f"  [*] Taklif: {proposal.get('description', '?')}")
    print(f"  [>] Sabab:  {proposal.get('reason', '?')}")
    print(f"  [F] Fayl:   {proposal.get('organ_filename', '?')}")
    kw = proposal.get("trigger_keywords", [])
    if kw:
        print(f"  [K] Kalit so'zlar: {', '.join(kw[:5])}")
    print()
    print("  Agar qo'shilsa, NeuroKey bu yangi qobiliyatga ega bo'ladi.")
    print()

    try:
        answer = input("  Qo'shsamma? [H]a / [Y]o'q > ").strip().lower()
        return answer in ("h", "ha", "y", "yes", "1", "да", "ok", "+")
    except (EOFError, KeyboardInterrupt):
        print("\n  Bekor qilindi.")
        return False


# ── Avto-install paket ───────────────────────────────────────────────────────
def _auto_install(package_name: str) -> bool:
    """Yetishmayotgan paketni avto o'rnatish."""
    import subprocess
    venv_pip = os.path.join(_BASE, ".venv", "Scripts", "pip.exe")
    pip_cmd  = venv_pip if os.path.exists(venv_pip) else sys.executable + " -m pip"
    try:
        print(f"  [INSTALL] pip install {package_name} ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name, "--quiet"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"  [OK] {package_name} o'rnatildi.")
            return True
        else:
            print(f"  [XATO] O'rnatish muvaffaqiyatsiz: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"  [XATO] pip xato: {e}")
        return False


# ── Xatoni tahlil qilish ─────────────────────────────────────────────────────
def _parse_error(error_text: str) -> Tuple[str, str]:
    """
    Xato turini va kerakli paketni aniqlab beradi.
    Returns: (error_type, package_name_if_any)
    """
    err = str(error_text)
    # ModuleNotFoundError: No module named 'X'
    m = re.search(r"No module named '([^']+)'", err)
    if m:
        pkg = m.group(1).split(".")[0]  # 'PIL.Image' -> 'PIL'
        # Modul nomi -> paket nomi mapping
        _pkg_map = {
            "PIL": "pillow", "cv2": "opencv-python", "sklearn": "scikit-learn",
            "bs4": "beautifulsoup4", "yaml": "pyyaml", "dotenv": "python-dotenv",
            "dateutil": "python-dateutil", "Crypto": "pycryptodome",
        }
        return "missing_module", _pkg_map.get(pkg, pkg)
    if "SyntaxError" in err:
        return "syntax_error", ""
    if "IndentationError" in err:
        return "indent_error", ""
    if "NameError" in err:
        return "name_error", ""
    return "runtime_error", ""


# ── LLM ga xatoni yuborib tuzatish ───────────────────────────────────────────
def _fix_code_with_llm(code: str, error: str, description: str) -> str:
    """Xato kodini LLM ga yuborib tuzatilgan versiyasini so'rash."""
    system = """Sen Python kod tuzatuvchisan.
Senga NeuroKey organ kodi va uning xatosi beriladi.
Xatoni topib, tuzatilgan kodni qaytarasan.

QOIDALAR:
- Faqat Python kodi, boshqa gap yo'q
- organ_handle(text) funksiyasi bo'lishi SHART
- Tashqi paket kerak bo'lsa, try/except bilan o'rab ol
- Xatoni aniq tuzat, boshqa narsani o'zgartirma
"""
    user = f"""Bu organ: {description}

XATO:
{error}

HOZIRGI KOD:
```python
{code}
```

Tuzatilgan kodni ber. Faqat kod, izoh yo'q."""

    raw = _groq_call(system, user, max_tokens=1200)
    if not raw:
        return code  # tuzatolmadi — asl kod qaytadi

    # Kod bloklarini tozalash
    raw = re.sub(r"```(?:python)?", "", raw).replace("```", "").strip()
    return raw


# ── Organ yozish, sinash, tuzatish (3 urinish) ───────────────────────────────
def write_and_test_organ(proposal: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Organ kodini yozib, sinab ko'radi.
    Xato bo'lsa: avto-install yoki LLM bilan tuzatadi (max 3 urinish).
    Returns: (success, organ_filepath)
    """
    filename    = proposal.get("organ_filename", "")
    code        = proposal.get("code", "")
    description = proposal.get("description", "")
    keywords    = proposal.get("trigger_keywords", [])

    # Fayl nomini tozalash
    filename = re.sub(r"[^a-zA-Z0-9_.]", "", filename)
    if not filename.startswith("organ_"):
        filename = f"organ_{datetime.now().strftime('%Y%m%d')}_auto.py"
    if not filename.endswith(".py"):
        filename += ".py"

    organ_path = os.path.join(_ORGANS_DIR, filename)
    os.makedirs(_ORGANS_DIR, exist_ok=True)

    # Sarlavha
    header = (
        f"# -*- coding: utf-8 -*-\n"
        f"# NeuroKey organ — {description}\n"
        f"# Yaratildi: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"# Kalit so'zlar: {', '.join(keywords)}\n"
        f"# Tonight Engine tomonidan avtomatik yozilgan.\n\n"
    )

    if "def organ_handle" not in code:
        code += "\n\ndef organ_handle(text: str):\n    return None\n"

    MAX_ATTEMPTS = 3
    last_error   = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            print(f"\n  [RETRY] {attempt}-urinish — xato tuzatilmoqda...")
            # LLM bilan tuzatish
            code = _fix_code_with_llm(code, last_error, description)
            if "def organ_handle" not in code:
                code += "\n\ndef organ_handle(text: str):\n    return None\n"

        full_code = header + code

        # Faylga yozish
        try:
            with open(organ_path, "w", encoding="utf-8") as f:
                f.write(full_code)
        except Exception as e:
            print(f"  [XATO] Yozish xato: {e}")
            return False, ""

        # Sinash
        print(f"  [TEST] Sinab ko'rilmoqda (urinish {attempt}/{MAX_ATTEMPTS})...")
        try:
            spec = importlib.util.spec_from_file_location(f"_test_organ_{attempt}", organ_path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            handler = getattr(mod, "organ_handle", None)
            if callable(handler):
                test_input = keywords[0] if keywords else "test"
                result = handler(test_input)
                print(f"  [~] '{test_input}' -> '{str(result)[:60]}'")
                print(f"  [OK] Organ ishlayapti! ({attempt}-urinishda)")
                return True, organ_path
            else:
                print("  [!] organ_handle topilmadi — yuklandigan hisoblaymiz.")
                return True, organ_path

        except Exception as e:
            last_error = str(e)
            print(f"  [XATO] {last_error[:120]}")

            # Yetishmayotgan paket?
            err_type, pkg = _parse_error(last_error)
            if err_type == "missing_module" and pkg:
                installed = _auto_install(pkg)
                if installed:
                    # O'rnatildi — qayta sin
                    continue

            # Sintaksis xato — LLM tuzatishi kerak (keyingi iteratsiyada)
            if attempt == MAX_ATTEMPTS:
                print(f"  [XATO] {MAX_ATTEMPTS} urinishda ham ishlamadi. O'chirilmoqda.")
                try:
                    os.remove(organ_path)
                except Exception:
                    pass
                return False, ""

    return False, ""


# ── Growth timeline ───────────────────────────────────────────────────────────
def _record_to_timeline(proposal: Dict[str, Any], organ_path: str) -> None:
    """growth_timeline.json ga yozish."""
    try:
        import growth_timeline as gt
        gt.record_improvement(
            organ_name=proposal.get("organ_filename", "?"),
            reason=proposal.get("reason", ""),
            description=proposal.get("description", ""),
            trigger_keywords=proposal.get("trigger_keywords", []),
            confirmed_by_owner=True,
        )
        total = gt.get_total_count()
        print(f"\n  [^] O'sish tarixi: NeuroKey {total} marta o'zini yangiladi.")
    except Exception as e:
        print(f"  [TONIGHT] Timeline xato: {e}")


# ── Hot-reload ────────────────────────────────────────────────────────────────
def _reload_organs() -> None:
    """Yangi organ darhol tizimga ulanadi."""
    try:
        import organ_loader
        count, errors = organ_loader.reload_organs()
        if errors:
            print(f"  [!] Organlar yuklashda xato: {errors}")
        else:
            print(f"  [~] {count} ta organ tizimga ulandi.")
    except Exception as e:
        print(f"  [TONIGHT] Reload xato: {e}")


# ── Asosiy funksiya ───────────────────────────────────────────────────────────
def run_tonight_engine() -> bool:
    """
    To'liq kechasi tahlil va yangilanish.
    Returns: True — yangilanish amalga oshirildi.
    """
    # 1. Tahlil
    proposal = analyze_and_propose()
    if not proposal:
        print("\n  [i] Bugun taklif yo'q — hamma narsa yaxshi ishlayapti.")
        return False

    # 2. Egaga ko'rsatish
    confirmed = present_to_owner(proposal)
    if not confirmed:
        print("\n  Bekor qilindi. Ertaga yana tahlil qilinadi.")
        return False

    print("\n  NeuroKey o'zini yangilayapti...")
    time.sleep(0.5)

    # 3. Organ yozish va test
    success, organ_path = write_and_test_organ(proposal)
    if not success:
        print("\n  [XATO] Yangilanish muvaffaqiyatsiz. Keyingi marta urinamiz.")
        return False

    # 4. Timeline ga yozish
    _record_to_timeline(proposal, organ_path)

    # 5. Hot-reload
    _reload_organs()

    sep = "=" * 60
    print()
    print(f"  {sep}")
    print("  [OK] NEUROKEY O'ZINI YANGILADI!")
    print(f"  {sep}")
    print()

    # Tonight log ga yozish
    try:
        log_entry = {
            "date": datetime.now().isoformat(),
            "proposal": proposal.get("description", ""),
            "organ": proposal.get("organ_filename", ""),
            "success": True,
        }
        tonight_log = []
        if os.path.exists(_TONIGHT_LOG):
            with open(_TONIGHT_LOG, "r", encoding="utf-8") as f:
                tonight_log = json.load(f)
        tonight_log.append(log_entry)
        with open(_TONIGHT_LOG, "w", encoding="utf-8") as f:
            json.dump(tonight_log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return True


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.path.insert(0, _BASE)
    run_tonight_engine()
