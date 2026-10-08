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

from . import ae_bridge, ae_fx_memory, ae_fx_visual_match, ae_look, ae_templates, ae_vfx_director, draw_order
from . import relight as relight_mod
from . import animation_opt
from . import atlas as atlas_mod
from . import fx as fx_mod
from . import fx_recipes, fx_style
from . import juice as juice_mod
from . import psd as psd_mod
from . import qa, render, rig, runtime, samples, spine_cli, volume25d
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
               groups_as_bones: bool = False, include_hidden: bool = False, scale: float = 1.0,
               alpha_threshold: int = 8) -> dict:
    """PSD → project: one slot per visible layer, placed exactly as on the
    canvas, PNGs cropped to content, Photoshop blend modes mapped.
    origin "center" for symbols, "bottom" for characters standing on y=0."""
    return psd_mod.import_psd(psd, out_dir, name or None, origin, groups_as_bones, include_hidden, scale,
                              alpha_threshold)


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


@mcp.tool()
def rig_volume_2p5d(project: str, slots: list[str], strength: float = 0.72, falloff: float = 1.6,
                    rim_weight: float = 0.0, parent: str = "", detail: float = 1.2,
                    max_vertices: int = 280, min_weight: float = 0.03, max_influences: int = 4,
                    physics: str = "none", test_animation: bool = True, name: str = "volume") -> dict:
    """Add a non-destructive 2.5D volume core to one or more slots.

    Existing heat/turn/limb weights are preserved, then a centre-heavy volume
    influence is layered on and renormalised to max_influences. The outline is
    pinned by default (rim_weight=0), so squash/bulge reads as depth instead of
    melting the silhouette. The returned core bone can be animated directly;
    physics="jiggle" adds runtime secondary motion. A sparse volume_test clip is
    created by default so the deformation can be judged immediately."""
    p = _open(project)
    return _saved(p, volume25d.rig_volume(
        p, slots, strength, falloff, rim_weight, parent, detail, max_vertices,
        min_weight, max_influences, physics, test_animation, name))


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
def optimize_animation(project: str, animation: str, mode: str = "editable", tolerance: float = 1.0,
                       recurve: bool = True, force_curved: bool = False, ease_ends: bool = True) -> dict:
    """Turn dense procedural keys into animator-friendly curves.

    mode: fidelity | balanced | editable. Keeps endpoints, extrema, direction
    changes and holds, removes redundant sampled keys within per-channel error
    tolerances, then rebuilds smooth monotone Bezier handles. Existing authored
    or stepped curves are untouched unless force_curved=True. Events,
    attachments and draw order are never simplified."""
    p = _open(project)
    return _saved(p, animation_opt.optimize(
        p, animation, mode, tolerance, recurve, force_curved, ease_ends))


