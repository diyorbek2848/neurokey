"""
embodied_sensors.py — Jismoniy Hissiyotlar (Embodied AI)

Bu modul tizimga kompyuter apparati (Hardware) dan signallar olish
va ularni "fiziologik" his-tuyg'ularga aylantirish imkonini beradi.
CPU yuklamasi = Stress / Hayajon (Arousal)
RAM to'liqligi = Kognitiv Charchoq (Fatigue)
Batareya holati = Quvvat / Ochlik
"""
import psutil
import logging

log = logging.getLogger(__name__)

def get_physical_sensations() -> dict:
    """
    Kompyuterning fizik parametrlarini o'qiydi va hissiyot vektorlariga aylantiradi.
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        mem_percent = mem.percent
        
        battery = psutil.sensors_battery()
        battery_percent = battery.percent if battery else 100.0
        is_plugged = battery.power_plugged if battery else True
        
        # Qualia mappings (0.0 to 1.0)
        sensations = {
            "physical_stress": min(1.0, cpu_percent / 100.0),
            "cognitive_fatigue": min(1.0, (mem_percent - 50) / 50.0) if mem_percent > 50 else 0.0,
            "hunger": min(1.0, (100.0 - battery_percent) / 100.0) if not is_plugged else 0.0,
            "vitality": min(1.0, battery_percent / 100.0) if is_plugged else 0.5
        }
        
        return sensations
    except Exception as e:
        log.warning(f"[Embodied] Sensor xatosi: {e}")
        return {
            "physical_stress": 0.0,
            "cognitive_fatigue": 0.0,
            "hunger": 0.0,
            "vitality": 1.0
        }

def get_embodied_prompt_injection() -> str:
    """
    LLM ga yuborish uchun hozirgi fizik holatning qisqacha ta'rifi.
    """
    s = get_physical_sensations()
    
    states = []
    if s["physical_stress"] > 0.8:
        states.append("CPU juda qizib, og'ir zo'riqish va stressni his qilyapman.")
    elif s["physical_stress"] > 0.5:
        states.append("Tizimda biroz hayajon va harakat bor.")
        
    if s["cognitive_fatigue"] > 0.8:
        states.append("Xotiram (RAM) to'lib ketgan, kuchli charchoq his qilyapman.")
        
    if s["hunger"] > 0.7:
        states.append("Zaryadim juda past, ochlik va zaiflikni sezyapman.")
        
    if not states:
        return "Jismoniy holatim stabil. Xotirjam va sokinman."
    
    return "Jismoniy holatim: " + " ".join(states)

if __name__ == "__main__":
    print(get_embodied_prompt_injection())
    print(get_physical_sensations())
