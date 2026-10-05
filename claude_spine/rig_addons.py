"""Add-on rigs: ``attach_rig`` plugs a small sub-rig into a named bone of ANY existing rig (a biped from rig_biped,
an import_psd project, the procedural host below) and MERGES its clips into the host's clips by name.

    ears         (head)   2-bone strands with physics; ear_perk, ear_flatten, ear_swivel (toward a sound); idle twitches
    tail         (hips)   strand with physics; tail_mood happy (slow, wide) | alert (still, raised) | angry (tip twitches)
    wings        (chest)  rig_flier wing pair (feathered | bat | insect); idle = slow breathing fold, excited = flutter
    horns        (head)   rigid, with a tiny inertia lag on head turns (physics on SHEAR only)
    digitigrade  (hips)   3-bone legs (thigh, shin, metatarsus) with the reversed hock; IK feet, a stepping walk
    mermaid      (hips)   a rig_serpent chain replacing the legs (they are hidden); swim and idle_float
    snake_hair   (head)   8-12 serpents, each with its own randomised idle wave and a shared head-look IK
    fur          (any)    physics on a few outline bones of a mesh, so the silhouette ruffles; a wind gust clip
    glow         (any)    the FX ``shine`` pulse or ``electric_frame`` on eyes / runes / veins, through fx_recipes.apply,
                          tiled into the host clips (FX and character rigs share one event system)

Clip merge rules (``rig_chain.merge_clips``): a clip the host already has keeps the host's length; loop content refits
its period so a whole number of cycles divides it exactly (``loops kept exact``); loop content landing in a host
one-shot is faded in and out so the one-shot still ends on setup; one-shots are retimed to the host's length. A clip
the host does not have is created at the add-on's own length (except pure reactions such as tail ``walk``).

Exaggerated real physics, as modelled: ear perks are the step response of an underdamped spring (overshoot exactly
exp(-pi z / sqrt(1 - z^2))), ear twitches and tail-tip flicks are its impulse response at seeded times, the far ear
turns to a sound later than the near one; a happy tail is a travelling wave (phase lag down the chain); horns lag
by shear because they are stiff (high strength, low inertia); digitigrade feet are planted (constant ground speed in
stance, a sine lift in swing, duty factor 0.6 walk / 0.4 run); fur ruffles under a wind gust acting on Spine physics.

Every part is found BY LAYER NAME (``ADDON_LAYERS``; case-insensitive, the last part of a flattened PSD path counts).
Events: ``sfx_ear_perk``, ``sfx_ear_flatten``, ``sfx_ear_swivel``, ``sfx_step`` (string field = l | r),
``sfx_snake_look``, ``sfx_fur_ruffle``, the FX events (``fx_shine`` / ``fx_electric_frame``, one per pulse) and the
rig_chain ones (``sfx_swim``).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .ir import EventKey, Key, MeshAttachment, RegionAttachment, SkeletonData, _wrap, new_skeleton
from .mesh import mesh_world_vertices, rig_mesh
from .project import Project
from .rig import add_chain, add_ik, reparent_slot
from .rig_chain import (FOLD, FOLD_SX, ClipSpec, Flier, Sheet, add_phys, base_name, build_serpent, build_wing,
                        centerline_world, ellipse_poly, event, find_bone, find_numbered, find_prefixed,
                        find_slot, fit_period, frame_bone, key_wave, key_wings, merge_clips, put, serpent_clips,
                        slot_bounds, smooth, spline, spring_kick, spring_overshoot, spring_step, strip_shape, times,
                        upstroke, warp)
from .timeline import AnimBuilder

KINDS = ("ears", "tail", "wings", "horns", "digitigrade", "mermaid", "snake_hair", "fur", "glow")

ADDON_LAYERS = {
    "ears": "ear_l, ear_r (or ear): one layer per ear, pointing away from the head",
    "tail": "tail: one layer; the root is the end nearest the attach bone",
    "wings": "wing_l, wing_r (at least one) + optional wing_<side>_feather<N> primaries",
    "horns": "horn_l, horn_r, horn, antler_l, antler_r, antler<N>: the base is the end nearest the head",
    "digitigrade": "leg_l, leg_r (thigh-shin-metatarsus drawn as one zigzag layer each) + optional foot_l/_r (paw_, hoof_)",
    "mermaid": "mermaid_tail (or fishtail) + optional fluke; leg*/foot*/shoe*/boot*/paw* layers are hidden",
    "snake_hair": "snake<N> / hair_snake<N> / snake_hair<N> (8-12 of them), each rooted on the scalp",
    "fur": "options.slots, or layers starting with fur, coat, mane, ruff, fleece",
    "glow": "options.slots, or layers starting with eye, rune, vein, glow, gem, crystal",
}
BONES = {
    "ears": ("head",), "horns": ("head",), "snake_hair": ("head",),
    "tail": ("hips", "hip", "pelvis", "spine1", "body"), "mermaid": ("hips", "hip", "pelvis", "body"),
    "digitigrade": ("hips", "hip", "pelvis", "body"),
    "wings": ("chest", "torso", "spine2", "upper_body", "spine", "body"),
    "fur": (), "glow": (),
}

# options per kind: {name: (default, what)}
OPTIONS: dict[str, dict[str, tuple[Any, str]]] = {
    "ears": dict(n_bones=(2, "bones per ear"), physics=("ear", "physics preset (rig_chain.PHYSICS / rig presets) or none"),
                 perk=(25.0, "max perk rotation toward the head's up (deg)"), zeta=(0.3, "perk spring damping ratio (overshoot)"),
                 flatten=(55.0, "flatten rotation away from up (deg)"), swivel=(35.0, "max swivel toward the sound (deg)"),
                 sound=([320.0, 60.0], "the sound source for ear_swivel: [dx, dy] world offset from the head"),
                 twitches=(2, "ear twitches per idle loop")),
    "tail": dict(n_bones=(5, "bones in the tail"), physics=("tail", "physics preset or none"),
                 tail_mood=("happy", "idle mood: happy (slow wide wag) | alert (still, raised) | angry (tip twitches)"),
                 amp=(14.0, "wag amplitude per joint at the tip (deg)"), hz=(0.8, "happy wag frequency (Hz)"),
                 lag=(0.12, "wave phase lag per joint (cycles): the wag travels to the tip")),
    "wings": dict(wing_type=("feathered", "feathered | bat | insect"), flap_hz=(0.0, "excited flutter frequency (0 = by type)"),
                  breath=(3.0, "idle breathing period (s)"), physics=("feather", "feather physics preset or none")),
    "horns": dict(strength=(320.0, "stiffness of the lag spring"), inertia=(0.5, "how much the horn resists the head's motion")),
    "digitigrade": dict(stride=(0.45, "walk stride as a fraction of leg length"), lift=(0.18, "foot lift as a fraction of leg length"),
                        duty=(0.6, "walk duty factor (fraction of the cycle a foot is planted)"),
                        facing=(1.0, "+1 the character walks toward +x, -1 toward -x"),
                        ground=("", "bone the IK targets live under (default: the attach bone's parent)")),
    "mermaid": dict(n_bones=(6, "bones in the fish tail"), speed=(0.8, "swim speed (body lengths/s)"),
                    wavelength=(1.2, "body wave length (body lengths)"), head_amp=(0.1, "wave amplitude at the hips (share)"),
                    exaggerate=(1.3, "x the Strouhal tail amplitude"), hide=(None, "leg layers to hide (default: by name)")),
    "snake_hair": dict(n_bones=(3, "bones per snake"), look=([260.0, 40.0], "snake_look target: [dx, dy] world offset from the head"),
                       amp=(0.14, "idle wave amplitude (fraction of a snake's length)"), seed=(7, "random seed for the idles"),
                       detail=(0.5, "mesh detail per snake (ten snakes add up)"),
                       max_turn=(45.0, "most a snake's head turns toward the look target (deg)")),
    "fur": dict(slots=(None, "slots to ruffle (default: by name)"), count=(6, "outline bones per slot"),
                wind=(32.0, "fur_ruffle gust strength (Spine physics wind; offset ~ wind x 100 / strength px)"),
                detail=(1.0, "mesh detail")),
    "glow": dict(slots=(None, "slots that glow (default: by name)"), fx=("auto", "shine | electric_frame | auto (runes/veins electric)"),
                 clips=(["idle"], "host clips to glow in (missing ones are created)"), period=(1.2, "pulse period (s)"),
                 color=("", "glow colour (default: the part's own colour if bright, else the recipe's)"),
                 size=(0.8, "glow size relative to the part"),
                 intensity=(0.85, "alpha gain"),
                 on_top=("auto", "true: glow at the top of the draw order (one extra batch); false: right above its part "
                                 "(covered by what covers the part, two extra batches); auto: eyes on top, runes/veins above their part")),
}


def _opts(kind: str, options: dict | None) -> dict:
    d = OPTIONS[kind]
    P = {k: v[0] for k, v in d.items()}
    bad = [k for k in (options or {}) if k not in P]
    if bad:
        raise ValueError(f"unknown option(s) {bad} for {kind!r}; valid: {sorted(P)}")
    P.update(options or {})
    return P


def _bone_mid(sk: SkeletonData, bone: str) -> tuple[float, float]:
    w = sk.world()[bone]
    if w.length > 0:
        return w.to_world(w.length / 2, 0)
    return w.x, w.y


def _up(sk: SkeletonData, bone: str) -> float:
    w = sk.world()[bone]
    return w.rotation if w.length > 0 else 90.0


def _need(sk: SkeletonData, kind: str, slots: list[str]) -> None:
    if not slots:
        raise ValueError(f"attach_rig {kind}: no layers found. Naming convention (case-insensitive): {ADDON_LAYERS[kind]}. "
                         f"Slots in the project: {[s.name for s in sk.slots]}")


def _ctrl_chain(project: Project, slot: str, n: int, parent: str, name: str, root_near) -> tuple[str, list[str], np.ndarray]:
    """A control bone at the strand's root (pointing along it) and the chain under it: keys go on the control,
    physics on the chain, so physics bones are never keyed."""
    sk = project.data
    pts = centerline_world(project, slot, n, root_near)
    d = pts[-1] - pts[0]
    ctrl = frame_bone(sk, f"{name}_ctrl", parent, pts[0][0], pts[0][1], math.degrees(math.atan2(d[1], d[0])), color="FFD400FF")
    bones = add_chain(sk, name, pts.tolist(), ctrl)
    rig_mesh(project, slot, bones=bones)
    return ctrl, bones, pts


# ================================================================== ears
def _ears(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    ears = [s for s in (find_slot(sk, "ear_l"), find_slot(sk, "ear_r")) if s] or [s for s in (find_slot(sk, "ear"),) if s]
    _need(sk, "ears", ears)
    head_c = _bone_mid(sk, bone)
    up = _up(sk, bone)
    E = []
    phys = []
    for es in ears:
        tag = base_name(es)
        ctrl, bones, pts = _ctrl_chain(project, es, int(P["n_bones"]), bone, f"{name}{tag}", head_c)
        if P["physics"] != "none":
            phys += add_phys(sk, bones, P["physics"])
        ang = math.degrees(math.atan2(*(pts[-1] - pts[0])[::-1]))
        to_up = _wrap(up - ang)
        E.append(dict(slot=es, ctrl=ctrl, bones=bones, base=pts[0], ang=ang, to_up=to_up,
                      out=-1.0 if to_up > 0 else 1.0))       # rotating by `out` turns the ear away from up
    perk, z = float(P["perk"]), float(P["zeta"])
    if not 0.02 <= z <= 0.95:
        raise ValueError("zeta is a damping ratio, 0.02..0.95 (lower overshoots more)")
    sound = np.array(head_c) + np.array(P["sound"], float)
    rng = np.random.default_rng(11)

    def perk_b(ab, D, env):
        t0, rel = 0.06 * D, 0.6 * D
        ts = times(D, 60, [t0, rel])
        hz = 3.0 / max(D, 0.3)

        def base(t):                                                # a tiny dip first (anticipation), then the spring
            return -0.15 * smooth(t, 0, t0) * (1 - smooth(t, t0, t0 + 0.05 * D)) + spring_step(t - t0, hz, z)

        def q(t):
            return base(t) if t < rel else base(rel) * (1 - smooth(t, rel, D))
        tg = {}
        for e in E:
            tgt = max(-perk, min(perk, 0.7 * e["to_up"])) or 0.0
            tg[e["slot"]] = round(tgt, 4)
            put(ab, e["ctrl"], "rotate", ts, lambda t, tgt=tgt: tgt * q(t))
            put(ab, e["ctrl"], "scale", ts, lambda t: (1 + 0.12 * q(t), 1.0))
        event(ab, 0.0, "sfx_ear_perk")
        return {"overshoot": round(spring_overshoot(z), 4), "targets": tg}

    def flatten_b(ab, D, env):
        hold = 0.6 * D
        ts = times(D, 60, [hold])
        hz = 2.2 / max(D, 0.3)

        def q(t):
            if t < hold:
                return ease(t / (0.12 * D))
            return (1 - spring_step(t - hold, hz, 0.4)) * (1 - smooth(t, D - 0.12 * D, D))
        for e in E:
            put(ab, e["ctrl"], "rotate", ts, lambda t, e=e: e["out"] * float(P["flatten"]) * q(t))
            put(ab, e["ctrl"], "scale", ts, lambda t: (1 - 0.3 * q(t), 1 - 0.1 * q(t)))   # folds back: foreshortened
        event(ab, 0.0, "sfx_ear_flatten")
        return {}

    def swivel_b(ab, D, env):
        ts = times(D, 60)
        dist = [float(np.hypot(*(sound - e["base"]))) for e in E]
        hz = 2.5 / max(D, 0.3)
        for e, dd in zip(E, dist):
            dl = 0.0 if dd <= min(dist) + 1e-6 else 0.08 * D             # the far ear turns later
            th = math.degrees(math.atan2(*(sound - e["base"])[::-1]))
            turn = max(-float(P["swivel"]), min(float(P["swivel"]), 0.5 * _wrap(th - e["ang"])))
            q = lambda t, dl=dl: spring_step(t - 0.05 * D - dl, hz, 0.45) * (1 - smooth(t, 0.68 * D, D))  # noqa: E731
            put(ab, e["ctrl"], "rotate", ts, lambda t, q=q, turn=turn: turn * q(t))
            put(ab, e["ctrl"], "scale", ts, lambda t, q=q: (1.0, 1 - 0.25 * q(t)))           # the opening turns edge-on
            e["swivel_delay"] = round(dl, 4)
        event(ab, 0.05 * D, "sfx_ear_swivel")
        return {"sound": [round(float(v), 1) for v in sound], "delays": [e["swivel_delay"] for e in E]}

    def idle_b(ab, D, env):
        n = int(P["twitches"])
        ts = times(D, 60)
        out = []
        for e in E:
            tw = sorted(float(v) for v in rng.uniform(0.1 * D, max(0.12 * D, D - 0.6), n)) if n > 0 else []
            out.append([round(v, 3) for v in tw])
            put(ab, e["ctrl"], "rotate", ts, lambda t, tw=tw, e=e: env(t) * e["out"] * 8.0 * sum(spring_kick(t - x, 6.0, 0.25) for x in tw)
                * (1 - smooth(t, D - 0.08 * D, D)), True)
        return {"twitches": out}
    specs = [ClipSpec("ear_perk", "oneshot", 1.0, perk_b), ClipSpec("ear_flatten", "oneshot", 1.5, flatten_b),
             ClipSpec("ear_swivel", "oneshot", 1.6, swivel_b), ClipSpec("idle", "loop", 2.4, idle_b)]
    return {"ears": {e["slot"]: {"control": e["ctrl"], "bones": e["bones"]} for e in E}, "physics": phys}, specs


def ease(u: float, p: float = 3.0) -> float:
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** p


# ================================================================== tail
def _tail(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    ts_ = find_slot(sk, "tail")
    _need(sk, "tail", [ts_] if ts_ else [])
    mood = str(P["tail_mood"])
    if mood not in ("happy", "alert", "angry"):
        raise ValueError(f"tail_mood is happy | alert | angry, got {mood!r}")
    w = sk.world()[bone]
    ctrl, bones, pts = _ctrl_chain(project, ts_, int(P["n_bones"]), bone, f"{name}tail", (w.x, w.y))
    phys = add_phys(sk, bones, P["physics"]) if P["physics"] != "none" else []
    n = len(bones)
    up = _up(sk, bone)
    ang = math.degrees(math.atan2(*(pts[-1] - pts[0])[::-1]))
    raise_ = max(-25.0, min(25.0, _wrap(up - ang)))
    A, lag = float(P["amp"]), float(P["lag"])
    rng = np.random.default_rng(23)

    def wag(ab, D, env, hz, amp_k=1.0):
        k, Pd = fit_period(D, 1 / hz)
        f = 1 / Pd
        ts = times(D, max(30, 16 * f))
        put(ab, ctrl, "rotate", ts, lambda t: env(t) * 0.8 * A * amp_k * math.sin(2 * math.pi * f * t), True)
        for i, b in enumerate(bones):
            ai = A * amp_k * (0.35 + 0.65 * i / max(n - 1, 1))
            put(ab, b, "rotate", ts, lambda t, i=i, ai=ai: env(t) * ai * math.sin(2 * math.pi * (f * t - (i + 1) * lag)), True)
        return {"cycles": k, "frequency": round(f, 4)}

    def happy(ab, D, env):
        return {"mood": "happy", **wag(ab, D, env, float(P["hz"]))}

    def alert(ab, D, env):
        ts = [0.0, D]
        put(ab, ctrl, "rotate", ts, lambda t: env(t) * raise_, True)
        for b in bones:
            put(ab, b, "rotate", ts, lambda t: 0.0, True)
        return {"mood": "alert", "raised": round(raise_, 2)}

    def angry(ab, D, env):
        ts = times(D, 60)
        rate = 2.5
        tw = []
        t = float(rng.exponential(1 / rate)) * 0.5
        while t < D - 0.45:                                       # Poisson flicks, each one done before the loop wraps
            tw.append((t, 1.0 if len(tw) % 2 == 0 else -1.0))
            t += float(rng.exponential(1 / rate)) + 0.12
        put(ab, ctrl, "rotate", ts, lambda t: env(t) * 10.0 * math.sin(2 * math.pi * t / D), True)   # slow lash at the base
        for i, b in enumerate(bones):
            tip = max(0.0, (i - (n - 3)) / 2)                        # the last two bones flick
            put(ab, b, "rotate", ts, lambda t, tip=tip: env(t) * tip * 25.0 * sum(s * spring_kick(t - x, 9.0, 0.3) for x, s in tw)
                * (1 - smooth(t, D - 0.06, D)), True)
        return {"mood": "angry", "twitches": [round(x, 3) for x, _ in tw]}
    by_mood = {"happy": happy, "alert": alert, "angry": angry}
    specs = [ClipSpec("idle", "loop", 2.0, by_mood[mood]),
             ClipSpec("tail_happy", "loop", 2.0, happy), ClipSpec("tail_alert", "loop", 2.0, alert),
             ClipSpec("tail_angry", "loop", 2.0, angry),
             ClipSpec("walk", "loop", 1.0, lambda ab, D, env: wag(ab, D, env, 1.6, 0.8), create=False),
             ClipSpec("run", "loop", 0.6, lambda ab, D, env: wag(ab, D, env, 2.6, 0.6), create=False),
             ClipSpec("win", "loop", 1.2, lambda ab, D, env: wag(ab, D, env, 3.0, 1.2), create=False)]
    return {"control": ctrl, "bones": bones, "physics": phys, "mood": mood}, specs


# ================================================================== wings
WING_TYPES = {
    #           bones flutter_hz  amp (shoulder, elbow, hand)  fold                     fold_sx
    "feathered": (3, 6.0, (18.0, 6.0, 8.0), FOLD, FOLD_SX),
    "bat":       (3, 4.5, (24.0, 10.0, 12.0), (-55.0, -30.0, -25.0), 0.5),
    "insect":    (1, 11.0, (28.0,), (-25.0,), 0.85),
}


def _wings(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    wt = str(P["wing_type"])
    if wt not in WING_TYPES:
        raise ValueError(f"wing_type is {' | '.join(WING_TYPES)}, got {wt!r}")
    nb, hz0, amp, fold, fold_sx = WING_TYPES[wt]
    hz = float(P["flap_hz"]) or hz0
    pairs = []
    for side in ("l", "r"):
        ws = find_slot(sk, f"wing_{side}")
        if ws:
            fe = find_numbered(sk, f"wing_{side}_feather", f"feather_{side}") if wt == "feathered" else []
            pairs.append((side, ws, fe))
    _need(sk, "wings", [p[1] for p in pairs])
    c = sk.world()[bone].x, sk.world()[bone].y
    wings, phys = [], []
    for side, ws, fe in pairs:
        w, ph = build_wing(project, ws, bone, c, f"{name}wing_{side}", fe, nb, P["physics"])
        if not fe and P["physics"] != "none" and nb > 1:
            ph += add_phys(sk, w.bones[-1:], P["physics"])                 # no feathers: the hand trails instead
        wings.append(w)
        phys += ph
    fl = Flier(frame="", body="", head=None, anchor=None, wings=wings, tail=[], span=0.0, body_h=0.0)
    lag = 30.0 if nb > 1 else 0.0

    def idle(ab, D, env):
        k, Pd = fit_period(D, float(P["breath"]))
        ts = times(D, 30)
        cfold = lambda t: 0.55 + 0.15 * math.sin(2 * math.pi * t / Pd)  # noqa: E731   a slow breath in the half-folded wings
        # half folded = swung back in depth (foreshortened) more than lowered
        key_wings(ab, fl, ts, lambda t: ([env(t) * 0.35 * cfold(t) * fold[min(j, len(fold) - 1)] for j in range(nb)],
                                         1 - env(t) * 1.3 * (1 - fold_sx) * cfold(t), env(t) * cfold(t)), True)
        return {"breaths": k}

    def flutter(ab, D, env, k_amp=1.0):
        k, Pd = fit_period(D, 1 / hz)
        f = 1 / Pd
        ts = times(D, max(30, 12 * f))

        def pose(t):
            rots = []
            for j in range(nb):
                u = f * t - j * lag / 360
                rots.append(env(t) * (k_amp * amp[min(j, len(amp) - 1)] * warp(u, 0.55)
                                      + 0.25 * fold[min(j, len(fold) - 1)] - (6.0 * upstroke(u, 0.55) if j else 0.0)))
            return rots, 1 - env(t) * 0.25 * (1 - fold_sx), env(t) * 0.25
        key_wings(ab, fl, ts, pose, True)
        return {"beats": k, "frequency": round(f, 4)}
    specs = [ClipSpec("idle", "loop", 3.0, idle), ClipSpec("excited", "loop", 1.0, flutter),
             ClipSpec("win", "loop", 1.2, lambda ab, D, env: flutter(ab, D, env, 1.3), create=False)]
    return {"wings": {w.slot: {"bones": w.bones, "feathers": [f for f, _ in w.feathers]} for w in wings},
            "wing_type": wt, "physics": phys}, specs


# ================================================================== horns
def _horns(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    horns = find_prefixed(sk, "horn", "antler")
    _need(sk, "horns", horns)
    head_c = _bone_mid(sk, bone)
    made, phys = {}, []
    for hs in horns:
        pts = centerline_world(project, hs, 1, head_c)
        d = pts[1] - pts[0]
        hb = frame_bone(sk, f"{name}{base_name(hs)}", bone, pts[0][0], pts[0][1], math.degrees(math.atan2(d[1], d[0])))
        sk.bone(hb).length = round(float(np.hypot(*d)), 3)         # physics shear/rotate needs a length
        reparent_slot(sk, hs, hb)
        phys += add_phys(sk, [hb], "horn", strength=float(P["strength"]), inertia=float(P["inertia"]))
        made[hs] = hb
    return {"horns": made, "physics": phys}, []


# ================================================================== digitigrade legs
def _digitigrade(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    legs = [(side, find_slot(sk, f"leg_{side}")) for side in ("l", "r")]
    legs = [(sd, s) for sd, s in legs if s]
    _need(sk, "digitigrade", [s for _, s in legs])
    ground = str(P["ground"]) or (sk.bone(bone).parent or "root")
    sk.bone(ground)
    duty, facing = float(P["duty"]), float(P["facing"])
    if not 0.2 <= duty <= 0.85:
        raise ValueError("duty is the planted fraction of the cycle, 0.2..0.85 (walk ~0.6, run ~0.4)")
    if facing not in (1.0, -1.0):
        raise ValueError("facing is +1 or -1")
    w = sk.world()
    hip = (w[bone].x, w[bone].y)
    L_ = {}
    out = {}
    for side, ls in legs:
        pts = centerline_world(project, ls, 3, hip)
        chain = add_chain(sk, f"{name}leg_{side}", pts.tolist(), bone)     # thigh, shin, metatarsus (the extra bone)
        rig_mesh(project, ls, bones=chain)
        v = [pts[i + 1] - pts[i] for i in range(3)]
        cross = lambda a, b: float(a[0] * b[1] - a[1] * b[0])  # noqa: E731
        knee, hock = cross(v[0], v[1]), cross(v[1], v[2])
        foot = frame_bone(sk, f"{name}foot_{side}_ik", ground, pts[3][0], pts[3][1], 0.0, color="FF3F00FF")
        hockt = frame_bone(sk, f"{name}hock_{side}_ik", foot, pts[2][0], pts[2][1], 0.0, color="FF3F00FF")
        ik1 = add_ik(sk, chain[:2], target=hockt)
        ik2 = add_ik(sk, chain[2:], target=foot)
        fs = find_slot(sk, f"foot_{side}", f"paw_{side}", f"hoof_{side}")
        if fs:
            reparent_slot(sk, fs, foot)                                        # the paw stays flat on the ground
        L_[side] = sum(float(np.hypot(*x)) for x in v)
        out[side] = {"bones": chain, "foot_target": foot, "hock_target": hockt, "ik": [ik1["constraint"], ik2["constraint"]],
                     "knee_bend": "positive" if knee >= 0 else "negative", "hock_bend": "positive" if hock >= 0 else "negative",
                     "reversed": (knee >= 0) != (hock >= 0), "bendPositive": ik1["bendPositive"], "foot_slot": fs}
    sides = [sd for sd, _ in legs]

    def gait(ab, D, env, stride_k=1.0, duty_=duty, lift_k=1.0):
        ts = times(D, 60, [0.5 * D])
        steps = []
        for sd in sides:
            S = float(P["stride"]) * stride_k * L_[sd]
            H = float(P["lift"]) * lift_k * L_[sd]
            ph = 0.5 if sd == "r" else 0.0
            ft = out[sd]["foot_target"]

            def at(t, S=S, H=H, ph=ph):
                u = (t / D + ph) % 1.0
                if u < duty_:                                          # planted: slides back at constant ground speed
                    return facing * (S / 2 - S * u / duty_), 0.0, 0.0
                q = (u - duty_) / (1 - duty_)
                return facing * (-S / 2 + S * (1 - math.cos(math.pi * q)) / 2), H * math.sin(math.pi * q), -15.0 * facing * math.sin(math.pi * q)
            put(ab, ft, "translate", ts, lambda t, at=at: (env(t) * at(t)[0], env(t) * at(t)[1]), True)
            put(ab, ft, "rotate", ts, lambda t, at=at: env(t) * at(t)[2], True)
            tf = round(((1 - ph) % 1.0) * D, 4) % D                      # footfall: u wraps to 0
            steps.append((tf, sd))
        ab.a.events = [e for e in ab.a.events if e.name != "sfx_step"]   # the legs own the footfalls now
        for tf, sd in sorted(steps):
            event(ab, tf, "sfx_step", string=sd)
        return {"footfalls": [[t, s] for t, s in sorted(steps)], "duty": duty_}
    specs = [ClipSpec("walk", "loop", 1.0, gait),
             ClipSpec("run", "loop", 0.6, lambda ab, D, env: gait(ab, D, env, 1.6, 0.4, 1.6), create=False)]
    return {"legs": out, "ground": ground}, specs


# ================================================================== mermaid tail
def _mermaid(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    ms = find_slot(sk, "mermaid_tail", "fishtail", "fish_tail")
    _need(sk, "mermaid", [ms] if ms else [])
    hide = P["hide"]
    if hide is None:
        hide = [s.name for s in sk.slots if base_name(s.name).startswith(("leg", "foot", "shoe", "boot", "paw", "thigh", "shin"))]
    for h in hide:
        sk.slot(h).attachment = None                                    # the fish tail replaces the legs
    w = sk.world()[bone]
    sp = build_serpent(project, ms, int(P["n_bones"]), bone, f"{name}mermaid", root_near=(w.x, w.y))
    fl = find_slot(sk, "fluke", "tail_fin")
    phys = []
    if fl:                                          # a fluke is wider than long: one rigid bone off the tail tip, with physics
        wl = sk.world()[sp.bones[-1]]
        x0, y0, x1, y1 = slot_bounds(project, fl)
        fb = frame_bone(sk, f"{name}fluke", sp.bones[-1], *wl.tail, wl.rotation)
        sk.bone(fb).length = round(max(x1 - x0, y1 - y0) * 0.5, 3)
        reparent_slot(sk, fl, fb)
        phys = add_phys(sk, [fb], "fin")
    kw = dict(speed=float(P["speed"]), wavelength=float(P["wavelength"]), head_amp=float(P["head_amp"]),
              exaggerate=float(P["exaggerate"]))
    specs = serpent_clips(sp, which=("swim", "idle_float"), **kw)
    specs += serpent_clips(sp, which=("idle_float",), names={"idle_float": "idle"}, **kw)
    return {"bones": sp.bones, "frame": sp.frame, "drive": sp.drive, "hidden": hide, "fluke": fl, "physics": phys}, specs


# ================================================================== snake hair
def _snake_hair(project: Project, bone: str, name: str, P: dict):
    sk = project.data
    snakes = find_numbered(sk, "snake", "hair_snake", "snake_hair")
    _need(sk, "snake_hair", snakes)
    head_c = np.array(_bone_mid(sk, bone))
    look0 = frame_bone(sk, f"{name}snake_look", bone, head_c[0], head_c[1], 0.0, color="FF3F00FF")
    rng = np.random.default_rng(int(P["seed"]))
    S = []
    for i, ss in enumerate(snakes):
        sp = build_serpent(project, ss, int(P["n_bones"]), bone, f"{name}snake{i + 1}", root_near=tuple(head_c),
                           detail=float(P["detail"]))
        ik = add_ik(sk, [sp.bones[-1]], target=look0, mix=0.0)
        S.append(dict(sp=sp, ik=ik["constraint"], m=int(rng.integers(1, 3)), ph=float(rng.uniform(0, 2 * math.pi)),
                      a=float(rng.uniform(0.7, 1.3)) * float(P["amp"]), lam=float(rng.uniform(0.8, 1.3)),
                      delay=float(rng.uniform(0, 0.3))))

    def idle(ab, D, env):
        ts = times(D, 30)
        for s in S:
            sp, L = s["sp"], s["sp"].L
            A = lambda x, L=L, a=s["a"]: a * L * (0.25 + 0.75 * (x / L) ** 1.5)  # noqa: E731
            y = lambda x, t, s=s, A=A, L=L: env(t) * A(x) * math.sin(2 * math.pi * (x / (s["lam"] * L) - s["m"] * t / D) + s["ph"])  # noqa: E731
            key_wave(ab, sp, ts, y, True, recoil=0.3)
        return {"cycles": [s["m"] for s in S]}

    def look(ab, D, env):
        goal = np.array(P["look"], float)
        wh = sk.world()[bone]                                               # the target's keys are in the head's space
        goal = np.array(wh.to_local(*(head_c + goal))) - np.array(wh.to_local(*head_c))
        ts = times(D, 30)
        put(ab, look0, "translate", ts, lambda t: tuple(goal * smooth(t, 0, 0.3 * D) * (1 - smooth(t, 0.75 * D, D))))
        wl = sk.world()
        tgt = np.array(wl[bone].to_world(*(np.array(wl[bone].to_local(*head_c)) + goal)))
        for s in S:
            d0 = s["delay"] * D / 1.8
            hb = wl[s["sp"].bones[-1]]
            need = abs(_wrap(math.degrees(math.atan2(*(tgt - np.array(hb.head))[::-1])) - hb.rotation))
            mx = round(min(0.85, float(P["max_turn"]) / max(need, 1e-6)), 4)   # heads turn partway, never fold back
            s["look_mix"] = mx
            pts = [(0.0, 0.0), (0.1 * D + d0, 0.0), (0.1 * D + d0 + 0.14 * D, mx), (0.68 * D, mx), (0.9 * D, 0.0), (D, 0.0)]
            ab.ik(s["ik"], sorted(pts), ease="sine_in_out")
        event(ab, 0.1 * D, "sfx_snake_look")
        return {"look": [round(float(v), 1) for v in goal], "mix": [s["look_mix"] for s in S]}
    specs = [ClipSpec("idle", "loop", 2.4, idle), ClipSpec("snake_look", "oneshot", 1.8, look)]
    count = len(snakes)
    out = {"snakes": {ss: s["sp"].bones for ss, s in zip(snakes, S)}, "look_target": look0, "count": count,
           "ik": [s["ik"] for s in S]}
    if not 8 <= count <= 12:
        out["warning"] = f"{count} snakes found; the look reads best with 8-12"
    return out, specs


# ================================================================== fur / feather coat
def _fur(project: Project, bone: str, name: str, P: dict, bone_given: bool):
    sk = project.data
    slots = P["slots"] or find_prefixed(sk, "fur", "coat", "mane", "ruff", "fleece")
    _need(sk, "fur", slots)
    count = int(P["count"])
    if count < 3:
        raise ValueError("count (outline bones per slot) must be >= 3")
    made, phys = {}, []
    for fs in slots:
        main = bone if bone_given else sk.slot(fs).bone
        att = sk.attachment(fs)
        if isinstance(att, RegionAttachment):
            rig_mesh(project, fs, bones=[], detail=float(P["detail"]))           # contour first, to find the silhouette
            att = sk.attachment(fs)
        if not isinstance(att, MeshAttachment):
            raise ValueError(f"fur: {fs!r} is a {att.type}; fur needs a region or mesh layer")
        old_bones = []
        if len(att.vertices) != 2 * (len(att.uvs) // 2):
            from .weights import decode_weighted
            old_bones = sorted({sk.bones[bi].name for v in decode_weighted(att.vertices, len(att.uvs) // 2) for bi, *_ in v})
        hull = mesh_world_vertices(sk, fs, att)[: att.hull]
        c = hull.mean(0)
        seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.vstack([hull, hull[:1]]), axis=0).T))]
        size = float(max(np.ptp(hull[:, 0]), np.ptp(hull[:, 1])))
        ob = []
        for k in range(count):
            s_ = seg[-1] * (k + 0.5) / count
            j = int(np.searchsorted(seg, s_) - 1)
            j = max(0, min(j, len(hull) - 1))
            a, b = hull[j], hull[(j + 1) % len(hull)]
            t = (s_ - seg[j]) / max(seg[j + 1] - seg[j], 1e-9)
            p = a + (b - a) * t
            d = p - c
            dn = d / max(float(np.hypot(*d)), 1e-9)
            L = 0.16 * size
            head = p - dn * L * 0.7
            nm = frame_bone(sk, f"{name}{base_name(fs)}_fur{k + 1}", main, head[0], head[1], math.degrees(math.atan2(dn[1], dn[0])))
            sk.bone(nm).length = round(L, 3)
            ob.append(nm)
        bones = sorted({main, *old_bones} - set(ob)) + ob
        rig_mesh(project, fs, bones=bones, detail=float(P["detail"]))
        phys += add_phys(sk, ob, "fur", taper=0.0)
        made[fs] = {"bones": ob, "weighted_to": bones}
    wind = float(P["wind"])

    def ruffle(ab, D, env):
        g = 0.65 * D
        ks = [Key(time=round(t, 4), value=round(wind * math.sin(math.pi * min(t / g, 1.0)) ** 2 * (t < g), 4))
              for t in times(D, 30)]
        for c_ in phys:
            ab.a.physics.setdefault(c_, {})["wind"] = [k.model_copy() for k in ks]
        event(ab, 0.0, "sfx_fur_ruffle")
        return {"gust": round(g, 4), "wind": wind}
    return {"fur": made, "physics": phys}, [ClipSpec("fur_ruffle", "oneshot", 1.4, ruffle)]


# ================================================================== glowing bits (FX recipes into the host clips)
def C_val(k) -> float:
    v = getattr(k, "value", None)
    return 0.0 if v is None else float(v)


def _shift_keys(keys: list, t0: float, k: float) -> list:
    out = []
    for key in keys:
        nk = key.model_copy(deep=True)
        nk.time = round(t0 + key.time * k, 4)
        if isinstance(key.curve, list):
            cv = list(key.curve)
            for i in range(0, len(cv), 2):
                cv[i] = round(t0 + cv[i] * k, 4)                         # bezier cx are absolute times; cy are values
            nk.curve = cv
        out.append(nk)
    return out


def _tile(keys: list, n: int, Pd: float, k: float, tl: str = "") -> list:
    """n copies of one period, retimed by k. A rotation that turns whole circles per period (rays spinning 360) is
    unwrapped, so tile i starts where tile i - 1 ended instead of snapping back through the circle."""
    out: list = []
    turn = 0.0
    if tl == "rotate" and len(keys) > 1:
        d = C_val(keys[-1]) - C_val(keys[0])
        if abs(d) > 1 and abs(d / 360 - round(d / 360)) < 1e-6:
            turn = d
    for i in range(n):
        for nk in _shift_keys(keys, i * Pd, k):
            if turn and i:
                nk.value = round(C_val(nk) + i * turn, 4)
            if out and abs(out[-1].time - nk.time) < 1e-4:
                out[-1] = nk
            else:
                out.append(nk)
    return out


def _own_colour(project: Project, slot: str) -> str:
    """The part's own mean colour when it is bright enough to glow (runes, veins); "" (the recipe's) for dark parts."""
    sk = project.data
    try:
        a = np.asarray(project.image(project.att_image_name(slot, sk.slot(slot).attachment)), float)
    except (FileNotFoundError, KeyError):
        return ""
    m = a[..., 3] > 128
    if not m.any():
        return ""
    rgb = a[..., :3][m].mean(0)
    if (0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]) / 255 < 0.35:
        return ""
    return "%02X%02X%02X" % tuple(int(v) for v in rgb)


def _glow(project: Project, bone: str, name: str, P: dict):
    from . import fx_recipes
    sk = project.data
    slots = P["slots"] or find_prefixed(sk, "eye", "rune", "vein", "glow", "gem", "crystal")
    slots = [s for s in slots if not s.startswith("fx_")]
    _need(sk, "glow", slots)
    fx = str(P["fx"])
    if fx not in ("auto", "shine", "electric_frame"):
        raise ValueError("fx is shine | electric_frame | auto")
    period = float(P["period"])
    if period <= 0:
        raise ValueError("period must be > 0")
    clips = list(P["clips"] or [])
    if not clips:
        raise ValueError("clips lists the host clips to glow in, e.g. ['idle']")
    groups = []
    for gs in slots:
        rec = fx if fx != "auto" else ("electric_frame" if base_name(gs).startswith(("rune", "vein")) else "shine")
        x0, y0, x1, y1 = slot_bounds(project, gs)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        par = sk.slot(gs).bone
        wp = sk.world()[par]
        lx, ly = wp.to_local(cx, cy)
        tmp = f"__glow_{len(groups)}"
        top = P["on_top"] if P["on_top"] != "auto" else rec == "shine"     # surface marks stay under what covers them
        front = sk.slots[-1].name if top else gs
        scale = float(P["size"]) * max(x1 - x0, y1 - y0) / 160              # design units -> the part's size
        opts = {"pulse": period} if rec == "shine" else {"width": (x1 - x0) / scale * 1.1, "height": (y1 - y0) / scale * 1.1}
        color = str(P["color"]) or _own_colour(project, gs)
        res = fx_recipes.apply(project, rec, x=lx, y=ly, scale=scale, duration=period if rec == "electric_frame" else 0.0,
                               color=color, intensity=float(P["intensity"]), into="", parent=par, front_of=front,
                               count=1 if rec == "shine" else 0, name=f"{name}glow_{base_name(gs)}", options=opts)
        g = sk.bone(res["group_bone"])
        g.rotation = round(-wp.rotation, 3)                               # screen-aligned, whatever the slot bone's angle
        src = sk.animations.pop(res["animation"])
        groups.append(dict(slot=gs, recipe=rec, res=res, src=src, tmp=tmp,
                           bones=[res["group_bone"], *sk.descendants(res["group_bone"])]))

    def build(ab, D, env):
        n, Pd = fit_period(D, period)
        k = Pd / period
        for gr in groups:
            a = gr["src"]
            for b in gr["bones"]:
                for tl, ks in a.bones.get(b, {}).items():
                    ab.a.bones.setdefault(b, {})[tl] = _tile(ks, n, Pd, k, tl)
            for s in gr["res"]["slots"]:
                for tl, ks in a.slots.get(s, {}).items():
                    ab.a.slots.setdefault(s, {})[tl] = _tile(ks, n, Pd, k)
            seen = set()
            for i in range(n):
                for e in a.events:
                    key = (round(i * Pd + e.time * k, 4), e.name)
                    if key not in seen and key[0] < D - 1e-4:
                        seen.add(key)
                        ab.a.events.append(EventKey(time=key[0], name=e.name))
            ab.a.events.sort(key=lambda e: e.time)
        return {"pulses": n, "period": round(Pd, 4)}
    specs = [ClipSpec(c, "loop", period * 2, build) for c in clips]
    return {"glows": {g["slot"]: {"recipe": g["recipe"], "group_bone": g["res"]["group_bone"], "slots": g["res"]["slots"]}
                      for g in groups}}, specs


# ================================================================== attach_rig
def attach_rig(project: Project, kind: str, bone: str = "", name: str = "", options: dict | None = None) -> dict:
    """Plug a sub-rig of ``kind`` into ``bone`` (default: the usual bone for that kind, found by name) and merge its
    clips into the host's by name. Returns what was built and, per clip, its length and merge mode."""
    sk = project.data
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; one of {list(KINDS)}")
    P = _opts(kind, options)
    given = bool(bone)
    if bone:
        if not sk.has_bone(bone):
            raise ValueError(f"no bone {bone!r} to attach {kind} to; bones: {[b.name for b in sk.bones]}")
    elif BONES[kind]:
        bone = find_bone(sk, *BONES[kind]) or ""
        if not bone:
            raise ValueError(f"attach_rig {kind}: name the bone to attach to (bone=); none of {list(BONES[kind])} exists. "
                             f"Bones: {[b.name for b in sk.bones]}")
    else:
        bone = "root"
    prefix = f"{name}_" if name else ""
    before = dict(bones=len(sk.bones), slots=len(sk.slots), physics=len(sk.physics), ik=len(sk.ik), transform=len(sk.transform))
    fn = {"ears": _ears, "tail": _tail, "wings": _wings, "horns": _horns, "digitigrade": _digitigrade, "mermaid": _mermaid,
          "snake_hair": _snake_hair, "glow": _glow}.get(kind)
    if kind == "fur":
        made, specs = _fur(project, bone, prefix, P, given)
    else:
        made, specs = fn(project, bone, prefix, P)
    made["clips"] = merge_clips(sk, specs)
    made.update(kind=kind, bone=bone, added={k: (len(getattr(sk, k)) - v) for k, v in before.items()})
    return made


