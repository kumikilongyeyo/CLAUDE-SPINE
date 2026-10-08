"""MCP tools for an extruded spinning coin: rig_coin (a flat coin face -> a real disc with a reeded side wall) and
coin_spin (loop / flip / spin_up / slow_down / land keyed on it). Registered on the server's FastMCP instance when
imported."""
from __future__ import annotations

from .server import _open, _saved, mcp
from . import coin as coin_mod


@mcp.tool()
def rig_coin(project: str, face: str = "", image: str = "", name: str = "coin", depth: str | float = "medium",
             radius: float = 0, ridges: int = 26, rim_color: str = "", parent: str = "root", x: float = 0,
             y: float = 0, back: str = "") -> dict:
    """Turn a FLAT coin face into a real extruded disc that can spin with depth.

    A scaleX card flip reads as a sticker; here the near face rides bone <name>_f (x = +T/2 sin, scaleX = cos), the
    far face rides <name>_eb (x = -T/2 sin, scaleX = cos) and the side wall is ONE weighted cylinder mesh (front ring
    -> <name>_f, back ring -> <name>_eb) with a procedural reeded rim texture: exact silhouette, nothing keyed per
    vertex. face = a slot showing the face art (e.g. from import_psd; it is hidden and the coin takes its place in the
    draw order, at its position) OR image = a PNG of it (copied into the project, 1 px = 1 unit, coin at x, y).
    The disc centre and radius are measured from the art's alpha (a circle fitted to the outline, so a drop shadow
    under the coin does not move it); radius > 0 overrides the radius in art pixels. depth: thin | medium | thick =
    thickness 0.065 / 0.13 / 0.26 of the diameter (medium is the approved coin), or a number (< 1 = fraction of the
    diameter, else units). ridges = reeding count; rim_color = the rim metal (RRGGBB; default sampled from the face's
    outer ring). back = other art for the back face (slot or PNG; default the same face, un-mirrored). x, y shift the
    coin in the parent's space. Builds bones <name>, <name>_f, <name>_eb and slots <name>_edge, <name>_back,
    <name>_front (that draw order), setup pose face-on. Then key it with coin_spin; FX ride it with prop=<name> or
    parent=<name>_f (things ON the face that narrow with the spin)."""
    p = _open(project)
    return _saved(p, coin_mod.rig_coin(p, face, image, name, depth, radius, ridges, rim_color, parent, x, y, back))


@mcp.tool()
def coin_spin(project: str, coin: str = "coin", animation: str = "spin", mode: str = "loop", turns: float = 1,
              duration: float = 2.0, start: float = 0.0, axis: str = "y", bob: float = 0, tilt: float = 0,
              ease: str = "auto", stop: str = "face", replace: bool = False) -> dict:
    """Spin a coin made by rig_coin, inside `animation` (created, or merged: keys outside [start, end] are kept
    unless replace=True).

    mode: loop (constant speed, whole turns per loop, seamless: last frame = first; bob / tilt are periodic) |
    flip (eased in-out, bob = hop height, lands on `end`) | spin_up (accelerating anticipation spin, then a hard
    brake to a stop) | slow_down (decelerates to a stop, e.g. freezing) | land (falls in from bob units above, or
    4 radii, tumbling and slowing to face-on at the landing on `end`, then a 0.7 s landing squash + small bounce on
    the coin bone, base planted). Every angle curve is normalised to EXACTLY turns x 360 (+180 when stop asks for
    the other side), so it stops face-on: stop = face (front showing) | back | any (exactly turns, may end
    edge-on). axis: y = turn round the vertical axis (scaleX = cos), x = flip over the horizontal axis
    (scaleY = cos). tilt = degrees of wobble (loop: periodic; land: leans in and straightens). ease = auto (the
    mode's own profile) or a timeline easing name (in_out, expo_out, back_out, ...) for the angle curve.
    The visible face swaps EXACTLY at the cos = 0 crossings (face_swaps in the result), faces and wall are shaded
    by slot colour (60 Hz keys + the exact crossing and face-on times). Events: flip sfx_flip (+ sfx_land with a
    hop), spin_up / slow_down sfx_spin + sfx_stop, land sfx_land."""
    p = _open(project)
    return _saved(p, coin_mod.coin_spin(p, coin, animation, mode, turns, duration, start, axis, bob, tilt, ease,
                                        stop, replace))
