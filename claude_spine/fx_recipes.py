"""FX recipes: hand-tuned, parameterised glow / light / particle layers — the ``fx_recipe`` tool's engine.

``fx.py`` holds generic slot-game presets (explosion, coin_burst, ...). This module holds *authored* looks: each
recipe is one visual element lifted from a real reference clip (a lotus blooming out of a magic book) and rebuilt
as Spine primitives, so it can be placed, recoloured, resized and mixed with any other recipe or any rig.

    rune_ring     gold rune circle on a surface: builds up, flashes white, fades (iso-squashed, counter-rotating)
    burst_flare   anamorphic flare + shock ring + flung sparks, the "pop" moment
    rim_wisps     soft feathery fringe around a footprint
    bloom_aura    coloured halo + inner core + rising light column
    floor_glow    warm glow and streaky reflection underneath a subject
    fireflies     drifting motes, each with its own looping life and twinkle
    twinkles      four-point stars popping and spinning
    light_beam    vertical beam: column glow, filaments (weaving ribbons), dust, glints (gold | ribbon | blue)
    portal        swirling disc + arms + specks + comets + flashes; its plasma ring is After Effects (hybrid)
    electric_frame violet underglow + sparks; its lightning line is After Effects (hybrid)
    magic_reveal  the seven lotus recipes, timed like the reference clip (13.2 s), into one animation

Rules every recipe follows (they are why the output is cheap and drops into a game):

* Procedural textures only, baked white or colourised once; no art is needed and the atlas stays tiny.
* Additive blend everywhere, so all FX slots sit in one batch (1 draw call).
* One group bone per recipe at the *subject centre* (``x``, ``y``); its scale is ``scale``, so every dimension below is
  in design units (a ~720-unit canvas, a subject ~420 wide) and the whole recipe resizes as one piece.
* FX slots have no setup attachment: the animation switches them on and off, so they never show in the setup pose
  or in animations that do not use them.
* Keys are dense *linear* samples of a closed-form function of time (not hand-keyed beziers), so every curve is
  exact and a recipe can be retimed by scaling its time axis.
* Looping lives (fireflies) get explicit keys at every respawn so the position jump hides inside alpha 0.
* ``into=`` merges into an existing animation, ``start=`` shifts it in time; every recipe fires ``fx_<recipe>``.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx import tex_glow, tex_ring, tex_spark, _rgba
from .ir import Bone, MeshAttachment, RegionAttachment, Slot
from .project import Project
from .timeline import AnimBuilder, r


# ------------------------------------------------------------------ colour + texture helpers
def _hexn(c: str | None, default: str) -> str:
    c = (c or default).lstrip("#").upper()
    return c[:6]


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def hexa(rgb: str, a: float) -> str:
    return rgb.lstrip("#").upper()[:6] + f"{max(0, min(255, round(a * 255))):02X}"


def _grid(n: int):
    y, x = np.mgrid[0:n, 0:n].astype(float)
    c = (n - 1) / 2
    return (x - c) / c, (y - c) / c


def _blur(a: np.ndarray, rad: float) -> np.ndarray:
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(rad))
    return np.asarray(im, np.float32) / 255


def _colorize(a: np.ndarray, hot: tuple, mid: tuple, edge: tuple | None = None) -> Image.Image:
    """Intensity (0..1) -> RGBA whose colour runs edge -> mid -> hot (near-white core) as it gets brighter."""
    a = np.clip(a, 0, 1)
    edge = edge or mid
    t1 = np.clip(a / 0.5, 0, 1)[..., None]
    t2 = np.clip((a - 0.5) / 0.5, 0, 1)[..., None]
    rgb = np.array(edge) * (1 - t1) + np.array(mid) * t1
    rgb = rgb * (1 - t2) + np.array(hot) * t2
    return _rgba(rgb / 255.0, a)


def _palette(color: str) -> tuple[tuple, tuple, tuple]:
    """(hot, mid, edge) from one colour: white-ish core, the colour itself, a deeper rim."""
    mid = _rgb(color)
    return _mix(mid, (255, 255, 255), 0.82), mid, _mix(mid, (255, 120, 0) if mid[0] > mid[2] else (0, 40, 255), 0.18)


def tex_rune_ring(color: str = "FFCD3C", n: int = 512, runes: int = 12) -> Image.Image:
    """Double ring, rune glyphs between them, tick marks, a spiral at the middle. Drawn at 2x, blurred twice."""
    S = 2
    N = n * S
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    c = N / 2
    rng = np.random.default_rng(11)
    R = N / 2

    def circle(rad, w):
        d.ellipse([c - rad, c - rad, c + rad, c + rad], outline=255, width=max(1, int(w * S)))

    circle(R * 0.93, 3)
    circle(R * 0.88, 1.4)
    circle(R * 0.60, 2)
    circle(R * 0.565, 1)
    for k in range(runes):
        a = k / runes * 2 * math.pi
        cx, cy = c + math.cos(a) * R * 0.74, c + math.sin(a) * R * 0.74
        ux, uy = math.cos(a), math.sin(a)
        vx, vy = -uy, ux
        g = R * 0.075
        pts = [(cx + ux * rng.uniform(-g, g) + vx * rng.uniform(-g, g),
                cy + uy * rng.uniform(-g, g) + vy * rng.uniform(-g, g)) for _ in range(int(rng.integers(3, 5)))]
        d.line(pts, fill=255, width=int(3.2 * S), joint="curve")
        d.line([(cx - ux * g, cy - uy * g), (cx + ux * g, cy + uy * g)], fill=255, width=int(2 * S))
    for k in range(48):
        a = k / 48 * 2 * math.pi
        r0, r1 = R * 0.885, R * (0.905 if k % 4 else 0.925)
        d.line([(c + math.cos(a) * r0, c + math.sin(a) * r0), (c + math.cos(a) * r1, c + math.sin(a) * r1)],
               fill=255, width=int(1.6 * S))
    pts = []
    for i in range(160):
        t = i / 159
        a = t * 4.2 * math.pi
        rad = R * 0.52 * (1 - t) ** 0.85
        pts.append((c + math.cos(a) * rad, c + math.sin(a) * rad))
    d.line(pts, fill=255, width=int(4 * S), joint="curve")
    for a in (0, math.pi / 2):
        d.line([(c - math.cos(a) * R * 0.1, c - math.sin(a) * R * 0.1), (c + math.cos(a) * R * 0.1, c + math.sin(a) * R * 0.1)],
               fill=255, width=int(3 * S))
    base = np.asarray(img, np.float32) / 255
    a = np.clip(_blur(base, 1.3 * S) * 1.15 + _blur(base, 7 * S) * 0.85, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS), np.float32) / 255
    x, y = _grid(n)
    a *= np.clip((1 - np.hypot(x, y)) / 0.06, 0, 1)         # nothing at the border: the quad edge never shows
    return _colorize(a, *_palette(color))


def tex_flare(color: str = "FFEE8C", w: int = 512, h: int = 128) -> Image.Image:
    """Anamorphic horizontal streak with a hot core; the tails take the colour."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    streak = np.exp(-(yn / 0.10) ** 2) * np.exp(-np.abs(xn) / 0.40)
    thin = np.exp(-(yn / 0.03) ** 2) * np.exp(-np.abs(xn) / 0.7)
    halo = np.exp(-((xn / 0.30) ** 2 + (yn / 0.42) ** 2))
    a = np.clip(streak * 0.95 + thin * 0.9 + halo * 0.55, 0, 1) * np.clip((1 - np.abs(xn)) / 0.06, 0, 1) * np.clip((1 - np.abs(yn)) / 0.1, 0, 1)
    hot, mid, edge = _palette(color)
    return _colorize(a, hot, mid, _mix(edge, (200, 235, 110), 0.35))


def tex_wisp(w: int = 256, h: int = 128, seed: int = 5) -> Image.Image:
    """Soft feathery tuft: base on the left edge, fraying to the right. Fine streaks run along its length.
    (Thresholding the noise to zero made speckle pits and read as gas flames; keep a floor under the streaks.)"""
    rng = np.random.default_rng(seed)

    def stretch(rows, cols):
        lo = rng.random((rows, cols))
        return np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255

    streak = 0.65 * stretch(h // 9, w // 36 + 2) + 0.35 * stretch(h // 4, w // 18 + 2)
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = x / (w - 1)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    width = 0.95 * (1 - xn ** 1.15) + 0.10
    env = np.exp(-(yn / np.maximum(width, 1e-3)) ** 2)
    a = env * (0.42 + 0.9 * streak) * np.clip(1 - xn, 0, 1) ** 1.5
    a *= np.clip(xn / 0.04, 0, 1) * np.clip((1 - np.abs(yn)) / 0.10, 0, 1)
    return _colorize(a * 1.2, (255, 255, 255), (255, 250, 232), (255, 238, 200))


def tex_beam(w: int = 128, h: int = 512) -> Image.Image:
    """Vertical light column, bright at the bottom, fading up, soft sides."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = 1 - y / (h - 1)
    a = np.exp(-(xn / (0.22 + 0.5 * (1 - yn))) ** 2) * (yn ** 1.6)
    a *= np.clip((1 - np.abs(xn)) / 0.1, 0, 1) * np.clip(y / 30, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_mote(n: int = 64) -> Image.Image:
    x, y = _grid(n)
    d = np.hypot(x, y)
    a = (np.exp(-(d / 0.16) ** 2) + 0.38 * np.exp(-(d / 0.55) ** 2)) * np.clip((1 - d) / 0.12, 0, 1)
    w3 = (255, 255, 255)
    return _colorize(np.clip(a, 0, 1), w3, w3, w3)


def tex_reflect(w: int = 128, h: int = 256) -> Image.Image:
    """Blurred vertical smear fading downward. Soft top edge and low-contrast streaks: a hard top line or strong
    banding reads as a curtain, not a reflection."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = y / (h - 1)
    a = np.exp(-(xn / 0.62) ** 2) * (1 - yn) ** 1.8 * np.clip(yn / 0.18, 0, 1)
    a *= 0.8 + 0.2 * np.cos(xn * 6.5 + 0.4) ** 2
    a *= np.clip((1 - np.abs(xn)) / 0.2, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1) * 0.9)


def tex_column(w: int = 128, h: int = 512) -> Image.Image:
    """Soft vertical column of light: gaussian across, smooth ends."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = y / (h - 1)
    a = np.exp(-(xn / 0.42) ** 2) * np.minimum(smooth_arr(yn, 0.0, 0.16), smooth_arr(1 - yn, 0.0, 0.16))
    a *= np.clip((1 - np.abs(xn)) / 0.12, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def smooth_arr(t, a, b):
    u = np.clip((t - a) / max(b - a, 1e-9), 0, 1)
    return u * u * (3 - 2 * u)


def tex_strand(color: str = "FFD21F", w: int = 64, h: int = 512) -> Image.Image:
    """One glowing vertical filament: hot thin core, soft halo, tapered ends, a little brightness drift along it."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = y / (h - 1)
    a = np.exp(-(xn / 0.11) ** 2) + 0.38 * np.exp(-(xn / 0.46) ** 2)
    a *= np.minimum(smooth_arr(yn, 0.0, 0.12), smooth_arr(1 - yn, 0.0, 0.12))
    a *= 0.82 + 0.18 * np.sin(yn * 23.0) * np.sin(yn * 7.0 + 1.0)
    a *= np.clip((1 - np.abs(xn)) / 0.1, 0, 1)
    return _colorize(np.clip(a, 0, 1), *_palette(color))



def tex_disc(color: str = "4A78FF", n: int = 384) -> Image.Image:
    """Dark indigo disc, a touch brighter toward the rim, soft edge. Meant for normal blend (it occludes)."""
    x, y = _grid(n)
    d = np.hypot(x, y)
    rim = smooth_arr(d, 0.35, 0.95)
    base = _mix((8, 6, 52), _mix(_rgb(color), (20, 20, 120), 0.45), 0.0)
    rgb = np.zeros((n, n, 3))
    for i in range(3):
        rgb[..., i] = (base[i] * (1 - rim) + _mix(_rgb(color), (14, 14, 110), 0.55)[i] * rim) / 255.0
    a = np.clip((1 - d) / 0.05, 0, 1)
    return _rgba(rgb, a)


def tex_swirl(arms: int = 3, color: str = "4A78FF", n: int = 512, twist: float = 2.3, seed: int = 2) -> Image.Image:
    """Spiral arms (logarithmic-ish), brighter and tighter toward the rim, hollow centre. Rotate it with a bone."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    # a little noise in the arm phase so the arms are not mathematically clean
    lo = rng.random((12, 12))
    nz = np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), np.float32) / 255
    ph = th * arms / (2 * math.pi) - twist * (1 - r) * arms * 0.5 + 0.18 * (nz - 0.5)
    f = ph - np.floor(ph)
    w = 0.11 + 0.10 * (1 - r)
    arm = np.exp(-((f - 0.5) / w) ** 2)
    a = arm * smooth_arr(r, 0.06, 0.34) * (1 - smooth_arr(r, 0.82, 0.98)) * (0.55 + 0.45 * r)
    return _colorize(np.clip(a, 0, 1), (215, 235, 255), _rgb(color), _mix(_rgb(color), (70, 20, 190), 0.55))


def tex_comet(color: str = "BFE8FF", n: int = 512, sweep: float = 210.0, turns: float = 0.8) -> Image.Image:
    """A single thin spiral streak with a bright head and a fading tail (the white curl that whips around inside the portal)."""
    S = 2
    N = n * S
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    c = N / 2
    m = 120
    pts = []
    for i in range(m + 1):
        t = i / m                          # 0 = head (outer), 1 = tail
        ang = math.radians(sweep) * t
        rad = (N / 2) * (0.84 - 0.62 * t ** 0.9)
        pts.append((c + math.cos(-ang) * rad, c + math.sin(-ang) * rad, t))
    for i in range(m):
        a0, a1 = pts[i], pts[i + 1]
        t = a0[2]
        d.line([(a0[0], a0[1]), (a1[0], a1[1])], fill=int(255 * (1 - t) ** 1.25), width=max(1, int((6.5 - 4.2 * t) * S)))
    base = np.asarray(img, np.float32) / 255
    a = np.clip(_blur(base, 1.2 * S) * 1.2 + _blur(base, 6 * S) * 0.7, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS), np.float32) / 255
    return _colorize(a, (255, 255, 255), _rgb(color), _mix(_rgb(color), (60, 90, 255), 0.5))



def tex_rrglow(w: float = 400, h: float = 400, corner: float = 0.14, spread: float = 0.16, n: int = 512) -> Image.Image:
    """Soft glow hugging a rounded rectangle (strongest on the outline, fading both outward and inward). Texture is square; the slot is sized w x h."""
    x, y = _grid(n)
    hx = hy = 0.74
    cr = corner
    qx, qy = np.abs(x) - (hx - cr), np.abs(y) - (hy - cr)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - cr
    out = np.exp(-(np.maximum(d, 0) / spread) ** 2)
    inn = 0.9 * np.exp(-(np.maximum(-d, 0) / (spread * 0.9)) ** 2)     # inside: fades inward, no fill
    a = np.where(d > 0, out, inn)
    a *= np.clip((1 - np.hypot(x, y) * 0.74) / 0.08, 0, 1)
    a *= np.clip((1 - np.maximum(np.abs(x), np.abs(y))) / 0.06, 0, 1)   # exactly 0 on the border: no faint box edge
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))



def _rr_sdf(n: int, hx: float, hy: float, cr: float):
    x, y = _grid(n)
    qx, qy = np.abs(x) - (hx - cr), np.abs(y) - (hy - cr)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - cr


def tex_frame9(color: str = "20E8C8", n: int = 192) -> Image.Image:
    """Source for a 9-slice glowing frame: a thin hot line on a rounded rectangle with a soft halo on both sides.
    Slice at 48 px: the corners (arc included) live inside the slices, the edge cross-section is constant along the
    middle, so stretching the middle never shows."""
    d = _rr_sdf(n, 0.78, 0.78, 0.14)
    core = np.exp(-(d / 0.016) ** 2)
    halo = np.where(d > 0, 0.6 * np.exp(-(d / 0.075) ** 2), 0.45 * np.exp(-(-d / 0.055) ** 2))
    x, y = _grid(n)
    a = np.clip(core + halo, 0, 1) * np.clip((1 - np.maximum(np.abs(x), np.abs(y))) / 0.04, 0, 1)
    return _colorize(a, *_palette(color))


def tex_cellfill(n: int = 192) -> Image.Image:
    """Soft rounded-rectangle fill, brighter toward the rim (white; tint with the slot colour)."""
    d = _rr_sdf(n, 0.78, 0.78, 0.14)
    inside = np.where(d < 0, 0.85 + 0.15 * np.exp(-(-d / 0.20) ** 2), np.exp(-(d / 0.05) ** 2) * 0.8)
    x, y = _grid(n)
    a = inside * np.clip((1 - np.maximum(np.abs(x), np.abs(y))) / 0.05, 0, 1)
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))


def tex_reticle(color: str = "FFB02E", n: int = 512) -> Image.Image:
    """Targeting reticle: double ring with four notches, a gapped cross, tick marks, soft glow."""
    S = 2
    N = n * S
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    c = N / 2
    R = N / 2

    def arc(rad, w, a0, a1):
        d.arc([c - rad, c - rad, c + rad, c + rad], a0, a1, fill=255, width=max(1, int(w * S)))
    for q in range(4):                                  # outer ring in four arcs (notches at the axes)
        arc(R * 0.86, 7, q * 90 + 12, q * 90 + 78)
    d.ellipse([c - R * 0.72, c - R * 0.72, c + R * 0.72, c + R * 0.72], outline=255, width=int(2.4 * S))
    for q in range(4):                                  # cross: long line outside the ring, short inside, gap at the centre
        ang = q * math.pi / 2
        ux, uy = math.cos(ang), math.sin(ang)
        d.line([(c + ux * R * 0.22, c + uy * R * 0.22), (c + ux * R * 0.60, c + uy * R * 0.60)], fill=255, width=int(3.2 * S))
        d.line([(c + ux * R * 0.80, c + uy * R * 0.80), (c + ux * R * 0.97, c + uy * R * 0.97)], fill=255, width=int(5 * S))
    for q in range(4):                                  # diagonal ticks
        ang = math.pi / 4 + q * math.pi / 2
        ux, uy = math.cos(ang), math.sin(ang)
        d.line([(c + ux * R * 0.66, c + uy * R * 0.66), (c + ux * R * 0.77, c + uy * R * 0.77)], fill=255, width=int(3 * S))
    r0 = R * 0.035
    d.ellipse([c - r0, c - r0, c + r0, c + r0], fill=255)
    base = np.asarray(img, np.float32) / 255
    a = np.clip(_blur(base, 1.2 * S) * 1.15 + _blur(base, 7 * S) * 0.9, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS), np.float32) / 255
    x, y = _grid(n)
    a *= np.clip((1 - np.hypot(x, y)) / 0.04, 0, 1)
    return _colorize(a, *_palette(color))


def tex_starburst(color: str = "FFB347", n: int = 512, rays: int = 13, seed: int = 9) -> Image.Image:
    """Irregular spiky star with a hot core, for an impact flash."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    ang = rng.uniform(0, 2 * math.pi, rays)
    ln = rng.uniform(0.45, 0.98, rays)
    wd = rng.uniform(0.05, 0.11, rays)
    a = np.zeros((n, n))
    for k in range(rays):
        dth = np.abs(((th - ang[k] + math.pi) % (2 * math.pi)) - math.pi)
        spike = np.exp(-(dth / (wd[k] * (1.3 - np.clip(r / ln[k], 0, 1)))) ** 2) * np.clip(1 - r / ln[k], 0, 1) ** 1.2
        a = np.maximum(a, spike)
    a = np.maximum(a, np.exp(-(r / 0.16) ** 2))
    a += 0.35 * np.exp(-(r / 0.38) ** 2)
    a *= np.clip((1 - r) / 0.05, 0, 1)
    return _colorize(np.clip(a, 0, 1), *_palette(color))



