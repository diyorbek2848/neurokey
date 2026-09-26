# -*- coding: utf-8 -*-
"""
NeuroKey Full-Screen HUD
========================
Layout (2026 — soddalashtirilgan, bitta "core" HUD):
  Markazda PLASMA ORB (ovozga reaktiv) + ECG chizig'i — DEFAULT.
  Ikki yon panel (chap: CPU/GPU/tizim statistikasi, o'ng: NeuroKey holati)
  DEFAULT holatda YASHIRIN — 'H' tugmasi bilan kerak bo'lsa yoqiladi (debug).

Black background, fullscreen, gold-amber theme.
Q / ESC to quit.  H = yon panellarni ko'rsatish/yashirish.
"""
import math, time, threading, datetime, collections, os, json
import numpy as np
import cv2
import pyaudiowpatch as pyaudio
import psutil

# ── Try GPU stats ─────────────────────────────────────────────────────────────
try:
    import GPUtil
    _GPU_AVAIL = True
except ImportError:
    _GPU_AVAIL = False

# ── Get screen resolution ─────────────────────────────────────────────────────
_tmp = np.zeros((1,1,3), np.uint8)
cv2.namedWindow("__tmp__", cv2.WINDOW_NORMAL)
cv2.setWindowProperty("__tmp__", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
cv2.imshow("__tmp__", _tmp)
cv2.waitKey(1)
SW = cv2.getWindowImageRect("__tmp__")[2]
SH = cv2.getWindowImageRect("__tmp__")[3]
cv2.destroyWindow("__tmp__")
if SW <= 0 or SH <= 0:
    SW, SH = 1920, 1080

print(f"Screen: {SW}x{SH}")

# ── Layout ─────────────────────────────────────────────────────────────────────
# Panel width = 22% of screen each side
PNL_W    = int(SW * 0.26)
ORB_X0   = PNL_W
ORB_X1   = SW - PNL_W
ORB_DISP_W = ORB_X1 - ORB_X0   # display width for orb
ORB_DISP_H = SH                  # full height

# Orb renders at SQUARE canvas (fast) then letterboxed into display area
ORB_SZ   = 480                   # render at 480×480 square (fast!)
ORB_W    = ORB_SZ
ORB_H    = ORB_SZ

# Letterbox: center the square orb in the display area
_orb_disp_x = (ORB_DISP_W - ORB_SZ) // 2   # horizontal offset within orb zone
_orb_disp_y = (SH - ORB_SZ) // 2            # vertical offset

# Orb parameters
CX_ORB  = ORB_W // 2
CY_ORB  = ORB_H // 2
R0      = int(ORB_SZ * 0.38)
TILT    = 0.27

# ── Audio ─────────────────────────────────────────────────────────────────────
CHUNK  = 1024
GAIN   = 8.0
SMOOTH = 0.10

# ── Intro ─────────────────────────────────────────────────────────────────────
INTRO_DUR = 3.5
FADE_DUR  = 1.2

# ── Shared state ──────────────────────────────────────────────────────────────
_vol_raw  = 0.0
_vol      = 0.0
_running  = True
_lock     = threading.Lock()
_nk_status = {"status": "Active", "audio": "Loopback", "errors": "None", "fps": 0}

# ── Colors (BGR) ──────────────────────────────────────────────────────────────
COL_GOLD   = (0,  180, 255)   # gold
COL_AMBER  = (0,  120, 220)   # amber
COL_DIM    = (0,   50, 100)   # dim
COL_WHITE  = (200, 220, 255)  # text
COL_RED    = (40,  40, 200)   # error red
COL_GREEN  = (80, 200,  80)   # ok green
COL_PANEL  = (8,   12,  18)   # panel background (very dark)
COL_BORDER = (0,   80, 180)   # panel border

# ── Colour themes (BGR float32) ────────────────────────────────────────────────
_THEMES = [
    # 0 - Gold / Amber (default)
    dict(nuc_core=np.array([0.80,0.95,1.00],np.float32),
         nuc_ring=np.array([0.00,0.52,1.00],np.float32),
         fil_hot =np.array([0.00,0.65,1.00],np.float32),
         fil_warm=np.array([0.00,0.38,0.95],np.float32),
         fil_cool=np.array([0.00,0.18,0.60],np.float32),
         fil_dim =np.array([0.00,0.08,0.30],np.float32),
         ring_dot=np.array([0.00,0.55,1.00],np.float32),
         ring_dim=np.array([0.00,0.20,0.55],np.float32),
         body    =np.array([0.00,0.03,0.15],np.float32),
         rim     =np.array([0.00,0.08,0.32],np.float32),
         intro_p =np.array([0.05,0.45,1.00],np.float32)),
    # 1 - Electric Blue / Cyan
    dict(nuc_core=np.array([1.00,0.98,0.85],np.float32),
         nuc_ring=np.array([0.90,0.65,0.00],np.float32),
         fil_hot =np.array([1.00,0.80,0.10],np.float32),
         fil_warm=np.array([0.80,0.50,0.00],np.float32),
         fil_cool=np.array([0.40,0.25,0.00],np.float32),
         fil_dim =np.array([0.15,0.08,0.00],np.float32),
         ring_dot=np.array([1.00,0.75,0.05],np.float32),
         ring_dim=np.array([0.45,0.25,0.00],np.float32),
         body    =np.array([0.05,0.02,0.00],np.float32),
         rim     =np.array([0.20,0.08,0.00],np.float32),
         intro_p =np.array([0.80,0.55,0.05],np.float32)),
    # 2 - Matrix Green
    dict(nuc_core=np.array([0.80,1.00,0.85],np.float32),
         nuc_ring=np.array([0.00,0.90,0.20],np.float32),
         fil_hot =np.array([0.05,1.00,0.30],np.float32),
         fil_warm=np.array([0.00,0.65,0.10],np.float32),
         fil_cool=np.array([0.00,0.35,0.05],np.float32),
         fil_dim =np.array([0.00,0.12,0.02],np.float32),
         ring_dot=np.array([0.10,1.00,0.35],np.float32),
         ring_dim=np.array([0.00,0.40,0.10],np.float32),
         body    =np.array([0.00,0.05,0.01],np.float32),
         rim     =np.array([0.00,0.15,0.03],np.float32),
         intro_p =np.array([0.05,0.80,0.20],np.float32)),
    # 3 - Violet / Purple
    dict(nuc_core=np.array([1.00,0.90,1.00],np.float32),
         nuc_ring=np.array([0.80,0.20,0.85],np.float32),
         fil_hot =np.array([0.90,0.30,1.00],np.float32),
         fil_warm=np.array([0.60,0.15,0.75],np.float32),
         fil_cool=np.array([0.30,0.05,0.40],np.float32),
         fil_dim =np.array([0.10,0.00,0.15],np.float32),
         ring_dot=np.array([0.85,0.25,1.00],np.float32),
         ring_dim=np.array([0.35,0.08,0.45],np.float32),
         body    =np.array([0.03,0.00,0.06],np.float32),
         rim     =np.array([0.10,0.02,0.18],np.float32),
         intro_p =np.array([0.55,0.15,0.80],np.float32)),
]
_THEME_NAMES = ["Gold", "Blue", "Green", "Violet"]
_theme_idx   = 0
P = {k: v.copy() for k, v in _THEMES[0].items()}   # active palette

# ── HUD toggles ─────────────────────────────────────────────────────────────────
# Default OFF (2026): faqat markaziy "core" HUD (plasma orb + ECG) ko'rsatiladi —
# ikki yon panel (chap: CPU/GPU/tizim statistikasi, o'ng: NeuroKey holati)
# yashirilgan. Kerak bo'lsa 'H' tugmasi bilan yoqiladi (pastga qarang).
_show_panels = False
GAIN_STEPS   = [4.0, 8.0, 16.0, 32.0]
_gain_idx    = 1   # default = GAIN_STEPS[1] = 8.0

# ── Pulse rings ──────────────────────────────────────────────────────────────────
_pulses     = []          # list of (birth_time,) float values
PULSE_DUR   = 1.6         # seconds for a pulse to expand and fade
PULSE_THRESH= 0.10        # volume threshold to spawn a pulse
PULSE_COOL  = 0.28        # minimum seconds between two pulses

# ── Waveform history ─────────────────────────────────────────────────────────────
WAVE_HIST   = 140
_vol_hist   = collections.deque([0.0]*WAVE_HIST, maxlen=WAVE_HIST)

# ── CPU/GPU sparkline history ─────────────────────────────────────────────────────
SPARK_N     = 60
_cpu_hist   = collections.deque([0.0]*SPARK_N, maxlen=SPARK_N)
_gpu_hist   = collections.deque([0.0]*SPARK_N, maxlen=SPARK_N)

# ── Real Graph-Theoretic Consciousness Metrics (phi_real.py) ─────────────────
_phi_real         = {}      # compute_all() result dict
_phi_real_loading = True    # True while background thread is running
_bench_tab        = 0       # cycling tab 0-3
_bench_tab_t      = 0.0     # last tab-switch time

def _load_phi_real(force=False):
    global _phi_real, _phi_real_loading
    _phi_real_loading = True
    try:
        from phi_real import compute_all
        _phi_real = compute_all(force=force)
    except Exception as e:
        _phi_real = {"error": str(e)}
    finally:
        _phi_real_loading = False

# Load in background so HUD starts instantly
threading.Thread(target=_load_phi_real, daemon=True).start()

# B key: force recompute
def _recompute_phi():
    global _phi_real_loading
    if not _phi_real_loading:
        threading.Thread(target=lambda: _load_phi_real(force=True), daemon=True).start()
        print("Real phi metrics recomputing (background)...")

# ── NeuroKey Live State Bridge ────────────────────────────────────────────────
_NK_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'neurokey_state.json')
_nk = {
    "mode":                "idle",      # idle | listening | thinking | speaking | error
    "last_input":          "",          # last user utterance
    "last_output":         "",          # last NeuroKey response
    "modules_active":      [],          # list of active consciousness modules
    "emotion":             "neutral",   # current emotion
    "consciousness_score": 0.0,         # 0.0-1.0
    "face_owner":          "",          # "Diyorbek (0.82)" yoki ""
    "face_known":          False,       # egasimi?
    "face_emotion":        "",          # "happy", "sad", "neutral" ...
    "timestamp":           0.0,
}
_nk_read_at = 0.0