@mcp.tool()
def volume_bounce(project: str, bones: list[str], animation: str = "volume_bounce", start: float = 0.0,
                  duration: float = 0.55, strength: float = 0.18, wobble: float = 0.03,
                  merge: bool = False) -> dict:
    """Sparse five-key squash/rebound animation for volume-core bones.

    Intended for bones returned by rig_volume_2p5d. Uses authored ease-in,
    back-out and settle curves rather than an evenly sampled bake."""
    p = _open(project)
    return _saved(p, volume25d.bounce(p, bones, animation, start, duration, strength, wobble, merge))


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
              options: dict | None = None, art: dict | None = None, tier: str = "", style: str = "",
              realism: float = -1.0, style_profile: dict | None = None, relight_slots: list[str] | None = None,
              relight_color: str = "", relight_strength: float = 0.0, relight_duration: float = 0.0,
              kit: str = "") -> dict:
    """Authored FX layers lifted from real reference clips: lotus set (rune_ring, burst_flare, rim_wisps, bloom_aura,
    floor_glow, fireflies, twinkles, plus magic_reveal = all seven timed like the clip, 13.2 s), light_beam (style
    gold | ribbon | blue), crosshair / hit_burst / lock_on (reticle locks on, fires, impact), cell_glow (resizable
    9-slice glowing cells that pop), puff (cartoon smoke puff, or flash + ring for an AE smoke_puff), smoke_glow (rising haze with a base glow),
    meteor_trace (comet racing around a frame), projectile (shot on an arc + impact), ice and water (frost, icicles,
    ice_shatter, bubbles, water_splash; AE template caustics), explosion and shine, the reel moments reel_stop (spring thud, squash, dust, screen shake on your reel/screen bones
    through inserted carrier bones) and anticipation_reel (accelerating heartbeat glow, edge flames or sparks, dimmed
    neighbours), the slot families (spin: near_miss, spin_blur, turbo_spin, screen_shake; wins: payline,
    win_highlight, multiplier_stack, win_rollup; payouts: coin_fountain, cascade_pop; features: wild_land, expanding_wild,
    scatter_trigger, free_spins_transition; bonus: pick_reveal, hold_respin, jackpot_wheel, meter_fill; ambient: weather,
    god_rays, water_surface, heat_shimmer, fog_roll, lightning_storm; UI: button_press, idle_shimmer, focus_glow, padlock,
    popup; saber = a port of Video Copilot's Saber beams with 12 presets and an ae_hint for the saber AE template; props = prop_idle, liquid_slosh + the prop library (prop_peek, prop_shake, prop_open, prop_hit, prop_upgrade, prop_shatter, prop_absorb, prop_overflow, counter_plate, prop_multiplier_slam, prop_charge, gem_glint, prop_bob, prop_blink, prop_breathe_heavy, prop_hover_spin, prop_dangle, prop_sway_wind, flame_wick, liquid_bubble, prop_drip, prop_steam, prop_electric, prop_freeze, prop_dissolve, smoke_wisp) and prop bundles (bonus_chest_reveal, collect_into_prop, pinata_style_break, magic_vessel), all on YOUR rig through carriers; cluster family = cluster_dim (+ _in intro), combo_banner, amount_to_bar, jelly_pop, scatter_shine; pinata family = wild_glow, wild_transform, mult_cell_glow, cell_pop, confetti_burst, mult_streak, wild_merge, coins_to_bar, bar_sweep, pinata_hit, jar_burst, banner_backdrop from one picture kit (swap a texture pack in by name with art=, retune it with options gain / thick); recipes that move your reel / symbol / screen / button bones do it through inserted carrier bones, never your
    own keys), and the hybrids portal and electric_frame, whose plasma / lightning part is
    After Effects: they return a ring_hint to pass to ae_fx_to_spine (guide explains). Procedural textures, additive only (one draw call), one group bone per recipe so it
    recolours, resizes and retimes as one piece, and it merges into any animation with into=.

    recipe="" lists every recipe with its options and defaults; recipe="guide" returns the guide (how to use, fork
    and mix them, how they were made, and the traps). x, y = the subject centre in the parent bone's space;
    scale 1 = a ~720-unit canvas with a ~420-wide subject; start = seconds into the animation; duration = life
    window (window recipes) or a time scale (one-shots); color = main tint; intensity = alpha gain; count = tufts /
    motes / stars / sparks; options = recipe-specific values (see the listing). magic_reveal takes
    options={skip: [recipe, ...], overrides: {recipe: {param: value}}}. Each recipe fires an fx_<recipe> event.

    art = your own pictures instead of the generated ones, keeping all the motion: {role: "file.png" |
    "file.psd#Layer" | {path, blend, scale, slice, px, anchor}}; the roles of each recipe are in the listing
    (e.g. crosshair: reticle). For lock_on / magic_reveal key it by member: {"crosshair": {"reticle": ...}}.

    kit = "realistic": every art role you did NOT give gets a bundled photographic CC0 picture chosen by role name
    (real smoke, real lightning, lens flares, smoke rings, a painted flash; Kenney, CC0), so the procedural look
    becomes realistic in one argument; game-art roles (symbol, coin, reticle, plates, confetti), 9-slice frames and
    mesh strips stay procedural. Bundles pass it to every member. The result's kit.roles lists what it filled;
    recipe="kit" returns the role -> picture table; art={role: "kit:<picture>"} names a kit picture directly.
    Realistic recipes: bolt_link (real lightning re-striking between point pairs), crackle (electricity or flames
    flickering round a shape) and surface_glow (an additive copy of YOUR slot that glows red-hot / icy / charged and
    follows its attachment keys).

    tier = small | medium | big | mega | epic: one recipe covers every win size (scale, counts, one-shot time and the
    recipe's own tier overrides; see the listing's `tiers`).

    style = stylized | premium | realistic retunes the SAME physical recipe instead of choosing a different effect.
    realism=0..1 interpolates stylized -> realistic when style is omitted. style_profile can deep-merge custom/captured
    tuning. relight_slots=[...] adds a short additive response using the target art itself; relight_color/strength/duration
    override its source colour and pulse. Results include semantic depth groups (back / subject / front / lens) and,
    when styled, recommended depth_parallax values. Use fx_style_profile to list/capture profiles and qa_fx_premium
    for a heuristic art-direction pass.

    Bundles: sequence = any list of recipes with offsets into one
    animation (options={steps: [{recipe, start, dx, dy, ...any fx_recipe argument}]}); win_banner = Big/Mega/Epic banner
    from one recipe (tier= picks the layers; options={banner: bone} slams your banner art in on an exact spring)."""
    if recipe == "guide":
        from .fx_recipes_guide import GUIDE
        return {"guide": GUIDE}
    if recipe == "kit":
        from . import fx_kit
        return {"kit": fx_kit.table({n: d.get("roles", {}) for n, d in fx_recipes.RECIPES.items()})}
    if not recipe:
        from . import fx_kit
        return {"recipes": fx_recipes.list_recipes(), "kits": fx_kit.KITS,
                "next": 'fx_recipe recipe="guide" for the full guide; recipe="kit" for the kit role table'}
    if not project:
        raise ValueError("project is required to add a recipe")
    p = _open(project)
    res = fx_recipes.apply(p, recipe, x, y, scale, start, duration, color, intensity, seed, into, parent, front_of,
                           behind, count, name, options, art, tier, style, realism, style_profile,
                           relight_slots, relight_color, relight_strength, relight_duration, kit)
    return _saved(p, res)


