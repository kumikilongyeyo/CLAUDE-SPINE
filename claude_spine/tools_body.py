"""MCP tools for character bodies: make_biped_sample, rig_biped, clip_set, secondary, squash_stretch, qa_character.

Engines: ``rig_body.py`` (rig, contract clips, secondary motion, squash) and ``qa_character.py`` (cracks, foot slide,
budgets). Imported by server.py at its end, so ``mcp`` already carries the core tools.
"""
from __future__ import annotations

from typing import Any

from . import qa_character as qc
from . import rig_body as rb
from .server import _open, _saved, mcp


@mcp.tool()
def make_biped_sample(out_dir: str, name: str = "biped", split_limbs: bool = False, facing: str = "right") -> dict:
    """Create a procedural biped (a chibi adventurer, side view) whose layers follow BIPED_LAYERS, exactly as
    import_psd would bring in a PSD with origin="bottom": torso, head, arm_l/r, hand_l/r, leg_l/r, foot_l/r (or
    upper_arm/lower_arm and thigh/shin with split_limbs=true), plus cape, ponytail, belt_tail, pouch and head features
    (eye_r, brow_r, mouth, ear_r, hat). Try rig_biped → clip_set → qa_character on it."""
    p = rb.make_sample_biped(out_dir, name, split_limbs, facing)
    return {"project": str(p.path), "slots": [s.name for s in p.data.slots], "parts": rb.find_parts(p.data)}


@mcp.tool()
def rig_biped(project: str, facing: str = "auto", meshes: bool = True, look_at: bool = True, breathing: bool = True,
              secondary_motion: bool = True, detail: float = 0.8, look_lag_frames: float = 2.0,
              spine_twist: float = 0.2) -> dict:
    """Rig a biped from its PSD layers in one call (import_psd origin="bottom" first).

    Layers are recognised by name (BIPED_LAYERS, case-insensitive, sides _l/_r, "Arm L", "arm.l", "left_arm"):
    required torso (body), head, arm_l/r (or upper_arm + lower_arm / forearm), leg_l/r (or thigh + shin / calf);
    optional pelvis, neck, hand_l/r, foot_l/r (boot/shoe), eye*, mouth, and strand layers (hair, cape, scarf,
    belt_tail, chain, feather, tail, pouch...). Missing required layers → a clear error listing them.

    Builds root → ground → hips → spine1-3 → chest → neck → head, shoulders/arms/hands, thighs/shins, floor-pinned
    foot IK (ik_foot_l/r under ground: the body bobs and the feet stay put), arm IK (ik_hand_l/r ride the chest),
    bones placed from each layer's own centre line, the knee/elbow bend taken from the art (straight art: knees
    forward, elbows back). One weighted mesh across each joint (shoulders, hips, elbows, knees) so bends cannot
    crack. breathing adds the 4 s `breathe` loop; look_at adds the look_target hook (eyes first, head
    look_lag_frames behind at 30 fps, spine twists spine_twist of the turn); secondary_motion runs `secondary`.
    Facing: auto (the way the feet point) | right | left."""
    p = _open(project)
    res = rb.rig_biped(p, facing, meshes, look_at, breathing, secondary_motion, detail, look_lag_frames, spine_twist)
    from . import qa
    res["budget_mobile_character"] = qa.budget(p.data, "mobile_character")["metrics"]
    return _json_safe(_saved(p, res))


