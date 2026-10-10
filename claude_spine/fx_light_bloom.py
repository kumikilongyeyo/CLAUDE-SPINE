"""Prism light bloom for ``fx_recipe``: a rainbow ray burst and a prism ring, additive, that grow from small to large.
Each piece starts small at low opacity, reaches 100% opacity at `peak` of its life (the middle by default), then fades
while it keeps growing, and the rings ripple outward past the rays. Three takes, one recipe each:

* ``light_bloom``  one gentle bloom: the rays open slowly, rings start inside them a beat later and ripple out past them
* ``light_ripple`` a seamless loop: a new wave (rays + ring) is born at the centre every D / waves seconds, each one
  turned differently, the rings wobble, the group breathes
* ``light_shock``  a punchy hit: the rays snap open (expo ease) against a counter-turning copy, then rings fire out
  fast, each one later, bigger and longer than the last

Built from an artist's two-layer PSB (ray burst + ring) and judged by them, so the defaults are those timings. The
pictures are art roles: ``art={"rays": "file.psb#Layer 1", "ring": "file.psb#Layer 2"}``. A user picture is cleaned
for additive (``clean``): a flat alpha haze over the whole layer is removed (additive turns it into a visible square),
the art fades out before its square edges, and it is centred on its own circle (a ring that sits off the burst's centre
would slide sideways while it scales). Keys are real bezier curves (editable in Spine), not dense samples; the loop
splits any curve that crosses the loop point so it is seamless.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .fx import _rgba
from .fx_recipes import RECIPES, ROLES, Ctx, _blur, _grid, _hexn, hexa
from .ir import Key

# eases as fractions of a segment (CSS cubic-bezier)
OUT_SINE = (0.3, 0.6, 0.55, 1.0)
OUT_EXPO = (0.12, 0.85, 0.3, 1.0)
IN_OUT = (0.42, 0.0, 0.58, 1.0)
LINEAR = (0.25, 0.25, 0.75, 0.75)
ALPHA_UP = (0.45, 0.0, 0.6, 1.0)          # slow start: low opacity while still small
ALPHA_DOWN = (0.35, 0.0, 0.65, 1.0)


# ------------------------------------------------------------------ default pictures (drawn, no user art)
def _hue(h: np.ndarray) -> np.ndarray:
    k = (h[..., None] * 6 + np.array([5.0, 3.0, 1.0])) % 6
    return 1 - np.clip(np.minimum(k, 4 - k), 0, 1)


def tex_prism_rays(n: int = 512, seed: int = 3) -> Image.Image:
    """A ring of rainbow light streaks around a dark hole: blue/violet streaks with cyan-green hot spots."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    r, th = np.hypot(x, y), np.arctan2(y, x)
    acc, col = np.zeros((n, n)), np.zeros((n, n, 3))
    for _ in range(78):
        ang, w = rng.uniform(-math.pi, math.pi), rng.uniform(0.012, 0.04)
        r0, ln, b = 0.42 + rng.uniform(0, 0.1), rng.uniform(0.22, 0.5), rng.uniform(0.15, 0.55)
        hue = rng.choice([rng.uniform(0.55, 0.75), rng.uniform(0.3, 0.5), rng.uniform(0.0, 0.1)], p=[0.6, 0.3, 0.1])
        dth = np.abs(((th - ang + math.pi) % (2 * math.pi)) - math.pi)
        rad = np.clip((r - r0 + 0.04) / 0.08, 0, 1) * np.clip(1 - (r - r0) / ln, 0, 1) ** 1.5
        s = b * np.exp(-(dth * r / (w * (0.5 + r))) ** 2) * rad
        if rng.random() < 0.3:                                        # a hot spot along the streak
            s = s + 0.9 * np.exp(-((r - r0 - 0.25 * ln) / 0.05) ** 2 - (dth * r / (w * 0.9)) ** 2)
        acc += s
        col += s[..., None] * _hue(np.full((n, n), hue))
    a = np.clip(_blur(np.clip(acc, 0, 1), n / 256), 0, 1)
    rgb = col / np.maximum(acc, 1e-6)[..., None]
    rgb = rgb * (1 - 0.2 * a[..., None]) + 0.2 * a[..., None]         # hot parts run toward white
    a *= np.clip((1 - r) / 0.08, 0, 1)
    return _rgba(rgb, a)


