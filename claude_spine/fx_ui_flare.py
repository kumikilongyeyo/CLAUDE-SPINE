"""UI flare family for ``fx_recipe``: the light around a slot's spin button and win banner, lifted from a reference
clip of a desert-themed slot's bottom UI (a round spin button, a win banner, a door with a rune coin above it).

* ``rim_glow_pulse``: a press on a round button. The rim turns white-hot, an orange wash covers the inner band (NORMAL
  blend, because additive light cannot turn a teal band orange), a halo spreads and 2 faint shock rings leave. The
  wavy fire ripple is After Effects: the existing ``ripple_glow`` template, look=line, origin=rim (``ae_hint``, or pass
  the rendered frames as ``ripple_frames`` and the recipe imports them, tintable).
* ``anamorphic_burst``: a spin-start flare on the button. A rim bloom, a wide bloom, a fan of thin rays, 2 tilted
  anamorphic streaks (white-cyan over warm), a blue light on the top rim and drifting sparks. The flame wisps that fly
  out along the streak are the new AE template ``flame_wisps`` (one grey frame set played as 4 tinted copies: orange,
  a mirrored orange, violet and pink).
* ``ray_fan_beam``: a looping "total win" light from the top of an arch. A fan of soft wedges sways and breathes on
  whole cycles (violet centre, pink-red, magenta outside), with a haze, a light column up to a target (a coin above a
  door) with a ring on it, and a hot spot with a flat flare.
* ``glyph_strike``: a glowing glyph flies straight into a target in 6 frames (measured at a constant ~38 px per
  frame), with a comet trail, a light band, prism shards and twinkles. On impact: a flash, burst rays, an orange ring,
  the glyph staying on the target and cooling to orange, and a light line drawing out through the target. A secondary
  target (a hanging coin) lights up; if you pass its lit picture as ``art={"secondary": ...}`` it is revealed bottom-up
  by a clipping wipe.
* ``banner_energy``: a win banner landing. Green burst spikes out of the text, green "/" slashes racing outward on both
  sides, green haze bands, a gold bloom, a flare along the top bar, coins popping from 2 sources, glints, and a
  resting gold light that rises and stays.
* ``ember_drift``: a seamless loop of embers drifting up and fading over an area.

All pictures are drawn here (white, tinted by the slot colour); ``art=`` roles take the caller's own. Times are the
clip's frames at 30 fps (``F``). At scale 1 the button is ~184 units across (rim radius ~92), the banner ~760 wide.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from . import ae_bridge
from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, _uniq, hexa
from .ir import ClippingAttachment, Slot

F = 1.0 / 30.0


# ---------------------------------------------------------------------------------------------------- pictures
def _g(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return (x + 0.5) / w * 2 - 1, (y + 0.5) / h * 2 - 1


def _img(a):
    a = np.clip(a, 0, 1)
    one = np.ones_like(a)
    return Image.fromarray((np.dstack([one, one, one, a]) * 255).round().astype(np.uint8), "RGBA")


def _sm(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _radial(n, prof, span):
    x, y = _g(n, n)
    return _img(prof(np.hypot(x, y) * span / 2))


def _ray():
    x, y = _g(256, 32)
    u = (x + 1) / 2
    return _img(_sm(u, 0.0, 0.06) * (1 - u) ** 1.3 * np.exp(-(y / (0.18 + 0.5 * (1 - u))) ** 2 * 3))


def _wedge():
    x, y = _g(256, 128)
    u = (x + 1) / 2
    half = 0.04 + 0.92 * u
    return _img(_sm(u, 0.0, 0.08) * (1 - u) ** 0.9 * np.exp(-(y / np.maximum(half, 1e-3)) ** 2 * 2.2))


def _streak():
    x, y = _g(512, 48)
    a = np.exp(-np.abs(x) ** 1.6 / 0.18) * np.exp(-(y / 0.22) ** 2) + 0.5 * np.exp(-np.abs(x) / 0.35) * np.exp(-(y / 0.6) ** 2)
    return _img(a * _sm(-np.abs(x), -1, -0.9))


def _trail():
    x, y = _g(256, 64)
    u = (x + 1) / 2
    return _img(u ** 1.4 * np.exp(-(y / (0.25 + 0.45 * u)) ** 2 * 2.4) * _sm(-u, -1, -0.97))


def _star4():
    x, y = _g(96, 96)
    r = np.hypot(x, y)
    a = np.exp(-np.abs(x) / 0.05) * np.exp(-np.abs(y) / 0.55) + np.exp(-np.abs(y) / 0.05) * np.exp(-np.abs(x) / 0.55)
    return _img((a + np.exp(-(r / 0.16) ** 2)) * _sm(-r, -1, -0.8))


def _shard():
    x, y = _g(64, 64)
    P = [(0.0, -0.9), (0.55, 0.7), (-0.5, 0.6)]
    d = np.full(x.shape, 9.0)
    inside = np.ones(x.shape, bool)
    for i in range(3):
        (x1, y1), (x2, y2) = P[i], P[(i + 1) % 3]
        nx, ny = y2 - y1, -(x2 - x1)
        s = ((x - x1) * nx + (y - y1) * ny) / math.hypot(nx, ny)
        inside &= s <= 0
        d = np.minimum(d, np.abs(s))
    return _img(np.where(inside, 0.35 + 0.65 * np.exp(-d / 0.06), np.exp(-d / 0.03) * 0.6))


def _line_v():
    x, y = _g(16, 256)
    return _img(np.exp(-(x / 0.28) ** 2 * 2.5) * _sm(-np.abs(y), -1, -0.9))


def _glyph():
    """the default projectile glyph: a glowing diamond outline with a bright core (pass your own rune as art=glyph)"""
    x, y = _g(160, 160)
    d = np.abs(x) + np.abs(y)                       # diamond distance
    edge = np.exp(-((d - 0.55) / 0.05) ** 2)
    core = np.exp(-(d / 0.22) ** 2)
    halo = np.exp(-(d / 0.6) ** 2) * 0.35
    return _img(edge + 0.8 * core + halo)


PICS = {
    "glow": lambda: _radial(128, lambda r: np.exp(-(r / 0.42) ** 2 * 2.2) * _sm(-r, -1, -0.92), 2.0),
    "halo": lambda: _radial(256, lambda r: _sm(r, 82, 93) * np.exp(-np.maximum(r - 93, 0) / 10.0) * _sm(-r, -150, -138), 300),
    "wash": lambda: _radial(256, lambda r: (0.45 + 0.55 * _sm(r, 50, 66)) * _sm(r, 28, 46) * _sm(-r, -95, -88), 200),
    "ring": lambda: _radial(256, lambda r: np.exp(-((r - 0.8) / 0.028) ** 2), 2.0),
    "ring_soft": lambda: _radial(256, lambda r: np.exp(-((r - 0.8) / 0.07) ** 2), 2.0),
    "bloomring": lambda: _radial(256, lambda r: _sm(r, 66, 92) * np.exp(-np.maximum(r - 92, 0) / 30.0) * _sm(-r, -210, -190), 420),
    "glow_flat": lambda: _radial(256, lambda r: np.exp(-(r / 0.62) ** 3) * _sm(-r, -1, -0.9), 2.0),
    "dot": lambda: _radial(32, lambda r: np.exp(-(r / 0.45) ** 2 * 2.5) * _sm(-r, -1, -0.85), 2.0),
    "ray": _ray, "wedge": _wedge, "streak": _streak, "trail": _trail, "star4": _star4, "shard": _shard,
    "line_v": _line_v, "glyph": _glyph,
}


def _slot(c: Ctx, bone, pic, w, h=None, *, ox=0.0, oy=0.0, blend="additive", role=None):
    return c.slot(bone, f"fx/uiflare_{pic}", w, color="FFFFFF00", ox=ox, oy=oy, height=h, make=PICS[pic], blend=blend,
                  role=role)


def _fade(c: Ctx, slot, col, pts, gain=1.0):
    """slot colour `col` at alpha gain * a, at the given (frame, a) knots, linear between them"""
    c.ab.slot_color(slot, _uniq([(c.T(f * F), hexa(col, c.a(a * gain))) for f, a in pts]), "linear")


def _keys(c: Ctx, bone, timeline, pts):
    """bone keys at (seconds, values...) design times"""
    c.ab.bone(bone, timeline, _uniq([(c.T(p[0]), *p[1:]) for p in pts]), "linear")


def _ts(t0, t1, step=F):
    n = max(1, int(round((t1 - t0) / step)))
    return [t0 + (t1 - t0) * i / n for i in range(n + 1)]


def _eo(u, p=2.5):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** p


def _frames(d):
    p = Path(str(d)).expanduser()
    fs = sorted(p.glob("*.tif")) or sorted(p.glob("*.png"))
    if not fs:
        raise ValueError(f"no .tif / .png frames in {p}")
    return fs


def _seq(c: Ctx, name, frames_dir, fps, *, parent, start_f, seq_mode, until_f=0.0, light, dark, max_size, max_frames=0):
    """an AE frame sequence (tintable, additive) placed in the recipe's slot run"""
    res = ae_bridge.import_sequence(
        c.p, c.sk.unique_name(f"{c.prefix}_{name}", "slot"), _frames(frames_dir), float(fps), mode="additive",
        seq_mode=seq_mode, animation=c.anim, start=c.T(start_f * F), until=c.T(until_f * F) if until_f else 0.0,
        parent=parent, max_size=max_size, max_frames=max_frames, front_of=c.last_slot or "", tintable=True,
        tint=f"{light}/{dark}")
    c.last_slot = res["slot"]
    c.slots.append(res["slot"])
    return res


