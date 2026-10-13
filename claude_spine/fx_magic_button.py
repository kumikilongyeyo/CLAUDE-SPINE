"""Magic button family for ``fx_recipe``: the light round a fantasy slot SPIN button (a round medallion in a spiked
frame) as it is tapped, spins, glows "ready" and is disabled. Lifted from a reference clip of a green spin button,
timed frame by frame (30 fps) and colour-matched; every colour is a parameter.

The noisy parts are After Effects templates (``energy_burst``: the cyan smoke burst filling a square round the
button; ``edge_aura``: lime energy hugging the button's silhouette, a loop); these recipes are the Spine-native
light that plays with them:

- ``magic_circle``: a faint magic circle (rings, rune band, spokes, hexagram, glyph circles) that appears small, snaps
  open, keeps opening and turning, with two bright arc swooshes counter-rotating on it.
- ``disc_flash``: the inner disc of the button lit from inside (normal blend, so it covers the disc art evenly);
  curve "press" (flash, hold, decay, 1.45 s) or "ready" (0.42 s ramp, then hold).
- ``rim_pulse``: the "ready" pulse: light hugging the button outline (peak just outside the edge) ramping up over
  0.42 s and holding, plus (``disc``) the disc fill in its own colour.
- ``silhouette_halo``: a wide soft glow round the silhouette with the press envelope (it carries the falloff under an
  ``edge_aura``).
- ``icon_spin``: an icon turning at a constant rate with trailing copies standing in for motion blur (loop).
- ``bar_flood``: a progress bar floods with violet energy, then settles into a gradient fill (the disabled cue).
- ``mote_loop``: motes drifting up round the subject, an exact loop.

The silhouette roles take the subject's outline as a PNG (alpha = shape, centred, the picture's full width =
``size`` units); without one a generic spiked medallion is drawn. Scale 1 = a ~420-unit-wide button.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, hexa, load_art

U = 420.0 / 170.0                 # the reference button was 170 units wide; scale 1 = a 420-wide button
SIL_PX = 384                      # procedural silhouette canvas (px)
SIL_SIZE = SIL_PX * U             # its width in units at scale 1 (the subject spans 170 of its 384 px)


# ---------------------------------------------------------------- pictures (procedural, white unless noted)
def _white(a: np.ndarray) -> Image.Image:
    a = np.clip(a, 0, 1)
    return Image.fromarray(np.dstack([np.full(a.shape + (3,), 255, np.uint8), (a * 255).astype(np.uint8)]), "RGBA")


def _grid(n):
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    return (x - c) / c, (y - c) / c


def tex_medallion(n: int = SIL_PX) -> Image.Image:
    """Generic spiked medallion silhouette: a round frame (r 80 of 384) with four diagonal spikes reaching 116."""
    S = 4
    im = Image.new("L", (n * S, n * S), 0)
    d = ImageDraw.Draw(im)
    c = n * S / 2
    r = 80 * S
    d.ellipse([c - r, c - r, c + r, c + r], fill=255)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        tip = (c + math.cos(a) * 116 * S, c + math.sin(a) * 116 * S)
        b1 = (c + math.cos(a - 0.36) * 70 * S, c + math.sin(a - 0.36) * 70 * S)
        b2 = (c + math.cos(a + 0.36) * 70 * S, c + math.sin(a + 0.36) * 70 * S)
        d.polygon([b1, tip, b2], fill=255)
    a = np.asarray(im.resize((n, n), Image.LANCZOS), np.float32) / 255
    return _white(a)


def tex_circle(n: int = 512, R: float = 160.0) -> Image.Image:
    """Magic circle: outer double ring + tick teeth, a band of rune glyphs, an inner ring, spokes, a hexagram and six
    small glyph circles with crescents. Radius R in its own units -> the outer ring at 152 / 160 of the half-size."""
    S = 2
    N = n * S
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    c = N / 2
    k = N / 2 / R
    rng = np.random.default_rng(13)

    def circle(r, w, v=255):
        d.ellipse([c - r * k, c - r * k, c + r * k, c + r * k], outline=v, width=max(1, int(w * k)))
    circle(152, 1.6)
    circle(146.5, 0.9, 200)
    circle(124, 1.2, 230)
    circle(118, 0.7, 150)
    for i in range(30):
        a0 = i / 30 * 2 * math.pi
        cx, cy = c + math.cos(a0) * 135 * k, c + math.sin(a0) * 135 * k
        ux, uy = math.cos(a0), math.sin(a0)
        vx, vy = -uy, ux
        g = 5.5 * k
        pts = [(cx + ux * rng.uniform(-g, g) + vx * rng.uniform(-g * 0.7, g * 0.7),
                cy + uy * rng.uniform(-g, g) + vy * rng.uniform(-g * 0.7, g * 0.7)) for _ in range(int(rng.integers(3, 5)))]
        d.line(pts, fill=235, width=int(1.1 * k), joint="curve")
    for i in range(72):
        a0 = i / 72 * 2 * math.pi
        r0, r1 = 152, 152 + (6 if i % 3 == 0 else 3)
        d.line([(c + math.cos(a0) * r0 * k, c + math.sin(a0) * r0 * k), (c + math.cos(a0) * r1 * k, c + math.sin(a0) * r1 * k)],
               fill=170, width=int(0.9 * k))
    for i in range(12):
        a0 = (i + 0.5) / 12 * 2 * math.pi
        d.line([(c + math.cos(a0) * 70 * k, c + math.sin(a0) * 70 * k), (c + math.cos(a0) * 118 * k, c + math.sin(a0) * 118 * k)],
               fill=120, width=int(0.8 * k))
    for off in (0, math.pi / 3):
        pts = [(c + math.cos(off + j * 2 * math.pi / 3) * 118 * k, c + math.sin(off + j * 2 * math.pi / 3) * 118 * k) for j in range(4)]
        d.line(pts, fill=140, width=int(0.9 * k))
    for i in range(6):
        a0 = i / 6 * 2 * math.pi + math.pi / 6
        cx, cy = c + math.cos(a0) * 100 * k, c + math.sin(a0) * 100 * k
        r = 9 * k
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=210, width=int(1.0 * k))
        d.arc([cx - r * 0.6, cy - r * 0.6, cx + r * 0.6, cy + r * 0.6], 40 + i * 25, 230 + i * 25, fill=230, width=int(1.0 * k))
    sharp = np.asarray(img.filter(ImageFilter.GaussianBlur(1.3 * S)), np.float32) / 255
    glow = np.asarray(img.filter(ImageFilter.GaussianBlur(5 * S)), np.float32) / 255
    a = np.clip(sharp * 1.1 + glow * 1.2, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((n, n), Image.LANCZOS), np.float32) / 255
    x, y = _grid(n)
    a *= np.clip((1 - np.hypot(x, y)) / 0.02, 0, 1)
    return _white(a)


def tex_arc(n: int = 512, R: float = 160.0, r: float = 150.0, span: float = 95.0) -> Image.Image:
    """A bright arc swoosh on the circle (same frame as tex_circle): thick in the middle, tapered ends."""
    x, y = _grid(n)
    rad = np.hypot(x, y) * R
    ang = np.degrees(np.arctan2(-y, x))
    u = np.clip(1 - np.abs(ang) / (span / 2), 0, 1)
    w = 0.6 + 3.2 * u ** 1.5
    a = np.exp(-((rad - r) / w) ** 2) * u ** 0.7 + 0.35 * np.exp(-((rad - r) / (w * 3.5)) ** 2) * u
    a *= np.clip((1 - np.hypot(x, y)) / 0.02, 0, 1)
    return _white(a)


def tex_disc(n: int = 128) -> Image.Image:
    """The lit disc: full to 98.5% of the radius, brightest in the middle (1.0) and 0.5 at the rim."""
    x, y = _grid(n)
    d = np.hypot(x, y)
    return _white((0.5 + 0.5 * np.exp(-(d / 0.62) ** 2)) * np.clip((0.985 - d) / 0.09, 0, 1))


def tex_mote(n: int = 32) -> Image.Image:
    x, y = _grid(n)
    d = np.hypot(x, y)
    return _white((np.exp(-(d / 0.22) ** 2) + 0.35 * np.exp(-(d / 0.6) ** 2)) * np.clip((1 - d) / 0.1, 0, 1))


def tex_arrows(n: int = 128) -> Image.Image:
    """Generic 'spin' icon: two curved arrows chasing each other (white; tinted by the slot)."""
    S = 4
    im = Image.new("L", (n * S, n * S), 0)
    d = ImageDraw.Draw(im)
    c = n * S / 2
    r0, r1 = 0.62 * c, 0.86 * c
    for k in range(2):
        base = 180 * k
        d.arc([c - r1, c - r1, c + r1, c + r1], base + 20, base + 150, fill=255, width=int(r1 - r0))
        a = math.radians(base + 150)
        mid = (r0 + r1) / 2
        p = (c + math.cos(a) * mid, c + math.sin(a) * mid)
        t = (-math.sin(a), math.cos(a))
        nrm = (math.cos(a), math.sin(a))
        L, Wd = 0.32 * c, 0.42 * c
        d.polygon([(p[0] + nrm[0] * Wd / 2, p[1] + nrm[1] * Wd / 2), (p[0] + t[0] * L, p[1] + t[1] * L),
                   (p[0] - nrm[0] * Wd / 2, p[1] - nrm[1] * Wd / 2)], fill=255)
    a = np.asarray(im.resize((n, n), Image.LANCZOS), np.float32) / 255
    return _white(a)


def _stops(t: np.ndarray, stops) -> np.ndarray:
    ts = [float(s[0]) for s in stops]
    cs = [np.array([int(_hexn(s[1], "FFFFFF")[i:i + 2], 16) for i in (0, 2, 4)], np.float32) for s in stops]
    return np.stack([np.interp(t, ts, [c_[j] for c_ in cs]) for j in range(3)], -1)


# the bar's bevel as a per-row multiplier of the fill colour (row 2 = the stops), measured on the reference
BAR_ROWS = [(1.0, 0.96, 1.61), (1.0, 0.98, 1.63), (1.0, 1.0, 1.0), (0.98, 0.97, 0.93), (0.98, 0.88, 0.55),
            (0.87, 0.79, 0.32), (0.81, 0.69, 0.84), (0.77, 0.64, 0.8), (0.58, 0.51, 0.87), (0.41, 0.26, 0.43),
            (0.31, 0.22, 0.42), (0.35, 0.27, 0.51), (0.31, 0.28, 0.54)]
BAR_STOPS = [[0.0, "FA56D8"], [0.07, "FA6BA8"], [0.14, "E8735B"], [0.21, "FF9B53"], [0.29, "FDBB44"],
             [0.36, "F7D827"], [0.43, "FFFA31"], [0.5, "F9FE4B"], [0.57, "FFFF64"], [0.64, "FEFC46"],
             [0.71, "FCE126"], [0.79, "FBAC38"], [0.86, "FF915A"], [0.93, "EE7183"], [1.0, "F070C0"]]


def tex_bar_fill(stops, w: int = 280) -> Image.Image:
    """The settled bar: the colour stops across, the bevel rows down. Coloured (normal blend): recolour via stops."""
    c = _stops(np.linspace(0, 1, w), stops) / 255
    rgb = np.clip(np.stack([c * np.array(m, np.float32) for m in BAR_ROWS]), 0, 1)
    alpha = np.ones((len(BAR_ROWS), w), np.float32)
    alpha[9:] = 0.9
    return Image.fromarray(np.dstack([(rgb * 255).astype(np.uint8), (alpha * 255).astype(np.uint8)]), "RGBA")


def tex_bar_flash(w: int = 280, h: int = 13) -> Image.Image:
    """Streaky horizontal plasma, brightest a little right of the middle, fading at both ends (white; tinted)."""
    rng = np.random.default_rng(4)
    xs = np.linspace(0, 1, w)
    a = np.zeros((h, w), np.float32)
    for _ in range(16):
        cx, s, amp = rng.uniform(0.1, 0.9), rng.uniform(0.02, 0.1), rng.uniform(0.4, 1)
        a += amp * np.exp(-((xs - cx) / s) ** 2)[None, :] * rng.uniform(0.6, 1.0, (h, 1))
    a = a / a.max()
    prof = np.array([0.95, 1, 1, 1, 1, 0.95, 0.9, 0.85, 0.8, 0.6, 0.5, 0.5, 0.45], np.float32)[:h, None]
    edge = np.clip(xs / 0.06, 0, 1) * np.clip((1 - xs) / 0.06, 0, 1)
    a = (0.4 + 0.6 * a ** 1.4) * prof * ((0.3 + 0.7 * np.exp(-((xs - 0.55) / 0.3) ** 2)) * edge)[None, :]
    return _white(a)


def _silhouette(c: Ctx, P: dict) -> tuple[np.ndarray, float, str]:
    """(alpha array, units per px at scale 1, a cache key). The caller's art 'silhouette' or the medallion."""
    if "silhouette" in c.art:
        im, _ = load_art(c.art["silhouette"])
        c.art_used["silhouette"] = "derived"
        a = np.asarray(im.convert("RGBA"), np.float32)[..., 3] / 255
        key = f"{abs(hash(a.tobytes())) % 10 ** 8:08d}"
    else:
        a = np.asarray(tex_medallion(), np.float32)[..., 3] / 255
        key = "medallion"
    return a, float(P["size"]) / a.shape[1], key


