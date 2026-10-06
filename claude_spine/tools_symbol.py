"""MCP tools that animate a symbol FROM THE ARTIST'S OWN ART: sphere_spin (a real 3D turn of a round symbol),
liquid_splat (a reference-grade splat from their splash layers), shake (violent shake before a burst), and ae_check
(what a saved After Effects project holds). Registered on the server's FastMCP instance when imported."""
from __future__ import annotations

from .server import _open, _saved, mcp
from . import ae_bridge, fx_splat, sphere


@mcp.tool()
def sphere_spin(project: str, slots: list[str], animation: str, start: float = 0.0, duration: float = 1.0,
                turns: int = 1, riders: list[str] | None = None, flip: list[str] | None = None, glow: float = 0.0,
                frames: int = 24, size: int = 640, name: str = "spin", host: str = "") -> dict:
    """Turn a ROUND symbol (ball, bomb, orb) around its vertical axis with real depth.

    A flat scaleX card flip squeezes a ball into a sliver; this wraps the artist's art (the `slots` making the
    round body, e.g. the shell pieces) onto a sphere and renders `frames` images of one turn: the pattern travels
    round the back (its own repeat is found and tiled, no mirror seams), the light stays put (rim shading divided
    out and put back, white glints kept at their screen spots), frames are motion-blurred, frame 0 is the art.
    In `animation` (created or merged, keys outside the window kept): the slots hide and a `<name> body` sequence
    is keyed frame by frame, eased (smootherstep) over `duration` for `turns` whole turns. riders: bones sitting
    on the surface (a cap), one group led by the first, orbit it with the right tilt and foreshortening and pass
    BEHIND the ball (draw order). flip: bones sticking out sideways (a wick) flatten and mirror as they turn.
    glow > 0: an additive twin swells to that alpha mid-turn. Re-running with the same name reuses the frames."""
    p = _open(project)
    return _saved(p, sphere.sphere_spin(p, slots, animation, start, duration, turns, riders, flip, glow, frames,
                                        size, name, host))


@mcp.tool()
def liquid_splat(project: str, slots: list[str], animation: str, at: float, name: str = "splat",
                 center: list[float] | None = None, composite: str = "", drip_slots: list[str] | None = None,
                 drips: int = 16, rays: int = 18, scale: float = 1.0, seed: int = 1, implode_bone: str = "",
                 implode_from: float = 1.0, implode_hide: list[str] | None = None, prefix: str = "",
                 offset: list[float] | None = None, lens: bool = True) -> dict:
    """A liquid splat built from the artist's own splash layers (`slots`: the pieces of a painted splash),
    bursting at `at` in `animation`.

    Beats (after a reference candy-slot burst): implode (implode_bone pinches from implode_from to a point with a
    white star; implode_hide slots vanish at the burst) -> a zoom-blurred smear of the whole splash for 4 frames
    (`composite`: a slot holding the whole splash, else the pieces composited) -> a RING of liquid: each piece on
    its own bone pointing away from the centre flies from the middle out past its painted spot (small pieces
    furthest), stretched along its flight, slapped wide, leaving the centre hollow -> the ring thins into ribbons
    that shrink away together while `drips` tear off and rain down (drip_slots: the artist's droplets, else a
    teardrop tinted in the splash's own colours) -> `rays` thin white rays and a lens streak, then a late glint.
    center: the blast point (default the splash's centre). The kit is built on first use and reused on later calls
    (other animations / times). prefix + offset [dx, dy]: a clone of the kit at another spot (one per bomb).
    ae_hint in the result: the After Effects layers (lens_flare ghosts, shockwave rings, bloom) and how to land
    them on the burst with ae_fx_to_spine."""
    p = _open(project)
    res = fx_splat.liquid_splat(p, slots, animation, at, name, center, composite, drip_slots, drips, rays, scale,
                                seed, implode_bone, implode_from, implode_hide, prefix, tuple(offset or (0, 0)), lens)
    return _saved(p, res)


@mcp.tool()
def shake(project: str, animation: str, bone: str, start: float, end: float, amplitude: float = 20.0,
          rotation: float = 10.0, every: int = 2, grow: bool = True, seed: int = 3) -> dict:
    """A violent shake on a bone (a bomb about to blow): translate + rotate jumps every `every` frames (30 fps),
    growing toward `end` (grow), back at rest on `end`. Merges into the animation (keys outside the window kept).
    Pair: shake until just before the burst, then liquid_splat with implode_bone for the pinch and pop."""
    p = _open(project)
    return _saved(p, fx_splat.shake(p, animation, bone, start, end, amplitude, rotation, every, grow, seed))


@mcp.tool()
def ae_check(aep: str, comps: list[str] | None = None) -> dict:
    """What a SAVED After Effects project holds, read from the file (no AE needed): its item / layer / effect
    names, any `CLAUDE_ERR <template>: <message>` comp a failed template script left, and found={comp: bool} for
    the comps you expect. Run it after the artist runs a template script and saves, before ae_fx_to_spine."""
    return ae_bridge.check_aep(aep, comps)