def _after(c: Ctx, slots):
    """the slot of `slots` that is last in the draw order becomes the run's tail"""
    idx = {s.name: i for i, s in enumerate(c.sk.slots)}
    c.last_slot = max(slots, key=lambda s: idx[s])


# ---------------------------------------------------------------------------------------------------- rim_glow_pulse
AMP = [(0, 0.57), (1, 0.75), (2, 0.87), (3, 0.95), (5, 1.0), (8, 0.9), (11, 0.85), (15, 0.75), (19, 0.64),
       (23, 0.53), (25, 0.46), (27, 0.33), (28, 0.18), (29, 0.0)]
WASH = [(0, 0.6), (2, 0.9), (5, 1.0), (20, 0.95), (25, 0.8), (27, 0.6), (28, 0.35), (29, 0.0)]
RIPPLE_PARAMS = dict(size=384, duration=1, fps=30, look="line", origin="rim", color="FF4A08", core="FFB040", radius=0.48,
                     travel=0.4, waves=3, life=0.9, echo=2, wave=0.9, wave_width=0.02, rim=0, halo=0.35, wobble=16,
                     wobble_size=0.1, softness=0.5, breathe=0, seed=5)


def rim_glow_pulse(c: Ctx, P: dict) -> dict:
    D = 29
    col = _hexn(P["color"], "FF6A14")
    hot, wash, deep = (_hexn(P[k], d) for k, d in (("hot", "FFD84A"), ("wash", "FF8A30"), ("deep", "A82006")))
    b = c.bone("halo")
    s = _slot(c, b, "halo", 300, role="halo")
    c.show([s], 0, D * F)
    _fade(c, s, col, AMP, 0.75)
    _keys(c, b, "scale", [(t, 1 + 0.09 * _eo(t / (D * F), 1.6), 1 + 0.09 * _eo(t / (D * F), 1.6)) for t in _ts(0, D * F)])
    for i, (f_on, a0, r1) in enumerate(((3, 0.18, 1.65), (8, 0.12, 1.5))):
        b = c.bone(f"wave{i}")
        s = _slot(c, b, "ring", 250, role="ring")
        c.show([s], f_on * F, D * F)
        life = (D - f_on) * F
        t_on = f_on * F
        _keys(c, b, "scale", [(t, *((1.0 + (r1 - 1) * _eo((t - t_on) / life, 2.2)),) * 2) for t in _ts(t_on, D * F)])
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(col, c.a(a0 * math.sin(math.pi * min(1, (t - t_on) / life)) ** 0.7)))
                                  for t in _ts(t_on, D * F)]), "linear")
    hint = dict(template="ripple_glow", params=dict(RIPPLE_PARAMS), mode="additive", seq_mode="loop", tintable=True,
                tint=f"{col}/{deep}", parent=c.group, max_size=320, max_frames=15, start=c.T(0), until=c.T(D * F),
                note="the wavy fire ripple: ae_template ripple_glow with these params -> render -> pass the frames "
                     "folder as options.ripple_frames (or ae_fx_to_spine with these args); its alpha follows the pulse at 0.3")
    seq = None
    if P["ripple_frames"]:
        seq = _seq(c, "ripple", P["ripple_frames"], P["frames_fps"], parent=c.group, start_f=0, seq_mode="loop",
                   until_f=D, light=col, dark=deep, max_size=320, max_frames=15)
        c.ab.slot_color(seq["slot"], _uniq([(c.T(f * F), hexa("FFFFFF", c.a(0.3 * a))) for f, a in AMP]), "linear", "alpha")
    s = _slot(c, c.group, "wash", 200, blend="normal", role="wash")
    c.show([s], 0, D * F)
    _fade(c, s, wash, WASH, 0.82)
    for pic, r, gain in (("ring", 88, 1.0), ("ring_soft", 89, 0.55)):
        s = _slot(c, c.group, pic, 2 * r / 0.8, role="ring")
        c.show([s], 0, D * F)
        _fade(c, s, hot, AMP, gain)
    return c.result(duration=D * F * c.k, ae_hint=hint, ripple=seq["slot"] if seq else None)