@mcp.tool()
def fx_style_profile(style: str = "", realism: float = -1.0, metrics: dict | None = None,
                     profile: dict | None = None) -> dict:
    """List/resolve the global FX art-direction profiles.

    style: stylized | premium | realistic.
    realism: 0..1 interpolates stylized -> realistic when style is omitted.
    profile: advanced deep-merge overrides (the result can be passed to fx_recipe style_profile=).
    metrics: normalised measurements from clip-breakdown (realism, glow_spread, particle_density,
    motion_exaggeration, decay, saturation; each 0..1). When metrics is supplied this returns a captured profile
    ready for style_profile=, keeping reference analysis separate from the low-level Spine package."""
    if metrics is not None:
        return fx_style.capture(metrics)
    if not style and realism < 0 and not profile:
        return fx_style.listing()
    return {"profile": fx_style.resolve(style, realism, profile)}


@mcp.tool()
def ae_vfx_plan(brief: str = "", event: str = "impact", style: str = "realistic", intensity: float = 1.0,
                fps: float = 30.0, duration: float = 0.0, target: str = "mobile_feature") -> dict:
    """Plan a production AE effect before touching the comp.

    event: impact | fire_hit | electric_hit | magic_reveal | win_burst | ambient.
    style: stylized | premium | realistic | anime.
    target: mobile_symbol | mobile_feature | mobile_hero | desktop_preview.
    Returns the comp layer hierarchy, compressed impact timing, look rules, review targets and a
    conservative AE->Spine sequence budget. Use this before issuing low-level After Effects MCP calls."""
    return ae_vfx_director.plan(brief, event, style, intensity, fps, duration, target)


