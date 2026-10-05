"""Ice and water element recipes for ``fx_recipe``: frost, icicles, ice_shatter, bubbles, water_splash.

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, closed-form keys, ``art=`` roles), plus one
new trick: ``frost`` grows by a GENERATED FLIPBOOK. The frost ferns are grown once in Python (branches at the 60 degrees of
ice crystals, every point stamped with the time it froze) and each frame shows what has frozen by then, so the growth is
exact and costs nothing at runtime but a sequence. Caustics (shimmering light under water) are an After Effects
template (``ae_template caustics``) because they need per-pixel noise.

Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx_recipes import (Ctx, RECIPES, ROLES, _blur, _colorize, _grid, _hexn, _mix, _rgb, _uniq, ease_out, hexa, smooth,
                         times_dense)
from .fx import _rgba
from .ir import Sequence

ICE = (150, 205, 245)


# ------------------------------------------------------------------ textures
def frost_frames(w: int = 320, h: int = 320, frames: int = 18, seed: int = 3, mode: str = "edges",
                 color: str = "9FD8FF") -> list[Image.Image]:
    """Frost ferns growing: branches every few steps at +-60 degrees (ice is hexagonal), thinner and shorter each
    generation. Every stamped point keeps the time it froze; frame k shows everything frozen by k/frames."""
    rng = np.random.default_rng(seed)
    segs: list[tuple] = []
    S = 2                                                          # supersample
    W, H = w * S, h * S

    def grow(x, y, ang, length, t, depth, wd, speed):
        step = 3.0 * S
        n = max(1, int(length / step))
        side = 1
        for i in range(n):
            ang += float(rng.normal(0, 0.06))
            nx, ny = x + math.cos(ang) * step, y + math.sin(ang) * step
            if not (0 <= nx < W and 0 <= ny < H):
                return
            segs.append((x, y, nx, ny, t, wd * (1 - 0.6 * i / n)))
            t += step / speed
            if depth < 4 and i % int(rng.integers(3, 6)) == 2 and i < n - 2:
                frac = 1 - i / n
                grow(nx, ny, ang + side * math.pi / 3 * float(rng.uniform(0.85, 1.1)),
                     length * float(rng.uniform(0.25, 0.5)) * frac, t, depth + 1, wd * 0.6, speed * 0.85)
                side = -side
            x, y = nx, ny

    if mode == "center":
        a0 = float(rng.uniform(0, math.pi / 3))
        for k in range(6):                                       # a six-armed star, like a snowflake
            grow(W / 2, H / 2, a0 + k * math.pi / 3, min(W, H) * 0.47, 0.0, 0, 2.6 * S, 1.0)
    else:                                                          # creep in from the borders
        for k in range(24):
            edge = k % 4
            u = float(rng.uniform(0.08, 0.92))
            x, y, a = {0: (u * W, 0, math.pi / 2), 1: (W - 1, u * H, math.pi), 2: (u * W, H - 1, -math.pi / 2), 3: (0, u * H, 0.0)}[edge]
            a += float(rng.uniform(-0.5, 0.5))
            grow(x, y, a, min(W, H) * float(rng.uniform(0.3, 0.62)), float(rng.uniform(0, 0.3)) * min(W, H), 0, 1.7 * S, 1.0)
    if not segs:
        segs.append((W / 2, H / 2, W / 2 + 1, H / 2, 0.0, 1.0))
    tmax = max(sg[4] for sg in segs) or 1.0
    rng2 = np.random.default_rng(seed + 1)
    speck = np.asarray(Image.fromarray((rng2.random((h // 2, w // 2)) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    hot, mid, edge = (255, 255, 255), _mix(_rgb(color), (255, 255, 255), 0.55), _rgb(color)
    out = []
    for f in range(1, frames + 1):
        tf = f / frames * tmax
        img = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(img)
        for x0, y0, x1, y1, t, wd in segs:
            if t <= tf:
                d.line([(x0, y0), (x1, y1)], fill=255, width=max(1, int(round(wd))))
        img = img.resize((w, h), Image.LANCZOS)
        core = np.asarray(img, np.float32) / 255
        glow = _blur(core, 2.2)
        frosted = _blur(core, 7.0) * (0.45 + 0.55 * speck)       # a frosted film builds up around the ferns
        a = np.clip(core * 0.95 + glow * 0.5 + frosted * 1.3, 0, 1)
        out.append(_colorize(a, hot, mid, edge))
    return out


def tex_icicle(seed: int = 1, w: int = 64, h: int = 320) -> Image.Image:
    """A hanging icicle (root at the TOP): tapered, slightly lumpy, translucent body, a bright highlight edge, darker
    far side, vertical streaks, a hot tip."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    v = y / (h - 1)
    ph = float(rng.uniform(0, 6.28))
    hw = 0.92 * (1 - v) ** 0.85 * (1 + 0.07 * np.sin(v * 23 + ph) + 0.05 * np.sin(v * 51 + 2 * ph)) + 0.02
    hw += 0.12 * np.exp(-((v - 0.03) / 0.05) ** 2)                 # lump where it joins the roof
    inside = np.clip((hw - np.abs(xn)) / 0.08, 0, 1)
    rel = np.clip(xn / np.maximum(hw, 1e-3), -1, 1)
    fres = np.abs(rel) ** 3                                        # edges are more opaque (fresnel)
    lo = rng.random((h // 16, 6))
    streak = np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    a = inside * (0.42 + 0.45 * fres + 0.12 * streak)
    hl = np.exp(-((rel + 0.45) / 0.16) ** 2) * inside                # highlight down the left side
    lum = 0.55 + 0.5 * hl - 0.18 * np.clip(rel, 0, 1) + 0.1 * streak
    tip = np.exp(-((v - 0.97) / 0.025) ** 2) * inside
    lum = np.clip(lum + tip * 0.6, 0, 1.2)
    a = np.clip(a + hl * 0.35 + tip * 0.4, 0, 1)
    base = np.array(ICE) / 255
    rgb = np.clip(base[None, None, :] * (0.6 + 0.4 * lum[..., None]) + (np.clip(lum - 0.8, 0, 1) * 1.6)[..., None], 0, 1)
    return _rgba(rgb, a)


def tex_drop(w: int = 48, h: int = 72) -> Image.Image:
    """A water droplet (falling, round bottom, pointed top): clear body, dark rim, white specular."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) * 0.62) / ((h - 1) * 0.38)
    r = np.hypot(xn, np.where(yn < 0, yn * 0.55, yn))
    r = np.where(yn < 0, np.hypot(xn / np.maximum(1 + yn * 0.95, 0.05), yn * 0.62), r)
    inside = np.clip((1 - r) / 0.08, 0, 1)
    rim = np.clip((r - 0.65) / 0.3, 0, 1)
    a = inside * (0.35 + 0.6 * rim)
    spec = np.exp(-(((xn + 0.3) / 0.18) ** 2 + ((yn + 0.1) / 0.16) ** 2))
    lum = 0.55 + 0.35 * (1 - rim) + spec
    a = np.clip(a + spec * 0.6, 0, 1)
    base = np.array((160, 210, 245)) / 255
    rgb = np.clip(base[None, None, :] * lum[..., None] + (np.clip(spec - 0.3, 0, 1))[..., None], 0, 1)
    return _rgba(rgb, a)


def tex_bubble(n: int = 128) -> Image.Image:
    """A soap/water bubble: nearly clear centre, bright fresnel rim with a hint of iridescence, a specular window top-left."""
    x, y = _grid(n)
    r = np.hypot(x, y)
    th = np.arctan2(y, x)
    rim = np.clip((r - 0.72) / 0.24, 0, 1) ** 1.6
    inside = np.clip((1 - r) / 0.04, 0, 1)
    a = inside * (0.06 + 0.85 * rim)
    spec = np.exp(-(((x + 0.38) / 0.17) ** 2 + ((y + 0.42) / 0.12) ** 2))
    spec2 = 0.5 * np.exp(-(((x - 0.45) / 0.08) ** 2 + ((y - 0.5) / 0.08) ** 2))
    a = np.clip(a + (spec + spec2) * inside, 0, 1)
    hue = 0.5 + 0.5 * np.sin(th * 2 + r * 6)
    rgb = np.dstack([0.75 + 0.25 * hue, 0.88 + 0.12 * (1 - hue), np.ones_like(r)])
    rgb = np.clip(rgb + (spec + spec2)[..., None], 0, 1)
    return _rgba(rgb, a)


def ice_block(n: int = 256, shards: int = 14, seed: int = 5, color: str = "9FD8FF"):
    """An ice block (rounded square) cut into Voronoi shards. Returns (block image, crack-lines image, [(shard image,
    cx, cy) in pixels from the block centre, y up])."""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    qx, qy = np.abs(x) - 0.7, np.abs(y) - 0.7
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - 0.22
    inside = np.clip(-d / 0.03, 0, 1)
    lo = rng.random((10, 10))
    cloudy = np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), np.float32) / 255
    lum = 0.55 + 0.25 * cloudy + 0.35 * np.exp(-((x + y + 0.6) / 0.25) ** 2) - 0.2 * np.clip((x - y) / 2 + 0.3, 0, 1)
    edge = np.exp(-(-d / 0.05) ** 2) * inside
    a = inside * (0.62 + 0.3 * edge + 0.08 * cloudy)
    base = np.array(_rgb(color)) / 255
    rgb = np.clip(base[None, None, :] * (0.55 + 0.45 * lum[..., None]) + (edge * 0.5)[..., None], 0, 1)
    block = _rgba(rgb, a)
    # Voronoi shards
    pts = rng.uniform(-0.85, 0.85, (shards, 2))
    pts[0] = (0, 0)
    dist = np.stack([np.hypot(x - px, y - py) for px, py in pts])
    lab = np.argmin(dist, 0)
    srt = np.sort(dist, 0)
    crack = np.clip(1 - (srt[1] - srt[0]) / 0.02, 0, 1) * inside
    crack_img = _colorize(np.clip(crack + _blur(crack, 2.0) * 0.6, 0, 1), (255, 255, 255), (220, 245, 255), (150, 210, 245))
    arr = np.asarray(block).copy()
    pieces = []
    for k in range(shards):
        m = (lab == k) & (inside > 0.02)
        if m.sum() < 30:
            continue
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        piece = arr[y0:y1, x0:x1].copy()
        piece[..., 3] = (piece[..., 3] * m[y0:y1, x0:x1]).astype(np.uint8)
        # a bright cut edge on every shard
        e = _blur(m[y0:y1, x0:x1].astype(np.float32), 1.0)
        cut = np.clip((1 - np.abs(e - 0.5) * 2) * m[y0:y1, x0:x1], 0, 1)
        piece[..., :3] = np.clip(piece[..., :3] + (cut[..., None] * 90), 0, 255).astype(np.uint8)
        cx = (x0 + x1) / 2 - n / 2
        cy = n / 2 - (y0 + y1) / 2
        pieces.append((Image.fromarray(piece, "RGBA"), float(cx), float(cy)))
    return block, crack_img, pieces


# ------------------------------------------------------------------ helpers
def _seq_slot(c: Ctx, bone: str, base: str, imgs: list[Image.Image], width: float, height: float | None = None,
              blend: str = "normal") -> str:
    """A region slot that plays a generated flipbook (base00, base01, ...)."""
    for i, im in enumerate(imgs):
        c.p.write_image(f"{base}{i:02d}", im)
    sl = c.slot(bone, f"{base}00", width, height=height, blend=blend)
    att = c.sk.skin("default").attachments[sl]["fx"]
    att.path = base
    att.sequence = Sequence(count=len(imgs), start=0, digits=2)
    return sl


# ------------------------------------------------------------------ recipes
def frost(c: Ctx, P: dict) -> dict:
    """Frost ferns grow across a box (from its borders, or from the centre like a snowflake), with a cold glow and glints."""
    D = float(P["duration"])
    grow_t = float(P["grow"])
    col = _hexn(P["color"], "9FD8FF")
    Wd, Hd = float(P["width"]), float(P["height"])
    F = int(P["frames"])
    k = 320 / max(Wd, Hd)
    tw, th = max(32, int(Wd * k)), max(32, int(Hd * k))
    grp = c.bone("frost", c.group, 0, 0)
    b_glow = c.bone("glow", grp, sx=Wd / max(Wd, Hd), sy=Hd / max(Wd, Hd))
    s_glow = c.slot(b_glow, "fx/glow", max(Wd, Hd) * 1.6, role="glow")
    b_f = c.bone("ferns", grp)
    base = f"fx/frost_{P['mode']}_{c.seed}_{tw}x{th}_{col}_"
    s_f = _seq_slot(c, b_f, base, frost_frames(tw, th, F, c.seed, P["mode"], col), Wd, height=Hd, blend=str(P["blend"]))
    rng = np.random.default_rng(c.seed + 111)
    glints = []
    for i in range(int(P["glints"])):
        bn = c.bone(f"g{i}", grp, float(rng.uniform(-Wd * 0.42, Wd * 0.42)), float(rng.uniform(-Hd * 0.42, Hd * 0.42)))
        sl = c.slot(bn, "fx/spark", float(rng.uniform(26, 54)), color=hexa("FFFFFF", c.a(1.0)), role="spark")
        glints.append((bn, sl, float(rng.uniform(grow_t * 0.6, max(grow_t * 0.6 + 0.01, D - 0.5)))))
    c.show([s_glow, s_f], 0, D)
    c.ab.sequence(s_f, "fx", [(c.T(0.0), "once", 0, grow_t / F)])
    ts = times_dense(0, D, 16)
    fade = lambda u: 1 - smooth(u, D - float(P["fade"]), D) if float(P["fade"]) > 0 else 1.0  # noqa: E731
    c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(0.35 * smooth(u, 0, grow_t) * fade(u))))
    c.color_keys(s_f, ts, lambda u: hexa("FFFFFF", c.a(fade(u))))
    for bn, sl, t0 in glints:
        c.ab.slot_attachment(sl, [(0.0, None), (c.T(t0), "fx"), (c.T(t0 + 0.45), None)])
        c.ab.bone(bn, "scale", _uniq([(c.T(t0), 0, 0), (c.T(t0 + 0.18), 1, 1), (c.T(t0 + 0.45), 0, 0)]), "quad_in_out")
        c.ab.bone(bn, "rotate", _uniq([(c.T(t0), 0), (c.T(t0 + 0.45), 70)]), "linear")
    c.ab.event(c.T(grow_t), "fx_frost_done")
    return c.result(duration=D * c.k, frames=F, grown_at=c.T(grow_t))


def icicles(c: Ctx, P: dict) -> dict:
    """Icicles grow down from the top edge of a box, a frost rim forms along it, glints run down them and drops fall."""
    D = float(P["duration"])
    Wd, Hd = float(P["width"]), float(P["height"])
    n = int(P["count"])
    Lmax = float(P["length"])
    rng = np.random.default_rng(c.seed + 121)
    grp = c.bone("icicles", c.group, 0, Hd / 2)
    b_rim = c.bone("rim", grp)
    s_rim = c.slot(b_rim, "fx/frostrim", Wd * 1.08, make=lambda: _tex_frost_rim(), role="rim")
    items = []
    for i in range(n):
        x = -Wd / 2 + (i + float(rng.uniform(0.25, 0.75))) / n * Wd
        L = Lmax * float(rng.uniform(0.45, 1.0)) * (1 - 0.35 * abs(x) / (Wd / 2 + 1e-6))
        bn = c.bone(f"i{i}", grp, x, 2)
        v = int(rng.integers(1, 4))
        sl = c.slot(bn, f"fx/icicle{v}", L * 0.22, height=L, oy=-L / 2, make=lambda v=v: tex_icicle(v), role="icicle", anchor="top")
        db = c.bone(f"d{i}", grp, x, 2 - L)
        ds = c.slot(db, "fx/drop", 11.0, make=lambda: tex_drop(), role="drop")
        gb = c.bone(f"gl{i}", grp, x, 0)
        gs = c.slot(gb, "fx/spark", 24.0, color=hexa("FFFFFF", 1.0), role="spark")
        items.append(dict(b=bn, s=sl, L=L, db=db, ds=ds, gb=gb, gs=gs, t0=float(rng.uniform(0, 0.45)),
                          drip=float(rng.uniform(1.1, max(1.2, D - 0.6))), g0=float(rng.uniform(0.8, max(0.9, D - 0.4)))))
    c.show([s_rim] + [it["s"] for it in items], 0, D)
    gt = float(P["grow"])
    ts = times_dense(0, D, 20)
    c.bone_keys(b_rim, "scale", ts, lambda u: (0.2 + 0.8 * ease_out(u / 0.5, 2.0), 1.0))
    c.color_keys(s_rim, ts, lambda u: hexa("FFFFFF", c.a(smooth(u, 0, 0.3))))
    for it in items:
        t0 = it["t0"]
        c.bone_keys(it["b"], "scale", ts, lambda u, t0=t0: (0.55 + 0.45 * ease_out((u - t0) / gt, 2.2) if u > t0 else 0.55,
                                                           ease_out((u - t0) / gt, 2.6) if u > t0 else 0.0))
        # a glint runs down the icicle once
        g0 = it["g0"]
        c.ab.slot_attachment(it["gs"], [(0.0, None), (c.T(g0), "fx"), (c.T(g0 + 0.35), None)])
        c.ab.bone(it["gb"], "translate", _uniq([(c.T(g0), 0, -it["L"] * 0.1), (c.T(g0 + 0.35), 0, -it["L"] * 0.85)]), "linear")
        c.ab.bone(it["gb"], "scale", _uniq([(c.T(g0), 0.3, 0.3), (c.T(g0 + 0.15), 1, 1), (c.T(g0 + 0.35), 0, 0)]), "linear")
        # a drop swells at the tip, lets go and falls (gravity), fading
        if P["drips"]:
            td = it["drip"]
            fall = times_dense(td + 0.35, min(D, td + 0.9), 24)
            c.ab.slot_attachment(it["ds"], [(0.0, None), (c.T(td), "fx"), (c.T(min(D, td + 0.9)), None)])
            c.ab.bone(it["db"], "scale", _uniq([(c.T(td), 0, 0), (c.T(td + 0.35), 1, 1)]), "sine_in_out")
            c.bone_keys(it["db"], "translate", [td] + fall, lambda u, td=td: (0.0, -0.5 * 1400 * max(0.0, u - td - 0.35) ** 2))
            c.color_keys(it["ds"], [td] + fall, lambda u, td=td: hexa("FFFFFF", c.a(1 - smooth(u, td + 0.6, td + 0.9))))
    c.ab.event(c.T(0.0), "fx_icicles")
    return c.result(duration=D * c.k, icicles=n)


def _tex_frost_rim(w: int = 512, h: int = 64, seed: int = 4) -> Image.Image:
    """A frost crust along an edge (the edge at the TOP), crystalline and ragged on its lower side."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(float)
    v = y / (h - 1)
    lo = rng.random((4, 48))
    ragged = np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
    depth = 0.35 + 0.45 * ragged[0:1, :]
    a = np.clip((depth - v) / 0.12, 0, 1)
    sp = rng.random((h, w))
    a = np.clip(a * (0.7 + 0.3 * sp) + np.clip((sp - 0.985) * 60, 0, 1) * (v < depth + 0.1), 0, 1)
    xn = x / (w - 1)
    a *= np.clip(xn / 0.05, 0, 1) * np.clip((1 - xn) / 0.05, 0, 1)
    return _colorize(a, (255, 255, 255), (225, 245, 255), ICE)


def ice_shatter(c: Ctx, P: dict) -> dict:
    """An ice block forms over the target, cracks, then shatters: shards fly out and fall, a cold mist puffs, glints."""
    D = 1.6
    col = _hexn(P["color"], "9FD8FF")
    size = float(P["size"])
    t_form, t_crack, t_break = 0.22, float(P["crack"]), float(P["shatter"])
    block, crack, pieces = ice_block(256, int(P["count"]), c.seed + 5, col)
    k = size / 256
    tag = f"{c.seed}_{int(P['count'])}_{col}"
    c.p.write_image(f"fx/iceblock_{tag}", block)
    c.p.write_image(f"fx/icecrack_{tag}", crack)
    grp = c.bone("ice", c.group, 0, 0)
    b_glow, b_blk, b_crk = c.bone("glow", grp), c.bone("block", grp), c.bone("crack", grp)
    s_glow = c.slot(b_glow, "fx/glow", size * 2.0, role="glow")
    s_blk = c.slot(b_blk, f"fx/iceblock_{tag}", size, blend="normal", role="block")
    s_crk = c.slot(b_crk, f"fx/icecrack_{tag}", size, role="crack")
    rng = np.random.default_rng(c.seed + 131)
    shards = []
    for i, (im, cx, cy) in enumerate(pieces):
        c.p.write_image(f"fx/iceshard_{tag}_{i}", im)
        bn = c.bone(f"s{i}", grp, cx * k, cy * k)
        sl = c.slot(bn, f"fx/iceshard_{tag}_{i}", im.size[0] * k, blend="normal")
        ang = math.atan2(cy, cx) if (cx or cy) else float(rng.uniform(0, 2 * math.pi))
        sp = float(rng.uniform(220, 420)) * (size / 200)
        shards.append(dict(b=bn, s=sl, vx=math.cos(ang) * sp, vy=math.sin(ang) * sp + float(rng.uniform(60, 200)) * (size / 200),
                           rot=float(rng.uniform(-420, 420))))
    b_mist = c.bone("mist", grp)
    s_mist = c.slot(b_mist, "fx/smoke", size * 1.8, blend="additive", role="mist")
    b_ring = c.bone("ring", grp)
    s_ring = c.slot(b_ring, "fx/ring", size * 2.0, role="ring")
    c.show([s_glow, s_blk, s_crk], 0, t_break + 0.02)
    c.show([s["s"] for s in shards], t_break, D)
    c.show([s_mist, s_ring], t_break - 0.02, D)
    ts = times_dense(0, D, 30)
    form = lambda u: smooth(u, 0, t_form)  # noqa: E731
    c.color_keys(s_blk, ts, lambda u: hexa("FFFFFF", c.a(form(u))))
    c.bone_keys(b_blk, "scale", ts, lambda u: (0.85 + 0.15 * ease_out(u / t_form, 2.5) + 0.04 * math.exp(-((u - t_break) / 0.05) ** 2),) * 2)
    c.color_keys(s_crk, ts, lambda u: hexa("FFFFFF", c.a(smooth(u, t_crack, t_crack + 0.12) * (0.75 + 0.25 * math.sin(u * 60)))))
    c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(0.45 * form(u) + 0.5 * math.exp(-((u - t_break) / 0.08) ** 2))))
    tb = times_dense(t_break, D, 30)
    for s_ in shards:
        c.bone_keys(s_["b"], "translate", tb, lambda u, s_=s_: (s_["vx"] * (u - t_break), s_["vy"] * (u - t_break) - 0.5 * 1500 * (size / 200) * (u - t_break) ** 2))
        c.bone_keys(s_["b"], "rotate", tb, lambda u, s_=s_: s_["rot"] * (u - t_break))
        c.color_keys(s_["s"], tb, lambda u: hexa("FFFFFF", c.a(1 - smooth(u, t_break + 0.55, D))))
    c.bone_keys(b_mist, "scale", tb, lambda u: (0.4 + 0.9 * ease_out((u - t_break) / 0.7, 2.2),) * 2)
    c.bone_keys(b_mist, "rotate", tb, lambda u: 25 * (u - t_break))
    c.color_keys(s_mist, tb, lambda u: hexa("CFEFFF", c.a(0.75 * smooth(u, t_break, t_break + 0.08) * (1 - smooth(u, t_break + 0.2, D)))))
    c.bone_keys(b_ring, "scale", tb, lambda u: (0.3 + 1.2 * ease_out((u - t_break) / 0.45, 2.5),) * 2)
    c.color_keys(s_ring, tb, lambda u: hexa("E8F8FF", c.a(0.85 * (1 - smooth(u, t_break, t_break + 0.45)))))
    c.ab.event(c.T(t_crack), "fx_ice_crack")
    c.ab.event(c.T(t_break), "fx_ice_shatter")
    return c.result(duration=D * c.k, shards=len(shards), shatter_at=c.T(t_break))


