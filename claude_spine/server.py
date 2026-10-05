"""CLAUDE-SPINE MCP server.

Small, sharp tools that each do one rigging job on a project on disk
(``<name>.json`` + ``images/``). Typical session:

    import_psd → rig_mesh / rig_strand / rig_ik / rig_turn → juice_apply →
    fx_generate / ae_fx_to_spine → validate → qa_budget → preview → make_editable / pack_atlas

Every tool returns a JSON summary; nothing is printed. Tools that change the
skeleton save it before returning, so tools can be chained freely.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import ae_bridge, ae_templates
from . import atlas as atlas_mod
from . import fx as fx_mod
from . import fx_recipes
from . import juice as juice_mod
from . import psd as psd_mod
from . import qa, render, rig, runtime, samples, spine_cli
from .ir import Bone
from .mesh import rig_mesh as _rig_mesh
from .project import Project
from .timeline import AnimBuilder

mcp = FastMCP("claude-spine")


def _open(project: str) -> Project:
    return Project.open(project)


def _saved(p: Project, result: dict) -> dict:
    p.save()
    v = qa.validate(p.data)
    result["project"] = str(p.path)
    if not v["ok"]:
        result["validation_errors"] = v["errors"][:10]
    return result


# ------------------------------------------------------------------ setup / io
@mcp.tool()
def doctor() -> dict:
    """Check the toolchain: Python deps, Node (official spine-core runtime for
    validation and previews) and the Spine editor CLI (editable .spine export)."""
    deps = {}
    for m in ("numpy", "scipy", "PIL", "psd_tools", "pydantic"):
        try:
            __import__(m)
            deps[m] = True
        except ImportError:
            deps[m] = False
    out: dict[str, Any] = {"python_deps": deps, "node": runtime.node_bin(), "spine_cli": spine_cli.SPINE_BIN,
                           "spine_cli_found": spine_cli.available()}
    if spine_cli.available():
        try:
            out["spine_version"] = spine_cli.version()
        except Exception as e:  # noqa: BLE001
            out["spine_version"] = f"error: {e}"
    if runtime.available():
        try:
            runtime.ensure_runtime()
            out["spine_core_runtime"] = "ready"
        except Exception as e:  # noqa: BLE001
            out["spine_core_runtime"] = f"error: {e}"
    return out


@mcp.tool()
def make_sample(kind: str, out_dir: str) -> dict:
    """Create a procedural sample project to try the tools on.
    kind: "symbol" (slot symbol: plate, gem, letter, highlight) or "character"
    (mascot with arms, cape, hair locks, face features, ears)."""
    if kind == "symbol":
        p = samples.make_symbol(out_dir)
    elif kind == "character":
        p = samples.make_character(out_dir)
    else:
        raise ValueError("kind is symbol|character")
    return {"project": str(p.path), "slots": [s.name for s in p.data.slots], "bones": [b.name for b in p.data.bones]}


@mcp.tool()
def inspect_psd(psd: str) -> dict:
    """List a PSD's layers (names, groups, visibility, blend, bounds, [tags])
    without writing anything. Run before import_psd."""
    return psd_mod.inspect(psd)


@mcp.tool()
def import_psd(psd: str, out_dir: str, name: str = "", origin: str = "center",
               groups_as_bones: bool = False, include_hidden: bool = False, scale: float = 1.0) -> dict:
    """PSD → project: one slot per visible layer, placed exactly as on the
    canvas, PNGs cropped to content, Photoshop blend modes mapped.
    origin "center" for symbols, "bottom" for characters standing on y=0."""
    return psd_mod.import_psd(psd, out_dir, name or None, origin, groups_as_bones, include_hidden, scale)


@mcp.tool()
def project_info(project: str) -> dict:
    """Bones (with world head positions), slots (bone, attachment type, blend),
    constraints and animations of a project."""
    p = _open(project)
    sk = p.data
    w = sk.world()
    atts = {}
    for s in sk.slots:
        a = None
        if s.attachment:
            try:
                a = sk.attachment(s.name).type
            except KeyError:
                a = "missing"
        atts[s.name] = {"bone": s.bone, "attachment": s.attachment, "type": a, "blend": s.blend}
    return {
        "bones": {b.name: {"parent": b.parent, "world": [round(w[b.name].x, 1), round(w[b.name].y, 1)],
                           "rotation": round(w[b.name].rotation, 1), "length": b.length} for b in sk.bones},
        "slots": atts,
        "ik": [c.name for c in sk.ik], "transform": [c.name for c in sk.transform],
        "physics": [c.name for c in sk.physics], "events": list(sk.events),
        "animations": {n: round(a.duration(), 3) for n, a in sk.animations.items()},
    }


# ----------------------------------------------------------------------- bones
@mcp.tool()
def add_bones(project: str, bones: list[dict]) -> dict:
    """Add bones in WORLD coordinates (y up). Each item:
    {"name", "parent" (default "root"), "x", "y", "rotation" (world degrees, default 0),
     "length" (default 0)}. Art never moves; only bones are added."""
    p = _open(project)
    made = []
    for b in bones:
        p.data.add_bone_world(b["name"], b.get("parent", "root"), float(b["x"]), float(b["y"]),
                              float(b.get("rotation", 0)), float(b.get("length", 0)))
        made.append(b["name"])
    return _saved(p, {"added": made})


@mcp.tool()
def add_chain(project: str, name: str, points: list[list[float]], parent: str = "root") -> dict:
    """Bones along a polyline of world points (n points → n-1 bones, each
    reaching the next point). Use for limbs, spines, tails, tentacles."""
    p = _open(project)
    return _saved(p, {"bones": rig.add_chain(p.data, name, points, parent)})


@mcp.tool()
def reparent_slot(project: str, slot: str, bone: str) -> dict:
    """Move a slot to another bone without moving its art."""
    p = _open(project)
    rig.reparent_slot(p.data, slot, bone)
    return _saved(p, {"slot": slot, "bone": bone})


# ------------------------------------------------------------------------ mesh
@mcp.tool()
def rig_mesh(project: str, slot: str, bones: list[str] | None = None, auto_bones: bool = True,
             detail: float = 1.0, max_vertices: int = 300, pad: float = 2.0, smooth: float = 1.0,
             min_weight: float = 0.05, max_influences: int = 4, attachment: str = "") -> dict:
    """Turn a slot's region into a clean contour mesh (or re-mesh a mesh) with
    bone-heat weights.

    Outline traced from alpha and simplified without clipping art; interior
    vertices denser at joints; conforming Delaunay (valid for Spine's
    importer). Weights diffuse from bone *segments* over the mesh, so they
    blend smoothly across joints and never leak across gaps in the art.

    bones        bones to weight to; omit with auto_bones=True to pick the slot
                 bone + descendants that touch the part; [] with
                 auto_bones=False gives an unweighted mesh.
    detail       vertex density (0.5 light … 1 balanced … 2 dense)
    smooth       >1 widens weight blending across joints, <1 tightens
    """
    p = _open(project)
    b: Any = bones if bones else ("auto" if auto_bones else None)
    return _saved(p, _rig_mesh(p, slot, attachment or None, b, detail, max_vertices, pad, 8, min_weight,
                               max_influences, smooth))


# ----------------------------------------------------------------- constraints
@mcp.tool()
def rig_ik(project: str, bones: list[str], target: str = "", target_parent: str = "",
           bend_positive: bool | None = None, softness: float = 0, stretch: bool = False, mix: float = 1) -> dict:
    """1- or 2-bone IK (e.g. ["upper_arm", "forearm"]). Creates a target bone at
    the chain tip unless `target` names one. Bend direction defaults to the
    setup pose's own bend. The target goes under juice_core when juice bones
    exist (so slams carry it), else under root."""
    p = _open(project)
    return _saved(p, rig.add_ik(p.data, bones, target or None, target_parent or None, None, bend_positive,
                                softness, stretch, False, mix))


@mcp.tool()
def rig_physics(project: str, bones: list[str], preset: str = "hair", taper: float = 0.15,
                overrides: dict | None = None) -> dict:
    """Spine 4.2 physics constraints (runtime secondary motion, no baked keys).
    presets: hair, cloth, tail, ribbon, jiggle, antenna, tassel. Down a chain
    each bone is `taper` looser. overrides: any physics field (inertia,
    strength, damping, mass, wind, gravity, limit, rotate, x, y, scaleX, shearX)."""
    p = _open(project)
    return _saved(p, {"constraints": rig.add_physics(p.data, bones, preset, taper, **(overrides or {})),
                      "preset": rig.PHYSICS_PRESETS[preset]})


@mcp.tool()
def rig_transform(project: str, bones: list[str], target: str, mix_rotate: float = 1, mix_x: float = 1,
                  mix_y: float | None = None, mix_scale_x: float = 0, mix_scale_y: float | None = None,
                  mix_shear_y: float = 0, local: bool = False, relative: bool = False,
                  offsets: dict | None = None) -> dict:
    """Transform constraint: `bones` copy `target`'s transform by the mixes.
    local+relative adds the target's local offset (drivers, parallax)."""
    p = _open(project)
    n = rig.add_transform(p.data, bones, target, None, mix_rotate, mix_x, mix_y, mix_scale_x, mix_scale_y,
                          mix_shear_y, local, relative, **(offsets or {}))
    return _saved(p, {"constraint": n})


