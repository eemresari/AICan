"""96×96 yazılım LED matrisi simülatörü — 40+ desen ve idle nefes.

Bir piksel buffer'ı (W*H tuple) tutar; UI tarafı (matrix_sim) her frame buffer'ı renderler.
Her sembol (kalp, yüz, el, soru işareti vs.) 96×96 ızgarada elle çizilmiş veya
parametrik üretilmiştir; jenerik desenler (pulse, wave, ripple) sin/cos tabanlıdır.
"""
from __future__ import annotations

import math
import random
import time
from pathlib import Path
from typing import Optional

from PIL import Image

W, H = 96, 96
CX, CY = 47.5, 47.5

# Emoji frame'leri saniyede kac kare oynatilacak — prepare_emojis.py FPS ile esit olmali
EMOJI_FPS = 12

# assets/emojis/<jest_id>/frame_NN.png yolu icin proje koku
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_EMOJI_BASE_DIR = _PROJECT_ROOT / "assets" / "emojis"

SPEED_MULTS = (0.4, 0.7, 1.0, 1.5, 2.5)
SPEED_NAME_TO_ID = {
    "cok_yavas": 0, "yavas": 1, "orta": 2, "hizli": 3, "cok_hizli": 4,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _scale(r: int, g: int, b: int, k: float) -> tuple[int, int, int]:
    k = _clamp(k, 0.0, 1.0)
    return (int(r * k), int(g * k), int(b * k))


def _scale8(c: tuple[int, int, int], factor: int) -> tuple[int, int, int]:
    r, g, b = c
    return (r * factor // 256, g * factor // 256, b * factor // 256)


class Buffer:
    """96×96 piksel buffer'i."""

    def __init__(self) -> None:
        self.pixels: list[tuple[int, int, int]] = [(0, 0, 0)] * (W * H)

    def clear(self) -> None:
        for i in range(W * H):
            self.pixels[i] = (0, 0, 0)

    def fill(self, color: tuple[int, int, int]) -> None:
        for i in range(W * H):
            self.pixels[i] = color

    def set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.pixels[y * W + x] = color

    def fade_all(self, factor: int) -> None:
        for i in range(W * H):
            self.pixels[i] = _scale8(self.pixels[i], factor)


# ============== Jenerik desenler ==============
# Imza: (buf, t_sec, r,g,b, r2,g2,b2, intensity, speed_mult)


def pat_pulse(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    w = (math.sin(2 * math.pi * t * 0.7 * speed_mult) + 1) * 0.5
    k = intensity * (0.20 + 0.80 * w)
    buf.fill(_scale(r, g, b, k))


def _wave(buf, t, r, g, b, intensity, speed_mult, vertical, reverse):
    pos = (t * 0.6 * speed_mult) % 1.0
    bound = H if vertical else W
    band = 18
    head = (1 - pos) * (bound + band) - 1 if reverse else pos * (bound + band) - band + 1
    buf.clear()
    for d in range(band):
        p = int(head + d)
        if p < 0 or p >= bound:
            continue
        k = intensity * (1 - d / band * 0.6)
        c = _scale(r, g, b, k)
        if vertical:
            for x in range(W):
                buf.set(x, p, c)
        else:
            for y in range(H):
                buf.set(p, y, c)


def pat_wave_up(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    _wave(buf, t, r, g, b, intensity, speed_mult, True, True)


def pat_wave_down(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    _wave(buf, t, r, g, b, intensity, speed_mult, True, False)


def pat_wave_left(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    _wave(buf, t, r, g, b, intensity, speed_mult, False, True)


def pat_wave_right(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    _wave(buf, t, r, g, b, intensity, speed_mult, False, False)


def _ripple(buf, t, r, g, b, intensity, speed_mult, out):
    pos = (t * 1.0 * speed_mult) % 1.0
    if not out:
        pos = 1.0 - pos
    radius = pos * 66.0
    buf.clear()
    band_w = 7.5
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - CX) ** 2 + (y - CY) ** 2)
            diff = abs(d - radius)
            if diff < band_w:
                k = intensity * (1 - diff / band_w)
                buf.set(x, y, _scale(r, g, b, k))


def pat_ripple_out(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    _ripple(buf, t, r, g, b, intensity, speed_mult, True)


def pat_ripple_in(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    _ripple(buf, t, r, g, b, intensity, speed_mult, False)


def pat_sparkle(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.fade_all(220)
    has_second = (r2 + g2 + b2) > 0
    n = int(70 + 160 * speed_mult)
    for _ in range(n):
        if random.randint(0, 99) >= 50:
            continue
        x = random.randint(0, W - 2)
        y = random.randint(0, H - 2)
        if has_second and random.randint(0, 1) == 0:
            cr, cg, cb = r2, g2, b2
        else:
            cr, cg, cb = r, g, b
        k = intensity * (0.55 + random.random() * 0.45)
        c = _scale(cr, cg, cb, k)
        for dx in (0, 1):
            for dy in (0, 1):
                buf.set(x + dx, y + dy, c)


def pat_drop(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.fade_all(200)
    xs = (15, 33, 48, 63, 81)
    for k_idx, x in enumerate(xs):
        phase = (t * 0.45 * speed_mult + k_idx * 0.2) % 1.0
        y = int(phase * (H + 9)) - 3
        if 0 <= y < H:
            c_main = _scale(r, g, b, intensity)
            c_dim = _scale(r, g, b, intensity * 0.55)
            for dx in (-1, 0, 1):
                buf.set(x + dx, y, c_main)
                buf.set(x + dx, y + 1, c_main)
            for trail in range(2, 5):
                yy = y + trail
                if yy < H:
                    k = intensity * (0.6 - 0.12 * trail)
                    c_t = _scale(r, g, b, k)
                    buf.set(x, yy, c_t)
                    buf.set(x - 1, yy, c_dim if trail == 2 else c_t)
                    buf.set(x + 1, yy, c_dim if trail == 2 else c_t)


def pat_fade(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    cycle_len = 2.5
    c_pos = ((t * speed_mult) % cycle_len) / cycle_len
    k = intensity * (1 - c_pos)
    buf.fill(_scale(r, g, b, k))


def pat_scan(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    pos = (t * 0.7 * speed_mult) % 1.0
    y = int(pos * H)
    buf.clear()
    if 0 <= y < H:
        c = _scale(r, g, b, intensity)
        for dy in (-1, 0, 1):
            yy = y + dy
            if 0 <= yy < H:
                for x in range(W):
                    buf.set(x, yy, c)


def pat_static_glow(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    w = (math.sin(2 * math.pi * t * 0.3 * speed_mult) + 1) * 0.5
    k = intensity * (0.55 + 0.15 * w)
    buf.fill(_scale(r, g, b, k))


def pat_three_dots(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.clear()
    dots = (24, 48, 72)
    y = 48
    radius = 6
    for i, dx in enumerate(dots):
        phase = t * 1.2 * speed_mult - i * 0.33
        w = (math.sin(2 * math.pi * phase) + 1) * 0.5
        if w < 0.25:
            w = 0
        k = intensity * w
        c = _scale(r, g, b, k)
        for ddy in range(-radius, radius + 1):
            for ddx in range(-radius, radius + 1):
                if ddx * ddx + ddy * ddy <= radius * radius:
                    buf.set(dx + ddx, y + ddy, c)


def pat_spiral_out(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.fade_all(220)
    angle = t * 4.0 * speed_mult
    radius = ((t * speed_mult) % 1.0) * 54.0
    cx = CX + radius * math.cos(angle)
    cy = CY + radius * math.sin(angle)
    c = _scale(r, g, b, intensity)
    # 5x5 iz disk
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if dx * dx + dy * dy <= 5:
                buf.set(int(cx + dx), int(cy + dy), c)


def pat_shake(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.clear()
    ox = random.randint(-6, 6)
    oy = random.randint(-6, 6)
    c = _scale(r, g, b, intensity * 0.85)
    for y in range(H):
        for x in range(W):
            buf.set(x + ox, y + oy, c)


def pat_diagonal_sweep(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.clear()
    pos = (t * 0.4 * speed_mult) % 1.0
    offset = pos * 198.0 - 12.0
    band = 12.0
    for y in range(H):
        for x in range(W):
            d = abs((x + y) - offset)
            if d < band:
                k = intensity * (1 - d / band)
                buf.set(x, y, _scale(r, g, b, k))


def pat_two_color_swing(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    w = (math.sin(2 * math.pi * t * 0.6 * speed_mult) + 1) * 0.5
    has_second = (r2 + g2 + b2) > 0
    if has_second:
        cr = int(r * (1 - w) + r2 * w)
        cg = int(g * (1 - w) + g2 * w)
        cb = int(b * (1 - w) + b2 * w)
    else:
        cr, cg, cb = r, g, b
    buf.fill(_scale(cr, cg, cb, intensity))


def pat_cross(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.clear()
    w = (math.sin(2 * math.pi * t * 0.7 * speed_mult) + 1) * 0.5
    k = intensity * (0.5 + 0.5 * w)
    c = _scale(r, g, b, k)
    # 3 piksel kalin diagonal X
    for i in range(W):
        for d in (-1, 0, 1):
            buf.set(i + d, i, c)
            buf.set(i, i + d, c)
            buf.set(i + d, H - 1 - i, c)
            buf.set(i, H - 1 - i + d, c)


def pat_border_only(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.clear()
    w = (math.sin(2 * math.pi * t * 0.5 * speed_mult) + 1) * 0.5
    k = intensity * (0.55 + 0.45 * w)
    c = _scale(r, g, b, k)
    # 3 piksel kalin cerceve
    for thick in range(3):
        for x in range(W):
            buf.set(x, thick, c)
            buf.set(x, H - 1 - thick, c)
        for y in range(thick + 1, H - 1 - thick):
            buf.set(thick, y, c)
            buf.set(W - 1 - thick, y, c)


def pat_split(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    buf.clear()
    pos = (t * 0.5 * speed_mult) % 1.0
    gap = int(pos * 45)
    top, bot = 47 - gap, 48 + gap
    c = _scale(r, g, b, intensity)
    for delta in (-1, 0, 1):
        ty = top + delta
        by = bot + delta
        if 0 <= ty < H:
            for x in range(W):
                buf.set(x, ty, c)
        if 0 <= by < H:
            for x in range(W):
                buf.set(x, by, c)


def _plot_seg(buf, x0, y0, x1, y1, prog, c, thickness=1):
    """Kalın çizgi segmenti — kare fırça boyutu = thickness."""
    dx, dy = x1 - x0, y1 - y0
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        buf.set(x0, y0, c)
        return
    n = min(int(prog * steps + 0.5), steps)
    half = thickness // 2
    for i in range(n + 1):
        x = int(x0 + dx * i / steps + 0.5)
        y = int(y0 + dy * i / steps + 0.5)
        for tx in range(-half, thickness - half):
            for ty in range(-half, thickness - half):
                buf.set(x + tx, y + ty, c)


def pat_checkmark(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    cycle = (t * 0.4 * speed_mult) % 1.0
    if cycle < 0.4:
        p1, p2 = cycle / 0.4, 0.0
    elif cycle < 0.85:
        p1, p2 = 1.0, (cycle - 0.4) / 0.45
    else:
        p1, p2 = 1.0, 1.0
    buf.clear()
    c = _scale(r, g, b, intensity)
    # 96x96 ✓ : kisa kol (18, 54) → (42, 78); uzun kol (42, 78) → (78, 24)
    _plot_seg(buf, 18, 54, 42, 78, p1, c, thickness=8)
    _plot_seg(buf, 42, 78, 78, 24, p2, c, thickness=8)


def pat_x_mark(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    cycle = (t * 0.4 * speed_mult) % 1.0
    if cycle < 0.4:
        p1, p2 = cycle / 0.4, 0.0
    elif cycle < 0.85:
        p1, p2 = 1.0, (cycle - 0.4) / 0.45
    else:
        p1, p2 = 1.0, 1.0
    buf.clear()
    c = _scale(r, g, b, intensity)
    # 96x96 ✗ : kosegenler (18, 18)-(77, 77) ve (77, 18)-(18, 77)
    _plot_seg(buf, 18, 18, 77, 77, p1, c, thickness=8)
    _plot_seg(buf, 77, 18, 18, 77, p2, c, thickness=8)


# ============== Sembol piksel setleri (96×96) ==============


def _build_heart() -> tuple[tuple[int, int], ...]:
    """96×96 dolu kalp — iki tepe disk + V tabani, ortada hafif çentik."""
    pts: set[tuple[int, int]] = set()
    # Iki ust tumsek (cember dolgu)
    for cx_b, cy_b, rad in [(28, 30, 22), (68, 30, 22)]:
        for y in range(max(0, cy_b - rad), min(H, cy_b + rad + 1)):
            dy = y - cy_b
            half = int(math.sqrt(rad * rad - dy * dy))
            for x in range(max(0, cx_b - half), min(W, cx_b + half + 1)):
                pts.add((x, y))
    # V tabani: y=30 tam genis → y=86 tek nokta
    for y in range(30, 87):
        if y < 44:
            left, right = 6, 89
        else:
            t = (y - 44) / 42.0
            left = int(6 + (48 - 6) * t)
            right = int(89 - (89 - 48) * t)
        for x in range(left, right + 1):
            pts.add((x, y))
    return tuple(sorted(pts))


HEART_PIXELS = _build_heart()


def _stamp_disk(pts: set, cx: int, cy: int, radius: int) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                pts.add((x, y))


def _stamp_square(pts: set, cx: int, cy: int, half: int) -> None:
    """Kare firca - disk gibi tek piksel uca dejenere olmaz."""
    for y in range(cy - half, cy + half + 1):
        for x in range(cx - half, cx + half + 1):
            pts.add((x, y))


def _build_question_body() -> tuple[tuple[int, int], ...]:
    """96×96 soru işareti gövdesi — üst yuvarlak kanca + dikey indirgemeli."""
    pts: set[tuple[int, int]] = set()
    cx_arc, cy_arc = 48, 26
    arc_r = 17
    # Ust kanca: 180° (sol) → tepe (270°) → 0° (sag) → 315° (sag-alt)
    n_samples = 80
    for i in range(n_samples):
        # angle 180° (math.pi) ile -45° (-math.pi/4) arasi (saat yonunde)
        a = math.pi - (i / (n_samples - 1)) * (math.pi * 1.25)
        x = cx_arc + arc_r * math.cos(a)
        y = cy_arc - arc_r * math.sin(a)
        _stamp_square(pts, round(x), round(y), 5)
    # Kanca sonundan (yaklasik 60, 38) dikey govdeye (48, 56) gecis
    for i in range(22):
        t = i / 21
        x = round(60 * (1 - t) + 48 * t)
        y = round(38 * (1 - t) + 56 * t)
        _stamp_square(pts, x, y, 5)
    # Dikey govde - 10 piksel genis (43-52), rows 54-72
    for y in range(54, 73):
        for x in range(43, 53):
            pts.add((x, y))
    return tuple(sorted(pts))


def _build_question_dot() -> tuple[tuple[int, int], ...]:
    """96×96 soru noktasi - 11x11 disk, rows 78-89."""
    pts: set[tuple[int, int]] = set()
    _stamp_disk(pts, 48, 83, 6)
    return tuple(sorted(pts))


QUESTION_BODY = _build_question_body()
QUESTION_DOT = _build_question_dot()


def pat_heart(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Kalp atışı — iki hızlı vuruş, sonra dinlenme."""
    buf.clear()
    cycle = (t * 0.8 * speed_mult) % 1.0
    if cycle < 0.15:
        beat = math.sin(math.pi * cycle / 0.15)
    elif cycle < 0.30:
        beat = 0.25
    elif cycle < 0.45:
        beat = math.sin(math.pi * (cycle - 0.30) / 0.15) * 0.75
    else:
        beat = max(0.25 - (cycle - 0.45) * 0.4, 0.0)
    k = intensity * (0.40 + 0.60 * beat)
    has_second = (r2 + g2 + b2) > 0
    if has_second:
        cr = int(r * (1 - beat * 0.4) + r2 * beat * 0.4)
        cg = int(g * (1 - beat * 0.4) + g2 * beat * 0.4)
        cb = int(b * (1 - beat * 0.4) + b2 * beat * 0.4)
    else:
        cr, cg, cb = r, g, b
    c = _scale(cr, cg, cb, k)
    for (x, y) in HEART_PIXELS:
        buf.set(x, y, c)


def pat_question_mark(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Soru işareti — gövde yumuşak nefes, nokta ayrı blink."""
    buf.clear()
    body_w = (math.sin(2 * math.pi * t * 0.5 * speed_mult) + 1) * 0.5
    k_body = intensity * (0.55 + 0.30 * body_w)
    c_body = _scale(r, g, b, k_body)
    for (x, y) in QUESTION_BODY:
        buf.set(x, y, c_body)
    dot_phase = (t * 0.7 * speed_mult) % 1.0
    if dot_phase < 0.55:
        k_dot = intensity * (0.85 + 0.15 * math.sin(math.pi * dot_phase / 0.55))
    else:
        k_dot = intensity * 0.30
    c_dot = _scale(r, g, b, k_dot)
    for (x, y) in QUESTION_DOT:
        buf.set(x, y, c_dot)


def pat_question_shake(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Sallanan soru işareti — 'anlamadım' hissi."""
    buf.clear()
    ox = random.randint(-3, 3)
    oy = random.randint(-3, 3)
    body_w = (math.sin(2 * math.pi * t * 0.7 * speed_mult) + 1) * 0.5
    k_body = intensity * (0.50 + 0.30 * body_w)
    c_body = _scale(r, g, b, k_body)
    for (x, y) in QUESTION_BODY:
        buf.set(x + ox, y + oy, c_body)
    dot_phase = (t * 1.0 * speed_mult) % 1.0
    if dot_phase < 0.55:
        k_dot = intensity * (0.80 + 0.20 * math.sin(math.pi * dot_phase / 0.55))
    else:
        k_dot = intensity * 0.30
    c_dot = _scale(r, g, b, k_dot)
    for (x, y) in QUESTION_DOT:
        buf.set(x + ox, y + oy, c_dot)


# --- Yildiz (8-uclu compass rose) ---

def _build_star() -> tuple[tuple[int, int], ...]:
    """96×96 8-uclu yildiz: kalin dikey + yatay cubuk + iki capraz."""
    pts: set[tuple[int, int]] = set()
    # Dikey + yatay cubuklar (6 piksel kalin)
    for i in range(H):
        for d in range(45, 51):
            pts.add((d, i))
            pts.add((i, d))
    # Diyagonaller (5 piksel kalin)
    for i in range(H):
        for d in range(-2, 3):
            if 0 <= i + d < W:
                pts.add((i + d, i))
            if 0 <= H - 1 - i + d < W:
                pts.add((H - 1 - i + d, i))
    return tuple(sorted(pts))


STAR_PIXELS = _build_star()


def pat_star(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Yildiz — gövde nefes alir, etrafa rastgele ikincil renkte parilti."""
    buf.clear()
    pulse = (math.sin(2 * math.pi * t * 0.5 * speed_mult) + 1) * 0.5
    k = intensity * (0.55 + 0.45 * pulse)
    c = _scale(r, g, b, k)
    for (x, y) in STAR_PIXELS:
        buf.set(x, y, c)
    has_second = (r2 + g2 + b2) > 0
    if has_second:
        n = int(8 + 16 * speed_mult)
        for _ in range(n):
            if random.randint(0, 99) >= 35:
                continue
            x = random.randint(0, W - 2)
            y = random.randint(0, H - 2)
            k_sp = intensity * (0.6 + random.random() * 0.4)
            c2 = _scale(r2, g2, b2, k_sp)
            for dx in (0, 1):
                for dy in (0, 1):
                    buf.set(x + dx, y + dy, c2)


# --- Unlem isareti ---

EXCLAMATION_BODY = tuple((x, y) for y in range(8, 60) for x in range(41, 55))
EXCLAMATION_DOT = tuple((x, y) for y in range(70, 85) for x in range(41, 55))


def pat_exclamation(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Unlem - baslangicta keskin flash, sonra hizli pulse."""
    buf.clear()
    cycle = (t * 1.0 * speed_mult) % 1.0
    if cycle < 0.10:
        k_main = intensity
    else:
        w = (math.sin(2 * math.pi * t * 1.0 * speed_mult) + 1) * 0.5
        k_main = intensity * (0.55 + 0.40 * w)
    c = _scale(r, g, b, k_main)
    for (x, y) in EXCLAMATION_BODY:
        buf.set(x, y, c)
    dot_pulse = (math.sin(2 * math.pi * t * 1.6 * speed_mult) + 1) * 0.5
    k_dot = intensity * (0.70 + 0.30 * dot_pulse)
    c_dot = _scale(r, g, b, k_dot)
    for (x, y) in EXCLAMATION_DOT:
        buf.set(x, y, c_dot)


# --- Yuz sekilleri (gozler ortak; gulen / uzgun agiz) ---

def _build_eyes() -> tuple[tuple[int, int], ...]:
    """Iki yuvarlak goz (R=8 disk), centerlar (28, 36) ve (68, 36)."""
    pts: set[tuple[int, int]] = set()
    _stamp_disk(pts, 28, 36, 8)
    _stamp_disk(pts, 68, 36, 8)
    return tuple(sorted(pts))


def _build_smile_mouth() -> tuple[tuple[int, int], ...]:
    """Yukari acik parabol — agiz koseleri yukari, ortasi asagi."""
    pts: set[tuple[int, int]] = set()
    for x in range(24, 73):
        u = (x - 48) / 24.0
        y_center = 62 + 14 * (1 - u * u)
        if y_center < 0:
            continue
        for dy in range(-2, 3):
            y = int(y_center + dy)
            if 0 <= y < H:
                pts.add((x, y))
    return tuple(sorted(pts))


def _build_sad_mouth() -> tuple[tuple[int, int], ...]:
    """Asagi acik parabol — koseler asagi, ortasi yukari (uzgun)."""
    pts: set[tuple[int, int]] = set()
    for x in range(24, 73):
        u = (x - 48) / 24.0
        y_center = 76 - 14 * (1 - u * u)
        for dy in range(-2, 3):
            y = int(y_center + dy)
            if 0 <= y < H:
                pts.add((x, y))
    return tuple(sorted(pts))


SMILE_EYES = _build_eyes()
SMILE_MOUTH = _build_smile_mouth()
SAD_MOUTH = _build_sad_mouth()
SMILE_PIXELS = tuple(sorted(set(SMILE_EYES) | set(SMILE_MOUTH)))
SAD_PIXELS = tuple(sorted(set(SMILE_EYES) | set(SAD_MOUTH)))


def pat_smile_face(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Gulen yuz - yumusak nefes pulsu."""
    buf.clear()
    pulse = (math.sin(2 * math.pi * t * 0.4 * speed_mult) + 1) * 0.5
    k = intensity * (0.60 + 0.35 * pulse)
    c = _scale(r, g, b, k)
    for (x, y) in SMILE_PIXELS:
        buf.set(x, y, c)


def pat_sad_face(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Uzgun yuz - yavas, agir pulse."""
    buf.clear()
    pulse = (math.sin(2 * math.pi * t * 0.25 * speed_mult) + 1) * 0.5
    k = intensity * (0.50 + 0.30 * pulse)
    c = _scale(r, g, b, k)
    for (x, y) in SAD_PIXELS:
        buf.set(x, y, c)


# --- Damla (gozyasi) ---

def pat_tear_drop(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Yavasca dusen gozyasi - 96x96 iri damla + iz."""
    buf.clear()
    cycle = (t * 0.25 * speed_mult) % 1.0
    head_y = int(cycle * 116) - 16  # ust merkez y
    cx = 48
    c_main = _scale(r, g, b, intensity)
    c_dim = _scale(r, g, b, intensity * 0.55)
    c_trail = _scale(r, g, b, intensity * 0.25)
    # Iz - 12 piksel yukariya solan iz (3 piksel genis)
    for off in range(-14, -4):
        py = head_y + off
        if 0 <= py < H:
            k = intensity * (0.10 + 0.15 * (off + 14) / 10)
            c = _scale(r, g, b, k)
            for dx in (-1, 0, 1):
                buf.set(cx + dx, py, c)
    # Sivri tepe (rows -4 to -2)
    for off, half in [(-4, 0), (-3, 1), (-2, 1)]:
        py = head_y + off
        if 0 <= py < H:
            for dx in range(-half, half + 1):
                buf.set(cx + dx, py, c_dim)
    # Genis govde (rows -1 to +4) — 7-9 piksel genis
    body_widths = [3, 4, 4, 4, 3, 3]
    for i, half in enumerate(body_widths):
        py = head_y - 1 + i
        if 0 <= py < H:
            for dx in range(-half, half + 1):
                buf.set(cx + dx, py, c_main)
    # Yuvarlak alt (rows +5 to +7)
    for off, half in [(5, 3), (6, 2), (7, 1)]:
        py = head_y + off
        if 0 <= py < H:
            for dx in range(-half, half + 1):
                buf.set(cx + dx, py, c_dim)


# --- Ates (alev) ---

def _build_fire_base() -> tuple[tuple[int, int], ...]:
    """96x96 alev tabani - asagidan yukariya daralan ucgen."""
    pts: set[tuple[int, int]] = set()
    # Genislik: y=95 -> 49 piksel genis; y=32 -> 1 piksel
    for y in range(32, 96):
        half_w = int((y - 32) / 63.0 * 25)
        for x in range(48 - half_w, 48 + half_w + 1):
            if 0 <= x < W:
                pts.add((x, y))
    return tuple(sorted(pts))


FIRE_BASE = _build_fire_base()


def pat_fire(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Alev - taban sabit, ustler kipirdar."""
    buf.clear()
    flicker = (math.sin(2 * math.pi * t * 4.0 * speed_mult) + 1) * 0.5
    base_k = intensity * (0.65 + 0.30 * flicker)
    c_base = _scale(r, g, b, base_k)
    for (x, y) in FIRE_BASE:
        buf.set(x, y, c_base)
    has_second = (r2 + g2 + b2) > 0
    n_tips = int(60 + 110 * speed_mult)
    for _ in range(n_tips):
        if random.randint(0, 99) >= 60:
            continue
        x = 26 + random.randint(0, 44)
        y = 28 + random.randint(0, 50)
        use_second = has_second and random.randint(0, 1) == 0
        cr, cg, cb = (r2, g2, b2) if use_second else (r, g, b)
        k = intensity * (0.45 + random.random() * 0.45)
        c = _scale(cr, cg, cb, k)
        # 2x2 alev parcaciklari
        for dx in (0, 1):
            for dy in (0, 1):
                buf.set(x + dx, y + dy, c)


# --- Simsek ---

def _build_lightning() -> tuple[tuple[int, int], ...]:
    """96x96 kalin zigzag simsek — sag-ust koseden sol-alta."""
    pts: set[tuple[int, int]] = set()
    # Ust kisim: (60, 6) -> (36, 36), kalin 5
    for i in range(0, 31):
        x = 60 - i + i // 2
        y = 6 + i
        for dx in range(-2, 3):
            for dy in (-1, 0, 1):
                pts.add((x + dx, y + dy))
    # Genisleme noktasi (rows 33-40)
    for x in range(24, 72):
        for y in (33, 34, 35, 36):
            pts.add((x, y))
    for x in range(30, 66):
        for y in (37, 38, 39, 40):
            pts.add((x, y))
    # Alt kisim: (36, 40) -> (12, 84), kalin 5
    for i in range(0, 45):
        x = 36 - i // 2
        y = 40 + i
        for dx in range(-2, 3):
            for dy in (-1, 0, 1):
                pts.add((x + dx, y + dy))
    return tuple(sorted(pts))


LIGHTNING_PIXELS = _build_lightning()


def pat_lightning(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Simsek — ani parlak cakma, ardindan karanlik."""
    buf.clear()
    cycle = (t * 0.9 * speed_mult) % 1.0
    if cycle < 0.05:
        c = _scale(255, 255, 255, intensity)
    elif cycle < 0.18:
        fade = 1.0 - (cycle - 0.05) / 0.13
        c = _scale(r, g, b, intensity * fade)
    else:
        return
    for (x, y) in LIGHTNING_PIXELS:
        buf.set(x, y, c)


# --- Oklar ---

def _build_arrow_up() -> tuple[tuple[int, int], ...]:
    """96x96 yukari ok: ucgen ust + genis govde."""
    pts: set[tuple[int, int]] = set()
    # Ucgen ust: y=12 (uc) → y=30 (taban genis)
    for y in range(12, 31):
        half_w = (y - 12)
        for x in range(48 - half_w, 48 + half_w + 1):
            if 0 <= x < W:
                pts.add((x, y))
    # Govde: cols 40-55 (16 genis), rows 30-83
    for y in range(30, 84):
        for x in range(40, 56):
            pts.add((x, y))
    return tuple(sorted(pts))


def _build_arrow_down() -> tuple[tuple[int, int], ...]:
    """96x96 asagi ok: govde + ucgen alt."""
    pts: set[tuple[int, int]] = set()
    # Govde: cols 40-55, rows 12-65
    for y in range(12, 66):
        for x in range(40, 56):
            pts.add((x, y))
    # Ucgen alt: y=66 (taban) → y=83 (uc)
    for y in range(66, 84):
        half_w = (83 - y)
        for x in range(48 - half_w, 48 + half_w + 1):
            if 0 <= x < W:
                pts.add((x, y))
    return tuple(sorted(pts))


ARROW_UP_PIXELS = _build_arrow_up()
ARROW_DOWN_PIXELS = _build_arrow_down()


def pat_arrow_up(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Yukari ok — uca dogru parlaklik gradyani."""
    buf.clear()
    pulse = (math.sin(2 * math.pi * t * 0.5 * speed_mult) + 1) * 0.5
    k_top = intensity * (0.70 + 0.30 * pulse)
    k_bottom = intensity * (0.40 + 0.20 * pulse)
    for (x, y) in ARROW_UP_PIXELS:
        ratio = 1 - (y - 12) / 72
        k = k_bottom + (k_top - k_bottom) * ratio
        buf.set(x, y, _scale(r, g, b, k))


def pat_arrow_down(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Asagi ok — asagiya dogru parlaklik gradyani."""
    buf.clear()
    pulse = (math.sin(2 * math.pi * t * 0.4 * speed_mult) + 1) * 0.5
    k_top = intensity * (0.30 + 0.15 * pulse)
    k_bottom = intensity * (0.65 + 0.30 * pulse)
    for (x, y) in ARROW_DOWN_PIXELS:
        ratio = (y - 12) / 72
        k = k_top + (k_bottom - k_top) * ratio
        buf.set(x, y, _scale(r, g, b, k))


# --- Yalniz tek nokta ---

def pat_lonely_dot(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Tek nokta merkezde, cok yavas nefes alir (96x96 iri disk)."""
    buf.clear()
    pulse = (math.sin(2 * math.pi * t * 0.20 * speed_mult) + 1) * 0.5
    k = intensity * (0.40 + 0.45 * pulse)
    c = _scale(r, g, b, k)
    # 13x13 disk
    radius = 6
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                buf.set(48 + dx, 48 + dy, c)


# --- Ziplayan toplar ---

def pat_bouncing(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """4 top farkli tempolarda ziplar — 96x96 iri toplar."""
    buf.clear()
    has_second = (r2 + g2 + b2) > 0
    balls = [(15, 0.0), (36, 0.25), (60, 0.50), (81, 0.75)]
    for cx, phase in balls:
        cycle = (t * 0.7 * speed_mult + phase) % 1.0
        bounce = abs(math.sin(math.pi * cycle))
        cy = 84 - int(bounce * 72)
        if not (0 <= cy < H):
            continue
        use_second = has_second and (int(t * 2 * speed_mult + phase * 3) % 2 == 0)
        cr, cg, cb = (r2, g2, b2) if use_second else (r, g, b)
        c = _scale(cr, cg, cb, intensity)
        # 9x9 top (radius 4)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if dx * dx + dy * dy <= 16:
                    buf.set(cx + dx, cy + dy, c)


# --- Saat ---

def pat_clock(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Donen saat ibresi — bekleme hissi (96x96 buyuk saat)."""
    buf.clear()
    cx, cy = CX, CY
    radius_marks = 41.0
    # 12 saat isareti — 4x4 sonuk blok
    c_marks = _scale(r, g, b, intensity * 0.35)
    for h in range(12):
        angle = 2 * math.pi * h / 12 - math.pi / 2
        mx = cx + radius_marks * math.cos(angle)
        my = cy + radius_marks * math.sin(angle)
        for dx in range(-2, 2):
            for dy in range(-2, 2):
                buf.set(int(mx + dx + 0.5), int(my + dy + 0.5), c_marks)
    # Ibre — 36 piksel uzunluk, 5 piksel kalin
    hand_angle = 2 * math.pi * (t * 0.25 * speed_mult) - math.pi / 2
    c_hand = _scale(r, g, b, intensity)
    cos_a = math.cos(hand_angle)
    sin_a = math.sin(hand_angle)
    for r_step in range(1, 36):
        for thick in (-2, -1, 0, 1, 2):
            px = cx + r_step * cos_a - thick * sin_a
            py = cy + r_step * sin_a + thick * cos_a
            buf.set(int(px), int(py), c_hand)
    # Merkez 6x6 disk
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            if dx * dx + dy * dy <= 9:
                buf.set(int(cx + dx + 0.5), int(cy + dy + 0.5), c_hand)


# --- Sallanan el (selamlama) ---

def _build_hand() -> tuple[tuple[int, int], ...]:
    """96x96 el silueti — 4 parmak yukari, basparmak saga, palme + bilek."""
    pts: set[tuple[int, int]] = set()
    # 4 parmak: (x0, x1, y0, y1) — 8 piksel kalin
    finger_specs = [
        (22, 29, 28, 46),   # kucuk parmak
        (31, 38, 18, 46),   # yuzuk
        (40, 47, 12, 46),   # orta (en uzun)
        (49, 56, 22, 46),   # isaret
    ]
    for x0, x1, y0, y1 in finger_specs:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                pts.add((x, y))
    # Palme - parmak diplerinden bilege
    for y in range(46, 68):
        for x in range(22, 60):
            pts.add((x, y))
    # Basparmak - palmenin sag kenarindan disariya cikan dolu oval
    # Y merkez 55, x merkez 60-72, ovaldir (genis ortada, daralan uclarda)
    for y_off in range(-7, 8):
        y = 55 + y_off
        if not (0 <= y < H):
            continue
        # Genislik: ortada en fazla 14, uclara dogru azalir
        if abs(y_off) <= 3:
            width = 14
        elif abs(y_off) <= 5:
            width = 14 - (abs(y_off) - 3) * 2
        else:
            width = 10 - (abs(y_off) - 5) * 3
        if width >= 0:
            for x in range(58, 58 + width):
                if 0 <= x < W:
                    pts.add((x, y))
    # Bilek - dar (cols 28-52, rows 68-86)
    for y in range(68, 86):
        for x in range(28, 53):
            pts.add((x, y))
    return tuple(sorted(pts))


HAND_PIXELS = _build_hand()
HAND_SET = frozenset(HAND_PIXELS)


def pat_wave_hand(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Selamlayan el - bilek pivotunda saga sola sallanir + arka hareket cizgileri."""
    buf.clear()
    phase = 2 * math.pi * t * 1.1 * speed_mult
    swing = math.sin(phase)
    angle = swing * (22.0 * math.pi / 180.0)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    px, py = 40.0, 80.0  # bilek pivot

    c = _scale(r, g, b, intensity)
    # Ters eslestirme: her hedef pikseli kaynak HAND_SET'e geri proje et
    for dy in range(H):
        for dx in range(W):
            ox = dx - px
            oy = dy - py
            sx = ox * cos_a + oy * sin_a + px
            sy = -ox * sin_a + oy * cos_a + py
            ix, iy = int(sx + 0.5), int(sy + 0.5)
            if (ix, iy) in HAND_SET:
                buf.set(dx, dy, c)

    # Hareket cizgileri (ikincil renk varsa)
    has_second = (r2 + g2 + b2) > 0
    if has_second and abs(swing) > 0.45:
        ck = intensity * (abs(swing) - 0.45) / 0.55
        c2 = _scale(r2, g2, b2, ck)
        if swing > 0:
            arcs = [(12, 18), (9, 21), (6, 24),
                    (15, 30), (12, 33), (9, 36),
                    (18, 42), (15, 45)]
        else:
            arcs = [(81, 18), (84, 21), (87, 24),
                    (78, 30), (81, 33), (84, 36),
                    (75, 42), (78, 45)]
        for (ax, ay) in arcs:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    buf.set(ax + dx, ay + dy, c2)


# --- Kaotik flas ---

def pat_chaotic_flash(buf, t, r, g, b, r2, g2, b2, intensity, speed_mult):
    """Panik icin kaotik rastgele flaslar."""
    buf.fade_all(170)
    has_second = (r2 + g2 + b2) > 0
    n = int(120 + 240 * speed_mult)
    for _ in range(n):
        if random.randint(0, 99) >= 65:
            continue
        x = random.randint(0, W - 2)
        y = random.randint(0, H - 2)
        use_second = has_second and random.randint(0, 1) == 0
        cr, cg, cb = (r2, g2, b2) if use_second else (r, g, b)
        k = intensity * (0.7 + random.random() * 0.3)
        c = _scale(cr, cg, cb, k)
        # 2x2 flash
        for dx in (0, 1):
            for dy in (0, 1):
                buf.set(x + dx, y + dy, c)


PATTERN_DISPATCH = {
    "pulse": pat_pulse,
    "wave_up": pat_wave_up,
    "wave_down": pat_wave_down,
    "wave_left": pat_wave_left,
    "wave_right": pat_wave_right,
    "ripple_out": pat_ripple_out,
    "ripple_in": pat_ripple_in,
    "sparkle": pat_sparkle,
    "drop": pat_drop,
    "fade": pat_fade,
    "scan": pat_scan,
    "static_glow": pat_static_glow,
    "three_dots": pat_three_dots,
    "spiral_out": pat_spiral_out,
    "shake": pat_shake,
    "diagonal_sweep": pat_diagonal_sweep,
    "two_color_swing": pat_two_color_swing,
    "cross_pattern": pat_cross,
    "border_only": pat_border_only,
    "split": pat_split,
    "checkmark": pat_checkmark,
    "x_mark": pat_x_mark,
    "heart": pat_heart,
    "question_mark": pat_question_mark,
    "question_shake": pat_question_shake,
    "star": pat_star,
    "exclamation": pat_exclamation,
    "smile_face": pat_smile_face,
    "sad_face": pat_sad_face,
    "tear_drop": pat_tear_drop,
    "fire": pat_fire,
    "lightning": pat_lightning,
    "arrow_up": pat_arrow_up,
    "arrow_down": pat_arrow_down,
    "lonely_dot": pat_lonely_dot,
    "bouncing": pat_bouncing,
    "clock": pat_clock,
    "chaotic_flash": pat_chaotic_flash,
    "wave_hand": pat_wave_hand,
}


# ============== Emoji frame onbellegi ==============


class EmojiCache:
    """Jest_id basina emoji karelerini lazy-load eder — VARYANTLARIYLA birlikte.

    Disk duzeni:
        assets/emojis/<jest_id>/frame_NN.png          -> varyant 0 (ana emoji)
        assets/emojis/<jest_id>/v01/frame_NN.png      -> varyant 1
        assets/emojis/<jest_id>/v02/frame_NN.png      -> varyant 2 ...

    get() varyant listesi doner: [[frame, ...], [frame, ...]]. Her frame,
    Buffer.pixels formatiyla uyumlu list[(r,g,b)]'dir.

    Bos liste = bu jest icin hic frame yok (cagiran soyut desene dusebilir).
    Cache pozitif/negatif sonuclari tutar; ayni jest icin disk tekrar okunmaz.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._cache: dict[str, list[list[list[tuple[int, int, int]]]]] = {}

    @staticmethod
    def _kareleri_oku(klasor: Path) -> list[list[tuple[int, int, int]]]:
        frames: list[list[tuple[int, int, int]]] = []
        for fp in sorted(klasor.glob("frame_*.png")):
            try:
                img = Image.open(fp).convert("RGB")
                if img.size != (W, H):
                    img = img.resize((W, H), Image.Resampling.LANCZOS)
                frames.append(list(img.getdata()))
            except (OSError, ValueError):
                pass  # bozuk dosya - atla
        return frames

    def get(self, jest_id: str) -> list[list[list[tuple[int, int, int]]]]:
        cached = self._cache.get(jest_id)
        if cached is not None:
            return cached
        varyantlar: list[list[list[tuple[int, int, int]]]] = []
        jest_dir = self.base_dir / jest_id
        if jest_dir.is_dir():
            ana = self._kareleri_oku(jest_dir)
            if ana:
                varyantlar.append(ana)
            for alt in sorted(jest_dir.glob("v[0-9][0-9]")):
                if not alt.is_dir():
                    continue
                kareler = self._kareleri_oku(alt)
                if kareler:
                    varyantlar.append(kareler)
        self._cache[jest_id] = varyantlar
        return varyantlar


# ============== Engine ==============


class GestureEngine:
    """Aktif jest durumunu tutar, her frame icin buffer'i gunceller."""

    def __init__(self, gestures_data: dict) -> None:
        self.gestures = {g["id"]: g for g in gestures_data["jestler"]}
        self.buf = Buffer()
        self.active: Optional[dict] = None
        self.start: float = 0.0
        self.duration: float = 0.0
        self.intensity: float = 1.0
        self._t0 = time.monotonic()
        self.emoji_cache = EmojiCache(_EMOJI_BASE_DIR)
        # Jest basina son oynatilan emoji varyanti — ayni duygu ust uste gelirse
        # ayni yuzu gostermemek icin (bkz _varyant_sec).
        self._son_varyant: dict[str, int] = {}
        self.variant = 0

    def _varyant_sec(self, jest_id: str, varyant_sayisi: int) -> int:
        """Rastgele varyant sec — en son oynatilani haric tutarak."""
        if varyant_sayisi <= 1:
            return 0
        son = self._son_varyant.get(jest_id, -1)
        if son < 0:
            idx = random.randrange(varyant_sayisi)          # ilk kez: hepsi esit sansli
        else:
            idx = random.randrange(varyant_sayisi - 1)      # [0, n-2] -> son haric [0, n-1]
            if idx >= son:
                idx += 1
        self._son_varyant[jest_id] = idx
        return idx

    def trigger(self, jest_id: str, yogunluk: Optional[float] = None,
                sure_sn: Optional[float] = None) -> bool:
        """sure_sn=None ise jest sonsuza kadar oynar (stop() ile durdurulur)."""
        g = self.gestures.get(jest_id)
        if not g:
            return False
        anim = g["animasyon"]
        self.active = g
        self.start = time.monotonic()
        self.duration = float("inf") if sure_sn is None else float(sure_sn)
        self.intensity = float(yogunluk if yogunluk is not None else anim["yogunluk_varsayilan"])
        if g.get("gorsel_tipi") == "emoji":
            self.variant = self._varyant_sec(jest_id, len(self.emoji_cache.get(jest_id)))
        else:
            self.variant = 0
        return True

    def stop(self) -> Optional[str]:
        """Aktif jesti durdur, idle'a don. Durdurulan jestin id'sini doner."""
        if not self.active:
            return None
        jid = self.active["id"]
        self.active = None
        return jid

    def render(self) -> list[tuple[int, int, int]]:
        now = time.monotonic()
        if self.active and (self.duration == float("inf") or (now - self.start) < self.duration):
            self._render_active(now)
        else:
            self.active = None
            self._render_idle(now)
        return self.buf.pixels

    def _render_active(self, now: float) -> None:
        g = self.active
        elapsed = now - self.start

        # Emoji yolu: secilen varyantin hazir frame'lerini sirayla oynat
        if g.get("gorsel_tipi") == "emoji":
            varyantlar = self.emoji_cache.get(g["id"])
            frames = varyantlar[self.variant] if self.variant < len(varyantlar) else (
                varyantlar[0] if varyantlar else [])
            if frames:
                idx = int(elapsed * EMOJI_FPS) % len(frames)
                src = frames[idx]
                if self.intensity >= 0.99:
                    self.buf.pixels[:] = src
                else:
                    k = self.intensity
                    self.buf.pixels[:] = [
                        (int(r * k), int(gv * k), int(bv * k)) for r, gv, bv in src
                    ]
                return
            # Frame bulunamadi (404 olan jestler vs.) - soyut desene düş

        # Soyut desen yolu
        anim = g["animasyon"]
        spd = SPEED_MULTS[SPEED_NAME_TO_ID[anim["hiz"]]]
        r, gg, b = anim["ana_renk"]
        sec = anim.get("ikincil_renk")
        r2, g2, b2 = (sec[0], sec[1], sec[2]) if sec else (0, 0, 0)
        fn = PATTERN_DISPATCH.get(anim["desen"])
        if fn is None:
            self.buf.clear()
            return
        fn(self.buf, elapsed, r, gg, b, r2, g2, b2, self.intensity, spd)

    def _render_idle(self, now: float) -> None:
        t = now - self._t0
        w = (math.sin(2 * math.pi * t / 4.0) + 1) * 0.5
        k = 0.18 + 0.22 * w
        self.buf.fill(_scale(60, 130, 150, k))

    def is_active(self) -> bool:
        if not self.active:
            return False
        if self.duration == float("inf"):
            return True
        return (time.monotonic() - self.start) < self.duration

    def active_id(self) -> Optional[str]:
        return self.active["id"] if self.active else None