def tex_rim(a: np.ndarray, upx: float, offset: float, width: float, tail: float) -> Image.Image:
    """Light hugging an outline: a band peaking `offset` units outside the edge (gaussian `width`) plus an
    exponential tail (`tail` units), from the silhouette's signed distance."""
    from scipy import ndimage as nd
    sil = a > 0.5
    d = (nd.distance_transform_edt(~sil) - nd.distance_transform_edt(sil)) * upx
    v = np.exp(-((d - offset) / width) ** 2) + 0.55 * np.exp(-np.clip(d, 0, None) / tail) * (d > -2 * U)
    v[d < -3 * U] = 0
    v = nd.gaussian_filter(v, 0.8)
    return _white(v / v.max())


def tex_halo(a: np.ndarray, upx: float, falloff: float) -> Image.Image:
    from scipy import ndimage as nd
    sil = a > 0.5
    d = nd.distance_transform_edt(~sil) * upx
    v = np.exp(-d / falloff)
    h, w = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - (w - 1) / 2, yy - (h - 1) / 2)
    v *= np.clip(((min(h, w) / 2 - 2) - rr) / 12, 0, 1)
    return _white(v)


def _tex(c: Ctx, name: str, im: Image.Image) -> str:
    try:
        c.p.image(name)
    except FileNotFoundError:
        c.p.write_image(name, im)
    return name