@mcp.tool()
def rig_strand(project: str, slot: str, n_bones: int = 3, parent: str = "", root_end: str = "auto",
               physics: str = "hair", detail: float = 1.0) -> dict:
    """Hair lock / cape / ribbon / tail in one call: a bone chain along the
    part's own centre line, a heat-weighted mesh and physics.
    root_end: auto(top)|top|bottom|left|right. physics: preset name or "none"."""
    p = _open(project)
    return _saved(p, rig.rig_strand(p, slot, n_bones, parent or None, root_end,
                                    None if physics == "none" else physics, detail=detail))


@mcp.tool()
def rig_turn(project: str, head_bone: str, face_slot: str, features: dict[str, float],
             turn_range: float = 0, pitch: float = 0.6, swap_pairs: list[list[str]] | None = None) -> dict:
    """2.5D head turn driven by ONE control bone (turn_ctrl).

    face_slot becomes a mesh whose middle travels with the control while its
    outline stays pinned (a surface turning, not a sticker sliding).
    features {slot: depth}: nose 1.25, mouth 1.0, brows 0.95, eyes 0.9,
    fringe 0.8; parts behind the head negative: ears -0.35, back hair -0.5.
    Adds a `turn_test` animation. Animate turn_ctrl's translate to turn."""
    p = _open(project)
    return _saved(p, rig.turn_rig(p, head_bone, face_slot, features, turn_range or None, pitch, swap_pairs))


