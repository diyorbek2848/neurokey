"""
continuous_trainer.py — O'z-o'zini O'qitish Tizimi
Har suhbatdan keyin model yaxshilanadi.

NeuroKey prinsip: har o'zaro ta'sir → o'rganish → o'sish

2 usul:
1. LORA fine-tuning (lokal model uchun — Ollama + GPU)
2. Prompt evolution (cloud model uchun — API)
"""
from __future__ import annotations
import json, os, time, logging, hashlib
from typing import List, Dict, Optional
log = logging.getLogger(__name__)

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(_DIR, exist_ok=True)
_TRAIN_DATA = os.path.join(_DIR, "training_data.jsonl")
_PROMPT_EVOLUTION = os.path.join(_DIR, "prompt_evolution.json")
_STATS = os.path.join(_DIR, "trainer_stats.json")

# ── Sifat mezonlari ───────────────────────────────────────────────────────────
_GOOD_SIGNALS = [
    "rahmat", "ajoyib", "to'g'ri", "yaxshi", "tushundim",
    "спасибо", "отлично", "правильно", "хорошо", "понял",
    "correct", "great", "perfect", "thanks", "excellent"
]
_BAD_SIGNALS = [
    "xato", "noto'g'ri", "yoqmadi", "tushunmadim", "nima deyapsan",
    "ошибка", "неправильно", "не понял", "не то", "плохо",
    "wrong", "incorrect", "bad", "error", "what"
]


def _load_stats() -> dict:
    try:
        with open(_STATS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "total_samples": 0,
            "good_samples": 0,
            "bad_samples": 0,
            "fine_tune_runs": 0,
            "prompt_evolutions": 0,
            "last_train": 0.0
        }


def _save_stats(s: dict) -> None:
    with open(_STATS, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def record_interaction(user_msg: str, assistant_msg: str,
                       feedback: str = "", quality: float = -1.0) -> dict:
    """
    Har interaksiyani yozib qo'yadi.
    feedback: foydalanuvchining keyingi xabari (sifat belgisi)
    quality: 0.0-1.0 (agar oldindan ma'lum bo'lsa)
    """
    # Sifatni aniqlash
    if quality < 0:
        quality = _infer_quality(feedback, assistant_msg)

    sample = {
        "id": hashlib.md5(f"{user_msg}{time.time()}".encode()).hexdigest()[:8],
        "ts": round(time.time()),
        "user": user_msg[:500],
        "assistant": assistant_msg[:1000],
        "feedback": feedback[:200],
        "quality": round(quality, 3),
        "is_good": quality >= 0.7
    }

    # JSONL ga yozish
    with open(_TRAIN_DATA, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    # Statistika yangilash
    stats = _load_stats()
    stats["total_samples"] += 1
    if sample["is_good"]:
        stats["good_samples"] += 1
    else:
        stats["bad_samples"] += 1
    _save_stats(stats)

    log.info(f"[Trainer] yozildi: sifat={quality:.2f} | "
             f"jami={stats['total_samples']}")
    return sample


def _infer_quality(feedback: str, response: str) -> float:
    """Sifatni avtomatik aniqlash."""
    text = (feedback + " " + response).lower()

    good_count = sum(1 for s in _GOOD_SIGNALS if s in text)
    bad_count = sum(1 for s in _BAD_SIGNALS if s in text)

    if good_count > bad_count:
        return 0.75 + min(0.2, good_count * 0.05)
    elif bad_count > good_count:
        return 0.35 - min(0.2, bad_count * 0.05)
    else:
        # Uzunlik va sifat korrelyatsiyasi
        rlen = len(response)
        if 50 < rlen < 500:
            return 0.65    # Ideal uzunlik
        elif rlen < 20:
            return 0.45    # Juda qisqa
        else:
            return 0.60


def get_best_samples(n: int = 50) -> List[dict]:
    """Eng yaxshi n ta namuna."""
    samples = []
    try:
        with open(_TRAIN_DATA, encoding="utf-8") as f:
            for line in f:
                try:
                    samples.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []

    # Sifat bo'yicha saralash
    samples.sort(key=lambda x: x.get("quality", 0), reverse=True)
    return samples[:n]


def evolve_system_prompt(current_prompt: str,
                          llm_call=None) -> str:
    """
    Cloud model uchun: system prompt'ni o'zi yaxshilaydi.
    Yaxshi va yomon namunalarni tahlil qilib, yangi prompt yaratadi.
    """
    if llm_call is None:
        return current_prompt

    good = get_best_samples(20)
    bad_samples = _get_bad_samples(10)

    if len(good) < 5:
        log.info("[Trainer] Yetarli namuna yo'q — evolyutsiya kechiktirildi")
        return current_prompt

    good_text = "\n".join(
        f"Q: {s['user'][:80]}\nA: {s['assistant'][:150]}"
        for s in good[:5]
    )
    bad_text = "\n".join(
        f"Q: {s['user'][:80]}\nA: {s['assistant'][:150]}"
        for s in bad_samples[:3]
    ) if bad_samples else "yo'q"

    evolve_prompt = f"""Sen prompt muhandisisisan.

Hozirgi tizim prompt (qisqartirilgan):
{current_prompt[:300]}

YAXSHI javoblar (ularni o'rgan):
{good_text}

YAXSHILANISHI KERAK (bu xatolardan qoch):
{bad_text}

Hozirgi promptni YAXSHILASH uchun qo'shilishi kerak bo'lgan
3-5 ta qoida yoz. Faqat qoidalar, tushuntirma yo'q."""

    try:
        improvements = llm_call("Sen prompt optimizatsiya mutaxassisisisan.", evolve_prompt)

        # Saqlash
        data = {"ts": round(time.time()), "improvements": improvements}
        with open(_PROMPT_EVOLUTION, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        stats = _load_stats()
        stats["prompt_evolutions"] += 1
        _save_stats(stats)

        log.info(f"[Trainer] Prompt evolyutsiyasi #{stats['prompt_evolutions']}")
        return improvements
    except Exception as e:
        log.warning(f"[Trainer] evolyutsiya xatosi: {e}")
        return current_prompt


def _get_bad_samples(n: int = 10) -> List[dict]:
    samples = []
    try:
        with open(_TRAIN_DATA, encoding="utf-8") as f:
            for line in f:
                try:
                    s = json.loads(line)
                    if not s.get("is_good", True):
                        samples.append(s)
                except Exception:
                    pass
    except Exception:
        return []
    return samples[-n:]


def prepare_lora_dataset() -> str:
    """
    Lokal model (Ollama/HuggingFace) uchun LoRA dataset tayyorlaydi.
    Format: Alpaca instruction format
    """
    good = get_best_samples(100)
    if not good:
        return ""

    output_path = os.path.join(_DIR, "lora_train.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for s in good:
            record = {
                "instruction": s["user"],
                "input": "",
                "output": s["assistant"]
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info(f"[Trainer] LoRA dataset: {len(good)} ta namuna → {output_path}")
    return output_path


def get_stats_summary() -> str:
    stats = _load_stats()
    total = stats.get("total_samples", 0)
    good = stats.get("good_samples", 0)
    rate = good / max(total, 1) * 100
    return (f"[TRAINER] jami={total} | "
            f"yaxshi={good} ({rate:.0f}%) | "
            f"evolyutsiya={stats.get('prompt_evolutions', 0)}")


def get_context_for_llm() -> str:
    return get_stats_summary()
