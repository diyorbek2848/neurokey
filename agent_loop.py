"""
agent_loop.py — NeuroKey Reasoning Engine
Haqiqiy "o'ylash" loop: Plan → Think → Critic → Answer
Mustaqil fikrlaydi, NeuroKey kabi yordam beradi.
"""
from __future__ import annotations
import json, logging, time
from typing import Optional
log = logging.getLogger(__name__)

# ── Prompt shablonlari ────────────────────────────────────────────────────────

_PLANNER_PROMPT = """Sen fikrlash rejasini tuzuvchisan.
Savol yoki vazifa: {question}

Quyidagilarni hal qil:
1. Bu savolning ASOSIY mohiyati nima?
2. Javob berish uchun qanday bosqichlar kerak?
3. Qanday xatolardan qochish kerak?

Faqat REJA yoz — 3-5 qator, qisqa."""

_THINKER_PROMPT = """Sen chuqur fikrlovchisan.
Savol: {question}
Reja: {plan}
Kontekst: {context}

Bosqichma-bosqich o'yla. Har bosqichni [FIKR: ...] bilan belgi.
So'ng [XULOSA: ...] bilan tugat."""

_CRITIC_PROMPT = """Sen tanqidchi aqisan.
Original savol: {question}
Fikrlash natijasi: {thinking}

Tekshir:
- Savol to'liq javoblanganimdi? (ha/yo'q)
- Biron xato bormi?
- Qisqartirish kerakmi?

[BAHO: x/10] va [TUZATISH: ...] (kerak bo'lsa)"""

_SYNTHESIZER_PROMPT = """Sen yakuniy javob beruvchisan.
Savol: {question}
Fikr: {thinking}
Tanqid: {critique}

Hozir YAKUNIY, ANIQ javob ber. Ortiqcha so'z yo'q."""


# ── Asosiy klass ─────────────────────────────────────────────────────────────

class AgentLoop:
    """
    4 bosqichli fikrlash loop:
    PLAN → THINK → CRITIC → SYNTHESIZE

    Har bosqich alohida LLM call — haqiqiy fikrlash simulyatsiyasi.
    """

    def __init__(self, fast_mode: bool = False):
        self.fast_mode = fast_mode          # True = faqat 1 bosqich (tez)
        self.last_trace: dict = {}          # Oxirgi fikrlash izi
        self.total_runs = 0
        self.avg_quality = 0.0

    def run(self, question: str, context: str = "",
            llm_call=None) -> str:
        """
        To'liq fikrlash loop.
        llm_call: callable(system, user) -> str
        """
        if llm_call is None:
            # Fallback — to'g'ridan-to'g'ri javob
            return question

        if self.fast_mode or len(question) < 30:
            # Qisqa savollar uchun — to'g'ri javob
            return llm_call("Sen aqlli yordamchisan.", question)

        t0 = time.time()

        # ── 1. PLAN ──────────────────────────────────────────────────────────
        plan = self._step(llm_call,
            "Sen strategik rejalashtiruvchisan. Qisqa va aniq bo'l.",
            _PLANNER_PROMPT.format(question=question))

        # ── 2. THINK ─────────────────────────────────────────────────────────
        thinking = self._step(llm_call,
            "Sen chuqur analitik fikrlovchisan.",
            _THINKER_PROMPT.format(
                question=question, plan=plan,
                context=context[:500] if context else "yo'q"))

        # ── 3. CRITIC ────────────────────────────────────────────────────────
        critique = self._step(llm_call,
            "Sen ob'ektiv tanqidchisan.",
            _CRITIC_PROMPT.format(question=question, thinking=thinking))

        # ── 4. SYNTHESIZE ────────────────────────────────────────────────────
        answer = self._step(llm_call,
            "Sen aniq va foydali javob beruvchisan.",
            _SYNTHESIZER_PROMPT.format(
                question=question, thinking=thinking, critique=critique))

        elapsed = time.time() - t0
        quality = self._parse_quality(critique)

        self.last_trace = {
            "question": question[:100],
            "plan": plan[:200],
            "thinking": thinking[:300],
            "critique": critique[:200],
            "answer": answer[:300],
            "quality": quality,
            "elapsed": round(elapsed, 2)
        }

        # EMA quality update
        self.total_runs += 1
        self.avg_quality = 0.85 * self.avg_quality + 0.15 * quality

        log.info(f"[AgentLoop] {elapsed:.1f}s | sifat={quality:.1f}/10 | o'rt={self.avg_quality:.1f}")
        return answer

    def _step(self, llm_call, system: str, user: str) -> str:
        try:
            result = llm_call(system, user)
            return result if result else ""
        except Exception as e:
            log.warning(f"[AgentLoop] bosqich xatosi: {e}")
            return ""

    def _parse_quality(self, critique: str) -> float:
        """[BAHO: x/10] dan sifat balini ajratadi."""
        import re
        m = re.search(r'\[BAHO[:\s]+(\d+(?:\.\d+)?)/10\]', critique, re.I)
        if m:
            return float(m.group(1))
        # Kritikada "yaxshi", "to'g'ri" bo'lsa — 8
        if any(w in critique.lower() for w in ['yaxshi','to\'g\'ri','correct','хорошо','верно']):
            return 8.0
        return 7.0

    def get_context_for_llm(self) -> str:
        if not self.last_trace:
            return ""
        q = self.last_trace.get('quality', 0)
        n = self.total_runs
        avg = self.avg_quality
        return f"[FIKRLASH LOOP] runs={n} | sifat={avg:.1f}/10 | oxirgi={q:.0f}/10"

    def get_trace_summary(self) -> str:
        """Debug uchun — oxirgi fikrlash izini ko'rsatadi."""
        if not self.last_trace:
            return "Hali hech qanday fikrlash bo'lmadi."
        t = self.last_trace
        return (
            f"SAVOL: {t.get('question','')}\n"
            f"REJA: {t.get('plan','')}\n"
            f"FIKR: {t.get('thinking','')[:200]}\n"
            f"TANQID: {t.get('critique','')[:100]}\n"
            f"SIFAT: {t.get('quality',0)}/10 | VAQT: {t.get('elapsed',0)}s"
        )


# ── Singleton ────────────────────────────────────────────────────────────────
_loop: Optional[AgentLoop] = None

def get_agent_loop(fast_mode: bool = False) -> AgentLoop:
    global _loop
    if _loop is None:
        _loop = AgentLoop(fast_mode=fast_mode)
    return _loop


def run_with_loop(question: str, context: str = "",
                  llm_call=None, fast: bool = False) -> str:
    """Asosiy API — tashqaridan chaqirish uchun."""
    return get_agent_loop(fast).run(question, context, llm_call)


def get_context_for_llm() -> str:
    """Modul darajasida kontekst — llm_router uchun."""
    return get_agent_loop().get_context_for_llm()
