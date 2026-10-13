"""Round SPIN-button light for ``fx_recipe``: the hover glow, the press flash + squash, and the "spin is running" light
(gold bloom collar, anamorphic streak, spectrum halo, glitter), measured frame by frame on a hot-air-balloon slot's
spin button (30 fps) and rebuilt as native Spine: every part is a procedural picture tinted by a slot colour.

Timing model (all recipes but hover_pulse): ``start`` = the flash frame (press_flash: the pressed/dark frame, the
flash comes ``dark`` s later), ``duration`` = how long the light HOLDS before the reels stop, then ``stop`` plays
the clip's own fade: "fade" (normal stop, everything gone in ~0.6 s) or "quick" (turbo stop: a 5-frame drop, then
an after-glow, the line and the spectrum linger ~1.25 s). Sizes follow ``radius`` (the button's radius, 88 in the
clip) times ``scale``.

The measured finding these recipes keep: the gold is NOT additive light on the clip (the background's blue drops by
50-100 where it passes), so the gold parts are a normal-blend WASH plus additive LIGHT. ``wash=False`` keeps only the
additive light (use it over dark backgrounds, where a wash would only darken).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .fx_recipes import BUNDLE_INFO, BUNDLES, RECIPES, ROLES, Ctx, _hexn, apply, hexa
from .timeline import AnimBuilder

F = 1 / 30                      # one frame of the reference (30 fps): the measured timings are in frames
R0 = 88.0                       # the reference button's radius: every size below is in its pixels
HOLD = 35 / 30                  # flash -> reels stop on the reference (f28 -> f63)
L1, L2, L3 = 0.53, 0.9, 1.25    # quick stop: linger, ~45 % left, gone


# ------------------------------------------------------------------ pictures (white unless noted; tint = slot colour)
def _img(a, rgb=None) -> Image.Image:
    a = np.clip(a, 0, 1)
    if rgb is None:
        rgb = np.ones(a.shape + (3,))
    return Image.fromarray((np.dstack([np.clip(rgb, 0, 1), a]) * 255).round().astype(np.uint8), "RGBA")


def _polar(n: int):
    y, x = np.mgrid[0:n, 0:n] + 0.5
    return np.hypot(x - n / 2, y - n / 2), np.arctan2(-(y - n / 2), x - n / 2)


def tex_face_glow() -> Image.Image:          # on the button face, brightest just inside the rim (r 84 of 88)
    r, _ = _polar(184)
    return _img(np.interp(r, [0, 40, 56, 68, 78, 84, 88, 91, 95], [.12, .16, .26, .42, .65, .85, .6, .15, 0]))


def tex_rim_line() -> Image.Image:           # a thin line on the edge
    r, _ = _polar(196)
    return _img(np.exp(-((r - 88) / 1.7) ** 2))


def tex_rim_hot() -> Image.Image:            # white-hot ring: tight core on the rim + soft glow
    r, _ = _polar(232)
    return _img(np.exp(-((r - 87) / 3.0) ** 2) + 0.1 * np.exp(-((r - 92) / 10) ** 2))


def tex_halo() -> Image.Image:               # halo hugging the rim, outside
    r, _ = _polar(256)
    return _img(np.interp(r, [84, 91, 97, 106, 117, 127], [0, 1, .62, .25, .06, 0]))


def tex_flash_halo() -> Image.Image:
    r, _ = _polar(256)
    return _img(np.interp(r, [78, 88, 96, 106, 116, 127], [0, 1, .78, .42, .12, 0]))


def tex_pulse() -> Image.Image:              # thin ring, radius 60 in the picture (bone scale = R / 60)
    r, _ = _polar(136)
    return _img(np.exp(-((r - 60) / 1.9) ** 2) + 0.25 * np.exp(-((r - 58) / 5) ** 2))


def tex_collar() -> Image.Image:             # fiery gold collar: a soft ring broken into wispy rays
    r, th = _polar(256)
    rng = np.random.default_rng(11)
    rays = sum(rng.uniform(.3, 1) * np.cos(k * th + rng.uniform(0, 6.3)) for k in (7, 11, 17, 23, 31)) / 3.2
    return _img(np.interp(r, [92, 97, 102, 110, 119, 127], [0, .85, 1, .5, .12, 0]) * (0.72 + 0.28 * rays))


def tex_ripple() -> Image.Image:             # thin ripple ring, radius 100 (scale = R / 100)
    r, _ = _polar(232)
    return _img(np.exp(-((r - 100) / 1.9) ** 2) + 0.25 * np.exp(-((r - 100) / 7) ** 2))


def tex_bloom() -> Image.Image:              # round bloom, hollow behind the button
    r, _ = _polar(440)
    return _img(np.interp(r, [0, 89, 97, 108, 126, 146, 168, 190, 212, 220], [0, 0, 1, .85, .66, .5, .36, .2, .06, 0]))


def tex_bloom_wash() -> Image.Image:         # the warm wash: peaks a little outside the collar, reaches r ~210
    r, _ = _polar(440)
    return _img(np.interp(r, [0, 89, 97, 110, 126, 146, 168, 190, 212, 220], [0, 0, .55, .8, .7, .55, .42, .28, .1, 0]))


def _streak_grid():
    y, x = np.mgrid[0:120, 0:540] + 0.5
    return (x - 270) / 270, (y - 60) / 60


def tex_streak_band() -> Image.Image:        # anamorphic band: bright flat core (+-10 px) over a haze, 540 wide
    gx, gy = _streak_grid()
    return _img(np.exp(-(gx / .62) ** 2) * (1 - np.abs(gx)) ** .4 * (0.75 * np.exp(-(gy / .16) ** 2) + 0.35 * np.exp(-(gy / .45) ** 2)))


def tex_streak_wash() -> Image.Image:
    gx, gy = _streak_grid()
    return _img(np.exp(-(gx / .55) ** 2 - (gy / .42) ** 2) * (1 - np.abs(gx)) ** .5)


def tex_streak_core() -> Image.Image:        # hairline beside the button
    y, x = np.mgrid[0:16, 0:380] + 0.5
    gx, gy = (x - 190) / 190, (y - 8) / 2.2
    return _img(np.exp(-gy ** 2) * np.clip(1 - np.abs(gx), 0, 1) ** 1.4)


def tex_streak_line() -> Image.Image:        # the long line across the screen, hidden near the button (the core is there)
    y, x = np.mgrid[0:12, 0:640] + 0.5
    gx, gy = (x - 320) / 320, (y - 6) / 1.55
    return _img(np.exp(-gy ** 2) * np.clip(1 - np.abs(gx), 0, 1) ** 0.6 * np.clip((np.abs(gx) - 0.5) / 0.2, 0, 1))


def tex_dot() -> Image.Image:
    r, _ = _polar(24)
    return _img(np.exp(-(r / 1.9) ** 2) + 0.35 * np.exp(-(r / 4.5) ** 2))


def tex_spectrum() -> Image.Image:
    """Spectrum ring, radius 183 of 440 (COLOURED: violet inside -> cyan -> green -> yellow -> orange/red outside),
    brightest at the left and right, the violet side fainter."""
    r, th = _polar(440)
    stops = [(167, (.55, .1, 1.0)), (172, (.1, .35, 1.0)), (177, (0, .9, 1.0)), (182, (.1, 1.0, .15)),
             (187, (1.0, 1.0, 0)), (192, (1.0, .45, 0)), (197, (1.0, .05, .3))]
    rs = [s[0] for s in stops]
    rgb = np.dstack([np.interp(r, rs, [s[1][k] for s in stops]) for k in range(3)])
    env = np.exp(-((r - 182) / 10) ** 2) * np.clip((r - 166) / 12, 0.45, 1)
    return _img(env * (0.42 + 0.58 * np.abs(np.cos(th)) ** 1.3), rgb)


PICS = {"face_glow": tex_face_glow, "rim_line": tex_rim_line, "rim_hot": tex_rim_hot, "halo": tex_halo,
        "flash_halo": tex_flash_halo, "pulse": tex_pulse, "collar": tex_collar, "ripple": tex_ripple, "bloom": tex_bloom,
        "bloom_wash": tex_bloom_wash, "streak_band": tex_streak_band, "streak_wash": tex_streak_wash,
        "streak_core": tex_streak_core, "streak_line": tex_streak_line, "dot": tex_dot, "spectrum": tex_spectrum}
SIZE = {"face_glow": 184, "rim_line": 196, "rim_hot": 232, "halo": 256, "flash_halo": 256, "pulse": 136, "collar": 256,
        "ripple": 232, "bloom": 440, "bloom_wash": 440, "streak_band": 540, "streak_wash": 540, "streak_core": 380,
        "streak_line": 640, "dot": 24, "spectrum": 440}


# ------------------------------------------------------------------ helpers
def _kr(P) -> float:
    return float(P["radius"]) / R0


def _pic(c: Ctx, bone: str, pic: str, kr: float, col: str, blend: str = "additive", role: str | None = None) -> str:
    return c.slot(bone, f"fx/btn_{pic}", SIZE[pic] * kr, color=hexa(col, 0), make=PICS[pic], blend=blend, role=role or pic)


def _alpha(c: Ctx, slot: str, col: str, pts) -> None:
    """pts: (u, value[, ease]) -> rgba keys of the family colour; value is 0..1 before intensity."""
    out = []
    for p in sorted(pts, key=lambda q: q[0]):
        e = p[2] if len(p) > 2 else "linear"
        if out and abs(out[-1][0] - c.T(p[0])) < 1e-6:
            out[-1] = (c.T(p[0]), hexa(col, c.a(p[1])), e)
        else:
            out.append((c.T(p[0]), hexa(col, c.a(p[1])), e))
    c.ab.slot_color(slot, out)


def _at(pts, u: float) -> float:
    """Value of a (u, v[, ease]) key list at u (linear between keys, holding after the last)."""
    pts = sorted(pts, key=lambda q: q[0])
    if u <= pts[0][0]:
        return pts[0][1]
    for a, b in zip(pts, pts[1:]):
        if a[0] <= u <= b[0]:
            if len(a) > 2 and a[2] == "stepped":
                return a[1]
            return a[1] + (b[1] - a[1]) * (u - a[0]) / max(b[0] - a[0], 1e-9)
    return pts[-1][1]


# stop profiles: (seconds after the stop, multiplier of the value held at the stop, ease)
STOP = {
    "fade": {
        "gold": [(0, 1, "sine_in"), (3 * F, .86), (8 * F, .62), (11 * F, .4, "sine_out"), (17 * F, 0)],
        "rim": [(0, 1, "sine_in"), (3 * F, .82), (7 * F, .58), (9 * F, .3, "sine_out"), (14 * F, 0)],
        "spectrum": [(0, 1, "sine_in"), (6 * F, .85), (11 * F, .4, "sine_out"), (19 * F, 0)],
    },
    "quick": {
        "wash": [(0, 1), (2 * F, .6), (3 * F, .25), (5 * F, 0)],
        "gold": [(0, 1), (3 * F, .5), (5 * F, .2, "sine_out"), (12 * F, 0)],
        "core": [(0, 1), (5 * F, .8), (L1, .75, "sine_in_out"), (L2, .3, "sine_out"), (L3, 0)],
        "line": [(0, 1), (L1, 1, "sine_in_out"), (L2, .5, "sine_out"), (L3, 0)],
        "rim": [(0, 1), (3 * F, .6), (5 * F, .3), (L1, .28, "sine_in_out"), (L2, .1, "sine_out"), (1.0, 0)],
        "rim_line": [(0, 1), (3 * F, .4), (6 * F, 0)],
        "face": [(0, 1), (2 * F, .3), (5 * F, 0)],
        "spectrum": [(0, 1), (3 * F, .7), (6 * F, .58), (L1, .5, "sine_in_out"), (L2, .25, "sine_out"), (L3, 0)],
    },
}


def _held(c: Ctx, slot: str, col: str, pts, H: float, stop: str, profile: str | None) -> float:
    """Key a slot: its in/hold curve `pts` cut at the stop H, then the stop profile from the value it holds there.
    Returns the end time (u)."""
    keep = [p for p in pts if p[0] <= H + 1e-6]
    if stop == "hold" or profile is None:
        _alpha(c, slot, col, keep)
        return keep[-1][0] if keep else 0.0
    prof = STOP[stop].get(profile) or STOP[stop]["gold"]
    v = _at(pts, H)
    keep = [p for p in keep if p[0] < H - 1e-6]
    out = keep + [(H + d, v * m, *(e or ["linear"])) for d, m, *e in prof]
    _alpha(c, slot, col, out)
    return H + prof[-1][0]


def _check_stop(P) -> str:
    s = str(P["stop"])
    if s not in ("fade", "quick", "hold"):
        raise ValueError(f"stop must be fade | quick | hold, got {s!r}")
    return s


def _ramp(H: float):
    """The gold family's snap-in (the measured f+1..f+5 ramp) that keeps growing slowly while it holds."""
    return [(0, 0.0), (F, .1), (2 * F, .3), (4 * F, .6), (5 * F, 1.0, "sine_in_out"), (max(H, 5 * F + 1e-3), 1.12)]