def tex_cloud(n: int = 256, seed: int = 4, soft: float = 0.06, shade: float = 0.24) -> Image.Image:
    """A round cartoon puff: 6-8 overlapping soft discs (metaballs) with a crisp-soft rim and shading from the top-left.
    (A radius wobbled by sines made spiky crumpled-paper shapes; overlapping discs read as a cloud.) White; tint with the slot."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    field = np.zeros((n, n))
    m = int(rng.integers(6, 9))
    for k in range(m):
        ang = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(0.0, 0.42) if k else 0.0
        rad = rng.uniform(0.26, 0.40) if k else 0.46
        cx, cy = math.cos(ang) * dist, math.sin(ang) * dist
        field += np.exp(-((np.hypot(x - cx, y - cy)) / rad) ** 2.4)
    a = np.clip((field - 0.62) / (soft * 4), 0, 1)
    a = a * a * (3 - 2 * a)
    light = 1.0 - shade * np.clip((x * 0.45 - y * 0.55 + 1) / 2, 0, 1) * np.clip(np.hypot(x, y) / 0.7, 0, 1)
    rgb = np.dstack([light, light, light * 0.985])
    return _rgba(rgb, a * np.clip((1 - np.hypot(x, y)) / 0.05, 0, 1))


def tex_smoke(n: int = 256, seed: int = 8) -> Image.Image:
    """A billowy smoke blob: soft round envelope times fractal noise, no hard rim. White (tint with the slot)."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    r = np.hypot(x, y)
    nz = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(5):
        cells = 3 * 2 ** o
        lo = rng.random((cells, cells))
        layer = np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), np.float32) / 255
        nz += amp * layer
        tot += amp
        amp *= 0.5
    nz /= tot
    env = np.exp(-(r / 0.55) ** 2)
    a = np.clip((nz - 0.28) * 2.2, 0, 1) * env
    a *= np.clip((1 - r) / 0.15, 0, 1)
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))



def tex_trail(color: str = "FFD25A", w: int = 64, h: int = 512) -> Image.Image:
    """A comet tail laid out vertically: v=0 (top) is the head, bright and wide, fading and narrowing to nothing at v=1."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    v = y / (h - 1)
    width = 0.55 * (1 - v) ** 0.8 + 0.06
    core = np.exp(-(xn / (width * 0.35)) ** 2)
    halo = 0.45 * np.exp(-(xn / width) ** 2)
    a = (core + halo) * (1 - v) ** 1.4 * np.clip(v / 0.02, 0, 1) ** 0.5
    a *= np.clip((1 - np.abs(xn)) / 0.1, 0, 1)
    return _colorize(np.clip(a, 0, 1), *_palette(color))



def tex_rays(color: str = "FFF2B0", n: int = 512, rays: int = 14, seed: int = 2) -> Image.Image:
    """A lens-flare star: many thin rays of uneven length from a hot core, soft, for a shine burst."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    a = np.zeros((n, n))
    base = rng.uniform(0, 2 * math.pi)
    for k in range(rays):
        ang = base + k * 2 * math.pi / rays + rng.uniform(-0.08, 0.08)
        ln = rng.uniform(0.35, 1.0) if k % 2 else rng.uniform(0.7, 1.0)
        wd = rng.uniform(0.012, 0.03)
        dth = np.abs(((th - ang + math.pi) % (2 * math.pi)) - math.pi)
        ray = np.exp(-(dth * r / (wd + 0.02 * r)) ** 2) * np.clip(1 - r / ln, 0, 1) ** 1.6
        a = np.maximum(a, ray)
    a = np.clip(a + np.exp(-(r / 0.12) ** 2) + 0.25 * np.exp(-(r / 0.3) ** 2), 0, 1)
    a *= np.clip((1 - r) / 0.04, 0, 1)
    return _colorize(a, *_palette(color))

# texture name -> factory (white textures are tinted per slot; coloured ones are named with their colour)
WHITE_TEX: dict[str, Callable[[], Image.Image]] = {
    "fx/wisp": tex_wisp, "fx/beam": tex_beam, "fx/mote": tex_mote, "fx/reflect": tex_reflect,
    "fx/glow": tex_glow, "fx/ring": tex_ring, "fx/spark": tex_spark, "fx/column": tex_column,
    "fx/rrglow": lambda: tex_rrglow(), "fx/cellfill": lambda: tex_cellfill(),
    "fx/cloud": tex_cloud, "fx/smoke": tex_smoke,
}


# ------------------------------------------------------------------ custom art
def load_art(spec: Any) -> tuple[Image.Image, dict]:
    """spec: "path.png", "path.psd#Layer name" (or "path.psd#Group/Layer"), or {"path": ..., blend, scale, slice, px, anchor}.
    Returns (RGBA image, options). A PSD layer is cut at its own bounding box, so its centre is the target point."""
    import os
    opts: dict = {}
    if isinstance(spec, dict):
        opts = {k: v for k, v in spec.items() if k != "path"}
        spec = spec.get("path")
    if not spec:
        raise ValueError("art entry needs a path")
    path = os.path.expanduser(str(spec))
    if "#" in path and path.split("#", 1)[0].lower().endswith(".psd"):
        file, layer_name = path.split("#", 1)
        from psd_tools import PSDImage
        psd = PSDImage.open(file)
        want = layer_name.strip().lower().split("/")
        found = None

        def walk(group, trail):
            nonlocal found
            for lay in group:
                here = trail + [lay.name.strip().lower()]
                if here[-len(want):] == want and not lay.is_group():
                    found = lay
                    return
                if lay.is_group():
                    walk(lay, here)
                    if found is not None:
                        return
        walk(psd, [])
        if found is None:
            raise ValueError(f"layer {layer_name!r} not found in {file}")
        im = found.composite() or found.topil()
        if im is None:
            raise ValueError(f"layer {layer_name!r} in {file} has no pixels")
    else:
        if not os.path.exists(path):
            raise ValueError(f"art file not found: {path}")
        im = Image.open(path)
    return im.convert("RGBA"), opts


# ------------------------------------------------------------------ math helpers
def smooth(t, a, b):
    u = np.clip((t - a) / max(b - a, 1e-9), 0, 1)
    return float(u * u * (3 - 2 * u))


def ease_out(u, p=3.0):
    return float(1 - (1 - np.clip(u, 0, 1)) ** p)


def times_dense(t0: float, t1: float, rate: float) -> list[float]:
    n = max(2, int(math.ceil((t1 - t0) * rate)) + 1)
    return [float(v) for v in np.linspace(t0, t1, n)]


def rr_point(s_: float, w: float, h: float, r: float) -> tuple[float, float, float]:
    """Point and tangent angle (deg) at fraction s_ of a rounded rectangle's perimeter, clockwise from the top-left
    end of the top edge (y up). The angle keeps decreasing lap after lap (-360 per lap), so keys never wrap."""
    r = max(0.0, min(r, w / 2, h / 2))
    sw, sh, arc = w - 2 * r, h - 2 * r, math.pi * r / 2
    # (kind, length, start point or arc centre, edge direction or arc start angle); angles are continuous around the loop
    segs = [("L", sw, (-w / 2 + r, h / 2), 0.0), ("A", arc, (w / 2 - r, h / 2 - r), 90.0),
            ("L", sh, (w / 2, h / 2 - r), -90.0), ("A", arc, (w / 2 - r, -h / 2 + r), 0.0),
            ("L", sw, (w / 2 - r, -h / 2), -180.0), ("A", arc, (-w / 2 + r, -h / 2 + r), -90.0),
            ("L", sh, (-w / 2, -h / 2 + r), -270.0), ("A", arc, (-w / 2 + r, h / 2 - r), -180.0)]
    total = sum(sg[1] for sg in segs) or 1.0
    lap = math.floor(s_)
    d = (s_ - lap) * total
    for k, (kind, ln, p0, a0) in enumerate(segs):
        if d <= ln or k == len(segs) - 1:
            d = min(d, ln)
            if kind == "L":
                x, y, ang = p0[0] + math.cos(math.radians(a0)) * d, p0[1] + math.sin(math.radians(a0)) * d, a0
            else:
                phi = math.radians(a0) - (d / max(arc, 1e-9)) * math.pi / 2      # clockwise quarter arc
                x, y, ang = p0[0] + r * math.cos(phi), p0[1] + r * math.sin(phi), math.degrees(phi) - 90.0
            return x, y, ang - 360.0 * lap
        d -= ln
    return -w / 2 + r, h / 2, -360.0 * lap


def _bez(p0, p1, p2, t):
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
    dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
    dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
    return x, y, math.degrees(math.atan2(dy, dx))



def _br(t, f, p=0.0):
    return 0.5 + 0.5 * math.sin(2 * math.pi * t * f + p)


# ------------------------------------------------------------------ build context
class Ctx:
    """One recipe application: a group bone at the subject centre, slots in one run, keys into one animation."""

    def __init__(self, p: Project, recipe: str, x: float, y: float, scale: float, start: float, k: float,
                 intensity: float, seed: int, into: str, parent: str, front_of: str, behind: str, name: str,
                 art: dict | None = None):
        self.p, self.sk = p, p.data
        self.art = art or {}
        self._art_cache: dict[str, dict] = {}
        self.art_used: dict[str, str] = {}
        self.recipe = recipe
        self.t0, self.k, self.I, self.seed, self.S = start, k, intensity, seed, scale
        self.anim = into or f"fx_{name or recipe}"
        self.ab = AnimBuilder(self.sk, self.anim, replace=not into)
        self.prefix = name or recipe
        self.front_of, self.behind = front_of, behind
        self.last_slot: str | None = None
        self.slots: list[str] = []
        self.bones: list[str] = []
        self.group = self.bone("grp", parent, x, y, sx=scale, sy=scale, root=True)

    # -- structure
    def bone(self, suffix: str, parent: str | None = None, x: float = 0, y: float = 0, rot: float = 0,
             sx: float = 1, sy: float = 1, root: bool = False) -> str:
        base = f"fx_{self.prefix}" if root else f"fx_{self.prefix}_{suffix}"
        nm = self.sk.unique_name(base)
        self.sk.bones.append(Bone(name=nm, parent=parent or self.group, x=x, y=y, rotation=rot, scaleX=sx, scaleY=sy, length=10))
        self.bones.append(nm)
        return nm

    def tex(self, name: str, make: Callable[[], Image.Image] | None = None) -> tuple[int, int]:
        try:
            im = self.p.image(name)
        except FileNotFoundError:
            im = (make or WHITE_TEX[name])()
            self.p.write_image(name, im)
        return im.size

    def _art(self, role: str | None) -> dict | None:
        """The user's picture for `role` (written into the project once), or None to use the generated one."""
        if not role or role not in self.art:
            return None
        if role not in self._art_cache:
            im, opts = load_art(self.art[role])
            name = f"fx/art_{self.recipe}_{role}"
            self.p.write_image(name, im)
            self._art_cache[role] = dict(tex=name, size=im.size, **opts)
            self.art_used[role] = name
        return self._art_cache[role]

    def slot(self, bone: str, tex: str, width: float, color: str = "FFFFFFFF", ox: float = 0.0, oy: float = 0.0,
             height: float | None = None, make: Callable[[], Image.Image] | None = None, blend: str = "additive",
             role: str | None = None, anchor: str = "center", stretch: bool = False) -> str:
        art = self._art(role)
        if art:                                   # the user's picture keeps its own aspect; the recipe keeps its width
            tex, make, blend = art["tex"], None, art.get("blend", blend)
            width = width * float(art.get("scale", 1.0))
            if not stretch:                       # stretch: the recipe's height wins (a column must span the beam)
                height = width * art["size"][1] / art["size"][0]
            ox = {"left": width / 2, "right": -width / 2}.get(art.get("anchor", anchor), 0.0)
            oy = {"bottom": height / 2, "top": -height / 2}.get(art.get("anchor", anchor), 0.0)
        nm = self.sk.unique_name(bone, "slot")
        s = Slot(name=nm, bone=bone, color=color, blend=blend)
        if self.last_slot is not None:
            self.sk.add_slot(s, after=self.last_slot)
        elif self.behind:
            self.sk.add_slot(s, before=self.behind)
        elif self.front_of:
            self.sk.add_slot(s, after=self.front_of)
        else:
            self.sk.add_slot(s)
        self.last_slot = nm
        tw, th = self.tex(tex, make)
        h = height if height is not None else width * th / tw
        self.sk.set_attachment(nm, "fx", RegionAttachment(path=tex, x=round(ox, 2), y=round(oy, 2), width=round(width, 2), height=round(h, 2)))
        self.slots.append(nm)
        return nm

    def strand(self, parent: str, tex: str, width: float, height: float, rows: int, x: float = 0.0,
               color: str = "FFFFFFFF", make: Callable[[], Image.Image] | None = None, tag: str = "st",
               role: str | None = None):
        """A tall ribbon mesh whose rows are each pinned to one bone, so animating those bones' translateX bends
        it into any wave (a weighted mesh costs no deform keys). Returns (slot, [row bones bottom->top])."""
        sk = self.sk
        art = self._art(role)
        blend = "additive"
        if art:
            tex, make, blend = art["tex"], None, art.get("blend", "additive")
            width = width * float(art.get("scale", 1.0))
        base = self.bone(tag, parent, x, 0)
        ys = [-height / 2 + i * height / (rows - 1) for i in range(rows)]
        nodes = [self.bone(f"{tag}_n{i}", base, 0, y) for i, y in enumerate(ys)]
        nm = sk.unique_name(base, "slot")
        s = Slot(name=nm, bone=base, color=color, blend=blend)
        if self.last_slot is not None:
            sk.add_slot(s, after=self.last_slot)
        elif self.behind:
            sk.add_slot(s, before=self.behind)
        elif self.front_of:
            sk.add_slot(s, after=self.front_of)
        else:
            sk.add_slot(s)
        self.last_slot = nm
        self.tex(tex, make)
        hw = width / 2
        verts: list[float] = []
        for i in range(rows):                       # hull order: left column up, then right column down
            verts += [1, sk.bone_index(nodes[i]), -hw, 0, 1]
        for i in range(rows - 1, -1, -1):
            verts += [1, sk.bone_index(nodes[i]), hw, 0, 1]
        uvs: list[float] = []
        for i in range(rows):
            uvs += [0.0, round(1 - i / (rows - 1), 5)]
        for i in range(rows - 1, -1, -1):
            uvs += [1.0, round(1 - i / (rows - 1), 5)]
        tris: list[int] = []
        n2 = 2 * rows
        for i in range(rows - 1):
            Li, Li1, Ri, Ri1 = i, i + 1, n2 - 1 - i, n2 - 2 - i
            tris += [Li, Ri, Ri1, Li, Ri1, Li1]
        edges = []
        for i in range(n2):
            edges += [i * 2, ((i + 1) % n2) * 2]
        sk.set_attachment(nm, "fx", MeshAttachment(path=tex, uvs=uvs, triangles=tris, vertices=verts, hull=n2, edges=edges,
                                                    width=round(width, 2), height=round(height, 2)))
        self.slots.append(nm)
        return nm, nodes

    def slice9(self, parent: str, tex: str, w: float, h: float, slice_px: float = 64.0, color: str = "FFFFFFFF",
               make: Callable[[], Image.Image] | None = None, tag: str = "s9", blend: str = "additive",
               share: tuple | None = None, role: str | None = None):
        """A 9-slice frame as a weighted mesh on four corner bones (TL, TR, BL, BR): the corners keep their art,
        the edges and the middle stretch. Move the corner bones in the game and the frame resizes. Returns
        (slot, {"tl": bone, ...}). share=(base, corners) from an earlier call makes this mesh ride the same corner bones."""
        sk = self.sk
        art = self._art(role)
        px = 1.0
        if art:                                  # custom 9-slice art: slice = corner size in art pixels, px = units per art pixel
            tex, make, blend = art["tex"], None, art.get("blend", blend)
            slice_px = float(art.get("slice", slice_px))
            px = float(art.get("px", 1.0))
        tw, th = self.tex(tex, make)
        s_ = min(slice_px * px, w / 2, h / 2)
        pos = {"tl": (-w / 2, h / 2), "tr": (w / 2, h / 2), "bl": (-w / 2, -h / 2), "br": (w / 2, -h / 2)}
        if share:                                     # reuse another 9-slice's corner bones: one set resizes both meshes
            base, cb = share
        else:
            base = self.bone(tag, parent, 0, 0)
            cb = {k: self.bone(f"{tag}_{k}", base, *pos[k]) for k in pos}
        xs = [-w / 2, -w / 2 + s_, w / 2 - s_, w / 2]
        ys = [h / 2, h / 2 - s_, -h / 2 + s_, -h / 2]
        us = [0.0, slice_px / tw, 1 - slice_px / tw, 1.0]
        vs = [0.0, slice_px / th, 1 - slice_px / th, 1.0]
        order = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (3, 3), (3, 2), (3, 1), (3, 0), (2, 0), (1, 0),
                 (1, 1), (1, 2), (2, 1), (2, 2)]
        idx = {ij: k for k, ij in enumerate(order)}
        verts: list[float] = []
        uvs: list[float] = []
        for (i, j) in order:
            key = ("t" if i < 2 else "b") + ("l" if j < 2 else "r")
            cx, cy = pos[key]
            verts += [1, sk.bone_index(cb[key]), round(xs[j] - cx, 3), round(ys[i] - cy, 3), 1]
            uvs += [round(us[j], 5), round(vs[i], 5)]
        tris: list[int] = []
        for i in range(3):
            for j in range(3):
                a_, b_, c_, d_ = idx[(i, j)], idx[(i, j + 1)], idx[(i + 1, j + 1)], idx[(i + 1, j)]
                tris += [a_, b_, c_, a_, c_, d_]
        edges: list[int] = []
        for k in range(12):
            edges += [k * 2, ((k + 1) % 12) * 2]
        nm = sk.unique_name(base, "slot")
        sl = Slot(name=nm, bone=base, color=color, blend=blend)
        if self.last_slot is not None:
            sk.add_slot(sl, after=self.last_slot)
        elif self.behind:
            sk.add_slot(sl, before=self.behind)
        elif self.front_of:
            sk.add_slot(sl, after=self.front_of)
        else:
            sk.add_slot(sl)
        self.last_slot = nm
        sk.set_attachment(nm, "fx", MeshAttachment(path=tex, uvs=uvs, triangles=tris, vertices=verts, hull=12, edges=edges,
                                                    width=tw, height=th))
        self.slots.append(nm)
        self._last_s9 = (base, cb)
        return nm, cb

    # -- keys (local time u at design speed -> animation time)
    def T(self, u: float) -> float:
        return r(self.t0 + u * self.k, 4)

    def a(self, v: float) -> float:
        return min(1.0, max(0.0, v * self.I))

    def show(self, slots: list[str], u_on: float, u_off: float | None) -> None:
        for s in slots:
            pts: list = [(0.0, None), (self.T(u_on), "fx")] if self.T(u_on) > 0 else [(0.0, "fx")]
            if u_off is not None:
                pts.append((self.T(u_off), None))
            self.ab.slot_attachment(s, pts)

    def bone_keys(self, bone: str, timeline: str, ts, fn) -> None:
        pts = []
        for u in ts:
            v = fn(u)
            pts.append((self.T(u), *(v if isinstance(v, tuple) else (v,))))
        self.ab.bone(bone, timeline, _uniq(pts), "linear")

    def color_keys(self, slot: str, ts, fn) -> None:
        self.ab.slot_color(slot, _uniq([(self.T(u), fn(u)) for u in ts]), "linear")

    def result(self, **extra) -> dict:
        self.ab.event(self.t0, f"fx_{self.recipe}")
        return {"recipe": self.recipe, "animation": self.anim, "group_bone": self.group, "bones": len(self.bones),
                "slots": list(self.slots), "event": f"fx_{self.recipe}", "start": self.t0, **extra}