def tex_prism_ring(n: int = 512, seed: int = 5) -> Image.Image:
    """A soft ring of fine, pale prism streaks (teal and peach), hollow in the middle."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    r, th = np.hypot(x, y), np.arctan2(y, x)
    acc, col = np.zeros((n, n)), np.zeros((n, n, 3))
    for _ in range(150):
        ang, w = rng.uniform(-math.pi, math.pi), rng.uniform(0.006, 0.018)
        mid, ln, b = rng.uniform(0.72, 0.84), rng.uniform(0.07, 0.14), rng.uniform(0.2, 0.6)
        tint = np.array([0.3, 0.8, 0.85]) if rng.random() < 0.6 else np.array([0.95, 0.6, 0.4])
        dth = np.abs(((th - ang + math.pi) % (2 * math.pi)) - math.pi)
        s = b * np.exp(-(dth * r / w) ** 2) * np.exp(-((r - mid) / ln) ** 2)
        acc += s
        col += s[..., None] * tint
    body = 0.12 * np.exp(-((r - 0.78) / 0.07) ** 2)                  # the soft body of the ring
    acc += body
    col += body[..., None] * np.array([0.6, 0.8, 0.9])
    a = np.clip(_blur(np.clip(acc * 0.6, 0, 1), n / 256), 0, 0.5)
    rgb = col / np.maximum(acc, 1e-6)[..., None]
    rgb = rgb * 0.8 + 0.2
    a *= np.clip((1 - r) / 0.08, 0, 1)
    return _rgba(np.clip(rgb, 0, 1), a)


# ------------------------------------------------------------------ user pictures: made safe for additive
def ring_centre(alpha: np.ndarray) -> tuple[float, float]:
    """Centre of the circle a ring / burst picture is drawn around: least-squares circle through the inner edge
    (the first place, walking out from the centre, where the blurred alpha gets bright). Falls back to the middle."""
    h, w = alpha.shape
    al = _blur(np.clip(alpha / 255.0, 0, 1), max(1.0, min(h, w) / 160))
    th = 0.25 * float(al.max())
    c = np.array([w / 2, h / 2], float)
    if th <= 0:
        return float(c[0]), float(c[1])
    for _ in range(3):
        pts = []
        for ang in np.linspace(0, 2 * math.pi, 180, endpoint=False):
            d = np.array([math.cos(ang), math.sin(ang)])
            for rr in range(int(min(h, w) * 0.04), int(max(h, w) * 0.6)):
                px, py = (c + d * rr).astype(int)
                if not (0 <= px < w and 0 <= py < h):
                    break
                if al[py, px] > th:
                    pts.append((px, py))
                    break
        if len(pts) < 24:
            break
        P = np.array(pts, float)
        A = np.c_[2 * P, np.ones(len(P))]
        cx, cy, _ = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
        if math.hypot(cx - w / 2, cy - h / 2) > 0.25 * min(h, w):
            break                                                     # not a ring: keep the middle
        c = np.array([cx, cy])
    return float(c[0]), float(c[1])


def clean_for_additive(im: Image.Image, recentre: bool = True, tex_scale: float = 1.0) -> Image.Image:
    """Remove a flat alpha haze, fade out before the square edges, centre on the picture's own circle, square it."""
    a = np.asarray(im.convert("RGBA"), np.float32).copy()
    al = a[..., 3]
    floor = float(np.percentile(al, 2))
    if floor > 0:                                                     # a haze over the whole layer
        al = np.clip((al - floor - 2) / (255 - floor - 2), 0, 1) * 255
    h, w = al.shape
    cx, cy = ring_centre(al) if recentre else (w / 2, h / 2)
    yy, xx = np.mgrid[:h, :w]
    rr = np.hypot(xx - cx, yy - cy)
    edge = max(1.0, min(cx, cy, w - cx, h - cy))
    border = np.concatenate([al[:2].ravel(), al[-2:].ravel(), al[:, :2].ravel(), al[:, -2:].ravel()])
    if border.max() > 20:                                             # the art runs off the layer: soft-cut it
        al = al * np.clip((edge - rr) / (edge * 0.14), 0, 1)
    a[..., 3] = al
    half = int(math.ceil(max(cx, cy, w - cx, h - cy)))
    sq = np.zeros((2 * half, 2 * half, 4), np.float32)
    ox, oy = int(round(half - cx)), int(round(half - cy))
    sq[oy:oy + h, ox:ox + w] = a[: 2 * half - oy, : 2 * half - ox]
    vis = np.argwhere(sq[..., 3] > 1)
    if len(vis):                                                      # trim, keeping the centre
        m = int(min(vis.min(0).min(), (2 * half - 1 - vis.max(0)).min()))
        sq = sq[m: 2 * half - m, m: 2 * half - m]
    out = Image.fromarray(sq.round().clip(0, 255).astype(np.uint8), "RGBA")
    if tex_scale != 1.0:
        n = max(8, round(out.size[0] * tex_scale))
        out = out.resize((n, n), Image.LANCZOS)
    return out