# ------------------------------------------------------------------ hover_pulse
def hover_pulse(c: Ctx, P: dict) -> dict:
    kr, per = _kr(P), float(P["period"])
    col = _hexn(P["color"], "FFB8D8")
    halo_c, rim_c, face_c = (_hexn(P[k], d) for k, d in (("halo_color", "7C8CFF"), ("rim_color", "D4CCFF"), ("face_color", "6CE0FF")))
    s_halo = _pic(c, c.group, "halo", kr, halo_c)
    b_pulse = c.bone("pulse", c.group)
    s_pulse = _pic(c, b_pulse, "pulse", kr, col)
    s_face = _pic(c, c.group, "face_glow", kr, face_c)
    s_line = _pic(c, c.group, "rim_line", kr, rim_c)
    _alpha(c, s_face, face_c, [(0, .42), (per, .42)])
    _alpha(c, s_line, rim_c, [(0, .18), (per, .18)])
    _alpha(c, s_halo, halo_c, [(0, .12 * .85, "sine_in_out"), (per / 2, .12, "sine_in_out"), (per, .12 * .85)])
    r0, r1 = float(P["rings"][0]), float(P["rings"][1])
    ts = list(np.arange(0, per, 2 * F)) + [per]
    sc, al = [], []
    for j, u in enumerate(ts):
        v = u / per
        rad = r0 + (r1 - r0) * v
        last = j == len(ts) - 1
        sc.append((c.T(u), rad / 60, rad / 60, "stepped" if last else "linear"))
        al.append((u, 0.0 if last else .62 / (1 + 3.5 * v) * min(1, (1 - v) / 0.15)))
    c.ab.bone(b_pulse, "scale", sc)
    _alpha(c, s_pulse, col, al)
    c.show([s_halo, s_pulse, s_face, s_line], 0, None)
    return c.result(duration=per, slots_by_part={"halo": s_halo, "pulse": s_pulse, "face": s_face, "rim_line": s_line})


