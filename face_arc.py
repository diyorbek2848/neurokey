# -*- coding: utf-8 -*-
"""
face_arc.py — NeuroKey ArcFace Yuz Tanish (Maksimal aniqlik)

InsightFace buffalo_l modeli:
  - ArcFace 512-o'lchamli embedding
  - LFW benchmark: ~99.4% aniqlik
  - LBPH dan: 75% → 99% ga o'tish
  - Kam yorug'likda: CLAHE preprocessing yordamida

Foydalanish:
  from face_arc import enroll, identify, is_owner

Ro'yxatga olish: enroll(frames_list) yoki enroll_from_camera()
Tanish: identify(frame) → {"known": bool, "similarity": float, ...}
"""
from __future__ import annotations

import os
import json
import logging
import threading
import time
from typing import Optional, List, Tuple

import numpy as np

log = logging.getLogger(__name__)

_BASE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(_BASE, "data")
PROF_PATH = os.path.join(DATA_DIR, "face_arc_profile.npy")
INFO_PATH = os.path.join(DATA_DIR, "face_arc_owner.json")

# ArcFace cosine o'xshashlik chegarasi
# 0.40 = liberal (ham taniydi), 0.50 = o'rtacha, 0.55 = qattiq
THRESHOLD  = 0.45
MODEL_PACK = "buffalo_l"   # ArcFace + RetinaFace

# ── Lazy-load ─────────────────────────────────────────────────────────────────
_app          = None
_owner_embed: Optional[np.ndarray] = None
_owner_info:  dict = {}
_lock         = threading.Lock()
_loaded       = False

# ── Real-time kamera fon thread ───────────────────────────────────────────────
_cam_result:  dict = {}
_cam_lock     = threading.Lock()
_cam_thread:  Optional[threading.Thread] = None
_cam_stop     = threading.Event()

# Oxirgi kadr (vision LLM uchun)
_last_frame:     Optional[np.ndarray] = None
_last_frame_ts:  float = 0.0
_frame_lock      = threading.Lock()

def get_last_face_result() -> dict:
    """Oxirgi kamera natijasi — 0ms, fon threaddan."""
    with _cam_lock:
        return dict(_cam_result)

def get_last_frame() -> Optional[np.ndarray]:
    """Oxirgi BGR kadr — vision LLM uchun. 0ms, fon threaddan."""
    with _frame_lock:
        return _last_frame.copy() if _last_frame is not None else None

def get_last_frame_age() -> float:
    """Oxirgi kadr necha sekund oldin olingan."""
    return time.time() - _last_frame_ts if _last_frame_ts > 0 else 9999.0