def _env(c: Ctx, slot: str, pts, col: str, ease: str = "linear"):
    c.ab.slot_color(slot, [(c.T(t), hexa(col, c.a(a))) for t, a in pts], ease)


# measured envelopes (seconds from the tap / from the start of the ramp)
PRESS_DISC = [(0, 0.06), (1 / 30, 0.2), (3 / 30, 0.49), (5 / 30, 0.77), (6 / 30, 0.92), (8 / 30, 1), (13 / 30, 1),
              (16 / 30, 0.91), (20 / 30, 0.84), (24 / 30, 0.81), (1.0, 0.79), (31 / 30, 0.77), (32 / 30, 0.66),
              (35 / 30, 0.53), (36 / 30, 0.39), (38 / 30, 0.26), (40 / 30, 0.13), (43 / 30, 0.0)]
READY_DISC = [(0.0, 0.0), (0.03, 0.05), (0.07, 0.16), (0.1, 0.39), (0.13, 0.51), (0.17, 0.63), (0.2, 0.76), (0.23, 0.89),
              (0.27, 0.95), (0.33, 1.0), (0.45, 1.0)]
READY_RIM = [(0.0, 0.0), (0.05, 0.05), (0.08, 0.36), (0.12, 0.42), (0.15, 0.64), (0.18, 0.68), (0.22, 0.78), (0.25, 0.8),
             (0.32, 0.84), (0.35, 0.9), (0.42, 1.0), (0.45, 1.0)]