# ---------------------------------------------------------------------------------------------------- anamorphic_burst
WISPS_PARAMS = dict(width=768, height=192, fps=30, duration=0.9, seed=11, speed=380, strand=16, stretch=14, contrast=145,
                    brightness=-42, spread=0.6, thick=0.24, curl=16, curl_size=34)


def anamorphic_burst(c: Ctx, P: dict) -> dict:
    D = 48
    col = _hexn(P["color"], "FFB42E")
    bloom, hot, ray, core, blue, spark = (_hexn(P[k], d) for k, d in (
        ("bloom", "FFD028"), ("hot", "FFF2B8"), ("ray", "FFE6F2"), ("core", "D8F6FF"), ("blue", "5AB4FF"), ("spark", "FFD070")))
    violet, violet_dark, pink, dark = (_hexn(P[k], d) for k, d in (
        ("violet", "C68CFF"), ("violet_dark", "3A10A0"), ("pink", "FF8CD2"), ("dark", "A02A08")))
    tilt = c.bone("tilt", rot=float(P["tilt"]))
    rng = np.random.default_rng(c.seed + 16)
    # behind: the wide bloom and the ray fan
    s = _slot(c, c.group, "glow", 680)
    c.show([s], 0, 26 * F)
    _fade(c, s, col, [(0, 0), (1, 0.6), (2, 0.9), (4, 0.95), (8, 0.55), (14, 0.25), (20, 0.08), (26, 0.0)])
    nr = int(P["rays"])
    ray_specs = []
    for i in range(nr):
        ang = i * 360.0 / nr + rng.uniform(-8, 8)
        L = rng.uniform(110, 170) + 70 * abs(math.sin(math.radians(ang))) ** 2
        w = rng.uniform(10, 22)
        a0 = rng.uniform(0.3, 0.6)
        ray_specs.append((ang, L, w, a0))
    rays = []
    for i, (ang, L, w, a0) in enumerate(ray_specs):
        b = c.bone(f"ray{i}", rot=ang)
        s = _slot(c, b, "ray", L, w, ox=L / 2, role="ray")
        rays.append(s)
        c.show([s], F, 24 * F)
        _fade(c, s, ray, [(1, 0.0), (2, 0.1), (5, 0.35), (8, 0.7), (12, 0.65), (18, 0.35), (23, 0.0)], a0)
        _keys(c, b, "scale", [(F, 0.65, 1.0), (6 * F, 1.0, 1.0), (23 * F, 1.15, 1.0)])
        _keys(c, b, "rotate", [(F, 0.0), (23 * F, 6.0)])
    # in front: the rim bloom, its pink tail, a faint hot core
    s = _slot(c, c.group, "bloomring", 420)
    c.show([s], 0, 31 * F)
    _fade(c, s, bloom, [(0, 0), (1, 0.45), (2, 0.75), (3, 1.0), (5, 0.7), (8, 0.4), (12, 0.2), (18, 0.05), (22, 0.0)], 0.75)
    s = _slot(c, c.group, "bloomring", 440)
    c.show([s], 6 * F, 31 * F)
    _fade(c, s, ray, [(6, 0), (8, 0.2), (12, 0.26), (18, 0.16), (25, 0.05), (30, 0.0)])
    s = _slot(c, c.group, "glow", 240)
    c.show([s], 0, 17 * F)
    _fade(c, s, hot, [(0, 0), (1, 0.06), (3, 0.1), (4, 0.1), (6, 0.05), (10, 0.0)])
    # the flame wisps (AE flame_wisps): orange, a mirrored orange, violet (stretching), pink
    hint = dict(template="flame_wisps", params=dict(WISPS_PARAMS), mode="additive", seq_mode="once", tintable=True,
                tint=f"{col}/{dark}", parent=tilt, start=c.T(4 * F), max_size=512,
                copies=[dict(x=0, y=-6, start=c.T(5 * F), scale=0.9, rotation=184.0),
                        dict(x=0, y=4, start=c.T(6 * F), scale=0.95, rotation=5.0, tint=f"{violet}/{violet_dark}"),
                        dict(x=-10, y=-10, start=c.T(8 * F), scale=0.8, rotation=-4.0, tint=f"{pink}/{violet_dark}")],
                note="ae_template flame_wisps with these params -> render -> pass the frames folder as options.wisps_frames "
                     "(the recipe then adds the per-copy alpha and the violet stretch too)")
    wisp_slots = []
    if P["wisps_frames"]:
        res = _seq(c, "wisps", P["wisps_frames"], P["frames_fps"], parent=tilt, start_f=4, seq_mode="once",
                   light=col, dark=dark, max_size=512)
        o2 = ae_bridge.copy_instance(c.p, res, x=0, y=-6, start=c.T(5 * F), scale=0.9, rotation=184.0)
        v = ae_bridge.copy_instance(c.p, res, x=0, y=4, start=c.T(6 * F), scale=0.95, rotation=5.0, tint=f"{violet}/{violet_dark}")
        _keys(c, v["bone"], "scale", [(6 * F, 1.0, 1.25), (30 * F, 1.1, 1.3)])
        p2 = ae_bridge.copy_instance(c.p, res, x=-10, y=-10, start=c.T(8 * F), scale=0.8, rotation=-4.0,
                                     tint=f"{pink}/{violet_dark}")
        c.ab.slot_color(p2["slot"], [(c.T(8 * F), "FFFFFF00"), (c.T(11 * F), "FFFFFFB0"), (c.T(30 * F), "FFFFFFB0")], "linear", "alpha")
        c.ab.slot_color(o2["slot"], [(c.T(5 * F), "FFFFFFD0"), (c.T(10 * F), "FFFFFF90"), (c.T(30 * F), "FFFFFF60")], "linear", "alpha")
        wisp_slots = [res["slot"], o2["slot"], v["slot"], p2["slot"]]
        c.slots += wisp_slots[1:]
        _after(c, wisp_slots)
    # the anamorphic streaks: warm under, white-cyan core over
    for nm, cl, w, h, oy, kv in (("streak_warm", col, 520, 34, -5, [(4, 0.0), (5, 0.75), (7, 0.6), (10, 0.25), (13, 0.0)]),
                                 ("streak", core, 600, 20, 0, [(4, 0.0), (5, 0.75), (7, 0.7), (9, 0.4), (12, 0.0)])):
        b = c.bone(nm, tilt, y=oy)
        s = _slot(c, b, "streak", w, h, role="streak")
        c.show([s], 4 * F, 13 * F)
        _fade(c, s, cl, kv)
        _keys(c, b, "scale", [(4 * F, 0.55, 1.0), (8 * F, 1.0, 1.0), (13 * F, 1.15, 0.8)])
    b = c.bone("blue", y=78)
    s = _slot(c, b, "glow", 220, 110)
    c.show([s], 7 * F, 25 * F)
    _fade(c, s, blue, [(7, 0), (10, 0.55), (15, 0.45), (20, 0.2), (24, 0)])
    ns = int(P["count"])
    for i in range(ns):
        side = 1 if i % 2 == 0 else -1
        t0 = rng.uniform(4, 9) * F
        life = rng.uniform(0.6, 1.3)
        r0 = rng.uniform(40, 95)
        sp = rng.uniform(40, 150)
        a = math.radians(rng.uniform(-14, 14))
        b = c.bone(f"spark{i}", tilt, x=side * r0)
        s = _slot(c, b, "dot", rng.uniform(5, 10))
        t1 = min(D * F, t0 + life)
        c.show([s], t0, t1)
        tt = _ts(t0, t1, 2 * F)
        _keys(c, b, "translate", [(t, side * (sp * (1 - math.exp(-(t - t0) * 2.2)) / 2.2 * math.cos(a)),
                                   sp * (1 - math.exp(-(t - t0) * 2.2)) / 2.2 * math.sin(a) + 12 * (t - t0)) for t in tt])
        ph = rng.uniform(0, 6.28)
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(spark, c.a((0.55 + 0.45 * math.sin(ph + 19 * (t - t0))) * min(1, (t - t0) / 0.08)
                                                              * max(0.0, 1 - (t - t0) / life) ** 0.8))) for t in tt]), "linear")
    return c.result(duration=D * F * c.k, rays=nr, sparks=ns, tilt_bone=tilt, ae_hint=hint, wisps=wisp_slots)


