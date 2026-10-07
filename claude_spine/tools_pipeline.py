"""High-impact production pipeline tools registered on the MCP server."""
from __future__ import annotations
from .server import mcp, _open, _saved
from . import ae_material, project_clean, secondary_motion

@mcp.tool()
def clean_project(project: str, mode: str = "editable", max_influences: int = 4,
                  dedupe_keys: bool = True, remove_empty_animations: bool = True) -> dict:
    """Sanitize a generated Spine project without rebuilding a working rig."""
    p = _open(project)
    return _saved(p, project_clean.clean(
        p, mode, max_influences, dedupe_keys, remove_empty_animations))

@mcp.tool()
def secondary_motion_solver(project: str, animation: str, chain: list[str],
                            timelines: list[str] | None = None, step_delay: float = 0.035,
                            gain_decay: float = 0.82, settle: float = 0.08,
                            ease: str = "sine_out", replace_followers: bool = True) -> dict:
    """Create sparse causal response such as torso -> jacket -> hair -> accessory."""
    p = _open(project)
    return _saved(p, secondary_motion.solve(
        p, animation, chain, timelines, step_delay, gain_decay, settle, ease, replace_followers))

@mcp.tool()
def ae_material_fx(project: str = "", name: str = "", material: str = "impact",
                   passes: list[dict] | None = None, fps: float = 0.0,
                   animation: str = "", start: float = 0.0, x: float = 0.0, y: float = 0.0,
                   scale: float = 1.0, parent: str = "root",
                   subject_slots: list[str] | None = None, max_size: int = 0,
                   max_frames: int = 0, realism: float = 0.75) -> dict:
    """Plan or import layered material FX from AE into Spine."""
    if not project or not passes:
        return ae_material.material_plan(material, realism)
    p = _open(project)
    res = ae_material.import_package(
        p, name or material, passes, fps, animation, start, x, y, scale, parent,
        subject_slots, max_size, max_frames)
    res["material_plan"] = ae_material.material_plan(material, realism)
    return _saved(p, res)