# --------------------------------------------------------------------- motion
@mcp.tool()
def juice_apply(project: str, clips: list[str] | None = None, intensity: float = 1.0,
                durations: dict[str, float] | None = None, fx: bool = False, shine_slot: str = "",
                merge: bool = False, options: dict | None = None) -> dict:
    """Slot-symbol juice. Default clips = the symbol contract:
    idle, land, win, win_loop, anticipation, dim. Extras: scatter_trigger,
    wild_expand, flip, flip_depth, multiplier_fly, win_big, win_mega, win_epic.

    Animates only two inserted bones (juice_ground at the base, juice_core at
    the centre) so the artist's own keys are never touched. One-shots end on
    the setup pose; loops are seamless; events fire for SFX (sfx_land, sfx_win…).
    intensity 0.5 subtle … 1.6 loud. fx=True layers matching FX. shine_slot adds
    a clipped shine sweep in win. options: back=<slot> (flip), rows (wild_expand),
    to=[x,y] (multiplier_fly), darkness (dim)."""
    p = _open(project)
    res = juice_mod.apply(p, clips or "contract", intensity, durations, fx, shine_slot or None, merge,
                          **(options or {}))
    return _saved(p, res)


@mcp.tool()
def fx_generate(project: str, preset: str, x: float = 0, y: float = 0, size: float = 0, intensity: float = 1.0,
                duration: float = 0, color: str = "", into: str = "", start: float = 0.0, parent: str = "root",
                front_of: str = "", behind: str = "", slot: str = "", count: int = 0) -> dict:
    """Add an FX preset built from Spine primitives with procedural textures
    (tinted per slot, so the atlas stays tiny).

    presets: explosion (flash + shockwave + sparks + smoke), shockwave,
    coin_burst (spinning flipbook coins on true parabolas), coin_shower,
    ripple (seamless water rings), glow_pulse, sparkle, shine_sweep (needs
    slot=; light band clipped to that part's outline).
    into: merge into an existing animation (e.g. "win") instead of a new one.
    Each preset fires an event fx_<preset> so the engine can add heavy
    particles (pixi emitters) at the same moment."""
    p = _open(project)
    extra: dict[str, Any] = {}
    if slot:
        extra["slot"] = slot
    if count and preset in ("coin_burst", "coin_shower", "sparkle"):
        extra["count"] = count
    res = fx_mod.generate(p, preset, x, y, size or None, intensity, duration or None, color or None, parent,
                          into or None, start, None, front_of or None, behind or None, **extra)
    return _saved(p, res)


