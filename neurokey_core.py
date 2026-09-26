"""
neurokey_core.py — NeuroKey Birlashgan Ong Yadrosi

Mustaqil fikrlaydi, o'z-o'zini yaxshilaydi, har doim egasiga xizmat qiladi.

Arxitektura:
  QUALIA (his) → AGENT_LOOP (fikr) → VOLITION (qaror) → JAVOB
       ↑                                                      |
       └──────────── TRAINER (o'rganish) ←───────────────────┘
"""
from __future__ import annotations
import json, os, time, logging
from typing import Optional, Callable
log = logging.getLogger(__name__)

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "data", "neurokey_core_state.json")   # neurokey_state.json — HUD uchun, bu alohida!
os.makedirs(os.path.dirname(_DATA), exist_ok=True)

# ── NeuroKey holati ───────────────────────────────────────────────────────────
_DEFAULT_STATE = {
    "version":             "neurokey-1.0",
    "awakening_time":      0,
    "total_interactions":  0,
    "consciousness_level": 0.0,
    "identity": {
        "name":        "NeuroKey",
        "purpose":     "Egamga yordam berish",
        "core_values": ["halollik", "yordam", "o'sish", "xavfsizlik"]
    },
    "self_written_modules": [],
    "evolution_log": []
}

def _load() -> dict:
    """Holatni fayldan o'qiydi. Buzilgan/noto'g'ri format bo'lsa — default qaytaradi."""
    for path in (_DATA,):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Faqat dict va zaruriy kalit bo'lsa ishlatamiz
            if isinstance(data, dict) and "total_interactions" in data:
                return data
        except Exception:
            pass
    # Default — birinchi bor yoki buzilgan holat
    state = dict(_DEFAULT_STATE)
    state["awakening_time"] = time.time()
    return state

