"""Prop recipes for ``fx_recipe``: idle life for a symbol / prop the artist already rigged (a potion, a chest, a jar,
a lantern), measured from a reference clip of a potion symbol.

They drive YOUR bones through inserted carrier bones (``fx_reels._carrier``), never your own keys:

* ``prop_idle``     the prop breathes: grows ~17 % while tilting clockwise, holds, shrinks back with a small counter-tilt
                    overshoot; an optional glow behind it pulses with the size. One seamless loop.
* ``liquid_slosh``  the liquid inside sloshes against the tilt and lags it (the surface angle is driven in WORLD space,
                    so it stays right whatever the prop does), with an optional clipping mask that trims the liquid
                    layers to the vessel (circle or polygon).

Use them together on one animation (into=) with the same duration: the slosh reads the prop's tilt curve.
"""
from __future__ import annotations

import math

from .fx_pinata import PICS
from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, hexa, times_dense
from .ir import ClippingAttachment, Slot

FPS = 30
# measured from the reference clip (u = 0..1 over the loop)
SCALE = [(0.0, 0.0), (0.48, 1.0), (0.62, 0.88), (0.92, 0.0), (1.0, 0.0)]          # 0..1 of `grow`
TILT = [(0.0, 0.0), (0.45, -1.0), (0.62, -0.57), (0.84, 0.29), (1.0, 0.0)]          # x `tilt` (deg, - = clockwise)
SURF = [(0.0, 0.69), (0.2, 0.46), (0.5, -0.46), (0.66, -0.23), (0.86, 1.0), (1.0, 0.69)]  # x `slosh` (deg, world)