# ------------------------------------------------------------------ press_flash
def press_flash(c: Ctx, P: dict) -> dict:
    """Pressed frame(s), then a squash to 90 % that springs back, a white-hot ring on the rim (it stays at the rim
    radius while the button shrinks), a pink-white flash just outside, the face lighting up cyan; holds (the rim
    decays slowly) and stops."""
    from .fx_reels import _merge_keys
    from .fx_ui import _drive
    kr, H, stop = _kr(P), float(P["duration"]), _check_stop(P)
    D0 = float(P["dark"])
    col = _hexn(P["color"], "C8EEFF")
    halo_c, rim_c, face_c = (_hexn(P[k], d) for k, d in (("halo_color", "FFB8D8"), ("rim_color", "D4CCFF"), ("face_color", "6CE0FF")))
    drv, is_carrier = _drive(c, P["button"], "press", (0.0, 0.0), "button")
    Fl = D0                                         # the flash, in recipe time
    s_flash = _pic(c, c.group, "flash_halo", kr, halo_c)
    s_disc = None
    if "disc" in c.art:                             # the caller's button picture, squashed with the press
        s_disc = c.slot(drv, "fx/btn_disc", 2 * float(P["radius"]), blend="normal", role="disc")
        c.ab.slot_color(s_disc, [(c.T(0), "FFFFFFFF")])
    s_face = _pic(c, drv, "face_glow", kr, face_c)
    s_line = _pic(c, drv, "rim_line", kr, rim_c)
    s_hot = _pic(c, c.group, "rim_hot", kr, col)
    k = float(P["depth"]) / 0.097                   # the measured curve: .955 .922 .903 .906 .94 .985 1
    sq = [(0, 1.0), (Fl - F / 2, 1.0), (Fl, 1 - .045 * k), (Fl + F, 1 - .078 * k), (Fl + 2 * F, 1 - .097 * k),
          (Fl + 3 * F, 1 - .094 * k), (Fl + 4 * F, 1 - .06 * k), (Fl + 5 * F, 1 - .015 * k), (Fl + 8 * F, 1.0)]
    _merge_keys(c, drv, "scale", [p[0] for p in sq], lambda u: (_at(sq, u), _at(sq, u)), "mul")
    end = Fl + H
    rim = [(0, 0, "stepped"), (Fl, .25), (Fl + F, .4), (Fl + 2 * F, .5), (Fl + 4 * F, .62), (Fl + 5 * F, .98, "sine_in_out"),
           (Fl + 6 * F, 1, "sine_out"), (Fl + 10 * F, .38), (Fl + 17 * F, .16), (Fl + 32 * F, .12), (max(end, Fl + 32 * F + .01), .1)]
    rim = [(u, v * .6, *e) for u, v, *e in rim]
    face = [(0, 0, "stepped"), (Fl, .6 * .75), (Fl + F, .86 * .75), (Fl + 2 * F, .75), (max(end, Fl + 2 * F + .01), .9 * .75)]
    line = [(0, 0, "stepped"), (Fl, .3), (max(end, Fl + .01), .3)]
    flash = [(0, 0, "stepped"), (Fl, .35 * .25), (Fl + F, .25), (Fl + 3 * F, .9 * .25, "sine_in_out"), (Fl + 6 * F, .25 * .25, "sine_out"),
             (Fl + 12 * F, 0)]
    q = stop == "quick"
    ends = [_held(c, s_hot, col, rim, end, stop, "rim"),
            _held(c, s_face, face_c, face, end, stop, "face" if q else "rim"),
            _held(c, s_line, rim_c, line, end, stop, "rim_line" if q else "rim")]
    _alpha(c, s_flash, halo_c, [p for p in flash if p[0] <= end + 1e-6] or [(0, 0)])
    c.show([s_flash, s_face, s_line, s_hot] + ([s_disc] if s_disc else []), 0, None)
    c.ab.event(c.T(Fl), "fx_press_flash")
    res = c.result(duration=max(ends), flash_at=c.T(Fl), stop_at=c.T(end), button_bone=drv, carrier=is_carrier)
    res["slots_by_part"] = {"flash_halo": s_flash, "face": s_face, "rim_line": s_line, "rim_hot": s_hot, **({"disc": s_disc} if s_disc else {})}
    return res