# ---------------------------------------------------------------------------------------------------- ray_fan_beam
FAN = [(-74, "magenta", 175, 0.75), (-56, "magenta", 190, 0.75), (-38, "red", 200, 0.6), (-20, "red", 195, 0.45),
       (-6, "color", 205, 0.55), (7, "color", 200, 0.5), (22, "red", 190, 0.45), (40, "red", 200, 0.6),
       (57, "magenta", 190, 0.75), (75, "magenta", 170, 0.75)]


def ray_fan_beam(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    C = dict(color=_hexn(P["color"], "9C78FF"), magenta=_hexn(P["magenta"], "F050E0"), red=_hexn(P["red"], "FF4A62"),
             beam=_hexn(P["beam"], "ECD2FF"), gold=_hexn(P["gold"], "FFB43C"), hot=_hexn(P["hot"], "FFF0FA"))
    tx, ty = (float(v) for v in P["target"])
    reach = float(P["reach"])
    tt = _ts(0, D, 2 * F)
    w = 2 * math.pi / D

    def wave(s, col, fn):
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(col, c.a(fn(t)))) for t in tt]), "linear")

    b = c.bone("door", x=tx, y=ty - 25)
    s = _slot(c, b, "glow", 440, 400)
    c.show([s], 0, None)
    wave(s, C["red"], lambda t: 0.18)
    rng = np.random.default_rng(c.seed - 2)
    for i, (ang, ck, L, a0) in enumerate(FAN):
        rot = 90 - ang
        b = c.bone(f"ray{i}", rot=rot)
        s = _slot(c, b, "wedge", L, L * 0.62, ox=L / 2, role="ray")
        c.show([s], 0, None)
        ph, k = rng.uniform(0, 6.28), int(rng.integers(1, 3))
        _keys(c, b, "rotate", [(t, 4.5 * math.sin(k * w * t + ph)) for t in tt])
        wave(s, C[ck], lambda t, a0=a0, ph=ph: a0 * (0.82 + 0.18 * math.sin(w * t + ph * 1.7)))
    b = c.bone("haze", y=40)
    s = _slot(c, b, "glow", 460, 170)
    c.show([s], 0, None)
    wave(s, C["magenta"], lambda t: 0.38 + 0.06 * math.sin(w * t + 2.0))
    top, bot = ty - 30, -6.0
    b = c.bone("beam", x=tx + 1, y=(top + bot) / 2)
    sg = _slot(c, b, "line_v", 26, top - bot)
    sc = _slot(c, b, "line_v", 5, top - bot)
    b2 = c.bone("beam_up", x=tx + 1, y=(reach + ty) / 2)
    su = _slot(c, b2, "line_v", 3, reach - ty + 30)
    c.show([sg, sc, su], 0, None)
    wave(sc, C["beam"], lambda t: 0.85)
    wave(su, C["beam"], lambda t: 0.25)
    wave(sg, C["color"], lambda t: 0.5 + 0.1 * math.sin(w * t))
    b = c.bone("target", x=tx, y=ty)
    s1 = _slot(c, b, "ring", 2 * float(P["target_radius"]) / 0.8)
    s2 = _slot(c, b, "glow", 110)
    c.show([s1, s2], 0, None)
    wave(s1, C["magenta"], lambda t: 0.45)
    wave(s2, C["magenta"], lambda t: 0.3)
    b = c.bone("hot")
    s1 = _slot(c, b, "glow", 400, 120, oy=-8)
    s2 = _slot(c, b, "streak", 230, 26)
    s3 = _slot(c, b, "glow", 80)
    c.show([s1, s2, s3], 0, None)
    wave(s1, C["gold"], lambda t: 0.3)
    wave(s2, C["magenta"], lambda t: 0.45)
    wave(s3, C["hot"], lambda t: 0.28 + 0.08 * math.sin(w * t + 1.0))
    return c.result(duration=D, loop=D, rays=len(FAN))