def bubbles(c: Ctx, P: dict) -> dict:
    """Bubbles rise through a box, wobbling and squishing, and pop at their top. Loops exactly."""
    D = float(P["duration"])
    Wd, Hd = float(P["width"]), float(P["height"])
    n = int(P["count"])
    rng = np.random.default_rng(c.seed + 141)
    grp = c.bone("bubbles", c.group, 0, 0)
    bs = []
    for i in range(n):
        bn = c.bone(f"b{i}", grp, float(-Wd / 2 + (i + rng.uniform(0.2, 0.8)) / n * Wd), -Hd / 2)
        sl = c.slot(bn, "fx/bubble", float(rng.uniform(14, 40)) * float(P["size"]), make=lambda: tex_bubble(), role="bubble")
        bs.append(dict(b=bn, s=sl, m=int(rng.choice([1, 1, 2])), ph=float(rng.uniform(0, 1)), sw=float(rng.uniform(4, 14)),
                       f=int(rng.integers(2, 5)), top=float(rng.uniform(0.7, 1.0))))
    c.show([b["s"] for b in bs], 0, None)
    for b in bs:
        tsd = set(times_dense(0, D, 14))
        for k_ in range(1, b["m"] + 1):
            wrap = (k_ - b["ph"]) * D / b["m"]
            if 0 < wrap < D:
                tsd.update([wrap - 0.002, wrap])
        tsd = sorted(t for t in tsd if 0 <= t <= D)
        q = lambda u, b=b: (u * b["m"] / D + b["ph"]) % 1.0  # noqa: E731
        c.bone_keys(b["b"], "translate", tsd, lambda u, b=b, q=q: (b["sw"] * math.sin(2 * math.pi * b["f"] * q(u)), q(u) * Hd * b["top"]))
        # wobble + pop: the last 6% of the life swells and vanishes
        def sc(u, b=b, q=q):
            qq = q(u)
            w = 1 + 0.08 * math.sin(2 * math.pi * 2 * b["f"] * qq)
            pop = 1 + 0.5 * smooth(qq, 0.94, 1.0)
            return (w * pop, (2 - w) * pop)
        c.bone_keys(b["b"], "scale", tsd, sc)
        c.color_keys(b["s"], tsd, lambda u, q=q: hexa("FFFFFF", c.a(smooth(q(u), 0.0, 0.08) * (1 - smooth(q(u), 0.94, 1.0)))))
    return c.result(duration=D * c.k, loop=D, bubbles=n)