def _cam_worker(camera_index: int = 0, interval: float = 3.0):
    """Kamera DOIMIY ochiq — LED yonib turadi. Har {interval}s da yuz taniydi."""
    import cv2
    cap = None
    try:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            log.warning("[FACE-ARC] Kamera ochilmadi (index=%d) — 5s kutib qayta urinadi", camera_index)
            _cam_stop.wait(5.0)
            # Qayta urinish
            if not _cam_stop.is_set():
                threading.Thread(target=_cam_worker, args=(camera_index, interval),
                                 daemon=True, name="FaceArc-CamRetry").start()
            return

        log.info("[FACE-ARC] Kamera YOQILDI (index=%d) — LED doimiy yonadi", camera_index)
        # Kamera isishi — birinchi kadrni o'tkazib yuboramiz
        _cam_stop.wait(0.6)
        _fail_count = 0

        while not _cam_stop.is_set():
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                # ── Oxirgi kadrni saqlash (vision LLM uchun) ─────────────────
                with _frame_lock:
                    global _last_frame, _last_frame_ts
                    _last_frame    = frame.copy()
                    _last_frame_ts = time.time()

                result = identify(frame)

                # ── Emotion detection (yuz ko'ringanda) ──────────────────────
                emotion = "neutral"
                if result.get("similarity", 0) > 0.10:   # yuz ko'rinsa
                    emotion = detect_emotion(frame)
                    result["emotion"] = emotion
                    # Valence yangilash kameradan
                    try:
                        from valence_state import update_from_face_emotion as _ufe
                        _ufe(emotion)
                    except Exception:
                        pass

                with _cam_lock:
                    global _cam_result
                    _cam_result = result
                _fail_count = 0

                # HUD ga yuz + emotion natijasini yuborish
                try:
                    from neurokey_state_writer import nk_state as _nks
                    if result.get("known"):
                        _emo_icon = {"happy": "😊", "sad": "😢", "angry": "😠",
                                     "fear": "😨", "surprise": "😲",
                                     "disgust": "🤢", "neutral": "😐"}.get(emotion, "")
                        _nks.update(
                            face_owner=f"{result.get('name','?')} ({result.get('similarity',0):.2f}) {_emo_icon}",
                            face_known=True,
                            face_emotion=emotion,
                        )
                        log.debug("[FACE-ARC] Egasi: %s (sim=%.2f) emotion=%s",
                                  result.get("name", "?"), result.get("similarity", 0), emotion)
                    else:
                        try:
                            from owner_trust import always_trust_owner, owner_nick, any_biometric_profile
                            if always_trust_owner() and any_biometric_profile():
                                _nks.update(
                                    face_owner=f"{owner_nick()} (kamera)",
                                    face_known=True,
                                    face_emotion=emotion,
                                )
                            elif result.get("similarity", 0) > 0.01:
                                _nks.update(face_owner="noma'lum", face_known=False, face_emotion="")
                            else:
                                _nks.update(face_owner="", face_known=False, face_emotion="")
                        except Exception:
                            _nks.update(face_owner="", face_known=False, face_emotion="")
                except Exception:
                    pass
            else:
                _fail_count += 1
                if _fail_count > 10:
                    log.warning("[FACE-ARC] Kamera signal yo'q (%d xato) — qayta ulanish", _fail_count)
                    break
            _cam_stop.wait(interval)

    except Exception as e:
        log.warning("[FACE-ARC] Kamera worker xatosi: %s", e)
    finally:
        if cap:
            try: cap.release()
            except: pass

    # Xato bo'lsa — 5s dan keyin qayta urinish
    if not _cam_stop.is_set():
        _cam_stop.wait(5.0)
        if not _cam_stop.is_set():
            threading.Thread(target=_cam_worker, args=(camera_index, interval),
                             daemon=True, name="FaceArc-CamRetry").start()

def start_camera_guard(camera_index: int = 0, interval: float = 2.5):
    """Fon kamera guardni ishga tushirish — main.py startup da chaqiriladi."""
    global _cam_thread
    if not profile_exists():
        return
    if _cam_thread and _cam_thread.is_alive():
        return
    _cam_stop.clear()
    _cam_thread = threading.Thread(
        target=_cam_worker,
        args=(camera_index, interval),
        daemon=True,
        name="FaceArc-CamGuard",
    )
    _cam_thread.start()
    log.info("[FACE-ARC] Kamera guard ishga tushdi (%.1fs interval)", interval)

def stop_camera_guard():
    _cam_stop.set()