def _user_art(c: Ctx, role: str, P: dict) -> None:
    """Load the user's picture for `role` once and replace it with its additive-safe version."""
    art = c._art(role)
    if not art or art.get("_cleaned") or not P["clean"]:
        return
    import hashlib
    raw = c.p.image(art["tex"])
    im = clean_for_additive(raw, recentre=True, tex_scale=float(P["tex_scale"]))
    # one texture per picture, whichever of the three takes uses it: they can share a project and an atlas
    name = f"fx/art_light_{role}_{hashlib.sha1(np.asarray(im).tobytes()).hexdigest()[:8]}"
    try:
        c.p.image(name)
    except FileNotFoundError:
        c.p.write_image(name, im)
    if name != art["tex"]:
        c.p.image_path(art["tex"]).unlink(missing_ok=True)
    art.update(tex=name, size=im.size, _cleaned=True)
    c.art_used[role] = name


# ------------------------------------------------------------------ bezier keys (seamless loops)
def _cubic(seg):
    t0, v0, t1, v1, e = seg
    p0, p3 = np.array([t0, *v0], float), np.array([t1, *v1], float)
    p1 = np.array([t0 + e[0] * (t1 - t0)] + [a + e[1] * (b - a) for a, b in zip(v0, v1)])
    p2 = np.array([t0 + e[2] * (t1 - t0)] + [a + e[3] * (b - a) for a, b in zip(v0, v1)])
    return [p0, p1, p2, p3]


def _split(q, ts):
    """Split a cubic (time/value space) at time ts by de Casteljau."""
    p0, p1, p2, p3 = q
    lo, hi = 0.0, 1.0
    for _ in range(60):
        u = (lo + hi) / 2
        t = (1 - u) ** 3 * p0[0] + 3 * (1 - u) ** 2 * u * p1[0] + 3 * (1 - u) * u * u * p2[0] + u ** 3 * p3[0]
        lo, hi = (u, hi) if t < ts else (lo, u)
    u = (lo + hi) / 2
    a, b, cc = p0 + (p1 - p0) * u, p1 + (p2 - p1) * u, p2 + (p3 - p2) * u
    d, f = a + (b - a) * u, b + (cc - b) * u
    s = d + (f - d) * u
    s[0] = ts
    return [p0, a, d, s], [s, f, cc, p3]