def water_splash(c: Ctx, P: dict) -> dict:
    """A splash: droplets thrown up on parabolas (stretched along their speed), two ripple rings on the surface, mist."""
    D = 1.3
    col = _hexn(P["color"], "8FD8FF")
    n = int(P["count"])
    sp0 = float(P["speed"])
    g = float(P["gravity"])
    rng = np.random.default_rng(c.seed + 151)
    grp = c.bone("splash", c.group, 0, 0)
    rings = []
    for i in range(2):
        rb = c.bone(f"ring{i}", grp, sy=0.28)
        rs = c.slot(rb, "fx/ring", float(P["size"]) * 1.6, role="ring")
        rings.append((rb, rs, i * 0.18))
    b_m = c.bone("mist", grp, 0, 20)
    s_m = c.slot(b_m, "fx/smoke", float(P["size"]) * 1.4, blend="additive", role="mist")
    drops = []
    for i in range(n):
        a = math.radians(90 + float(rng.uniform(-62, 62)))
        sp = sp0 * float(rng.uniform(0.55, 1.05))
        bn = c.bone(f"d{i}", grp)
        sl = c.slot(bn, "fx/drop", float(rng.uniform(15, 32)) * float(P["size"]) / 100, make=lambda: tex_drop(), role="drop")
        drops.append(dict(b=bn, s=sl, vx=math.cos(a) * sp, vy=math.sin(a) * sp, t0=float(rng.uniform(0, 0.07))))
    c.show([r[1] for r in rings] + [s_m] + [d["s"] for d in drops], 0, D)
    ts = times_dense(0, D, 30)
    for rb, rs, d0 in rings:
        c.bone_keys(rb, "scale", ts, lambda u, d0=d0: (0.15 + 1.25 * ease_out((u - d0) / 0.9, 2.2) if u >= d0 else 0.0,) * 2)
        c.color_keys(rs, ts, lambda u, d0=d0: hexa(col, c.a(0.8 * (1 - smooth(u, d0, d0 + 0.9)) * smooth(u, d0, d0 + 0.04))))
    c.bone_keys(b_m, "scale", ts, lambda u: (0.3 + 0.9 * ease_out(u / 0.6, 2.2),) * 2)
    c.color_keys(s_m, ts, lambda u: hexa("E8F8FF", c.a(0.45 * smooth(u, 0, 0.06) * (1 - smooth(u, 0.15, 0.9)))))
    for d in drops:
        t0 = d["t0"]

        def st(u, d=d, t0=t0):
            t = max(0.0, u - t0)
            vx, vy = d["vx"], d["vy"] - g * t
            x, y = d["vx"] * t, d["vy"] * t - 0.5 * g * t * t
            ang = math.degrees(math.atan2(vy, vx)) - 90.0          # the drop's pointed end trails its motion
            stretch = 1 + 0.7 * min(1.0, math.hypot(vx, vy) / max(sp0, 1))
            return x, y, ang, stretch
        vals = [st(u) for u in ts]
        ang = np.degrees(np.unwrap(np.radians([v[2] for v in vals])))
        c.ab.bone(d["b"], "translate", _uniq([(c.T(u), v[0], v[1]) for u, v in zip(ts, vals)]), "linear")
        c.ab.bone(d["b"], "rotate", _uniq([(c.T(u), float(a)) for u, a in zip(ts, ang)]), "linear")
        c.ab.bone(d["b"], "scale", _uniq([(c.T(u), 1 / math.sqrt(v[3]), v[3]) for u, v in zip(ts, vals)]), "linear")
        c.color_keys(d["s"], ts, lambda u, t0=t0: hexa("FFFFFF", c.a(smooth(u, t0, t0 + 0.04) * (1 - smooth(u, 0.85, D)))))
    c.ab.event(c.T(0.0), "fx_splash")
    return c.result(duration=D * c.k, drops=n)