@mcp.tool()
def ae_fx_capture(source: str, library_dir: str, name: str, fps: float = 24.0,
                  mask_mode: str = "auto", background: str = "", max_frames: int = 96,
                  archive_source: bool = True) -> dict:
    """Reverse engineer a VFX reference video or PNG sequence into a persistent editable recipe.

    The capture stores an FX energy/timing curve, impact beats, center of motion, spread,
    dominant colors and reference contact sheet under library_dir/<name>/.
    Source = video (ffmpeg installed) or image-sequence folder (supply fps).
    mask_mode = auto|alpha|black|green|background|none. For footage shot over a
    scene, provide background=<clean plate PNG> and mask_mode=background.
    This estimates visible behavior, not unavailable original AE/particle settings.
    Next: ae_fx_remix(recipe=returned recipe path)."""
    return ae_fx_memory.capture(source, library_dir, name, fps, mask_mode, background,
                                max_frames, archive_source)


@mcp.tool()
def ae_fx_library(library_dir: str, query: str = "") -> dict:
    """Search saved reference-footage FX recipes by name or event family.

    Returns reusable recipe paths, reference thumbnails, duration and captured behavior.
    These recipes can be passed directly to ae_fx_remix to make new color/style/
    high-impact variations at any time."""
    return ae_fx_memory.library(library_dir, query)


@mcp.tool()
def ae_fx_remix(recipe: str, out_dir: str, strength: float = 1.0, style: str = "premium",
                color: str = "", speed: float = 1.0, spark_count: int = -1,
                comp_name: str = "", save_as: str = "", canvas: int = 1024) -> dict:
    """Build a reusable editable native AE FX composition from a captured reference recipe.

    strength 0.25..3 boosts impact, scale and particle energy; style = stylized,
    premium, realistic, anime; color = #RRGGBB; speed 0.25..4 retimes the keyframes;
    spark_count >= 0 overrides the automatic count. Returns a .jsx script that builds
    live keyframed core, halo, ring and spark layers with Impact Strength and
    Global Scale controls. Run using AE MCP ae_run_script. Optional save_as=.aep
    saves the created project. A multi-layer AE comp is a reusable library asset;
    a single-layer .ffx can be saved inside AE via Animation > Save Animation Preset.
    This is a first-pass procedural rebuild, not an exact inverse render."""
    return ae_fx_memory.remix(recipe, out_dir, strength, style, color, speed,
                              spark_count, comp_name, save_as, canvas)


@mcp.tool()
def ae_fx_match(recipe: str, out_dir: str, candidate_frames: str = "", candidate_fps: float = 0.0,
                aep: str = "", comp: str = "", reference: str = "", background: str = "",
                candidate_mode: str = "alpha", max_frames: int = 40,
                iteration: int = 1, style: str = "premium",
                strength: float = 1.0, color: str = "", speed: float = 1.0,
                canvas: int = 1024, tuning: dict | None = None) -> dict:
    """Compare the actual rendered AE effect with its captured reference, then AUTO-CORRECT
    the next editable After Effects build. Re-run after every AE render for a genuine feedback loop.

    Use candidate_frames (sequence + candidate_fps), OR saved .aep + comp
    (rendered with aerender). Reference footage path comes from ae_fx_capture's
    recipe; reference= overrides it if moved. background= clean plate for
    original composite footage; candidate_mode=alpha|black|none.

    Reports frame-matched image/alpha/energy/size/position/timing/texture error,
    writes comparison JPG and JSON, calculates damped corrections and produces
    the next .jsx automatically. Pass the returned tuning to the NEXT call
    after running/rendering the new JSX. Stop based on measured scores and
    art direction, NOT on unverified predicted improvements.
    Original reference is never altered. Native AE source layers stay editable."""
    return ae_fx_visual_match.compare(
        recipe=recipe, out_dir=out_dir, candidate_frames=candidate_frames,
        candidate_fps=candidate_fps, aep=aep, comp=comp, reference=reference,
        background=background, candidate_mode=candidate_mode, max_frames=max_frames,
        iteration=iteration, style=style, strength=strength, color=color,
        speed=speed, canvas=canvas, tuning=tuning)


@mcp.tool()
def ae_vfx_review(metrics: dict[str, float], style: str = "realistic") -> dict:
    """Self-review a rendered AE VFX pass from 0..10 measurements.

    metrics: readability, impact, depth, lighting_integration, motion_flow, texture_quality, timing,
    and clarity (or clutter, where clarity=10-clutter). Returns a weighted score and the smallest
    useful revision list. When clarity is weak, subtraction is always recommended before adding FX."""
    return ae_vfx_director.review(metrics, style)


