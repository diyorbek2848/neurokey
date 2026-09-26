# NeuroKey — yo'riqnoma

Bu papka ishlayotgan NeuroKey. GitHub dan olgandan keyin modellar va kutubxonalar
avtomatik yuklanadi. Shaxsiy xotira, API kalit va yuz/ovoz namunalari repoda yo'q.

## Kompyuterda nima bo'lishi kerak

- Windows 10 yoki 11
- Python 3.10, o'rnatishda **Add Python to PATH** belgilangan
- Internet (birinchi o'rnatish)
- Mikrofon va quloqchin
- Groq kaliti, bepul: https://console.groq.com

## Noldan olish va o'rnatish

```bat
git clone <repo-manzili> neurokey
cd neurokey
SETUP.bat
```

`SETUP.bat` o'zi qiladi:

1. `.venv` yaratadi
2. `requirements.txt` dagi kutubxonalarni o'rnatadi
3. NVIDIA bo'lsa torch ni CUDA bilan qo'yadi
4. Vosk, Piper ovoz, Whisper va xotira modelini yuklaydi
5. `.env.example` dan `.env` yasaydi va ochadi
6. Shu kompyuter uchun mahalliy litsenziya yozadi (`data\license.key`)

`.env` ichida shu qator to'ldirilishi shart:

```
GROQ_API_KEY=gsk_...
```

Saqlang, notepad ni yoping. Keyin:

```bat
!NeuroKey.bat
```

Oyna ochiq tursa, mikrofon tinglaydi. Yopish: `!NeuroKey.bat stop` yoki Ctrl+F10.

## Qaysi model nima qiladi

| Vazifa | Model | Qayerda |
|---|---|---|
| Javob yozish | Groq `openai/gpt-oss-20b` | internet, kalit `.env` da |
| Eshitish | faster-whisper `base` | birinchi marta Hugging Face keshiga |
| Gapirish | Edge ovoz `ru-RU-DmitryNeural` | internet, fayl saqlanmaydi |
| Ovoz zaxirasi | Piper Irina | `models\piper` |
| Mikrofon zaxirasi | Vosk small-ru | `models\vosk` |
| Xotira qidiruvi | MiniLM | Hugging Face keshiga |
| Yuz | InsightFace buffalo_l | birinchi ochilishda `models\insightface` |
| Ovoz tanish | ECAPA-TDNN | birinchi ochilishda `models\ecapa` |

## Boshqa ochish fayllari

- `!NeuroKey.bat` — kundalik, ruscha ovoz, Groq
- `!NeuroKey_UZBEK.bat` — o'zbekcha
- `!NeuroKey_YENGIL.bat` — internetsiz kichik model (Ollama `qwen2.5:1.5b` alohida o'rnatiladi)
- `NeuroKey_START.bat` — asosiy faylni chaqiradi

## GitHub ga nima kirmaydi

`.gitignore` bularni chiqarmaydi:

- `.env` (kalit)
- `.venv`
- `models\` va `data\` (yuklab olingan modellar, xotira, litsenziya)
- `__pycache__`

Har bir yangi kompyuter `SETUP.bat` ni o'zi to'ldiradi.