# the edge aura's envelope (seconds from the start of the glow, which leads the burst peak by 0.065 s)
PRESS_AURA = [(0.0, 0.0), (0.037, 0.3), (0.07, 1.0), (0.3, 1.0), (0.4, 0.93), (0.54, 0.9), (0.67, 0.87), (0.8, 0.82),
              (0.94, 0.7), (1.07, 0.48), (1.2, 0.2), (1.32, 0.0)]


# ---------------------------------------------------------------- recipes
def magic_circle(c: Ctx, P: dict) -> dict:
    D = 1.19
    col = _hexn(P["color"], "40FFC8")
    rad = float(P["radius"])                         # outer ring radius, units at scale 1
    w = rad * 320.0 / 152.0
    grp = c.bone("ring", c.group)
    s_ring = c.slot(grp, "fx/mbtn_circle", w, make=tex_circle, role="circle")
    c.show([s_ring], 0, D)
    small, snap = float(P["small"]), float(P["snap"])
    c.ab.bone(grp, "scale", [(c.T(0.0), small, small), (c.T(0.007), small * 1.03, small * 1.03),
                             (c.T(snap), 1.0, 1.0, "sine_out"), (c.T(D), float(P["open"]), float(P["open"]))], "linear")
    turn = float(P["turn"])
    c.ab.bone(grp, "rotate", [(c.T(0.0), turn * 0.16 / 1.35), (c.T(D), turn)], "linear")
    g = float(P["glow"])
    _env(c, s_ring, [(0.0, 0.8 * g), (0.03, 0.55 * g), (0.04, 0.34 * g), (0.29, 0.28 * g), (0.74, 0.24 * g),
                     (0.99, 0.08 * g), (D, 0.0)], col)
    arcs = []
    for i in range(int(P["arcs"])):
        base = 360.0 * i / max(1, int(P["arcs"]))
        b = c.bone(f"arc{i}", grp, rot=base)
        s = c.slot(b, "fx/mbtn_arc", w, make=tex_arc, role="arc")
        arcs.append(s)
        c.show([s], 0.03, 1.04)
        _env(c, s, [(0.03, 0.0), (0.06, 0.85), (0.44, 0.65), (0.79, 0.4), (1.04, 0.0)], col)
        # rotate keys are offsets from the bone's setup angle (base): every arc travels 40 -> 40 - sweep
        c.ab.bone(b, "rotate", [(c.T(0.03), 40.0), (c.T(1.04), 40.0 - float(P["sweep"]))], "sine_out")
    return c.result(duration=D * c.k, arcs=len(arcs))


