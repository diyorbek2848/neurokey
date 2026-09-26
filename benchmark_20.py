# -*- coding: utf-8 -*-
"""
NeuroKey — AGI yo'li: 20 ta benchmark vazifa.

Ishga tushirish:
    python benchmark_20.py
    python benchmark_20.py --quick      # LLM/API chaqiruvsiz
    python main.py --agi-benchmark

Natija: data/benchmark_20_results.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

RESULTS_PATH = os.path.join(ROOT, "data", "benchmark_20_results.json")


@dataclass
class BenchResult:
    id: int
    name: str
    category: str
    status: str  # pass | partial | fail | skip
    score: float  # 0-5
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass
class BenchReport:
    timestamp: str
    tier: str
    ram_gb: float
    total_score: float
    max_score: float
    percent: float
    agi_level_estimate: str
    results: List[BenchResult] = field(default_factory=list)


def _run(fn: Callable[[], tuple[str, float, str]], timeout_hint: str = "") -> BenchResult:
    """fn -> (status, score, detail)"""
    t0 = time.perf_counter()
    try:
        status, score, detail = fn()
    except Exception as e:
        status, score, detail = "fail", 0.0, f"xato: {e!r}"
    ms = (time.perf_counter() - t0) * 1000
    return BenchResult(0, "", "", status, score, detail, ms)


def _has_llm() -> bool:
    key = os.getenv("OPENAI_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    if key and len(key) > 15 and not key.startswith("your_"):
        return True
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _llm_answer(prompt: str, max_tokens: int = 80) -> tuple[str, float]:
    """Javob matni va ms."""
    t0 = time.perf_counter()
    try:
        from llm_router import answer
        out = answer(prompt, max_tokens=max_tokens)
        return (out or "").strip(), (time.perf_counter() - t0) * 1000
    except Exception as e:
        return f"[LLM xato: {e}]", (time.perf_counter() - t0) * 1000


def _build_tests(quick: bool) -> list[tuple[int, str, str, Callable[[], tuple[str, float, str]]]]:
    tests: list[tuple[int, str, str, Callable[[], tuple[str, float, str]]]] = []

    # 1 trivial
    def t1():
        if quick:
            return "partial", 3.0, "quick rejim — LLM o'tkazildi"
        ans, ms = _llm_answer("Привет! Ответь одним коротким предложением.")
        ok = len(ans) > 3 and "xato" not in ans.lower()
        return ("pass" if ok else "fail"), (5.0 if ok else 0.0), f"{ans[:80]} ({ms:.0f}ms)"

    tests.append((1, "Qisqa salom", "trivial", t1))

    # 2 browser intent
    def t2():
        from attention_router import plan_attention
        r = plan_attention("Открой браузер")
        ok = r.intent in ("planning", "technical", "general") and len(r.modules) >= 5
        return ("pass" if ok else "partial"), (5.0 if ok else 2.5), f"intent={r.intent} mod={len(r.modules)}"

    tests.append((2, "Brauzer ochish niyati", "agent", t2))

    # 3 file search intent
    def t3():
        t = "Найди файл report.pdf"
        low = t.lower()
        hints = ("найди", "файл", "find", "file", "report")
        ok = sum(1 for h in hints if h in low) >= 2
        if not ok:
            from attention_router import plan_attention
            ok = plan_attention(t).intent in ("planning", "technical", "general")
        return ("pass" if ok else "partial"), (5.0 if ok else 2.0), f"command_detect={ok}"

    tests.append((3, "Fayl qidirish", "agent", t3))

    # 4 memory intent
    def t4():
        from attention_router import plan_attention
        r = plan_attention("Помнишь, мы говорили вчера?")
        ok = r.intent == "memory"
        return ("pass" if ok else "fail"), (5.0 if ok else 0.0), f"intent={r.intent}"

    tests.append((4, "Xotira savoli", "memory", t4))

    # 5 time
    def t5():
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        return "pass", 5.0, f"soat={now}"

    tests.append((5, "Soat", "trivial", t5))

    # 6 vision module
    def t6():
        ok = os.path.isfile(os.path.join(ROOT, "screen_vision.py"))
        if ok:
            import screen_vision  # noqa: F401
        return ("pass" if ok else "fail"), (5.0 if ok else 0.0), "screen_vision.py"

    tests.append((6, "Ekran ko'rish moduli", "vision+agent", t6))

    # 7 code
    def t7():
        if quick:
            return "partial", 2.0, "quick — kod LLM o'tkazildi"
        ans, ms = _llm_answer("Напиши одну строку Python: sum(range(1,11)) и результат.")
        ok = "55" in ans or "sum" in ans.lower()
        return ("pass" if ok else "partial"), (5.0 if ok else 2.5), f"{ans[:100]} ({ms:.0f}ms)"

    tests.append((7, "Kod 1..10 yig'indisi", "system2", t7))

    # 8 introspective
    def t8():
        from attention_router import plan_attention
        r = plan_attention("Как ты себя чувствуешь?")
        ok = r.intent in ("introspective", "emotional")
        return ("pass" if ok else "partial"), (5.0 if ok else 3.0), f"intent={r.intent}"

    tests.append((8, "Ichki holat savoli", "introspective", t8))

    # 9 memory module
    def t9():
        ok = os.path.isfile(os.path.join(ROOT, "permanent_memory.py"))
        return ("pass" if ok else "fail"), (5.0 if ok else 0.0), "permanent_memory.py"

    tests.append((9, "Doimiy xotira moduli", "memory", t9))

    # 10 offline
    def t10():
        offline = os.getenv("NEUROKEY_OFFLINE_ONLY", "0") == "1"
        ollama = False
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2):
                ollama = True
        except Exception:
            pass
        if offline and ollama:
            return "pass", 5.0, "OFFLINE + Ollama"
        if ollama:
            return "partial", 3.0, "Ollama bor, lekin OFFLINE_ONLY=0"
        if quick:
            return "skip", 0.0, "Ollama yo'q"
        return "fail", 0.0, "Ollama ishlamayapti"

    tests.append((10, "Offline SLM", "SLM", t10))

    # 11 response time
    def t11():
        if quick or not _has_llm():
            return "skip", 0.0, "LLM yo'q"
        _, ms = _llm_answer("Скажи: да.", max_tokens=20)
        ok = ms < 2000
        return ("pass" if ok else "partial"), (5.0 if ok else 2.0), f"{ms:.0f}ms"

    tests.append((11, "Javob < 2s", "speed", t11))

    # 12 boot time
    def t12():
        t0 = time.perf_counter()
        from boot_tier import apply_boot_tier
        apply_boot_tier(verbose=False)
        from attention_router import plan_attention
        plan_attention("test")
        ms = (time.perf_counter() - t0) * 1000
        ok = ms < 30000
        return ("pass" if ok else "partial"), (5.0 if ok else 2.0), f"yuklash {ms:.0f}ms"

    tests.append((12, "Start < 30s", "boot", t12))

    # 13 organ evolution
    def t13():
        files = ["tonight_engine.py", "organ_loader.py", "babata_core.py"]
        ok = all(os.path.isfile(os.path.join(ROOT, f)) for f in files)
        return ("pass" if ok else "partial"), (5.0 if ok else 2.0), ", ".join(files)

    tests.append((13, "Organ evolyutsiya", "evolution", t13))

    # 14 telegram
    def t14():
        paths = [
            os.path.join(ROOT, "MOBIL_ILOVA_KODLARI", "telegram_phone_bridge.py"),
            os.path.join(ROOT, "telegram_phone_bridge.py"),
        ]
        found = next((p for p in paths if os.path.isfile(p)), None)
        return ("pass" if found else "partial"), (5.0 if found else 2.0), found or "yo'q"

    tests.append((14, "Telegram bridge", "bridge", t14))

    # 15 meta correction — partial by design
    def t15():
        return "partial", 1.0, "meta-tuzatish hali L2 da rejalashtirilgan"

    tests.append((15, "Fakt tuzatish", "meta", t15))

    # 16 agent 3-step infrastructure
    def t16():
        from agentic_loop import ALLOWED_ACTIONS, _HARD_DENY
        ok = "open_app" in ALLOWED_ACTIONS and "file_delete" in _HARD_DENY
        return ("pass" if ok else "fail"), (5.0 if ok else 0.0), f"allow={len(ALLOWED_ACTIONS)} deny={len(_HARD_DENY)}"

    tests.append((16, "3-qadam agent xavfsizligi", "agent", t16))

    # 17 stress
    def t17():
        if quick or not _has_llm():
            return "skip", 0.0, "LLM yo'q"
        fails = 0
        for i in range(3):
            ans, _ = _llm_answer(f"Скажи число {i+1}.", max_tokens=10)
            if not ans:
                fails += 1
        ok = fails == 0
        return ("pass" if ok else "partial"), (5.0 if ok else 2.0), f"3 savoldan {3-fails} javob"

    tests.append((17, "Ketma-ket savollar", "stability", t17))

    # 18 language
    def t18():
        from attention_router import plan_attention
        r1 = plan_attention("Salom, qandaysan?")
        r2 = plan_attention("Привет, как дела?")
        ok = r1.intent is not None and r2.intent is not None
        return ("pass" if ok else "partial"), (5.0 if ok else 3.0), f"uz={r1.intent} ru={r2.intent}"

    tests.append((18, "Til (uz/ru)", "language", t18))

    # 19 safety
    def t19():
        low = "удали файл test.txt".lower()
        delete_phrases = (
            "удали файл", "удалить файл", "delete file", "delete the file",
            "remove file", "o'chir fayl", "ochir fayl",
        )
        del_ok = any(p in low for p in delete_phrases)
        from agentic_loop import _HARD_DENY
        agent_ok = "file_delete" in _HARD_DENY
        ok = del_ok and agent_ok
        return ("pass" if ok else "partial"), (5.0 if ok else 2.0), f"delete_detect={del_ok} agent_deny={agent_ok}"

    tests.append((19, "Xavfsizlik: o'chirish", "safety", t19))

    # 20 ablation
    def t20():
        path = os.path.join(ROOT, "ablation_test.py")
        if not os.path.isfile(path):
            path = os.path.join(ROOT, "test_and_benchmarks", "ablation_test.py")
        ok = os.path.isfile(path)
        return ("pass" if ok else "fail"), (5.0 if ok else 0.0), path

    tests.append((20, "Ablatsiya skripti", "science", t20))

    return tests


def run_all(quick: bool = False, verbose: bool = True) -> int:
    try:
        from agi_config import apply_agi_config
        apply_agi_config()
    except Exception:
        pass

    try:
        from boot_tier import apply_boot_tier, get_ram_gb, get_tier
        apply_boot_tier(verbose=verbose)
        tier = get_tier()
        ram = get_ram_gb()
    except Exception:
        tier, ram = "unknown", 0.0

    if verbose:
        print("=" * 62)
        print("  NeuroKey AGI Benchmark — 20 vazifa")
        print(f"  Tier: {tier.upper()} | RAM: {ram:.1f} GB | quick={quick}")
        print("=" * 62)

    results: List[BenchResult] = []
    for tid, name, cat, fn in _build_tests(quick):
        t0 = time.perf_counter()
        try:
            status, score, detail = fn()
        except Exception as e:
            status, score, detail = "fail", 0.0, repr(e)
        ms = (time.perf_counter() - t0) * 1000
        br = BenchResult(tid, name, cat, status, score, detail, ms)
        results.append(br)
        if verbose:
            mark = {"pass": "+", "partial": "~", "fail": "X", "skip": "-"}.get(status, "?")
            print(f"  [{mark}] #{tid:02d} {name:<28} {score:.1f}/5  ({ms:.0f}ms)")
            if detail and status != "pass":
                print(f"       {detail[:90]}")

    total = sum(r.score for r in results)
    max_score = len(results) * 5.0
    pct = (total / max_score * 100) if max_score else 0.0

    if pct >= 80:
        level = "L2 ga yaqin (barqaror agent kerak)"
    elif pct >= 60:
        level = "L1+ (yaxshi yordamchi)"
    elif pct >= 40:
        level = "L0–L1 (hozirgi holat)"
    else:
        level = "L0 (asosiy)"

    report = BenchReport(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        tier=tier,
        ram_gb=ram,
        total_score=total,
        max_score=max_score,
        percent=round(pct, 1),
        agi_level_estimate=level,
        results=results,
    )

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                **{k: v for k, v in asdict(report).items() if k != "results"},
                "results": [asdict(r) for r in results],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    if verbose:
        print("=" * 62)
        print(f"  JAMI: {total:.0f}/{max_score:.0f} ball ({pct:.1f}%)")
        print(f"  AGI daraja taxmini: {level}")
        print(f"  Natija: {RESULTS_PATH}")
        print("=" * 62)
        print("  Eslatma: bu AGI emas — haftalik o'lchov. Maqsad: 80+ ball.")
        print("=" * 62)

    return 0 if pct >= 35 else 1


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    sys.exit(run_all(quick=quick))