@mcp.tool()
def clip_set(project: str, clips: list[str] | None = None, intensity: float = 1.0, bone_map: dict | None = None,
             facing: str = "auto", durations: dict | None = None, wind: bool = True, blow_from: str = "front",
             attack_hand: str = "auto") -> dict:
    """The character contract: the SAME clip names for every character, so game code never changes.

    idle (loop 4 s: one real breath), idle_fidget, walk (loop), run (loop), jump, land, hit, attack, win, lose,
    talk (loop). Loops close exactly, one-shots end exactly on the setup pose, the artist's setup never moves.
    Events: sfx_step on every footfall (string = the foot bone, float = the ground speed in px/s: move the character
    at that speed and the feet do not slide), sfx_jump, sfx_land, sfx_hit, sfx_attack + attack_hit (damage frame),
    sfx_win, sfx_lose, sfx_talk, sfx_idle_fidget.
    Physics: walk = inverted pendulum, run = spring-mass + gravity-parabola flight, land = exact spring squash 0.85 →
    overshoot 1.05 (volume kept), hit = 2-frame anticipation against the blow then a spring recoil lagging up the
    chain, attack = wind-up, strike, spring follow-through. Strands get a headwind ~ v^2 in walk/run.

    Works on any rig that has the bones a clip needs (canonical names from rig_biped; bone_map renames them, e.g.
    {"hips": "hip", "ik_hand_r": "arm_r2_ik"}); clips whose bones are missing are skipped and listed with what is
    missing. intensity 0.5 subtle … 1 standard … 1.6 cartoon. durations {clip: seconds}. blow_from front|back."""
    p = _open(project)
    res = rb.clip_set(p, clips or "all", intensity, bone_map, facing, durations, wind, None, blow_from, attack_hand)
    return _json_safe(_saved(p, res))


@mcp.tool()
def secondary(project: str, presets: dict | None = None, by_shape: bool = True, exclude: list[str] | None = None,
              slots: list[str] | None = None, n_bones: int = 0, detail: float = 0.8) -> dict:
    """Secondary motion in one call: find every strand-like layer and give it a chain along its own centre line, a
    weighted mesh and Spine physics. By name (hair/lock/ponytail/braid → hair; cape/cloak/skirt → cloth;
    scarf/ribbon/sash → silk; belt_tail/strap → leather; chain/necklace → chain; feather/plume → feather; tail;
    pouch/bag/charm/pendant → a one-bone pendulum) and, with by_shape, any other elongated layer (cloth).
    The chain starts at the end that overlaps the body and hangs from the body bone nearest it.
    presets {slot: hair|cloth|silk|leather|chain|feather|tail|ear|pouch} overrides; n_bones 0 = the preset's."""
    p = _open(project)
    res = rb.secondary(p, presets, by_shape, exclude, slots, n_bones or None, detail)
    return _json_safe(_saved(p, res))


@mcp.tool()
def squash_stretch(project: str, chain: list[str], clip: str, start: float = 0.0, squash: float = 0.85,
                   overshoot: float = 1.05, hz: float = 2.6, duration: float = 0.0, volume: str = "3d",
                   intensity: float = 1.0, event: str = "") -> dict:
    """Volume-preserving squash & stretch of any bone chain on an exact spring, keyed into `clip` from `start`.
    The first extreme of the along-chain scale is exactly `squash` (< 1 squashes first, > 1 stretches first), the
    next exactly `overshoot` on the other side of 1, then it settles exactly to rest. volume 3d: across =
    along^-1/2 (a cylinder keeps its volume); area: across = 1/along. Keys go on a carrier bone ss_<chain[0]> inserted
    at the chain base and aligned with it (the artist's bones and keys are never touched); several calls multiply."""
    p = _open(project)
    res = rb.squash_stretch(p, chain, clip, start, squash, overshoot, hz, duration or None, volume, intensity,
                            event or None)
    return _json_safe(_saved(p, res))


@mcp.tool()
def qa_character(project: str, animations: list[str] | None = None, rig_type: str = "auto", fps: float = 30,
                 crack_threshold: float = 0.08) -> dict:
    """Character QA played in spine-core: joint cracks (where two parts' art separates at a bending joint, or a
    single mesh folds), foot slide (a planted foot drifting from the clip's ground speed) and the mobile bone budget
    for the rig type (biped, quadruped, flier, serpent, face; auto detects) plus mobile_character. Returns `fix`:
    what to change, joint by joint and clip by clip."""
    p = _open(project)
    res = qc.qa_character(p, animations, rig_type, fps, crack_threshold=crack_threshold)
    res.pop("_all_cracks", None)
    res.pop("_all_slides", None)
    return _json_safe(res)


def _json_safe(o: Any):
    import numpy as np
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o