def disc_flash(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "32FACD")
    curve = str(P["curve"])
    if curve not in ("press", "ready"):
        raise ValueError("disc_flash curve is 'press' or 'ready'")
    pts = PRESS_DISC if curve == "press" else READY_DISC
    D = pts[-1][0] if curve == "press" else 0.45
    b = c.bone("disc", c.group)
    s = c.slot(b, "fx/mbtn_disc", 2 * float(P["radius"]) * 64 / 63, make=tex_disc, role="disc", blend="normal")
    c.show([s], 0, D if curve == "press" else None)
    _env(c, s, pts, col)
    return c.result(duration=D * c.k, curve=curve)


def rim_pulse(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "1E8C48")
    a, upx, key = _silhouette(c, P)
    tex = _tex(c, f"fx/mbtn_rim_{key}", tex_rim(a, upx, 4.0 * U, 5.5 * U, 9.0 * U))
    b = c.bone("rim", c.group)
    s = c.slot(b, tex, float(P["size"]))
    c.show([s], 0, None)
    _env(c, s, READY_RIM, col)
    slots = [s]
    if P["disc"]:
        bd = c.bone("disc", c.group)
        sd = c.slot(bd, "fx/mbtn_disc", 2 * float(P["disc_radius"]) * 64 / 63, make=tex_disc, role="disc", blend="normal")
        c.show([sd], 0, None)
        _env(c, sd, READY_DISC, _hexn(P["disc_color"], "36E08C"))
        slots.append(sd)
    return c.result(duration=0.45 * c.k, holds=True)


