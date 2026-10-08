"""MCP tools for the After Effects FX library (`ae_fx_library`): list / build in AE, fetch the CC0 textures, hand an
effect to Spine. Registered on the server's FastMCP instance when imported."""
from __future__ import annotations

from .server import mcp
from . import ae_fx_library as L


@mcp.tool()
def ae_library(names: list[str] | None = None, look: str = "", kind: str = "", out_dir: str = "",
               textures_dir: str = "", rebuild: bool = False, save_as: str = "") -> dict:
    """After Effects FX library: 50 finished procedural effects (After Effects builders, ready for Spine).

    No `names`: lists them (filter with look = cel | realistic, kind = hero | clip | glow | element). Cel look: flat
    toon effects (target ring, sun rune burst, electric star / ring loop, fire rose burst, water impact and dome
    splash, whirlpool transition, pink radial loop, smoke puffs, side fireball, pot burst, rainbow burst, coin glow,
    reel fire column + confetti, free-spins flash + sunburst loop). Realistic look (`re_<name>`): the same effects
    made of CC0 photo / Kenney textures, driven by the cel comp's motion. Plus gl_* glows (gold win aura, energy
    orb, symbol rim sweep, hit flash, green magic pulse, god-ray reveal) and el_* elements (fire burst, fire loop,
    water splash, ice shatter, lightning strike, earth rock burst, wind swirl, poison bubbles).
    With `names` and `out_dir`: writes one ExtendScript that builds them (and what they need, e.g. a realistic
    effect needs its cel comp) in the OPEN project, keeping comps that already exist unless rebuild=True, and saves
    (save_as=<.aep> to save as). Realistic / gl_ / el_ entries need `textures_dir` from ae_library_textures.
    Run the returned `run_with` with the After Effects MCP's ae_run_script, then ae_library_to_spine."""
    if not names:
        rows = L.listing(look, kind)
        return {"count": len(rows), "effects": rows,
                "next": "ae_library(names=[...], out_dir=..., textures_dir=...) writes the build script"}
    if not out_dir:
        raise ValueError("out_dir is needed to write the script")
    return L.write_script(names, out_dir, textures_dir, rebuild, save_as)


@mcp.tool()
def ae_library_textures(dest: str, download: bool = True) -> dict:
    """Make the texture folder the realistic library effects use (once per machine): downloads Kenney's Particle
    Pack and Smoke Particles (CC0, ~21 MB, kenney.nl), copies the library's 21 CC0 / public-domain photos, writes
    `ready/` (photos on black unmultiplied to RGBA exactly as the builders were tuned) and CREDITS. Pass the folder
    as ae_library(textures_dir=...)."""
    return L.fetch_textures(dest, download)


@mcp.tool()
def ae_library_to_spine(name: str, out_dir: str, aep: str = "", frames_dir: str = "", max_size: int = 0,
                        max_frames: int = 0, spine_project: bool = True) -> dict:
    """Library effect -> its own Spine skeleton `fx_<name>` (one animation `<name>` on bone `fx` at the origin):
    renders the comp from the SAVED aep with aerender (or reads frames_dir), imports it at the entry's budget
    (soft full-screen effects at half size and scaled back up, slow loops subsampled; override with max_size /
    max_frames), packs <out_dir>/<name>/export/ and, with the Spine CLI, makes <out_dir>/<name>/fx_<name>.spine.
    Returns texture size, frames, atlas pages and GPU MB."""
    return L.to_spine(name, out_dir, aep, frames_dir, max_size, max_frames, spine_project)
