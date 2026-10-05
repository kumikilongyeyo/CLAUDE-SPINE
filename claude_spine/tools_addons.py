"""MCP tools for the chain rigs and add-ons: rig_serpent, rig_flier, attach_rig and their procedural samples.
Registered on the server's FastMCP instance when imported (server.py imports this module at its end)."""
from __future__ import annotations

from .server import _open, _saved, mcp
from . import rig_addons, rig_chain


def _summary(p) -> dict:
    sk = p.data
    return {"project": str(p.path), "slots": [s.name for s in sk.slots], "bones": len(sk.bones),
            "animations": sorted(sk.animations)}


@mcp.tool()
def rig_serpent(project: str, slot: str = "", n_bones: int = 8, mode: str = "swim", root_end: str = "auto",
                parent: str = "", name: str = "serpent", speed: float = 1.0, wavelength: float = 0.0,
                head_amp: float = -1.0, amp: float = 0.0, exaggerate: float = 1.5, cycles: int = 2,
                turn_angle: float = 40.0, side: float = 1.0, reach: list[float] | None = None,
                clips: list[str] | None = None) -> dict:
    """Fish, eel, snake, dragon body or tentacle: ONE long chain along the body layer with a travelling wave.

    Layers by name (case-insensitive): body (required, one long layer), head + eye*/jaw/mouth (ride the first bone),
    fin* (2-bone strands with physics on the nearest body bone), tail_fin / fluke (strand on the last bone).

    Physics: y(s,t) = A(s) sin(2 pi (s/lambda - f t)) head -> tail, amplitude growing toward the tail
    (head_amp = the head's share). speed (body lengths/s) sets the beat like a fish: f = speed / (0.7 lambda);
    the tail amplitude follows Strouhal St = 0.3 (x exaggerate) unless amp (fraction of length) is given; the head
    recoils sideways and thrust surges the body at 2f. Clips: swim (exact loop, `cycles` beats, event sfx_swim per
    beat), idle_float (slow hover wave + heave), turn (fish C-start: curl, tail kick, spring decay; sfx_turn).
    mode="tentacle": the root is the base (root_end auto = the bottom), wave 1.3 lengths, plus 2-bone reach IK on
    the tip and a `reach` clip (wind-up, constant-curvature strike on an exact spring, grab; sfx_reach).
    reach = [x, y] in the tentacle's frame (x along it from the base). Clips merge by name into existing ones."""
    p = _open(project)
    return _saved(p, rig_chain.rig_serpent(p, slot, n_bones, mode, root_end, parent, name, speed, wavelength,
                                           head_amp, amp, exaggerate, cycles, turn_angle, side, reach, clips=clips))


@mcp.tool()
def rig_flier(project: str, parent: str = "", name: str = "flier", flap_hz: float = 2.4, cycles: int = 2,
              amp: list[float] | None = None, lag: float = 30.0, downstroke: float = 0.58, bob: float = -1.0,
              stabilize_head: bool = True, clips: list[str] | None = None) -> dict:
    """Bird / flier (front view, wings to the sides). Layers by name: body (required), head (stabilised),
    beak/eye*/head_* (ride the head), wing_l / wing_r (3-bone chains, shoulder = the end nearest the body),
    wing_<side>_feather<N> (primary feathers fanning off the hand, strands with physics), tail (strand, physics).

    flap: a warped sine per joint, downstroke = 58% of the beat, each joint `lag` degrees of phase behind the last
    (shoulder leads, tip trails), the hand flexes and the primaries fan shut on the upstroke; the body bobs once per
    beat (lift on the downstroke) while the HEAD stays still (transform constraint to a non-bobbing anchor).
    amp = [shoulder, elbow, hand] degrees (default 40, 15, 20). Clips: flap (loop, sfx_flap per downstroke),
    glide (loop), perch (folded, body bobs, head still with a glance), takeoff (crouch, launch, power strokes; ends
    on setup; sfx_takeoff, sfx_flap), land (flare, braking strokes, touchdown spring; ends EXACTLY on perch's first
    frame so land -> perch is seamless; sfx_land)."""
    p = _open(project)
    return _saved(p, rig_chain.rig_flier(p, parent, name, flap_hz, cycles, amp, lag, downstroke, bob, stabilize_head,
                                         clips=clips))