def silhouette_halo(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "10500A")
    a, upx, key = _silhouette(c, P)
    tex = _tex(c, f"fx/mbtn_halo_{key}_{int(P['falloff'])}", tex_halo(a, upx, float(P["falloff"])))
    b = c.bone("halo", c.group)
    s = c.slot(b, tex, float(P["size"]))
    D = PRESS_AURA[-1][0]
    c.show([s], 0, D)
    _env(c, s, PRESS_AURA, col)
    return c.result(duration=D * c.k)


def icon_spin(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "FFFFFF")
    speed = float(P["speed"])
    L = 360.0 / abs(speed)
    size = float(P["size"])
    rot = c.bone("spin", c.group)
    slots = []
    trail = float(P["trail"])
    for i in range(int(P["smears"]), 0, -1):         # the faintest copy first (drawn under)
        b = c.bone(f"smear{i}", rot, rot=trail * i if speed > 0 else -trail * i)   # trailing behind the turn
        s = c.slot(b, "fx/mbtn_icon", size, make=tex_arrows, role="icon", blend="normal",
                   color=hexa(col, c.a([0.36, 0.2, 0.12, 0.08][min(i - 1, 3)])))
        slots.append(s)
    s_main = c.slot(rot, "fx/mbtn_icon", size, make=tex_arrows, role="icon", blend="normal", color=hexa(col, c.a(1.0)))
    slots.append(s_main)
    c.show(slots, 0, None)
    sign = -1.0 if speed > 0 else 1.0                # speed > 0 = clockwise (Spine rotation is counter-clockwise)
    c.ab.bone(rot, "rotate", [(c.T(0.0), 0.0), (c.T(L / 2), sign * 180.0), (c.T(L), sign * 360.0)], "linear")
    return c.result(duration=L * c.k, loop=round(L, 4))


def bar_flood(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "B040FF")
    W, H = float(P["width"]), float(P["height"])
    stops = P["stops"] or BAR_STOPS
    key = f"{abs(hash(str(stops))) % 10 ** 8:08d}"
    b = c.bone("bar", c.group)
    bf = c.bone("flash", b)
    s_fill = c.slot(b, f"fx/mbtn_bar_{key}", W, height=H, make=lambda: tex_bar_fill(stops), role="fill", blend="normal",
                    stretch=True)
    s_flash = c.slot(bf, "fx/mbtn_bar_flash", W, height=H, make=tex_bar_flash, role="flash", stretch=True)
    c.show([s_flash], 0.0, 0.25)
    c.ab.bone(bf, "scale", [(c.T(0.0), 0.6, 1.0), (c.T(0.075), 1.0, 1.0, "sine_out"), (c.T(0.24), 1.05, 1.0)], "linear")
    _env(c, s_flash, [(0.0, 0.0), (0.01, 0.6), (0.075, 1.0), (0.11, 1.0), (0.143, 0.7), (0.177, 0.35), (0.21, 0.05),
                      (0.24, 0.0)], col)
    c.show([s_fill], 0.11, None)
    c.ab.slot_color(s_fill, [(c.T(t), hexa("FFFFFF", c.a(v))) for t, v in
                             [(0.11, 0.0), (0.143, 0.4), (0.177, 0.65), (0.21, 1.0), (0.91, 1.0)]], "linear")
    return c.result(duration=0.91 * c.k)