def _read_nk_state():
    """Read neurokey_state.json at most every 0.4 s (cached otherwise)."""
    global _nk, _nk_read_at
    now = time.time()
    if now - _nk_read_at < 0.4:
        return _nk
    _nk_read_at = now
    try:
        if os.path.exists(_NK_STATE_PATH):
            with open(_NK_STATE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _nk.update(data)
    except Exception:
        pass
    return _nk

# ── Mic input stream (reacts to user's voice, separate from loopback) ─────────
_mic_vol    = 0.0
_mic_lock   = threading.Lock()
_MIC_SMOOTH = 0.12
_MIC_GAIN   = 6.0

def _mic_cb(in_data, fc, ti, st):
    global _mic_vol
    d   = np.frombuffer(in_data, np.float32)
    rms = float(np.sqrt(np.mean(d**2))) * _MIC_GAIN
    with _mic_lock:
        _mic_vol = _mic_vol * (1. - _MIC_SMOOTH) + rms * _MIC_SMOOTH
    return (None, pyaudio.paContinue)

# ── ECG heartbeat display ─────────────────────────────────────────────────────
_ECG_N    = 600                    # rolling sample buffer size
_ecg_buf  = np.zeros(_ECG_N, np.float32)
_ecg_write          = 0            # next write position
_ecg_last_beat_samp = -9999        # sample index of last R-peak
_ecg_sample_count   = 0            # total samples written since start
_ECG_SPS  = 150                    # scroll speed: 150 samples/second

def _make_pqrst(n=90):
    """Synthetic PQRST one-beat ECG template."""
    t  = np.linspace(0., 1., n, dtype=np.float32)
    p  =  0.14 * np.exp(-((t-0.10)/0.045)**2)   # P wave  (small bump)
    q  = -0.08 * np.exp(-((t-0.29)/0.018)**2)   # Q dip
    r  =  1.00 * np.exp(-((t-0.33)/0.018)**2)   # R spike (tallest)
    s  = -0.22 * np.exp(-((t-0.38)/0.018)**2)   # S dip
    tw =  0.20 * np.exp(-((t-0.60)/0.085)**2)   # T wave  (broad bump)
    return (p + q + r + s + tw).astype(np.float32)
_ECG_TMPL   = _make_pqrst(90)
_ECG_TMPL_N = len(_ECG_TMPL)

# ── Orb pixel grids (relative to orb canvas center) ───────────────────────────
_xa_o = (np.arange(ORB_W) - CX_ORB).astype(np.float32)
_ya_o = (np.arange(ORB_H) - CY_ORB).astype(np.float32)
PX_O, PY_O = np.meshgrid(_xa_o, _ya_o)
DIST_O = np.sqrt(PX_O**2 + PY_O**2).astype(np.float32)
D2_O   = (PX_O**2 + PY_O**2).astype(np.float64)   # precomputed, reused in nucleus

# ── Orb vignette: smoothly fades canvas edges → pure black (hides rectangle) ──
_VIG_R0 = ORB_SZ * 0.42          # start fading at 42% half-canvas (≈201 px)
_VIG_R1 = ORB_SZ * 0.505         # fully black at 50.5% half-canvas (= just beyond edge)
_ORB_VIG = np.clip(1.0 - (DIST_O - _VIG_R0) / (_VIG_R1 - _VIG_R0),
                   0., 1.).astype(np.float32)[:, :, None]   # (H,W,1) for broadcast

# ── Nucleus sub-canvas (only compute exp() on small center crop, ~7× faster) ──
_NRAD  = 90                              # half-size of nucleus crop in pixels
_NX0   = CX_ORB - _NRAD;  _NX1 = CX_ORB + _NRAD
_NY0   = CY_ORB - _NRAD;  _NY1 = CY_ORB + _NRAD
_NUC_D2   = D2_O  [_NY0:_NY1, _NX0:_NX1]      # (180,180) float64 view
_NUC_DIST = DIST_O[_NY0:_NY1, _NX0:_NX1]      # (180,180) float32 view

# ── Rotation helpers ──────────────────────────────────────────────────────────
def _ry(pts, a):
    c,s = math.cos(a),math.sin(a)
    return np.stack([pts[:,0]*c+pts[:,2]*s, pts[:,1], -pts[:,0]*s+pts[:,2]*c],1)
def _rx(pts, a):
    c,s = math.cos(a),math.sin(a)
    return np.stack([pts[:,0], pts[:,1]*c-pts[:,2]*s, pts[:,1]*s+pts[:,2]*c],1)
def _project(pts3, rot, R_cur):
    p  = _rx(_ry(pts3,rot),TILT)
    sx = np.clip((CX_ORB+p[:,0]).astype(np.int32),0,ORB_W-1)
    sy = np.clip((CY_ORB+p[:,1]).astype(np.int32),0,ORB_H-1)
    dp = ((p[:,2]+R_cur)/(2.0*R_cur)).clip(0.,1.)
    return sx,sy,dp

def _make_arc(ad, t, R_cur):
    """Build one arc using precomputed sv/rv/tilt stored in the arc dict."""
    sv      = ad['_sv']
    r_v     = ad['_rv'] * (R_cur / R0)        # scale to current orb radius
    th_v    = ad['theta0'] + ad['span'] * sv
    if ad['noise_amp'] > 0.:
        th_v = th_v + ad['noise_amp'] * (
            np.sin(sv*7.1  + t*2.1 + ad['theta0']*2.5) * 0.50 +
            np.cos(sv*13.7 + t*1.5 + ad['theta0']*1.7) * 0.30 +
            np.sin(sv*29.3 + t*0.9)                     * 0.20)
    xl = r_v * np.cos(th_v)
    yl = r_v * np.sin(th_v)
    cX, sX = ad['_cX'], ad['_sX']
    y1 = yl * cX;  z1 = yl * sX        # zl=0 so cross-terms vanish
    cZ, sZ = ad['_cZ'], ad['_sZ']
    x2 = xl * cZ - y1 * sZ
    y2 = xl * sZ + y1 * cZ
    return np.stack([x2, y2, z1], 1).astype(np.float32)

# ── Arc catalogue ─────────────────────────────────────────────────────────────
import random as _rr
_rs = _rr.Random(777)
_rng= np.random.RandomState(42)
_ARC_DEF=[]
for i in range(10):
    _ARC_DEF.append(dict(theta0=math.tau*i/10,span=_rs.uniform(0.7,1.8),
        height=_rs.uniform(0.30,0.70),tilt_x=_rs.uniform(-1.5,1.5),
        tilt_z=_rs.uniform(-math.pi,math.pi),n=60,noise_amp=0.22,scale=1.15,
        co='fil_warm',ci='fil_hot',to=3,ti=2))
for i in range(6):
    _ARC_DEF.append(dict(theta0=math.tau*i/6,span=math.tau*_rs.uniform(0.35,0.68),
        height=_rs.uniform(0.01,0.06),tilt_x=math.pi/2+_rs.uniform(-0.28,0.28),
        tilt_z=_rs.uniform(-0.6,0.6),n=70,noise_amp=0.014,scale=0.70,
        co='fil_cool',ci='fil_warm',to=2,ti=1))
for i in range(12):
    _ARC_DEF.append(dict(theta0=math.tau*i/12+math.pi/12,span=_rs.uniform(0.4,1.3),
        height=_rs.uniform(0.10,0.42),tilt_x=_rs.uniform(-1.57,1.57),
        tilt_z=_rs.uniform(-math.pi,math.pi),n=40,noise_amp=0.15,scale=0.58,
        co='fil_cool',ci='fil_warm',to=2,ti=1))
for i in range(14):
    _ARC_DEF.append(dict(theta0=math.tau*i/14+_rs.uniform(-0.2,0.2),
        span=_rs.uniform(0.15,0.75),height=_rs.uniform(0.01,0.20),
        tilt_x=_rs.uniform(-1.57,1.57),tilt_z=_rs.uniform(-math.pi,math.pi),
        n=25,noise_amp=0.20,scale=0.26,co='fil_dim',ci='fil_cool',to=1,ti=1))

# Precompute per-arc sv, rv (scaled to R0) and zero arrays → skip per-frame alloc
for _ad in _ARC_DEF:
    _n = _ad['n']
    _sv = np.linspace(0., 1., _n+1, dtype=np.float32)
    _ad['_sv']  = _sv
    _ad['_rv']  = R0 * (1.0 + _ad['height'] * np.sin(math.pi * _sv))
    _ad['_zl']  = np.zeros(_n+1, np.float32)
    _ad['_cX'], _ad['_sX'] = math.cos(_ad['tilt_x']), math.sin(_ad['tilt_x'])
    _ad['_cZ'], _ad['_sZ'] = math.cos(_ad['tilt_z']), math.sin(_ad['tilt_z'])

N_P=420
_p_th =_rng.uniform(0,math.tau,N_P).astype(np.float32)
_p_ph =_rng.uniform(0.06,math.pi-0.06,N_P).astype(np.float32)
_p_r  =(_rng.uniform(0.80,1.65,N_P)*R0).astype(np.float32)
_p_vt =_rng.uniform(0.06,0.52,N_P).astype(np.float32)
_p_ph2=_rng.uniform(0,math.tau,N_P).astype(np.float32)
_p_sz =_rng.randint(1,4,N_P)
_p_br =_rng.uniform(0.18,1.00,N_P).astype(np.float32)
_p_hot=_p_br>0.62

N_ORB=160
_o_ang=np.linspace(0,math.tau,N_ORB,endpoint=False,dtype=np.float32)
_o_R  =(_rng.uniform(1.38,1.55,N_ORB)*R0).astype(np.float32)
_o_br =_rng.uniform(0.20,1.00,N_ORB).astype(np.float32)
_o_sz =_rng.randint(1,4,N_ORB)
_o_hot=_o_br>0.55
N_ORB2=90
_o2ang=np.linspace(0,math.tau,N_ORB2,endpoint=False,dtype=np.float32)
_o2br =_rng.uniform(0.15,0.80,N_ORB2).astype(np.float32)  # noqa
_O2T  =0.55

N_I=500
_i_start=(_rng.uniform(-1,1,(N_I,3))*R0*4.0).astype(np.float32)
_i_br   =_rng.uniform(0.4,1.0,N_I).astype(np.float32)
_i_end  =np.zeros((N_I,3),np.float32)
for _j in range(N_I):
    _th=_rng.uniform(0,math.tau); _ph=_rng.uniform(0,math.pi)
    _r=R0*_rng.uniform(0.90,1.10)
    _i_end[_j]=[_r*math.sin(_ph)*math.cos(_th),
                _r*math.sin(_ph)*math.sin(_th),_r*math.cos(_ph)]

# ── Audio callback ────────────────────────────────────────────────────────────
def _audio_cb(in_data, fc, ti, st):
    global _vol_raw, _vol
    d = np.frombuffer(in_data, np.float32)
    rms = float(np.sqrt(np.mean(d**2)))*GAIN
    with _lock:
        _vol_raw = _vol_raw*(1.-SMOOTH)+rms*SMOOTH
        _vol = min(1.0,_vol_raw)
    return (None, pyaudio.paContinue)

# ── Loopback finder ───────────────────────────────────────────────────────────
def find_loopback(pa):
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        spk    = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        for lb in pa.get_loopback_device_info_generator():
            if spk["name"] in lb["name"]:
                return lb["index"], lb["maxInputChannels"], int(lb["defaultSampleRate"]), "Loopback"
        for lb in pa.get_loopback_device_info_generator():
            return lb["index"], lb["maxInputChannels"], int(lb["defaultSampleRate"]), "Loopback(fallback)"
    except Exception as e:
        pass
    return None, 2, 44100, "Error"

# ── Fast half-res bloom ───────────────────────────────────────────────────────
def bloom_fast(canvas, ksize, strength):
    W_c,H_c = canvas.shape[1],canvas.shape[0]
    small = cv2.resize(canvas,(W_c//2,H_c//2),interpolation=cv2.INTER_LINEAR)
    k = int(ksize)|1
    glow = cv2.GaussianBlur(np.clip(small-0.05,0.,None),(k,k),0)
    up   = cv2.resize(glow,(W_c,H_c),interpolation=cv2.INTER_LINEAR)
    return np.clip(canvas+up*strength,0.,None)

def tone_map(c):
    return (c*(2.51*c+0.03))/(c*(2.43*c+0.59)+0.14)

# ── Orb draw functions ────────────────────────────────────────────────────────
def draw_sphere_body(cv, R_cur, vol):
    rad=(DIST_O/R_cur).clip(0.,2.)
    inside=(rad<1.0).astype(np.float32)*(rad**2.2)*(0.45+vol*0.20)
    cv+=inside[:,:,None]*P['body']
    rim=np.exp(-(DIST_O-R_cur)**2/(R_cur*0.030)**2)*(1.20+vol*0.80)
    cv+=rim[:,:,None]*P['rim']

def draw_arcs(cv, rot, t, vol, R_cur):
    boost=1.0+vol*2.5
    for ad in _ARC_DEF:
        pts3=_make_arc(ad, t, R_cur)
        sx,sy,dp=_project(pts3,rot,R_cur)
        mask=dp>0.22
        if mask.sum()<2: continue
        dp_m = float(dp[mask].mean()) * ad['scale'] * boost   # compute once
        pts2d=np.stack([sx[mask],sy[mask]],1).astype(np.int32)
        cv2.polylines(cv,[pts2d],False,(P[ad['co']]*(dp_m*0.26)).tolist(),ad['to'],cv2.LINE_AA)
        cv2.polylines(cv,[pts2d],False,(P[ad['ci']]*dp_m).tolist(),ad['ti'],cv2.LINE_AA)

_RING_LATS = [(0.0,0.48,2),(math.radians(32),0.18,1),(-math.radians(32),0.18,1),
              (math.radians(58),0.07,1),(-math.radians(58),0.07,1)]
_RING_THS  = np.linspace(0, math.tau, 111, dtype=np.float32)[:-1]  # precomputed
_RING_N    = len(_RING_THS)

def draw_rings(cv, rot, t, vol, R_cur):
    boost=1.0+vol*3.0
    for lat,b0,th in _RING_LATS:
        rl=float(R_cur*math.cos(lat)); yl=float(R_cur*math.sin(lat))
        pts3=np.stack([rl*np.cos(_RING_THS),np.full(_RING_N,yl,np.float32),rl*np.sin(_RING_THS)],1)
        sx,sy,dp=_project(pts3,rot,R_cur)
        mask=dp>0.18
        if mask.sum()<2: continue
        b=b0*float(dp[mask].mean())*boost
        pts2d=np.stack([sx[mask],sy[mask]],1).astype(np.int32)
        cv2.polylines(cv,[pts2d],False,(P['fil_warm']*b).tolist(),th,cv2.LINE_AA)

def draw_orbit_rings(cv, rot, t, vol, R_cur):
    boost=1.0+vol*4.5
    ths1=_o_ang+t*0.22
    pts3=np.stack([_o_R*np.cos(ths1),np.zeros(N_ORB,np.float32),_o_R*np.sin(ths1)],1).astype(np.float32)
    sx,sy,dp=_project(pts3,rot,R_cur); mask=dp>0.15; br=_o_br*dp*boost
    bm=mask&_o_hot;  np.add.at(cv,(sy[bm],sx[bm]),P['ring_dot']*br[bm,None])
    dm=mask&~_o_hot; np.add.at(cv,(sy[dm],sx[dm]),P['ring_dim']*br[dm,None]*0.7)
    for k in np.where(mask&(_o_sz==3))[0]:       # only largest dots (sz==3 ≈ 1/3 of set)
        cv2.circle(cv,(int(sx[k]),int(sy[k])),3,
                   (P['ring_dot' if _o_hot[k] else 'ring_dim']*float(br[k])*0.4).tolist(),-1)
    ths2=_o2ang+t*(-0.14); ct,st=math.cos(_O2T),math.sin(_O2T)
    R2=R_cur*1.25; x2=R2*np.cos(ths2); z2=R2*np.sin(ths2)
    pts3b=np.stack([x2.astype(np.float32),(z2*st).astype(np.float32),(z2*ct).astype(np.float32)],1)
    sx2,sy2,dp2=_project(pts3b,rot,R_cur); mask2=dp2>0.15; br2=_o2br*dp2*boost*0.50
    bm2=mask2&(_o2br>0.50)
    np.add.at(cv,(sy2[bm2],sx2[bm2]),P['ring_dot']*br2[bm2,None])
    dm2=mask2&~(_o2br>0.50)
    np.add.at(cv,(sy2[dm2],sx2[dm2]),P['ring_dim']*br2[dm2,None])

def draw_particles(cv, rot, t, vol, R_cur):
    boost=1.0+vol*3.0
    ths=_p_th+t*_p_vt*(0.50+vol*0.55); phs=_p_ph+t*0.035
    rr=_p_r*(0.93+0.07*np.sin(t*1.9+_p_ph2))
    sph=np.sin(phs); cph=np.cos(phs)
    pts3=np.stack([rr*sph*np.cos(ths),rr*sph*np.sin(ths),rr*cph],1).astype(np.float32)
    sx,sy,dp=_project(pts3,rot,R_cur); mask=dp>0.16; br=_p_br*dp*boost
    bm=mask&_p_hot;  np.add.at(cv,(sy[bm],sx[bm]),P['fil_hot']*br[bm,None]*0.72)
    dm=mask&~_p_hot; np.add.at(cv,(sy[dm],sx[dm]),P['ring_dim']*br[dm,None]*0.52)
    for k in np.where(mask&(_p_sz==3))[0]:       # only largest particles (sz==3 ≈ 1/3 of set)
        cv2.circle(cv,(int(sx[k]),int(sy[k])),3,
                   (P['fil_hot' if _p_hot[k] else 'ring_dim']*float(br[k])*0.38).tolist(),-1)

def draw_nucleus(cv, t, vol, R_cur):
    # All exp() ops on the tiny 180×180 sub-canvas only (7× fewer elements)
    sub = cv[_NY0:_NY1, _NX0:_NX1]           # view - writes back to cv
    d2   = _NUC_D2                             # precomputed constant
    dist = _NUC_DIST
    pulse = math.sin(t * math.tau * 1.28)
    rn    = max((1.8 + 1.0*abs(pulse)) * (1.0 + vol*5.0), 0.5)
    g_c   = np.exp(-d2 / rn**2) * (14.0 + vol*40.0)
    g_h   = np.exp(-d2 / (R_cur*0.09)**2) * (0.65 + vol*2.8)
    g_a   = np.exp(-d2 / (R_cur*0.38)**2) * (0.10 + vol*0.45)
    sub  += g_c.astype(np.float32)[:,:,None] * P['nuc_core'] * 0.38
    sub  += g_h.astype(np.float32)[:,:,None] * P['nuc_ring'] * 0.48
    sub  += g_a.astype(np.float32)[:,:,None] * P['nuc_ring'] * 0.16
    for rr in (R_cur*0.06, R_cur*0.11):
        sub += np.exp(-(dist-rr)**2 / max((rr*0.22)**2, 0.1))[:,:,None] * P['nuc_ring'] * (0.28+vol*0.75)
    if vol > 0.06:
        wr = R_cur * 0.15 * vol
        sub += np.exp(-(dist-wr)**2 / max((wr*0.25)**2, 0.1))[:,:,None] * P['nuc_ring'] * vol * 1.6

def draw_intro(cv, prog, rot, R_cur):
    ease=1.0-(1.0-min(prog,1.0))**2.8
    pos=_i_start*(1.0-ease)+_i_end*ease
    sx,sy,dp=_project(pos,rot,R_cur)
    br=_i_br*(0.25+ease*0.75)
    mask=(sx>=0)&(sx<ORB_W)&(sy>=0)&(sy<ORB_H)
    np.add.at(cv,(sy[mask],sx[mask]),P['intro_p']*br[mask,None])

# ── Lightning bolts (on orb canvas) ──────────────────────────────────────────
_LT_RNG = np.random.RandomState(0)
def draw_lightning(cv, t, vol, R_cur):
    """Jagged bolts radiating from nucleus when voice is active."""
    if vol < 0.25: return
    n_bolts = 1 + int(vol * 3.5)
    seed = int(t * 25) & 0xFFFF
    _LT_RNG.seed(seed)
    br = min(vol * 2.2, 2.0)
    col_inner = (P['nuc_core'] * br).tolist()
    col_outer = (P['fil_hot']  * br * 0.5).tolist()
    for _ in range(n_bolts):
        angle = _LT_RNG.uniform(0, math.tau)
        length = R_cur * (1.0 + vol * 1.8)
        n_segs = 7
        pts = [[CX_ORB, CY_ORB]]
        a = angle
        for seg in range(n_segs):
            a  += _LT_RNG.uniform(-0.55, 0.55)
            frac = (seg + 1) / n_segs
            d  = length * frac / n_segs * n_segs   # cumulative distance
            nx = int(CX_ORB + math.cos(a) * d * (frac**0.6))
            ny = int(CY_ORB + math.sin(a) * d * (frac**0.6))
            pts.append([nx, ny])
        pts2d = np.array(pts, np.int32)
        cv2.polylines(cv, [pts2d], False, col_outer, 2, cv2.LINE_AA)
        cv2.polylines(cv, [pts2d], False, col_inner, 1, cv2.LINE_AA)

# ── Pulse rings (on main frame) ───────────────────────────────────────────────
def draw_pulse_rings(frame, t, cx, cy):
    """Expanding gold rings that fade as they grow."""
    global _pulses
    alive = []
    for birth in _pulses:
        age = t - birth
        if age >= PULSE_DUR: continue
        alive.append(birth)
        prog  = age / PULSE_DUR
        ease  = 1.0 - (1.0 - prog)**2      # ease-out
        r     = int(R0 * 0.45 + ease * R0 * 3.2)
        alpha = max(0.0, 1.0 - prog * 1.25)
        col   = (int(0), int(130*alpha), int(240*alpha))
        thick = max(1, int((1.0-prog)*3))
        cv2.circle(frame, (cx, cy), r, col, thick, cv2.LINE_AA)
        # inner bright ring at half-life
        if prog < 0.35:
            r2  = int(R0 * 0.45 + ease * R0 * 1.2)
            a2  = (0.35 - prog) / 0.35
            cv2.circle(frame, (cx, cy), r2,
                       (int(0), int(180*a2), int(255*a2)), 1, cv2.LINE_AA)
    _pulses = alive

# ── Waveform bar (below orb on main frame) ───────────────────────────────────
def draw_waveform(frame, x0, y0, w, h):
    """Horizontal audio waveform using rolling vol history."""
    pts = list(_vol_hist)
    n   = len(pts)
    if n < 4: return
    cv2.rectangle(frame, (x0, y0), (x0+w, y0+h), (6, 9, 14), -1)
    # centre line
    cy_w = y0 + h//2
    cv2.line(frame, (x0, cy_w), (x0+w, cy_w), (20, 35, 50), 1)
    xs = np.linspace(x0, x0+w-1, n).astype(np.int32)
    arr = np.array(pts, np.float32)
    # mirror top & bottom (oscilloscope look)
    half = int(h * 0.45)
    ys_top = (cy_w - arr * half).clip(y0, y0+h-1).astype(np.int32)
    ys_bot = (cy_w + arr * half).clip(y0, y0+h-1).astype(np.int32)
    p_top = np.stack([xs, ys_top], 1)
    p_bot = np.stack([xs, ys_bot], 1)
    # fill between top & bottom with dim bars
    for i in range(0, n, 3):
        v = int(arr[i] * half)
        if v > 0:
            cv2.line(frame, (int(xs[i]), cy_w-v), (int(xs[i]), cy_w+v),
                     (0, int(60*arr[i]+20), int(120*arr[i]+40)), 1)
    cv2.polylines(frame, [p_top], False, COL_AMBER, 1, cv2.LINE_AA)
    cv2.polylines(frame, [p_bot], False, COL_AMBER, 1, cv2.LINE_AA)
    # border
    cv2.rectangle(frame, (x0, y0), (x0+w, y0+h), COL_DIM, 1)

# ── ECG: advance rolling buffer (call every frame) ───────────────────────────
def update_ecg(cpu_pct, vol, fps_cur):
    global _ecg_write, _ecg_last_beat_samp, _ecg_sample_count
    spf = max(1, round(_ECG_SPS / max(fps_cur, 15)))     # samples to write this frame
    bpm = max(40., min(170., 55. + cpu_pct * 1.15 + vol * 30.))
    spb = int(_ECG_SPS * 60. / bpm)                      # samples per beat
    for _ in range(spf):
        since = _ecg_sample_count - _ecg_last_beat_samp
        if since >= spb:
            _ecg_last_beat_samp = _ecg_sample_count
        pos = _ecg_sample_count - _ecg_last_beat_samp
        if 0 <= pos < _ECG_TMPL_N:
            val = float(_ECG_TMPL[pos] * (1.0 + vol * 0.55))
        else:
            val = 0.007 * math.sin(_ecg_sample_count * 0.053)   # baseline wander
        _ecg_buf[_ecg_write] = val
        _ecg_write = (_ecg_write + 1) % _ECG_N
        _ecg_sample_count += 1


def draw_ecg(frame, x0, y0, w, h, cpu_pct, vol):
    """Full-width ECG heartbeat monitor below the orb - green plasma aesthetic."""
    bpm     = int(max(40., min(170., 55. + cpu_pct * 1.15 + vol * 30.)))
    bpm_col = COL_GREEN if bpm < 100 else (COL_AMBER if bpm < 140 else COL_RED)

    # ── Background ──────────────────────────────────────────────────────────
    cv2.rectangle(frame, (x0, y0), (x0+w, y0+h), (3, 9, 5), -1)

    # ── Grid lines ──────────────────────────────────────────────────────────
    gc = (0, 24, 13)
    for i in range(1, 8):
        gx = x0 + i * w // 8
        cv2.line(frame, (gx, y0), (gx, y0+h), gc, 1)
    cy_ecg = y0 + int(h * 0.66)
    cv2.line(frame, (x0, cy_ecg), (x0+w, cy_ecg), (0, 40, 20), 1)
    # horizontal mid-grid
    cv2.line(frame, (x0, y0 + h//3), (x0+w, y0 + h//3), (0, 14, 8), 1)

    # ── ECG curve: reorder buffer oldest → newest ────────────────────────────
    buf = (np.concatenate([_ecg_buf[_ecg_write:], _ecg_buf[:_ecg_write]])
           if _ecg_write > 0 else _ecg_buf.copy())
    xs  = np.linspace(x0, x0+w-1, _ECG_N).astype(np.int32)
    amp = int(h * 0.62)
    ys  = (cy_ecg - buf * amp).clip(y0+2, y0+h-3).astype(np.int32)
    pts = np.stack([xs, ys], 1)
    # outer glow (thick dim)
    cv2.polylines(frame, [pts], False, (0, 60, 32), 3, cv2.LINE_AA)
    # main bright line
    cv2.polylines(frame, [pts], False, (55, 235, 95), 2, cv2.LINE_AA)
    # inner highlight on positive peaks only
    mask_up = buf > 0.15
    if mask_up.any():
        xs_hi = xs[mask_up]; ys_hi = ys[mask_up]
        for xi, yi in zip(xs_hi[::4], ys_hi[::4]):
            cv2.circle(frame, (int(xi), int(yi)), 1, (160, 255, 200), -1)

    # ── Scan cursor (right edge = newest sample) ─────────────────────────────
    cx     = int(xs[-1])
    cy_dot = int(ys[-1])
    cv2.line(frame, (cx, y0+1), (cx, y0+h-1), (90, 255, 130), 1)
    cv2.circle(frame, (cx, cy_dot), 4, (180, 255, 220), -1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy_dot), 7, (60, 200, 100), 1, cv2.LINE_AA)

    # ── Labels ──────────────────────────────────────────────────────────────
    put(frame, "CPU VITALS", x0+8, y0+int(LH*0.58), (50, 175, 80), FS*0.68, 1)
    put(frame, f"CPU {cpu_pct:.0f}%", x0+8, y0+h-6, (28, 110, 50), FS*0.60, 1)

    # BPM top-right
    bpm_s  = f"{bpm} BPM"
    bw_px  = cv2.getTextSize(bpm_s, FONT, FS*0.80, 1)[0][0]
    put(frame, bpm_s, x0+w-bw_px-9, y0+int(LH*0.58), bpm_col, FS*0.80, 1)
    # BPM descriptor
    bpm_label = "NORMAL" if bpm < 100 else ("ELEVATED" if bpm < 140 else "CRITICAL")
    bl_px = cv2.getTextSize(bpm_label, FONT, FS*0.54, 1)[0][0]
    put(frame, bpm_label, x0+w-bl_px-9, y0+h-6, bpm_col, FS*0.54, 1)

    # Heartbeat blink dot on R-peak
    since_beat = _ecg_sample_count - _ecg_last_beat_samp
    if since_beat < int(_ECG_SPS * 0.13):
        cv2.circle(frame, (x0+w//2, y0+h-9), 5, bpm_col, -1, cv2.LINE_AA)
        cv2.circle(frame, (x0+w//2, y0+h-9), 9, bpm_col, 1, cv2.LINE_AA)

    # ── Border + corner L-brackets ───────────────────────────────────────────
    cv2.rectangle(frame, (x0, y0), (x0+w, y0+h), (0, 52, 26), 1)
    CL = 14; CT = 2; ga = (65, 215, 85)
    for px, py, sx, sy in ((x0, y0, 1, 1), (x0+w, y0, -1, 1),
                            (x0, y0+h, 1, -1), (x0+w, y0+h, -1, -1)):
        cv2.line(frame, (px, py), (px+sx*CL, py), ga, CT)
        cv2.line(frame, (px, py), (px, py+sy*CL), ga, CT)


# ── Sparkline helper ──────────────────────────────────────────────────────────
def draw_sparkline(frame, x0, y0, w, h, data, col):
    """Mini line graph of last N values."""
    pts = list(data)
    n   = len(pts)
    if n < 2: return
    mx  = max(max(pts), 1.0)
    arr = np.array(pts, np.float32) / mx
    xs  = np.linspace(x0, x0+w-1, n).astype(np.int32)
    ys  = (y0 + h - 1 - arr*(h-2)).clip(y0, y0+h-1).astype(np.int32)
    pts2d = np.stack([xs, ys], 1)
    cv2.rectangle(frame, (x0,y0), (x0+w, y0+h), (5,8,12), -1)
    cv2.polylines(frame, [pts2d], False, col, 1, cv2.LINE_AA)

# ── Panel drawing helpers ─────────────────────────────────────────────────────
FS  = max(0.50, SH/1080*0.64)   # font scale - clear and readable
FT  = 1                           # font thickness (1 = clean, no blur)
LH  = int(SH * 0.044)            # line height
FONT= cv2.FONT_HERSHEY_DUPLEX    # DUPLEX = cleaner letterforms than SIMPLEX

def draw_panel(frame, x0, y0, w, h, title):
    """Draw dark panel with gold border and title."""
    # Background (direct, no alpha copy - fast)
    cv2.rectangle(frame, (x0,y0), (x0+w, y0+h), COL_PANEL, -1)
    # Border
    cv2.rectangle(frame, (x0,y0), (x0+w,y0+h), COL_BORDER, 1)
    # Top accent line
    cv2.line(frame, (x0+4,y0), (x0+w-4,y0), COL_GOLD, 2)
    # Bottom accent line
    cv2.line(frame, (x0+4,y0+h), (x0+w-4,y0+h), COL_DIM, 1)
    # Title
    ts = cv2.getTextSize(title, FONT, FS*1.1, 2)[0]
    tx = x0 + (w-ts[0])//2
    cv2.putText(frame, title, (tx, y0+LH), FONT, FS*1.1, COL_GOLD, 2, cv2.LINE_AA)
    # Title underline
    cv2.line(frame, (x0+8,y0+LH+6), (x0+w-8,y0+LH+6), COL_AMBER, 1)

def draw_bar(frame, x, y, w, h, pct, col_fill, col_bg=(20,25,30)):
    """Horizontal progress bar."""
    cv2.rectangle(frame, (x,y), (x+w,y+h), col_bg, -1)
    fill = int(w * min(pct,1.0))
    if fill > 0:
        cv2.rectangle(frame, (x,y), (x+fill,y+h), col_fill, -1)
    cv2.rectangle(frame, (x,y), (x+w,y+h), COL_DIM, 1)

def pct_col(pct):
    """Color by load: green → amber → red."""
    if pct < 0.6:  return COL_GREEN
    if pct < 0.85: return COL_AMBER
    return COL_RED

def put(frame, text, x, y, col=COL_WHITE, scale=None, thick=FT):
    cv2.putText(frame, text, (x,y), FONT,
                scale if scale else FS, col, thick, cv2.LINE_AA)

# ── System stats (cached per second) ─────────────────────────────────────────
_sys_cache = {}
_sys_last  = 0.0

def get_sys_stats():
    global _sys_cache, _sys_last
    now = time.time()
    if now - _sys_last < 1.0:
        return _sys_cache
    _sys_last = now
    s = {}
    s['cpu']   = psutil.cpu_percent()
    vm = psutil.virtual_memory()
    s['ram_pct'] = vm.percent
    s['ram_gb']  = vm.used / (1024**3)
    s['ram_tot'] = vm.total/ (1024**3)
    try:
        dk = psutil.disk_usage('C:\\')
        s['disk_pct'] = dk.percent
        s['disk_free'] = dk.free / (1024**3)
    except:
        s['disk_pct'] = 0; s['disk_free'] = 0
    try:
        net = psutil.net_io_counters()
        s['net_sent'] = net.bytes_sent / (1024**2)
        s['net_recv'] = net.bytes_recv / (1024**2)
    except:
        s['net_sent'] = s['net_recv'] = 0
    if _GPU_AVAIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                s['gpu_load'] = gpus[0].load*100
                s['gpu_mem']  = gpus[0].memoryUtil*100
                s['gpu_temp'] = gpus[0].temperature
            else:
                s['gpu_load'] = s['gpu_mem'] = s['gpu_temp'] = 0
        except:
            s['gpu_load'] = s['gpu_mem'] = s['gpu_temp'] = 0
    _sys_cache = s
    return s

# ── Mini-card styling ────────────────────────────────────────────────────────
_CARD_BG  = (4, 7, 14)         # near-black tinted background
CGAP      = 6                   # gap between cards
_L_ACC    = (0, 165, 255)       # gold  - left panel accent  (BGR)
_R_ACC    = (210, 100, 10)      # blue  - right panel accent (BGR)

def _card(frame, x0, y0, w, h, title="", acc=_L_ACC):
    """
    Styled mini-card with:
      • Dark background
      • Mid-dim full border
      • Bright corner L-brackets
      • Title inline with a separator line
    Returns (inner_x, inner_y) for content.
    """
    dim = (acc[0]//7,  acc[1]//7,  acc[2]//7)   # very dim for full border
    mid = (acc[0]//3,  acc[1]//3,  acc[2]//3)   # mid for separator

    # Background
    cv2.rectangle(frame, (x0, y0), (x0+w, y0+h), _CARD_BG, -1)

    # Full dim border (gives structure without overpowering)
    cv2.rectangle(frame, (x0, y0), (x0+w, y0+h), dim, 1)

    # Bright corner L-brackets
    CL = min(14, w // 6)
    CT = 2
    for px, py, sx, sy in ((x0,   y0,   1,  1),   # TL
                            (x0+w, y0,  -1,  1),   # TR
                            (x0,   y0+h, 1, -1),   # BL
                            (x0+w, y0+h,-1, -1)):  # BR
        cv2.line(frame, (px, py), (px + sx*CL, py),       acc, CT)
        cv2.line(frame, (px, py), (px,          py+sy*CL), acc, CT)

    # Title + horizontal separator below it
    if title:
        put(frame, title, x0+6, y0+int(LH*0.68), acc, FS*0.74, 1)
        sep_y = y0 + int(LH*0.85)
        cv2.line(frame, (x0+2, sep_y), (x0+w-2, sep_y), mid, 1)
        return x0+6, sep_y + 3

    return x0+6, y0 + int(LH*0.25)


def _section_hdr(frame, x0, y0, w, label, acc):
    """Draws 'SYSTEM' / 'NEUROKEY' header with decorative side lines."""
    ts = cv2.getTextSize(label, FONT, FS*0.85, 2)[0]
    tx = x0 + (w - ts[0]) // 2          # center
    put(frame, label, tx, y0+int(LH*0.75), acc, FS*1.00, 2)
    line_y = y0 + int(LH*0.90)
    # Left  side-line
    cv2.line(frame, (x0, line_y), (tx-6, line_y), mid3(acc), 1)
    # Right side-line
    cv2.line(frame, (tx+ts[0]+6, line_y), (x0+w, line_y), mid3(acc), 1)
    # Dot endpoints
    cv2.circle(frame, (x0, line_y), 2, acc, -1)
    cv2.circle(frame, (x0+w, line_y), 2, acc, -1)
    return y0 + int(LH*1.10)

def mid3(c): return (c[0]//4, c[1]//4, c[2]//4)

# ── Draw left panel: System Status ───────────────────────────────────────────
def draw_left_panel(frame, vol):
    if PNL_W < 80: return
    s   = get_sys_stats()
    PAD = 4
    cw  = PNL_W - PAD*2
    bw  = cw - 10
    bh  = max(6, int(LH*0.36))
    y   = int(SH*0.04)

    # Panel strip background + inner edge separator
    cv2.rectangle(frame, (0, 0), (PNL_W, SH), (3, 5, 10), -1)
    cv2.line(frame, (PNL_W, 0), (PNL_W, SH), mid3(_L_ACC), 1)

    # Section header
    y = _section_hdr(frame, PAD, y, cw, "SYSTEM", _L_ACC)

    A = _L_ACC  # shorthand accent

    def card_bar_spark(title, pct, col, val_txt, spark=None, sp_col=None):
        nonlocal y
        h   = int(LH*2.22)
        ix, iy = _card(frame, PAD, y, cw, h, title, acc=A)
        vw  = int(cw * 0.44)          # big value occupies left 44%
        bww = cw - vw - 8             # bar takes remaining space
        # Big clear value (thick=1 = no blur/overlap)
        put(frame, val_txt, ix, iy+int(LH*0.84), col, FS*1.10, 1)
        # Bar right of value
        draw_bar(frame, ix+vw, iy+int(LH*0.10), bww, bh, pct, col)
        # Sparkline below bar
        if spark is not None:
            draw_sparkline(frame, ix+vw, iy+int(LH*0.10)+bh+4, bww, bh, spark, sp_col or col)
        y += h + CGAP

    def card_bar(title, pct, col, val_txt):
        nonlocal y
        h   = int(LH*2.10)
        ix, iy = _card(frame, PAD, y, cw, h, title, acc=A)
        vw  = int(cw * 0.52)
        bww = cw - vw - 8
        # Big clear value left (thick=1)
        put(frame, val_txt, ix, iy+int(LH*0.84), col, FS*1.05, 1)
        # Bar right
        draw_bar(frame, ix+vw, iy+int(LH*0.25), bww, bh, pct, col)
        y += h + CGAP

    def card_text2(title, line1, line2):
        nonlocal y
        h   = int(LH*2.50)
        ix, iy = _card(frame, PAD, y, cw, h, title, acc=A)
        put(frame, line1, ix, iy+int(LH*0.50), COL_WHITE, FS*0.98, 1)
        put(frame, line2, ix, iy+int(LH*1.28), COL_WHITE, FS*0.98, 1)
        y += h + CGAP

    card_bar_spark("CPU",
        s.get('cpu',0)/100, pct_col(s.get('cpu',0)/100),
        f"{s.get('cpu',0):.0f}%", _cpu_hist, COL_GREEN)

    card_bar("RAM",
        s.get('ram_pct',0)/100, pct_col(s.get('ram_pct',0)/100),
        f"{s.get('ram_gb',0):.1f} / {s.get('ram_tot',0):.0f} GB")

    if _GPU_AVAIL and 'gpu_load' in s:
        # GPU + VRAM in one compact combined card
        h_gv = int(LH*3.15)
        ix_g, iy_g = _card(frame, PAD, y, cw, h_gv, "GPU", acc=A)
        gc   = pct_col(s['gpu_load']/100)
        vc   = pct_col(s['gpu_mem']/100)
        vw   = int(cw*0.44); bww = cw - vw - 8
        # GPU load row: big text + bar + sparkline
        put(frame, f"{s['gpu_load']:.0f}%  {s['gpu_temp']:.0f}C",
            ix_g, iy_g+int(LH*0.84), gc, FS*1.05, 1)
        draw_bar(frame, ix_g+vw, iy_g+int(LH*0.08), bww, bh, s['gpu_load']/100, gc)
        draw_sparkline(frame, ix_g+vw, iy_g+int(LH*0.08)+bh+4, bww, bh, _gpu_hist, (80,180,255))
        # VRAM row below
        iy_v = iy_g + int(LH*1.40)
        put(frame, f"VRAM {s['gpu_mem']:.0f}%",
            ix_g, iy_v+int(LH*0.76), vc, FS*0.96, 1)
        draw_bar(frame, ix_g+vw, iy_v+int(LH*0.14), bww, bh, s['gpu_mem']/100, vc)
        y += h_gv + CGAP

    card_bar("DISK  C:",
        s.get('disk_pct',0)/100, pct_col(s.get('disk_pct',0)/100),
        f"{s.get('disk_free',0):.0f} GB free")

    sent = s.get('net_sent',0); recv = s.get('net_recv',0)
    card_text2("NETWORK",
        f"Up   {sent:.0f} MB",
        f"Dn   {recv:.0f} MB")

    # Clock card - large centered time display
    h_cl = int(LH*1.65)
    ix, iy = _card(frame, PAD, y, cw, h_cl, acc=A)
    now_str = datetime.datetime.now().strftime("%H : %M : %S")
    ts_w = cv2.getTextSize(now_str, FONT, FS*1.06, 1)[0][0]
    cx_off = max(0, (cw - 12 - ts_w) // 2)
    put(frame, now_str, ix+cx_off, iy+int(LH*0.42), COL_AMBER, FS*1.06, 1)
    y += h_cl + CGAP

    # ── Real Graph-Theoretic Consciousness Metrics (cycling) ─────────────────
    global _bench_tab, _bench_tab_t
    BA   = (180, 80, 220)
    BA_L = (170, 120, 230)
    h_bn = min(int(LH * 5.50), SH - y - CGAP - 2)

    if _phi_real_loading and not _phi_real:
        # Computing — show spinner
        ix, iy = _card(frame, PAD, y, cw, h_bn, "CONSCIOUSNESS  1/4", acc=BA)
        put(frame, "Hisoblanmoqda...", ix, iy+int(LH*0.55), BA_L, FS*0.82, 1)
        n_dot = int(time.time() * 2) % 4
        for i in range(4):
            cv2.circle(frame, (ix+i*20+8, iy+int(LH*1.50)), 5,
                       BA if i == n_dot else (50,25,70), -1)
        y += h_bn + CGAP

    elif _phi_real and "n_modules" in _phi_real:
        pr = _phi_real
        ph = pr.get("phi_algebraic",    {})
        ef = pr.get("global_efficiency", {})
        cd = pr.get("causal_density",    {})
        sw = pr.get("small_world",       {})

        # Auto-advance tab every 4 sec
        now = time.time()
        if now - _bench_tab_t > 4.0:
            _bench_tab   = (_bench_tab + 1) % 4
            _bench_tab_t = now

        # ── Per-tab data ────────────────────────────────────────────────────
        if _bench_tab == 0:
            # Phi algebraic (Oizumi 2014)
            phi_v  = ph.get("phi", 0.0)
            tab_name = "PHI  algebraic"
            tab_num  = f"{phi_v:.4f}"
            ref_lbl  = "Oizumi 2014"
            # Bar capped at 1.0; phi_v typically 0-0.2 range, show vs 0.5 ceiling
            bar_val  = min(phi_v / 0.20, 1.0)
            v_col    = COL_AMBER if phi_v > 0.03 else COL_RED
            subs = [
                ("lambda2",  min(ph.get("lambda2",0)/5.0, 1.0),
                 f"{ph.get('lambda2',0):.3f}"),
                ("lam.max",  min(ph.get("lambda_max",0)/50.0, 1.0),
                 f"{ph.get('lambda_max',0):.1f}"),
                ("vs rand",  min(ph.get("phi",0)/max(ph.get("random_baseline",0.001),0.001)/2,1.0),
                 ph.get("vs_random","?")),
            ]
        elif _bench_tab == 1:
            # Global Efficiency (Latora 2001)
            eff_v    = ef.get("efficiency", 0.0)
            tab_name = "GLOBAL  Efficiency"
            tab_num  = f"{eff_v:.4f}"
            ref_lbl  = "Latora 2001"
            bar_val  = min(eff_v, 1.0)
            v_col    = COL_GREEN if eff_v > 0.50 else COL_AMBER
            rp       = ef.get("reachable_pairs", 0)
            mp       = ef.get("max_pairs", 1)
            subs = [
                ("reach",    rp/mp,
                 f"{rp}/{mp}"),
                ("vs rand",  min(eff_v/max(ef.get("random_baseline",0.001),0.001)/2,1.0),
                 ef.get("vs_random","?")),
                ("n_mods",   min(pr.get("n_modules",0)/50.0, 1.0),
                 f"{pr.get('n_modules',0)} mod"),
            ]
        elif _bench_tab == 2:
            # Causal Density (Seth 2011)
            cd_v     = cd.get("cd", 0.0)
            tab_name = "CAUSAL  Density"
            tab_num  = f"{cd_v:.4f}"
            ref_lbl  = "Seth 2011"
            bar_val  = min(cd_v, 1.0)
            v_col    = COL_AMBER if cd_v > 0.10 else COL_RED
            cp       = cd.get("causal_pairs",0)
            tp       = cd.get("total_pairs",1)
            cr       = cd.get("cd_reciprocal", 0.0)
            subs = [
                ("causal",   cd_v,  f"{cp}/{tp}"),
                ("reciproc", min(cr*5,1.0), f"{cr:.4f}"),
                ("edges",    min(pr.get("n_edges",0)/200.0,1.0),
                 f"{pr.get('n_edges',0)} links"),
            ]
        else:
            # Small-World (Watts 1998)
            sig_v    = sw.get("sigma", 0.0)
            tab_name = "SMALL-WORLD  sigma"
            tab_num  = f"{sig_v:.2f}"
            ref_lbl  = "Watts 1998"
            # sigma>1 = small-world; human brain ~3-5; normalize by 20
            bar_val  = min(sig_v / 20.0, 1.0)
            v_col    = COL_GREEN if sig_v > 1.0 else COL_RED
            cl       = sw.get("clustering_C", 0.0)
            pl       = sw.get("path_length_L", 0.0)
            subs = [
                ("cluster C", min(cl, 1.0),   f"{cl:.4f}"),
                ("path L",    min(1.0/max(pl,0.5)*0.5,1.0), f"{pl:.3f}"),
                ("small-wld", 1.0 if sw.get("is_small_world") else 0.0,
                 "YES" if sw.get("is_small_world") else "NO"),
            ]

        # ── Draw card ───────────────────────────────────────────────────────
        card_hdr = f"CONSCIOUSNESS  {_bench_tab+1}/4"
        ix, iy   = _card(frame, PAD, y, cw, h_bn, card_hdr, acc=BA)

        # Metric name  |  value (right-aligned)
        put(frame, tab_name[:20], ix, iy+int(LH*0.80), BA_L, FS*0.82, 1)
        num_w = cv2.getTextSize(tab_num, FONT, FS*1.05, 1)[0][0]
        put(frame, tab_num, ix+cw-14-num_w, iy+int(LH*0.80), v_col, FS*1.05, 1)

        # Reference label (small, italic-style)
        put(frame, ref_lbl, ix, iy+int(LH*1.12), (100, 65, 140), FS*0.60, 1)
        iy += int(LH*1.28)

        # Main bar
        draw_bar(frame, ix, iy+int(LH*0.08), cw-14, bh+2, bar_val, v_col)
        iy += int(LH*0.55)

        # Thin separator
        cv2.line(frame, (ix, iy), (ix+cw-14, iy), (70, 35, 100), 1)
        iy += int(LH*0.18)

        # 3 detail rows
        lbl_w = int(cw * 0.36)
        bar_w = int(cw * 0.38)
        num_x = ix + lbl_w + bar_w + 4
        for lbl_s, bval, num_s in subs:
            s_col = COL_GREEN if bval > 0.7 else COL_AMBER if bval > 0.3 else COL_RED
            put(frame, lbl_s[:8], ix, iy+int(LH*0.68), BA_L, FS*0.68, 1)
            draw_bar(frame, ix+lbl_w, iy+int(LH*0.08), bar_w, bh, bval, s_col)
            put(frame, num_s[:8], num_x, iy+int(LH*0.68), s_col, FS*0.68, 1)
            iy += int(LH*0.82)

        # Progress dots
        dot_y = iy + int(LH*0.28)
        for i in range(4):
            cv2.circle(frame, (ix+i*18+6, dot_y), 4,
                       BA if i == _bench_tab else (55,28,78), -1)
        st = "hisoblayapti..." if _phi_real_loading else "[B]=qayta hisoblash"
        put(frame, st, ix+86, dot_y+5, (110,70,150), FS*0.58, 1)

        y += h_bn + CGAP

# ── Draw right panel: NeuroKey Status ────────────────────────────────────────
def draw_right_panel(frame, vol, fps, audio_mode, full_mode, intro_pct):
    if PNL_W < 80: return
    PAD = 4
    RX  = SW - PNL_W
    cw  = PNL_W - PAD*2
    bw  = cw - 10
    bh  = max(6, int(LH*0.36))
    y   = int(SH*0.04)
    A   = _R_ACC   # blue accent for right panel

    # Panel strip background + inner edge separator
    cv2.rectangle(frame, (RX, 0), (SW, SH), (3, 5, 10), -1)
    cv2.line(frame, (RX, 0), (RX, SH), mid3(_R_ACC), 1)

    # Section header
    y = _section_hdr(frame, RX+PAD, y, cw, "NEUROKEY", A)

    def card_kv(title, value, col_v=COL_WHITE):
        nonlocal y
        h = int(LH*2.10)
        ix, iy = _card(frame, RX+PAD, y, cw, h, title, acc=A)
        put(frame, value, ix, iy+int(LH*0.38), col_v, FS*0.88, 1)
        y += h + CGAP

    def card_kv2(t1, v1, col1, t2, v2, col2):
        nonlocal y
        h = int(LH*2.10)
        ix, iy = _card(frame, RX+PAD, y, cw, h, acc=A)
        hw = cw//2 - 6
        put(frame, t1, ix,      iy,              mid3(A),  FS*0.66)
        put(frame, v1, ix,      iy+int(LH*0.54), col1,     FS*0.83)
        put(frame, t2, ix+hw+4, iy,              mid3(A),  FS*0.66)
        put(frame, v2, ix+hw+4, iy+int(LH*0.54), col2,     FS*0.83)
        # vertical divider between the two halves
        div_x = RX+PAD + hw + 2
        cv2.line(frame, (div_x, y+4), (div_x, y+h-4), mid3(A), 1)
        y += h + CGAP

    # ── Read live NeuroKey state ─────────────────────────────────────────────
    nk   = _read_nk_state()
    mode = nk.get("mode", "idle")
    nk_age = time.time() - nk.get("timestamp", 0)
    nk_live = nk_age < 8.0   # treat as live if updated within 8 s

    # ── STATUS ───────────────────────────────────────────────────────────────
    _MODE_LABELS = {
        "idle":      ("Standby",    COL_WHITE),
        "listening": ("LISTENING",  (255, 220, 60)),   # yellow
        "thinking":  ("PROCESSING", COL_AMBER),
        "speaking":  ("SPEAKING",   COL_GREEN),
        "error":     ("ERROR",      COL_RED),
    }
    if not full_mode:
        sv, sc = f"Init {intro_pct}%", COL_AMBER
    elif nk_live and mode in _MODE_LABELS:
        sv, sc = _MODE_LABELS[mode]
    elif vol > 0.04:
        sv, sc = "ACTIVE", COL_GREEN
    else:
        sv, sc = "Standby", COL_WHITE

    # Blinking effect for THINKING mode
    if mode == "thinking" and nk_live:
        import math as _m
        blink = abs(_m.sin(time.time() * 4.0))
        sc = tuple(int(c * (0.5 + 0.5*blink)) for c in sc)

    h_st = int(LH*2.10)
    ix, iy = _card(frame, RX+PAD, y, cw, h_st, "STATUS", acc=A)
    put(frame, sv, ix, iy+int(LH*0.38), sc, FS*0.88, 1)
    # Mode dot indicator
    dot_col = sc if nk_live else mid3(A)
    cv2.circle(frame, (RX+PAD+cw-12, iy+int(LH*0.30)), 5, dot_col, -1, cv2.LINE_AA)
    y += h_st + CGAP

    # ── YUZ TANISH + EMOTION ─────────────────────────────────────────────────
    face_owner  = nk.get("face_owner", "")
    face_known  = nk.get("face_known", False)
    face_emo    = nk.get("face_emotion", "")
    h_face = int(LH*2.55)   # biroz balandroq — emotion satri uchun
    ix, iy = _card(frame, RX+PAD, y, cw, h_face, "YUZ / KAYFIYAT", acc=A)
    if face_owner and face_known:
        # Egasi tanildi — yashil
        face_col = (60, 255, 120)
        put(frame, f"OK  {face_owner}", ix, iy+int(LH*0.36), face_col, FS*0.78, 1)
        # Emotion satri
        _emo_uz = {
            "happy":   "XURSAND  :)",
            "sad":     "XAFA  :(",
            "angry":   "JAHL  >:(",
            "fear":    "XAVOTIR  :O",
            "surprise":"HAYRON  :D",
            "disgust": "BEZOR  :/",
            "neutral": "NEYTRAL  :|",
        }.get(face_emo, "")
        _emo_col = {
            "happy":    (60, 255, 120),
            "sad":      (120, 120, 255),
            "angry":    (60, 60, 255),
            "fear":     (200, 100, 255),
            "surprise": (255, 200, 60),
            "disgust":  (100, 200, 80),
            "neutral":  (160, 160, 160),
        }.get(face_emo, (160, 160, 160))
        if _emo_uz:
            put(frame, _emo_uz, ix, iy+int(LH*1.25), _emo_col, FS*0.72, 1)
    elif face_owner == "noma'lum":
        # Noma'lum — sariq
        face_col = (60, 200, 255)
        put(frame, "NOMA'LUM ODAM", ix, iy+int(LH*0.36), face_col, FS*0.78, 1)
    else:
        # Kamera natijasi yo'q — kulrang
        put(frame, "Kutilmoqda...", ix, iy+int(LH*0.36), (100, 100, 100), FS*0.78)
    y += h_face + CGAP

    # ── LAST INPUT (what user said) ───────────────────────────────────────────
    last_in = nk.get("last_input", "")
    if last_in:
        h_li = int(LH*2.55)
        ix, iy = _card(frame, RX+PAD, y, cw, h_li, "LAST INPUT", acc=A)
        # Truncate to fit (≈30 chars per line at FS*0.72)
        max_c = max(10, int(cw / max(1, int(FS*10.5))))
        line1 = last_in[:max_c]
        line2 = last_in[max_c:max_c*2] if len(last_in) > max_c else ""
        put(frame, line1, ix, iy,              (220, 220, 180), FS*0.72)
        if line2:
            put(frame, line2+"...", ix, iy+int(LH*0.88), (180,180,140), FS*0.68)
        y += h_li + CGAP

    # ── LAST RESPONSE (what NK said) ─────────────────────────────────────────
    last_out = nk.get("last_output", "")
    if last_out:
        h_lo = int(LH*2.55)
        ix, iy = _card(frame, RX+PAD, y, cw, h_lo, "RESPONSE", acc=A)
        max_c = max(10, int(cw / max(1, int(FS*10.5))))
        line1 = last_out[:max_c]
        line2 = last_out[max_c:max_c*2] if len(last_out) > max_c else ""
        put(frame, line1, ix, iy,              COL_WHITE, FS*0.72)
        if line2:
            put(frame, line2+"...", ix, iy+int(LH*0.88), (160,160,160), FS*0.68)
        y += h_lo + CGAP

    # ── CONSCIOUSNESS SCORE ───────────────────────────────────────────────────
    c_score = float(nk.get("consciousness_score", 0.0))
    emotion  = nk.get("emotion", "neutral")
    if nk_live:
        h_cs = int(LH*2.55)
        ix, iy = _card(frame, RX+PAD, y, cw, h_cs, "CONSCIOUSNESS", acc=A)
        cs_col = (int(60+c_score*160), int(200+c_score*55), int(80+c_score*40))
        draw_bar(frame, ix, iy, bw, bh, c_score, cs_col)
        put(frame, f"{c_score:.2f}  |  {emotion}", ix, iy+bh+int(LH*0.42),
            cs_col, FS*0.75)
        y += h_cs + CGAP

    # ── AUDIO SOURCE ─────────────────────────────────────────────────────────
    card_kv("AUDIO SOURCE", audio_mode)

    card_kv2("THEME", _THEME_NAMES[_theme_idx], (0, int(A[1]*0.8), int(A[2]*0.8)),
              "GAIN",  f"{GAIN_STEPS[_gain_idx]:.0f}x", COL_WHITE)

    # ── VOLUME bar ───────────────────────────────────────────────────────────
    h_vol = int(LH*2.55)
    ix, iy = _card(frame, RX+PAD, y, cw, h_vol, "VOLUME", acc=A)
    v_col = (0, int(80+vol*175), int(100+vol*155))
    draw_bar(frame, ix, iy, bw, bh, vol, v_col)
    put(frame, f"{vol:.3f}", ix, iy+bh+int(LH*0.42), COL_WHITE, FS*0.79)
    y += h_vol + CGAP

    card_kv2("FPS", f"{fps:.0f}", COL_GREEN if fps>20 else COL_AMBER,
              "ERRORS", "None", COL_GREEN)

    # ── ACTIVE MODULES (live from NK state, else fallback) ───────────────────
    nk_mods = nk.get("modules_active", [])
    lb_ok   = "OK" if "Loopback" in audio_mode else "Error"
    if nk_live and nk_mods:
        mods = [(m, "Active") for m in nk_mods[:6]]
    else:
        mods = [("Orb Renderer","OK"), ("Audio Loopback",lb_ok),
                ("Voice React","Active"), ("HUD","Running")]
    h_mod = int(LH*(1.05 + len(mods)*1.02))
    ix, iy = _card(frame, RX+PAD, y, cw, h_mod, "MODULES", acc=A)
    for mod, st in mods:
        c = COL_GREEN if st in ("OK","Active","Running") else COL_AMBER
        # Pulse active modules in THINKING mode
        if mode == "thinking" and nk_live and st == "Active":
            import math as _m2
            pulse = abs(_m2.sin(time.time()*6 + hash(mod)*0.5))
            c = tuple(int(x*(0.5+0.5*pulse)) for x in c)
        put(frame, ("[>] " if mode=="thinking" and nk_live else
                    "[+] " if c==COL_GREEN else "[~] ")+mod,
            ix, iy, c, FS*0.73)
        iy += int(LH*0.98)
    y += h_mod + CGAP

    # ── CONTROLS ─────────────────────────────────────────────────────────────
    h_ctl = int(LH*2.10)
    if y + h_ctl < SH - 30:
        ix, iy = _card(frame, RX+PAD, y, cw, h_ctl, "CONTROLS", acc=A)
        put(frame, "[G]Gain  [T]Theme  [H]Panels", ix, iy,              COL_DIM, FS*0.65)
        put(frame, "[Q] / ESC  -  Quit",           ix, iy+int(LH*0.80), COL_DIM, FS*0.65)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global _running, _vol_raw, _vol, GAIN, _gain_idx, _theme_idx, _show_panels, P

    pa = pyaudio.PyAudio()
    stream = None
    audio_mode = "None"

    dev_idx,dev_ch,dev_sr,audio_mode = find_loopback(pa)
    if dev_idx is not None:
        try:
            stream = pa.open(format=pyaudio.paFloat32,
                             channels=dev_ch, rate=dev_sr,
                             input=True, input_device_index=dev_idx,
                             frames_per_buffer=CHUNK,
                             stream_callback=_audio_cb)
            stream.start_stream()
            print(f"Audio loopback: device {dev_idx} ({dev_sr}Hz)")
        except Exception as e:
            print(f"Loopback error: {e}")
            audio_mode = "Error"

    # ── Mic input stream (for LISTENING reactivity) ───────────────────────────
    _mic_stream = None
    try:
        _mic_stream = pa.open(format=pyaudio.paFloat32,
                              channels=1, rate=16000,
                              input=True,
                              frames_per_buffer=512,
                              stream_callback=_mic_cb)
        _mic_stream.start_stream()
        print("Mic stream: OK (LISTENING reactivity enabled)")
    except Exception as e:
        print(f"Mic stream skipped: {e}")

    print(f"Screen: {SW}x{SH}  Orb panel: {ORB_W}x{ORB_H}  Panels: {PNL_W}px")
    print("Q/ESC quit  |  G gain  |  T theme  |  H panels")

    # Preallocate buffers - reused every frame (avoids malloc/GC)
    _orb_buf   = np.empty((ORB_H, ORB_W, 3), dtype=np.float32)
    _frame_buf = np.zeros((SH, SW, 3), dtype=np.uint8)

    _is_fullscreen = os.getenv("NEUROKEY_HUD_FULLSCREEN", "0") == "1"
    cv2.namedWindow("NeuroKey", cv2.WINDOW_NORMAL)
    if _is_fullscreen:
        cv2.setWindowProperty("NeuroKey", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow("NeuroKey", min(1280, SW), min(720, SH))

    # ── Auto-focus sozlamasi (faqat fullscreen rejimda) ─────────────────────
    _user32 = None
    _HWND_TOPMOST  = -1          # HWND_TOPMOST
    _SWP_KEEP      = 0x0003      # SWP_NOMOVE | SWP_NOSIZE
    if _is_fullscreen:
        try:
            import ctypes as _ct
            _user32 = _ct.windll.user32
        except Exception:
            pass

    def _set_topmost():
        if not _is_fullscreen or _user32 is None:
            return
        try:
            hwnd = _user32.FindWindowW(None, "NeuroKey")
            if hwnd:
                _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_KEEP)
        except Exception:
            pass

    _topmost_frame = 0

    t0     = time.time()
    fps    = 30.0
    t_prev = t0
    _orb_u8_cached = np.zeros((ORB_H, ORB_W, 3), dtype=np.uint8)

    while _running:
        t_loop = time.time()
        t      = t_loop - t0
        with _lock:
            vol = float(_vol)

        intro_prog = min(1.0, t/INTRO_DUR)
        fade_prog  = min(1.0, max(0.0,(t-INTRO_DUR)/FADE_DUR))
        full_mode  = t >= INTRO_DUR+FADE_DUR

        # ── Read NeuroKey live state ──────────────────────────────────────────
        nk_state = _read_nk_state()
        nk_mode  = nk_state.get("mode", "idle")
        nk_live  = (time.time() - nk_state.get("timestamp", 0)) < 8.0
        with _mic_lock:
            mic_v = float(_mic_vol)

        # ── Breathing: slow sine pulse when truly idle ───────────────────────
        idle = max(0.0, 1.0 - vol * 15.0)           # fades out when speaking
        breath = idle * (0.5 + 0.5*abs(math.sin(t * math.pi / 3.8)))
        eff_vol = vol + breath * 0.06                # effective vol for visuals

        # ── Mode-based visual boosts ─────────────────────────────────────────
        _rot_mult = 1.0
        if nk_live:
            if nk_mode == "listening":
                eff_vol = max(eff_vol, mic_v * 1.2 + 0.06)  # react to mic
            elif nk_mode == "thinking":
                # Orb spins faster, brighter - "brain processing"
                eff_vol = max(eff_vol, 0.18 + 0.10*abs(math.sin(t*3.1)))
                _rot_mult = 2.2
            elif nk_mode == "speaking":
                eff_vol = max(eff_vol, vol + 0.04)   # already boosted by loopback

        R_cur = R0 * (1.0 + eff_vol*0.13)
        rot   = t * (0.30 + eff_vol*0.70) * _rot_mult

        # ── Sparkline / waveform data updates ────────────────────────────────
        _vol_hist.append(vol)
        _s_now = get_sys_stats()   # cached 1 s - cheap every frame
        if int(t*4) != int((t - (time.time()-t_loop))*4):   # ~4 Hz update
            _cpu_hist.append(_s_now.get('cpu', 0) / 100.0)
            _gpu_hist.append(_s_now.get('gpu_load', 0) / 100.0 if _GPU_AVAIL else 0.0)
        update_ecg(_s_now.get('cpu', 0), vol, fps)

        # ── Pulse ring spawning ───────────────────────────────────────────────
        if vol > PULSE_THRESH and full_mode:
            if not _pulses or (t - _pulses[-1]) > PULSE_COOL:
                _pulses.append(t)

        # ── Render orb every 2nd frame; reuse cached uint8 on off-frames ─────
        _render_this = (t_loop == t0) or (fps < 18) or (int(t*60)%2==0)

        if _render_this:
            orb_f = _orb_buf
            orb_f[:] = 0.

            if not full_mode:
                draw_intro(orb_f, intro_prog, rot, R_cur)
                if fade_prog > 0.:
                    orb2=np.zeros((ORB_H,ORB_W,3),dtype=np.float32)
                    draw_sphere_body(orb2,R_cur,eff_vol)
                    draw_rings(orb2,rot,t,eff_vol,R_cur)
                    draw_orbit_rings(orb2,rot,t,eff_vol,R_cur)
                    draw_arcs(orb2,rot,t,eff_vol,R_cur)
                    draw_particles(orb2,rot,t,eff_vol,R_cur)
                    orb_f=orb_f*(1.-fade_prog)+orb2*fade_prog
            else:
                draw_sphere_body(orb_f,R_cur,eff_vol)
                draw_rings(orb_f,rot,t,eff_vol,R_cur)
                draw_orbit_rings(orb_f,rot,t,eff_vol,R_cur)
                draw_arcs(orb_f,rot,t,eff_vol,R_cur)
                draw_particles(orb_f,rot,t,eff_vol,R_cur)
                draw_lightning(orb_f, t, vol, R_cur)   # lightning on voice only

            orb_f  = bloom_fast(orb_f, 21, 1.05+eff_vol*1.55)
            draw_nucleus(orb_f, t, eff_vol, R_cur)
            _orb_u8_cached = np.clip(tone_map(orb_f * _ORB_VIG)*255.,0,255).astype(np.uint8)

            # ── Mode tint overlay (after tone-map, before display) ───────────
            if nk_live:
                if nk_mode == "listening":
                    # Cool blue-cyan wash while user is speaking
                    strength = 0.28 + mic_v * 0.5
                    _orb_u8_cached = np.clip(
                        _orb_u8_cached.astype(np.float32) *
                        np.array([1.10, 1.05, 0.75], np.float32) * strength
                        + _orb_u8_cached * (1.0 - strength),
                        0, 255).astype(np.uint8)
                elif nk_mode == "thinking":
                    # Rapid amber pulse - "brain working"
                    pulse = 0.75 + 0.25*abs(math.sin(t * 5.0))
                    _orb_u8_cached = np.clip(
                        _orb_u8_cached.astype(np.float32) *
                        np.array([0.70, 1.05, 1.20], np.float32) * pulse,
                        0, 255).astype(np.uint8)

        # ── Compose full frame ────────────────────────────────────────────────
        frame = _frame_buf
        frame[:] = 0

        dx = ORB_X0 + _orb_disp_x
        dy = _orb_disp_y
        frame[dy:dy+ORB_SZ, dx:dx+ORB_SZ] = _orb_u8_cached

        # Pulse rings expand into the black area around the orb
        orb_cx = dx + ORB_SZ//2
        orb_cy = dy + ORB_SZ//2
        draw_pulse_rings(frame, t, orb_cx, orb_cy)

        # ECG heartbeat display - full width of center zone, below the orb
        ecg_h = max(58, int(SH * 0.068))
        ecg_y = dy + ORB_SZ + max(4, int(SH * 0.012))
        ecg_x = ORB_X0
        ecg_w = ORB_DISP_W
        if ecg_y + ecg_h < SH - 28:
            draw_ecg(frame, ecg_x, ecg_y, ecg_w, ecg_h,
                     _s_now.get('cpu', 0), vol)

        # Panels (only if visible)
        if _show_panels:
            draw_left_panel(frame, eff_vol)
            draw_right_panel(frame, vol, fps, audio_mode, full_mode, int(intro_prog*100))

        # Bottom status bar
        bar_y = SH-20
        cv2.line(frame,(0,bar_y),(SW,bar_y),COL_DIM,1)
        now_s = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        put(frame, f"NeuroKey HUD  |  {now_s}  |  {SW}x{SH}  |  {_THEME_NAMES[_theme_idx]}",
            SW//2-200, SH-5, COL_DIM, FS*0.72)

        cv2.imshow("NeuroKey", frame)

        # ── Auto-focus: har 120 kadrda HUD ni oldinga chiqarish ──────────────
        _topmost_frame += 1
        if _topmost_frame >= 120:
            _topmost_frame = 0
            _set_topmost()

        # FPS
        dt = time.time()-t_prev; t_prev=time.time()
        fps = 0.9*fps + 0.1*(1.0/max(dt,0.001))

        # ── Hotkeys ──────────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), ord('Q'), 27):
            break
        elif key in (ord('g'), ord('G')):
            _gain_idx = (_gain_idx + 1) % len(GAIN_STEPS)
            GAIN = GAIN_STEPS[_gain_idx]
            print(f"GAIN -> {GAIN}")
        elif key in (ord('t'), ord('T')):
            _theme_idx = (_theme_idx + 1) % len(_THEMES)
            P = {k: v.copy() for k, v in _THEMES[_theme_idx].items()}
            print(f"Theme -> {_THEME_NAMES[_theme_idx]}")
        elif key in (ord('h'), ord('H')):
            _show_panels = not _show_panels
            print(f"Panels {'ON' if _show_panels else 'OFF'}")
        elif key in (ord('b'), ord('B')):
            _recompute_phi()

    _running=False
    cv2.destroyAllWindows()
    if stream:
        stream.stop_stream(); stream.close()
    if _mic_stream:
        _mic_stream.stop_stream(); _mic_stream.close()
    pa.terminate()
    print("NeuroKey yopildi.")

if __name__=='__main__':
    main()
