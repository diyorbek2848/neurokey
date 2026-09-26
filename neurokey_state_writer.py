# -*- coding: utf-8 -*-
"""
NeuroKey HUD State Writer
=========================
main.py yoki boshqa NG modullar bu faylni import qilib,
HUD ga real vaqtda holat yozadi.

Ishlatish:
    from neurokey_state_writer import nk_state

    nk_state.update(mode="listening")
    nk_state.update(mode="thinking", modules_active=["attention_schema","working_memory"])
    nk_state.update(mode="speaking", last_output="Salom, men shu yerdaman!")
    nk_state.update(mode="idle")
"""
import json, os, time, threading

_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'neurokey_state.json')
_lock = threading.Lock()

_state = {
    "mode":                "idle",
    "last_input":          "",
    "last_output":         "",
    "modules_active":      [],
    "emotion":             "neutral",
    "consciousness_score": 0.0,
    "face_owner":          "",        # "Diyorbek (0.82)" yoki ""
    "face_known":          False,     # egasimi?
    "face_emotion":        "",        # "happy", "sad", "neutral" ...
    "timestamp":           time.time(),
}

def _write():
    try:
        with open(_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_state, f, ensure_ascii=False, indent=None)
    except Exception as e:
        pass   # HUD yo'q bo'lsa ham main.py ishlashi kerak

class _StateProxy:
    """nk_state.update(mode=...) interfeysi."""

    def update(self, mode=None, last_input=None, last_output=None,
               modules_active=None, emotion=None, consciousness_score=None,
               face_owner=None, face_known=None, face_emotion=None,
               **extra):
        with _lock:
            if mode               is not None: _state["mode"]               = mode
            if last_input         is not None: _state["last_input"]         = str(last_input)
            if last_output        is not None: _state["last_output"]        = str(last_output)
            if modules_active     is not None: _state["modules_active"]     = list(modules_active)
            if emotion            is not None: _state["emotion"]            = str(emotion)
            if consciousness_score is not None:
                _state["consciousness_score"] = float(consciousness_score)
            if face_owner         is not None: _state["face_owner"]         = str(face_owner)
            if face_known         is not None: _state["face_known"]         = bool(face_known)
            if face_emotion       is not None: _state["face_emotion"]       = str(face_emotion)
            _state["timestamp"] = time.time()
            _write()

    # Shortcut helpers
    def listening(self, text=""):
        self.update(mode="listening", last_input=text)

    def thinking(self, modules=None):
        self.update(mode="thinking",
                    modules_active=modules or _state["modules_active"])

    def speaking(self, text=""):
        self.update(mode="speaking", last_output=text)

    def idle(self):
        self.update(mode="idle")

    def error(self, msg=""):
        self.update(mode="error", last_output=msg)


nk_state = _StateProxy()


# ── main.py ga qo'shish uchun misol ──────────────────────────────────────────
# (Bu qatorlarni main.py ga nusxa olish kerak)
#
# === STT natija kelganda (foydalanuvchi gapirdi) ===
#   nk_state.listening(text=user_text)
#
# === LLM jarayoni boshlanganida ===
#   nk_state.thinking(modules=["attention_schema", "working_memory", "goal_system"])
#
# === TTS jarayoni boshlanganida ===
#   nk_state.speaking(text=response_text[:120])
#
# === Bo'sh turganida ===
#   nk_state.idle()
#
# === Consciousness score yangilanganda ===
#   from consciousness_orchestrator import get_consciousness_score
#   nk_state.update(consciousness_score=get_consciousness_score(),
#                   emotion="curious",
#                   modules_active=active_list)