# ---------------------------------------------------------------------------------------------------- glyph_strike
def glyph_strike(c: Ctx, P: dict) -> dict:
    D, hitf = 31, 6
    hit = hitf * F
    col = _hexn(P["color"], "FFE430")
    trail, hot, shard, impact, ringc, sec, line = (_hexn(P[k], d) for k, d in (
        ("trail", "FFB030"), ("hot", "FFFBD2"), ("shard", "D8FFA0"), ("impact", "FFC424"), ("ring", "FF7020"),
        ("secondary_glow", "FF4418"), ("line", "FFE47A")))
    p0 = np.array([float(v) for v in P["source"]])          # start, relative to the target (the group origin)
    d = -p0
    ang = math.degrees(math.atan2(d[1], d[0]))
    pos = lambda t: p0 + d * min(1.0, t / hit)                # noqa: E731   constant speed
    rng = np.random.default_rng(c.seed + 4)
    secp = P["secondary"]
    # the secondary target (drawn first: the strike passes over it)
    sec_slots = []
    if secp is not None:
        hc = c.bone("sec", x=float(secp[0]), y=float(secp[1]))
        art = c._art("secondary")
        if art:                                              # the lit picture, revealed bottom-up by a clipping wipe
            ww, hh = float(P["secondary_size"]), float(P["secondary_size"]) * art["size"][1] / art["size"][0]
            wipe = c.bone("sec_wipe", hc, y=-hh / 2 - 6)
            clip = c.sk.unique_name(f"fx_{c.prefix}_sec_clip", "slot")
            c.sk.add_slot(Slot(name=clip, bone=wipe), after=c.last_slot) if c.last_slot else c.sk.add_slot(Slot(name=clip, bone=wipe))
            c.last_slot = clip
            s = c.slot(hc, art["tex"], ww, height=hh, blend=art.get("blend", "normal"), role=None)
            c.sk.set_attachment(clip, "clip", ClippingAttachment(end=s, vertexCount=4,
                                                                 vertices=[-ww, -2 * hh, ww, -2 * hh, ww, 0, -ww, 0]))
            c.ab.slot_attachment(clip, [(0.0, "clip")])
            c.show([s], hit, None)
            _keys(c, wipe, "translate", [(0, 0, 0), (hit, 0, 0), (10 * F, 0, hh + 12)])
            sec_slots += [clip, s]
            c.slots.append(clip)
        s = _slot(c, hc, "ring_soft", 2 * 33 / 0.8)
        c.show([s], 8 * F, 22 * F)
        _fade(c, s, sec, [(8, 0.0), (10, 0.4), (14, 0.3), (18, 0.15), (22, 0.0)])
        for size, cl, kv in ((160, sec, [(7, 0.0), (10, 1.0), (13, 0.85), (16, 0.5), (22, 0.0)]),
                             (56, impact, [(8, 0.0), (10, 0.6), (14, 0.3), (18, 0.0)])):
            s = _slot(c, hc, "glow", size)
            c.show([s], 7 * F, 22 * F)
            _fade(c, s, cl, kv)
    # the light line drawing out of the target (up and down)
    for nm, L, rot in (("line_up", float(P["line_up"]), 0.0), ("line_dn", float(P["line_down"]), 180.0)):
        if L <= 0:
            continue
        b = c.bone(nm, rot=rot)
        for wd, a0 in ((12, 0.45), (3, 1.0)):
            s = _slot(c, b, "line_v", wd, L, oy=L / 2)
            c.show([s], 8 * F, D * F)
            _fade(c, s, line, [(8, a0), (12, a0), (16, a0 * 0.7), (28, a0 * 0.55), (31, 0.0)])
        _keys(c, b, "scale", [(8 * F, 1.0, 0.0), (11 * F, 1.0, 1.0)])
    # the projectile
    head = c.bone("head", x=float(p0[0]), y=float(p0[1]))
    _keys(c, head, "translate", [(t, *(pos(t) - p0)) for t in _ts(0, hit)])
    tb = c.bone("trail", head, rot=ang)
    s = _slot(c, tb, "trail", 220, 130, ox=-110, role="trail")
    s2 = _slot(c, tb, "trail", 140, 16, ox=-70, role="trail")
    s3 = _slot(c, tb, "glow", 240, 96, ox=-90)
    c.show([s, s3], 0, 20 * F)
    c.show([s2], 0, 12 * F)
    _fade(c, s3, trail, [(0, 0.25), (2, 0.5), (6, 0.55), (10, 0.4), (15, 0.2), (20, 0.0)])
    _keys(c, tb, "scale", [(0, 0.35, 0.8), (2 * F, 0.7, 1.0), (hit, 1.0, 1.0), (20 * F, 1.0, 1.25)])
    _fade(c, s, trail, [(0, 0.7), (2, 1.0), (6, 1.0), (10, 0.75), (15, 0.4), (20, 0.0)])
    _fade(c, s2, hot, [(0, 0.3), (3, 0.38), (6, 0.3), (9, 0.1), (12, 0.0)])
    shard_specs = []
    for i in range(int(P["count"])):
        t0 = (1.5 + i * 0.8) * F
        q = pos(t0) + rng.normal(0, 12, 2)
        rot0 = rng.uniform(0, 360)
        size = rng.uniform(20, 30)
        t1 = t0 + rng.uniform(0.35, 0.55)
        nrm = np.array([-d[1], d[0]]) / np.linalg.norm(d) * rng.choice([-1, 1]) * rng.uniform(15, 35)
        spin = rng.uniform(-90, 90)
        shard_specs.append((q, rot0, size, t0, t1, nrm, spin))
    for i, (q, rot0, size, t0, t1, nrm, spin) in enumerate(shard_specs):
        b = c.bone(f"shard{i}", x=float(q[0]), y=float(q[1]), rot=rot0)
        s = _slot(c, b, "shard", size, role="shard")
        c.show([s], t0, t1)
        _keys(c, b, "translate", [(t0, 0, 0), (t1, *(nrm + d / np.linalg.norm(d) * 10))])
        _keys(c, b, "rotate", [(t0, 0), (t1, spin)])
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(shard, c.a(a))) for t, a in ((t0, 0.0), (t0 + 2 * F, 0.65), (t1 - 4 * F, 0.45), (t1, 0.0))]), "linear")
    cb = c.bone("hit")
    for size, cl, kv in ((300, trail, [(6, 0), (7, 0.45), (12, 0.3), (20, 0.0)]),
                         (170, impact, [(6, 0.0), (7, 0.5), (9, 0.5), (11, 0.4), (15, 0.3), (21, 0.0)])):
        s = _slot(c, cb, "glow", size)
        c.show([s], hit, 21 * F)
        _fade(c, s, cl, kv)
    s = _slot(c, head, "star4", 150)
    c.show([s], 0, 10 * F)
    _fade(c, s, col, [(0, 0.45), (2, 0.55), (5, 0.5), (6, 0.25), (9, 0.0)])
    gb = c.bone("glyph", head)
    s = _slot(c, head, "glow", 120)
    c.show([s], 0, 12 * F)
    _fade(c, s, col, [(0, 0.5), (2, 0.7), (6, 0.7), (8, 0.3), (11, 0.0)])
    s = _slot(c, gb, "glyph", 104, role="glyph")
    c.show([s], 0, 22 * F)
    c.ab.slot_color(s, [(c.T(0), hexa(col, c.a(0.9))), (c.T(hit), hexa(col, c.a(1.0))), (c.T(9 * F), hexa(impact, c.a(0.9))),
                        (c.T(14 * F), hexa(ringc, c.a(0.55))), (c.T(21 * F), hexa(ringc, 0.0))], "linear")
    for i, (px, py, f0) in enumerate(P["twinkles"]):
        b = c.bone(f"twinkle{i}", x=float(px), y=float(py))
        s = _slot(c, b, "star4", 30)
        t0 = f0 * F
        c.show([s], t0, t0 + 10 * F)
        _keys(c, b, "scale", [(t0, 0.2, 0.2), (t0 + 3 * F, 1.0, 1.0), (t0 + 10 * F, 0.3, 0.3)])
        _keys(c, b, "rotate", [(t0, 0), (t0 + 10 * F, 40)])
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(hot, c.a(a))) for t, a in ((t0, 0), (t0 + 3 * F, 0.95), (t0 + 10 * F, 0))]), "linear")
    for i in range(12):
        a = i * 30 + rng.uniform(-10, 10)
        L = rng.uniform(55, 95)
        b = c.bone(f"hit_ray{i}", cb, rot=a)
        s = _slot(c, b, "ray", L, 12, ox=L / 2)
        c.show([s], hit, 13 * F)
        _keys(c, b, "scale", [(hit, 0.6, 1.0), (13 * F, 1.3, 1.0)])
        _fade(c, s, hot, [(6, 0.0), (7, 0.25), (9, 0.18), (12, 0.0)])
    b = c.bone("hit_ring", cb)
    s = _slot(c, b, "ring_soft", 2 * 44 / 0.8)
    c.show([s], 9 * F, 23 * F)
    _keys(c, b, "scale", [(9 * F, 0.95, 0.95), (23 * F, 1.12, 1.12)])
    _fade(c, s, ringc, [(9, 0.0), (11, 0.7), (15, 0.4), (22, 0.0)])
    c.ab.event(c.T(hit), "fx_glyph_strike_hit")
    return c.result(duration=D * F * c.k, hit=c.T(hit), secondary=sec_slots or None)