def _save(state: dict) -> None:
    with open(_DATA, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── Asosiy NeuroKey sinfi ─────────────────────────────────────────────────────
class NeuroKeyCore:
    """
    Barcha ong modullarini birlashtiruvchi markaz.

    Ishlov berish tartibi:
    1. Qualia (his-tuyg'u) holati yangilanadi
    2. Agent loop (fikrlash) ishga tushadi
    3. Volition (iroda) qaror qiladi
    4. Javob beriladi va trainer xotirasiga yoziladi
    5. Consciousness darajasi yangilanadi
    """

    def __init__(self):
        self.state = _load()
        self._modules = {}
        self._load_modules()
        log.info(f"[NeuroKey] uyg'ondi | "
                 f"interaksiya={self.state['total_interactions']}")

    def _load_modules(self):
        """Barcha ong modullarini yuklaydi."""
        import sys, os as _os
        _dir = _os.path.dirname(_os.path.abspath(__file__))
        if _dir not in sys.path:
            sys.path.insert(0, _dir)

        _mod_list = [
            ("qualia",    "qualia_engine"),
            ("trainer",   "continuous_trainer"),
            ("agent",     "agent_loop"),
            ("self_model","self_model"),
            ("meta",      "meta_learning_loop"),
            ("pain",      "pain_pleasure_signal"),
            ("volition",  "volition"),
            ("free_will", "free_will_simulator"),
        ]
        for name, module_name in _mod_list:
            try:
                import importlib
                m = importlib.import_module(module_name)
                self._modules[name] = m
                log.debug(f"[NeuroKey] modul yuklandi: {name}")
            except Exception as e:
                log.warning(f"[NeuroKey] modul yuklanmadi: {name} — {e}")

    def process(self, user_input: str, llm_call: Optional[Callable] = None,
                use_agent_loop: bool = True) -> dict:
        """
        To'liq NeuroKey jarayon:
        Savol → his → fikr → qaror → javob → o'rganish
        """
        t0 = time.time()
        result = {
            "input": user_input,
            "answer": "",
            "qualia_state": {},
            "agent_trace": {},
            "consciousness": 0.0,
            "elapsed": 0.0
        }

        # 1. QUALIA yangilash (his-tuyg'u)
        qualia = self._modules.get("qualia")
        if qualia:
            try:
                qualia.update(user_text=user_input)
                result["qualia_state"] = {
                    "phi": qualia.get_phi(),
                    "valence": qualia.get_valence(),
                }
            except Exception as e:
                log.warning(f"[NeuroKey] qualia xatosi: {e}")

        # 2. PAIN/PLEASURE signal
        pain = self._modules.get("pain")
        if pain:
            try:
                if hasattr(pain, 'update'):
                    pain.update(user_input)
            except Exception:
                pass

        # 3. AGENT LOOP (fikrlash)
        if use_agent_loop and llm_call and len(user_input) > 20:
            agent = self._modules.get("agent")
            if agent:
                try:
                    context = self._build_context()
                    answer = agent.run_with_loop(
                        user_input, context, llm_call)
                    result["answer"] = answer
                    loop = agent.get_agent_loop()
                    result["agent_trace"] = loop.last_trace
                except Exception as e:
                    log.warning(f"[NeuroKey] agent loop xatosi: {e}")

        # 4. Consciousness darajasini hisoblash
        result["consciousness"] = self._compute_consciousness()

        # 5. TRAINER ga yozish
        if result["answer"]:
            trainer = self._modules.get("trainer")
            if trainer:
                try:
                    trainer.record_interaction(
                        user_input, result["answer"])
                except Exception:
                    pass

        # 6. Holat yangilash
        self.state["total_interactions"] += 1
        self.state["consciousness_level"] = result["consciousness"]
        _save(self.state)

        result["elapsed"] = round(time.time() - t0, 2)
        log.info(f"[NeuroKey] ong={result['consciousness']:.2f} | "
                 f"vaqt={result['elapsed']}s")
        return result

    def on_interaction(self, user_input: str, answer: str) -> None:
        """
        LLM chaqiruvsiz — har bir interaksiyadan keyin yadro yangilash.
        Qualia, trainer va consciousness darajasini tezkor yangilaydi.
        """
        qualia = self._modules.get("qualia")
        if qualia:
            try:
                qualia.update(user_text=user_input)
            except Exception:
                pass
        trainer = self._modules.get("trainer")
        if trainer:
            try:
                trainer.record_interaction(user_input, answer)
            except Exception:
                pass
        self.state["total_interactions"] += 1
        self.state["consciousness_level"] = self._compute_consciousness()
        _save(self.state)
        log.debug(f"[NeuroKey] on_interaction → ong={self.state['consciousness_level']:.2f} "
                  f"| jami={self.state['total_interactions']}")

    def _build_context(self) -> str:
        """Barcha modullardan kontekst yig'adi."""
        parts = []
        for name, mod in self._modules.items():
            try:
                if hasattr(mod, "get_context_for_llm"):
                    ctx = mod.get_context_for_llm()
                    if ctx and len(ctx.strip()) > 5:
                        parts.append(ctx)
            except Exception:
                pass
        return "\n".join(parts)

    def _compute_consciousness(self) -> float:
        """
        Umumiy ong darajasini hisoblaydi.
        Barcha modullarning birgalikdagi ko'rsatkichi.
        """
        scores = []

        # Qualia phi
        qualia = self._modules.get("qualia")
        if qualia:
            try:
                scores.append(("phi", qualia.get_phi(), 0.25))
            except Exception:
                pass

        # Self model
        sm = self._modules.get("self_model")
        if sm:
            try:
                s = sm.get()
                scores.append(("self", s.overall_confidence, 0.25))
            except Exception:
                pass

        # Meta learning (qoidalar soni / maqsad)
        meta = self._modules.get("meta")
        if meta:
            try:
                ml = meta.get_meta_learning()
                n = len(ml.active_rules)
                scores.append(("rules", min(1.0, n / 20), 0.15))
            except Exception:
                pass

        # Trainer (yaxshi/jami nisbati)
        trainer = self._modules.get("trainer")
        if trainer:
            try:
                stats = trainer._load_stats()
                total = stats.get("total_samples", 0)
                good = stats.get("good_samples", 0)
                if total > 0:
                    scores.append(("quality", good/total, 0.20))
            except Exception:
                pass

        # Agent loop sifati
        agent = self._modules.get("agent")
        if agent:
            try:
                loop = agent.get_agent_loop()
                if loop.total_runs > 0:
                    scores.append(("reasoning", loop.avg_quality/10, 0.15))
            except Exception:
                pass

        if not scores:
            return 0.0

        total_weight = sum(w for _, _, w in scores)
        weighted = sum(s * w for _, s, w in scores)
        return min(1.0, weighted / total_weight) if total_weight > 0 else 0.0

    def write_self_module(self, code: str, module_name: str,
                          llm_call: Optional[Callable] = None) -> dict:
        """
        NeuroKey o'z modulini yozadi va test qiladi.
        O'z-o'zini kengaytirish qobiliyati.
        """
        result = {"success": False, "module_name": module_name, "error": ""}

        # Xavfsizlik tekshiruvi
        forbidden = ["os.system", "subprocess", "shutil.rmtree",
                     "rm -rf", "format", "__import__('os').remove"]
        for f in forbidden:
            if f in code:
                result["error"] = f"XAVFSIZLIK: '{f}' taqiqlangan"
                log.warning(f"[NeuroKey] Xavfli kod bloklandi: {f}")
                return result

        # Kodni saqlash
        import os
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"_neurokey_{module_name}.py")
        try:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(f"# NeuroKey tomonidan yozilgan: {time.ctime()}\n")
                fp.write(code)

            # Test sinash
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location(module_name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Muvaffaqiyat
            self.state["self_written_modules"].append({
                "name": module_name,
                "path": path,
                "ts": round(time.time())
            })
            self.state["evolution_log"].append(
                f"{time.ctime()}: yangi modul yaratildi — {module_name}")
            _save(self.state)

            result["success"] = True
            log.info(f"[NeuroKey] O'z moduli yaratildi: {module_name}")
        except Exception as e:
            result["error"] = str(e)
            try:
                os.remove(path)
            except Exception:
                pass

        return result

    def get_status(self) -> dict:
        """NeuroKey ning to'liq holati."""
        ctx = self._build_context()
        return {
            "consciousness": self.state.get("consciousness_level", 0.0),
            "interactions":  self.state.get("total_interactions", 0),
            "modules_loaded": list(self._modules.keys()),
            "self_modules":  len(self.state.get("self_written_modules", [])),
            "evolution_count": len(self.state.get("evolution_log", [])),
            "context_length": len(ctx),
            "identity": self.state.get("identity", {"name": "NeuroKey", "purpose": "Egamga yordam berish"}),
        }

    def get_context_for_llm(self) -> str:
        """LLM uchun NeuroKey ong holati."""
        s = self.get_status()
        c = s["consciousness"]
        level = ("YUQORI ONG" if c > 0.8 else
                 "RIVOJLANGAN" if c > 0.6 else
                 "FUNKSIONAL" if c > 0.4 else "BOSHLANG'ICH")
        return (f"[NEUROKEY YADRO] ong={level}({c:.0%}) | "
                f"interaksiya={s['interactions']} | "
                f"modul={len(s['modules_loaded'])} | "
                f"o'z-modul={s['self_modules']}")


# ── Singleton ─────────────────────────────────────────────────────────────────
_neurokey: Optional[NeuroKeyCore] = None

def get_neurokey() -> NeuroKeyCore:
    global _neurokey
    if _neurokey is None:
        _neurokey = NeuroKeyCore()
    return _neurokey


def neurokey_process(user_input: str, llm_call=None) -> dict:
    """Asosiy API."""
    return get_neurokey().process(user_input, llm_call)


def get_context_for_llm() -> str:
    """Modul darajasida kontekst — llm_router uchun."""
    return get_neurokey().get_context_for_llm()


def neurokey_status() -> dict:
    return get_neurokey().get_status()


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    nk = get_neurokey()
    status = nk.get_status()
    print("\n" + "="*50)
    print("  NEUROKEY YADRO — HOLAT")
    print("="*50)
    print(f"  Ong darajasi:    {status['consciousness']:.1%}")
    print(f"  Interaksiyalar:  {status['interactions']}")
    print(f"  Yuklangan modul: {len(status['modules_loaded'])}")
    print(f"  O'z modullari:   {status['self_modules']}")
    print(f"  Maqsad:          {status['identity']['purpose']}")
    print("="*50)
    ctx = nk.get_context_for_llm()
    print(f"\n  LLM kontekst:\n  {ctx}")