@mcp.tool()
def fx_recipe(project: str = "", recipe: str = "", x: float = 0, y: float = 0, scale: float = 1.0, start: float = 0.0,
              duration: float = 0.0, color: str = "", intensity: float = 1.0, seed: int = 7, into: str = "",
              parent: str = "root", front_of: str = "", behind: str = "", count: int = 0, name: str = "",
              options: dict | None = None) -> dict:
    """Authored FX layers lifted from real reference clips: lotus set (rune_ring, burst_flare, rim_wisps, bloom_aura,
    floor_glow, fireflies, twinkles, plus magic_reveal = all seven timed like the clip, 13.2 s), light_beam (style
    gold | ribbon | blue), and the hybrids portal and electric_frame, whose plasma / lightning part is After Effects:
    they return a ring_hint to pass to ae_fx_to_spine (guide explains). Procedural textures, additive only (one draw call), one group bone per recipe so it
    recolours, resizes and retimes as one piece, and it merges into any animation with into=.

    recipe="" lists every recipe with its options and defaults; recipe="guide" returns the guide (how to use, fork
    and mix them, how they were made, and the traps). x, y = the subject centre in the parent bone's space;
    scale 1 = a ~720-unit canvas with a ~420-wide subject; start = seconds into the animation; duration = life
    window (window recipes) or a time scale (one-shots); color = main tint; intensity = alpha gain; count = tufts /
    motes / stars / sparks; options = recipe-specific values (see the listing). magic_reveal takes
    options={skip: [recipe, ...], overrides: {recipe: {param: value}}}. Each recipe fires an fx_<recipe> event."""
    if recipe == "guide":
        from .fx_recipes_guide import GUIDE
        return {"guide": GUIDE}
    if not recipe:
        return {"recipes": fx_recipes.list_recipes(), "next": 'fx_recipe recipe="guide" for the full guide'}
    if not project:
        raise ValueError("project is required to add a recipe")
    p = _open(project)
    res = fx_recipes.apply(p, recipe, x, y, scale, start, duration, color, intensity, seed, into, parent, front_of,
                           behind, count, name, options)
    return _saved(p, res)


@mcp.tool()
def ae_fx_to_spine(project: str, name: str, aep: str = "", comp: str = "", frames_dir: str = "", fps: float = 0,
                   mode: str = "alpha", seq_mode: str = "once", animation: str = "", start: float = 0.0,
                   hit_ae: float = -1.0, hit_at: float = -1.0, fit_duration: float = 0.0, until: float = 0.0,
                   x: float = 0, y: float = 0, scale: float = 1.0, max_size: int = 0, max_frames: int = 0,
                   blend: str = "", color: str = "FFFFFFFF", parent: str = "root", front_of: str = "",
                   behind: str = "", fade: float = 0.0, start_frame: int = -1, end_frame: int = -1,
                   keep_frames: str = "") -> dict:
    """Render an After Effects comp and play it in Spine as a frame sequence, timing matched to the comp.

    Source: aep + comp (rendered headless with aerender from the SAVED .aep, over the work area, never
    touching the project open in the AE window), or frames_dir + fps (frames already rendered: .tif
    premultiplied, or .png).
    mode: "alpha" (the comp's own transparency; normal blend) or "additive" (light on black: alpha from
    brightness; additive blend). blend overrides the slot blend.
    Timing: playback speed equals the comp's (delay = 1/comp fps). Place it with start= (seconds into the
    Spine animation) or, to land an AE moment on a Spine one, hit_ae= (seconds in the comp, e.g. the
    impact) + hit_at= (Spine time it should coincide with). fit_duration= stretches the sequence to span that
    many seconds (loops that must divide the symbol's loop). seq_mode: once | loop | pingpong; a loop runs to
    until= (default: the end of the animation it is merged into). max_frames/max_size shrink it (every Nth
    frame; longest side in px), scale = game units per comp pixel, fade = fade-out seconds.
    animation= merges into an existing animation, otherwise ae_<name> is created. Leading and trailing empty
    frames are trimmed. Frames land in images/ae/<name>_NN.png; an event ae_<name> fires at the start."""
    p = _open(project)
    res = ae_bridge.fx_to_spine(
        p, name, aep=aep, comp=comp, frames_dir=frames_dir, fps=fps, mode=mode, seq_mode=seq_mode,
        animation=animation, start=start, hit_ae=None if hit_ae < 0 else hit_ae,
        hit_at=None if hit_at < 0 else hit_at, fit_duration=fit_duration, until=until, x=x, y=y, scale=scale,
        max_size=max_size, max_frames=max_frames, blend=blend, color=color, parent=parent, front_of=front_of,
        behind=behind, fade=fade, start_frame=None if start_frame < 0 else start_frame,
        end_frame=None if end_frame < 0 else end_frame, keep_frames=keep_frames)
    return _saved(p, res)