@mcp.tool()
def ae_vfx_to_spine(project: str, name: str, aep: str = "", comp: str = "", frames_dir: str = "", fps: float = 0,
                    event: str = "impact", style: str = "realistic", target: str = "mobile_feature",
                    intensity: float = 1.0, duration: float = 0.0, mode: str = "alpha",
                    seq_mode: str = "once", animation: str = "", start: float = 0.0,
                    hit_ae: float = -1.0, hit_at: float = -1.0, fit_duration: float = 0.0, until: float = 0.0,
                    x: float = 0, y: float = 0, scale: float = 1.0, max_size: int = 0, max_frames: int = 0,
                    blend: str = "", color: str = "FFFFFFFF", parent: str = "root", front_of: str = "",
                    behind: str = "", fade: float = 0.0, start_frame: int = -1, end_frame: int = -1,
                    keep_frames: str = "", copies: list[list[float | None] | dict[str, Any]] | None = None,
                    feather: float = -1.0, anchor: list[float] | None = None,
                    deform_like: list[str] | None = None, min_fps: float = -1.0, tintable: bool = False,
                    tint: str = "", spectrum: float = 0.0, spectrum_bands: int = 3, spectrum_turn: float = 0.0) -> dict:
    """Production AE->Spine import with automatic mobile-safe sequence budgets.

    This wraps ae_fx_to_spine rather than replacing it. The director trims empty frames, keeps playback
    speed when subsampling, caps frame count/texture size by target, feathers comp borders, and encourages
    copies= so repeated effects share one frame set (copies=[[x, y, start, scale, rotation], ...] as in
    ae_fx_to_spine). Explicit max_size/max_frames/feather override the policy.
    min_fps (default 12; 0 = off; with an explicit max_size AND max_frames it is off unless given): subsampling never
    drops below this playback rate. Loops/pingpongs shrink the texture first, then frames; one-shots drop frames
    first, down to min_fps, then shrink the texture, so a 16-frame 24 fps fire loop stays smooth.
    tintable / tint / spectrum: one grey frame set recoloured per slot, or split into a spectrum (see ae_fx_to_spine)."""
    p = _open(project)
    res = ae_vfx_director.import_optimized(
        p, name, event=event, style=style, target=target, intensity=intensity, duration=duration,
        aep=aep, comp=comp, frames_dir=frames_dir, fps=fps, mode=mode, seq_mode=seq_mode,
        animation=animation, start=start, hit_ae=None if hit_ae < 0 else hit_ae,
        hit_at=None if hit_at < 0 else hit_at, fit_duration=fit_duration, until=until, x=x, y=y, scale=scale,
        max_size=max_size, max_frames=max_frames, blend=blend, color=color, parent=parent, front_of=front_of,
        behind=behind, fade=fade, start_frame=None if start_frame < 0 else start_frame,
        end_frame=None if end_frame < 0 else end_frame, keep_frames=keep_frames, copies=copies,
        feather=feather, anchor=anchor, deform_like=deform_like, min_fps=None if min_fps < 0 else min_fps,
        tintable=tintable, tint=tint, spectrum=spectrum, spectrum_bands=spectrum_bands, spectrum_turn=spectrum_turn)
    return _saved(p, res)


@mcp.tool()
def qa_fx_premium(project: str, animation: str = "", subject_slots: list[str] | None = None) -> dict:
    """Heuristic art-direction QA for an FX build: lighting integration, depth separation, impact hierarchy,
    material richness and mobile readability. It flags additive white-soup, one-plane effects, excessive lens
    layers and missing reactive subject light. This is a lint pass; final judgement still belongs to preview/video."""
    p = _open(project)
    return fx_style.qa_premium(p, animation, subject_slots)