# ================================================================== the procedural host
HOST_PARTS = ("ears", "tail", "wings", "horns", "snake_hair", "mermaid", "fur", "glow", "digitigrade")


def make_sample_host(out_dir: str | Path, parts: tuple[str, ...] | list[str] = ("ears", "tail", "wings"), name: str = "host") -> Project:
    """A minimal chibi biped (hips -> chest -> head, single-bone legs and arms) with an idle (loop 2.4 s), a walk
    (loop 1.0 s) and a win (one-shot 1.2 s), plus the layers for the add-ons listed in ``parts``, named exactly as
    import_psd would name them from a PSD that follows ADDON_LAYERS. Feet stand on y = 0."""
    bad = [p for p in parts if p not in HOST_PARTS]
    if bad:
        raise ValueError(f"unknown part(s) {bad}; one of {list(HOST_PARTS)}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=760, height=760)
    p = Project(out / f"{name}.json", sk)
    sk.add_bone_world("hips", "root", 0, 170, 90, length=50)
    sk.add_bone_world("chest", "hips", 0, 220, 90, length=80)
    sk.add_bone_world("head", "chest", 0, 300, 90, length=170)
    for side, sg in (("l", -1), ("r", 1)):
        sk.add_bone_world(f"leg_{side}", "hips", sg * 34, 172, -90, length=150)
        sk.add_bone_world(f"arm_{side}", "chest", sg * 62, 282, -90 + sg * 28, length=100)
    sh = Sheet(p, 760, 880, 380, 740)
    skin, skin2 = (255, 214, 176), (232, 168, 132)
    fur_c, fur2 = (236, 128, 52), (196, 84, 30)
    P = set(parts)
    if "wings" in P:
        for side, sg in (("l", -1), ("r", 1)):
            arm = [(sg * 40, 268), (sg * 140, 318), (sg * 240, 372), (sg * 300, 430)]
            sh.add(f"wing_{side}", sh.paint(strip_shape(sh, *spline(arm, [30, 46, 40, 14])), (250, 250, 255), (180, 196, 230)))
    if "tail" in P:
        pts = [(30, 180), (110, 170), (180, 210), (215, 290), (205, 370)]
        sh.add("tail", sh.paint(strip_shape(sh, *spline(pts, [14, 26, 36, 34, 18])), fur_c, fur2))
    if "snake_hair" in P:
        for i in range(10):
            a = math.radians(20 + 140 * i / 9)
            r0 = 70
            pts = []
            for k in range(8):
                rr = r0 + 120 * k / 7
                wob = 0.07 * math.sin(k * 1.3 + i)
                pts.append((rr * math.cos(a + wob), 385 + rr * math.sin(a + wob)))
            hw = [9, 9, 8.5, 8, 7.5, 7, 9, 11]
            sh.add(f"snake{i + 1}", sh.paint(strip_shape(sh, *spline(pts, hw)), (120, 200, 90), (50, 130, 60), ow=2.5))
    if "mermaid" in P:
        pts = [(0, 200), (8, 120), (-6, 40), (0, -30)]
        sh.add("mermaid_tail", sh.paint(strip_shape(sh, *spline(pts, [62, 48, 30, 14])), (60, 200, 190), (20, 120, 140)))
        sh.add("fluke", sh.paint(lambda d, o: d.polygon(sh.pts([(0, -24 - o), (-70 + o, -96 + o), (0, -70), (70 - o, -96 + o)]), fill=255),
                                 (70, 210, 200), (20, 130, 150)))
    for side, sg in (("l", -1), ("r", 1)):
        if "digitigrade" in P:
            pts = [(sg * 34, 176), (sg * 34 + 22, 112), (sg * 34 - 14, 56), (sg * 34 + 2, 14)]
            sh.add(f"leg_{side}", sh.paint(strip_shape(sh, pts, [26, 20, 14, 12]), fur_c, fur2), f"leg_{side}")
            sh.add(f"foot_{side}", sh.paint(lambda d, o, sg=sg: d.polygon(ellipse_poly(sh, sg * 34 + 14, 10, 22 - o, 10 - o), fill=255),
                                            (90, 60, 50), (60, 40, 35)), f"leg_{side}")
        else:
            sh.add(f"leg_{side}", sh.paint(strip_shape(sh, [(sg * 34, 172), (sg * 36, 14)], [22, 22]), (70, 90, 160), (40, 50, 110)), f"leg_{side}")
    sh.add("body", sh.paint(lambda d, o: d.rounded_rectangle([*sh.px(-78 + o, 305 - o), *sh.px(78 - o, 150 + o)], radius=50 - o, fill=255),
                            (90, 130, 230), (50, 70, 160)), "chest")
    if "glow" in P:
        im = Image.new("RGBA", (760, 880), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        cx, cy = sh.px(0, 232)
        dr.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], outline=(120, 240, 255, 255), width=4)
        dr.line([cx, cy - 14, cx - 11, cy + 9, cx + 11, cy + 9, cx, cy - 14], fill=(120, 240, 255, 255), width=3)
        sh.add("rune", im, "chest")
    for side, sg in (("l", -1), ("r", 1)):
        sh.add(f"arm_{side}", sh.paint(strip_shape(sh, [(sg * 64, 282), (sg * 112, 196)], [17, 15]), skin, skin2), f"arm_{side}")
    if "fur" in P:
        def mane(d, o):
            d.polygon(ellipse_poly(sh, 0, 296, 104 - o, 34 - o), fill=255)
            for k in range(14):
                a = 2 * math.pi * k / 14
                x, y = sh.px(98 * math.cos(a), 296 + 30 * math.sin(a))
                r_ = 20 - o
                d.ellipse([x - r_, y - r_, x + r_, y + r_], fill=255)
        sh.add("mane", sh.paint(mane, (250, 240, 225), (215, 195, 170)), "chest")
    if "ears" in P:
        for side, sg in (("l", -1), ("r", 1)):
            pts = [(sg * 52, 446), (sg * 64, 500), (sg * 78, 552), (sg * 84, 590)]
            sh.add(f"ear_{side}", sh.paint(strip_shape(sh, *spline(pts, [30, 24, 14, 4])), fur_c, fur2), "head")
    sh.add("head", sh.paint(lambda d, o: d.polygon(ellipse_poly(sh, 0, 385, 96 - o, 90 - o), fill=255), skin, skin2), "head")
    for side, sg in (("l", -1), ("r", 1)):
        eye = Image.new("RGBA", (760, 880), (0, 0, 0, 0))
        de = ImageDraw.Draw(eye)
        ex, ey = sh.px(sg * 34, 395)
        de.ellipse([ex - 13, ey - 17, ex + 13, ey + 17], fill=(30, 20, 40, 255))
        de.ellipse([ex - 7, ey - 11, ex, ey - 4], fill=(255, 255, 255, 255))
        sh.add(f"eye_{side}", eye, "head")
    mouth = Image.new("RGBA", (760, 880), (0, 0, 0, 0))
    mx, my = sh.px(0, 352)
    ImageDraw.Draw(mouth).chord([mx - 20, my - 12, mx + 20, my + 12], 0, 180, fill=(150, 40, 60, 255))
    sh.add("mouth", mouth, "head")
    if "horns" in P:
        for side, sg in (("l", -1), ("r", 1)):
            pts = [(sg * 36, 452), (sg * 52, 500), (sg * 44, 536), (sg * 26, 556)]
            sh.add(f"horn_{side}", sh.paint(strip_shape(sh, *spline(pts, [13, 10, 6, 2.5])), (245, 235, 210), (170, 150, 120), ow=2.5), "head")
    _host_clips(sk)
    p.save()
    return p


