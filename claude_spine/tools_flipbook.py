"""fx_flipbook: the After Effects templates rendered once and stored, dropped onto any skeleton without AE."""
from __future__ import annotations

import shutil
from typing import Any

from .server import mcp, _open, _saved
from . import ae_bridge, flipbooks as F


@mcp.tool()
def fx_flipbook(project: str = "", name: str = "", part: str = "", x: float = 0.0, y: float = 0.0,
                scale: float = 1.0, parent: str = "root", front_of: str = "", behind: str = "", start: float = 0.0,
                animation: str = "", seq_mode: str = "", until: float = 0.0, fit_duration: float = 0.0,
                fade: float = 0.0, max_size: int = 0, max_frames: int = 0, blend: str = "",
                color: str = "FFFFFFFF", tintable: bool = False, tint: str = "",
                copies: list[list[float | None] | dict[str, Any]] | None = None, anchor: list[float] | None = None,
                feather: float = 0.0, slot_name: str = "") -> dict:
    """Ready After Effects flipbooks: the non-particle AE templates rendered ONCE and stored in the rigger, so
    they drop onto any asset with NO After Effects: caustics, electric_frame, energy_burst, fire, fire_aura,
    fire_strip, flame_wisps, fog_roll, sand_roll, frost_creep, glow_pulse, god_rays, lens_flare, lightning,
    magic_glow, magic_smoke, magic_smoke_dark, orbit_ribbons (parts back / front), portal_ring, prism_glow,
    ripple_glow, ripple_lines, shockwave, smoke_haze, smoke_puff, win_aura (parts in / loop / out).
    (Particle templates are fx_emitter presets ae_*; templates that need your art or text, such as
    heat_shimmer, surface_sweep, edge_aura, saber, still go through ae_template.)

    No project: lists them with blend mode, loop or once, length and size. With project + name: one sequence
    slot playing it, through the same importer as ae_fx_to_spine: x, y in the parent bone's space, scale
    1 = one unit per pixel of the template's own comp, behind / front_of = draw order round your art, start
    seconds, animation= merges into an existing animation, seq_mode once | loop | pingpong (default the
    flipbook's own), until / fit_duration / fade, max_size / max_frames = texture budget, tintable + tint =
    recolour one frame set (good for lightning, frost, smoke and the glows; fire and gold stay as rendered),
    copies = more instances sharing the frames ({"x", "y", "start", "tint", "offset", "parent"}). part picks
    one part of a multi-part flipbook (win_aura: in, loop, out; orbit_ribbons: back behind your art, front in
    front of it). Also usable as a particle picture: fx_emitter texture={"frames": "flipbook:<name>"}."""
    if not project:
        return {"flipbooks": F.listing(), "data_dir": str(F.data_dir()),
                "usage": "fx_flipbook project=<.json> name=<flipbook> x= y= behind=<slot>"}
    tmp, m = F.materialize(name, part)
    try:
        src = m.get("source_size") or m["size"]
        k = src[0] / max(m["size"][0], 1)             # stored frames may be smaller than the comp: keep comp units
        p = _open(project)
        res = ae_bridge.fx_to_spine(
            p, slot_name or (name if not part else f"{name}_{part}"), frames_dir=str(tmp), fps=m["fps"],
            mode=m["mode"], seq_mode=seq_mode or m.get("seq_mode") or "once", animation=animation, start=start,
            fit_duration=fit_duration, until=until, x=x, y=y, scale=scale * k, max_size=max_size,
            max_frames=max_frames, blend=blend, color=color, parent=parent, front_of=front_of, behind=behind,
            fade=fade, copies=copies, anchor=anchor, feather=feather, tintable=tintable, tint=tint)
        res["flipbook"] = {"name": name, "part": m["part"], "template": m["template"], "mode": m["mode"]}
        return _saved(p, res)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
