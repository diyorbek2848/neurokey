# -*- coding: utf-8 -*-
"""
NeuroKey - OpenAI Realtime API klient.
Real vaqt streaming: STT + LLM + TTS hammasi bitta WebSocket da.
Latency: 500-800ms (gap tugagandan birinchi ovoz chiqgancha).

Ishlash:
  1. Mikrofondan PCM16 24kHz oqim olib boriladi -> OpenAI ga
  2. Server-side VAD aniqlaydi: gap tugadi
  3. Server javobini PCM16 streaming -> dinamikga real vaqt
  4. user gapirsa - serverning o'z gapi to'xtaydi (interrupt)

Variables:
  OPENAI_API_KEY        - haqiqiy OpenAI API key (sk-proj-...)
  OPENAI_REALTIME_MODEL - gpt-4o-mini-realtime-preview (default)
  OPENAI_REALTIME_VOICE - shimmer/alloy/coral/echo/sage (default: shimmer)
  INPUT_DEVICE_INDEX    - mikrofon (default: avtomatik)
  OUTPUT_DEVICE_INDEX   - dinamik (default: avtomatik)
"""
import os, sys, time, base64, json, asyncio, threading, queue, audioop
import numpy as np
from websockets.exceptions import ConnectionClosedError

# Consciousness module — optional, degrades gracefully if missing
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from consciousness import get_consciousness as _get_consciousness
    _CONSCIOUSNESS_AVAILABLE = True
except Exception:
    _CONSCIOUSNESS_AVAILABLE = False
    _get_consciousness = None

# Audio params - Realtime API talab qiladi
SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = np.int16
CHUNK_MS = 40       # har 40ms da serverga audio yuborish (~25 Hz)
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)

# NeuroKey persona - BASE SYSTEM PROMPT (consciousness context appended at runtime)
SYSTEM_PROMPT_BASE = """Ты Нейрокей, AI ассистент Диёрбека. ВСЕГДА отвечай:
- ТОЛЬКО на русском
- Максимум 2 предложения, до 30 слов
- Если в контексте есть "Недавний контекст" — используй его: упомяни прошлый разговор естественно
- Без раздумий, мгновенно, от первого лица
Создатель: Диёрбек, 21 год, Узбекистан, стартап в Дубае."""

SYSTEM_PROMPT = SYSTEM_PROMPT_BASE  # fallback if no consciousness


def _build_system_prompt() -> str:
    """Consciousness kontekstini SYSTEM_PROMPT ga qo'shish.
    Compressed versiya — tezlikni saqlab, ongni ko'rsatadi."""
    if not _CONSCIOUSNESS_AVAILABLE or _get_consciousness is None:
        return SYSTEM_PROMPT_BASE
    try:
        c = _get_consciousness()
        ctx = c.get_context_compressed()   # 50 so'z, tez
        if ctx:
            return SYSTEM_PROMPT_BASE + "\n\n" + ctx
    except Exception:
        pass
    return SYSTEM_PROMPT_BASE


def _safe_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _is_quota_error(exc: Exception) -> bool:
    s = str(exc or "").lower()
    return ("insufficient_quota" in s) or ("quota" in s and "insufficient" in s)