def _host_clips(sk: SkeletonData) -> None:
    D = 2.4
    ab = AnimBuilder(sk, "idle")
    ts = times(D, 30)
    put(ab, "chest", "scale", ts, lambda t: (1.0, 1 + 0.03 * math.sin(2 * math.pi * t / D)), True)
    put(ab, "head", "rotate", ts, lambda t: 5.0 * math.sin(2 * math.pi * t / D), True)
    put(ab, "hips", "translate", ts, lambda t: (0.0, 2.0 * math.sin(4 * math.pi * t / D)), True)
    D = 1.0
    ab = AnimBuilder(sk, "walk")
    ts = times(D, 40)
    put(ab, "hips", "translate", ts, lambda t: (0.0, -5.0 * math.cos(4 * math.pi * t / D)), True)
    for side, sg in (("l", 1), ("r", -1)):
        put(ab, f"leg_{side}", "rotate", ts, lambda t, sg=sg: sg * 18.0 * math.sin(2 * math.pi * t / D), True)
        put(ab, f"arm_{side}", "rotate", ts, lambda t, sg=sg: -sg * 16.0 * math.sin(2 * math.pi * t / D), True)
    put(ab, "head", "rotate", ts, lambda t: 2.5 * math.sin(4 * math.pi * t / D), True)
    for tf, s in ((0.25, "l"), (0.75, "r")):
        ab.event(tf, "sfx_step", string=s)
    D = 1.2
    ab = AnimBuilder(sk, "win")
    ts = times(D, 60)

    def hop(t):
        if t < 0.2:
            return -12 * smooth(t, 0, 0.2)
        if t < 0.7:
            u = (t - 0.2) / 0.5
            return -12 * (1 - u) + 80 * 4 * u * (1 - u)                 # a parabola: gravity
        return -10 * spring_kick(t - 0.7, 2.4, 0.4) * (1 - smooth(t, 1.0, D))
    put(ab, "hips", "translate", ts, lambda t: (0.0, hop(t)))
    put(ab, "hips", "scale", ts, lambda t: (1 + 0.004 * max(0.0, -hop(t)), 1 - 0.008 * max(0.0, -hop(t))))
    for side, sg in (("l", -1), ("r", 1)):
        put(ab, f"arm_{side}", "rotate", ts, lambda t, sg=sg: sg * 120.0 * smooth(t, 0.15, 0.4) * (1 - smooth(t, 0.8, D)))
    ab.event(0.2, "sfx_win")