@mcp.tool()
def ae_template(name: str = "", params: dict | None = None, out_dir: str = "") -> dict:
    """Build an After Effects FX comp from a template: returns a script to run in AE (nothing is rendered here).

    name="" lists the templates with their parameters and defaults. Otherwise name is one of: glow_pulse,
    shockwave, sparkle, relief_shimmer (light wave over a picture, traced by its relief or a depth map),
    fire, lightning, burst (parabolic sparks), splash. params override the defaults (comp= names the comp;
    save_as= saves the open AE project to that .aep right after, which aerender needs).
    Then: run the returned `run_with` with the After Effects MCP's ae_run_script (it creates the comp in an
    ae_fx_templates folder of the OPEN project and returns its name, size, fps, frames), save the project, and
    pass the comp to ae_fx_to_spine (use mode="additive" when the result says so). After Effects caches
    rendered frames by comp name: when tuning, give each attempt a new comp name."""
    if not name:
        return {"templates": ae_templates.list_templates()}
    return ae_templates.build_script(name, params or {}, out_dir or None)


@mcp.tool()
def add_keys(project: str, animation: str, bone: str = "", slot: str = "", timeline: str = "rotate",
             keys: list[list] | None = None, ease: str = "sine_in_out", replace_animation: bool = False) -> dict:
    """Key one timeline with named easing (Spine curves are written for you).

    Bone timelines: rotate [t, deg], translate/scale/shear [t, x, y],
    translatex/translatey/scalex/scaley [t, v]. Slot timelines: rgba/rgb
    [t, "RRGGBBAA"], attachment [t, name-or-null]. Values are offsets from the
    setup pose (Spine semantics). Append an easing name to a key to override
    `ease` for the segment leaving it.
    Easings: anticipate, back_in, back_in_out, back_out, cubic_in, cubic_in_out,
    cubic_out, ease, expo_in, expo_in_out, expo_out, in, in_out, linear, out,
    quad_in, quad_in_out, quad_out, sine_in, sine_in_out, sine_out, snap,
    stepped"""
    p = _open(project)
    ab = AnimBuilder(p.data, animation, replace=replace_animation)
    keys = keys or []
    if bone:
        ab.bone(bone, timeline, keys, ease)
    elif slot:
        if timeline == "attachment":
            ab.slot_attachment(slot, [(k[0], k[1]) for k in keys])
        else:
            ab.slot_color(slot, keys, ease, timeline)
    else:
        raise ValueError("give bone= or slot=")
    return _saved(p, {"animation": animation, "duration": round(ab.a.duration(), 3)})


@mcp.tool()
def add_event(project: str, animation: str, time: float, name: str, string: str = "", int_value: int = 0,
              float_value: float = 0) -> dict:
    """Fire a Spine event (SFX cue, rollup start/stop, particle trigger) in an animation."""
    p = _open(project)
    kw: dict[str, Any] = {}
    if string:
        kw["string"] = string
    if int_value:
        kw["int"] = int_value
    if float_value:
        kw["float"] = float_value
    AnimBuilder(p.data, animation, replace=False).event(time, name, **kw)
    return _saved(p, {"animation": animation, "event": name, "time": time})


