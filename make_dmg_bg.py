"""
Generate the DMG installer background (600 x 400 px).
Run once:  python3 make_dmg_bg.py
"""
from PIL import Image, ImageDraw, ImageFont
import math, os

W, H = 600, 400
BG      = (18,  18,  18)
PANEL   = (30,  30,  30)
ACCENT  = (0,   200, 65)     # green matching the TC display
DIM     = (80,  80,  80)
WHITE   = (200, 200, 200)
ARROW   = (60,  60,  60)

img  = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# ── subtle top gradient band ──────────────────────────────────────────────────
for y in range(60):
    alpha = int(18 + (40 - 18) * (1 - y / 60))
    draw.line([(0, y), (W, y)], fill=(alpha, alpha, alpha))

# ── title ─────────────────────────────────────────────────────────────────────
try:
    font_title = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 22)
    font_sub   = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 13)
    font_hint  = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 12)
except Exception:
    font_title = font_sub = font_hint = ImageFont.load_default()

title = "LTC → MIDI Program Change"
bbox  = draw.textbbox((0, 0), title, font=font_title)
tw    = bbox[2] - bbox[0]
draw.text(((W - tw) // 2, 22), title, font=font_title, fill=WHITE)

# thin accent line under title
draw.rectangle([W // 2 - 140, 54, W // 2 + 140, 55], fill=ACCENT)

# ── drop-zone labels ──────────────────────────────────────────────────────────
# app label (left icon area, x≈150)
lbl1 = "LTCtoMIDI"
b1   = draw.textbbox((0, 0), lbl1, font=font_sub)
draw.text((150 - (b1[2]-b1[0])//2, 290), lbl1, font=font_sub, fill=DIM)

# applications label (right icon area, x≈450)
lbl2 = "Applications"
b2   = draw.textbbox((0, 0), lbl2, font=font_sub)
draw.text((450 - (b2[2]-b2[0])//2, 290), lbl2, font=font_sub, fill=DIM)

# ── arrow ─────────────────────────────────────────────────────────────────────
ax1, ax2, ay = 215, 375, 210
shaft_y = ay
# shaft
draw.rectangle([ax1, shaft_y - 2, ax2 - 18, shaft_y + 2], fill=ARROW)
# arrowhead (triangle pointing right)
pts = [
    (ax2,      ay),
    (ax2 - 18, ay - 10),
    (ax2 - 18, ay + 10),
]
draw.polygon(pts, fill=ARROW)

# ── hint text ─────────────────────────────────────────────────────────────────
hint = "Drag to install"
bh   = draw.textbbox((0, 0), hint, font=font_hint)
draw.text(((W - (bh[2]-bh[0])) // 2, 350), hint, font=font_hint, fill=(55, 55, 55))

# ── save ──────────────────────────────────────────────────────────────────────
out = os.path.join(os.path.dirname(__file__), "dmg_background.png")
img.save(out, "PNG")
print(f"Saved {W}×{H} background → {out}")