def mote_loop(c: Ctx, P: dict) -> dict:
    L = float(P["duration"])
    n = int(P["count"])
    cols = [_hexn(P["color"], "9CFF6A"), _hexn(P["color2"], "5CFFD2")]
    rng = np.random.default_rng(5 + c.seed - 7)
    sx0, sx1 = (float(v) for v in P["spread_x"])
    y0r = [float(v) for v in P["spread_y"]]
    slots = []
    for i in range(n):
        per = L / int(rng.choice([2, 2, 4]))
        ph = rng.uniform(0, 1)
        x0 = rng.choice([-1, 1]) * rng.uniform(sx0, sx1)
        y0 = rng.uniform(*y0r)
        rise = rng.uniform(40, 90) * U * float(P["rise"])
        sw = rng.uniform(4, 10) * U
        sc = rng.uniform(0.6, 1.25)
        amp = rng.uniform(0.75, 1.0)
        b = c.bone(f"m{i}")
        s = c.slot(b, "fx/mbtn_mote", 11.0 * U * float(P["mote"]), make=tex_mote, role="mote",
                   color=hexa(cols[0 if i % 3 else 1], 0))
        slots.append(s)
        ts = [round(t, 4) for t in np.arange(0, L + 1e-6, 0.1)]
        for w in [(k - ph) * per for k in range(1, int(L / per) + 2) if 0 < (k - ph) * per < L]:
            ts += [round(w - 0.002, 4), round(w, 4)]
        ts = sorted(set(t for t in ts if 0 <= t <= L))

        def st(u, per=per, ph=ph, x0=x0, y0=y0, rise=rise, sw=sw, amp=amp):
            q = (u / per + ph) % 1.0
            e = math.sin(math.pi * q) ** 1.4
            tw = 0.7 + 0.3 * math.sin(2 * math.pi * u * 1.5 + ph * 9)
            return x0 + sw * math.sin(2 * math.pi * (q + ph)), y0 + rise * q, amp * e * tw
        c.ab.bone(b, "translate", [(c.T(t), *st(t)[:2]) for t in ts], "linear")
        c.ab.bone(b, "scale", [(c.T(0.0), sc, sc)], "linear")
        col = cols[0 if i % 3 else 1]
        c.ab.slot_color(s, [(c.T(t), hexa(col, c.a(st(t)[2]))) for t in ts], "linear")
    c.show(slots, 0, None)
    return c.result(duration=L, motes=n, loop=L)


_SIL_OPT = (SIL_SIZE, "width (units at scale 1) of the silhouette picture: the procedural one spans 384 px with the "
                      "subject 170 px wide, so 949 = a 420-wide subject; for your own PNG give its full width in units")