def _ss(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def keyed(u, pts):
    for (u0, v0), (u1, v1) in zip(pts, pts[1:]):
        if u0 <= u <= u1:
            return v0 + (v1 - v0) * _ss((u - u0) / max(u1 - u0, 1e-9))
    return pts[-1][1]


def _times(D, stepped, cycles=1):
    total = D * max(1, int(cycles))
    n = max(2, int(round(total * FPS)))
    ts = [total * i / n for i in range(n + 1)]
    return ts[::2] + ([ts[-1]] if n % 2 else []) if stepped else ts


def _u(t, D):
    """Phase 0..1 inside the current cycle (the last key of the last cycle reads 1.0, not 0)."""
    q = t / D
    return 1.0 if q > 0 and abs(q - round(q)) < 1e-9 else q % 1.0


def _key(c: Ctx, bone: str, timeline: str, ts, fn, stepped: bool):
    pts = []
    for t in ts:
        v = fn(t)
        pts.append((c.T(t), *(v if isinstance(v, tuple) else (v,))))
    c.ab.bone(bone, timeline, pts, "stepped" if stepped else "linear")


def _descendants(sk, bone):
    kids = {bone}
    grew = True
    while grew:
        grew = False
        for b in sk.bones:
            if b.parent in kids and b.name not in kids:
                kids.add(b.name)
                grew = True
    return kids


def prop_idle(c: Ctx, P: dict) -> dict:
    from .fx_reels import _carrier, _merge_keys
    D, stepped, N = float(P["duration"]), bool(P["stepped"]), max(1, int(P["cycles"]))
    sk = c.sk
    grow, tilt = float(P["grow"]), float(P["tilt"])
    ts = _times(D, stepped, N)
    sc = lambda t: 1 + grow * keyed(_u(t, D), SCALE)  # noqa: E731
    if P["prop"]:                                   # your prop: carriers above its bone, your keys untouched
        prop = str(P["prop"])
        if not sk.has_bone(prop):
            raise ValueError(f"no bone {prop!r} for the prop")
        w = sk.world()
        at = tuple(float(v) for v in P["pivot"]) if P["pivot"] else (w[prop].x, w[prop].y)
        car_s = _carrier(c, prop, "propgrow", at)
        car_r = _carrier(c, prop, "proptilt", at)
        _merge_keys(c, car_s, "scale", ts, lambda u: (sc(u), sc(u)), "mul")
    else:                                           # no prop: our own bone (parent your art to it), glow on by default
        prop = car_s = car_r = c.bone("prop")
        at = (sk.world()[c.group].x, sk.world()[c.group].y)
        _key(c, car_s, "scale", ts, lambda t: (sc(t), sc(t)), stepped)
        P = dict(P, glow=P["glow"] or 260.0)
    _key(c, car_r, "rotate", ts, lambda t: tilt * keyed(_u(t, D), TILT), stepped)
    res = dict(duration=D * N, loop=D * N, carriers=[car_s, car_r] if car_s != car_r else [], prop_bone=prop, pivot=list(at))
    if P["glow"]:
        col = _hexn(P["color"], "FF4FE0")
        under = [s.name for s in sk.slots if s.bone in _descendants(sk, prop)]
        if under and not c.behind and not c.front_of:
            c.behind = under[0]                     # the glow goes under the prop's first layer
        g = c.bone("glow")
        s = c.slot(g, "fx/pinata_glow_soft", float(P["glow"]), make=PICS["glow_soft"], role="glow")
        c.show([s], 0, None)
        if P["prop"]:                                # glow centred on the pivot (world = root space here)
            gb = sk.bones[[b.name for b in sk.bones].index(c.group)]
            gb.parent, gb.x, gb.y = "root", at[0], at[1]
        _key(c, g, "scale", ts, lambda t: (1 + 0.35 * grow * keyed(_u(t, D), SCALE),) * 2, stepped)
        c.ab.slot_color(s, [(c.T(t), hexa(col, c.a(0.65 + 0.35 * keyed(_u(t, D), SCALE)))) for t in ts],
                        "stepped" if stepped else "linear")
        res["glow_slot"] = s
    return c.result(**res)


def liquid_slosh(c: Ctx, P: dict) -> dict:
    from .fx_reels import _carrier, _merge_keys
    D, stepped, N = float(P["duration"]), bool(P["stepped"]), max(1, int(P["cycles"]))
    sk = c.sk
    slosh, tilt, shift = float(P["slosh"]), float(P["tilt"]), float(P["shift"])
    ts = _times(D, stepped, N)
    if P["liquid"]:
        liq = str(P["liquid"])
        if not sk.has_bone(liq):
            raise ValueError(f"no bone {liq!r} for the liquid")
        vessel = sk.bone(liq).parent                # the clip rides the vessel, not the slosh
        car = _carrier(c, liq, "slosh")
    else:                                           # no liquid bone: our own, with a surface line to show the slosh
        vessel = c.group
        car = liq = c.bone("liquid")
        s = c.slot(liq, "fx/pinata_light_streak", 240.0, height=40.0, make=PICS["light_streak"], role="surface")
        c.show([s], 0, None)
        tilt = 0.0 if not P["tilt"] else tilt
    world = lambda t: slosh * keyed(_u(t, D), SURF)  # noqa: E731   the lag behind the tilt is built into SURF
    # the prop's own tilt (prop_idle with the same tilt) is inherited: subtract it so the surface angle is the WORLD one
    local = lambda t: world(t) - tilt * keyed(_u(t, D), TILT)  # noqa: E731
    _key(c, car, "rotate", ts, local, stepped)
    if P["liquid"]:
        _merge_keys(c, car, "translate", ts, lambda t: (shift * world(t) / max(abs(slosh), 1e-9), 0.0), "add")
    else:
        _key(c, car, "translate", ts, lambda t: (shift * world(t) / max(abs(slosh), 1e-9), 0.0), stepped)
    res = dict(duration=D * N, loop=D * N, carrier=car, vessel=vessel)
    if P["clip"]:
        layers = [s.name for s in sk.slots if s.bone in _descendants(sk, liq)]
        if not layers:
            raise ValueError(f"no slots hang from {liq!r} to clip")
        first, last = (P["clip_slots"] or [layers[0], layers[-1]])[:2]
        clip = P["clip"]
        if isinstance(clip, (int, float)):          # a circle: radius around clip_center in the vessel's space
            cx, cy = (float(v) for v in P["clip_center"])
            n = 16
            verts = []
            for i in range(n):
                a = 2 * math.pi * i / n
                verts += [round(cx + float(clip) * math.cos(a), 2), round(cy + float(clip) * math.sin(a), 2)]
        else:                                        # a polygon [[x, y], ...] in the vessel's space, counter-clockwise
            verts = [round(float(v), 2) for pt in clip for v in pt]
        name = sk.unique_name(f"fx_clip_{liq}", "slot")
        sk.add_slot(Slot(name=name, bone=vessel, attachment=name), before=first)
        sk.set_attachment(name, name, ClippingAttachment(end=last, vertexCount=len(verts) // 2, vertices=verts))
        res.update(clip_slot=name, clipped=[first, last])
    return c.result(**res)


RECIPES.update({
    "prop_idle": dict(
        fn=prop_idle, duration=0.755, kind="window", color="FF4FE0",
        summary="Idle life for a rigged prop / symbol (measured from a potion symbol): it grows ~17 % while tilting clockwise, "
                "holds, shrinks back with a small counter-tilt overshoot; optional glow behind it pulsing with the size. "
                "Drives your bone through carriers (your keys untouched). Seamless loop of `duration`.",
        anchor="Ignored for the motion (the pivot is the prop bone's origin or `pivot`); the glow sits on the pivot.",
        options=dict(prop=("", "the prop's root bone (empty: a bone of the recipe's own; parent your art to it)"), pivot=(None, "[x, y] world pivot (default: the bone's origin)"),
                     grow=(0.17, "extra scale at the peak (0.17 = +17 %)"), tilt=(14.0, "peak tilt, degrees (clockwise)"),
                     glow=(0.0, "> 0: add a pulsing glow this wide behind the prop"),
                     stepped=(False, "hold every pose 2 frames (the hand-drawn flipbook look)"),
                     cycles=(1, "repeat the cycle N times (duration stays ONE cycle): match a longer loop"))),
    "liquid_slosh": dict(
        fn=liquid_slosh, duration=0.755, kind="window", color="",
        summary="Liquid sloshing in a vessel: the surface angle is driven in WORLD space (it swings against the vessel's tilt "
                "and lags it), the mass shifts to the low side; optional clipping mask (circle radius or polygon) that trims "
                "the liquid layers to the vessel. Pair with prop_idle (same duration and tilt) via into=.",
        anchor="Ignored (works on your liquid bone).",
        options=dict(liquid=("", "bone the liquid layers hang from, placed on the surface line (empty: our own + a surface line)"),
                     slosh=(26.0, "peak surface swing, degrees in the world"), shift=(21.0, "sideways mass shift at the peak"),
                     tilt=(14.0, "the vessel's tilt from prop_idle (0 if the vessel does not tilt)"),
                     clip=(0.0, "radius (circle) or [[x, y], ...] polygon in the vessel bone's space; 0 = no mask"),
                     clip_center=([0.0, 0.0], "circle centre in the vessel bone's space"),
                     clip_slots=(None, "[first, last] slots to clip (default: every slot on the liquid bone)"),
                     stepped=(False, "hold every pose 2 frames"),
                     cycles=(1, "repeat the cycle N times (duration stays ONE cycle)"))),
})
ROLES["prop_idle"] = {"glow": "soft round glow behind the prop (additive, white: tinted by color)"}
ROLES["liquid_slosh"] = {"surface": "the surface line shown when no liquid bone is given (additive)"}
for _n in ("prop_idle", "liquid_slosh"):
    RECIPES[_n]["roles"] = ROLES[_n]