# ------------------------------------------------------------------ bloom_collar
def bloom_collar(c: Ctx, P: dict) -> dict:
    kr, H, stop = _kr(P), float(P["duration"]), _check_stop(P)
    col = _hexn(P["color"], "FFA81C")
    light_c, after_c = _hexn(P["light_color"], "FFC428"), _hexn(P["afterglow_color"], "FFE45A")
    wash = bool(P["wash"])
    b = c.bone("bloom", c.group)
    parts = {}
    if wash:
        parts["wash"] = _pic(c, b, "bloom_wash", kr, col, blend="normal")
    parts["light"] = _pic(c, b, "bloom", kr, col)
    if stop == "quick":
        parts["afterglow"] = _pic(c, b, "bloom", kr, after_c)
    parts["collar"] = _pic(c, b, "collar", kr, light_c)
    rings = []
    for i, (r0, r1, a) in enumerate(((95, 117, 1.0), (106, 114, .6), (128, 136, .45))):
        rb = c.bone(f"ripple{i}", c.group)
        rings.append(s := _pic(c, rb, "ripple", kr, light_c))
        c.ab.bone(rb, "scale", [(c.T(4 * F), r0 / 100, r0 / 100, "sine_out"), (c.T(max(H, 4 * F + .01)), r1 / 100, r1 / 100)])
        parts[f"ripple{i}"] = s
    c.ab.bone(b, "scale", [(c.T(0), .7, .7, "quad_out"), (c.T(5 * F), 1, 1), (c.T(max(H, 5 * F + .01)), 1.04, 1.04)])
    ramp = _ramp(H)
    q = stop == "quick"
    ends = []
    if wash:
        ends.append(_held(c, parts["wash"], col, [(u, v * .38, *e) for u, v, *e in ramp], H, stop, "wash" if q else "gold"))
    ends.append(_held(c, parts["light"], col, [(u, v * (.08 if wash else .2), *e) for u, v, *e in ramp], H, stop, "gold"))
    ends.append(_held(c, parts["collar"], light_c, [(u, v * .26, *e) for u, v, *e in ramp], H, stop, "gold"))
    for s, a in zip(rings, (1.0, .6, .45)):
        g = .22 * a
        ends.append(_held(c, s, light_c, [(3 * F, 0), (5 * F, g), (max(H, 5 * F + .01), .8 * g)], H, stop, "gold"))
    if q:
        g = .19
        _alpha(c, parts["afterglow"], after_c, [(0, 0, "stepped"), (H, 0), (H + 3 * F, g), (H + L1, .93 * g, "sine_in_out"),
                                                (H + L2, .45 * g, "sine_out"), (H + L3, 0)])
        ends.append(H + L3)
    c.show(list(parts.values()), 0, None)
    return c.result(duration=max(ends), stop_at=c.T(H), slots_by_part=parts)