def bezier_keys(c: Ctx, segs, fields, loop: float | None = None) -> list[Key]:
    """Contiguous segments [(u0, values0, u1, values1, ease)] in recipe time -> Spine keys with absolute curves,
    mapped through the recipe clock (start, time scale). loop=L wraps into 0..L, splitting a curve that crosses L."""
    qs = [_cubic(s) for s in segs]
    if loop:
        out = []
        for q in qs:
            shift = np.zeros(len(q[0]))
            shift[0] = loop
            if q[0][0] < loop - 1e-9 < q[3][0]:
                left, right = _split(q, loop)
                out += [left, [p - shift for p in right]]
            elif q[0][0] >= loop - 1e-9:
                out.append([p - shift for p in q])
            else:
                out.append(q)
        qs = sorted(out, key=lambda q: q[0][0])
    T = lambda u: c.t0 + float(u) * c.k  # noqa: E731
    keys: list[Key] = []

    def key(p, curve=None):
        k = Key(time=round(T(p[0]), 4), curve=curve)
        for f, v in zip(fields, p[1:]):
            setattr(k, f, round(float(v), 4))
        return k

    for i, (p0, p1, p2, p3) in enumerate(qs):
        if keys and abs(keys[-1].time - round(T(p0[0]), 4)) < 1e-6:
            keys.pop()                                                # the previous end key = this start
        curve = []
        for j in range(1, len(p0)):
            curve += [round(T(p1[0]), 4), round(float(p1[j]), 4), round(T(p2[0]), 4), round(float(p2[j]), 4)]
        keys.append(key(p0, curve))
        nxt = qs[i + 1][0][0] if i + 1 < len(qs) else None
        if nxt is None or abs(nxt - p3[0]) > 1e-6:
            keys.append(key(p3))
    return keys


# ------------------------------------------------------------------ one element's life
def _life(c: Ctx, P: dict, slot: str, bone: str, u0: float, u1: float, s0: float, s1: float, *, ease=OUT_SINE,
          alpha: float = 1.0, rot=(0.0, 0.0), squash: float = 0.0, loop: float | None = None) -> None:
    """Scale s0 -> s1, opacity 0 -> alpha at P["peak"] of the life -> 0, rotation rot[0] -> rot[1].
    squash: the ring breathes as an ellipse in between (x leads y by a quarter of the life), round at both ends."""
    um = u0 + (u1 - u0) * float(P["peak"])
    pk = c.a(alpha)
    # before its first key Spine shows the SETUP pose: a piece that starts late is held invisible and small from 0
    hold = (lambda v, e=LINEAR: [(0.0, v, u0, v, e)]) if (u0 > 1e-6 and not loop) else (lambda v, e=LINEAR: [])
    c.ab.a.slots.setdefault(slot, {})["alpha"] = bezier_keys(
        c, hold([0.0]) + [(u0, [0.0], um, [pk], ALPHA_UP), (um, [pk], u1, [0.0], ALPHA_DOWN)], ["value"], loop)
    squash *= float(P["wobble"])
    if squash:
        q = (u1 - u0) / 4
        mid = [s0 + (s1 - s0) * f for f in (0.0, 0.62, 0.86, 0.96, 1.0)]
        sx = [m * (1 + squash * w) for m, w in zip(mid, (0, 1, 0, -1, 0))]
        sy = [m * (1 + squash * w) for m, w in zip(mid, (0, -1, 0, 1, 0))]
        segs = [(u0 + i * q, [sx[i], sy[i]], u0 + (i + 1) * q, [sx[i + 1], sy[i + 1]], ease if i == 0 else IN_OUT)
                for i in range(4)]
    else:
        segs = [(u0, [s0, s0], u1, [s1, s1], ease)]
    segs = hold([s0, s0]) + segs
    b = c.ab.a.bones.setdefault(bone, {})
    b["scale"] = bezier_keys(c, segs, ["x", "y"], loop)
    sp = float(P["spin"])
    if rot != (0.0, 0.0):
        b["rotate"] = bezier_keys(c, hold([rot[0] * sp]) + [(u0, [rot[0] * sp], u1, [rot[1] * sp], LINEAR)],
                                  ["value"], loop)