@mcp.tool()
def ae_fx_to_spine(project: str, name: str, aep: str = "", comp: str = "", frames_dir: str = "", fps: float = 0,
                   mode: str = "alpha", seq_mode: str = "once", animation: str = "", start: float = 0.0,
                   hit_ae: float = -1.0, hit_at: float = -1.0, fit_duration: float = 0.0, until: float = 0.0,
                   x: float = 0, y: float = 0, scale: float = 1.0, max_size: int = 0, max_frames: int = 0,
                   blend: str = "", color: str = "FFFFFFFF", parent: str = "root", front_of: str = "",
                   behind: str = "", fade: float = 0.0, start_frame: int = -1, end_frame: int = -1,
                   keep_frames: str = "", copies: list[list[float | None] | dict[str, Any]] | None = None,
                   feather: float = 0.0, anchor: list[float] | None = None,
                   deform_like: list[str] | None = None, min_fps: float = 0.0, tintable: bool = False,
                   tint: str = "", spectrum: float = 0.0, spectrum_bands: int = 3, spectrum_turn: float = 0.0) -> dict:
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
    frames are trimmed. Frames land in images/ae/<name>_NN.png; an event ae_<name> fires at the start.
    copies=[[x, y], [x, y, start], [x, y, start, scale, rotation], ...] plays more instances that SHARE the frames
    (one set in the atlas): glitter in every cell of a cluster, a crackle on every scatter, sparks on three hits at
    escalating sizes ([[0, 0, 0.4, 1.3], [0, 0, 0.8, 1.7]]). start null = the original's; scale multiplies that
    instance's size, rotation in degrees. The result keeps copies = their slot names and adds copy_instances
    ({slot, bone, x, y, start, end, scale, rotation} each).
    min_fps (0 = off): never subsample below this playback rate (see ae_vfx_to_spine).
    anchor=[fx, fy]: the comp point (fractions, y down) that lands on x, y (an off-centre lens-flare source);
    feather (0..0.5): fade the frames to nothing toward their border (a halo the comp edge would cut square);
    deform_like=[slots]: the sequence becomes a grid mesh whose weights are copied from those slots' meshes, so
    light baked on the art (surface_sweep) bends with the art (its tilt, its 2.5D turn).
    tintable=True: the frames are stored GREY and coloured by the slot's light + dark colour (Spine two-colour tint,
    "tint black"), fitted so it still looks like the render; then ONE frame set plays in any colour: tint="RRGGBB"
    turns the fitted pair to that hue (a white core stays white), tint="LLLLLL/DDDDDD" sets light/dark exactly, and
    copies take their own: copies=[{"x": 0, "y": 0, "tint": "FF3030"}, ...] (a dict copy also takes "offset": frames
    into the sequence it starts at, so looping copies run out of step, and "parent": the bone it hangs from). The result's tint.grade says whether
    the effect is two-tone: good for lightning, electricity, frost, ice, smoke; fair for cooling sparks; poor for fire and gold
    glows (white -> yellow -> orange -> red needs more than two colours: make those variants in AE). The game
    runtime must draw two-colour tint (spine-webgl does; spine-pixi turns it on for slots with a dark colour).
    spectrum (needs tintable): every instance is split into additive colour bands of the same frames, each scaled
    `spectrum` more than the next (red outermost) and turned spectrum_turn degrees: white where they overlap, rainbow
    fringes at every edge (a prism / chromatic dispersion) for no extra frames. spectrum_bands 3 (red, green, blue:
    cheapest) or 6 (red, yellow, green, cyan, blue, magenta: smoother). Judged on prism_glow: 0.03 is a faint
    fringe, spectrum=0.05 spectrum_bands=6 spectrum_turn=2 fans every ray into a rainbow. Each band redraws the
    glow's area (fill cost on mobile)."""
    p = _open(project)
    res = ae_bridge.fx_to_spine(
        p, name, aep=aep, comp=comp, frames_dir=frames_dir, fps=fps, mode=mode, seq_mode=seq_mode,
        animation=animation, start=start, hit_ae=None if hit_ae < 0 else hit_ae,
        hit_at=None if hit_at < 0 else hit_at, fit_duration=fit_duration, until=until, x=x, y=y, scale=scale,
        max_size=max_size, max_frames=max_frames, blend=blend, color=color, parent=parent, front_of=front_of,
        behind=behind, fade=fade, start_frame=None if start_frame < 0 else start_frame,
        end_frame=None if end_frame < 0 else end_frame, keep_frames=keep_frames, copies=copies, feather=feather,
        anchor=anchor, deform_like=deform_like, min_fps=min_fps, tintable=tintable, tint=tint, spectrum=spectrum,
        spectrum_bands=spectrum_bands, spectrum_turn=spectrum_turn)
    return _saved(p, res)


