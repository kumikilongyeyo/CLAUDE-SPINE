"""MCP tools for gaits and the quadruped rig (engine: rig_gait.py). Registered on import; server.py imports this
module at its end."""
from __future__ import annotations

from .server import _open, _saved, mcp
from . import rig_gait as G


@mcp.tool()
def gait(project: str = "", legs: list | None = None, body: str = "", gait: str = "walk", name: str = "",
         speed: float = 0, cycles: int = 1, start: float = 0.0, frequency: float = 0, duty: float = 0,
         clearance: float = -1, bob: float = -1, pitch: float = -1, roll: float = -1, exaggerate: float = 1.0,
         facing: int = 0, leg_length: float = 0, events: bool = True) -> dict:
    """Key a gait on ANY rig that has foot IK targets and a body bone: planted stance, swing arc, toe roll, body
    bob and pitch coupled to the footfalls, and an sfx_step event (string = leg name) at every touch-down.
    Call with no project to list the gaits.

    gait: walk (4-beat LH LF RH RF), trot (diagonals), pace (laterals), canter (3-beat), gallop (rotary, two
          flights), bound (hind pair / fore pair) for 4 legs; tripod (L1 R2 L3 / R1 L2 R3) and wave for 6;
          biped_walk / biped_run for 2 ("walk"/"run" resolve by leg count).
    legs: the foot IK target bones, e.g. ["ik_front_L", "ik_front_R", "ik_hind_L", "ik_hind_R"]; side and end are
          read from the name (_L/_R, front/hind/middle, LF, RH, L1..R3) or given as dicts
          {"target", "side": "L|R", "end": "front|middle|hind", "name", "roll", "hip", "reach", "offset", "bias"}.
          Hip, reach and the hock offset are found from the IK constraint that serves each target.
    body: the bone that bobs and pitches (its children carry the hips/shoulders; the targets must NOT be under it).
    speed: units/s (default: the gait's typical speed in leg lengths/s x the hip height). The cycle is in place;
          the game scrolls the world at this speed. Frequency f = c sqrt(speed / leg_length), stride = speed / f,
          so speed scales both by sqrt; if a stride would over-stretch a leg the frequency is raised (reported).
    frequency / duty / clearance / bob / pitch / roll: overrides (0 or -1 = gait default; clearance and bob in units,
          pitch and roll in degrees). exaggerate scales clearance, bob, pitch and roll. facing: 1 right, -1 left,
          0 auto (front feet ahead of hind feet). Loops close exactly; keys go into animation `name` (default the
          gait's name), at `start`, `cycles` strides long.
    """
    if not project:
        return {"gaits": G.list_gaits(), "aliases": {f"{k[0]} ({k[1]} legs)": v for k, v in G.GAIT_ALIASES.items()}}
    if not legs or not body:
        raise ValueError("gait needs legs (foot IK target bones) and body (the bone that bobs)")
    p = _open(project)
    res = G.gait(p, legs, body, gait, name or None, speed or None, cycles, start, frequency or None, duty or None,
                 None if clearance < 0 else clearance, None if bob < 0 else bob, None if pitch < 0 else pitch,
                 exaggerate, facing, leg_length or None, None if roll < 0 else roll, events)
    return _saved(p, res)


@mcp.tool()
def rig_quadruped(project: str, leg_type: str = "digitigrade", clips: list[str] | None = None,
                  speeds: dict | None = None, seed: int = 7, exaggerate: float = 1.0, physics: bool = True) -> dict:
    """Rig a four-legged animal from its layers and build its clips in one call.

    Layers (case-insensitive, _R = near side, _L = far side, the animal faces right or left; see QUADRUPED_LAYERS):
    REQUIRED body, head, {front|hind}_{upper|lower|foot}_{L|R}; optional {front|hind}_mid_{L|R} (metapodial),
    neck, tail, ear_L/ear_R, eye_L/eye_R, mane*, tuft*, wattle*, snout/nose/jaw/... (ride the head); anything else
    rides the nearest body bone. Missing optional parts are skipped; missing required ones are listed in the error.

    leg_type: plantigrade (2-bone IK, flat foot), digitigrade (3 segments: 2-bone IK to a hock/carpus target +
    1-bone IK on the metapodial; made by splitting the lower leg if there is no mid layer), unguligrade (long
    cannon + pastern bone for the hoof). Spine q_body -> spine_back/hips + spine_front/shoulders, neck1/neck2,
    head, eye bones, physics strands (tail loose and wild, ears, mane, tufts, wattles).

    clips (default all): idle, alert, walk, trot, gallop, bound, pounce, sleep, shake (+ pace, canter). Loops are
    exact, one-shots end on the setup pose. Events: sfx_step (string = foot), sfx_idle (ear_flick / tail_swish /
    blink), sfx_alert, sfx_pounce, sfx_sleep, sfx_shake. speeds: {clip: units/s} for the gait clips. seed drives
    the idle's ear flick / tail swish / blink timer. exaggerate scales every amplitude."""
    p = _open(project)
    res = G.rig_quadruped(p, leg_type, clips or "all", speeds, seed, exaggerate, physics)
    from . import qa
    res["budget"] = {k: v for k, v in qa.budget(p.data, "mobile_character").items()
                     if k in ("ok", "metrics", "over_budget")}
    return _saved(p, res)


@mcp.tool()
def make_quadruped_sample(out_dir: str, name: str = "dog", rig: bool = False, leg_type: str = "digitigrade",
                          with_mid: bool = True) -> dict:
    """A procedural dog-like side view (faces right, stands on y = 0) with one layer per part, named by the
    QUADRUPED_LAYERS convention, to try rig_quadruped and gait on. rig=True also runs rig_quadruped (all clips).
    with_mid=False leaves out the metapodial layers (the rig then splits the lower legs)."""
    p = G.make_sample_quadruped(out_dir, name, with_mid)
    out = {"slots": [s.name for s in p.data.slots]}
    if rig:
        out["rig"] = G.rig_quadruped(p, leg_type)
    return _saved(p, out)