def detect_emotion(frame: np.ndarray) -> str:
    """Yuz ifodasi tanish.
    Qaytaradi: 'happy', 'sad', 'angry', 'fear', 'surprise', 'disgust', 'neutral'
    1. DeepFace (agar o'rnatilgan) — ~94% aniqlik
    2. OpenCV smile cascade (fallback) — taxminiy
    3. 'neutral' (oxirgi fallback)
    """
    if frame is None or frame.size == 0:
        return "neutral"

    # ── 1. DeepFace ────────────────────────────────────────────────────────────
    try:
        from deepface import DeepFace
        res = DeepFace.analyze(
            frame,
            actions=["emotion"],
            enforce_detection=False,
            silent=True,
        )
        if isinstance(res, list):
            res = res[0]
        emo = res.get("dominant_emotion", "neutral")
        return emo
    except ImportError:
        pass   # DeepFace yo'q — keyingiga o'tamiz
    except Exception:
        pass

    # ── 2. OpenCV smile cascade (fallback) ─────────────────────────────────────
    try:
        import cv2 as _cv2
        gray = _cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY)
        # Yuz topamiz
        face_cas = _cv2.CascadeClassifier(
            _cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces_r = face_cas.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
        if len(faces_r) > 0:
            x, y, w, h = faces_r[0]
            roi = gray[y : y + h, x : x + w]
            smile_cas = _cv2.CascadeClassifier(
                _cv2.data.haarcascades + "haarcascade_smile.xml"
            )
            smiles = smile_cas.detectMultiScale(
                roi, scaleFactor=1.5, minNeighbors=22, minSize=(25, 25)
            )
            if len(smiles) > 0:
                return "happy"
    except Exception:
        pass

    return "neutral"


def _clahe_enhance(frame: np.ndarray) -> np.ndarray:
    """Kam yorug'lik uchun CLAHE (Adaptive Histogram Equalization).
    BGR kiradi, BGR qaytadi."""
    try:
        import cv2
        lab  = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        cl   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l    = cl.apply(l)
        lab  = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception:
        return frame


# ROOT-CAUSE FIX (2026-09-13, real test bilan topildi): onnxruntime-gpu
# o'rnatilgan va `onnxruntime.get_available_providers()` CUDAExecutionProvider
# ni ro'yxatda ko'rsatadi (tekshirildi), LEKIN cuDNN DLL (cudnn64_9.dll va
# cudnn_*64_9.dll bo'laklari) faqat `pip install nvidia-cudnn-cu12` orqali
# site-packages\nvidia\cudnn\bin\ ichiga o'rnatilgan — bu papka Windows PATH
# da YO'Q (faqat PyTorch buni o'zining ICHKI DLL-qidiruv mexanizmi bilan
# topadi, torch.cuda ishlashi buni TASDIQLAMAYDI ham — onnxruntime butunlay
# boshqa, mustaqil DLL yuklash yo'li ishlatadi). Natijada
# CUDAExecutionProvider session yaratishga urinadi, lekin cuDNN topa
# olmagani uchun ICHKI jim (silent) ravishda CPUExecutionProvider ga
# qaytadi — aynan shu bug logda ko'ringan `Applied providers: ['CPUExecutionProvider']`
# ning sababi (koddagi eski cuDNN-tekshiruv FAQAT ogohlantirish chop etardi,
# lekin muammoni tuzatmasdi).
#
# SINAB KO'RILDI VA RAD ETILDI: `os.add_dll_directory(cudnn_bin)` — bu Win32
# AddDllDirectory() ni chaqiradi va nazariy jihatdan process-wide DLL qidiruv
# yo'liga qo'shishi kerak, LEKIN real testda onnxruntime_providers_cuda.dll
# hamon "cudnn64_9.dll ... is missing" xatosi bilan CPUExecutionProvider ga
# qaytishda davom etdi (onnxruntime provider bridge cudnn'ni add_dll_directory
# ro'yxatini hurmat qilmaydigan usulda yuklaydi, shekilli).
# ISHLAYDIGAN YECHIM (tekshirildi, real InferenceSession bilan): cuDNN bin
# papkasini `os.environ["PATH"]` ning BOSHIGA qo'shish — PATH klassik DLL
# qidiruv tartibining bir qismi, har qanday LoadLibrary chaqiruvi (flag'idan
# qat'i nazar) uni ko'radi. CUDA runtime (cudart64_12.dll) ALLAQACHON PATH da
# (tizimga o'rnatilgan NVIDIA CUDA Toolkit v12.6 orqali, tekshirildi), faqat
# cuDNN yetishmayapti edi.
def _register_cuda_dll_dirs() -> None:
    try:
        import importlib.util as _ilu
        added = []
        for _pkg in ("nvidia.cudnn", "nvidia.cublas", "nvidia.cuda_nvrtc", "nvidia.cuda_runtime"):
            try:
                _spec = _ilu.find_spec(_pkg)
            except Exception:
                _spec = None
            if not _spec or not _spec.submodule_search_locations:
                continue
            for _root in _spec.submodule_search_locations:
                _bin_dir = os.path.join(_root, "bin")
                if os.path.isdir(_bin_dir) and _bin_dir not in added:
                    added.append(_bin_dir)
                    # Win32-darajasida ham qo'shamiz (zarar qilmaydi,
                    # ba'zi boshqa DLL yuklash yo'llari buni hurmat qiladi)
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(_bin_dir)
                        except (OSError, FileNotFoundError):
                            pass
        if added:
            _cur_path = os.environ.get("PATH", "")
            _new_dirs = [d for d in added if d not in _cur_path]
            if _new_dirs:
                os.environ["PATH"] = os.pathsep.join(_new_dirs) + os.pathsep + _cur_path
                log.info("[FACE-ARC] cuDNN/cuBLAS DLL papkalari PATH ga qo'shildi: %s", _new_dirs)
    except Exception as e:
        log.debug("[FACE-ARC] CUDA DLL papkalarini ro'yxatga olishda xato: %s", e)


def _load():
    """InsightFace modelini bir marta yuklaydi.

    RACE-CONDITION FIX (2026-09-13, real hangdan keyin topildi): bu funksiya
    startupda BIR NECHA threaddan deyarli bir vaqtda chaqiriladi — (1)
    neurokey_prewarm.py'dagi "NK-FaceArcWarm" fon thread, (2) main.py'dagi
    "ArcFace-preload" fon thread, va (3) main.py asosiy (main) threadi
    o'zi ham GUARDIAN blokida get_status() orqali bu yerga kirardi.
    Avval `_loaded=True` OG'IR ishdan (FaceAnalysis + .prepare(), GPU sovuq
    boshlanishida CUDA/cuDNN JIT ~o'nlab-yuzlab soniya cho'zilishi mumkin)
    OLDIN qo'yilardi — bu ikkita muammo keltirib chiqargan:
      a) Agar ikkinchi chaqiruvchi juda tez kelsa, `_loaded` hali False,
         `with _lock` ni birinchi bo'lib O'ZI ushlab, OG'IR yuklashni O'ZI
         boshlab yuborishi mumkin edi — agar bu ASOSIY (main) thread bo'lsa,
         butun ilova shu yerda, sekundlab, HECH QANDAY konsol chiqishisiz
         (quyidagi progress xabarlari faqat log.info() orqali edi, root
         logger darajasi WARNING — main.py:16 — shuning uchun ko'rinmas edi)
         qotib qolardi.
      b) `_loaded=True` yuklash TUGAMASDAN turib qo'yilgani uchun boshqa
         chaqiruvchilar hali tayyor bo'lmagan _app/_owner_info bilan
         "tayyor" deb noto'g'ri javob olardi.
    FIX: (1) main.py endi bu funksiyani asosiy threadda UMUMAN chaqirmaydi —
    get_status_cheap() dan foydalanadi (faqat fayldan metadata o'qiydi).
    (2) `_loaded=True` endi FAQAT haqiqatan tugagach (muvaffaqiyat YOKI
    xato) qo'yiladi — shu tufayli ikkinchi chaqiruvchi (agar baribir kirsa)
    `with _lock` da to'g'ri KUTADI, noto'g'ri "tayyor" holatini qaytarmaydi.
    (3) Og'ir bosqich atrofiga shartsiz print() (log emas!) qo'shildi —
    endi konsolda har doim ko'rinadi."""
    global _app, _owner_embed, _owner_info, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _t_load0 = time.time()
        print("[FACE-ARC] InsightFace yuklanmoqda (birinchi marta — GPU sovuq boshlanishda bir necha o'n soniya olishi mumkin)...", flush=True)
        try:
            _register_cuda_dll_dirs()
            from insightface.app import FaceAnalysis
            import onnxruntime as _ort
            _avail = _ort.get_available_providers()
            if "CUDAExecutionProvider" in _avail:
                _providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                _ctx = 0
                # cuDNN tekshiruvi — endi _register_cuda_dll_dirs() pip bilan
                # o'rnatilgan cuDNN papkasini ham DLL qidiruv yo'liga qo'shgan,
                # shuning uchun bu tekshiruv ham o'sha joyni ko'radi.
                import ctypes as _ct2, os as _os2, importlib.util as _ilu2
                _cudnn_dirs = list(_os2.environ.get("PATH", "").split(";"))
                try:
                    _spec2 = _ilu2.find_spec("nvidia.cudnn")
                    if _spec2 and _spec2.submodule_search_locations:
                        _cudnn_dirs += [os.path.join(r, "bin") for r in _spec2.submodule_search_locations]
                except Exception:
                    pass
                _cudnn_found = any(
                    _os2.path.exists(_os2.path.join(d, dll))
                    for dll in ("cudnn64_9.dll", "cudnn64_8.dll")
                    for d in _cudnn_dirs
                    if d.strip()
                )
                if not _cudnn_found:
                    log.warning(
                        "[FACE-ARC] cuDNN DLL topilmadi! 1k3d68.onnx (landmark) CPU da ishlaydi. "
                        "GPU da ishlatish uchun: https://developer.nvidia.com/cudnn "
                        "→ cudnn64_9.dll ni C:\\Windows\\System32 ga ko'chiring."
                    )
                    print("[FACE-ARC] ⚠ cuDNN topilmadi → landmark model CPU da (sekinroq)", flush=True)
                else:
                    log.info("[FACE-ARC] cuDNN topildi (pip nvidia-cudnn-cu12 DLL yo'liga qo'shildi) — to'liq GPU rejimi")
                log.info("[FACE-ARC] CUDA provider mavjud — GPU ishlatiladi")
            else:
                _providers = ["CPUExecutionProvider"]
                _ctx = -1
                log.info("[FACE-ARC] CUDA provider yo'q — CPU rejimi")
            _app = FaceAnalysis(
                name=MODEL_PACK,
                root=os.path.join(_BASE, "models", "insightface"),
                providers=_providers,
            )
            # CPU rejimida 640x640 juda og'ir (5 ta model, har safar) — tizimni
            # qotirib qo'yishi mumkin. GPU (CUDA) bo'lsa katta o'lcham xavfsiz,
            # CPU bo'lsa kichikroq o'lcham ishlatamiz.
            _det_size = (640, 640) if "CUDAExecutionProvider" in _providers else (320, 320)
            _app.prepare(ctx_id=_ctx, det_size=_det_size)
            log.info("[FACE-ARC] InsightFace %s yuklandi", MODEL_PACK)
            print(f"[FACE-ARC] InsightFace {MODEL_PACK} tayyor ({time.time() - _t_load0:.1f}s)", flush=True)
        except Exception as e:
            log.warning("[FACE-ARC] InsightFace yuklanmadi: %s", e)
            print(f"[FACE-ARC] InsightFace yuklashda XATO ({time.time() - _t_load0:.1f}s): {e!r}", flush=True)
            _app = None
            _loaded = True  # urinib ko'rildi — har chaqiruvda qayta muzlab qolmasin
            return

        # Profil yuklash
        if os.path.exists(PROF_PATH):
            try:
                _owner_embed = np.load(PROF_PATH)
                _owner_embed /= (np.linalg.norm(_owner_embed) + 1e-8)
            except Exception as e:
                log.warning("[FACE-ARC] Profil yuklanmadi: %s", e)
        if os.path.exists(INFO_PATH):
            try:
                with open(INFO_PATH, encoding="utf-8") as f:
                    _owner_info = json.load(f)
            except Exception:
                pass
        if _owner_embed is not None:
            log.info("[FACE-ARC] Profil tayyor: %s (%d dim)",
                     _owner_info.get("name", "?"), _owner_embed.shape[0])
        _loaded = True  # ENDI — haqiqatan hammasi tayyor bo'lgach


def _get_face_embedding(frame: np.ndarray) -> Optional[np.ndarray]:
    """Rasmdan ArcFace 512-dim embedding olish."""
    if _app is None or frame is None:
        return None
    try:
        # Kam yorug'lik tekshiruvi
        gray_mean = float(np.mean(frame))
        if gray_mean < 50:       # Juda qorong'u → CLAHE
            frame = _clahe_enhance(frame)
        elif gray_mean < 100:    # Dim yorug'lik → ozroq CLAHE
            frame = _clahe_enhance(frame)

        faces = _app.get(frame)
        if not faces:
            return None
        # Eng katta yuz (kameraga yaqin)
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        emb  = face.normed_embedding
        return emb / (np.linalg.norm(emb) + 1e-8)
    except Exception as e:
        log.debug("[FACE-ARC] embedding xato: %s", e)
        return None


# ── Ro'yxatga olish ───────────────────────────────────────────────────────────

def enroll(frames: List[np.ndarray], name: str = "owner") -> bool:
    """
    Bir nechta kadrdan profil yaratish.
    frames: BGR numpy array list (kameradan olingan)
    """
    _load()
    if _app is None:
        log.error("[FACE-ARC] InsightFace yuklanmagan — enroll imkonsiz")
        return False

    embeddings = []
    for i, frame in enumerate(frames):
        emb = _get_face_embedding(frame)
        if emb is not None:
            embeddings.append(emb)

    if len(embeddings) < 5:
        log.warning("[FACE-ARC] Yetarli yuz topilmadi (%d < 5)", len(embeddings))
        return False

    # O'rtacha profil
    profile = np.mean(embeddings, axis=0)
    profile /= (np.linalg.norm(profile) + 1e-8)

    os.makedirs(DATA_DIR, exist_ok=True)
    np.save(PROF_PATH, profile)

    from datetime import datetime
    info = {
        "name":        name,
        "enrolled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "num_frames":  len(embeddings),
        "method":      "arcface_512dim",
        "dims":        512,
        "threshold":   THRESHOLD,
    }
    with open(INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    global _owner_embed, _owner_info
    _owner_embed = profile
    _owner_info  = info
    log.info("[FACE-ARC] Profil saqlandi: %d kadr, %s", len(embeddings), name)
    return True


def enroll_from_camera(
    camera_index: int = 0,
    n_frames: int = 120,
    name: str = "owner",
) -> bool:
    """Kameradan avtomatik kadrlar olib profil yaratish."""
    import cv2
    _load()
    if _app is None:
        return False

    print(f"\n  Kamera ochilmoqda... {n_frames} ta yuz kadr olinadi.")
    print("  Kameraga to'g'ri qarang. Boshingizni asta harakat ettiring.")
    cap    = cv2.VideoCapture(camera_index)
    frames = []
    collected = 0
    start_t = time.time()

    while collected < n_frames and (time.time() - start_t) < 60:
        ret, frame = cap.read()
        if not ret:
            break
        emb = _get_face_embedding(frame)
        if emb is not None:
            frames.append(frame)
            collected += 1
            if collected % 20 == 0:
                print(f"    {collected}/{n_frames} kadr ✓")
        time.sleep(0.05)

    cap.release()
    if collected < 5:
        print("  Yuz topilmadi. Yaxshi yorug'lik kerak.")
        return False
    return enroll(frames, name=name)


# ── Tanish ────────────────────────────────────────────────────────────────────

def identify(frame: np.ndarray) -> dict:
    """
    Kadrdan egasining yuzimi?
    Returns: {"known": bool, "similarity": float, "threshold": float, ...}
    """
    _load()

    base = {
        "known":        False,
        "similarity":   0.0,
        "threshold":    THRESHOLD,
        "profile_exists": os.path.exists(PROF_PATH),
        "name":         "noma'lum",
        "method":       "arcface",
    }

    if _app is None or _owner_embed is None or frame is None:
        return base

    emb = _get_face_embedding(frame)
    if emb is None:
        return base  # Yuz ko'rinmadi

    sim   = float(np.dot(_owner_embed, emb))
    known = sim >= THRESHOLD

    out = {
        **base,
        "known":      known,
        "similarity": round(sim, 3),
        "name":       _owner_info.get("name", "egasi") if known else "noma'lum",
    }
    try:
        from owner_trust import trust_biometric_result
        return trust_biometric_result(out)
    except Exception:
        return out


def identify_from_camera(camera_index: int = 0) -> dict:
    """Kameradan bir kadr olib tanish."""
    import cv2
    cap = cv2.VideoCapture(camera_index)
    time.sleep(0.3)  # kamera isishi
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return {"known": False, "similarity": 0.0, "profile_exists": False}
    return identify(frame)


def is_owner(frame: Optional[np.ndarray] = None,
             camera_index: int = 0) -> bool:
    """Tez tekshiruv — egasimi?"""
    if frame is not None:
        return identify(frame)["known"]
    return identify_from_camera(camera_index)["known"]


def profile_exists() -> bool:
    return os.path.exists(PROF_PATH)


def prewarm() -> None:
    """FON THREADIDA chaqirilishi kerak (neurokey_prewarm.start() orqali,
    xuddi vector_memory.prewarm()/knowledge_index kabi) — InsightFace ning
    5 ta ONNX modelini (1k3d68, 2d106det, det_10g, genderage, w600k_r50)
    BIR MARTA, ERTA, jonli suhbat boshlanishidan OLDIN yuklaydi.

    ROOT-CAUSE FIX (2026-09-13, real test bilan topildi): ilgari bu yuklash
    FAQAT `identify()` birinchi marta chaqirilganda sodir bo'lardi (lazy) —
    bu odatda kamera guard fon threadida birinchi kadr o'qilganda, LEKIN bu
    "birinchi chaqiruv" istalgan vaqtda, jonli suhbat o'rtasida ham sodir
    bo'lishi mumkin edi (masalan owner_trust/GUARDIAN moduli identify()ni
    boshqa triggerdan chaqirsa). O'lchandi (gil_test.py): CPU rejimida 5 ta
    ONNX InferenceSession yaratish ~5.8s davom etadi VA bu vaqt davomida
    asosiy threaddagi ODDIY Python operatsiyalari (masalan bir necha KB li
    JSON o'qish) GIL/CPU raqobati sabab 800ms+ to'xtab qolishi mumkin — bu
    aynan free_will_simulator.get_stats()=2213ms va qisman vector_memory.
    get_stats()=22413ms kechikishlarining video-dalili (ORCH_SLOW_MODULE
    logida ikkalasi ham shu ONNX yuklash oynasida ko'rinadi). Endi bu
    yuklash boshqa prewarm qatlamlari (Groq, vector_memory) kabi startupda,
    fon threadida, foydalanuvchi hali gapirmasdan oldin bajariladi —
    identify() keyinchalik chaqirilsa _load() darhol qaytadi (_loaded=True),
    hech qanday qo'shimcha kechikish yo'q."""
    if not profile_exists():
        # Egasi hali ro'yxatdan o'tmagan — modelni oldindan yuklashning
        # hojati yo'q (identify() baribir _owner_embed=None qaytaradi).
        # Kamera guard ham shu holatda ishga tushmaydi (start_camera_guard).
        return
    try:
        _load()
        log.info("[FACE-ARC] InsightFace modeli oldindan isitildi (prewarm)")
    except Exception as e:
        log.debug("[FACE-ARC] prewarm xato: %s", e)


def get_status() -> dict:
    _load()
    return {
        "profile_exists": profile_exists(),
        "owner":          _owner_info.get("name", ""),
        "enrolled_at":    _owner_info.get("enrolled_at", ""),
        "method":         "arcface_512dim",
        "threshold":      THRESHOLD,
        "model_loaded":   _app is not None,
    }


def get_status_cheap() -> dict:
    """get_status() bilan bir xil, lekin OG'IR modelni yuklamaydi (_load()
    chaqirmaydi) — faqat egasi ismi/vaqti kerak bo'lganda (masalan main.py
    startup GUARDIAN xabarida) ASOSIY (main) threadda xavfsiz chaqirish
    uchun. Modelni yuklash fon prewarm threadlariga (neurokey_prewarm.py,
    ArcFace-preload) qoldiriladi — shu bilan main thread hech qachon
    InsightFace .prepare() poygasini "yutib" qolmaydi (qarang _load()
    tepasidagi RACE-CONDITION FIX izohi)."""
    info = {}
    if os.path.exists(INFO_PATH):
        try:
            with open(INFO_PATH, encoding="utf-8") as f:
                info = json.load(f)
        except Exception:
            pass
    return {
        "profile_exists": profile_exists(),
        "owner":          info.get("name", ""),
        "enrolled_at":    info.get("enrolled_at", ""),
        "method":         "arcface_512dim",
        "threshold":      THRESHOLD,
        "model_loaded":   bool(_loaded and _app is not None),
    }