RECIPES.update({
    "magic_circle": dict(
        fn=magic_circle, duration=1.19, kind="one-shot", color="40FFC8",
        summary="A faint magic circle (double ring, rune band, spokes, hexagram, glyph circles) that appears small, snaps "
                "open in 0.03 s, keeps opening and turning, fading by 1.19 s, with bright arc swooshes counter-rotating on it "
                "(a button tap / spell cast; play it BEHIND the subject).",
        anchor="The subject centre.",
        options=dict(radius=(152.0 * U, "outer ring radius at full size (units at scale 1)"),
                     small=(0.62, "size it appears at (fraction of full)"), snap=(0.04, "seconds to snap open"),
                     open=(1.08, "size it reaches at the end"), turn=(28.0, "degrees it turns (counter-clockwise)"),
                     arcs=(2, "arc swooshes (evenly spaced)"), sweep=(160.0, "degrees each arc travels (clockwise)"),
                     glow=(1.0, "circle brightness (the arcs keep theirs)"))),
    "disc_flash": dict(
        fn=disc_flash, duration=43 / 30, kind="one-shot", color="32FACD", normal_blend=True,
        summary="The inner disc of a button lit from inside: a disc (brighter middle, darker rim) in NORMAL blend so it "
                "covers the disc art evenly; curve 'press' = flash in 0.2 s, hold, decay to nothing by 1.43 s; 'ready' = "
                "0.42 s ramp then hold. Draw it over the disc art and under the icon.",
        anchor="The disc centre.",
        options=dict(radius=(63.0 * U, "disc radius (units at scale 1)"), curve=("press", "press | ready"))),
    "rim_pulse": dict(
        fn=rim_pulse, duration=0.45, kind="one-shot", color="1E8C48", normal_blend=True,
        summary="'Ready' pulse: light hugging the subject's outline (peak ~10 units outside the edge at scale 1, a soft "
                "tail) ramping up over 0.42 s and HOLDING (clear the track to cut it), plus the disc lit in disc_color. "
                "The outline comes from art={'silhouette': png} (a spiked medallion without it). Draw the rim BEHIND the "
                "subject, the disc over the disc art.",
        anchor="The subject centre (the silhouette picture's centre).",
        options=dict(size=_SIL_OPT, disc=(True, "also light the disc"), disc_color=("36E08C", "disc colour"),
                     disc_radius=(63.0 * U, "disc radius (units at scale 1)"))),
    "silhouette_halo": dict(
        fn=silhouette_halo, duration=PRESS_AURA[-1][0], kind="one-shot", color="10500A",
        summary="A wide soft glow round the subject's silhouette (exp falloff) with the edge aura's press envelope "
                "(in by 0.07 s, hold, fade out by 1.32 s): the soft light under an edge_aura AE loop. Behind the subject.",
        anchor="The subject centre (the silhouette picture's centre).",
        options=dict(size=_SIL_OPT, falloff=(18.0 * U, "falloff distance (units at scale 1)"))),
    "icon_spin": dict(
        fn=icon_spin, duration=360 / 708.0, kind="loop", color="FFFFFF", normal_blend=True,
        summary="An icon turning at a constant rate (speed deg/s, > 0 = clockwise; the loop is one turn) with `smears` "
                "trailing copies at `trail` degree steps standing in for motion blur. Give your icon as art={'icon': png} "
                "(a generic pair of curved arrows without it). To stop, pause the track (timeScale 0).",
        anchor="The icon's rotation centre.",
        options=dict(speed=(708.0, "degrees per second (> 0 clockwise)"), size=(128.0 * U, "icon width (units at scale 1)"),
                     smears=(2, "trailing copies (0-4)"), trail=(6.5, "degrees between copies"))),
    "bar_flood": dict(
        fn=bar_flood, duration=0.91, kind="one-shot", color="B040FF", normal_blend=True,
        summary="A progress bar floods with violet plasma (in 0.075 s, spreading from 60% to full width) that hands over "
                "to a settled gradient fill (stops, with the bar's bevel rows) between 0.11 and 0.21 s; the fill holds. "
                "color = the plasma, stops = the fill.",
        anchor="The bar centre.",
        options=dict(width=(280.0 * U, "bar length (units at scale 1)"), height=(13.0 * U, "bar thickness"),
                     stops=(None, "[[t 0..1, 'RRGGBB'], ...] fill colour stops (default magenta-orange-yellow-orange-magenta)"))),
    "mote_loop": dict(
        fn=mote_loop, duration=8.0, kind="loop", color="9CFF6A", count=8,
        summary="Motes drifting up round the subject with sway and twinkle, each on a period that divides the loop, so "
                "the loop is exact (idle ambience).",
        anchor="The subject centre.",
        options=dict(color2=("5CFFD2", "every third mote's colour"), spread_x=([95.0 * U, 135.0 * U], "[min, max] distance left / right"),
                     spread_y=([-150.0 * U, 30.0 * U], "[min, max] start height"), rise=(1.0, "rise multiplier"),
                     mote=(1.0, "mote size multiplier"))),
})
ROLES.update({
    "magic_circle": {"circle": "the magic circle, square, centred (outer ring at 95% of the half-size)",
                     "arc": "one arc swoosh on the same frame as the circle (the arc centred on +x)"},
    "disc_flash": {"disc": "the lit disc, square, centred (white = full light)"},
    "rim_pulse": {"silhouette": "the subject's outline: a PNG whose alpha is the shape, centred (the rim is DERIVED from it)",
                  "disc": "the lit disc, square, centred"},
    "silhouette_halo": {"silhouette": "the subject's outline: a PNG whose alpha is the shape, centred (the halo is derived)"},
    "icon_spin": {"icon": "the icon, square, centred on its rotation centre"},
    "bar_flood": {"fill": "the settled bar fill (stretched to width x height)", "flash": "the plasma strip, white"},
    "mote_loop": {"mote": "one soft dot, centred"},
})
for _n in ("magic_circle", "disc_flash", "rim_pulse", "silhouette_halo", "icon_spin", "bar_flood", "mote_loop"):
    RECIPES[_n]["roles"] = ROLES[_n]