# ------------------------------------------------------------------ anamorphic_streak
def anamorphic_streak(c: Ctx, P: dict) -> dict:
    kr, H, stop = _kr(P), float(P["duration"]), _check_stop(P)
    col = _hexn(P["color"], "FFE45A")
    wash_c, line_c = _hexn(P["wash_color"], "FFA81C"), _hexn(P["line_color"], "88E4FF")
    wash = bool(P["wash"])
    b = c.bone("streak", c.group)
    bl = c.bone("line", c.group)
    bl2 = c.bone("line2", c.group, 0, float(P["second_line"]) * kr)
    parts = {}
    if wash:
        parts["wash"] = _pic(c, b, "streak_wash", kr, wash_c, blend="normal")
    parts["band"] = _pic(c, b, "streak_band", kr, col)
    parts["line"] = _pic(c, bl, "streak_line", kr * float(P["length"]), line_c, role="line")
    parts["line2"] = _pic(c, bl2, "streak_line", kr * float(P["length"]), line_c, role="line")
    parts["core"] = _pic(c, bl, "streak_core", kr, col)
    for bb in (b, bl, bl2):
        c.ab.bone(bb, "scale", [(c.T(0), .35, 1, "linear"), (c.T(2 * F), .6, 1, "quad_out"), (c.T(5 * F), 1, 1)])
    ramp = _ramp(H)
    q = stop == "quick"
    ends = []
    for part, g, prof in (("wash", 1.0, "wash" if q else "gold"), ("band", .6, "gold"), ("line", .65, "line" if q else "gold"),
                          ("line2", .3, "line" if q else "gold"), ("core", .9, "core" if q else "gold")):
        if part in parts:
            cc = wash_c if part == "wash" else (line_c if part.startswith("line") else col)
            ends.append(_held(c, parts[part], cc, [(u, v * g, *e) for u, v, *e in ramp], H, stop, prof))
    c.show(list(parts.values()), 0, None)
    return c.result(duration=max(ends), stop_at=c.T(H), slots_by_part=parts)


