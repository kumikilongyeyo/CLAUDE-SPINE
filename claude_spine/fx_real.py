"""Realistic layers for ``fx_recipe``: what the procedural recipes could not draw, ported from the job that made the
FX "look real" (coin-fx-test/fx_layers.py: bolt_link, crackle, face_heat).

    bolt_link     real lightning between point PAIRS: a bolt picture stretched from A to B on one aimed bone,
                  re-striking every `rate` s with another picture, a random mirror and a flicker; flares at the ends
    crackle       electricity (or flames) flickering at points around a shape: each point swaps to a random picture,
                  a random turn and a random brightness every `rate` s, and is dark part of the time
    surface_glow  an additive copy of one of YOUR slots, on its bone, drawn right after it, that follows its attachment
                  keys (it hides when the face swaps away) and glows with keyed colour / alpha: red-hot metal, an icy
                  sheen, a charge-up; `pair` does a second slot (the back face) at the same time

They come alive with ``kit="realistic"`` (the real-lightning sprites of the Kenney Particle Pack: bolts for bolt_link,
crackles for crackle, real flames for crackle kind=fire, lens flares at the bolt ends). Without the kit they draw
their own jagged bolts, crackles and flame tongues in code, so they work anywhere.

Keys are stepped (a strike is one frame of light, not a fade), every strike comes from one seeded random stream
(``seed`` re-rolls it), and the window ramps in and out over ``ramp`` s. ``loop=true`` drops the ramp, strikes at 0
and repeats the first strike's key at the end, so the cycle closes exactly.

Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw

from .fx import _rgba
from .fx_pinata import _finish
from .fx_props_elements import tex_flame_tongue
from .fx_recipes import RECIPES, ROLES, Ctx, _blur, _grid, _hexn, _uniq, hexa
from .ir import RegionAttachment, Slot

W_BOLT = 512.0                 # a bolt picture's length in design units: the link bone's scaleX = distance / W_BOLT
BOLT_ROLES = ("bolt", "bolt_2", "bolt_3")
SPARK_ROLES = ("spark_1", "spark_2", "spark_3", "spark_4")
FLAME_ROLES = ("flame_1", "flame_2", "flame_3", "flame_4")
POINTS = [[-170.0, -40.0], [-40.0, 50.0], [80.0, -30.0], [180.0, 40.0]]
HOT = [[0.0, "FF3A10", 0.0], [0.6, "FF5A18", 0.3], [1.3, "FFB060", 0.7], [1.7, "FFF0C8", 0.95], [2.2, "FF7A20", 0.0]]


# ====================================================================== procedural pictures (no kit)
def _jag(rng, p0, p1, depth: int, amp: float) -> list[tuple[float, float]]:
    """Midpoint displacement: a lightning-like polyline p0 -> p1."""
    pts = [p0, p1]
    for _ in range(depth):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
            nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
            off = float(rng.normal(0, amp * L))
            out += [((a[0] + b[0]) / 2 + nx * off, (a[1] + b[1]) / 2 + ny * off), b]
        pts = out
    return pts


def _glow_lines(size: tuple[int, int], lines, widths, S: int = 2) -> np.ndarray:
    """Polylines drawn at S x, a hot core and two blurred halos, back to size; alpha 0..1."""
    w, h = size
    im = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(im)
    for pts, wd in zip(lines, widths):
        d.line([(x * S, y * S) for x, y in pts], fill=255, width=max(1, int(wd * S)), joint="curve")
    base = np.asarray(im, np.float32) / 255
    a = np.clip(_blur(base, 0.8 * S) * 1.2 + _blur(base, 4 * S) * 0.7 + _blur(base, 10 * S) * 0.35, 0, 1)
    return np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((w, h), Image.LANCZOS), np.float32) / 255


def tex_bolt(seed: int = 0, w: int = 512, h: int = 128) -> Image.Image:
    """A horizontal lightning bolt, left edge to right edge (the link stretches it from A to B), one or two forks."""
    rng = np.random.default_rng(seed + 11)
    main = _jag(rng, (6.0, h / 2), (w - 6.0, h / 2 + float(rng.uniform(-6, 6))), 6, 0.16)
    main = [(x, float(np.clip(y, 10, h - 10))) for x, y in main]
    lines, widths = [main], [3.2]
    for _ in range(int(rng.integers(1, 3))):
        k = int(rng.integers(len(main) // 5, len(main) * 3 // 4))
        x0, y0 = main[k]
        tip = (x0 + float(rng.uniform(40, 110)), float(np.clip(y0 + rng.choice([-1, 1]) * rng.uniform(22, 44), 8, h - 8)))
        lines.append([(x, float(np.clip(y, 8, h - 8))) for x, y in _jag(rng, (x0, y0), tip, 4, 0.2)])
        widths.append(1.6)
    a = _glow_lines((w, h), lines, widths)
    a *= np.clip(np.minimum(np.arange(w)[None, :], w - 1 - np.arange(w)[None, :]) / 6.0, 0, 1)
    a *= np.clip(np.minimum(np.arange(h)[:, None], h - 1 - np.arange(h)[:, None]) / 6.0, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_crackle(seed: int = 0, n: int = 256) -> Image.Image:
    """A small burst of electricity: three or four jagged arcs flicking out of one spot, a fork or two."""
    rng = np.random.default_rng(seed + 23)
    c = n / 2
    lines, widths = [], []
    for k in range(int(rng.integers(3, 5))):
        ang = float(rng.uniform(0, 2 * math.pi))
        ln = float(rng.uniform(0.45, 0.8)) * c
        p0 = (c + math.cos(ang) * ln * 0.15, c + math.sin(ang) * ln * 0.15)
        p1 = (c + math.cos(ang) * ln, c + math.sin(ang) * ln)
        arc = _jag(rng, p0, p1, 4, 0.22)
        lines.append(arc)
        widths.append(2.4 if k < 2 else 1.6)
        if rng.random() < 0.6:
            q = arc[int(rng.integers(1, len(arc) - 1))]
            a2 = ang + float(rng.choice([-1, 1]) * rng.uniform(0.4, 0.9))
            lines.append(_jag(rng, q, (q[0] + math.cos(a2) * ln * 0.4, q[1] + math.sin(a2) * ln * 0.4), 3, 0.25))
            widths.append(1.2)
    a = _glow_lines((n, n), lines, widths)
    x, y = _grid(n)
    a *= np.clip((1 - np.hypot(x, y)) / 0.12, 0, 1)
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))


def tex_soft_disc(n: int = 256) -> Image.Image:
    """The stand-in for surface_glow without a slot: a round face with a soft rim."""
    x, y = _grid(n)
    r = np.hypot(x, y)
    a = np.clip((0.92 - r) / 0.12, 0, 1) * (0.75 + 0.25 * (1 - r))
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))


_FLAME_SIZES = ((96, 192), (84, 200), (108, 180), (90, 168))
PROC: dict[str, tuple[str, Callable[[], Image.Image]]] = {
    **{r: (f"fx/real_bolt_{i}", (lambda i=i: tex_bolt(i))) for i, r in enumerate(BOLT_ROLES)},
    **{r: (f"fx/real_crackle_{i}", (lambda i=i: tex_crackle(i))) for i, r in enumerate(SPARK_ROLES)},
    **{r: (f"fx/real_flame_{i}", (lambda i=i: tex_flame_tongue(*_FLAME_SIZES[i]))) for i, r in enumerate(FLAME_ROLES)},
}


# ====================================================================== helpers
def _region(c: Ctx, role: str, width: float, anchor: str = "center") -> RegionAttachment:
    """One attachment for `role`: the caller's / kit picture (its own aspect, the given width x its scale) or the
    procedural one; anchor left = starts at the bone (a bolt), bottom = stands on it (a flame)."""
    art = c._art(role)
    if art:
        tex, width = art["tex"], width * float(art.get("scale", 1.0))
        h = width * art["size"][1] / art["size"][0]
        anchor = art.get("anchor", anchor)
    else:
        tex, make = PROC[role]
        tw, th = c.tex(tex, make)
        h = width * th / tw
    ox = {"left": width / 2, "right": -width / 2}.get(anchor, 0.0)
    oy = {"bottom": h / 2, "top": -h / 2}.get(anchor, 0.0)
    return RegionAttachment(path=tex, x=round(ox, 2), y=round(oy, 2), width=round(width, 2), height=round(h, 2))


def _multi_slot(c: Ctx, bone: str, roles, width: float, anchor: str = "center") -> tuple[str, list[str]]:
    """A slot holding one attachment per role (fx, fx2, ...): a strike swaps between them."""
    first = _region(c, roles[0], width, anchor)
    nm = c.slot(bone, first.path, first.width, height=first.height, ox=first.x, oy=first.y,
                make=PROC.get(roles[0], (None, None))[1], blend=_blend(c, roles[0]))
    names = ["fx"]
    for k, role in enumerate(roles[1:], start=2):
        c.sk.set_attachment(nm, f"fx{k}", _region(c, role, width, anchor))
        names.append(f"fx{k}")
    return nm, names


def _blend(c: Ctx, role: str) -> str:
    art = c._art(role)
    return art.get("blend", "additive") if art else "additive"


def _strikes(rng, D: float, rate: float, loop: bool) -> list[float]:
    """Strike times in [0, D): a loop strikes at 0 (its first key is repeated at D); a window starts within one rate."""
    t = 0.0 if loop else float(rng.uniform(0, rate))
    out = []
    end = D - 0.3 * rate if loop else D
    while t < end - 1e-6:
        out.append(t)
        t += rate * float(rng.uniform(0.7, 1.4))
    return out or [0.0]


def _env(u: float, D: float, ramp: float, loop: bool) -> float:
    if loop or ramp <= 0:
        return 1.0
    return max(0.0, min(1.0, u / ramp, (D - u) / max(min(ramp, 0.15), 1e-3)))


def _key_strikes(c: Ctx, slot: str, bone: str, names: list[str], ts: list[float], D: float, rng, on: float,
                 col: str, alpha: float, ramp: float, loop: bool, rot: float = 0.0, flip: bool = False,
                 stretch: tuple[float, float] | None = None) -> int:
    """Stepped attachment / colour / turn / scale keys: one strike per time, lit with chance `on`."""
    att, colk, rk, sk = [], [], [], []
    lit_n = 0
    for u in ts:
        lit = bool(rng.random() < on)
        lit_n += lit
        att.append((c.T(u), names[int(rng.integers(len(names)))] if lit else None))
        colk.append((c.T(u), hexa(col, c.a(alpha * _env(u, D, ramp, loop) * float(rng.uniform(0.55, 1.0)))), "stepped"))
        if rot:
            rk.append((c.T(u), float(rng.uniform(-rot, rot)), "stepped"))
        if flip or stretch:
            sy = (float(rng.choice([-1.0, 1.0])) if flip else 1.0) * (float(rng.uniform(*stretch)) if stretch else 1.0)
            sk.append((c.T(u), 1.0, sy, "stepped"))
    if loop:                                   # the end repeats the start: the cycle closes exactly
        att.append((c.T(D), att[0][1]))
        colk.append((c.T(D), colk[0][1], "stepped"))
        if rk:
            rk.append((c.T(D), rk[0][1], "stepped"))
        if sk:
            sk.append((c.T(D), *sk[0][1:3], "stepped"))
    else:
        att.append((c.T(D), None))
        colk.append((c.T(D), hexa(col, 0.0), "stepped"))
    if c.T(0) > 0 or (att and att[0][0] > 0):
        att.insert(0, (0.0, None))
    c.ab.slot_attachment(slot, _uniq(att))
    c.ab.slot_color(slot, _uniq(colk), "stepped")
    if rk:
        c.ab.bone(bone, "rotate", _uniq(rk), "stepped")
    if sk:
        c.ab.bone(bone, "scale", _uniq(sk), "stepped")
    return lit_n


def _pairs(P: dict, n: int) -> list[tuple[int, int]]:
    links = P["links"]
    if links is None:
        return [(i, i + 1) for i in range(n - 1)]
    out = []
    for lk in links:
        i, j = int(lk[0]), int(lk[1])
        if not (0 <= i < n and 0 <= j < n) or i == j:
            raise ValueError(f"link {list(lk)} must join two different points of 0..{n - 1}")
        out.append((i, j))
    if not out:
        raise ValueError("links is empty")
    return out


# ====================================================================== bolt_link
def bolt_link(c: Ctx, P: dict) -> dict:
    """Real lightning between point PAIRS. Each link is one bone at A aimed at B (rotation atan2, scaleX = distance
    / picture length) whose slot holds the bolt pictures; every `rate` s a strike shows one of them (or none, 1 - on of
    the time) with a random mirror and brightness. Short links are drawn thinner (sqrt of length / 512)."""
    D = float(P["duration"])
    pts = [(float(p[0]), float(p[1])) for p in P["points"]]
    if len(pts) < 2:
        raise ValueError("points needs at least two [x, y] points")
    links = _pairs(P, len(pts))
    rate, on, thick, ramp, loop = float(P["rate"]), float(P["on"]), float(P["thick"]), float(P["ramp"]), bool(P["loop"])
    if rate <= 0:
        raise ValueError("rate must be > 0")
    col = _hexn(P["color"], "CFEFFF")
    rng = np.random.default_rng(c.seed + 313)
    built, strikes = [], 0
    for li, (i, j) in enumerate(links):
        (ax, ay), (bx, by) = pts[i], pts[j]
        dist = math.hypot(bx - ax, by - ay)
        if dist < 1.0:
            raise ValueError(f"link {li} joins two points at the same place")
        sy = thick * math.sqrt(max(0.5, min(1.0, dist / W_BOLT)))
        b = c.bone(f"l{li}", x=ax, y=ay, rot=math.degrees(math.atan2(by - ay, bx - ax)), sx=dist / W_BOLT, sy=sy)
        s, names = _multi_slot(c, b, BOLT_ROLES, W_BOLT, anchor="left")
        built.append(dict(link=[i, j], bone=b, slot=s, length=round(dist, 2)))
        strikes += _key_strikes(c, s, b, names, _strikes(rng, D, rate, loop), D, rng, on, col, 1.0, ramp, loop,
                                flip=True, stretch=(0.85, 1.15))
    flares = []
    if P["ends"]:
        size = float(P["flare"]) * thick
        for i in sorted({k for lk in links for k in lk}):
            b = c.bone(f"end{i}", x=pts[i][0], y=pts[i][1])
            s = c.slot(b, "fx/glow", size, role="glow_core")
            _key_strikes(c, s, b, ["fx"], _strikes(rng, D, rate, loop), D, rng, min(1.0, on + 0.15), col, 0.85,
                         ramp, loop)
            flares.append(s)
    return _finish(c, {}, duration=D, loop=D if loop else None, links=built, strikes=strikes, end_flares=flares)


# ====================================================================== crackle
def _ring(n: int, radius: float, kind: str) -> list[tuple[float, float, float]]:
    out = []
    for i in range(n):
        a = 90.0 + 360.0 * i / n
        # electric: along the rim (tangent); fire: the flame's up points away from the centre
        rot = a + 90.0 if kind == "electric" else a - 90.0
        out.append((radius * math.cos(math.radians(a)), radius * math.sin(math.radians(a)), rot))
    return out


def crackle(c: Ctx, P: dict) -> dict:
    """Electricity or flames flickering at points round a shape: each point's slot holds four pictures; every `rate` s
    it shows one (or nothing), turned by up to `spin` degrees, at a random brightness; flames also stretch."""
    kind = str(P["kind"]).lower()
    if kind not in ("electric", "fire"):
        raise ValueError("kind must be electric or fire")
    D = float(P["duration"])
    fire = kind == "fire"
    rate = float(P["rate"] if P["rate"] is not None else (0.08 if fire else 0.055))
    on = float(P["on"] if P["on"] is not None else (0.85 if fire else 0.6))
    size = float(P["size"] if P["size"] is not None else (70.0 if fire else 150.0))
    if rate <= 0:
        raise ValueError("rate must be > 0")
    n = max(1, int(P["count"]))
    if P["points"]:
        pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else (0.0 if fire else float(k * 137 % 360)))
               for k, p in enumerate(P["points"])]
    else:
        pts = _ring(n, float(P["radius"]), kind)
    col = _hexn(P["color"], "FFA040" if fire else "9FE0FF")
    roles = FLAME_ROLES if fire else SPARK_ROLES
    rng = np.random.default_rng(c.seed + 421)
    ramp, loop = float(P["ramp"]), bool(P["loop"])
    made, lit = [], 0
    for k, (x, y, rot) in enumerate(pts):
        b = c.bone(f"p{k}", x=x, y=y, rot=rot)
        s, names = _multi_slot(c, b, roles, size, anchor="bottom" if fire else "center")
        made.append(s)
        lit += _key_strikes(c, s, b, names, _strikes(rng, D, rate, loop), D, rng, on, col, float(P["alpha"]), ramp,
                            loop, rot=float(P["spin"]), flip=not fire, stretch=(0.8, 1.2) if fire else None)
    return _finish(c, {}, duration=D, loop=D if loop else None, points=len(pts), kind=kind, strikes_lit=lit)


# ====================================================================== surface_glow
def _parse_keys(keys) -> list[tuple[float, str, float]]:
    out = []
    for k in keys or []:
        if len(k) != 3:
            raise ValueError(f"keys entries are [t, 'RRGGBB', alpha]; got {k}")
        out.append((float(k[0]), _hexn(str(k[1]), "FFFFFF"), float(k[2])))
    if not out:
        raise ValueError("keys needs at least one [t, 'RRGGBB', alpha]")
    return sorted(out, key=lambda q: q[0])


def _copy_slot(c: Ctx, src: str, follow: bool = True) -> str:
    """An additive twin of `src`: same bone, right after it in draw order, every attachment of it (all skins),
    following its attachment (and deform / sequence) keys in the target animation."""
    sk = c.sk
    if not sk.has_slot(src):
        raise ValueError(f"no slot {src!r} to glow")
    sl = sk.slot(src)
    nm = sk.unique_name(f"fx_{c.prefix}_{src}", "slot")
    sk.add_slot(Slot(name=nm, bone=sl.bone, color="FFFFFF00", blend="additive"), after=src)
    n_att = 0
    for skin in sk.skins:
        for an, att in skin.attachments.get(src, {}).items():
            cp = att.model_copy(deep=True)
            if getattr(cp, "path", None) is None and cp.type in ("region", "mesh", "linkedmesh"):
                cp.path = an                     # the twin's own name must still find the source picture
            skin.attachments.setdefault(nm, {})[an] = cp
            n_att += 1
    if not n_att:
        raise ValueError(f"slot {src!r} has no attachment to glow")
    a = c.ab.a
    src_keys = [k for k in a.slots.get(src, {}).get("attachment", [])]
    if follow and src_keys:
        pts = [(k.time, getattr(k, "name", None)) for k in src_keys]
        if pts[0][0] > 0:
            pts.insert(0, (0.0, sl.attachment))
    else:
        pts = [(0.0, sl.attachment)]
    if all(n is None for _, n in pts):
        raise ValueError(f"slot {src!r} shows no attachment in {c.anim!r} (nothing to glow)")
    c.ab.slot_attachment(nm, pts)
    for skin_name, per in list(a.attachments.items()):
        if src in per:
            a.attachments.setdefault(skin_name, {})[nm] = {k: {tl: [kk.model_copy(deep=True) for kk in ks]
                                                               for tl, ks in v.items()} for k, v in per[src].items()}
    c.slots.append(nm)
    c.depth[nm] = "subject"
    return nm


def surface_glow(c: Ctx, P: dict) -> dict:
    """The subject's own picture glowing: an additive copy of `slot` (and `pair`) keyed through colour / alpha."""
    keys = _parse_keys(P["keys"])
    targets = [s for s in (P["slot"], P["pair"]) if s]
    if P["pair"] and not P["slot"]:
        raise ValueError("pair needs slot (the front face) as well")
    made = []
    if targets:
        made = [_copy_slot(c, s, bool(P["follow"])) for s in targets]
    else:                                    # no slot of yours: a stand-in disc so the recipe still shows something
        b = c.bone("disc")
        s = c.slot(b, "fx/real_disc", float(P["size"]), make=tex_soft_disc, role="disc")
        end = max(float(P["duration"]), keys[-1][0])
        c.show([s], 0, end)
        made = [s]
    pts = [(c.T(t), hexa(rgb, c.a(al))) for t, rgb, al in keys]
    for s in made:
        c.ab.slot_color(s, _uniq(pts), "linear")
    return _finish(c, {}, duration=max(float(P["duration"]), keys[-1][0]), glow_slots=made,
                   follows=list(targets) if P["follow"] else [], peak_at=c.T(max(keys, key=lambda q: q[2])[0]))