@mcp.tool()
def relight_from_fx(project: str, animation: str, sources: list[str], subjects: list[str], strength: float = 0.6,
                    floor: float = 0.0, gamma: float = 1.0, norm: float = 0.0, fps: float = 30,
                    name: str = "relight", saturation: float = 1.0) -> dict:
    """Light the subject with the effect, measured instead of hand-keyed (the director's first realism rule).

    Plays `animation` in the spine-core runtime; every frame, each draw of the `sources` slots (names or globs such
    as "ae_flash*") adds its displayed area x opacity x the mean light of the exact texture region shown (a
    sequence's current frame), in the colour it is drawn (two-colour tint included). Additive twins of `subjects`
    (e.g. a coin's front and back faces; they follow the subject's attachment keys) are keyed to that light:
    alpha = clamp(floor + strength * (E / norm) ** gamma), colour = the light's colour (violet under a violet aura,
    white on a spectrum flash). norm=0 uses this animation's peak; pass the returned norm of one animation to the
    next (idle -> reveal) so the same aura lights the subject equally and only the flash goes beyond. Returns the
    twins, norm, the peak and `hits` (times of the sharpest light rises, for shakes or sounds)."""
    p = _open(project)
    return _saved(p, relight_mod.relight(p, animation, sources, subjects, strength, floor, gamma, norm, fps, name,
                                         saturation))


@mcp.tool()
def optimize_draw_order(project: str, animations: list[str] | None = None, fps: float = 15, apply: bool = True,
                        group_pages: bool | None = None) -> dict:
    """Fewer draw calls, same picture. Regroups the draw order, moving a slot only past neighbours it commutes
    with: both additive (light adds), or never overlapping on screen in any frame where both are drawn (checked on
    the runtime's vertices). Keeps a move only when the REAL calls (runs of blend mode + atlas page among the
    slots drawn, every frame of every animation) go down; clipping ranges stay put; skeletons with draw-order keys
    are left alone. group_pages None tries the plain atlas packing and the grouped one (sequences kept on one
    page) and keeps the better: export with pack_atlas group_sequences=<pack_atlas_group_sequences>. Renders
    sample frames before and after and refuses the change if any pixel moves by more than 2/255. On the coin
    magic pass: reveal 8.0 -> 6.75 mean calls (max 12 -> 8), three-coin loop 10.5 -> 5.1 (max 12 -> 7), 0/255."""
    p = _open(project)
    res = draw_order.optimize(p, animations, fps, apply, group_pages=group_pages)
    return _saved(p, res) if res.get("applied") else res


@mcp.tool()
def ae_quick_look(aep: str = "", comp: str = "", frames_dir: str = "", fps: float = 0, mode: str = "alpha",
                  art: str = "", art_scale: float = 1.0, art_offset: list[float] | None = None,
                  art_in_front: bool = False, background: str = "", out: str = "", tile: int = 260,
                  start_frame: int = -1, end_frame: int = -1, keep_frames: str = "") -> dict:
    """Judge an AE effect BEFORE importing it: one contact-sheet PNG of its four key frames (end of anticipation,
    impact, mid decay, last visible frame), found on the effect's own energy curve, on dark grey and in the scene.

    Source: aep + comp (aerender, from the SAVED .aep) or frames_dir + fps. mode: "alpha" or "additive" (light on
    black), as for ae_fx_to_spine. art: a PNG of the thing it sits on (the coin face), drawn at comp pixels x
    art_scale, centred on the comp + art_offset [x, y] px (y down); art_in_front=True draws it over the effect (an
    aura behind a coin). background: a PNG filling the tile behind everything (the game screen). Read the sheet
    image to judge; the energy curve under it marks the beats. kind: "hit" (anticipation end, impact = the hottest
    frame, mid decay, residual), "build" (rises and holds, e.g. frost: start, half built, fully built, end) or
    "loop" (four evenly spaced frames). Returns the sheet path, the beats (comp frame and seconds), and hit_ae (a
    hit's impact time) or built_at, to pass to ae_fx_to_spine / ae_vfx_to_spine as hit_ae. Default sheet: <tmp>/claude_spine_looks/<comp>.png. Render time is mostly AE
    opening the project (18-22 s for a 300-comp project, 5-8 s for a small one): tune effects in a small .aep."""
    return ae_look.quick_look(aep=aep, comp=comp, frames_dir=frames_dir, fps=fps, mode=mode, art=art,
                              art_scale=art_scale, art_offset=tuple(art_offset or (0.0, 0.0)),
                              art_in_front=art_in_front, background=background, out=out, tile=tile,
                              start_frame=None if start_frame < 0 else start_frame,
                              end_frame=None if end_frame < 0 else end_frame, keep_frames=keep_frames)