# ---------------------------------------------------------------------------------------------------- banner_energy
def banner_energy(c: Ctx, P: dict) -> dict:
    D = 54
    gold = _hexn(P["color"], "FFD23C")
    hot, rest, green, green_hot, coin = (_hexn(P[k], d) for k, d in (
        ("hot", "FFF6C8"), ("rest", "FFA810"), ("green", "5CFF2A"), ("green_hot", "E8FFB0"), ("coin", "FFC844")))
    rng_b = np.random.default_rng(c.seed)
    for w, h, cl, kv in ((720, 300, gold, [(2, 0), (3, 0.85), (5, 1.0), (8, 0.85), (14, 0.55), (20, 0.3), (30, 0.15), (42, 0.0)]),
                         (320, 110, hot, [(2, 0), (3, 0.6), (6, 0.5), (12, 0.2), (18, 0.0)])):
        s = _slot(c, c.group, "glow", w, h)
        c.show([s], 2 * F, 43 * F)
        _fade(c, s, cl, kv)
    s = _slot(c, c.group, "glow_flat", 760, 190)
    c.show([s], 2 * F, None)
    _fade(c, s, rest, [(2, 0.0), (4, 0.6), (8, 0.9), (54, 0.9)])
    for j in range(12):
        side = 0 if j % 2 == 0 else 180
        a = side + rng_b.uniform(-50, 50)
        x = (-1 if side else 1) * rng_b.uniform(30, 110)
        L = rng_b.uniform(90, 150)
        wd = rng_b.uniform(18, 30)
        b = c.bone(f"burst{j}", x=x, rot=a)
        s = _slot(c, b, "ray", L, wd, ox=L / 2)
        c.show([s], F, 9 * F)
        _keys(c, b, "scale", [(F, 0.6, 1.0), (9 * F, 1.8, 0.7)])
        _fade(c, s, green, [(1, 0.0), (2, 0.7), (3, 1.0), (5, 0.8), (9, 0.0)])
    rng = np.random.default_rng(c.seed + 24)
    # the slashes, haze bands, coins and glints are drawn in two passes so the draw order matches: slashes 0-3 of
    # each side under the bar flare, the rest over it
    slashes, hazes, coins = [], [], []
    k = 0
    for side in (-1, 1):
        for j in range(8):
            t0 = (2 + j * 1.3 + rng.uniform(-0.5, 0.5)) * F
            life = rng.uniform(6, 9) * F
            x0 = side * (rng.uniform(0, 70) if j < 3 else rng.uniform(40, 150))
            vx = side * rng.uniform(800, 1050)
            y0 = rng.uniform(-22, 26)
            rot = 58 + rng.uniform(-6, 6)
            Lh = rng.uniform(120, 170)
            slashes.append(dict(k=k, j=j, t0=t0, life=life, x0=x0, vx=vx, y0=y0, rot=rot, L=Lh))
            k += 1
        for j in range(2):
            hazes.append(dict(k=k, side=side, t0=(11 + j * 4) * F, x0=side * rng.uniform(120, 260)))
            k += 1
    for side, (sx, sy) in zip((-1, 1), P["sources"]):
        for j in range(6):
            t0 = (10 + j * 3 + rng.uniform(0, 2)) * F
            life = rng.uniform(0.45, 0.75)
            vx = -side * rng.uniform(20, 110)
            vy = rng.uniform(170, 280)
            x = float(sx) + rng.uniform(-14, 14)
            size = rng.uniform(9, 13)
            coins.append(dict(t0=t0, life=life, vx=vx, vy=vy, x=x, y=float(sy), size=size))
    glints = []
    for j in range(10):
        t0 = (4 + rng.uniform(0, 24)) * F
        glints.append(dict(t0=t0, x=rng.uniform(-330, 330), y=rng.uniform(-38, 46), size=rng.uniform(16, 26)))

    def slash(sp):
        b = c.bone(f"slash{sp['k']}", x=sp["x0"], y=sp["y0"], rot=sp["rot"])
        t0, life = sp["t0"], sp["life"]
        for wd, cl, a0 in ((44, green, 0.55), (12, green_hot, 0.95)):
            s = _slot(c, b, "streak", sp["L"], wd, role="slash")
            c.show([s], t0, t0 + life)
            c.ab.slot_color(s, _uniq([(c.T(t), hexa(cl, c.a(a))) for t, a in
                                      ((t0, 0), (t0 + 2 * F, a0), (t0 + life * 0.6, a0 * 0.7), (t0 + life, 0))]), "linear")
        _keys(c, b, "translate", [(t, sp["vx"] * (t - t0) * (1 - 0.35 * (t - t0) / life), 0.0) for t in _ts(t0, t0 + life)])

    for sp in slashes:
        if sp["j"] < 4:
            slash(sp)
    bx, by = (float(v) for v in P["bar"])
    b = c.bone("bar", x=bx, y=by)
    for h, cl, a0 in ((34, gold, 0.85), (8, hot, 0.9)):
        s = _slot(c, b, "streak", float(P["bar_width"]), h)
        c.show([s], 3 * F, 21 * F)
        _fade(c, s, cl, [(3, 0), (4, 1.0), (8, 0.7), (14, 0.35), (20, 0.0)], a0)
    hz = {h["k"]: h for h in hazes}
    for kk in range(k):
        sp = next((s_ for s_ in slashes if s_["k"] == kk), None)
        if sp is not None and sp["j"] >= 4:
            slash(sp)
        if kk in hz:
            h = hz[kk]
            b = c.bone(f"haze{kk}", x=h["x0"], rot=60)
            s = _slot(c, b, "streak", 200, 90)
            c.show([s], h["t0"], h["t0"] + 12 * F)
            _keys(c, b, "translate", [(h["t0"], 0, 0), (h["t0"] + 12 * F, h["side"] * 90, 0)])
            c.ab.slot_color(s, _uniq([(c.T(t), hexa(green, c.a(a))) for t, a in ((h["t0"], 0), (h["t0"] + 3 * F, 0.38), (h["t0"] + 12 * F, 0))]), "linear")
    for i, cn in enumerate(coins):
        b = c.bone(f"coin{i}", x=cn["x"], y=cn["y"])
        s = _slot(c, b, "dot", cn["size"], role="coin")
        t0 = cn["t0"]
        t1 = min(D * F, t0 + cn["life"])
        c.show([s], t0, t1)
        _keys(c, b, "translate", [(t, cn["vx"] * (t - t0), cn["vy"] * (t - t0) - 450 * (t - t0) ** 2) for t in _ts(t0, t1, 2 * F)])
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(coin, c.a(a))) for t, a in ((t0, 0), (t0 + 2 * F, 1), (t1 - 4 * F, 0.9), (t1, 0))]), "linear")
    for i, gl in enumerate(glints):
        b = c.bone(f"glint{i}", x=gl["x"], y=gl["y"])
        s = _slot(c, b, "star4", gl["size"])
        t0 = gl["t0"]
        c.show([s], t0, t0 + 9 * F)
        _keys(c, b, "scale", [(t0, 0.2, 0.2), (t0 + 3 * F, 1.0, 1.0), (t0 + 9 * F, 0.2, 0.2)])
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(hot, c.a(a))) for t, a in ((t0, 0), (t0 + 3 * F, 0.9), (t0 + 9 * F, 0))]), "linear")
    return c.result(duration=D * F * c.k, slashes=len(slashes), coins=len(coins))


