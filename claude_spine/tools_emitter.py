"""fx_emitter: the Unity-style particle emitter, baked into Spine keys (claude_spine/fx_emitter.py)."""
from __future__ import annotations

from .server import mcp, _open, _saved
from . import fx_emitter as E


@mcp.tool()
def fx_emitter(project: str = "", preset: str = "", emitter: dict | None = None, x: float = 0.0, y: float = 0.0,
               scale: float = 1.0, start: float = 0.0, intensity: float = 1.0, into: str = "", parent: str = "root",
               front_of: str = "", behind: str = "", name: str = "", save_preset: str = "",
               preset_doc: str = "") -> dict:
    """Particle FX without Unity: a Shuriken-style emitter simulated here and BAKED into ordinary Spine keys
    (a pool of reused slots, one bone each; shown at birth, hidden at death), so it plays in every Spine runtime.

    preset = a stored emitter (sparks_burst, embers_rise, magic_motes, coin_fountain, confetti, smoke_puffs,
    dust_hit, star_twinkle, snow, bubbles, comet_trail, firework, plus your own); emitter = overrides, module by
    module, Unity names: duration, loop, lifetime, speed, size, rotation, color, alpha, gravity, max_particles,
    seed, emission {rate, bursts [{time, count, cycles, interval, probability}]}, shape {type point | circle |
    ring | cone | rect | edge | path, radius, thickness, arc, angle (90 = up), spread, width, height, length,
    points, direction outward | angle | normal, edge_only}, velocity {x, y, orbital, radial, speed_multiplier},
    drag, inherit, noise {strength, frequency, scroll}, size_over_lifetime, alpha_over_lifetime,
    color_over_lifetime, spin, renderer {blend, align none | velocity, stretch, flip}, texture, sub_emitters
    [{on death | birth, emitter {...} | "<preset>", probability}], move [[t, x, y], ...], key_rate, tolerance.
    Values: number, [lo, hi] random, over-lifetime [[t, v], ...] (t = 0..1 of the life) or {min, max} curves;
    colours RRGGBB, [RRGGBB, ...] or a gradient [[t, RRGGBB], ...].

    texture = your art, swappable any time: a built-in (fx/spark, fx/mote, fx/glow, fx/smoke, fx/cloud, fx/ring,
    fx/wisp, fx/chip), "kit:<picture>" (bundled CC0), a PNG, "file.psd#Layer", or a flipbook {"frames": folder |
    [pngs], "fps": 24 | "cycles": 1, "random_start": true} played as a Spine sequence (After Effects frames from
    aerender drop straight in, TIFF alpha read correctly).

    max_particles is a hard cap on slots: extra particles are DROPPED and reported (dropped, warnings). loop=True
    closes exactly (periodic spawns, a particle crossing the loop point keeps its slot, noise scrolls whole
    cycles). x, y = the emitter in the parent bone's space; into = add to an existing animation; front_of /
    behind = draw order. The result reports emitted, dropped, peak_alive, pool_slots and keys (the cost follows
    peak_alive, not emitted).

    No project: lists the presets. save_preset=<name> stores the resolved emitter as YOUR preset
    (~/.claude-spine/emitter_presets, or CLAUDE_SPINE_PRESETS) for reuse; start every new effect from the
    closest preset and change only what differs."""
    if not project and not save_preset:
        return {"presets": {k: v.get("doc", "") for k, v in E.presets().items()},
                "modules": sorted(E.DEFAULTS),
                "usage": "fx_emitter project=<.json> preset=<name> emitter={overrides}"}
    out: dict = {}
    if save_preset:
        out["saved_preset"] = E.save_preset(save_preset, E.resolve(preset, emitter), preset_doc)
        if not project:
            return out
    p = _open(project)
    res = E.bake(p, preset, emitter, x, y, scale, start, intensity, into, parent, front_of, behind, name)
    return _saved(p, {**res, **out})
