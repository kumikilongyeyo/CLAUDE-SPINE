"""MCP tools for the creature rigs: rig_creature and make_creature_sample.
Registered on the server's FastMCP instance when imported (server.py imports this module at its end)."""
from __future__ import annotations

from .server import _open, _saved, mcp
from . import rig_creature as _rc


@mcp.tool()
def rig_creature(project: str = "", kind: str = "", clips: list[str] | None = None, seed: int = 7,
                 exaggerate: float = 1.0, options: dict | None = None) -> dict:
    """Rig a non-humanoid creature from its layers and build its clip set, composing the existing rigs (gait /
    rig_quadruped, rig_serpent chains, rig_flier wings, clip merge by name, fx recipes). kind="" lists every kind with
    its layer convention (case-insensitive, last group/ part of a PSD name counts), clips and options.

    Kinds (clips):
      slime (idle, hop, hit, win): body = one mesh on a core + n_outline (6-8) outline bones with soft physics; squash
            keeps the volume (scaleY 0.7 -> scaleX 1.195; options.law="area" -> 1/scaleY); hop = anticipation squash,
            ballistic parabola (stretch ~ speed), splat recovering on an exact spring; outline wobble in Rayleigh drop
            modes (mode 3 at 1.936 x mode 2). Events sfx_hop, sfx_land, sfx_hit, sfx_win.
      golem (idle, stomp, hit): rigid parts with gaps, each lagging its parent through a critically / over-damped
            filter (zeta >= 1: never overshoots; fists lag two levels); glowing seams (additive glow slot per crack*);
            stomp = slow heavy rise, gravity drop, dust, event screen_shake (float = px, int = ms) + sfx_stomp.
      ghost (idle, swoop, fade_out, fade_in): strand-chain body with physics, no legs; bob and sway from two
            incommensurate periods closed exactly over the loop; alpha breathing; trailing wisp* strands. fade_out ends
            invisible (bones on setup), fade_in starts there.
      tentacle (idle, reach, slam): tentacle<N> layers each a rig_serpent tentacle chain off the core with reach IK
            on the tip; idle phases per tentacle; reach = spring strike + IK grab (sfx_reach, sfx_grab); sucker
            template clones swap to stretched art while the tentacle stretches; slam whips (screen_shake).
      dragon (idle, walk, fly, breath, roar): rig_quadruped body + serpent neck and tail + bat wings (rig_flier
            stroke); breath = generated fire flipbook from the mouth (fx_fire, sfx_breath) with an ae_hint for the AE
            fire template; roar with screen_shake.
      insect (idle, walk, fly): leg_{L|R}{1|2|3}_{upper|lower}, tripod (or wave) gait with sfx_step per foot,
            antenna strands, wing-blur flipbook in fly.
      plant (idle, grow, attack): trunk chain, branch* strands, root* IK feet, leaf* physics fans; grow is
            diffusion-limited (front s = sqrt(2 k t)), leaves pop on a spring; attack whips a branch (screen_shake).
      mimic (idle, open, bite, land, win): spring hinge lid (exact overshoot), gravity close with restitution
            bounces, tongue strand, teeth; open fires the FX shine; land / win through the juice_apply contract.

    Loops close exactly, one-shots end on the setup pose; the artist's setup never moves. The result reports the
    bones / slots / constraints and qa.budget(mobile_character)."""
    if not kind:
        return {"kinds": _rc.list_kinds()}
    if not project:
        raise ValueError("project is required to rig a creature")
    p = _open(project)
    return _saved(p, _rc.rig_creature(p, kind, clips, seed, exaggerate, options))


@mcp.tool()
def make_creature_sample(out_dir: str, kind: str) -> dict:
    """Procedural sample for rig_creature (slime | golem | ghost | tentacle | dragon | insect | plant | mimic): simple
    readable parts drawn with PIL, one image per layer, named exactly as import_psd names a PSD that follows the
    kind's convention. Not rigged: run rig_creature on it."""
    p = _rc.make_sample_creature(out_dir, kind)
    sk = p.data
    return {"project": str(p.path), "kind": kind, "slots": [s.name for s in sk.slots], "bones": len(sk.bones)}