def _uniq(pts: list) -> list:
    """Drop keys whose time repeats (retiming can collapse two samples onto one tick)."""
    out: list = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-6:
            out[-1] = p
        else:
            out.append(p)
    return out


# ------------------------------------------------------------------ the recipes
# Each takes (ctx, params) where params is the merged defaults+overrides dict, and returns a result dict.
def rune_ring(c: Ctx, P: dict) -> dict:
    D = 2.7
    color = _hexn(P["color"], "FFCD3C")
    runes = int(P["runes"])
    tname = f"fx/rune_ring_{color}" + ("" if runes == 12 else f"_{runes}")
    mk = lambda: tex_rune_ring(color, runes=runes)  # noqa: E731
    grp = c.bone("ring", c.group, 8, 24, sx=1, sy=float(P["squash"]))     # iso squash: children rotate in the plane
    b_out, b_in, b_core = c.bone("outer", grp), c.bone("inner", grp), c.bone("core", grp)
    s_glow = c.slot(b_core, "fx/glow", 370)
    s_out = c.slot(b_out, tname, 400, make=mk, role="ring")
    s_in = c.slot(b_in, tname, 238, make=mk, role="ring_inner" if "ring_inner" in c.art else "ring")
    s_flash = c.slot(b_core, "fx/glow", 170)
    ts = times_dense(0, D, 24)
    c.show([s_glow, s_out, s_in, s_flash], 0, D)
    peak = 1.45
    build = lambda u: smooth(u, 0.0, 1.3)  # noqa: E731
    fade = lambda u: 1 - smooth(u, 1.65, D)  # noqa: E731
    flick = lambda u: 0.9 + 0.1 * math.sin(u * 17) * math.sin(u * 5.3)  # noqa: E731
    env = lambda u: (0.08 + 0.92 * build(u)) * fade(u) * flick(u)  # noqa: E731
    spin = float(P["spin"])

    def scl(u):
        s = 0.62 + 0.38 * ease_out(u / 1.0, 2.5)
        if u > 1.45:
            s += 0.22 * smooth(u, 1.45, D)
        return s
    ang = lambda u: -(spin * u + 70 * smooth(u, 0.9, 1.6) * (u - 0.9))  # noqa: E731
    c.bone_keys(b_out, "rotate", ts, ang)
    c.bone_keys(b_out, "scale", ts, lambda u: (scl(u), scl(u)))
    c.bone_keys(b_in, "rotate", ts, lambda u: -1.6 * ang(u))
    c.bone_keys(b_in, "scale", ts, lambda u: (scl(u) * 0.96 + 0.04,) * 2)
    for s in (s_out, s_in):
        c.color_keys(s, ts, lambda u: hexa("FFFFFF", c.a(env(u) * 1.05)))
    core = _hexn(None, color)
    gl = lambda u: (0.12 + 0.5 * build(u) + 0.55 * math.exp(-((u - peak) / 0.16) ** 2)) * fade(u)  # noqa: E731
    c.color_keys(s_glow, ts, lambda u: hexa(core, c.a(gl(u))))
    cs = lambda u: 0.8 + 0.25 * build(u) + 0.3 * math.exp(-((u - peak) / 0.25) ** 2)  # noqa: E731
    c.bone_keys(b_core, "scale", ts, lambda u: (cs(u), cs(u)))
    flash = float(P["flash"])
    c.color_keys(s_flash, ts, lambda u: hexa("FFFBE0", c.a(flash * math.exp(-((u - peak) / 0.12) ** 2))))
    return c.result(duration=D * c.k, peak_at=c.T(peak))