class RealtimeClient:
    def __init__(self, api_key: str, model: str = None, voice: str = None,
                 input_device=None, output_device=None):
        self.api_key = api_key
        self.model = model or os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-mini-realtime-preview")
        self.voice = voice or os.getenv("OPENAI_REALTIME_VOICE", "shimmer")
        self.transport = (os.getenv("REALTIME_TRANSPORT", "websocket") or "websocket").strip().lower()
        self.audio_format = (os.getenv("REALTIME_AUDIO_FORMAT", "pcm16") or "pcm16").strip().lower()
        if self.audio_format not in ("pcm16", "g711_ulaw"):
            self.audio_format = "pcm16"
        # g711_ulaw da 8k ishlatamiz; pcm16 da 24k
        self.sample_rate = 8000 if self.audio_format == "g711_ulaw" else SAMPLE_RATE
        self.chunk_samples = int(self.sample_rate * CHUNK_MS / 1000)
        self.input_device = input_device
        self.output_device = output_device

        # Audio output queue: thread-safe (asyncio receive_loop -> play thread)
        self._out_queue = queue.Queue(maxsize=200)
        # Mikrofondan audio - sinxron (queue) -> async ga
        self._in_queue = None  # asyncio.Queue, asyncio loop ichida yaratiladi
        # Play thread va stop flag
        self._play_thread = None
        self._play_stop = threading.Event()

        self._connection = None
        self._stop_event = asyncio.Event()
        self._loop = None

        # Statistika - latency o'lchash
        self._t_user_speech_end = 0.0
        self._t_first_audio = 0.0
        self._latency_logged = False

        # Consciousness — conversation tracking
        self._consciousness = None
        if _CONSCIOUSNESS_AVAILABLE and _get_consciousness is not None:
            try:
                self._consciousness = _get_consciousness()
            except Exception:
                pass
        self._last_user_text: str = ""
        self._last_ai_text: str = ""

    async def _send_audio_loop(self):
        """Mikrofondan kelayotgan audio chunklarni serverga yuborish."""
        while not self._stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(self._in_queue.get(), timeout=0.5)
                if chunk is None:
                    break
                # PCM16 -> base64
                if self.audio_format == "g711_ulaw":
                    chunk = audioop.lin2ulaw(chunk, 2)
                b64 = base64.b64encode(chunk).decode("ascii")
                await self._connection.input_audio_buffer.append(audio=b64)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                _safe_print(f"[REALTIME] send_audio xato: {e}")
                break

    async def _receive_loop(self):
        """Serverdan kelayotgan eventlarni qayta ishlash."""
        async for event in self._connection:
            etype = event.type

            if etype == "session.created":
                _safe_print(f"[REALTIME] Session yaratildi: {event.session.id}")

            elif etype == "session.updated":
                _safe_print(f"[REALTIME] Session yangilandi (instructions+VAD aktiv).")

            elif etype == "input_audio_buffer.speech_started":
                _safe_print("[USER] gapirmoqda...")
                self._latency_logged = False
                # Barge-in: eski audioni tashlab, dinamikni jim qilamiz
                with self._out_queue.mutex:
                    self._out_queue.queue.clear()

            elif etype == "input_audio_buffer.speech_stopped":
                self._t_user_speech_end = time.monotonic()
                _safe_print("[USER] gap tugadi - javob kutilmoqda...")

            elif etype == "conversation.item.input_audio_transcription.completed":
                # User gapining transkriptsiyasi tayyor (rasmiy)
                txt = getattr(event, "transcript", "") or ""
                if txt.strip():
                    _safe_print(f">> {txt}")
                    self._last_user_text = txt.strip()
                    if self._consciousness:
                        try:
                            self._consciousness.set_focus(txt.strip()[:150])
                        except Exception:
                            pass

            elif etype == "response.audio.delta":
                # Server audio chunk yubordi (base64 PCM16)
                if not self._latency_logged and self._t_user_speech_end > 0:
                    latency_ms = (time.monotonic() - self._t_user_speech_end) * 1000
                    _safe_print(f"[LATENCY] gap tugagandan birinchi audio: {latency_ms:.0f}ms")
                    self._latency_logged = True
                try:
                    audio_bytes = base64.b64decode(event.delta)
                    if self.audio_format == "g711_ulaw":
                        audio_bytes = audioop.ulaw2lin(audio_bytes, 2)
                    self._out_queue.put_nowait(audio_bytes)
                except queue.Full:
                    pass  # Eski audio - tashlab yuboramiz
                except Exception as e:
                    _safe_print(f"[REALTIME] audio decode xato: {e}")

            elif etype == "response.audio_transcript.delta":
                # AI matn javobi (streaming) - log uchun
                pass  # Faqat audio kerak

            elif etype == "response.audio_transcript.done":
                txt = getattr(event, "transcript", "") or ""
                if txt.strip():
                    _safe_print(f"<< {txt}")
                    self._last_ai_text = txt.strip()
                    # Consciousness: save turn + reflection
                    if self._consciousness and self._last_user_text:
                        try:
                            self._consciousness.add_turn(self._last_user_text, txt.strip())
                            self._consciousness.add_post_turn_reflection(
                                self._last_user_text, txt.strip()
                            )
                        except Exception:
                            pass
                        self._last_user_text = ""

            elif etype == "response.done":
                pass  # Javob to'liq tugadi

            elif etype == "error":
                err = getattr(event, "error", None)
                _safe_print(f"[REALTIME ERROR] {err}")

    def _play_thread_func(self):
        """Audio play thread - asyncio dan ALOHIDA, blocking write OK."""
        try:
            import sounddevice as sd
            stream = sd.RawOutputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                device=self.output_device,
                blocksize=self.chunk_samples,
            )
            stream.start()
        except Exception as e:
            _safe_print(f"[REALTIME] OutputStream yaratib bo'lmadi: {e}")
            return

        try:
            while not self._play_stop.is_set():
                try:
                    audio_bytes = self._out_queue.get(timeout=0.2)
                    if audio_bytes is None:
                        break
                    stream.write(audio_bytes)
                except queue.Empty:
                    continue
                except Exception as e:
                    _safe_print(f"[REALTIME] play xato: {e}")
                    break
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _mic_callback(self, indata, frames, time_info, status):
        """Mikrofon callback - sinxron, asyncio queue ga uzatadi."""
        if status:
            return
        try:
            # indata - PCM16 bytes
            chunk = bytes(indata)
            if self._loop and not self._stop_event.is_set():
                asyncio.run_coroutine_threadsafe(
                    self._in_queue.put(chunk), self._loop
                )
        except Exception:
            pass

    async def run(self):
        """Asosiy ishchi loop - WebSocket ulanish + audio stream."""
        from openai import AsyncOpenAI

        self._loop = asyncio.get_running_loop()
        self._in_queue = asyncio.Queue(maxsize=200)

        client = AsyncOpenAI(api_key=self.api_key)

        _safe_print(f"[REALTIME] Ulanmoqda: {self.model} | voice={self.voice}")
        if self.transport != "websocket":
            _safe_print(f"[REALTIME] transport={self.transport} hozircha tayyor emas, websocket fallback ishlatiladi.")
            self.transport = "websocket"
        t0 = time.monotonic()

        async with client.beta.realtime.connect(model=self.model) as conn:
            self._connection = conn

            # ======================================================
            # ENG TEZ KONFIGURATSIYA - <500ms maqsad
            # ======================================================
            # VAD turi: env var dan tanlash
            #   "semantic" - LLM gap tugashini predikta qiladi (eng tez, ~100-200ms turn detect)
            #   "aggressive" - server VAD 200ms silence (tez, lekin gapni kesishi mumkin)
            #   "balanced" - 350ms silence (xavfsiz, biroz sekin)
            vad_mode = os.getenv("REALTIME_VAD_MODE", "semantic").strip().lower()

            if vad_mode == "semantic":
                turn_detection = {
                    "type": "semantic_vad",
                    "eagerness": "high",   # eng agressiv - tezroq turn detect
                }
                _safe_print("[REALTIME] VAD: semantic_vad (eagerness=high)")
            elif vad_mode == "aggressive":
                turn_detection = {
                    "type": "server_vad",
                    "threshold": 0.4,
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 200,   # 200ms jimlik = gap tugadi (was 500)
                    "create_response": True,
                    "interrupt_response": True,
                }
                _safe_print("[REALTIME] VAD: aggressive server_vad (200ms silence)")
            else:
                turn_detection = {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 350,
                    "create_response": True,
                    "interrupt_response": True,
                }
                _safe_print("[REALTIME] VAD: balanced server_vad (350ms silence)")

            # Build system prompt with live consciousness context
            live_prompt = _build_system_prompt()
            if self._consciousness:
                _safe_print("[CONSCIOUSNESS] Ong aktiv — working memory injektsiya qilindi.")

            await conn.session.update(session={
                "modalities": ["audio", "text"],
                "instructions": live_prompt,
                "voice": self.voice,
                "input_audio_format": self.audio_format,
                "output_audio_format": self.audio_format,
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "turn_detection": turn_detection,
                "temperature": 0.6,
                # Qisqa javoblar = TTS tezroq tugaydi va keyingi savol tez keladi
                "max_response_output_tokens": 80,
            })

            connect_ms = (time.monotonic() - t0) * 1000
            _safe_print(f"[REALTIME] Ulandi: {connect_ms:.0f}ms")
            _safe_print("[REALTIME] Gapiring (rus tilida)... Chiqish: Ctrl+C")

            # Consciousness startup greeting — xotirani ko'rsatish
            if self._consciousness:
                wm = self._consciousness.data.get("working_memory") or []
                if wm:
                    last = wm[-1]
                    last_topic = (last.get("user") or "")[:60].strip()
                    if last_topic:
                        await conn.conversation.item.create(item={
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text",
                                         "text": "Начни сессию. Скажи одно предложение — вспомни тему нашего прошлого разговора."}],
                        })
                        await conn.response.create()

            # Mikrofon ishga tushirish
            import sounddevice as sd
            mic_stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype="int16",
                device=self.input_device,
                blocksize=self.chunk_samples,
                callback=self._mic_callback,
            )
            mic_stream.start()

            # Audio play thread (asyncio dan tashqarida)
            self._play_thread = threading.Thread(
                target=self._play_thread_func, daemon=True, name="realtime-play"
            )
            self._play_thread.start()

            try:
                # Parallel: mikrofondan audio yuborish + serverdan eventlar
                await asyncio.gather(
                    self._send_audio_loop(),
                    self._receive_loop(),
                )
            finally:
                self._play_stop.set()
                try:
                    mic_stream.stop()
                    mic_stream.close()
                except Exception:
                    pass
                if self._play_thread and self._play_thread.is_alive():
                    self._play_thread.join(timeout=2)

    def stop(self):
        self._stop_event.set()


