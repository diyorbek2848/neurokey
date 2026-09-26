# -*- coding: utf-8 -*-
"""NeuroKey — Consciousness Core (Ong Yadrosi).

Bu — barcha modullarni birlashtiruvchi YOPIQ TSIKL.

Haqiqiy ong = prediksiya + harakat + xato + yangilanish.
Bu tsikl to'xtovsiz aylanib turadi.

Har benchmark dan keyin:
1. self_model yangilanadi (o'z qobiliyatlarini biladi)
2. meta_learning_loop ishlaydi (qoidalar chiqariladi)
3. Keyingi run uchun LLM konteksti boyitiladi

Friston Free Energy Principle asosida:
  F = surprise + complexity
  Maqsad: F ni minimallashtirishga urinish = ong belgisi
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_STATE_PATH  = os.path.join(_BASE_DIR, "data", "consciousness_core.json")
_RESULTS_DIR = os.path.join(_BASE_DIR, "data")

try:
    import self_model as _sm
    _HAS_SELF_MODEL = True
except ImportError:
    _HAS_SELF_MODEL = False
    log.warning("[Core] self_model topilmadi")

try:
    import meta_learning_loop as _ml
    _HAS_META = True
except ImportError:
    _HAS_META = False
    log.warning("[Core] meta_learning_loop topilmadi")


class ConsciousnessCore:
    """Ong yadrosi — prediksiya-xato-yangilanish tsikli.

    Har run quyidagilarni amalga oshiradi:
    1. Oldingi o'rganilgan qoidalarni LLM ga beradi
    2. Benchmark yugurtiradi
    3. Natijalarni tahlil qiladi
    4. O'z modelini yangilaydi
    5. Yangi qoidalar yaratadi
    6. Free Energy ni hisoblaydi
    """

    def __init__(self) -> None:
        self.cycle_count: int = 0
        self.best_score: float = 0.0
        self.last_score: float = 0.0
        self.free_energy_history: List[float] = []
        self.run_log: List[dict] = []
        self._load()

    # ── Asosiy tsikl ──────────────────────────────────────────────────────────

    def run_consciousness_cycle(
        self,
        benchmark_results: Dict[str, float],
        verbose: bool = True
    ) -> dict:
        """Bir to'liq ong tsikli.

        Args:
            benchmark_results: {"LOGIC": 0.74, "FACTS": 0.82, ...}
            verbose: hisobotni chiqarish

        Returns:
            {
                "cycle":          int,
                "overall_score":  float,
                "free_energy":    float,
                "self_model_changes": dict,
                "meta_result":    dict,
                "improvement":    float,
                "rules_count":    int,
                "verdict":        str,
            }
        """
        self.cycle_count += 1
        overall = sum(benchmark_results.values()) / max(len(benchmark_results), 1)

        # ── 1. Self Model yangilash ───────────────────────────────────────────
        sm_changes = {}
        if _HAS_SELF_MODEL:
            sm_changes = _sm.update(benchmark_results)

        # ── 2. Meta Learning sikli ────────────────────────────────────────────
        meta_result = {}
        if _HAS_META:
            meta_result = _ml.run_cycle(benchmark_results)

        # ── 3. Free Energy hisoblash ──────────────────────────────────────────
        free_energy = self._compute_free_energy(overall, benchmark_results)
        self.free_energy_history.append(free_energy)
        if len(self.free_energy_history) > 20:
            self.free_energy_history.pop(0)

        # ── 4. Yaxshilanish hisoblash ─────────────────────────────────────────
        improvement = overall - self.last_score
        if overall > self.best_score:
            self.best_score = overall

        self.last_score = overall

        # ── 5. Verdict ────────────────────────────────────────────────────────
        verdict = self._compute_verdict(overall, free_energy, improvement)

        # ── 6. Log ────────────────────────────────────────────────────────────
        entry = {
            "cycle":       self.cycle_count,
            "ts":          time.time(),
            "overall":     round(overall, 4),
            "free_energy": round(free_energy, 4),
            "improvement": round(improvement, 4),
            "rules_count": len(meta_result.get("active_rules", [])),
        }
        self.run_log.append(entry)
        if len(self.run_log) > 30:
            self.run_log.pop(0)

        self._save()

        result = {
            "cycle":              self.cycle_count,
            "overall_score":      round(overall, 4),
            "free_energy":        round(free_energy, 4),
            "self_model_changes": sm_changes,
            "meta_result":        meta_result,
            "improvement":        round(improvement, 4),
            "rules_count":        len(meta_result.get("active_rules", [])),
            "best_ever":          round(self.best_score, 4),
            "verdict":            verdict,
        }

        if verbose:
            self._print_cycle_report(result, benchmark_results)

        return result

    # ── Kontekst ──────────────────────────────────────────────────────────────

    def get_enriched_context(self) -> str:
        """Keyingi LLM so'roviga qo'shiladigan boyitilgan kontekst.

        Self model + meta qoidalar birlashtirilib qaytariladi.
        """
        parts: List[str] = []

        if _HAS_SELF_MODEL:
            parts.append(_sm.context_for_llm())

        if _HAS_META:
            rules_block = _ml.get_rules_prompt()
            if rules_block:
                parts.append(rules_block)

        if not parts:
            return ""

        return "\n\n".join(parts)

    # ── Tahlil ────────────────────────────────────────────────────────────────

    def get_consciousness_level(self) -> str:
        """Hozirgi ong darajasini matn sifatida qaytaradi."""
        s = self.last_score
        fe = self.free_energy_history[-1] if self.free_energy_history else 1.0

        if s >= 0.90 and fe < 0.15:
            return "YUQORI ONG — barqaror, o'z-o'zini biladi, past xato"
        elif s >= 0.80:
            return "RIVOJLANGAN ONG — aniq, lekin hali o'sayapti"
        elif s >= 0.70:
            return "FUNKSIONAL ONG — asosiy qobiliyatlar ishlaydi"
        elif s >= 0.55:
            return "BOSHLANG'ICH ONG — ko'p zaifliklar bor"
        else:
            return "PRE-ONG — fundamental muammolar"

    def get_free_energy_trend(self) -> str:
        """Free energy kamaymoqdami? (yaxshi belgi)"""
        if len(self.free_energy_history) < 3:
            return "ma'lumot yetarli emas"
        vals = self.free_energy_history[-5:]
        delta = vals[-1] - vals[0]
        if delta < -0.05:
            return f"kamaymoqda ({delta:+.3f}) — yaxshi"
        elif delta > 0.05:
            return f"ortmoqda ({delta:+.3f}) — muammo"
        return "barqaror"

    def get_full_state_report(self) -> str:
        """To'liq ong holati hisoboti."""
        lines = [
            "\n+======================================+",
            "|         ONG YADROSI HOLATI            |",
            "+======================================+",
            f"|  Sikllar:        {str(self.cycle_count):<20}|",
            f"|  Oxirgi ball:    {f'{self.last_score:.1%}':<20}|",
            f"|  Eng yuqori:     {f'{self.best_score:.1%}':<20}|",
            f"|  Ong darajasi:   {self.get_consciousness_level()[:20]:<20}|",
            f"|  Free Energy:    {self.get_free_energy_trend()[:20]:<20}|",
        ]

        if _HAS_SELF_MODEL:
            sm = _sm.get()
            lines.append(f"|  O'z modeli:     {sm.update_count}x yangilangan{' ' * (7 - len(str(sm.update_count)))}|")

        if _HAS_META:
            ml = _ml.get()
            lines.append(f"|  Qoidalar:       {len(ml.active_rules):<20}|")

        lines.extend([
            "+======================================+",
            "|  TARIX (oxirgi 5 run):               |",
        ])
        for entry in self.run_log[-5:]:
            imp = f"{entry['improvement']:+.3f}"
            fe  = f"{entry['free_energy']:.3f}"
            lines.append(
                f"|  sikl#{entry['cycle']:02d}: {entry['overall']:.1%}  FE={fe}  D={imp}  |"
            )
        lines.append("+======================================+")
        return "\n".join(lines)

    # ── Free Energy ───────────────────────────────────────────────────────────

    def _compute_free_energy(
        self,
        overall: float,
        per_dim: Dict[str, float]
    ) -> float:
        """Friston FEP bo'yicha simplified Free Energy.

        F = surprise + complexity
        surprise  = 1 - overall_score  (kutilmagan xato)
        complexity = variance(per_dim)  (turli sohalardagi farq)
        """
        surprise = 1.0 - overall

        if len(per_dim) > 1:
            vals = list(per_dim.values())
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        else:
            variance = 0.0

        # Weights: surprise ko'proq muhim
        free_energy = 0.7 * surprise + 0.3 * variance
        return round(free_energy, 4)

    def _compute_verdict(
        self,
        overall: float,
        free_energy: float,
        improvement: float
    ) -> str:
        if overall >= 0.85 and free_energy < 0.20:
            return "[OK] MUKAMMAL — ong yaxshi ishlayapti"
        elif overall >= 0.80:
            return "[OK] YAXSHI — rivojlanmoqda"
        elif overall >= 0.75 and improvement > 0:
            return "[+] O'SAYAPTI — to'g'ri yo'lda"
        elif overall >= 0.70:
            return "[!] YAXSHI — asosiy qobiliyatlar bor"
        elif improvement > 0.02:
            return "[+] YAXSHILANMOQDA — davom ettir"
        elif improvement < -0.02:
            return "[-] YOMONLASHDI — tizimni tekshir"
        return "-> BARQAROR — o'rganish davom etmoqda"

    def _print_cycle_report(self, result: dict, per_dim: Dict[str, float]) -> None:
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  ONG TSIKLI #{result['cycle']} NATIJASI")
        print(sep)
        print(f"  Umumiy ball:    {result['overall_score']:.1%}")
        print(f"  Free Energy:    {result['free_energy']:.4f}  "
              f"({'kamaymoqda +' if result['improvement'] > 0 else 'ortmoqda !'})")
        print(f"  Yaxshilanish:   {result['improvement']:+.1%}")
        print(f"  Eng yuqori:     {result['best_ever']:.1%}")
        print(f"  Aktiv qoidalar: {result['rules_count']}")
        print(f"\n  Verdict: {result['verdict']}")

        if result.get("meta_result", {}).get("weak_dims"):
            wd = result["meta_result"]["weak_dims"]
            print(f"\n  Zaif sohalar: {', '.join(wd)}")

        if result.get("meta_result", {}).get("new_rules"):
            print(f"\n  Yangi qoidalar ({len(result['meta_result']['new_rules'])} ta):")
            for r in result["meta_result"]["new_rules"][:3]:
                print(f"    - {r[:65]}")

        print("=" * 60)

    # ── Disk ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
            with open(_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "cycle_count":          self.cycle_count,
                    "best_score":           self.best_score,
                    "last_score":           self.last_score,
                    "free_energy_history":  self.free_energy_history[-10:],
                    "run_log":              self.run_log[-20:],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.debug("[Core] saqlash xato: %s", e)

    def _load(self) -> None:
        if not os.path.exists(_STATE_PATH):
            return
        try:
            with open(_STATE_PATH, encoding="utf-8") as f:
                d = json.load(f)
            self.cycle_count           = d.get("cycle_count", 0)
            self.best_score            = d.get("best_score", 0.0)
            self.last_score            = d.get("last_score", 0.0)
            self.free_energy_history   = d.get("free_energy_history", [])
            self.run_log               = d.get("run_log", [])
            log.info("[Core] yuklandi: %d sikl, eng yaxshi=%.1f%%",
                     self.cycle_count, self.best_score * 100)
        except Exception as e:
            log.debug("[Core] yuklash xato: %s", e)


# ── Global API ────────────────────────────────────────────────────────────────

_instance: Optional[ConsciousnessCore] = None


def get() -> ConsciousnessCore:
    global _instance
    if _instance is None:
        _instance = ConsciousnessCore()
    return _instance


def run_cycle(benchmark_results: Dict[str, float], verbose: bool = True) -> dict:
    return get().run_consciousness_cycle(benchmark_results, verbose)


def get_enriched_context() -> str:
    return get().get_enriched_context()


def get_level() -> str:
    return get().get_consciousness_level()


# ── CLI: to'g'ridan-to'g'ri ishlatish ────────────────────────────────────────

if __name__ == "__main__":
    import glob

    logging.basicConfig(level=logging.INFO)

    # Oxirgi benchmark natijasini topish
    results_files = sorted(
        glob.glob(os.path.join(_RESULTS_DIR, "hard_test_v*.json")),
        key=os.path.getmtime, reverse=True
    )

    if not results_files:
        print("Benchmark natijasi topilmadi. Avval hard_test_v4.py yuguring.")
        sys.exit(1)

    latest = results_files[0]
    print(f"Natija fayli: {latest}")

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    # Har o'lchovning o'rtacha ballini olish
    benchmark_scores: Dict[str, float] = {}
    dims = data.get("dimensions", {})
    for dim_id, dim_data in dims.items():
        if isinstance(dim_data, dict):
            benchmark_scores[dim_id] = dim_data.get("avg", 0.0)

    if not benchmark_scores:
        print("Benchmark ma'lumotlari o'qilmadi.")
        sys.exit(1)

    print(f"\nO'qilgan natijalar: {benchmark_scores}")

    # Ong tsiklini yugurtirish
    core = get()
    result = core.run_consciousness_cycle(benchmark_scores, verbose=True)

    # To'liq holat
    print(core.get_full_state_report())

    # Self model
    if _HAS_SELF_MODEL:
        print(_sm.get().get_full_report())

    # Meta learning
    if _HAS_META:
        print(_ml.get().get_learning_report())