# ------------------------------------------------------------------ rainbow_halo
def rainbow_halo(c: Ctx, P: dict) -> dict:
    kr, H, stop = _kr(P), float(P["duration"]), _check_stop(P)
    col = _hexn(P["color"], "FFFFFF")
    b = c.bone("ring", c.group)
    s = _pic(c, b, "spectrum", kr, col, role="ring")
    R = [(0, 110), (F, 122), (2 * F, 150, "quad_out"), (4 * F, 168, "quad_out"), (5 * F, 183), (max(H, 5 * F + .01), 196)]
    c.ab.bone(b, "scale", [(c.T(u), v / 183, v / 183, *(e or ["linear"])) for u, v, *e in R])
    g = .23
    end = _held(c, s, col, [(0, 0), (F, .2 * g), (2 * F, .45 * g), (4 * F, .62 * g), (5 * F, g), (max(H, 5 * F + .01), g)],
                H, stop, "spectrum")
    c.show([s], 0, None)
    return c.result(duration=end, stop_at=c.T(H), ring_radius=183 * kr)


# ------------------------------------------------------------------ glitter_halo
def glitter_halo(c: Ctx, P: dict) -> dict:
    kr, D, N = _kr(P), float(P["duration"]), int(P["count"])
    col = _hexn(P["color"], "FFB848")
    r_in, r_out = (float(v) for v in P["band"])
    rng = np.random.default_rng(c.seed)
    pops = 0
    for i in range(N):
        b = c.bone(f"g{i}", c.group)
        s = _pic(c, b, "dot", kr, col, role="spark")
        t = rng.uniform(0, 0.5) * (i % 3 != 0)
        al, tr, sc = [(0, 0.0, "stepped")], [], []
        while t < D - 0.1:
            life = rng.uniform(0.45, 0.9)
            ang = rng.uniform(0, 2 * math.pi)
            if rng.random() < float(P["sides"]):                   # bias toward the left and right
                ang = rng.choice([0, math.pi]) + rng.normal(0, 0.45)
            rad = rng.uniform(r_in, r_out) if rng.random() < 0.6 else r_in + abs(rng.normal(0, 30))
            x, y = rad * math.cos(ang) * kr, rad * math.sin(ang) * 0.85 * kr
            dx, dy = math.cos(ang) * rng.uniform(6, 18) * kr, rng.uniform(4, 16) * kr
            peak = rng.uniform(0.55, 1.0)
            sz = rng.uniform(1.1, 2.0)
            e = min(t + life, D)
            tr += [(c.T(t), x, y, "linear"), (c.T(e), x + dx * (e - t) / life, y + dy * (e - t) / life, "stepped")]
            sc += [(c.T(t), sz, sz, "stepped")]
            al += [q for q in [(t, 0.0), (t + 0.06, peak), (t + life * 0.45, peak * 0.35), (t + life * 0.65, peak * 0.9)]
                   if q[0] < e - 1e-3] + [(e, 0.0, "stepped")]
            t = e + rng.uniform(0.02, 0.25)
            pops += 1
        if tr:
            c.ab.bone(b, "translate", tr)
            c.ab.bone(b, "scale", sc)
        _alpha(c, s, col, al)
        c.show([s], 0, None)
    return c.result(duration=D, dots=N, pops=pops)