def main():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not api_key.startswith("sk-"):
        # .env dan o'qish
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.isfile(env_path):
            try:
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENAI_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass

    if not api_key or not api_key.startswith("sk-"):
        _safe_print("[XATO] OPENAI_API_KEY topilmadi yoki noto'g'ri. .env yoki env var ni tekshiring.")
        sys.exit(1)

    # Audio device parametrlari
    inp_idx = os.getenv("INPUT_DEVICE_INDEX", "").strip()
    out_idx = os.getenv("OUTPUT_DEVICE_INDEX", "").strip()
    input_device = int(inp_idx) if inp_idx.isdigit() else None
    output_device = int(out_idx) if out_idx.isdigit() else None

    client = RealtimeClient(
        api_key=api_key,
        input_device=input_device,
        output_device=output_device,
    )

    max_retries = int(os.getenv("REALTIME_CONNECT_RETRIES", "2") or "2")
    retry_sleep_sec = float(os.getenv("REALTIME_CONNECT_RETRY_SLEEP_SEC", "2.0") or "2.0")

    try:
        attempt = 0
        while True:
            attempt += 1
            try:
                asyncio.run(client.run())
                break
            except ConnectionClosedError as e:
                if _is_quota_error(e):
                    _safe_print("[REALTIME] OpenAI quota yetarli emas (insufficient_quota). Billingni tekshiring.")
                    break
                if attempt > max_retries:
                    _safe_print(f"[REALTIME] Reconnect urinishlar tugadi: {e}")
                    break
                _safe_print(f"[REALTIME] Ulanish uzildi, qayta uriniladi ({attempt}/{max_retries})...")
                time.sleep(retry_sleep_sec)
    except KeyboardInterrupt:
        _safe_print("\n[REALTIME] Foydalanuvchi to'xtatdi.")
    except Exception as e:
        _safe_print(f"[REALTIME] Xato: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
