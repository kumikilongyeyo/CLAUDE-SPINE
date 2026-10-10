"""MCP tools for the magic smoke puff (`fx_magic_puff`): `magic_puff_ae` simulates the puff and writes the After
Effects look script (+ a preview made without AE), `magic_puff_to_spine` renders the saved comp and lands it in Spine
with its lights and glitter. Registered on the server's FastMCP instance when imported."""
from __future__ import annotations

import json
from pathlib import Path

from .server import _open, _saved, mcp
from . import ae_bridge, fx_magic_puff


@mcp.tool()
def magic_puff_ae(out_dir: str, comp: str = "magic_puff", params: dict | None = None, preview: bool = True,
                  alerts: bool = True) -> dict:
    """Magic smoke puff, step 1: simulate it and write the After Effects look script (`<out_dir>/<comp>.jsx`).

    A physical one-shot (~3.7 s) for a wide banner: from nothing, gas appears at the centre and bursts out both ways
    (a real 2D smoke simulation in Python: no mirror, each side its own turbulence), held in a band by soft barriers
    along the gold lines until the ends, where the front rolls up into curling vortex pairs; it swirls, its glow dies
    as the smoke ages (heat = freshness), the barriers let go, it billows, lifts a little and dissolves thin-first.
    The nebula detail rides the flow; glitter rides the same flow (sim.json). Passes go to `<out_dir>/sim/`
    (op = density with detail, heat = freshness, lum = detail; 16-bit PNG at `res` of the banner).
    The script builds the look in its OWN project saved to `<out_dir>/<comp>.aep` (it stops if the open project has
    unsaved changes and reopens it afterwards): palette ramp, hot glow keyed out, cooling, bloom, a softened density
    matte eroding thin-first. Comps: `<comp>_full` (render this) and `<comp>_master` (over a dark background).
    params (all optional; `fx_magic_puff.DEFAULTS` lists them): width/height (the banner, 2172 x 724), cx/cy (the
    origin), res (0.5; 0.25 for a quick draft), t_end, U0/hold/decay/stop (the burst), slab, expand, wall_* (the band:
    wall_in/out = distance of the barriers from cy, wall_end = where they stop), wall_release (when they let go),
    vort/stir/visc (swirl vs smoothness), cool (how fast the glow dies), glitter (per side), seed, and the look:
    shadow/mid/light (palette RRGGBB), hot_mid/hot_light, heat_mix/heat_off, cool_to, erode, fade, bloom, matte_*.
    The simulation takes ~2 minutes at res 0.5 (about 30 s at 0.25). preview: a contact sheet + GIF of the look made
    here without AE: tune on it before running AE. alerts=False for an After Effects MCP run (no modal dialogs).
    Then: run the script in AE (the AE MCP's ae_run_script with `run_with`, or File > Scripts > Run Script File) and
    call magic_puff_to_spine."""
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    aep, script, sim_dir = out / f"{comp}.aep", out / f"{comp}.jsx", out / "sim"
    meta = fx_magic_puff.simulate(sim_dir, params)
    script.write_text(fx_magic_puff.jsx(meta["params"], comp, aep, sim_dir, alerts=alerts), encoding="utf-8")
    res = {"script": str(script), "save_as": str(aep), "comps": [f"{comp}_full", f"{comp}_master"], "sim_dir": str(sim_dir),
           "frames": meta["frames"], "fps": meta["fps"], "pass_size": meta["pass_size"],
           "glitter": sum(1 for g in meta["glitter"] if g["path"]),
           "run_with": "return String($.evalFile(new File(" + json.dumps(str(script).replace("\\", "/")) + ")));",
           "next": f"run the script in After Effects, then magic_puff_to_spine(aep={str(aep)!r}, comp={comp!r}, ...)"}
    if preview:
        res["preview"] = fx_magic_puff.preview(meta["params"], sim_dir, out / "preview")
    return res


@mcp.tool()
def magic_puff_to_spine(project: str, animation: str = "magic_puff", aep: str = "", comp: str = "magic_puff",
                        frames_dir: str = "", sim_dir: str = "", x: float = 0, y: float = 0, scale: float = 1.0,
                        start: float = 0.0, parent: str = "root", fps: float = 20, max_size: int = 652,
                        lights: bool = True, rays: bool = True, glitter: bool = True, front_of: str = "",
                        behind: str = "", params: dict | None = None) -> dict:
    """Magic smoke puff, step 2: render `<comp>_full` and land the puff in `animation` with its lights and glitter.

    Source: `aep` (the project magic_puff_ae's script saved; `<comp>_full` is rendered headless with aerender into
    `<aep folder>/frames/<comp>_full`) or `frames_dir` (its AE TIFFs already rendered). sim_dir: the passes folder
    (default: `sim` next to the aep, or next to frames_dir's parent) for the glitter paths and the banner size.
    The smoke becomes ONE full-width sequence (normal blend), resampled to `fps` (20: smooth flow, ~75 frames) at
    `max_size` px on its longest side (652 = two 2048 atlas pages with the lights; raise it for a sharper, heavier
    puff). Over it: the pop (a gathering point, then a flash + streak), the gold lines drawn outward with glints,
    flares igniting, the ray fan blooming from the bottom flare (rays=False to skip), an ambient glow (lights=False
    skips all of these) and glitter on the simulated paths (glitter=False to skip).
    x, y: the banner centre in `parent`'s space; scale: game units per banner pixel; start: the Spine time of the
    simulation's t=0 (the pop comes t_burst = 0.12 s later). params: Spine-side overrides of the simulation's
    params, no re-simulation needed: lines (the gold lines' y in comp px, [] = none), ray_color, glitter_colors,
    ray_angles, edge_fade (where the smoke thins out toward the ends; [] keeps the frames as rendered). The lights
    are timed to the default burst. On the 2172 x 724 banner at scale 0.6: 77 bones, 76 slots, 2 atlas pages.
    Run optimize_draw_order then pack_atlas after it."""
    if aep:
        aep_p = Path(aep).expanduser().resolve()
        src = aep_p.parent / "frames" / f"{comp}_full"
        info = ae_bridge.render_comp(aep_p, f"{comp}_full", src)
        src_fps = float(info.fps)
        sim = Path(sim_dir).expanduser() if sim_dir else aep_p.parent / "sim"
    elif frames_dir:
        src = Path(frames_dir).expanduser().resolve()
        meta_f = src / "meta.json"
        src_fps = float(json.loads(meta_f.read_text())["fps"]) if meta_f.exists() else 0.0
        sim = Path(sim_dir).expanduser() if sim_dir else src.parent.parent / "sim"
    else:
        raise ValueError("give aep= (the saved magic puff project) or frames_dir= (its rendered `_full` frames)")
    meta = json.loads((sim / "sim.json").read_text())
    src_fps = src_fps or float(meta["fps"])
    frames = sorted(src.glob("*.tif")) + sorted(src.glob("*.png"))
    if not frames:
        raise ValueError(f"no frames in {src}")
    p = _open(project)
    res = fx_magic_puff.to_spine(p, animation, frames, src_fps, meta, x=x, y=y, scale=scale, start=start, parent=parent,
                                 fps=fps, max_size=max_size, lights=lights, rays=rays, glitter=glitter,
                                 front_of=front_of, behind=behind, params=params)
    res["frames_dir"] = str(src)
    return _saved(p, res)