# ====================================================================== registry
NAMES = ("bolt_link", "crackle", "surface_glow")
RECIPES.update({
    "bolt_link": dict(
        fn=bolt_link, duration=1.5, kind="window", color="CFEFFF",
        summary="Real lightning between point PAIRS (coins, terminals, horns, symbols): each link is one bone at A aimed "
                "at B whose bolt picture is stretched to the distance; every `rate` s it re-strikes with another bolt, a "
                "random mirror and flicker, dark 1 - on of the time; flares flicker at the ends. With kit=\"realistic\" the "
                "bolts are the Kenney real-lightning sprites; without, it draws its own jagged forked bolts.",
        anchor="Origin of the points (x, y place the whole set).",
        options=dict(points=(POINTS, "[[x, y], ...] the terminals"),
                     links=(None, "[[i, j], ...] which points to join (default: a chain 0-1, 1-2, ...)"),
                     rate=(0.06, "seconds between strikes (each strike is a new bolt)"),
                     on=(0.8, "chance a strike is lit (the rest are dark frames: real flicker)"),
                     thick=(0.75, "bolt thickness multiplier (short links are thinner on their own)"),
                     ramp=(0.12, "seconds to fade in at the start (and out, at most 0.15 s, at the end)"),
                     ends=(True, "flickering flares at the terminals"), flare=(90.0, "end flare size"),
                     loop=(False, "true: strikes from 0, the end repeats the start (a seamless loop, no ramp)"))),
    "crackle": dict(
        fn=crackle, duration=1.6, kind="window", color="", count=6,
        summary="Electricity (kind=electric) or flames (kind=fire) flickering at points around a shape: every `rate` s each "
                "point swaps to one of four pictures (or nothing, 1 - on of the time), a random turn of up to spin degrees "
                "and a random brightness; flames stand on their point, face away from the centre and stretch. Default "
                "points: a ring of count points at radius (electric runs along it, fire points out). With kit=\"realistic\" "
                "the Kenney real-lightning crackles / real flames; without, procedural crackles / flame tongues. Default "
                "colour 9FE0FF electric, FFA040 fire.",
        anchor="Shape centre; points relative to it.",
        options=dict(kind=("electric", "electric | fire"),
                     points=(None, "[[x, y] or [x, y, rotation], ...] (default: a ring of count points at radius)"),
                     radius=(120.0, "ring radius for the default points"),
                     size=(None, "picture width (default 150 electric, 70 fire)"),
                     rate=(None, "seconds between swaps (default 0.055 electric, 0.08 fire)"),
                     on=(None, "chance a swap is lit (default 0.6 electric, 0.85 fire)"),
                     spin=(35.0, "random turn per swap, +- degrees"), alpha=(1.0, "brightness"),
                     ramp=(0.3, "seconds to build up at the start (it fades out over 0.15 s at the end)"),
                     loop=(False, "true: a seamless loop (no ramp, the end repeats the start)"))),
    "surface_glow": dict(
        fn=surface_glow, duration=2.2, kind="window", color="FF5A18",
        summary="The subject's OWN picture glows: an additive copy of slot= (all its attachments, on its bone, drawn right "
                "after it) that follows that slot's attachment keys in the animation it goes into (into=), so it hides "
                "when a spinning coin's face swaps away, and glows with keyed colour / alpha: red-hot metal (the default "
                "keys), an icy sheen ([[0, 'BFE6FF', 0], [1, 'D8F2FF', 0.35], ...]), a charge-up. pair= a second slot "
                "(the back face) at the same time. Without slot it glows a stand-in disc.",
        anchor="Your slot's own bone (x / y only place the stand-in disc).",
        options=dict(slot=("", "YOUR slot whose picture glows (required for real use)"),
                     pair=("", "a second slot glowing the same way (the back face)"),
                     keys=(HOT, "[[t, 'RRGGBB', alpha], ...] seconds from start (linear between keys)"),
                     follow=(True, "copy the slot's attachment keys from the target animation (false: its setup picture)"),
                     size=(220.0, "stand-in disc size (no slot)"))),
})
ROLES["bolt_link"] = {"bolt": "one bolt, HORIZONTAL, from the left edge to the right edge (stretched A -> B)",
                      "bolt_2": "a second bolt variant, same layout", "bolt_3": "a third bolt variant, same layout",
                      "glow_core": "the flare at each end, centred"}
ROLES["crackle"] = {**{r: f"electric crackle {i + 1}, centred (kind=electric)" for i, r in enumerate(SPARK_ROLES)},
                    **{r: f"flame {i + 1}, point UP, base at the bottom (kind=fire)" for i, r in enumerate(FLAME_ROLES)}}
ROLES["surface_glow"] = {"disc": "the stand-in face when no slot is given, round, centred"}
for _n in NAMES:
    RECIPES[_n]["roles"] = ROLES[_n]