# ---------------------------------------------------------------------------------------------------- ember_drift
def ember_drift(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    col = _hexn(P["color"], "FFB840")
    W, H = (float(v) for v in P["area"])
    rng = np.random.default_rng(c.seed + 34)
    n = int(P["count"])
    for i in range(n):
        x0 = rng.uniform(-W / 2, W / 2)
        y0 = -rng.uniform(-H / 2, H / 2)
        b = c.bone(f"e{i}", x=x0, y=y0)
        s = _slot(c, b, "dot", rng.uniform(5, 8), role="ember")
        c.show([s], 0, None)
        ph = rng.uniform(0, 1)
        vx, vy = rng.uniform(-14, 14), rng.uniform(8, 26)
        tt = _ts(0, D, 4 * F)

        def life(t, ph=ph):
            return ((t / D) + ph) % 1.0
        _keys(c, b, "translate", [(t, vx * D * (life(t) - 0.5), vy * D * (life(t) - 0.5)) for t in tt])
        c.ab.slot_color(s, _uniq([(c.T(t), hexa(col, c.a(0.8 * math.sin(math.pi * life(t)) ** 1.5))) for t in tt]), "linear")
    return c.result(duration=D, loop=D, embers=n)


RECIPES.update({
    "rim_glow_pulse": dict(
        fn=rim_glow_pulse, duration=29 * F, kind="one-shot", color="FF6A14", normal_blend=True,
        summary="A press on a round button: the rim turns white-hot, an orange wash covers the inner band (normal blend), a "
                "halo spreads and 2 faint shock rings leave, pulsing over ~0.97 s. The wavy fire ripple is After Effects "
                "(template ripple_glow look=line origin=rim, see ae_hint; options.ripple_frames imports the render, tintable).",
        anchor="The button centre (at scale 1 the rim radius is ~92 units).",
        options=dict(hot=("FFD84A", "rim colour"), wash=("FF8A30", "inner-band wash colour (normal blend)"),
                     deep=("A82006", "dark colour of the AE ripple's two-colour tint"),
                     ripple_frames=("", "folder of the rendered ripple_glow frames (imported tintable, looped)"),
                     frames_fps=(30.0, "fps of the rendered AE frames"))),
    "anamorphic_burst": dict(
        fn=anamorphic_burst, duration=48 * F, kind="one-shot", color="FFB42E", count=16,
        summary="Spin-start flare on a button: a rim bloom, a wide bloom, a fan of thin rays, 2 tilted anamorphic streaks "
                "(white-cyan over warm), a blue light on the top rim and drifting sparks (count). The flame wisps are the "
                "AE template flame_wisps (ae_hint; options.wisps_frames plays one grey frame set as orange, mirrored "
                "orange, violet and pink copies).",
        anchor="The button centre.",
        options=dict(bloom=("FFD028", "rim bloom"), hot=("FFF2B8", "hot core"), ray=("FFE6F2", "rays and the pink bloom tail"),
                     core=("D8F6FF", "the core streak"), blue=("5AB4FF", "the light on the top rim"),
                     spark=("FFD070", "sparks"), dark=("A02A08", "dark of the orange wisps' tint"),
                     violet=("C68CFF", "violet wisps"), violet_dark=("3A10A0", "dark of the violet and pink wisps"),
                     pink=("FF8CD2", "pink wisps"), rays=(26, "number of rays"), tilt=(12.0, "streak angle, degrees"),
                     wisps_frames=("", "folder of the rendered flame_wisps frames"),
                     frames_fps=(30.0, "fps of the rendered AE frames"))),
    "ray_fan_beam": dict(
        fn=ray_fan_beam, duration=84 * F, kind="loop", color="9C78FF",
        summary="Looping win light from the top of an arch: 10 soft wedges sway and breathe on whole cycles (color in the "
                "centre, red, magenta outside), a haze, a light column up to a target with a ring on it, a hot spot with a "
                "flat flare, a gold glow on the arch and warm light on the area behind.",
        anchor="The light source (top of the arch); the target is relative to it.",
        options=dict(magenta=("F050E0", "outer wedges, haze, target ring"), red=("FF4A62", "middle wedges, back light"),
                     beam=("ECD2FF", "column core"), gold=("FFB43C", "glow along the arch"), hot=("FFF0FA", "hot spot"),
                     target=([-2.0, 92.0], "the column's target (a coin) relative to the source"),
                     target_radius=(37.0, "radius of the ring on the target"),
                     reach=(200.0, "how high the faint column continues above the source"))),
    "glyph_strike": dict(
        fn=glyph_strike, duration=31 * F, kind="one-shot", color="FFE430", count=5,
        summary="A glowing glyph flies straight into a target in 6 frames with a comet trail, a light band, prism shards "
                "(count) and twinkles; impact flash, burst rays, an orange ring, the glyph cooling on the target, a light "
                "line drawing out through it; a secondary target lights up (its lit picture revealed bottom-up when given "
                "as art=secondary). Event fx_glyph_strike_hit.",
        anchor="The target (where it lands); source / secondary / twinkles are relative to it.",
        options=dict(trail=("FFB030", "trail and back light"), hot=("FFFBD2", "trail core, twinkles, burst rays"),
                     shard=("D8FFA0", "prism shards"), impact=("FFC424", "impact flash, cooling glyph"),
                     ring=("FF7020", "impact ring, cooled glyph"), secondary_glow=("FF4418", "secondary target glow"),
                     line=("FFE47A", "the light line through the target"),
                     source=([-168.0, 166.0], "start point relative to the target"),
                     secondary=([-178.0, -7.0], "secondary target relative to the target (None = none)"),
                     secondary_size=(66.0, "width of the secondary picture (art=secondary)"),
                     line_up=(76.0, "length of the line above the target (0 = none)"),
                     line_down=(114.0, "length of the line below the target (0 = none)"),
                     twinkles=([[-110.0, 142.0, 3], [-44.0, 122.0, 4], [12.0, 22.0, 6], [-140.0, 108.0, 5]],
                               "[x, y, frame] twinkles along the path"))),
    "banner_energy": dict(
        fn=banner_energy, duration=54 * F, kind="one-shot", color="FFD23C",
        summary="A win banner landing: green burst spikes out of the text, green slashes racing outward on both sides, "
                "green haze bands, a gold bloom, a flare along the top bar, coins popping from 2 sources, glints, and a "
                "resting gold light that rises and stays (the banner's lit state).",
        anchor="The banner text centre.",
        options=dict(hot=("FFF6C8", "hot bloom, bar core, glints"), rest=("FFA810", "the resting light"),
                     green=("5CFF2A", "energy spikes, slashes, haze"), green_hot=("E8FFB0", "slash cores"),
                     coin=("FFC844", "coins"), bar=([-21.0, 38.0], "top bar flare centre"),
                     bar_width=(940.0, "top bar flare length"),
                     sources=([[-371.0, 30.0], [357.0, 26.0]], "[left, right] coin sources (the sacks)"))),
    "ember_drift": dict(
        fn=ember_drift, duration=4.0, kind="loop", color="FFB840", count=10,
        summary="Seamless loop of embers drifting up and to the sides over an area, each fading in and out once per loop.",
        anchor="The centre of the area.",
        options=dict(area=([380.0, 220.0], "[width, height] of the area"))),
})
ROLES.update({
    "rim_glow_pulse": {"halo": "the outer halo (a ring of light outside the rim, hollow inside)",
                       "ring": "a thin ring (the rim and the shock rings)",
                       "wash": "the inner-band wash, NORMAL blend (a soft annulus)"},
    "anamorphic_burst": {"ray": "a thin ray, source at the LEFT edge", "streak": "an anamorphic streak, horizontal, centred"},
    "ray_fan_beam": {"ray": "a soft wedge, source at the LEFT edge, widening to the right"},
    "glyph_strike": {"glyph": "the flying glyph / rune (white or coloured, centred)", "trail": "comet trail, head at the RIGHT edge",
                     "shard": "a small shard", "secondary": "the secondary target's LIT picture, revealed bottom-up (normal blend)"},
    "banner_energy": {"slash": "an energy streak, horizontal, centred", "coin": "a coin / sparkle dot"},
    "ember_drift": {"ember": "one ember dot"},
})
for _n in ("rim_glow_pulse", "anamorphic_burst", "ray_fan_beam", "glyph_strike", "banner_energy", "ember_drift"):
    RECIPES[_n]["roles"] = ROLES[_n]