# ------------------------------------------------------------------ spin_button_glow (bundle)
def spin_button_glow(project, *, x, y, scale, start, duration, color, intensity, seed, into, parent, front_of, behind,
                     count, name, options, art, tier, **_):
    """The whole press -> spin -> stop light of a round spin button, timed like the reference: bloom_collar,
    anamorphic_streak, rainbow_halo, glitter_halo and press_flash (front) in one animation."""
    ok = {"radius", "hold", "stop", "button", "dark", "wash", "skip", "steps"}
    bad = set(options) - ok
    if bad:
        raise ValueError(f"unknown option(s) {sorted(bad)} for 'spin_button_glow'; valid: {sorted(ok)}")
    if color or count or duration:
        raise ValueError("spin_button_glow: colour / count / timing go per member: options={'steps': {recipe: {...}}} or hold=")
    bad = [k for k in (art or {}) if k != "press_flash"]
    if bad:
        raise ValueError("spin_button_glow takes art={'press_flash': {'disc': ...}}")
    anim = into or name or "spin_button_glow"
    if not into:
        AnimBuilder(project.data, anim, replace=True)
    radius = float(options.get("radius", R0))
    hold = float(options.get("hold", HOLD))
    stop = str(options.get("stop", "fade"))
    dark = float(options.get("dark", 2 * F))
    skip = set(options.get("skip", []))
    steps = dict(options.get("steps", {}))
    parts = []
    base = dict(x=x, y=y, scale=scale, intensity=intensity, seed=seed, into=anim, parent=parent)
    last = front_of
    order = [("bloom_collar", start + dark, dict(radius=radius, stop=stop, wash=options.get("wash", True))),
             ("anamorphic_streak", start + dark, dict(radius=radius, stop=stop, wash=options.get("wash", True))),
             ("rainbow_halo", start + dark, dict(radius=radius, stop=stop)),
             ("glitter_halo", start + dark, dict(radius=radius)),
             ("press_flash", start, dict(radius=radius, stop=stop, dark=dark, button=options.get("button", "")))]
    for i, (rec, t, opts) in enumerate(order):
        if rec in skip:
            continue
        o = dict(opts, **steps.get(rec, {}).get("options", {}))
        kw = {k: v for k, v in steps.get(rec, {}).items() if k in ("color", "count", "intensity")}
        dur = hold + (0.35 if stop == "fade" else 0.2) if rec == "glitter_halo" else hold
        r = apply(project, rec, start=t, duration=dur, options=o, art=(art or {}).get(rec), front_of=last,
                  behind=behind if not parts else "", **{**base, **kw})
        last = r["slots"][-1] if r["slots"] else last
        parts.append(r)
    return {"recipe": "spin_button_glow", "animation": anim, "parts": [p["recipe"] for p in parts],
            "slots": [s for p in parts for s in p["slots"]], "bones": sum(p["bones"] for p in parts),
            "events": [p["event"] for p in parts], "flash_at": start + dark, "stop_at": start + dark + hold,
            "button_bone": next((p.get("button_bone") for p in parts if p["recipe"] == "press_flash"), "")}


# ------------------------------------------------------------------ registry
_STOP = ("fade", "fade | quick | hold: what plays after `duration` (fade = normal stop, ~0.6 s; quick = turbo stop, a "
                 "5-frame drop then a ~1.25 s linger; hold = no stop keys, the pose holds)")