# ------------------------------------------------------------------------- QA
@mcp.tool()
def validate(project: str, runtime_check: bool = True) -> dict:
    """Structural validation (references, weights, triangulations, UV range,
    curves, events) plus — when Node is available — loading the skeleton in
    the official spine-core runtime and applying every animation frame by
    frame (non-finite vertices, missing regions)."""
    p = _open(project)
    out = qa.validate(p.data)
    if runtime_check and runtime.available():
        r = runtime.load_check(p)
        out["runtime"] = {k: r.get(k) for k in ("ok", "error", "stage", "problems")}
        out["runtime"]["animations"] = {n: {"events": a["events"], "max_vertices": a["maxVertices"]}
                                        for n, a in r.get("animations", {}).items()}
        out["ok"] = out["ok"] and bool(r.get("ok"))
    return out


@mcp.tool()
def qa_budget(project: str, profile: str = "mobile_symbol", atlas: str = "") -> dict:
    """Performance budget for mobile web. Profiles: mobile_symbol,
    mobile_banner, mobile_character, desktop. Counts bones, slots, vertices,
    weighted vertices, clipping, physics, deform keys, influences, atlas pages,
    and estimates draw calls (every blend-mode or page change along the draw
    order breaks the batch). Returns what is over budget and how to fix it."""
    p = _open(project)
    pages, region_pages = None, None
    if atlas:
        a = atlas_mod.parse_atlas(atlas)
        pages = [tuple(int(v) for v in pg.get("size", "0,0").split(",")) for pg in a["pages"].values()]
        region_pages = {k: v["page"] for k, v in a["regions"].items()}
    return qa.budget(p.data, profile, page_sizes=pages, region_pages=region_pages)


@mcp.tool()
def preview(project: str, animations: list[str] | None = None, out_dir: str = "", size: int = 360,
            fps: float = 20, wire: bool = False) -> dict:
    """Render animations through the official spine-core runtime (IK, physics,
    clipping all solved) to GIFs + contact sheets, plus a setup-pose PNG."""
    p = _open(project)
    out = Path(out_dir) if out_dir else p.root / "previews"
    out.mkdir(parents=True, exist_ok=True)
    names = animations or list(p.data.animations)
    dump = runtime.run(p, animations=names, fps=fps, geometry=True)
    if not dump.get("ok") and dump.get("error"):
        return {"ok": False, "error": dump["error"]}
    res = {"setup": render.render_setup(dump, out / "setup.png", size, wire=wire)}
    for n in names:
        if n in dump["animations"]:
            res[n] = render.render_animation(dump, n, out, size, wire=wire)
    shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)
    res["problems"] = dump.get("problems", [])
    return res


# ---------------------------------------------------------------------- export
@mcp.tool()
def pack_atlas(project: str, out_dir: str = "", name: str = "", max_size: int = 2048, scale: float = 1.0,
               pma: bool = True, strip_whitespace: bool = True) -> dict:
    """Pack every image the skeleton references (sequence frames included)
    into a Spine 4.x .atlas + pages. Copies the skeleton JSON next to it, so
    out_dir is a ready runtime folder."""
    p = _open(project)
    out = Path(out_dir) if out_dir else p.root / "export"
    res = atlas_mod.pack(p, out, name or p.name, max_size, 2, strip_whitespace, pma, scale)
    js = out / f"{name or p.name}.json"
    data = p.data.model_copy(deep=True)
    if scale != 1.0:
        res["note"] = "atlas packed at scale; set the runtime loader scale to match or export at 1.0"
    data.save(js, indent=None)
    res["json"] = str(js)
    return res


@mcp.tool()
def make_editable(project: str, out_spine: str = "") -> dict:
    """Import the project into an editable .spine file with the licensed Spine
    editor CLI. Reports any repairs the importer made."""
    p = _open(project)
    if not spine_cli.available():
        return {"ok": False, "error": f"Spine CLI not found at {spine_cli.SPINE_BIN} (set SPINE_BIN)"}
    p.save()
    return spine_cli.make_project(str(p.path), out_spine or str(p.root / f"{p.name}.spine"))


@mcp.tool()
def export_runtime(spine_project: str, out_dir: str, fmt: str = "json") -> dict:
    """Export a .spine project to runtime data with the Spine CLI (json|binary
    or a path to an export-settings JSON)."""
    return spine_cli.export_project(spine_project, out_dir, fmt)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