@mcp.tool()
def ae_template(name: str = "", params: dict | None = None, out_dir: str = "") -> dict:
    """Build an After Effects FX comp from a template: returns a script to run in AE (nothing is rendered here).

    name="" lists the templates with their parameters and defaults. Otherwise name is one of: glow_pulse,
    shockwave, sparkle, relief_shimmer (light wave over a picture, traced by its relief or a depth map),
    fire, fire_aura (flame ring shooting out of a hole: fists, scatters, power-ups), lightning, burst (parabolic
    sparks), splash, surface_sweep (the art's own colours brightened in a soft band bent round the volume: a
    shine that sits ON the surface), lens_flare (optical flare with a ghost chain), metal_sparks (realistic
    metal-impact sparks, CC Particle World + Echo streaks, additive), frost_creep (frost growing over a coin face
    from its rim and freezing solid, transparent, parent it to the face bone), and the rest the listing shows. params override the defaults (comp= names the comp; save_as= saves the open AE project to that .aep
    right after, which aerender needs, then reopens the artist's own project if it was saved and clean). With no
    AE MCP connected, ask the artist to run the script via File > Scripts > Run Script File (AfterFX.exe -r may
    never reach an open AE), then confirm the comps with ae_check.
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
               pma: bool = True, strip_whitespace: bool = True, group_sequences: bool = False) -> dict:
    """Pack every image the skeleton references (sequence frames included)
    into a Spine 4.x .atlas + pages. Copies the skeleton JSON next to it, so
    out_dir is a ready runtime folder. group_sequences=True keeps each frame
    sequence on as few pages as possible (a sequence spread over pages switches
    texture, one more draw call, from frame to frame); optimize_draw_order
    measures with this packing."""
    p = _open(project)
    out = Path(out_dir) if out_dir else p.root / "export"
    res = atlas_mod.pack(p, out, name or p.name, max_size, 2, strip_whitespace, pma, scale, group=group_sequences)
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


# rig families register their tools on this server (each module starts with `from .server import mcp, _open, _saved`)
from . import tools_face  # noqa: E402,F401   rig_face, face_clip, look_at, lipsync, make_face_sample
from . import tools_addons  # noqa: E402,F401   rig_serpent, rig_flier, attach_rig, sample makers
from . import tools_gait  # noqa: E402,F401   gait, rig_quadruped, make_quadruped_sample
from . import tools_body  # noqa: E402,F401   rig_biped, clip_set, secondary, squash_stretch, qa_character, make_biped_sample
from . import tools_creature  # noqa: E402,F401   rig_creature, make_creature_sample
from . import tools_symbol  # noqa: E402,F401   sphere_spin, liquid_splat, shake, ae_check, edit_slots, clone_art, art_twin, hue_cycle
from . import tools_sugar  # noqa: E402,F401   sugar_splat_ae, sugar_splat_to_spine
from . import tools_library  # noqa: E402,F401   ae_library, ae_library_textures, ae_library_to_spine
from . import tools_coin  # noqa: E402,F401   rig_coin, coin_spin


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