# ------------------------------------------------------------------ registry
RECIPES.update({
    "frost": dict(
        fn=frost, duration=2.4, kind="window", color="9FD8FF",
        summary="Frost ferns grow across a box (from its borders, or from the centre like a snowflake) as a generated "
                "flipbook: branches at the 60 degrees of ice crystals, a frosted film building up, a cold glow, glints. Event fx_frost_done.",
        anchor="Box centre.",
        options=dict(width=(200.0, "box width"), height=(200.0, "box height"), mode=("edges", "edges | center"),
                     grow=(1.4, "seconds to fully freeze"), frames=(18, "flipbook frames"), glints=(6, "sparkles after it freezes"),
                     blend=("normal", "normal (white frost) | additive (glowing frost)"), fade=(0.0, "seconds to fade out at the end (0 = stays)"))),
    "icicles": dict(
        fn=icicles, duration=3.0, kind="window", color="9FD8FF",
        summary="Icicles grow down from the top edge of a box, a frost crust forms along it, glints run down them and "
                "water drops swell at the tips and fall.",
        anchor="Box centre; icicles hang from its top edge.",
        options=dict(width=(220.0, "box width"), height=(160.0, "box height"), length=(110.0, "longest icicle"),
                     grow=(0.8, "seconds for one icicle to grow"), drips=(True, "drops fall from the tips"))),
    "ice_shatter": dict(
        fn=ice_shatter, duration=1.6, kind="one-shot", color="9FD8FF",
        summary="Freeze and break: an ice block forms over the target, cracks (Voronoi crack lines), then shatters into shards "
                "that fly out and fall, with a cold mist and a ring. Events fx_ice_crack and fx_ice_shatter.",
        anchor="Target centre.",
        options=dict(size=(200.0, "ice block size"), crack=(0.45, "seconds when it cracks"),
                     shatter=(0.75, "seconds when it shatters"))),
    "bubbles": dict(
        fn=bubbles, duration=4.0, kind="loop", color="",
        summary="Bubbles rise through a box, wobbling and squishing, and pop at their top; clear centres, fresnel rims, "
                "specular window. Loops exactly.",
        anchor="Box centre.",
        options=dict(width=(160.0, "box width"), height=(300.0, "box height"), size=(1.0, "size multiplier"))),
    "water_splash": dict(
        fn=water_splash, duration=1.3, kind="one-shot", color="8FD8FF",
        summary="A splash: droplets thrown up on parabolas, stretched along their speed, two ripple rings on the surface, a mist. Event fx_splash.",
        anchor="Point of impact on the water surface.",
        options=dict(speed=(520.0, "launch speed"), gravity=(1500.0, "gravity"), size=(100.0, "ring/mist size"))),
})
# count= (the shared argument) is the number of icicles / shards / bubbles / droplets
for _n, _k in (("icicles", 7), ("ice_shatter", 14), ("bubbles", 16), ("water_splash", 18)):
    RECIPES[_n]["count"] = _k
ROLES.update({
    "frost": {"glow": "the cold glow behind", "spark": "one glint"},
    "icicles": {"icicle": "one icicle, ROOT at the TOP, tip at the bottom", "rim": "the frost crust along the edge (edge at the TOP)",
                "drop": "one water drop", "spark": "the glint running down"},
    "ice_shatter": {"block": "the ice block (normal blend)", "crack": "the crack lines over it", "glow": "cold glow", "mist": "the mist puff",
                    "ring": "the burst ring"},
    "bubbles": {"bubble": "one bubble, round, centred"},
    "water_splash": {"drop": "one droplet, pointed end UP (it is turned along its motion)", "ring": "the ripple ring", "mist": "the mist"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
