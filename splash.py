# -*- coding: utf-8 -*-
"""
NeuroKey — Loading Splash (chiroyli yuklanish animatsiyasi)
===========================================================
Tkinter (Python ichida bor) — qo'shimcha kutubxona kerak emas.
Ishlatish:  python splash.py [soniya]
"""
import sys, math, time
import tkinter as tk

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0

BG = "#0a0a14"
GOLD = "#fbbf24"
GOLD2 = "#f97316"
CYAN = "#22d3ee"
MUT = "#6e6e7a"

root = tk.Tk()
root.overrideredirect(True)
root.configure(bg=BG)
try:
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.0)
except Exception:
    pass

W, H = 460, 360
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
x = (sw - W) // 2
y = (sh - H) // 2
root.geometry(f"{W}x{H}+{x}+{y}")

cv = tk.Canvas(root, width=W, height=H, bg=BG, highlightthickness=0)
cv.pack()

CX, CY = W // 2, 135

def draw_logo(scale=1.0):
    cv.delete("logo")
    s = 46 * scale
    x0, y0 = CX - s, CY - s
    x1, y1 = CX + s, CY + s
    # oltin yumaloq blok
    cv.create_oval(x0, y0, x1, y1, outline=GOLD, width=4, tags="logo")
    # N + K (kalit)
    lw = max(3, int(6 * scale))
    nx = CX - 22 * scale
    cv.create_line(nx, CY-26*scale, nx, CY+26*scale, fill=CYAN, width=lw, capstyle="round", tags="logo")
    cv.create_line(nx, CY-26*scale, nx+30*scale, CY+26*scale, fill=CYAN, width=lw, capstyle="round", tags="logo")
    cv.create_line(nx+30*scale, CY-26*scale, nx+30*scale, CY+26*scale, fill=CYAN, width=lw, capstyle="round", tags="logo")
    kx = CX + 20 * scale
    cv.create_line(kx, CY-26*scale, kx, CY+26*scale, fill=GOLD2, width=lw, capstyle="round", tags="logo")
    cv.create_line(kx, CY, kx+18*scale, CY-16*scale, fill=GOLD2, width=lw, capstyle="round", tags="logo")
    cv.create_line(kx, CY, kx+18*scale, CY+16*scale, fill=GOLD2, width=lw, capstyle="round", tags="logo")

cv.create_text(CX, 230, text="NeuroKey", fill="#ffffff",
               font=("Segoe UI", 26, "bold"), tags="title")
cv.create_text(CX, 262, text="The Key to Your Mind", fill=MUT,
               font=("Segoe UI", 10), tags="sub")

# loading bar
BAR_W = 300
bx0 = CX - BAR_W // 2
bar_bg = cv.create_rectangle(bx0, 300, bx0 + BAR_W, 306, outline="", fill="#1e1e2a")
bar_fg = cv.create_rectangle(bx0, 300, bx0, 306, outline="", fill=CYAN)
status = cv.create_text(CX, 325, text="Yuklanmoqda...", fill=MUT, font=("Segoe UI", 9))

MSGS = ["Ong uyg'onmoqda...", "Yuz va ovoz tayyorlanmoqda...",
        "Xotira yuklanmoqda...", "NeuroKey tayyor!"]

t0 = time.time()

def animate():
    el = time.time() - t0
    p = min(1.0, el / DURATION)
    # fade in
    try:
        root.attributes("-alpha", min(1.0, el * 2))
    except Exception:
        pass
    # pulse logo
    scale = 1.0 + 0.06 * math.sin(el * 4)
    draw_logo(scale)
    # bar
    cv.coords(bar_fg, bx0, 300, bx0 + int(BAR_W * p), 306)
    # status text
    idx = min(len(MSGS) - 1, int(p * len(MSGS)))
    cv.itemconfig(status, text=MSGS[idx])
    if p >= 1.0:
        root.after(300, root.destroy)
        return
    root.after(33, animate)

animate()
root.mainloop()