def _pieces(c: Ctx, P: dict, parent: str, specs: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """specs [(tag, "rays" | "ring")] -> {tag: (slot, bone)}; rays drawn under rings in the order given. Setup alpha is
    0 (the alpha keys bring each piece in), so nothing shows in the setup pose or before a piece's life."""
    col = _hexn(P["color"], "FFFFFF")
    size = float(P["size"])
    for role in ("rays", "ring"):
        _user_art(c, role, P)
    out = {}
    for tag, kind in specs:
        b = c.bone(tag, parent)
        if kind == "rays":
            s = c.slot(b, "fx/prism_rays", size, color=hexa(col, 0.0), make=tex_prism_rays, role="rays")
        else:
            s = c.slot(b, "fx/prism_ring", size * float(P["ring"]), color=hexa(col, 0.0), make=tex_prism_ring,
                       role="ring")
        out[tag] = (s, b)
    return out


def _reach(P: dict, s: float) -> float:
    """Ring end scale, pushed further (reach > 1) or held in (reach < 1) relative to 1."""
    return 1.0 + (s - 1.0) * float(P["reach"])


# ------------------------------------------------------------------ the three takes
def light_bloom(c: Ctx, P: dict) -> dict:
    D = 2.7
    n = max(0, int(P["rings"]))
    grp = c.bone("bloom", c.group)
    pcs = _pieces(c, P, grp, [("rays", "rays")] + [(f"ring{i}", "ring") for i in range(n)])
    _life(c, P, *pcs["rays"], 0.0, 2.0, 0.12, 1.1, rot=(0, 12))
    for i in range(n):
        u0 = 0.35 + 0.4 * i
        _life(c, P, *pcs[f"ring{i}"], u0, min(D, u0 + 1.95), 0.15, _reach(P, 1.6 + 0.35 * i),
              rot=((0, -8), (20, 28), (-15, -24))[i % 3])
    c.show([s for s, _ in pcs.values()], 0, D)
    return c.result(duration=D * c.k, rings=n)


def light_ripple(c: Ctx, P: dict) -> dict:
    D = 2.4
    N = max(1, int(P["waves"]))
    grp = c.bone("ripple", c.group)
    pcs = _pieces(c, P, grp, [(f"rays{i}", "rays") for i in range(N)] + [(f"ring{i}", "ring") for i in range(N)])
    life = D - 1 / 30                       # one frame dead before the respawn: two keys never share a time
    rng = np.random.default_rng(c.seed + 11)
    for i in range(N):
        o = i * D / N
        turn = (0.0, 137.0, 251.0)[i] if i < 3 else float(rng.uniform(0, 360))
        spin = (10.0, -9.0, 7.0)[i % 3]
        _life(c, P, *pcs[f"rays{i}"], o, o + life, 0.1, 1.2, rot=(turn, turn + spin), loop=D)
        _life(c, P, *pcs[f"ring{i}"], o + 0.08, o + 0.08 + life, 0.12, _reach(P, 1.55), rot=(-turn, -turn - spin),
              squash=0.05, loop=D)
    q = D / 4                               # the whole group breathes 1 -> 1.04 -> 1, twice a loop
    c.ab.a.bones.setdefault(grp, {})["scale"] = bezier_keys(
        c, [(i * q, [1 + 0.04 * (i % 2)] * 2, (i + 1) * q, [1 + 0.04 * ((i + 1) % 2)] * 2, IN_OUT) for i in range(4)],
        ["x", "y"])
    c.show([s for s, _ in pcs.values()], 0, None)
    return c.result(duration=D * c.k, loop=D * c.k, waves=N)


def light_shock(c: Ctx, P: dict) -> dict:
    D = 1.55
    n = max(0, int(P["rings"]))
    grp = c.bone("shock", c.group)
    pcs = _pieces(c, P, grp, [("rays", "rays"), ("rays2", "rays")] + [(f"ring{i}", "ring") for i in range(n)])
    _life(c, P, *pcs["rays"], 0.0, 1.3, 0.08, 1.25, ease=OUT_EXPO, rot=(0, 14))
    _life(c, P, *pcs["rays2"], 0.05, 1.25, 0.06, 1.05, ease=OUT_EXPO, alpha=0.7, rot=(17, -6))
    for i in range(n):
        u0 = (0.0, 0.12, 0.3)[i] if i < 3 else 0.3 + 0.15 * (i - 2)
        u1 = min(D, (0.9, 1.2, 1.55)[i] if i < 3 else D)
        _life(c, P, *pcs[f"ring{i}"], u0, u1, 0.1, _reach(P, (1.5, 1.8, 2.1)[i] if i < 3 else 2.1 + 0.2 * (i - 2)),
              ease=OUT_EXPO, rot=((0, -10), (40, 52), (95, 85))[i % 3], squash=(0.0, 0.04, 0.06)[i % 3])
    c.show([s for s, _ in pcs.values()], 0, D)
    return c.result(duration=D * c.k, rings=n)


_OPTS = dict(
    size=(400.0, "ray burst diameter (the picture's width at scale 1; it ends its life at ~1.1-1.25x)"),
    ring=(0.7, "ring diameter as a fraction of size"),
    peak=(0.5, "when each piece is at 100% opacity, as a fraction of its life (0.5 = the middle)"),
    reach=(1.0, "how far the rings travel past their start size (1 = as designed, 1.3 = further out)"),
    spin=(1.0, "multiplies every turn (0 = no rotation)"),
    wobble=(1.0, "multiplies the rings' ellipse wobble (0 = always round)"),
    clean=(True, "make your art additive-safe: remove a flat alpha haze, fade the square edges, centre it on its circle"),
    tex_scale=(0.5, "texture size for YOUR art after cleaning (soft light loses nothing at half size)"),
)
_ART = {"rays": "the ray burst: light streaks round a dark hole, square, centred (e.g. file.psb#Layer 1)",
        "ring": "the ring: a soft hollow ring, centred (e.g. file.psb#Layer 2)"}

RECIPES.update({
    "light_bloom": dict(
        fn=light_bloom, duration=2.7, kind="one-shot", color="FFFFFF",
        summary="Additive prism light, one gentle bloom: the rainbow ray burst opens slowly from small and faint to 100% "
                "opacity mid-life and fades as it keeps growing; `rings` prism rings start inside it a beat later and ripple "
                "out past it. Event fx_light_bloom.",
        anchor="Centre of the burst.",
        options=dict(_OPTS, rings=(2, "rings rippling out after the rays"))),
    "light_ripple": dict(
        fn=light_ripple, duration=2.4, kind="one-shot", color="FFFFFF",
        summary="Additive prism light as a seamless loop: a new wave (ray burst + ring) is born small and faint at the centre "
                "every duration / waves seconds, peaks mid-life, fades as it ripples outward; each wave is turned "
                "differently, the rings wobble, the group breathes. Result `loop` = loop length.",
        anchor="Centre of the waves.",
        options=dict(_OPTS, waves=(3, "waves alive at once"))),
    "light_shock": dict(
        fn=light_shock, duration=1.55, kind="one-shot", color="FFFFFF",
        summary="Additive prism light as a punchy hit: the ray burst snaps open (expo ease) against a counter-turning copy "
                "that shimmers, then `rings` rings fire out fast, each later, bigger and longer than the last. Every piece "
                "still peaks at 100% mid-life. Event fx_light_shock.",
        anchor="Centre of the hit.",
        options=dict(_OPTS, rings=(3, "shock rings"))),
})
for _n in ("light_bloom", "light_ripple", "light_shock"):
    ROLES[_n] = dict(_ART)
    RECIPES[_n]["roles"] = ROLES[_n]