def burst_flare(c: Ctx, P: dict) -> dict:
    D = 1.8
    color = _hexn(P["color"], "FFEE8C")
    ring_color = _hexn(P["ring_color"], "FFE9A0")
    ns = int(P["count"])
    tname = f"fx/flare_{color}"
    mk = lambda: tex_flare(color)  # noqa: E731
    grp = c.bone("flare", c.group, 0, 62)
    b_h, b_v = c.bone("h", grp), c.bone("v", grp, rot=90)
    b_core, b_ring = c.bone("core", grp), c.bone("ring", grp, sy=0.42)
    s_ring = c.slot(b_ring, "fx/ring", 420)
    s_h = c.slot(b_h, tname, 680, make=mk, role="flare")
    s_v = c.slot(b_v, tname, 330, make=mk, role="flare")
    s_core = c.slot(b_core, "fx/glow", 280)
    rng = np.random.default_rng(c.seed + 14)
    sp = []
    spread = float(P["spread"])
    for i in range(ns):
        a = rng.uniform(0, 2 * math.pi)
        bn = c.bone(f"sp{i}", grp)
        sl = c.slot(bn, "fx/mote", rng.uniform(26, 44))
        sp.append((bn, sl, a, rng.uniform(150, 320) * spread, rng.uniform(0.7, 1.3), rng.uniform(0, 0.12)))
    ts = times_dense(0, D, 30)
    c.show([s_ring, s_h, s_v, s_core], 0, D)
    att, dec = 0.10, 1.5

    def amp(u):
        if u < att:
            return ease_out(u / att, 2)
        return float(max(0.0, 1 - ((u - att) / (dec - att))) ** 1.8)
    sx = lambda u: 1.2 * ease_out(u / 0.28, 3) * (1 - 0.45 * smooth(u, 0.28, dec))  # noqa: E731
    c.bone_keys(b_h, "scale", ts, lambda u: (sx(u), 0.25 + 0.75 * amp(u) ** 0.6))
    c.color_keys(s_h, ts, lambda u: hexa("FFFFFF", c.a(amp(u))))
    c.bone_keys(b_v, "scale", ts, lambda u: (0.55 * sx(u), 0.2 + 0.6 * amp(u) ** 0.6))
    c.color_keys(s_v, ts, lambda u: hexa(color, c.a(0.8 * amp(u))))
    c.bone_keys(b_core, "scale", ts, lambda u: (0.5 + 0.9 * ease_out(u / 0.35, 2.5),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa("FFF8C8", c.a(1.1 * amp(u))))
    c.bone_keys(b_ring, "scale", ts, lambda u: (0.18 + 1.35 * ease_out(u / 1.1, 2.6),) * 2)
    c.color_keys(s_ring, ts, lambda u: hexa(ring_color, c.a(0.9 * (1 - smooth(u, 0.05, 1.1)) * smooth(u, 0, 0.04))))
    for bn, sl, a, dist, life, delay in sp:
        tts = times_dense(delay, delay + life, 24)

        def pos(u, a=a, dist=dist, delay=delay, life=life):
            q = (u - delay) / life
            e = ease_out(q, 2.4)
            return (math.cos(a) * dist * e, math.sin(a) * dist * e * 0.7 - 70 * q * q + 20 * q)
        c.bone_keys(bn, "translate", tts, pos)
        c.bone_keys(bn, "scale", tts, lambda u, d=delay, L=life: (1.0 - 0.7 * ((u - d) / L),) * 2)
        c.color_keys(sl, tts, lambda u, d=delay, L=life: hexa("FFF2A8", c.a(0.95 * max(0.0, 1 - (u - d) / L) ** 1.3)))
        c.ab.slot_attachment(sl, [(0.0, None), (c.T(delay), "fx"), (c.T(delay + life), None)])
    return c.result(duration=D * c.k, sparks=ns)


def rim_wisps(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    n = int(P["count"])
    RX, RY = float(P["rx"]), float(P["ry"])
    tint = _hexn(P["color"], "FFF6DC")
    grp = c.bone("rim", c.group, 4, -6)
    rng = np.random.default_rng(c.seed - 4)
    b_ring = c.bone("ring", grp, sy=RY / RX)
    s_ring = c.slot(b_ring, "fx/ring", 2 * RX / 0.78)
    wl = float(P["length"])
    w = []
    for i in range(n):
        ph = i / n * 2 * math.pi + rng.uniform(-0.06, 0.06)
        x, y = math.cos(ph) * RX, math.sin(ph) * RY
        rot = math.degrees(math.atan2(math.sin(ph) / RY, math.cos(ph) / RX))    # outward normal of the ellipse
        bn = c.bone(f"w{i}", grp, x, y, rot)
        length = rng.uniform(105, 165) * wl
        sl = c.slot(bn, "fx/wisp", length, ox=length / 2, height=length * 0.62, role="wisp", anchor="left")
        w.append((bn, sl, rng.uniform(0, 2 * math.pi), rng.uniform(0.8, 1.15), rng.uniform(1.6, 2.6), rng.uniform(0, 0.5)))
    ts = times_dense(0, dur, 14)
    c.show([s_ring] + [x[1] for x in w], 0, dur)
    ringa = lambda u: ease_out(u / 0.8, 2) * (1 - smooth(u, dur - 1.1, dur)) * (0.38 + 0.12 * math.sin(2 * math.pi * u / 2.2))  # noqa: E731
    c.color_keys(s_ring, ts, lambda u: hexa(tint, c.a(ringa(u))))
    for bn, sl, ph, ln, per, dl in w:
        grow = lambda u, dl=dl: ease_out((u - dl) / 0.7, 2.2)  # noqa: E731
        out = lambda u: 1 - smooth(u, dur - 1.1, dur)  # noqa: E731
        osc = lambda u, per=per, ph=ph: 0.5 + 0.5 * math.sin(2 * math.pi * u / per + ph)  # noqa: E731
        c.bone_keys(bn, "scale", ts, lambda u, grow=grow, osc=osc, ln=ln, per=per, ph=ph: (
            ln * (0.25 + 0.75 * grow(u)) * (0.84 + 0.3 * osc(u)), 0.85 + 0.3 * math.sin(2 * math.pi * u / per * 0.7 + ph * 1.3)))
        c.bone_keys(bn, "rotate", ts, lambda u, per=per, ph=ph: 7 * math.sin(2 * math.pi * u / (per * 1.3) + ph))
        c.color_keys(sl, ts, lambda u, grow=grow, out=out, osc=osc: hexa(tint, c.a(grow(u) * out(u) * (0.42 + 0.5 * osc(u)))))
    return c.result(duration=dur * c.k, tufts=n)


def bloom_aura(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    halo = _hexn(P["color"], "FF4FA6")
    core = _hexn(P["color2"], "C890FF")
    beam_c = _hexn(P["beam_color"], "FFA6DC")
    grp = c.bone("aura", c.group, 0, 105)
    b_big, b_beam = c.bone("big", grp, 0, -15), c.bone("beam", grp, 0, 10)
    b_core, b_hot = c.bone("core", grp, 0, 6), c.bone("hot", grp, 0, 10)
    s_big = c.slot(b_big, "fx/glow", 720)
    s_beam = c.slot(b_beam, "fx/beam", 190, oy=170, height=340, role="beam", anchor="bottom") if P["beam"] else None
    s_core = c.slot(b_core, "fx/glow", 270)
    s_hot = c.slot(b_hot, "fx/glow", 90)
    ts = times_dense(0, dur, 16)
    c.show([s for s in (s_big, s_beam, s_core, s_hot) if s], 0, dur)
    inn = lambda u: ease_out(u / 0.9, 2.2)  # noqa: E731
    out = lambda u: 1 - smooth(u, dur - 1.3, dur)  # noqa: E731
    env = lambda u: inn(u) * out(u)  # noqa: E731
    c.color_keys(s_big, ts, lambda u: hexa(halo, c.a(env(u) * (0.55 + 0.25 * _br(u, 0.42)))))
    c.bone_keys(b_big, "scale", ts, lambda u: (0.55 + 0.45 * inn(u) + 0.07 * _br(u, 0.42),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa(core, c.a(env(u) * (0.55 + 0.3 * _br(u, 0.6, 1.1)))))
    c.bone_keys(b_core, "scale", ts, lambda u: (0.7 + 0.35 * inn(u) + 0.1 * _br(u, 0.6, 1.1),) * 2)
    c.color_keys(s_hot, ts, lambda u: hexa("FFE8FF", c.a(env(u) * (0.35 + 0.3 * _br(u, 0.9, 2)))))
    if s_beam:
        c.color_keys(s_beam, ts, lambda u: hexa(beam_c, c.a(env(u) * (0.38 + 0.2 * _br(u, 0.5, 0.4)))))
        c.bone_keys(b_beam, "scale", ts, lambda u: (0.75 + 0.2 * _br(u, 0.5, 0.4), 0.3 + 0.7 * ease_out(u / 1.4, 2) + 0.08 * _br(u, 0.5)))
    return c.result(duration=dur * c.k)


def floor_glow(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    col = _hexn(P["color"], "FFB84A")
    grp = c.bone("floor", c.group, 0, -92)
    b_glow, b_refl, b_pool = c.bone("glow", grp, sy=0.3), c.bone("refl", grp, 0, -20), c.bone("pool", grp, 0, 10, sy=0.2)
    s_glow = c.slot(b_glow, "fx/glow", 640)
    s_refl = c.slot(b_refl, "fx/reflect", 330, oy=-130, height=260, role="reflect", anchor="top") if P["reflection"] else None
    s_pool = c.slot(b_pool, "fx/glow", 420)
    ts = times_dense(0, dur, 10)
    c.show([s for s in (s_glow, s_refl, s_pool) if s], 0, dur)
    inn = lambda u: smooth(u, 0, 1.0)  # noqa: E731
    out = lambda u: 1 - smooth(u, dur - 1.8, dur)  # noqa: E731
    swell = lambda u: 0.45 + 0.55 * smooth(u, dur * 0.12, dur * 0.3) * (1 - 0.6 * smooth(u, dur * 0.75, dur * 0.95))  # noqa: E731
    warm = _mix(_rgb(col), (255, 255, 255), 0.35)
    warm_hex = "%02X%02X%02X" % tuple(int(v) for v in warm)
    refl = "%02X%02X%02X" % tuple(int(v) for v in _mix(_rgb(col), (255, 255, 255), 0.12))
    c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(inn(u) * out(u) * swell(u) * (0.5 + 0.12 * _br(u, 0.35)))))
    c.color_keys(s_pool, ts, lambda u: hexa(warm_hex, c.a(inn(u) * out(u) * swell(u) * (0.45 + 0.15 * _br(u, 0.5, 1)))))
    c.bone_keys(b_glow, "scale", ts, lambda u: (0.9 + 0.12 * swell(u),) * 2)
    if s_refl:
        c.color_keys(s_refl, ts, lambda u: hexa(refl, c.a(inn(u) * out(u) * swell(u) * (0.38 + 0.15 * _br(u, 0.4, 2)))))
        c.bone_keys(b_refl, "scale", ts, lambda u: (0.9 + 0.1 * _br(u, 0.4, 2), 0.8 + 0.25 * swell(u) + 0.06 * _br(u, 0.3)))
    return c.result(duration=dur * c.k)


def fireflies(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    n = int(P["count"])
    palette = [_hexn(x, "FFFFFF") for x in ([P["color"]] if P["color"] else P["palette"])]
    sxr, syr, rise_k, size_k = float(P["spread_x"]), float(P["spread_y"]), float(P["rise"]), float(P["size"])
    grp = c.bone("motes", c.group, 0, 40)
    rng = np.random.default_rng(c.seed + 1)
    motes = []
    for i in range(n):
        bn = c.bone(f"m{i}", grp)
        size = float(rng.choice([rng.uniform(22, 36), rng.uniform(50, 84)], p=[0.7, 0.3])) * size_k
        sl = c.slot(bn, "fx/mote", size, role="mote")
        rho, a = math.sqrt(rng.uniform(0.04, 1)), rng.uniform(0, 2 * math.pi)
        motes.append(dict(b=bn, s=sl, hx=math.cos(a) * rho * sxr, hy=math.sin(a) * rho * syr + 30, T=rng.uniform(4.2, 7.5),
                          ph=rng.uniform(0, 1), rise=rng.uniform(40, 120) * rise_k, swx=rng.uniform(18, 46), swy=rng.uniform(8, 24),
                          tw=rng.uniform(1.4, 3.0), twph=rng.uniform(0, 6.28), col=str(rng.choice(palette)), amp=rng.uniform(0.55, 1.0)))
    c.show([m["s"] for m in motes], 0, dur)
    glob = lambda u: smooth(u, 0, 1.0) * (1 - smooth(u, dur - 1.4, dur))  # noqa: E731
    for m in motes:
        ts = set(times_dense(0, dur, 8))
        k = 0
        while True:                      # a key pair at every respawn: the jump happens at alpha 0
            k += 1
            wrap = (k - m["ph"]) * m["T"]
            if wrap >= dur:
                break
            if wrap > 0:
                ts.update([wrap - 0.002, wrap])
        ts = sorted(t for t in ts if 0 <= t <= dur)

        def state(u, m=m):
            q = (u / m["T"] + m["ph"]) % 1.0
            env = math.sin(math.pi * q) ** 1.25
            x = m["hx"] + m["swx"] * math.sin(2 * math.pi * (q * 1.3 + m["ph"] * 3))
            y = m["hy"] + m["rise"] * q + m["swy"] * math.sin(2 * math.pi * (q * 2.1 + m["ph"] * 5))
            tw = 0.62 + 0.38 * math.sin(2 * math.pi * m["tw"] * u + m["twph"])
            return x, y, min(1.0, 1.25 * env * tw * m["amp"] * glob(u))
        c.bone_keys(m["b"], "translate", ts, lambda u, m=m: state(u, m)[:2])
        c.color_keys(m["s"], ts, lambda u, m=m: hexa(m["col"], c.a(state(u, m)[2])))
    return c.result(duration=dur * c.k, motes=n)


def twinkles(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    n = int(P["count"])
    palette = [_hexn(x, "FFFFFF") for x in ([P["color"]] if P["color"] else P["palette"])]
    size_k = float(P["size"])
    grp = c.bone("tw", c.group, 0, 120)
    rng = np.random.default_rng(c.seed + 7)
    used = 0
    for i in range(n):
        a, rad = rng.uniform(0, 2 * math.pi), rng.uniform(130, 300)
        bn = c.bone(f"s{i}", grp, math.cos(a) * rad * 1.15, math.sin(a) * rad * 0.8)
        col = str(rng.choice(palette))
        sl = c.slot(bn, "fx/spark", rng.uniform(70, 140) * size_k, color=hexa(col, c.a(1.0)), role="spark")
        t_start, life = rng.uniform(0.1, 3.6), rng.uniform(0.55, 0.95)
        rot, rep, gap = rng.uniform(40, 90) * rng.choice([-1, 1]), int(rng.integers(2, 4)), rng.uniform(1.1, 1.9)
        sc, ro, att = [], [], [(0.0, None)]
        for q in range(rep):
            s = t_start + q * gap
            e = s + life
            if e > dur:
                break
            att += [(c.T(s), "fx"), (c.T(e), None)]
            sc += [(c.T(s), 0, 0), (c.T(s + life * 0.42), 1.0, 1.0), (c.T(e), 0, 0)]
            ro += [(c.T(s), 0), (c.T(e), rot)]
        if not sc:
            c.slots.remove(sl)
            continue
        used += 1
        c.ab.bone(bn, "scale", _uniq(sc), "quad_in_out")
        c.ab.bone(bn, "rotate", _uniq(ro), "linear")
        c.ab.slot_attachment(sl, att)
    return c.result(duration=dur * c.k, stars=used)


def _styles() -> dict[str, dict]:
    return {
        "gold": dict(color="FFD21F", column_color="FFB000", column_alpha=0.5, column_width=220, strands=5, wave=0.3,
                     dust=10, dust_width=45, sparks=0, core_width=24, strand_width=1.0, dust_size=1.0, dust_tint="FFFFFF"),
        "ribbon": dict(color="FFD21F", column_color="FFB000", column_alpha=0.34, column_width=240, strands=5, wave=1.7,
                       dust=8, dust_width=60, sparks=9, core_width=16, strand_width=2.3, dust_size=1.0, dust_tint="FFFFFF"),
        "blue": dict(color="3FB4FF", column_color="1F3CFF", column_alpha=0.5, column_width=380, strands=2, wave=0.15,
                     dust=150, dust_width=50, sparks=0, core_width=11, strand_width=1.0, dust_size=0.85, dust_tint="C8F3FF"),
    }


def light_beam(c: Ctx, P: dict) -> dict:
    style = P["style"]
    st = _styles().get(style)
    if st is None:
        raise ValueError(f"unknown style {style!r}; one of {sorted(_styles())}")
    g = lambda k: st[k] if P.get(k) in (None, "") else P[k]  # noqa: E731
    D = float(P["duration"])
    H = float(P["height"])
    color = _hexn(P["color"], st["color"])
    col_c = _hexn(g("column_color"), st["column_color"])
    ns = int(g("strands"))
    wave = float(g("wave"))
    nd = int(P["count"] or g("dust"))
    dw = float(g("dust_width"))
    core_w = float(g("core_width"))
    sw_k = float(g("strand_width"))
    dsz = float(g("dust_size"))
    dust_tint = _hexn(g("dust_tint"), "FFFFFF")
    rows = max(6, int(round(H / 40)) + 1)
    rng = np.random.default_rng(c.seed + 21)
    grp = c.bone("beam", c.group, 0, 0)
    tname = f"fx/strand_{color}"
    mk = lambda: tex_strand(color)  # noqa: E731
    all_slots: list[str] = []
    # ---- column glow behind everything
    b_col = c.bone("column", grp)
    s_col = c.slot(b_col, "fx/column", float(g("column_width")), oy=0, height=H * 1.02, role="column", stretch=True)
    all_slots.append(s_col)
    cap = _hexn(P["cap"], "") if P["cap"] else ""
    caps = []
    if cap:
        for nm_, yy, sy_ in (("cap_top", H / 2, 0.45), ("cap_bot", -H / 2, 0.45)):
            bb = c.bone(nm_, grp, 0, yy, sy=sy_)
            caps.append((c.slot(bb, "fx/glow", float(g("column_width")) * 1.25), bb))
        all_slots += [x[0] for x in caps]
    # ---- strands
    strands = []
    for i in range(ns):
        if i == 0:
            xo, w_, al, A, lam, m = 0.0, core_w, 1.0, 3.0 * wave, 430.0, 1
        else:
            side = -1 if i % 2 else 1
            xo = side * (10 + 9 * ((i + 1) // 2))
            w_ = rng.uniform(5.5, 9.5) * sw_k
            al = rng.uniform(0.42, 0.72)
            A = (6 + 4 * i) * wave
            lam = rng.uniform(240, 460)
            m = int(rng.choice([1, 2]))
        sl, nodes = c.strand(grp, tname, w_ * 2.4, H, rows, x=xo, make=mk, tag=f"st{i}", role="strand")
        strands.append(dict(s=sl, nodes=nodes, a=al, A=A, lam=lam, m=m * (1 if i % 2 else -1), ph=rng.uniform(0, 2 * math.pi),
                            fl=int(rng.integers(2, 6)), flph=rng.uniform(0, 6.28)))
        all_slots.append(sl)
    # white-hot line down the middle of the core
    hot_t = "fx/strand_FFFFFF"
    sl, nodes = c.strand(grp, hot_t, core_w * 0.55 * 2.4, H * 0.96, rows, x=0.0, make=lambda: tex_strand("FFFFFF"), tag="hot")
    strands.append(dict(s=sl, nodes=nodes, a=0.95, A=3.0 * wave, lam=430.0, m=1, ph=strands[0]["ph"], fl=3, flph=0.0))
    all_slots.append(sl)
    # ---- dust motes
    dust = []
    for i in range(nd):
        bn = c.bone(f"d{i}", grp)
        size = float(rng.choice([rng.uniform(7, 13), rng.uniform(16, 28)], p=[0.8, 0.2])) * dsz
        sl = c.slot(bn, "fx/mote", size, role="mote")
        yy = (rng.beta(2.2, 2.2) - 0.5) * H * 0.95
        xx = float(np.clip(rng.normal(0, dw / 2.0), -dw * 1.2, dw * 1.2)) * (0.5 + 0.7 * (1 - abs(yy) / (H / 2)))
        dust.append(dict(b=bn, s=sl, x=xx, y=yy, m=int(rng.choice([1, 1, 2])), ph=rng.uniform(0, 1), vy=rng.uniform(-60, 90),
                         swx=rng.uniform(3, 12), tw=int(rng.integers(3, 9)), twph=rng.uniform(0, 6.28), amp=rng.uniform(0.55, 1.0),
                         col=color if rng.random() < 0.55 else dust_tint))
        all_slots.append(sl)
    # ---- sparks (small four-point glints that pop along the beam)
    spk = []
    for i in range(int(g("sparks"))):
        bn = c.bone(f"sp{i}", grp, rng.uniform(-40, 40), rng.uniform(-H * 0.42, H * 0.42))
        sl = c.slot(bn, "fx/spark", rng.uniform(26, 56), role="spark")
        spk.append(dict(b=bn, s=sl, t=rng.uniform(0, D), life=rng.uniform(0.25, 0.55), rot=rng.uniform(40, 120) * rng.choice([-1, 1])))
        all_slots.append(sl)
    c.show(all_slots, 0, None)

    # ---- animation: everything is a function of t/D with integer cycle counts, so the loop closes exactly
    ts = times_dense(0, D, 12)
    br = lambda u, n, ph=0.0: 0.5 + 0.5 * math.sin(2 * math.pi * n * u / D + ph)  # noqa: E731
    c.color_keys(s_col, ts, lambda u: hexa(col_c, c.a(float(g("column_alpha")) * (0.8 + 0.2 * br(u, 1, 0.5)))))
    for sl, bb in caps:
        c.color_keys(sl, ts, lambda u: hexa(cap, c.a(0.7 * (0.75 + 0.25 * br(u, 2)))))
    for sd in strands:
        for i, nb in enumerate(sd["nodes"]):
            y = -H / 2 + i * H / (rows - 1)
            env = math.sin(math.pi * (y + H / 2) / H) ** 0.8
            c.bone_keys(nb, "translate", ts, lambda u, y=y, env=env, sd=sd: (
                sd["A"] * env * math.sin(2 * math.pi * (y / sd["lam"] - sd["m"] * u / D) + sd["ph"]), 0.0))
        c.color_keys(sd["s"], ts, lambda u, sd=sd: hexa("FFFFFF", c.a(sd["a"] * (0.78 + 0.22 * br(u, sd["fl"], sd["flph"])))))
    for m in dust:
        tsd = set(times_dense(0, D, 8))
        for k in range(1, m["m"] + 1):         # a key pair at each respawn
            wrap = (k - m["ph"]) * D / m["m"]
            if 0 < wrap < D:
                tsd.update([wrap - 0.002, wrap])
        wrap0 = (0 - m["ph"]) % 1.0
        tsd = sorted(t for t in tsd if 0 <= t <= D)

        def state(u, m=m):
            q = (u * m["m"] / D + m["ph"]) % 1.0
            env = math.sin(math.pi * q) ** 1.0
            tw = 0.6 + 0.4 * math.sin(2 * math.pi * m["tw"] * u / D + m["twph"])
            return (m["x"] + m["swx"] * math.sin(2 * math.pi * (q + m["ph"])), m["y"] + m["vy"] * (q - 0.5),
                    min(1.0, 1.2 * env * tw * m["amp"]))
        c.bone_keys(m["b"], "translate", tsd, lambda u, m=m: state(u, m)[:2])
        c.color_keys(m["s"], tsd, lambda u, m=m: hexa(m["col"], c.a(state(u, m)[2])))
    for k in spk:
        a0, a1 = c.T(k["t"]), c.T(k["t"] + k["life"])
        if k["t"] + k["life"] > D:
            k["t"] = D - k["life"]
            a0, a1 = c.T(k["t"]), c.T(D)
        c.ab.bone(k["b"], "scale", _uniq([(a0, 0, 0), (c.T(k["t"] + k["life"] * 0.4), 1, 1), (a1, 0, 0)]), "quad_in_out")
        c.ab.bone(k["b"], "rotate", _uniq([(a0, 0), (a1, k["rot"])]), "linear")
        c.ab.slot_attachment(k["s"], [(0.0, None), (a0, "fx"), (a1, None)])
        c.ab.slot_color(k["s"], [(0.0, hexa(color if int(k["rot"]) % 2 else "FFFFFF", c.a(1.0)))], "linear")
    return c.result(duration=D * c.k, loop=D, strands=ns, dust=nd, sparks=len(spk))


def portal(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    color = _hexn(P["color"], "4A78FF")
    flash_c = _hexn(P["color2"], "B050FF")
    nsp, ncm, arms = int(P["specks"]), int(P["comets"]), int(P["arms"])
    rng = np.random.default_rng(c.seed + 31)
    grp = c.bone("portal", c.group, 0, 0)
    ts = times_dense(0, D, 12)
    all_slots: list[str] = []
    br = lambda u, n, ph=0.0: 0.5 + 0.5 * math.sin(2 * math.pi * n * u / D + ph)  # noqa: E731
    # back glow
    b_glow = c.bone("glow", grp)
    s_glow = c.slot(b_glow, "fx/glow", 800)
    # the disc occludes the scene (normal blend); everything else is light
    b_disc = c.bone("disc", grp)
    s_disc = c.slot(b_disc, f"fx/disc_{color}", 400, color=hexa("FFFFFF", c.a(float(P["disc_alpha"]))), make=lambda: tex_disc(color), blend="normal", role="disc")
    b_sw1, b_sw2 = c.bone("swirl_a", grp), c.bone("swirl_b", grp)
    s_sw1 = c.slot(b_sw1, f"fx/swirl{arms}_{color}", 410, make=lambda: tex_swirl(arms, color), role="swirl_a")
    s_sw2 = c.slot(b_sw2, f"fx/swirl{arms + 2}_{color}", 330, make=lambda: tex_swirl(arms + 2, color, seed=5, twist=3.1), role="swirl_b")
    all_slots += [s_glow, s_disc, s_sw1, s_sw2]
    # specks orbiting inward
    specks = []
    for i in range(nsp):
        piv = c.bone(f"sp{i}", grp)
        mb = c.bone(f"sp{i}m", piv, 100, 0)
        sl = c.slot(mb, "fx/mote", float(rng.uniform(5, 11)), role="mote")
        specks.append(dict(piv=piv, mb=mb, s=sl, r0=float(rng.uniform(70, 185)), a0=float(rng.uniform(0, 360)),
                           rev=int(rng.choice([1, 1, 2])) * int(rng.choice([1, -1])), m=int(rng.choice([1, 1, 2])), ph=float(rng.uniform(0, 1)),
                           tw=int(rng.integers(3, 9)), twph=float(rng.uniform(0, 6.28)), amp=float(rng.uniform(0.5, 0.95)),
                           col=str(rng.choice(["E8DCC8", "FFFFFF", "BFE8FF"]))))
        all_slots.append(sl)
    # comet streaks
    comets = []
    for i in range(ncm):
        bn = c.bone(f"cm{i}", grp)
        sl = c.slot(bn, "fx/comet", 400 - i * 40, make=lambda: tex_comet(), role="comet")
        comets.append(dict(b=bn, s=sl, rev=3 * (1 if i % 2 == 0 else -1), ph=i * 180.0 + float(rng.uniform(0, 40)), n=int(2 + i),
                           pph=float(rng.uniform(0, 6.28))))
        all_slots.append(sl)
    ring_after = c.slots[-1] if c.slots else ""
    # flashes
    fl = [float(x) for x in P["flashes"]]
    b_fl = c.bone("flash", grp)
    s_fl = c.slot(b_fl, "fx/glow", 640)
    s_fc = c.slot(b_fl, "fx/glow", 300)
    all_slots += [s_fl, s_fc]
    c.show(all_slots, 0, None)
    # --- keys
    c.color_keys(s_glow, ts, lambda u: hexa(color, c.a(0.5 + 0.12 * br(u, 1, 0.7))))
    c.bone_keys(b_glow, "scale", ts, lambda u: (0.95 + 0.06 * br(u, 1, 0.7),) * 2)
    # a vortex: inner layers spin FASTER than outer ones (differential rotation), same direction
    spin = float(P["spin"])
    c.bone_keys(b_sw1, "rotate", ts, lambda u: -360.0 * spin * u / D)
    c.bone_keys(b_sw2, "rotate", ts, lambda u: -1080.0 * spin * u / D)
    # the flashes pump the vortex: every flash pushes the swirl out and it falls back
    g_ = lambda u, t0, w: math.exp(-((((u - t0 + D / 2) % D) - D / 2) / w) ** 2)  # noqa: E731
    fa_ = lambda u: min(1.0, sum(g_(u, t0, 0.22) for t0 in [float(x) for x in P["flashes"]]))  # noqa: E731
    c.bone_keys(b_sw1, "scale", ts, lambda u: (1.0 + 0.09 * fa_(u),) * 2)
    c.bone_keys(b_sw2, "scale", ts, lambda u: (1.0 + 0.14 * fa_(u),) * 2)
    c.bone_keys(b_disc, "scale", ts, lambda u: (1.0 + 0.05 * fa_(u),) * 2)
    c.color_keys(s_sw1, ts, lambda u: hexa("FFFFFF", c.a(0.78 + 0.12 * br(u, 2))))
    c.color_keys(s_sw2, ts, lambda u: hexa("FFFFFF", c.a(0.5 + 0.15 * br(u, 3, 1.3))))
    for sp in specks:
        tsd = set(times_dense(0, D, 10))
        for k in range(1, sp["m"] + 1):
            wrap = (k - sp["ph"]) * D / sp["m"]
            if 0 < wrap < D:
                tsd.update([wrap - 0.002, wrap])
        tsd = sorted(t for t in tsd if 0 <= t <= D)
        q = lambda u, sp=sp: (u * sp["m"] / D + sp["ph"]) % 1.0  # noqa: E731
        # Keplerian infall: angular speed grows as r^-1.5 while the speck spirals in, so it whips round near the centre
        kep = lambda qq: ((1 - 0.6 * qq) ** -0.5 - 1) / ((0.4) ** -0.5 - 1)  # noqa: E731  (0 -> 1 over a life)
        c.bone_keys(sp["piv"], "rotate", tsd, lambda u, sp=sp, q=q, kep=kep: sp["a0"] + sp["rev"] * 300.0 * kep(q(u)))
        c.bone_keys(sp["mb"], "translate", tsd, lambda u, sp=sp, q=q: (sp["r0"] * (1 - 0.6 * q(u)) - 100, 0.0))
        c.color_keys(sp["s"], tsd, lambda u, sp=sp, q=q: hexa(sp["col"], c.a(min(1.0, math.sin(math.pi * q(u)) ** 0.8 * (0.6 + 0.4 * math.sin(2 * math.pi * sp["tw"] * u / D + sp["twph"])) * sp["amp"]))))
    for cm in comets:
        c.bone_keys(cm["b"], "rotate", ts, lambda u, cm=cm: cm["ph"] + cm["rev"] * 360.0 * u / D)
        c.color_keys(cm["s"], ts, lambda u, cm=cm: hexa("FFFFFF", c.a(min(1.0, 0.35 + 0.65 * br(u, cm["n"], cm["pph"]) ** 1.5 + 0.4 * fa_(u)))))
    g = lambda u, t0, w: math.exp(-((((u - t0 + D / 2) % D) - D / 2) / w) ** 2)  # noqa: E731
    fa = lambda u: min(1.0, sum(g(u, t0, 0.22) for t0 in fl))  # noqa: E731
    c.color_keys(s_fl, ts_fine := times_dense(0, D, 24), lambda u: hexa(flash_c, c.a(0.95 * fa(u))))
    c.bone_keys(b_fl, "scale", ts_fine, lambda u: (0.75 + 0.5 * fa(u),) * 2)
    c.color_keys(s_fc, ts_fine, lambda u: hexa("F4E6FF", c.a(0.8 * fa(u) ** 1.4)))
    hint = dict(parent=c.group, front_of=ring_after, mode="additive", seq_mode="loop", until=D,
                note="AE ring: ae_template portal_ring -> save -> ae_fx_to_spine with these args; scale ~ 1.8 for a 384px comp")
    return c.result(duration=D * c.k, loop=D, ring_after=ring_after, ring_hint=hint, ae_hint=hint)


def _frame_glow(c: Ctx, parent: str, Wd: float, Hd: float, tag: str = "under", role: str = "under"):
    """Soft glow hugging a Wd x Hd frame, as a 9-slice of the rrglow texture: the glow keeps its thickness and corners at
    any aspect (a stretched square texture floods the ends of a long bar)."""
    inset = 0.26 * 256                      # the outline sits 26% of the half-size in from the texture edge
    tw = 512
    s9, cb = c.slice9(parent, "fx/rrglow", Wd + 2 * inset, Hd + 2 * inset, 150.0, make=lambda: tex_rrglow(), tag=tag, role=role)
    return s9


def electric_frame(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    col = _hexn(P["color"], "9A30FF")
    spark_c = _hexn(P["color2"], "F0D8FF")
    ns = int(P["sparks"])
    Wd, Hd = float(P["width"]), float(P["height"])
    rng = np.random.default_rng(c.seed + 41)
    grp = c.bone("frame", c.group, 0, 0)
    ts = times_dense(0, D, 16)
    br = lambda u, n, ph=0.0: 0.5 + 0.5 * math.sin(2 * math.pi * n * u / D + ph)  # noqa: E731
    s_under = _frame_glow(c, grp, Wd, Hd)
    b_g = c.sk.slot(s_under).bone
    slots = [s_under]
    sparks = []
    for i in range(ns):
        # a random point on the frame outline
        t = rng.uniform(0, 4)
        if t < 1:
            px, py = -Wd / 2 + t * Wd, Hd / 2
        elif t < 2:
            px, py = Wd / 2, Hd / 2 - (t - 1) * Hd
        elif t < 3:
            px, py = Wd / 2 - (t - 2) * Wd, -Hd / 2
        else:
            px, py = -Wd / 2, -Hd / 2 + (t - 3) * Hd
        bn = c.bone(f"sp{i}", grp, px, py)
        sl = c.slot(bn, "fx/spark", float(rng.uniform(34, 78)), color=hexa(spark_c, c.a(1.0)), role="spark")
        sparks.append(dict(b=bn, s=sl, t=float(rng.uniform(0, D)), life=float(rng.uniform(0.14, 0.34)), rep=int(rng.integers(2, 5)),
                           rot=float(rng.uniform(-70, 70))))
        slots.append(sl)
    ring_after = c.slots[0]
    c.show(slots, 0, None)
    c.color_keys(s_under, ts, lambda u: hexa(col, c.a(0.55 + 0.25 * br(u, 3, 0.6) + 0.12 * br(u, 7))))
    c.bone_keys(b_g, "scale", ts, lambda u: (1.0 + 0.012 * br(u, 3, 0.6),) * 2)
    for sp in sparks:
        sc, ro, att = [], [], [(0.0, None)]
        for q in range(sp["rep"]):
            s0 = (sp["t"] + q * D / sp["rep"]) % D
            e0 = s0 + sp["life"]
            if e0 > D:
                continue
            att += [(c.T(s0), "fx"), (c.T(e0), None)]
            sc += [(c.T(s0), 0, 0), (c.T(s0 + sp["life"] * 0.4), 1, 1), (c.T(e0), 0, 0)]
            ro += [(c.T(s0), 0), (c.T(e0), sp["rot"])]
        if not sc:
            continue
        att.sort(key=lambda a: a[0])
        c.ab.bone(sp["b"], "scale", _uniq(sorted(sc, key=lambda a: a[0])), "quad_in_out")
        c.ab.bone(sp["b"], "rotate", _uniq(sorted(ro, key=lambda a: a[0])), "linear")
        c.ab.slot_attachment(sp["s"], att)
    hint = dict(parent=c.group, front_of=ring_after, mode="additive", seq_mode="loop", until=D,
                note="AE line: ae_template electric_frame -> save -> ae_fx_to_spine with these args; scale ~ 0.95 for the default 512 comp and a 400 frame")
    return c.result(duration=D * c.k, loop=D, ring_after=ring_after, ring_hint=hint, ae_hint=hint)


def crosshair(c: Ctx, P: dict) -> dict:
    D = 1.25
    col = _hexn(P["color"], "FFB02E")
    size = float(P["size"])
    lock, hit = float(P["lock"]), float(P["hit"])
    tname = f"fx/reticle_{col}"
    mk = lambda: tex_reticle(col)  # noqa: E731
    grp = c.bone("lock", c.group, 0, 0)
    b_glow, b_ret, b_flash, b_ring = c.bone("glow", grp), c.bone("ret", grp), c.bone("flash", grp), c.bone("ring", grp)
    s_glow = c.slot(b_glow, "fx/glow", size * 1.9, role="glow")
    s_ring = c.slot(b_ring, "fx/ring", size * 1.5, role="ring")
    s_ret = c.slot(b_ret, tname, size, make=mk, role="reticle")
    s_flash = c.slot(b_flash, "fx/glow", size * 0.9, role="flash")
    ts = times_dense(0, D, 30)
    c.show([s_glow, s_ring, s_ret, s_flash], 0, D)
    appear = lambda u: ease_out(u / lock, 3.0)  # noqa: E731
    kick = lambda u: math.exp(-((u - lock) / 0.07) ** 2)  # noqa: E731
    leave = lambda u: smooth(u, hit, hit + 0.3)  # noqa: E731

    def scl(u):
        if u < lock:
            return 2.5 - 1.5 * appear(u)
        hold = 1.0 + 0.035 * math.sin(2 * math.pi * 3.2 * (u - lock)) * (1 - leave(u))
        return (hold + 0.14 * kick(u)) * (1 - 0.2 * smooth(u, hit, hit + 0.12)) * (1 + 0.25 * leave(u))
    rot = lambda u: -120.0 * (1 - appear(u)) + 5.0 * math.sin(2 * math.pi * 1.3 * u) * smooth(u, lock, lock + 0.2) + 40.0 * leave(u)  # noqa: E731
    alpha = lambda u: smooth(u, 0, 0.14) * (1 - leave(u))  # noqa: E731
    c.bone_keys(b_ret, "scale", ts, lambda u: (scl(u),) * 2)
    c.bone_keys(b_ret, "rotate", ts, rot)
    c.color_keys(s_ret, ts, lambda u: hexa("FFFFFF", c.a(alpha(u) * (0.9 + 0.1 * math.sin(2 * math.pi * 6 * u)))))
    c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(alpha(u) * smooth(u, lock * 0.6, lock) * (0.42 + 0.14 * math.sin(2 * math.pi * 3.2 * u)))))
    c.bone_keys(b_glow, "scale", ts, lambda u: (0.8 + 0.2 * smooth(u, 0, lock) + 0.1 * kick(u),) * 2)
    c.color_keys(s_flash, ts, lambda u: hexa("FFF4C8", c.a(0.95 * kick(u))))
    c.bone_keys(b_flash, "scale", ts, lambda u: (0.6 + 0.9 * smooth(u, lock - 0.05, lock + 0.25),) * 2)
    c.bone_keys(b_ring, "scale", ts, lambda u: (0.55 + 1.15 * ease_out((u - lock) / 0.45, 2.4) if u >= lock else 0.0,) * 2)
    c.color_keys(s_ring, ts, lambda u: hexa(col, c.a(0.85 * (1 - smooth(u, lock, lock + 0.45)) if u >= lock else 0.0)))
    c.ab.event(c.T(lock), "fx_crosshair_lock")
    c.ab.event(c.T(hit), "fx_crosshair_hit")
    return c.result(duration=D * c.k, lock_at=c.T(lock), hit_at=c.T(hit))


def hit_burst(c: Ctx, P: dict) -> dict:
    D = 0.95
    col = _hexn(P["color"], "FFB347")
    size = float(P["size"])
    ns = int(P["count"])
    tname = f"fx/starburst_{col}"
    mk = lambda: tex_starburst(col)  # noqa: E731
    grp = c.bone("hit", c.group, 0, 0)
    b_glow, b_star, b_core, b_r1, b_r2 = (c.bone("glow", grp), c.bone("star", grp), c.bone("core", grp),
                                          c.bone("ring1", grp), c.bone("ring2", grp))
    s_glow = c.slot(b_glow, "fx/glow", size * 1.8, role="glow")
    s_r1 = c.slot(b_r1, "fx/ring", size * 1.4, role="ring")
    s_r2 = c.slot(b_r2, "fx/ring", size * 1.4, role="ring")
    s_star = c.slot(b_star, tname, size, make=mk, role="starburst")
    s_core = c.slot(b_core, "fx/glow", size * 0.55, role="core")
    rng = np.random.default_rng(c.seed + 51)
    sp = []
    for i in range(ns):
        a = rng.uniform(0, 2 * math.pi)
        bn = c.bone(f"sp{i}", grp)
        sl = c.slot(bn, "fx/mote", float(rng.uniform(10, 24)), role="mote")
        sp.append((bn, sl, a, float(rng.uniform(0.45, 1.0)) * size * 0.9, float(rng.uniform(0.35, 0.7)), float(rng.uniform(0, 0.06))))
    ts = times_dense(0, D, 30)
    c.show([s_glow, s_r1, s_r2, s_star, s_core], 0, D)
    att = lambda u: ease_out(u / 0.09, 2.0) if u < 0.09 else max(0.0, 1 - (u - 0.09) / 0.62) ** 1.6  # noqa: E731
    c.bone_keys(b_star, "scale", ts, lambda u: (0.15 + 1.0 * ease_out(u / 0.16, 3.0) - 0.15 * smooth(u, 0.2, 0.7),) * 2)
    c.bone_keys(b_star, "rotate", ts, lambda u: 24.0 * u)
    c.color_keys(s_star, ts, lambda u: hexa("FFFFFF", c.a(att(u))))
    c.bone_keys(b_core, "scale", ts, lambda u: (0.4 + 0.9 * ease_out(u / 0.12, 2.5),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa("FFF6D8", c.a(min(1.0, 1.2 * att(u)))))
    c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(0.8 * att(u))))
    c.bone_keys(b_glow, "scale", ts, lambda u: (0.5 + 0.7 * ease_out(u / 0.3, 2.5),) * 2)
    for bn, d0, colr, w in ((b_r1, 0.0, col, 0.62), (b_r2, 0.1, "FFFFFF", 0.5)):
        sl = s_r1 if bn == b_r1 else s_r2
        c.bone_keys(bn, "scale", ts, lambda u, d0=d0: (0.2 + 1.2 * ease_out((u - d0) / 0.5, 2.6) if u >= d0 else 0.0,) * 2)
        c.color_keys(sl, ts, lambda u, d0=d0, colr=colr, w=w: hexa(colr, c.a(0.9 * (1 - smooth(u, d0, d0 + w)) * smooth(u, d0, d0 + 0.03))))
    for bn, sl, a, dist, life, delay in sp:
        tts = times_dense(delay, delay + life, 24)

        def pos(u, a=a, dist=dist, delay=delay, life=life):
            q = (u - delay) / life
            e = ease_out(q, 2.2)
            return (math.cos(a) * dist * e, math.sin(a) * dist * e - 40 * q * q)
        c.bone_keys(bn, "translate", tts, pos)
        c.color_keys(sl, tts, lambda u, d=delay, L=life: hexa("FFD070", c.a(0.95 * max(0.0, 1 - (u - d) / L) ** 1.3)))
        c.ab.slot_attachment(sl, [(0.0, None), (c.T(delay), "fx"), (c.T(delay + life), None)])
    c.ab.event(c.T(0.0), "fx_hit")
    return c.result(duration=D * c.k, sparks=ns)


def cell_glow(c: Ctx, P: dict) -> dict:
    """Glowing cell frames with a twinkling starfield inside; each pops (flash, burst, vanish) at `pop`."""
    dur = float(P["duration"])
    col = _hexn(P["color"], "20E8C8")
    col2 = _hexn(P["color2"], "3CFF8A")
    pop = float(P["pop"])
    stagger = float(P["stagger"])
    cells = P["cells"] or [[0.0, 0.0, float(P["width"]), float(P["height"])]]
    tname = f"fx/frame9_{col}"
    mk = lambda: tex_frame9(col)  # noqa: E731
    fill_hex = _hexn(P["fill_color"], "") if P["fill_color"] else "%02X%02X%02X" % tuple(int(v) for v in _mix(_rgb(col), (0, 0, 0), 0.8))   # default: dark tint, the cell darkens what is behind it
    fill_a = float(P["fill_alpha"])
    rng = np.random.default_rng(c.seed + 61)
    out_cells = []
    for ci, (cx, cy, w, h) in enumerate(cells):
        t0 = ci * stagger
        grp = c.bone(f"cell{ci}", c.group, cx, cy)
        s_fill, _ = c.slice9(grp, "fx/cellfill", w, h, 48.0, tag=f"cell{ci}", blend="normal", role="fill")
        s_frame, corners = c.slice9(grp, tname, w, h, 48.0, make=mk, tag=f"cell{ci}", share=c._last_s9, role="frame")
        area = w * h
        nspk = int(P["specks"]) if P["specks"] else int(np.clip(area / 2000, 8, 70))
        specks = []
        for k in range(nspk):
            bn = c.bone(f"c{ci}_s{k}", grp, float(rng.uniform(-w * 0.42, w * 0.42)), float(rng.uniform(-h * 0.42, h * 0.42)))
            sl = c.slot(bn, "fx/mote", float(rng.uniform(9, 20)), role="mote")
            specks.append(dict(b=bn, s=sl, f=float(rng.uniform(1.2, 3.2)), ph=float(rng.uniform(0, 6.28)), amp=float(rng.uniform(0.5, 1.0)),
                               dx=float(rng.uniform(2, 7)), dy=float(rng.uniform(2, 7)), col=str(rng.choice(["FFFFFF", col, "C8FFF4"]))))
        # pop debris: sparkles + motes flying outward from the middle
        nsp = 8
        deb = []
        for k in range(nsp):
            bn = c.bone(f"c{ci}_d{k}", grp)
            sl = c.slot(bn, "fx/spark", float(rng.uniform(26, 52)), role="spark")
            deb.append((bn, sl, float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(0.45, 0.95)) * max(w, h), float(rng.uniform(0, 0.08))))
        b_ring, b_glow = c.bone(f"c{ci}_ring", grp), c.bone(f"c{ci}_pg", grp)
        s_ring = c.slot(b_ring, "fx/ring", max(w, h) * 0.9, role="ring")
        s_pg = c.slot(b_glow, "fx/glow", max(w, h) * 1.1, role="glow")
        slots_all = [s_fill, s_frame] + [x["s"] for x in specks] + [s_ring, s_pg] + [x[1] for x in deb]
        end = t0 + pop + 0.8 if pop > 0 else dur
        c.show(slots_all, t0, end)
        ts = times_dense(t0, min(end, t0 + dur + (0.8 if pop > 0 else 0)), 20)
        appear = lambda u: smooth(u, t0, t0 + 0.35)  # noqa: E731
        pu = t0 + pop
        popk = lambda u: smooth(u, pu, pu + 0.25) if pop > 0 else 0.0  # noqa: E731
        gone = lambda u: smooth(u, pu + 0.06, pu + 0.4) if pop > 0 else 0.0  # noqa: E731
        flashk = lambda u: math.exp(-((u - pu - 0.05) / 0.08) ** 2) if pop > 0 else 0.0  # noqa: E731
        pulse = lambda u: 0.85 + 0.15 * math.sin(2 * math.pi * 0.9 * u + ci)  # noqa: E731
        c.color_keys(s_frame, ts, lambda u: hexa("FFFFFF" if flashk(u) > 0.5 else col, c.a(appear(u) * (1 - gone(u)) * pulse(u))))
        c.color_keys(s_fill, ts, lambda u: hexa(fill_hex, c.a(fill_a * appear(u) * (1 - gone(u)) * (0.9 + 0.1 * pulse(u)))))
        c.bone_keys(grp, "scale", ts, lambda u: ((0.92 + 0.08 * appear(u)) * (1 + 0.28 * popk(u)),) * 2)
        for sp in specks:
            c.bone_keys(sp["b"], "translate", ts, lambda u, sp=sp: (sp["dx"] * math.sin(0.6 * u + sp["ph"]), sp["dy"] * math.cos(0.5 * u + sp["ph"] * 1.7)))
            c.color_keys(sp["s"], ts, lambda u, sp=sp: hexa(sp["col"], c.a(appear(u) * (1 - gone(u)) * sp["amp"] * (0.55 + 0.45 * math.sin(2 * math.pi * sp["f"] * u + sp["ph"])))))
        if pop > 0:
            c.bone_keys(b_ring, "scale", ts, lambda u: (0.3 + 1.3 * ease_out((u - pu) / 0.5, 2.4) if u >= pu else 0.0,) * 2)
            c.color_keys(s_ring, ts, lambda u: hexa(col2, c.a(0.9 * (1 - smooth(u, pu, pu + 0.5)) * smooth(u, pu, pu + 0.03))))
            c.bone_keys(b_glow, "scale", ts, lambda u: (0.4 + 0.8 * ease_out((u - pu) / 0.4, 2.0) if u >= pu else 0.0,) * 2)
            c.color_keys(s_pg, ts, lambda u: hexa(col2, c.a(0.85 * math.exp(-((u - pu - 0.1) / 0.18) ** 2))))
            for bn, sl, a, dist, delay in deb:
                tts = times_dense(pu + delay, pu + delay + 0.6, 24)
                c.bone_keys(bn, "translate", tts, lambda u, a=a, dist=dist, d=delay: (
                    math.cos(a) * dist * ease_out((u - pu - d) / 0.6, 2.2), math.sin(a) * dist * ease_out((u - pu - d) / 0.6, 2.2)))
                c.bone_keys(bn, "scale", tts, lambda u, d=delay: (max(0.0, 1 - (u - pu - d) / 0.6),) * 2)
                c.color_keys(sl, tts, lambda u, d=delay: hexa("D8FFE8", c.a(0.95 * max(0.0, 1 - (u - pu - d) / 0.6))))
                c.ab.slot_attachment(sl, [(0.0, None), (c.T(pu + delay), "fx"), (c.T(pu + delay + 0.6), None)])
            c.ab.event(c.T(pu), "fx_cell_pop")
        else:
            c.ab.slot_attachment(s_ring, [(0.0, None)])
            c.ab.slot_attachment(s_pg, [(0.0, None)])
            for bn, sl, *_ in deb:
                c.ab.slot_attachment(sl, [(0.0, None)])
        out_cells.append(dict(frame=s_frame, corners=corners, pop_at=c.T(pu) if pop > 0 else None))
    return c.result(duration=dur * c.k, cells=len(cells), corner_bones=[v for o in out_cells for v in o["corners"].values()],
                    pops=[o["pop_at"] for o in out_cells])


def puff(c: Ctx, P: dict) -> dict:
    """A cartoon puff of smoke: cloud lobes burst outward, swell, then thin out; a flash and a soft ring at the start."""
    D = 1.15
    col = _hexn(P["color"], "FFF1DC")
    flash_c = _hexn(P["color2"], "FFD27A")
    n = int(P["count"])
    R_ = float(P["radius"])
    size = float(P["size"])
    blend = str(P["blend"])
    rise = float(P["rise"])
    if not P["lobes"]:
        n = 0                                     # realistic puff: the smoke body comes from After Effects (smoke_puff)
    rng = np.random.default_rng(c.seed + 71)
    grp = c.bone("puff", c.group, 0, 0)
    b_fl, b_ring = c.bone("flash", grp), c.bone("ring", grp)
    s_fl = c.slot(b_fl, "fx/glow", size * 3.2, role="glow")
    s_ring = c.slot(b_ring, "fx/ring", size * 3.0, role="ring")
    blobs = []
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.35, 0.35)
        bn = c.bone(f"b{i}", grp)
        sl = c.slot(bn, "fx/cloud", size * rng.uniform(0.8, 1.25), blend=blend, role="cloud")
        blobs.append(dict(b=bn, s=sl, a=a, d=R_ * rng.uniform(0.55, 1.0), g=rng.uniform(1.0, 1.55), rot=rng.uniform(-35, 35),
                          delay=rng.uniform(0, 0.08), tint=("FFFFFF" if rng.random() < 0.5 else col)))
    # a bigger core puff in the middle
    bc = c.bone("core", grp)
    sc = c.slot(bc, "fx/cloud", size * 1.5, blend=blend, role="cloud") if P["lobes"] else None
    ring_after = s_ring
    ts = times_dense(0, D, 30)
    c.show([x for x in (s_fl, s_ring, sc) if x] + [x["s"] for x in blobs], 0, D)
    fl = lambda u: math.exp(-((u - 0.05) / 0.10) ** 2)  # noqa: E731
    c.color_keys(s_fl, ts, lambda u: hexa(flash_c, c.a(0.95 * fl(u))))
    c.bone_keys(b_fl, "scale", ts, lambda u: (0.5 + 1.0 * ease_out(u / 0.25, 2.5),) * 2)
    c.bone_keys(b_ring, "scale", ts, lambda u: (0.2 + 1.2 * ease_out(u / 0.6, 2.5),) * 2)
    c.color_keys(s_ring, ts, lambda u: hexa(col, c.a(0.55 * (1 - smooth(u, 0, 0.6)) * smooth(u, 0, 0.03))))
    env = lambda u, dl: (smooth(u, dl, dl + 0.10)) * (1 - smooth(u, dl + 0.45, dl + 1.0))  # noqa: E731
    for bl in blobs:
        dl = bl["delay"]
        c.bone_keys(bl["b"], "translate", ts, lambda u, bl=bl: (math.cos(bl["a"]) * bl["d"] * ease_out((u - bl["delay"]) / 0.7, 2.4) if u >= bl["delay"] else 0.0,
                                                                  (math.sin(bl["a"]) * bl["d"] * 0.8 * ease_out((u - bl["delay"]) / 0.7, 2.4) + rise * max(0.0, u - bl["delay"])) if u >= bl["delay"] else 0.0))
        c.bone_keys(bl["b"], "scale", ts, lambda u, bl=bl: ((0.25 + (bl["g"] - 0.25) * ease_out((u - bl["delay"]) / 0.55, 2.2)) if u >= bl["delay"] else 0.0,) * 2)
        c.bone_keys(bl["b"], "rotate", ts, lambda u, bl=bl: bl["rot"] * ease_out((u - bl["delay"]) / 0.9, 1.6) if u >= bl["delay"] else 0.0)
        c.color_keys(bl["s"], ts, lambda u, bl=bl: hexa(bl["tint"], c.a(0.95 * env(u, bl["delay"]))))
    if sc:
        c.bone_keys(bc, "scale", ts, lambda u: (0.3 + 1.1 * ease_out(u / 0.5, 2.2),) * 2)
        c.color_keys(sc, ts, lambda u: hexa("FFFFFF", c.a(0.95 * env(u, 0.0))))
    hint = dict(parent=c.group, front_of=ring_after, mode="alpha", seq_mode="once", start=c.T(0.0),
                note="realistic smoke: ae_template smoke_puff -> save -> ae_fx_to_spine with these args (scale ~ size*2.6/comp size)")
    return c.result(duration=D * c.k, blobs=n, ae_hint=hint)


def smoke_glow(c: Ctx, P: dict) -> dict:
    """Rising smoke haze inside a box with a glow at its base (flame light). Loops exactly every `duration`."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FF9F8A")
    glow_c = _hexn(P["color2"], "FFC24A")
    W, H = float(P["width"]), float(P["height"])
    n = int(P["count"])
    blend = str(P["blend"])
    alpha = float(P["alpha"])
    rng = np.random.default_rng(c.seed + 81)
    grp = c.bone("smoke", c.group, 0, 0)
    b_g = c.bone("base", grp, 0, -H / 2, sy=0.45)
    s_g = c.slot(b_g, "fx/glow", max(W * 2.2, 160), role="glow")
    blobs = []
    for i in range(n):
        bn = c.bone(f"s{i}", grp)
        sl = c.slot(bn, "fx/smoke", float(rng.uniform(1.4, 2.1)) * max(W, 90), blend=blend, role="smoke")
        blobs.append(dict(b=bn, s=sl, x=float(-W / 2 + (i + rng.uniform(0.2, 0.8)) / n * W), m=int(rng.choice([1, 1, 2])), ph=float(rng.uniform(0, 1)),
                          sw=float(rng.uniform(6, 22)), rot=float(rng.uniform(-40, 40)), g=float(rng.uniform(1.0, 1.6)), amp=float(rng.uniform(0.6, 1.0))))
    c.show([s_g] + [x["s"] for x in blobs], 0, None)
    ts = times_dense(0, D, 12)
    br = lambda u, k, ph=0.0: 0.5 + 0.5 * math.sin(2 * math.pi * k * u / D + ph)  # noqa: E731
    c.color_keys(s_g, ts, lambda u: hexa(glow_c, c.a(0.45 + 0.2 * br(u, 3, 0.4) + 0.1 * br(u, 7))))
    c.bone_keys(b_g, "scale", ts, lambda u: (0.95 + 0.1 * br(u, 3, 0.4), 0.95 + 0.1 * br(u, 3, 0.4)))
    for bl in blobs:
        tsd = set(times_dense(0, D, 8))
        for k in range(1, bl["m"] + 1):
            wrap = (k - bl["ph"]) * D / bl["m"]
            if 0 < wrap < D:
                tsd.update([wrap - 0.002, wrap])
        tsd = sorted(t for t in tsd if 0 <= t <= D)
        q = lambda u, bl=bl: (u * bl["m"] / D + bl["ph"]) % 1.0  # noqa: E731
        c.bone_keys(bl["b"], "translate", tsd, lambda u, bl=bl, q=q: (bl["x"] + bl["sw"] * math.sin(2 * math.pi * (q(u) + bl["ph"])),
                                                                       -H / 2 + 0.1 * H + q(u) * H * 0.85))
        c.bone_keys(bl["b"], "scale", tsd, lambda u, bl=bl, q=q: ((0.55 + (bl["g"] - 0.55) * q(u)),) * 2)
        c.bone_keys(bl["b"], "rotate", tsd, lambda u, bl=bl, q=q: bl["rot"] * q(u))
        c.color_keys(bl["s"], tsd, lambda u, bl=bl, q=q: hexa(col, c.a(alpha * bl["amp"] * math.sin(math.pi * q(u)) ** 1.1)))
    return c.result(duration=D * c.k, loop=D, blobs=n)


def _trail_keys(c: Ctx, nodes: list[str], rows: int, height: float, ts, pos_at):
    """Key a strand mesh so it lies along a moving curve: row i (bottom = tail end ... top = head) follows
    pos_at(u, lag_fraction) -> (x, y, tangent_deg). Rows rotate so the strip's width is always across the curve;
    angles are unwrapped, so a tangent crossing +-180 never spins a row the long way round."""
    for i, nb in enumerate(nodes):
        lagf = (rows - 1 - i) / (rows - 1)
        y0 = -height / 2 + i * height / (rows - 1)
        vals = [pos_at(u, lagf) for u in ts]
        c.ab.bone(nb, "translate", _uniq([(c.T(u), v[0], v[1] - y0) for u, v in zip(ts, vals)]), "linear")
        ang = np.degrees(np.unwrap(np.radians([v[2] + 90.0 for v in vals])))
        c.ab.bone(nb, "rotate", _uniq([(c.T(u), float(a)) for u, a in zip(ts, ang)]), "linear")


def meteor_trace(c: Ctx, P: dict) -> dict:
    """A bright head with a comet tail racing around a rounded-rectangle frame, shedding sparks. Loops exactly."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FFD25A")
    W, H, R_ = float(P["width"]), float(P["height"]), float(P["corner"])
    laps, tail = int(P["laps"]), float(P["tail"])
    rows = 24
    grp = c.bone("trace", c.group, 0, 0)
    s_under = _frame_glow(c, grp, W, H) if P["underglow"] else None
    s_tail, nodes = c.strand(grp, f"fx/trail_{col}", float(P["thickness"]) * 2.4, 100.0, rows, make=lambda: tex_trail(col), tag="tail", role="tail")
    b_head = c.bone("head", grp)
    s_hg = c.slot(b_head, "fx/glow", float(P["size"]) * 2.2, role="glow")
    s_hs = c.slot(b_head, "fx/spark", float(P["size"]) * 1.4, role="spark")
    rng = np.random.default_rng(c.seed + 91)
    nsp = int(P["sparks"])
    sparks = []
    for i in range(nsp):
        bn = c.bone(f"sp{i}", grp)
        sl = c.slot(bn, "fx/mote", float(rng.uniform(8, 18)), role="mote")
        sparks.append(dict(b=bn, s=sl, t=i * D / max(nsp, 1), life=float(rng.uniform(0.35, 0.6)), out=float(rng.uniform(8, 26))))
    slots = [x for x in (s_under, s_tail, s_hg, s_hs) if x]
    c.show(slots, 0, None)
    ts = times_dense(0, D, 30)
    per = lambda u: laps * u / D  # noqa: E731

    def pos_at(u, lagf):
        x, y, a = rr_point(per(u) - lagf * tail, W, H, R_)
        return x, y, a
    _trail_keys(c, nodes, rows, 100.0, ts, pos_at)
    c.color_keys(s_tail, ts, lambda u: hexa("FFFFFF", c.a(0.95)))
    c.bone_keys(b_head, "translate", ts, lambda u: pos_at(u, 0.0)[:2])
    c.bone_keys(b_head, "rotate", ts, lambda u: 360.0 * 2 * u / D)
    c.color_keys(s_hg, ts, lambda u: hexa(col, c.a(0.75 + 0.2 * math.sin(2 * math.pi * 6 * u / D))))
    c.color_keys(s_hs, ts, lambda u: hexa("FFFFFF", c.a(0.9)))
    if s_under:
        c.color_keys(s_under, ts, lambda u: hexa(col, c.a(0.22 + 0.06 * math.sin(2 * math.pi * 2 * u / D))))
    for sp in sparks:
        t0, life = sp["t"], sp["life"]
        x0, y0, a0 = rr_point(per(t0), W, H, R_)
        nx, ny = math.cos(math.radians(a0 + 90)), math.sin(math.radians(a0 + 90))      # outward-ish normal (CW path: left of travel is outside)
        tts = times_dense(t0, min(D, t0 + life), 20)
        c.bone_keys(sp["b"], "translate", tts, lambda u, x0=x0, y0=y0, nx=nx, ny=ny, t0=t0, sp=sp, life=life: (
            x0 + nx * sp["out"] * (u - t0) / life, y0 + ny * sp["out"] * (u - t0) / life - 10 * ((u - t0) / life) ** 2))
        c.color_keys(sp["s"], tts, lambda u, t0=t0, life=life: hexa(col, c.a(0.95 * max(0.0, 1 - (u - t0) / life))))
        c.ab.slot_attachment(sp["s"], [(0.0, None), (c.T(t0), "fx"), (c.T(min(D, t0 + life)), None)])
    return c.result(duration=D * c.k, loop=D, laps=laps)


def projectile(c: Ctx, P: dict) -> dict:
    """A glowing shot flies from the anchor to target (tx, ty) on an arc, comet tail behind it, then an impact flash."""
    T = float(P["flight"])
    col = _hexn(P["color"], "FFD25A")
    tx, ty, arc = float(P["tx"]), float(P["ty"]), float(P["arc"])
    tail = float(P["tail"])
    size = float(P["size"])
    rows = 20
    p0, p2 = (0.0, 0.0), (tx, ty)
    mx, my = tx / 2, ty / 2
    ln = math.hypot(tx, ty) or 1.0
    nx, ny = -ty / ln, tx / ln                          # left normal of the chord
    if ny < 0:
        nx, ny = -nx, -ny                                # arc bulges upward
    p1 = (mx + nx * arc, my + ny * arc)
    grp = c.bone("shot", c.group, 0, 0)
    s_tail, nodes = c.strand(grp, f"fx/trail_{col}", size * 0.7 * 2.4, 100.0, rows, make=lambda: tex_trail(col), tag="tail", role="tail")
    b_head = c.bone("head", grp)
    s_hg = c.slot(b_head, "fx/glow", size * 2.0, role="glow")
    s_hs = c.slot(b_head, "fx/spark", size * 1.3, role="spark")
    b_imp = c.bone("impact", grp, tx, ty)
    s_ig = c.slot(b_imp, "fx/glow", size * 4.0, role="impact_glow")
    s_ir = c.slot(b_imp, "fx/ring", size * 3.2, role="impact_ring")
    s_is = c.slot(b_imp, f"fx/starburst_{col}", size * 3.0, make=lambda: tex_starburst(col), role="impact_star")
    rng = np.random.default_rng(c.seed + 101)
    nsp = int(P["sparks"])
    sparks = []
    for i in range(nsp):
        bn = c.bone(f"sp{i}", grp)
        sl = c.slot(bn, "fx/mote", float(rng.uniform(7, 15)), role="mote")
        sparks.append(dict(b=bn, s=sl, t=T * (i + 0.5) / nsp, life=float(rng.uniform(0.3, 0.55)), dx=float(rng.uniform(-14, 14)), dy=float(rng.uniform(-22, 4))))
    D = T + 0.75
    ease = lambda q: q * q * (3 - 2 * q) * 0.35 + q * 0.65  # noqa: E731  (a touch of acceleration)

    def pos_at(u, lagf):
        q = max(0.0, min(1.0, (u - lagf * tail * T) / T))
        return _bez(p0, p1, p2, ease(q))
    tsf = times_dense(0, T + tail * T, 40)
    c.ab.slot_attachment(s_tail, [(0.0, "fx") if c.T(0) == 0 else (0.0, None), (c.T(0), "fx"), (c.T(T + tail * T), None)])
    c.ab.slot_attachment(s_hg, [(0.0, "fx") if c.T(0) == 0 else (0.0, None), (c.T(0), "fx"), (c.T(T), None)])
    c.ab.slot_attachment(s_hs, [(0.0, "fx") if c.T(0) == 0 else (0.0, None), (c.T(0), "fx"), (c.T(T), None)])
    _trail_keys(c, nodes, rows, 100.0, tsf, pos_at)
    c.color_keys(s_tail, tsf, lambda u: hexa("FFFFFF", c.a(smooth(u, 0, 0.06) * (1 - smooth(u, T, T + tail * T)))))
    c.bone_keys(b_head, "translate", tsf, lambda u: pos_at(u, 0.0)[:2])
    c.bone_keys(b_head, "rotate", tsf, lambda u: 540.0 * u)
    c.color_keys(s_hg, tsf, lambda u: hexa(col, c.a(0.85)))
    # impact
    tsi = times_dense(T, D, 30)
    for sl in (s_ig, s_ir, s_is):
        c.ab.slot_attachment(sl, [(0.0, None), (c.T(T), "fx"), (c.T(D), None)])
    fl = lambda u: ease_out((u - T) / 0.08, 2) if u < T + 0.08 else max(0.0, 1 - (u - T - 0.08) / 0.55) ** 1.5  # noqa: E731
    c.color_keys(s_ig, tsi, lambda u: hexa(col, c.a(0.9 * fl(u))))
    c.bone_keys(b_imp, "scale", tsi, lambda u: (0.4 + 0.8 * ease_out((u - T) / 0.25, 2.5),) * 2)
    c.color_keys(s_is, tsi, lambda u: hexa("FFFFFF", c.a(fl(u))))
    c.color_keys(s_ir, tsi, lambda u: hexa(col, c.a(0.8 * (1 - smooth(u, T, T + 0.5)))))
    for sp in sparks:
        t0, life = sp["t"], sp["life"]
        x0, y0, _ = pos_at(t0, 0.0)
        tts = times_dense(t0, t0 + life, 20)
        c.bone_keys(sp["b"], "translate", tts, lambda u, x0=x0, y0=y0, t0=t0, sp=sp, life=life: (
            x0 + sp["dx"] * (u - t0) / life, y0 + sp["dy"] * (u - t0) / life))
        c.color_keys(sp["s"], tts, lambda u, t0=t0, life=life: hexa(col, c.a(0.95 * max(0.0, 1 - (u - t0) / life))))
        c.ab.slot_attachment(sp["s"], [(0.0, None), (c.T(t0), "fx"), (c.T(t0 + life), None)])
    c.ab.event(c.T(0.0), "fx_projectile_launch")
    c.ab.event(c.T(T), "fx_projectile_hit")
    return c.result(duration=D * c.k, hit_at=c.T(T), target=[tx, ty])


def explosion(c: Ctx, P: dict) -> dict:
    """An explosion with exaggerated blast physics: an instant flash that decays like 1/t, a shockwave whose radius grows as
    t^0.4 (Sedov-Taylor) and thins as it spreads, a fireball of blobs that balloon with the same law while cooling from
    white through orange to dark smoke that rises on its own heat, debris on parabolas with air drag (velocity decays,
    stretched along their speed), embers that linger, and a dust ring kicked up along the ground."""
    D = 1.9
    col = _hexn(P["color"], "FF9A2A")
    size = float(P["size"])
    nd = int(P["count"])
    sq = float(P["squash"])
    rng = np.random.default_rng(c.seed + 161)
    grp = c.bone("boom", c.group, 0, 0)
    b_fl = c.bone("flash", grp)
    s_fl = c.slot(b_fl, "fx/glow", size * 2.8, role="flash")
    b_dust = c.bone("dust", grp, 0, -size * 0.28, sy=0.22)
    s_dust = c.slot(b_dust, "fx/ring", size * 2.6, blend="normal", role="dust")
    b_r1, b_r2 = c.bone("shock", grp, sy=sq), c.bone("shock2", grp, sy=sq)
    s_r1 = c.slot(b_r1, "fx/ring", size * 3.4, role="ring")
    s_r2 = c.slot(b_r2, "fx/ring", size * 3.4, role="ring")
    blobs = []
    for i in range(7):
        a = 2 * math.pi * i / 7 + float(rng.uniform(-0.4, 0.4))
        bn = c.bone(f"fb{i}", grp)
        gk = float(rng.uniform(0.8, 1.3)) if i else 1.6
        s_fire = c.slot(bn, "fx/smoke", size * 1.35 * gk, role="fire")
        s_smoke = c.slot(bn, "fx/smoke", size * 1.35 * gk, blend="normal", role="smoke")
        blobs.append(dict(b=bn, f=s_fire, s=s_smoke, a=a, d=(0.0 if not i else size * float(rng.uniform(0.25, 0.5))),
                          rot=float(rng.uniform(-60, 60)), dl=float(rng.uniform(0, 0.05)) if i else 0.0))
    debris = []
    for i in range(nd):
        a = math.radians(90 + float(rng.uniform(-80, 80)))
        v0 = size * float(rng.uniform(5.0, 9.0))
        bn = c.bone(f"db{i}", grp)
        sl = c.slot(bn, "fx/mote", float(rng.uniform(16, 30)) * size / 200, role="mote")
        debris.append(dict(b=bn, s=sl, vx=math.cos(a) * v0, vy=math.sin(a) * v0, k=float(rng.uniform(1.4, 2.4)),
                           life=float(rng.uniform(0.7, 1.3)), t0=float(rng.uniform(0, 0.04))))
    embers = []
    for i in range(int(P["embers"])):
        bn = c.bone(f"em{i}", grp, float(rng.uniform(-1, 1)) * size * 0.9, float(rng.uniform(-0.2, 1.0)) * size * 0.8)
        sl = c.slot(bn, "fx/spark", float(rng.uniform(16, 34)) * size / 200, color=hexa("FFD08A", 1.0), role="spark")
        embers.append(dict(b=bn, s=sl, t=float(rng.uniform(0.25, D - 0.5)), life=float(rng.uniform(0.3, 0.5)), rot=float(rng.uniform(-90, 90))))
    c.show([s_fl, s_dust, s_r1, s_r2] + [x for b_ in blobs for x in (b_["f"], b_["s"])], 0, D)
    ts = times_dense(0, D, 30)
    G = size * 7.0                                                   # gravity in units/s^2, scaled with the blast
    sedov = lambda u: (max(0.0, u) / D) ** 0.4  # noqa: E731
    fl = lambda u: smooth(u, 0, 0.025) / (1 + 45 * max(0.0, u - 0.025))  # noqa: E731
    c.color_keys(s_fl, ts, lambda u: hexa("FFF6DC", c.a(min(1.0, 1.2 * fl(u)))))
    c.bone_keys(b_fl, "scale", ts, lambda u: (0.6 + 1.1 * ease_out(u / 0.12, 2.5),) * 2)
    for bn, sl, d0, k_ in ((b_r1, s_r1, 0.0, 1.0), (b_r2, s_r2, 0.07, 0.72)):
        c.bone_keys(bn, "scale", ts, lambda u, d0=d0, k_=k_: (0.08 + 1.35 * k_ * sedov(u - d0),) * 2 if u >= d0 else (0.0, 0.0))
        c.color_keys(sl, ts, lambda u, d0=d0, k_=k_: hexa("FFE9B0" if k_ == 1.0 else col, c.a(0.95 * k_ * (1 - sedov(u - d0)) ** 1.6 * smooth(u, d0, d0 + 0.02))))
    c.bone_keys(b_dust, "scale", ts, lambda u: (0.15 + 1.1 * sedov(u),) * 2)
    c.color_keys(s_dust, ts, lambda u: hexa("7A6450", c.a(0.3 * smooth(u, 0.02, 0.1) * (1 - smooth(u, 0.3, 1.2)))))
    # the fireball: balloon as t^0.4, cool white -> yellow -> orange -> dark, rise on its heat
    stops = [(0.0, "FFF8E0", 1.0), (0.08, "FFE070", 1.0), (0.22, "FF9A2A", 0.9), (0.45, "FF4A10", 0.55), (0.75, "A02808", 0.2), (1.1, "600000", 0.0)]

    def fire_col(u):
        for (t0, c0, a0), (t1, c1, a1) in zip(stops, stops[1:]):
            if u <= t1:
                f = max(0.0, (u - t0) / (t1 - t0))
                rgb = _mix(_rgb(c0), _rgb(c1), f)
                return "%02X%02X%02X" % tuple(int(v) for v in rgb), a0 + (a1 - a0) * f
        return "600000", 0.0
    for b_ in blobs:
        dl = b_["dl"]
        grow = lambda u, b_=b_, dl=dl: 0.12 + 1.15 * sedov(u - dl) * (1.0 if b_["d"] else 1.1)  # noqa: E731
        c.bone_keys(b_["b"], "scale", ts, lambda u, grow=grow: (grow(u),) * 2)
        c.bone_keys(b_["b"], "translate", ts, lambda u, b_=b_, dl=dl: (math.cos(b_["a"]) * b_["d"] * ease_out((u - dl) / 0.45, 2.6),
                                                                        math.sin(b_["a"]) * b_["d"] * 0.7 * ease_out((u - dl) / 0.45, 2.6) + size * 0.9 * max(0.0, u - dl) ** 2 * 0.55))
        c.bone_keys(b_["b"], "rotate", ts, lambda u, b_=b_: b_["rot"] * u)
        c.color_keys(b_["f"], ts, lambda u, dl=dl: (lambda cc: hexa(cc[0], c.a(cc[1] * smooth(u, dl, dl + 0.03))))(fire_col(u - dl)))
        c.color_keys(b_["s"], ts, lambda u, dl=dl: hexa("6E6260", c.a(0.7 * smooth(u - dl, 0.12, 0.5) * (1 - smooth(u - dl, 0.9, D)))))
    # debris: parabolas with air drag (v decays as e^-kt), stretched along the velocity
    for d in debris:
        t0, k_, L = d["t0"], d["k"], d["life"]
        tdd = times_dense(t0, min(D, t0 + L), 24)

        def st(u, d=d, t0=t0, k_=k_):
            t = max(0.0, u - t0)
            e = (1 - math.exp(-k_ * t)) / k_
            x, y = d["vx"] * e, d["vy"] * e - 0.5 * G * t * t
            vx, vy = d["vx"] * math.exp(-k_ * t), d["vy"] * math.exp(-k_ * t) - G * t
            sp = math.hypot(vx, vy)
            return x, y, math.degrees(math.atan2(vy, vx)) - 90.0, 1 + 1.4 * min(1.0, sp / (size * 7.0))
        vals = [st(u) for u in tdd]
        ang = np.degrees(np.unwrap(np.radians([v[2] for v in vals])))
        c.ab.bone(d["b"], "translate", _uniq([(c.T(u), v[0], v[1]) for u, v in zip(tdd, vals)]), "linear")
        c.ab.bone(d["b"], "rotate", _uniq([(c.T(u), float(a_)) for u, a_ in zip(tdd, ang)]), "linear")
        c.ab.bone(d["b"], "scale", _uniq([(c.T(u), 1 / math.sqrt(v[3]), v[3]) for u, v in zip(tdd, vals)]), "linear")
        c.color_keys(d["s"], tdd, lambda u, t0=t0, L=L: hexa("FFD070" if (u - t0) < L * 0.4 else "FF6A20", c.a(0.95 * max(0.0, 1 - (u - t0) / L) ** 1.2)))
        c.ab.slot_attachment(d["s"], [(0.0, None), (c.T(t0), "fx"), (c.T(min(D, t0 + L)), None)])
    for e in embers:
        c.ab.slot_attachment(e["s"], [(0.0, None), (c.T(e["t"]), "fx"), (c.T(e["t"] + e["life"]), None)])
        c.ab.bone(e["b"], "scale", _uniq([(c.T(e["t"]), 0, 0), (c.T(e["t"] + e["life"] * 0.4), 1, 1), (c.T(e["t"] + e["life"]), 0, 0)]), "quad_in_out")
        c.ab.bone(e["b"], "rotate", _uniq([(c.T(e["t"]), 0), (c.T(e["t"] + e["life"]), e["rot"])]), "linear")
    c.ab.event(c.T(0.0), "fx_explosion")
    c.ab.event(c.T(0.02), "fx_explosion_shock")
    hint = dict(parent=c.group, front_of=s_r2, mode="alpha", seq_mode="once", start=c.T(0.0),
                note="volumetric fireball: ae_template smoke_puff params={light: FFF3A0, mid: FF7A1C, shadow: 3A2018, rise: 0.3} -> ae_fx_to_spine with these args (scale ~ size*2.4/384)")
    return c.result(duration=D * c.k, debris=nd, ae_hint=hint)


def shine(c: Ctx, P: dict) -> dict:
    """A burst of light with exaggerated optics: instant bloom that decays like 1/t with a long tail, two ray stars turning
    against each other, an anamorphic streak, a halo ring that expands and a second chromatic one just behind, twinkles.
    pulse > 0 makes it a breathing loop instead of a burst."""
    pulse = float(P["pulse"])
    D = pulse if pulse > 0 else 1.4
    col = _hexn(P["color"], "FFF2B0")
    size = float(P["size"])
    rng = np.random.default_rng(c.seed + 171)
    grp = c.bone("shine", c.group, 0, 0)
    b_core, b_r1, b_r2, b_fl, b_h1, b_h2 = (c.bone("core", grp), c.bone("rays1", grp), c.bone("rays2", grp), c.bone("flare", grp),
                                             c.bone("halo", grp), c.bone("halo2", grp))
    s_h2 = c.slot(b_h2, "fx/ring", size * 2.2, role="ring")
    s_h1 = c.slot(b_h1, "fx/ring", size * 1.9, role="ring")
    s_r1 = c.slot(b_r1, f"fx/rays_{col}", size * 2.6, make=lambda: tex_rays(col), role="rays")
    s_r2 = c.slot(b_r2, f"fx/rays_{col}_b", size * 2.0, make=lambda: tex_rays(col, rays=10, seed=7), role="rays")
    s_fl = c.slot(b_fl, f"fx/flare_{col}", size * 3.2, make=lambda: tex_flare(col), role="flare")
    s_core = c.slot(b_core, "fx/glow", size * 1.3, role="glow")
    tw = []
    for i in range(int(P["count"])):
        a, rad = rng.uniform(0, 2 * math.pi), size * rng.uniform(0.5, 1.3)
        bn = c.bone(f"tw{i}", grp, math.cos(a) * rad, math.sin(a) * rad * 0.8)
        sl = c.slot(bn, "fx/spark", float(rng.uniform(0.18, 0.34)) * size, color=hexa("FFFFFF", 1.0), role="spark")
        tw.append(dict(b=bn, s=sl, t=float(rng.uniform(0.05, max(0.1, D - 0.45))), life=float(rng.uniform(0.3, 0.5)), rot=float(rng.uniform(-80, 80))))
    slots = [s_h2, s_h1, s_r1, s_r2, s_fl, s_core]
    ts = times_dense(0, D, 30)
    if pulse > 0:
        c.show(slots, 0, None)
        br2 = lambda u: 0.5 + 0.5 * math.sin(2 * math.pi * u / D)  # noqa: E731
        I = lambda u: 0.55 + 0.45 * br2(u)  # noqa: E731
        rot = lambda u: 360.0 * u / D  # noqa: E731
        c.bone_keys(b_h1, "scale", ts, lambda u: (0.95 + 0.1 * br2(u),) * 2)
        c.color_keys(s_h1, ts, lambda u: hexa(col, c.a(0.35 * I(u))))
        c.bone_keys(b_h2, "scale", ts, lambda u: (1.0 + 0.12 * br2(u),) * 2)
        c.color_keys(s_h2, ts, lambda u: hexa("FFB070", c.a(0.2 * I(u))))
        c.bone_keys(b_fl, "scale", ts, lambda u: (0.8 + 0.25 * br2(u), 0.8 + 0.1 * br2(u)))
        c.color_keys(s_fl, ts, lambda u: hexa("FFFFFF", c.a(0.75 * I(u))))
    else:
        c.show(slots, 0, D)
        att = lambda u: smooth(u, 0, 0.05)  # noqa: E731
        I = lambda u: att(u) * (0.22 + 0.78 / (1 + 14 * max(0.0, u - 0.05))) * (1 - smooth(u, D - 0.45, D))  # noqa: E731
        rot = lambda u: 30.0 * ease_out(u / D, 1.5)  # noqa: E731
        c.bone_keys(b_h1, "scale", ts, lambda u: (0.45 + 0.85 * ease_out(u / 0.6, 2.2),) * 2)
        c.color_keys(s_h1, ts, lambda u: hexa(col, c.a(0.75 * (1 - smooth(u, 0.08, 0.9)) * att(u))))
        c.bone_keys(b_h2, "scale", ts, lambda u: (0.4 + 0.95 * ease_out((u - 0.05) / 0.7, 2.2) if u > 0.05 else 0.0,) * 2)
        c.color_keys(s_h2, ts, lambda u: hexa("FFB070", c.a(0.45 * (1 - smooth(u, 0.15, 1.0)) * smooth(u, 0.05, 0.1))))
        c.bone_keys(b_fl, "scale", ts, lambda u: (0.25 + 0.95 * ease_out(u / 0.3, 3.0), 0.5 + 0.5 * I(u)))
        c.color_keys(s_fl, ts, lambda u: hexa("FFFFFF", c.a(min(1.0, 1.1 * I(u)))))
    c.bone_keys(b_r1, "rotate", ts, lambda u: rot(u))
    c.bone_keys(b_r2, "rotate", ts, lambda u: -rot(u) * (1.0 if pulse > 0 else 1.4))
    c.bone_keys(b_r1, "scale", ts, lambda u: (0.55 + 0.45 * (ease_out(u / 0.25, 3.0) if pulse <= 0 else 1.0) * (0.9 + 0.1 * I(u)),) * 2)
    c.bone_keys(b_r2, "scale", ts, lambda u: (0.5 + 0.5 * (ease_out(u / 0.3, 3.0) if pulse <= 0 else 1.0) * (0.85 + 0.15 * I(u)),) * 2)
    c.color_keys(s_r1, ts, lambda u: hexa("FFFFFF", c.a(I(u))))
    c.color_keys(s_r2, ts, lambda u: hexa("FFFFFF", c.a(0.8 * I(u))))
    c.bone_keys(b_core, "scale", ts, lambda u: (0.7 + 0.5 * I(u),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa("FFFFFF", c.a(min(1.0, 1.2 * I(u)))))
    for t_ in tw:
        c.ab.slot_attachment(t_["s"], [(0.0, None), (c.T(t_["t"]), "fx"), (c.T(min(D, t_["t"] + t_["life"])), None)])
        c.ab.bone(t_["b"], "scale", _uniq([(c.T(t_["t"]), 0, 0), (c.T(t_["t"] + t_["life"] * 0.4), 1, 1), (c.T(min(D, t_["t"] + t_["life"])), 0, 0)]), "quad_in_out")
        c.ab.bone(t_["b"], "rotate", _uniq([(c.T(t_["t"]), 0), (c.T(min(D, t_["t"] + t_["life"])), t_["rot"])]), "linear")
    return c.result(duration=D * c.k, loop=(D if pulse > 0 else None))


# ------------------------------------------------------------------ registry
# defaults: every recipe also takes the shared args (x, y, scale, start, duration, color, intensity, seed, into,
# parent, front_of, behind, count, name). "duration" is the life window for window recipes and a time-scale
# (duration / default) for the two one-shots. A default of None / "" means "the recipe's own".
RECIPES: dict[str, dict[str, Any]] = {
    "rune_ring": dict(
        fn=rune_ring, duration=2.7, kind="one-shot", color="FFCD3C",
        summary="Gold rune circle flat on a surface: rings counter-rotate, build up, flash white, fade out.",
        anchor="Subject centre; the ring sits 24 up and is squashed to read as lying flat.",
        options=dict(squash=(0.5, "vertical squash of the ring plane (1 = seen from above, 0.3 = grazing)"),
                     runes=(12, "glyphs between the rings"), spin=(34.0, "deg/s of the outer ring (inner goes -1.6x)"),
                     flash=(1.0, "white flash strength at the peak"))),
    "burst_flare": dict(
        fn=burst_flare, duration=1.8, kind="one-shot", color="FFEE8C", count=10,
        summary="Anamorphic flare with a shock ring and flung sparks: the moment something pops into being.",
        anchor="62 above the subject centre.",
        options=dict(ring_color=("FFE9A0", "shock-ring tint"), spread=(1.0, "how far the sparks fly (x)"))),
    "rim_wisps": dict(
        fn=rim_wisps, duration=5.6, kind="window", color="FFF6DC", count=30,
        summary="Soft feathery fringe all around a footprint; every tuft breathes and flickers on its own.",
        anchor="4, -6 from the subject centre; the ellipse is the footprint.",
        options=dict(rx=(212.0, "footprint half-width"), ry=(110.0, "footprint half-height"),
                     length=(1.0, "tuft length multiplier"))),
    "bloom_aura": dict(
        fn=bloom_aura, duration=5.9, kind="window", color="FF4FA6",
        summary="Coloured halo + inner core + hot spot + rising light column, all breathing.",
        anchor="105 above the subject centre (the flower).",
        options=dict(color2=("C890FF", "inner core colour"), beam=(True, "include the light column"),
                     beam_color=("FFA6DC", "light column tint"))),
    "floor_glow": dict(
        fn=floor_glow, duration=9.8, kind="window", color="FFB84A",
        summary="Warm ellipse of light and a soft streaky reflection under a subject; swells at the climax.",
        anchor="92 below the subject centre.",
        options=dict(reflection=(True, "include the streaky reflection"))),
    "fireflies": dict(
        fn=fireflies, duration=8.2, kind="window", count=34,
        summary="Drifting motes, each with its own respawn period, sway and twinkle (never visibly loops).",
        anchor="40 above the subject centre; spread_x/spread_y set the cloud.",
        options=dict(palette=(["FFE890"] * 6 + ["CFFF8E"] * 2 + ["FFFFFF"] * 2, "colours drawn at random (repeat one to weight it)"),
                     spread_x=(330.0, "cloud half-width"), spread_y=(250.0, "cloud half-height"),
                     rise=(1.0, "upward drift multiplier"), size=(1.0, "mote size multiplier"))),
    "light_beam": dict(
        fn=light_beam, duration=4.0, kind="loop", color="",
        summary="Tall vertical beam: column glow + hot filaments (optionally weaving ribbons) + drifting dust + glints. "
                "style gold = straight shimmering lines, ribbon = big weaving strands with curly glints, blue = thin core with a dense sparkle cloud.",
        anchor="Beam centre (height/2 up and down). Loops every `duration` seconds (use a multiple of 4 to merge into longer clips).",
        options=dict(style=("gold", "gold | ribbon | blue (sets the defaults marked 'style' below)"),
                     height=(640.0, "beam height"), strands=(None, "filament count (style)"), wave=(None, "weave amplitude multiplier (style)"),
                     dust=(None, "dust motes (style); count= overrides"), dust_width=(None, "dust cloud width (style)"),
                     sparks=(None, "popping glints (style)"), core_width=(None, "core thickness (style)"),
                     column_color=(None, "tint of the wide glow (style)"), column_alpha=(None, "wide glow strength (style)"),
                     column_width=(None, "wide glow width (style)"), strand_width=(None, "filament width multiplier (style)"),
                     dust_size=(None, "dust size multiplier (style)"), dust_tint=(None, "hex of the white-ish dust (style)"),
                     cap=("", "hex: add a flat glow at both ends (e.g. FF7A00)"))),
    "portal": dict(
        fn=portal, duration=6.0, kind="loop", color="4A78FF",
        summary="Swirling magic portal: dark indigo disc, two counter-rotating spiral-arm layers, specks orbiting inward, "
                "whipping comet streaks, purple flashes. The churning plasma ring around it is After Effects (template portal_ring): "
                "add it with ae_fx_to_spine using the ring_hint in the result.",
        anchor="Portal centre; design diameter ~420.",
        options=dict(color2=("B050FF", "flash colour"), arms=(3, "spiral arms on the main layer"), specks=(50, "orbiting specks"),
                     comets=(2, "comet streaks"), flashes=([1.5, 4.2], "seconds of the colour flashes inside the loop"),
                     spin=(1.0, "revolutions of the main swirl per loop (integer keeps the loop closed)"),
                     disc_alpha=(0.88, "how much the disc hides what is behind it"))),
    "electric_frame": dict(
        fn=electric_frame, duration=1.0, kind="loop", color="9A30FF",
        summary="Crackling electric border: soft violet underglow that pulses plus white sparks flashing along the outline. "
                "The jagged lightning line itself is After Effects (template electric_frame): add it with ae_fx_to_spine using the ring_hint in the result.",
        anchor="Frame centre.",
        options=dict(width=(400.0, "frame width"), height=(400.0, "frame height"), color2=("F0D8FF", "spark colour"),
                     sparks=(10, "spark flashes along the outline"))),
    "crosshair": dict(
        fn=crosshair, duration=1.25, kind="one-shot", color="FFB02E",
        summary="Targeting reticle: drops in large and spinning, snaps onto the target with a flash and shock ring, hovers, "
                "then recoils and fades when it fires. Events fx_crosshair_lock and fx_crosshair_hit.",
        anchor="Target centre.",
        options=dict(size=(170.0, "reticle diameter"), lock=(0.35, "seconds until it locks on"),
                     hit=(0.85, "seconds when it fires (reticle recoils and fades)"))),
    "hit_burst": dict(
        fn=hit_burst, duration=0.95, kind="one-shot", color="FFB347", count=14,
        summary="Impact: spiky starburst + hot core + two shock rings + flung sparks. Fires fx_hit. Put it on the target when the reticle fires.",
        anchor="Impact point.", options=dict(size=(260.0, "starburst diameter"))),
    "cell_glow": dict(
        fn=cell_glow, duration=3.2, kind="window", color="20E8C8",
        summary="Glowing cell frame(s) with a twinkling starfield inside; pop = flash, burst ring, debris, frame vanishes. "
                "The frame is a 9-slice mesh on four corner bones, so any width/height keeps sharp corners and the "
                "game can resize it by moving the corner bones (result lists them).",
        anchor="Cell centre (each entry of cells is [dx, dy, width, height] from it).",
        options=dict(width=(130.0, "cell width"), height=(130.0, "cell height"), cells=(None, "list of [dx, dy, w, h] to build several cells at once"),
                     color2=("3CFF8A", "pop burst colour"), pop=(2.4, "seconds when it pops (<= 0: never pops, just glows)"),
                     stagger=(0.0, "seconds between cells (appear and pop)"), specks=(None, "starfield count per cell (default from area)"),
                     fill_color=("", "hex of the fill (default: a dark tint of color, which darkens what is behind)"),
                     fill_alpha=(0.55, "fill opacity"))),
    "puff": dict(
        fn=puff, duration=1.15, kind="one-shot", color="FFF1DC", count=9,
        summary="Cartoon puff of smoke: cloud lobes burst outward from a flash, swell and thin out; soft ring. Clear a symbol, "
                "hide a swap, punctuate a pop. Event fx_puff.",
        anchor="Puff centre.",
        options=dict(color2=("FFD27A", "flash colour"), radius=(110.0, "how far the lobes travel"), size=(130.0, "lobe size"),
                     blend=("normal", "normal (opaque cartoon puff) | additive (glowing)"), rise=(24.0, "upward drift in units"),
                     lobes=(True, "cartoon cloud lobes; False = flash + ring only, add the realistic smoke from After Effects (ae_hint)"))),
    "smoke_glow": dict(
        fn=smoke_glow, duration=4.0, kind="loop", color="FF9F8A", count=14,
        summary="Rising smoke haze filling a box with a glow at its base (flame light); loops exactly. Behind a glowing cell, "
                "over a fire, above a bar.",
        anchor="Box centre (width x height).",
        options=dict(width=(130.0, "box width"), height=(350.0, "box height"), color2=("FFC24A", "glow at the base"),
                     blend=("normal", "normal | additive"), alpha=(0.5, "smoke opacity"))),
    "meteor_trace": dict(
        fn=meteor_trace, duration=2.0, kind="loop", color="FFD25A", count=0,
        summary="A bright head with a comet tail racing around a rounded-rectangle frame (any width/height/corner), shedding "
                "sparks, over a faint underglow. Loops exactly; laps per loop is an integer.",
        anchor="Frame centre.",
        options=dict(width=(150.0, "frame width"), height=(150.0, "frame height"), corner=(14.0, "corner radius"),
                     laps=(1, "laps per loop"), tail=(0.22, "tail length as a fraction of the perimeter"),
                     thickness=(24.0, "tail thickness"), size=(60.0, "head size"), sparks=(10, "sparks shed per loop"),
                     underglow=(True, "faint glow hugging the whole frame"))),
    "projectile": dict(
        fn=projectile, duration=0.6, kind="window", color="FFD25A", count=0,
        summary="A glowing shot flies on an arc from the anchor to (tx, ty) with a comet tail and sparks, then an impact flash, "
                "ring and starburst. Events fx_projectile_launch and fx_projectile_hit.",
        anchor="Launch point; tx, ty are the target relative to it.",
        options=dict(tx=(320.0, "target x relative to the launch point"), ty=(-60.0, "target y"), arc=(90.0, "how high the arc bows"),
                     flight=(0.6, "flight time in seconds"), tail=(0.45, "tail length as a fraction of the flight time"),
                     size=(40.0, "head size"), sparks=(10, "sparks shed during the flight"))),
    "explosion": dict(
        fn=explosion, duration=1.9, kind="one-shot", color="FF9A2A", count=22,
        summary="Blast with exaggerated real physics: 1/t flash, Sedov-Taylor shockwave (radius ~ t^0.4, thinning as it spreads), "
                "a fireball that balloons the same way while cooling white -> orange -> dark smoke and rising on its heat, debris with air drag "
                "stretched along its speed, lingering embers, a dust ring on the ground. Events fx_explosion, fx_explosion_shock. "
                "ae_hint: smoke_puff in fire colours for a volumetric fireball.",
        anchor="Blast centre (ground is ~0.28*size below).",
        options=dict(size=(200.0, "blast size"), squash=(0.45, "shockwave squash (1 = seen from the side, 0.3 = from above)"),
                     embers=(8, "lingering embers"))),
    "shine": dict(
        fn=shine, duration=1.4, kind="one-shot", color="FFF2B0", count=7,
        summary="Burst of light: instant bloom decaying like 1/t with a long tail, two ray stars turning against each other, an anamorphic "
                "streak, an expanding halo with a chromatic second ring, twinkles. options={pulse: seconds} turns it into a breathing loop. Event fx_shine.",
        anchor="Light source.",
        options=dict(size=(160.0, "core size"), pulse=(0.0, "> 0: loop that breathes with this period instead of a one-shot burst"))),
    "twinkles": dict(
        fn=twinkles, duration=5.8, kind="window", count=9,
        summary="Four-point stars that pop, spin and vanish, two or three times each, around the subject.",
        anchor="120 above the subject centre.",
        options=dict(palette=(["FFFFFF", "FFF2B0", "FFD6F2"], "star colours"), size=(1.0, "star size multiplier"))),
}

# magic_reveal: (recipe, start, duration, front/back order) — timed against the 13.2 s reference clip.
REVEAL = [("floor_glow", 0.9, 11.2), ("rim_wisps", 3.75, 5.9), ("bloom_aura", 3.7, 6.0), ("rune_ring", 2.0, None),
          ("burst_flare", 3.55, None), ("fireflies", 3.4, 9.2), ("twinkles", 3.9, 5.4)]
REVEAL_LENGTH = 13.2

# art roles: which picture of each recipe the user can replace with their own (art={role: "file.png" | "file.psd#Layer" | {...}})
ROLES: dict[str, dict[str, str]] = {
    "rune_ring": {"ring": "the ring (outer; also the inner ring unless ring_inner is given); centred, square", "ring_inner": "the inner counter-rotating ring"},
    "burst_flare": {"flare": "the streak (horizontal; the vertical one is the same picture turned); centred, wide"},
    "rim_wisps": {"wisp": "one tuft; its BASE on the left edge, fraying to the right"},
    "bloom_aura": {"beam": "the light column; BASE at the bottom, tall"},
    "floor_glow": {"reflect": "the reflection; TOP edge at the subject, fading downward"},
    "fireflies": {"mote": "one soft dot, centred"},
    "twinkles": {"spark": "one star, centred"},
    "light_beam": {"strand": "one filament, tall strip, centred (bent as a mesh)", "column": "the wide glow, tall (stretched to the beam height)",
                   "mote": "one dust dot", "spark": "one glint"},
    "portal": {"disc": "the dark disc (normal blend by default)", "swirl_a": "main spiral layer, square, centred", "swirl_b": "second spiral layer",
               "comet": "the whip streak, square, centred", "mote": "one orbiting speck"},
    "electric_frame": {"under": "the glow hugging the frame, square (stretched to width/height)", "spark": "one spark"},
    "crosshair": {"reticle": "the reticle, square, target point at its centre", "glow": "the soft light behind it", "ring": "the shock ring at lock-on",
                  "flash": "the lock-on flash"},
    "hit_burst": {"starburst": "the impact star, square, centred", "mote": "one flying spark", "glow": "the soft light behind",
                  "ring": "the two shock rings", "core": "the hot centre"},
    "cell_glow": {"frame": "9-slice frame art: give slice (corner size in art px) and px (units per art px)", "fill": "9-slice fill art",
                  "mote": "one starfield dot", "spark": "one pop sparkle", "ring": "the pop shock ring", "glow": "the pop glow"},
    "meteor_trace": {"tail": "the comet tail: a vertical strip, head at the TOP, fading downward (bent along the path)",
                     "glow": "light around the head", "spark": "the head star", "mote": "one shed spark", "under": "the frame underglow"},
    "projectile": {"tail": "the comet tail strip, head at the TOP", "glow": "light around the head", "spark": "the head star",
                   "mote": "one shed spark", "impact_glow": "impact light", "impact_ring": "impact ring", "impact_star": "impact starburst"},
    "explosion": {"flash": "the flash", "ring": "the shockwaves", "fire": "a fireball blob while hot (additive)", "smoke": "the same blob as smoke (normal)",
                  "mote": "one piece of debris", "spark": "one ember", "dust": "the ground dust ring"},
    "shine": {"glow": "the core bloom", "rays": "the ray star (both layers)", "flare": "the anamorphic streak", "ring": "the halo rings", "spark": "one twinkle"},
    "puff": {"cloud": "one cloud lobe (also the core), roughly round, centred", "glow": "the flash", "ring": "the soft ring"},
    "smoke_glow": {"smoke": "one smoke blob, soft, centred", "glow": "the glow at the base"},
}
for _n, _d in ROLES.items():
    RECIPES[_n]["roles"] = _d

SHARED = ("x", "y", "scale", "start", "duration", "color", "intensity", "seed", "into", "parent", "front_of", "behind",
          "count", "name", "art")


def list_recipes() -> dict:
    out: dict[str, Any] = {}
    for n, d in RECIPES.items():
        out[n] = {
            "summary": d["summary"], "kind": d["kind"], "anchor": d["anchor"], "default_duration": d["duration"],
            "default_color": d.get("color", ""), "default_count": d.get("count", 0),
            "options": {k: {"default": v[0], "what": v[1]} for k, v in d["options"].items()},
            "art_roles": d.get("roles", {}),
        }
    out["lock_on"] = {
        "summary": "Crosshairs lock onto each target in turn, fire, and a hit burst lands on every one. Add the symbol pop / coins "
                   "with the game or fx_generate coin_burst at the fx_hit events.",
        "kind": "bundle", "anchor": "Origin of the target offsets", "default_duration": 2.0,
        "options": {"targets": {"default": [[0, 0]], "what": "[[dx, dy], ...] target centres relative to x, y"},
                    "stagger": {"default": 0.18, "what": "seconds between targets"},
                    "crosshair": {"default": {}, "what": "options for crosshair (size, lock, hit, ...)"},
                    "hit": {"default": {}, "what": "options for hit_burst"}},
        "art_roles": {"crosshair": ROLES["crosshair"], "hit_burst": ROLES["hit_burst"]},
        "art_note": "art={'crosshair': {role: spec}, 'hit_burst': {role: spec}}",
    }
    out["magic_reveal"] = {
        "summary": "All seven recipes in one animation, timed like the reference clip (ring 2.0s, flare 3.55s, bloom + wisps + "
                   "twinkles from ~3.8s, fireflies from 3.4s, floor glow 0.9-12s). Hook each fx_<recipe> event to a sound.",
        "kind": "bundle", "anchor": "Subject centre", "default_duration": REVEAL_LENGTH,
        "options": {"skip": {"default": [], "what": "recipe names to leave out"},
                    "overrides": {"default": {}, "what": "{recipe: {param: value}} to retune any member"}},
        "art_note": "art={'<recipe>': {role: spec}} for any member; roles are listed under that recipe",
    }
    out.update({k: dict(v) for k, v in BUNDLE_INFO.items()})
    for n, d in RECIPES.items():
        if d.get("tiers"):
            out[n]["tiers"] = d["tiers"]
    return out


def _params(recipe: str, color: str, count: int, duration: float, options: dict | None) -> dict:
    d = RECIPES[recipe]
    P = {k: v[0] for k, v in d["options"].items()}
    opts = dict(options or {})
    bad = [k for k in opts if k not in P]
    if bad:
        raise ValueError(f"unknown option(s) {bad} for {recipe!r}; valid: {sorted(P)}")
    P.update(opts)
    P["color"] = color or d.get("color", "")
    P["count"] = count or d.get("count", 0)
    P["duration"] = duration or d["duration"]
    return P


# win tiers: one recipe covers small .. epic. Generic multipliers (scale, default count, intensity, one-shot time), then
# the recipe's own `tiers` overrides (RECIPES[name]["tiers"][tier] = {option: value}); the caller's options win over both.
TIERS: dict[str, dict[str, float]] = {
    "small": dict(scale=0.8, count=0.6, intensity=0.85, time=0.85),
    "medium": dict(scale=1.0, count=1.0, intensity=1.0, time=1.0),
    "big": dict(scale=1.15, count=1.4, intensity=1.0, time=1.1),
    "mega": dict(scale=1.3, count=1.9, intensity=1.0, time=1.25),
    "epic": dict(scale=1.5, count=2.6, intensity=1.0, time=1.4),
}

# bundles (recipes made of recipes) register here: name -> fn(project, **apply kwargs) and a listing entry
BUNDLES: dict[str, Callable[..., dict]] = {}
BUNDLE_INFO: dict[str, dict] = {}


def tiered(recipe: str, tier: str, scale: float, count: int, duration: float, intensity: float,
           options: dict | None) -> tuple[float, int, float, float, dict | None]:
    """Apply a win tier to one recipe's arguments (see TIERS). tier "" leaves everything as given."""
    if not tier:
        return scale, count, duration, intensity, options
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; one of {list(TIERS)}")
    m, d = TIERS[tier], RECIPES[recipe]
    opts = dict(d.get("tiers", {}).get(tier, {}))
    t_count, t_duration = opts.pop("count", None), opts.pop("duration", None)   # arguments, not options
    opts.update(options or {})
    if not count:
        count = int(t_count) if t_count else (max(1, round(d["count"] * m["count"])) if d.get("count") else 0)
    if not duration:
        duration = float(t_duration) if t_duration else (d["duration"] * m["time"] if d["kind"] == "one-shot" else 0.0)
    return scale * m["scale"], count, duration, intensity * m["intensity"], opts or None


def apply(project: Project, recipe: str, x: float = 0, y: float = 0, scale: float = 1.0, start: float = 0.0,
          duration: float = 0.0, color: str = "", intensity: float = 1.0, seed: int = 7, into: str = "",
          parent: str = "root", front_of: str = "", behind: str = "", count: int = 0, name: str = "",
          options: dict | None = None, art: dict | None = None, tier: str = "") -> dict:
    """Add one recipe (or a bundle) to the project. Does not save. ``art`` swaps the recipe's pictures for the
    user's own (see ``ROLES``); for the bundles it is keyed by member recipe. ``tier`` (small | medium | big | mega |
    epic) scales the recipe for a win size (see TIERS)."""
    if recipe in BUNDLES:
        return BUNDLES[recipe](project, x=x, y=y, scale=scale, start=start, duration=duration, color=color,
                               intensity=intensity, seed=seed, into=into, parent=parent, front_of=front_of,
                               behind=behind, count=count, name=name, options=options or {}, art=art or {}, tier=tier)
    if tier and recipe in ("lock_on", "magic_reveal"):
        raise ValueError(f"tier is not supported for {recipe}; put its members in a sequence with tier instead")
    if recipe == "lock_on":
        return _lock_on(project, x, y, scale, start, into, parent, front_of, behind, intensity, seed, name, options or {}, art or {})
    if recipe == "magic_reveal":
        return _reveal(project, x, y, scale, start, into, parent, front_of, behind, intensity, seed, name, options or {}, art or {})
    if recipe not in RECIPES:
        raise ValueError(f"unknown recipe {recipe!r}; one of {sorted([*RECIPES, 'lock_on', 'magic_reveal', *BUNDLES])}")
    if scale <= 0:
        raise ValueError("scale must be > 0")
    scale, count, duration, intensity, options = tiered(recipe, tier, scale, count, duration, intensity, options)
    d = RECIPES[recipe]
    P = _params(recipe, color, count, duration, options)
    bad = [r for r in (art or {}) if r not in d.get("roles", {})]
    if bad:
        raise ValueError(f"unknown art role(s) {bad} for {recipe!r}; valid: {sorted(d.get('roles', {}))}")
    # one-shots retime through k; window recipes take the window length directly
    k = (P["duration"] / d["duration"]) if d["kind"] == "one-shot" else 1.0
    c = Ctx(project, recipe, x, y, scale, start, k, intensity, seed, into, parent, front_of, behind, name, art=art)
    res = d["fn"](c, P)
    if c.art_used:
        res["art"] = dict(c.art_used)
    return res


def _split_art(art: dict, members: list[str]) -> dict[str, dict]:
    bad = [k for k in art if k not in members]
    if bad:
        raise ValueError(f"art for a bundle is keyed by member recipe; unknown {bad}; members: {members}")
    return {k: dict(v) for k, v in art.items()}


def _lock_on(project: Project, x, y, scale, start, into, parent, front_of, behind, intensity, seed, name, options, art=None) -> dict:
    """Crosshairs lock onto each target in turn, fire, and a hit burst lands on every one."""
    targets = options.get("targets") or [[0.0, 0.0]]
    stagger = float(options.get("stagger", 0.18))
    ch_opts = dict(options.get("crosshair", {}))
    hit_opts = dict(options.get("hit", {}))
    anim = into or (name or "lock_on")
    last, parts = front_of, []
    hit_at = float(ch_opts.get("hit", 0.85))
    arts = _split_art(art or {}, ["crosshair", "hit_burst"])
    for i, (tx, ty) in enumerate(targets):
        base = dict(x=x, y=y, scale=scale, intensity=intensity, seed=seed + i, into=anim, parent=parent)
        r1 = apply(project, "crosshair", start=start + i * stagger, front_of=last, behind=behind if not parts else "", options=ch_opts or None, art=arts.get("crosshair"), **base)
        # the target offset is applied on the group bone (x, y are the parent-space centre of the whole set)
        g1 = project.data.bone(r1["group_bone"]); g1.x, g1.y = x + tx * scale, y + ty * scale
        last = r1["slots"][-1]
        r2 = apply(project, "hit_burst", start=start + i * stagger + hit_at, front_of=last, options=hit_opts or None,
                   art=arts.get("hit_burst"), **base)
        g2 = project.data.bone(r2["group_bone"]); g2.x, g2.y = x + tx * scale, y + ty * scale
        last = r2["slots"][-1]
        parts += [r1, r2]
    return {"recipe": "lock_on", "animation": anim, "targets": len(targets), "bones": sum(p["bones"] for p in parts),
            "slots": [s for p in parts for s in p["slots"]], "events": sorted({p["event"] for p in parts}),
            "length": start + (len(targets) - 1) * stagger + hit_at + 0.95}


def _reveal(project: Project, x, y, scale, start, into, parent, front_of, behind, intensity, seed, name, options, art=None) -> dict:
    arts = _split_art(art or {}, [r for r, *_ in REVEAL])
    skip = set(options.get("skip", []))
    over = options.get("overrides", {})
    unknown = (skip | set(over)) - set(RECIPES)
    if unknown:
        raise ValueError(f"unknown recipe(s) {sorted(unknown)} in skip/overrides")
    anim = into or f"{name or 'magic_reveal'}"
    parts, last = [], front_of
    first_behind = behind
    for rec, t0, dur in REVEAL:
        if rec in skip:
            continue
        o = dict(over.get(rec, {}))
        o_opts = o.pop("options", None)
        kw = dict(x=x, y=y, scale=scale, start=start + t0, intensity=intensity, seed=seed, into=anim, parent=parent,
                  front_of=last, behind=first_behind if not parts else "", name="", options=o_opts, art=arts.get(rec))
        if dur is not None:
            kw["duration"] = dur
        kw.update(o)
        res = apply(project, rec, **kw)
        parts.append(res)
        last = res["slots"][-1] if res["slots"] else last
    AnimBuilder(project.data, anim, replace=False).event(start + REVEAL_LENGTH, "fx_reveal_end")   # fixes the loop length
    out = {"recipe": "magic_reveal", "animation": anim, "length": REVEAL_LENGTH, "parts": [p["recipe"] for p in parts],
           "bones": sum(p["bones"] for p in parts), "slots": [s for p in parts for s in p["slots"]],
           "events": [p["event"] for p in parts] + ["fx_reveal_end"]}
    return out


# ice and water elements, and the reel moments, register themselves into RECIPES / ROLES
from . import fx_elements  # noqa: E402,F401
from . import fx_reels  # noqa: E402,F401   reel_stop, anticipation_reel
from . import fx_wins  # noqa: E402,F401   payline, win_highlight, multiplier_stack, win_rollup
from . import fx_payouts  # noqa: E402,F401   coin_fountain, cascade_pop
from . import fx_spin  # noqa: E402,F401   near_miss, spin_blur, turbo_spin, screen_shake
from . import fx_ui  # noqa: E402,F401   button_press, idle_shimmer, focus_glow, padlock, popup
from . import fx_ambient  # noqa: E402,F401   weather, god_rays, water_surface, heat_shimmer, fog_roll, lightning_storm
from . import fx_features  # noqa: E402,F401   wild_land, expanding_wild, scatter_trigger, free_spins_transition
from . import fx_bonus  # noqa: E402,F401   pick_reveal, hold_respin, jackpot_wheel, meter_fill
from . import fx_saber  # noqa: E402,F401   saber (Spine half; the AE half is ae_templates/saber.jsx)
from . import fx_pinata  # noqa: E402,F401   wild_glow, wild_transform, mult_cell_glow, cell_pop, confetti_burst, mult_streak, wild_merge, coins_to_bar, bar_sweep, pinata_hit, jar_burst, banner_backdrop
from . import fx_focus  # noqa: E402,F401   speed_lines
from . import fx_cluster  # noqa: E402,F401   cluster_dim, combo_banner, amount_to_bar, jelly_pop, scatter_shine
from . import fx_props  # noqa: E402,F401   prop_idle, liquid_slosh
from . import fx_bundles  # noqa: E402,F401   sequence, win_banner
from . import fx_props_reveal  # noqa: E402,F401   prop_peek, prop_shake, prop_open, prop_hit, prop_upgrade, prop_shatter
from . import fx_props_collect  # noqa: E402,F401   prop_absorb, prop_overflow, counter_plate, prop_multiplier_slam, prop_charge, gem_glint
from . import fx_props_life  # noqa: E402,F401   prop_bob, prop_blink, prop_breathe_heavy, prop_hover_spin, prop_dangle, prop_sway_wind
from . import fx_props_elements  # noqa: E402,F401   flame_wick, liquid_bubble, prop_drip, prop_steam, prop_electric, prop_freeze, prop_dissolve, smoke_wisp
from . import fx_props_bundles  # noqa: E402,F401   bonus_chest_reveal, collect_into_prop, pinata_style_break, magic_vessel