@mcp.tool()
def attach_rig(project: str = "", kind: str = "", bone: str = "", name: str = "", options: dict | None = None) -> dict:
    """Plug a sub-rig into a named bone of ANY rig; its clips MERGE by name into the host's clips (same name = same
    animation, timelines added; a host clip keeps its length, loops refit to divide it exactly, one-shots retime).

    kind="" lists the kinds with their layer names, default bones and options. Kinds (default bone):
      ears (head): ear_l/ear_r 2-bone strands with physics; clips ear_perk (exact spring overshoot), ear_flatten,
                   ear_swivel (toward options.sound, the far ear lags), idle twitches.
      tail (hips): strand with physics; options.tail_mood happy | alert | angry drives idle; clips tail_happy,
                   tail_alert, tail_angry; reacts in walk / run / win if the host has them.
      wings (chest): wing_l/wing_r (+ wing_<side>_feather<N>); options.wing_type feathered | bat | insect;
                   idle = slow breathing fold, excited = flutter; win reaction.
      horns (head): horn*/antler*: rigid, tiny inertia lag on head turns (physics on shear only).
      digitigrade (hips): leg_l/leg_r zigzag layers -> thigh, shin, metatarsus with the reversed hock, IK feet
                   (foot_l/_r ride them); walk (planted feet, sfx_step with l/r in the string), run reaction.
      mermaid (hips): mermaid_tail (+ fluke) as a rig_serpent chain; legs hidden; swim, idle_float, idle.
      snake_hair (head): snake<N> (8-12): each a serpent with its own randomised idle; snake_look (shared IK target).
      fur (any): options.slots or fur*/coat*/mane*/ruff*: outline bones with physics; fur_ruffle (wind gust).
      glow (any): options.slots or eye*/rune*/vein*: the FX shine pulse (eyes) or electric_frame (runes) via
                   fx_recipes.apply, tiled into options.clips (default idle) with exact loops and fx_* events.
    name prefixes the new bones (attach the same kind twice)."""
    if not kind:
        return {"kinds": {k: {"layers": rig_addons.ADDON_LAYERS[k], "default_bone": list(rig_addons.BONES[k]) or "slot's bone",
                              "options": {o: {"default": v[0], "what": v[1]} for o, v in rig_addons.OPTIONS[k].items()}}
                          for k in rig_addons.KINDS}}
    if not project:
        raise ValueError("project is required to attach a rig")
    p = _open(project)
    return _saved(p, rig_addons.attach_rig(p, kind, bone, name, options))


@mcp.tool()
def make_serpent_sample(out_dir: str, kind: str = "fish") -> dict:
    """Procedural sample for rig_serpent. kind "fish": a koi (body, head, eye, fin_dorsal, fin_pectoral, tail_fin),
    head to the right. kind "tentacle": one tapered tentacle with suckers, base at the bottom."""
    return _summary(rig_chain.make_sample_serpent(out_dir, kind))


@mcp.tool()
def make_flier_sample(out_dir: str, feathers: int = 4) -> dict:
    """Procedural front-view bird for rig_flier: tail, wing_l/_r with wing_<side>_feather1..N, body, head, beak, eyes."""
    return _summary(rig_chain.make_sample_flier(out_dir, feathers=feathers))


@mcp.tool()
def make_host_sample(out_dir: str, parts: list[str] | None = None) -> dict:
    """Procedural minimal biped host for attach_rig (bones root > hips > chest > head, legs, arms; clips idle
    2.4 s loop, walk 1.0 s loop, win 1.2 s one-shot) with the layers for the add-ons in `parts`
    (ears, tail, wings, horns, snake_hair, mermaid, fur, glow, digitigrade; default ears, tail, wings)."""
    return _summary(rig_addons.make_sample_host(out_dir, tuple(parts) if parts else ("ears", "tail", "wings")))
