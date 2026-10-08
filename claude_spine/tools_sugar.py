"""MCP tools for the melted-sugar splat (`fx_sugar_splat`): `sugar_splat_ae` writes the After Effects script (and a
preview made without AE), `sugar_splat_to_spine` renders the saved comp, glosses it and lands it on a burst.
Registered on the server's FastMCP instance when imported."""
from __future__ import annotations

import json
from pathlib import Path

from .server import _open, _saved, mcp
from . import ae_bridge, ae_vfx_director, fx_sugar_splat


@mcp.tool()
def sugar_splat_ae(out_dir: str, comp: str = "sugar_splat", params: dict | None = None, preview: bool = True,
                   alerts: bool = True) -> dict:
    """Melted-sugar splat, step 1: write the After Effects script (`<out_dir>/<comp>.jsx`).

    A physical liquid burst simulated in Python (air drag + gravity): fat centre globs swell and drain, globs fly
    out at uneven speeds dragging syrup ligaments, tear into drops with teardrop tails, which tear into droplets
    that fall; everything stretched along its velocity. Gets smaller by breaking up, never by shrinking in place.
    The script builds one shape layer per drop keyed every frame, one precomp per candy colour finished as metaballs
    (Turbulent Displace -> Fast Box Blur -> Levels on alpha: close drops melt into gooey necks that pinch off), in
    its OWN project saved to `<out_dir>/<comp>.aep` (it stops if the open project has unsaved changes, and reopens
    it afterwards). Comps: `<comp>_flat` (colour only, glossed by sugar_splat_to_spine) and `<comp>_bevel` (all-AE
    look). Problems are left as `CLAUDE_ERR sugar: ...` comps (ae_check).
    params (all optional): size (comp px, 1800), fps (30), duration (1.4), colors {name: RRGGBB}, accents (colours
    for 2 globs only), globs (20), speed [lo, hi] px/s, glob_size [lo, hi] px, ligament (beads per glob), splits
    [lo, hi] drops per glob, gravity / drag (multipliers), centre (bool), blur (merge reach), levels [lo, hi] (alpha
    threshold, 0..255), turbulence, seed.
    preview: a contact sheet + GIF of the same metaball maths and gloss, rendered here without AE: tune the motion on
    it before running AE. alerts=False for an After Effects MCP run (no modal dialogs).
    Then: run the script in AE (File > Scripts > Run Script File, or the AE MCP's ae_run_script with `run_with`;
    `AfterFX.exe -r` may never reach an open AE) and call sugar_splat_to_spine."""
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    aep, script = out / f"{comp}.aep", out / f"{comp}.jsx"
    P = fx_sugar_splat.params_of(params)
    script.write_text(fx_sugar_splat.jsx(P, comp, aep, alerts=alerts), encoding="utf-8")
    res = {"script": str(script), "save_as": str(aep), "comps": [f"{comp}_flat", f"{comp}_bevel"],
           "drops": len(fx_sugar_splat.simulate(P)), "params": P,
           "run_with": "return String($.evalFile(new File(" + json.dumps(str(script).replace("\\", "/")) + ")));",
           "next": f"run the script in After Effects, then sugar_splat_to_spine(aep={str(aep)!r}, comp={comp!r}, ...)"}
    if preview:
        res["preview"] = fx_sugar_splat.preview(P, out / "preview")
    return res


@mcp.tool()
def sugar_splat_to_spine(project: str, animation: str, at: float, aep: str = "", comp: str = "sugar_splat",
                         frames_dir: str = "", name: str = "sugar", x: float = 0, y: float = 0, parent: str = "root",
                         scale: float = 1.6, mirror: bool = False, max_size: int = 800, max_frames: int = 30,
                         target: str = "mobile_feature", front_of: str = "", behind: str = "") -> dict:
    """Melted-sugar splat, step 2: render, gloss and land it in Spine, the comp's frame 0 on the burst `at`.

    Source: `aep` (the project sugar_splat_ae's script saved; `<comp>_flat` is rendered headless with aerender
    into `<aep folder>/frames/<comp>_flat`) or `frames_dir` (AE TIFFs of `<comp>_flat` already rendered).
    The frames get the wet-sugar gloss (dome height from the alpha, sharp specular + sheen, translucent core,
    darker rim) into `<frames>_shaded`, then go through the AE VFX Director's importer (trimmed, capped at
    max_size / max_frames with playback speed kept, edge-feathered). scale: game units per comp px (the comp is
    `size` px wide, 1800 by default). mirror: play it flipped left-right (a second variation from one frame set:
    import once per animation, or copy the slot's keys). x, y: the burst point in `parent`'s space."""
    if aep:
        src = Path(aep).expanduser().resolve().parent / "frames" / f"{comp}_flat"
        info = ae_bridge.render_comp(Path(aep).expanduser().resolve(), f"{comp}_flat", src)
        (src / "meta.json").write_text(json.dumps({"fps": info.fps, "width": info.width, "height": info.height}))
    elif frames_dir:
        src = Path(frames_dir).expanduser().resolve()
    else:
        raise ValueError("give aep= (the saved sugar splat project) or frames_dir= (its rendered `_flat` frames)")
    shaded = fx_sugar_splat.shade_frames(src, src.parent / f"{src.name}_shaded")
    fps = float(shaded.get("fps") or 30)
    p = _open(project)
    res = ae_vfx_director.import_optimized(
        p, name, event="win_burst", style="stylized", target=target, max_size=max_size, max_frames=max_frames,
        feather=0.02, frames_dir=shaded["dir"], fps=fps, mode="alpha", animation=animation, hit_ae=0.0, hit_at=at,
        x=x, y=y, scale=scale, parent=parent, front_of=front_of, behind=behind)
    if mirror:
        from .timeline import AnimBuilder
        AnimBuilder(p.data, res["animation"], replace=False).bone(res["bone"], "scale", [(0, -1, 1)])
    res["shaded"] = shaded["dir"]
    res["mirrored"] = mirror
    return _saved(p, res)
