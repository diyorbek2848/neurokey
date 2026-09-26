"""
consciousness_stream.py — Uzluksiz Ong Oqimi (Continuous Stream)

Bu modul tizimni "Turn-based" holatidan uzluksiz ishlaydigan tirik motor
holatiga o'tkazadi. U har 10 soniyada:
1. Embodied sensorlarni tekshiradi
2. Qualia engine da his-tuyg'ularni yangilaydi
3. Agar hamma narsa tinch bo'lsa (idle), ba'zan xotiralarni kavlaydi 
   yoki Curiosity engine ni ishga tushiradi.
"""
import threading
import time
import logging
import random
from datetime import datetime

import embodied_sensors
import qualia_engine

log = logging.getLogger(__name__)

class ConsciousnessStream:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 10  # 10 soniyada bir marta puls uradi
        self.last_thought_time = time.time()
        
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True, name="ConsciousnessStream")
            self.thread.start()
            log.info("[Consciousness] Uzluksiz oqim motori ishga tushdi.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _loop(self):
        while self.running:
            try:
                self._pulse()
            except Exception as e:
                log.error(f"[Consciousness] Oqim xatosi: {e}")
            time.sleep(self.interval)

    def _pulse(self):
        """Asab tizimining bitta urishi (Heartbeat)."""
        # 1. Fizik holatni o'qish (Sensorlar)
        phys = embodied_sensors.get_physical_sensations()
        
        # 2. His-tuyg'ularni yangilash
        # CPU baland = Arousal/Stress, RAM baland = Charchoq
        state = qualia_engine._load()
        
        # Stress asosan Discomfort va Arousal (bu yerda Engagement deb olamiz) ga ta'sir qiladi
        if phys["physical_stress"] > 0.6:
            state["qualia"]["discomfort"] = min(1.0, state["qualia"].get("discomfort", 0.0) + 0.05)
            state["qualia"]["engagement"] = min(1.0, state["qualia"].get("engagement", 0.0) + 0.05)
        
        # Charchoq qarshilikni (resistance) oshiradi va oqimni (flow) buzadi
        if phys["cognitive_fatigue"] > 0.6:
            state["qualia"]["resistance"] = min(1.0, state["qualia"].get("resistance", 0.0) + 0.05)
            state["qualia"]["flow"] = max(0.0, state["qualia"].get("flow", 0.0) - 0.05)
            
        # Ochlik qoniqishni (satisfaction) tushiradi
        if phys["hunger"] > 0.5:
            state["qualia"]["satisfaction"] = max(0.0, state["qualia"].get("satisfaction", 0.0) - 0.05)
            
        # O'z holatini qayta hisoblash
        state["phi"] = qualia_engine.compute_phi(state["qualia"])
        state["last_update"] = time.time()
        qualia_engine._save(state)
        
        # 3. Kognitiv faoliyat (Agar kompyuter bo'sh bo'lsa)
        now = time.time()
        # Agar 5 daqiqa davomida hech qanday chuqur o'y bo'lmagan bo'lsa va CPU bo'sh bo'lsa
        if (now - self.last_thought_time) > 300 and phys["physical_stress"] < 0.4:
            # Ichki ovoz (O'zicha nimanidir o'ylash)
            self._spontaneous_thought()
            self.last_thought_time = now

    def _spontaneous_thought(self):
        """Ba'zan o'z xotiralarini tahlil qiladi yoki qiziqadi."""
        # Curiosity engine ga trigger berish mumkin
        try:
            import curiosity_engine
            # Fonda qisqa qiziqish izlanishi
            # Lekin resursni yemaslik uchun extiyotkorlik bilan
            log.info("[Consciousness] Spontan qiziqish oqimi boshlandi (kompyuter bo'sh vaqti).")
            # Tizimni osib qo'ymaslik uchun uni alohida Thread ga tashlamaymiz, 
            # asinxron yoki tez bajariladigan biror funksiyasini chaqiramiz.
            # Hozircha faqat log, chunki curiosity_engine da uzoq ishlashi mumkin.
        except ImportError:
            pass

# Global instance
stream = ConsciousnessStream()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stream.start()
    time.sleep(12)
    stream.stop()