_RAD = (R0, "button radius (all sizes follow it; 88 = the reference)")
RECIPES.update({
    "hover_pulse": dict(
        fn=hover_pulse, duration=1.0, kind="loop", color="FFB8D8",
        summary="Round button hover glow (exact loop): the face glows cyan, a thin lilac line on the edge, a violet halo hugging "
                "the rim breathes, and a pink-white ring leaves the rim every period and travels outward fading (84 -> 114 for "
                "r 88, ~1 px per frame). Put it in FRONT of the button art.",
        anchor="Button centre.",
        options=dict(radius=_RAD, period=(1.0, "loop length = one pulse (s)"), rings=([84.0, 114.0], "pulse ring [start, end] radius at r 88"),
                     halo_color=("7C8CFF", "halo hugging the rim"), rim_color=("D4CCFF", "edge line"),
                     face_color=("6CE0FF", "face glow"))),
    "press_flash": dict(
        fn=press_flash, duration=HOLD, kind="window", color="C8EEFF",
        summary="Round button press: the pressed frame(s), a squash to 90 % springing back by f+8 (moves your button= through a "
                "carrier, or the disc art= you pass), a white-hot ring on the rim (stays at the rim radius while the button "
                "shrinks), a pink-white flash halo (peak f+1, gone f+12), the face lighting up cyan; the rim decays while it holds "
                "`duration` s, then `stop`. Event fx_press_flash at the flash.",
        anchor="Button centre.",
        options=dict(radius=_RAD, stop=_STOP, dark=(2 * F, "seconds of the pressed (dark) frame before the flash"),
                     depth=(0.097, "squash depth at the bottom (0.097 = to 90.3 %)"),
                     button=("", "bone of YOUR button: a carrier above it is squashed (your keys untouched); empty: the result's "
                                 "button_bone is ours (parent your button art under it, or pass art={'disc': ...})"),
                     halo_color=("FFB8D8", "flash halo just outside the rim"), rim_color=("D4CCFF", "edge line"),
                     face_color=("6CE0FF", "face glow"))),
    "bloom_collar": dict(
        fn=bloom_collar, duration=HOLD, kind="window", color="FFA81C", normal_blend=True,
        summary="Warm bloom round a round button while it spins: a normal-blend WASH (what turns the background gold), an additive "
                "bloom, a fiery collar broken into rays, and three thin ripple rings creeping out (95->117, 106->114, 128->136 at "
                "r 88). Snaps in over 5 frames, grows slowly while it holds `duration`, then `stop` (quick adds an after-glow).",
        anchor="Button centre (put it BEHIND the button).",
        options=dict(radius=_RAD, stop=_STOP, wash=(True, "normal-blend wash under the additive light (False: additive only, "
                                                           "for dark backgrounds)"),
                     light_color=("FFC428", "collar + ripple rings (additive)"),
                     afterglow_color=("FFE45A", "after-glow of a quick stop"))),
    "anamorphic_streak": dict(
        fn=anamorphic_streak, duration=HOLD, kind="window", color="FFE45A", normal_blend=True,
        summary="Horizontal anamorphic streak through a button: a bright flat band (+-10 px) over a haze, a hairline core beside "
                "the button, a long pale line across the screen and a fainter one below, over a normal-blend wash. Grows out "
                "from 35 % width in 5 frames, holds `duration`, then `stop` (quick: the line and core linger).",
        anchor="Button centre (behind the button).",
        options=dict(radius=_RAD, stop=_STOP, wash=(True, "normal-blend wash under the band (False: additive only)"),
                     wash_color=("FFA81C", "the wash"), line_color=("88E4FF", "the long line"),
                     length=(1.0, "length multiplier of the long lines (1 = 640 at r 88)"),
                     second_line=(-21.0, "offset of the second line (y, at r 88; 0 = on the first)"))),
    "rainbow_halo": dict(
        fn=rainbow_halo, duration=HOLD, kind="window", color="FFFFFF",
        summary="Spectrum halo ring (violet inside -> cyan -> green -> yellow -> orange/red outside, brightest left and right): born "
                "at r 120 one frame after the flash, out to 183 by f+5 (ease out), creeping to 196 while it holds, then `stop`. "
                "The colours are the picture's; `color` only tints / dims it.",
        anchor="Button centre.",
        options=dict(radius=_RAD, stop=_STOP)),
    "glitter_halo": dict(
        fn=glitter_halo, duration=HOLD + 0.35, kind="window", color="FFB848", count=64,
        summary="Gold glitter round a button: dots pop, twinkle twice while drifting out / up and vanish, respawned through the "
                "window (radius band 94-200 at r 88, biased to the sides).",
        anchor="Button centre.",
        options=dict(radius=_RAD, band=([94.0, 200.0], "[inner, outer] radius at r 88"),
                     sides=(0.45, "share of dots placed near the left / right"))),
})
ROLES.update({
    "hover_pulse": {"halo": "halo hugging the rim (hollow ring)", "pulse": "the travelling thin ring (radius 60 of 136)",
                    "face_glow": "the face glow", "rim_line": "the edge line"},
    "press_flash": {"disc": "YOUR button picture (round, centred; drawn 2 x radius wide on the squash bone)",
                    "flash_halo": "flash halo outside the rim", "face_glow": "the face glow", "rim_line": "the edge line",
                    "rim_hot": "the white-hot ring on the rim"},
    "bloom_collar": {"bloom_wash": "the wash (normal blend)", "bloom": "the bloom", "collar": "the collar ring",
                     "ripple": "one thin ripple ring (radius 100 of 232)"},
    "anamorphic_streak": {"streak_wash": "the wash", "streak_band": "the band", "line": "the long thin line",
                          "streak_core": "the hairline core"},
    "rainbow_halo": {"ring": "the spectrum ring (coloured, radius 183 of 440)"},
    "glitter_halo": {"spark": "one glitter dot"},
})
for _n in ("hover_pulse", "press_flash", "bloom_collar", "anamorphic_streak", "rainbow_halo", "glitter_halo"):
    RECIPES[_n]["roles"] = ROLES[_n]

BUNDLES["spin_button_glow"] = spin_button_glow
BUNDLE_INFO["spin_button_glow"] = {
    "summary": "A round spin button's press -> spin -> stop light in one call, timed like the reference: bloom_collar, "
               "anamorphic_streak, rainbow_halo, glitter_halo (behind) and press_flash (front). start = the pressed frame; "
               "the light holds `hold` s, then `stop`.",
    "kind": "bundle", "anchor": "Button centre", "default_duration": 2 * F + HOLD + 0.633,
    "options": {"radius": {"default": R0, "what": "button radius"},
                "hold": {"default": HOLD, "what": "seconds from the flash to the reels stopping"},
                "stop": {"default": "fade", "what": "fade | quick | hold"},
                "dark": {"default": 2 * F, "what": "pressed frame(s) before the flash"},
                "button": {"default": "", "what": "your button bone (press_flash squashes it through a carrier)"},
                "wash": {"default": True, "what": "normal-blend gold washes (False: additive only)"},
                "skip": {"default": [], "what": "member recipes to leave out"},
                "steps": {"default": {}, "what": "{recipe: {color, count, intensity, options}} per member"}},
    "art_note": "art={'press_flash': {'disc': 'button.png'}} draws your button on the squash bone",
}
