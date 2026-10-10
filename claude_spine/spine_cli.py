"""Thin wrappers around the licensed Spine editor's command-line interface.

Adapted from egorfedorov/spine-mcp (MIT). The editor CLI (activated license
required) imports runtime JSON into an editable .spine project, exports
projects back to runtime data, and renders PNG/GIF frames headlessly.
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

_DEFAULTS = {
    "Darwin": "/Applications/Spine.app/Contents/MacOS/Spine",
    "Windows": r"C:\Program Files\Spine\Spine.com",
    "Linux": "/opt/spine/Spine.sh",
}
SPINE_BIN = os.environ.get("SPINE_BIN", _DEFAULTS.get(platform.system(), "Spine"))
_NOISE = ("Spine Launcher", "Esoteric Software", "Mac OS X", "Starting:", "Licensed to:")


def available() -> bool:
    return Path(SPINE_BIN).exists()


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([SPINE_BIN, *args], capture_output=True, text=True, timeout=timeout)


def _clean(out: str) -> str:
    return "\n".join(l for l in out.splitlines() if not l.startswith(_NOISE)).strip()


def version() -> str:
    out = _run(["--version"]).stdout
    for line in out.splitlines():
        if any(k in line for k in ("Professional", "Essential", "Trial", "Enterprise")):
            return line.replace("Starting:", "").strip()
    return out.strip().splitlines()[-1] if out.strip() else "unknown"


def make_project(runtime_json: str, out_spine: str) -> dict:
    """Import runtime JSON into an editable .spine project, replacing any project already at ``out_spine``. The
    CLI imports INTO an existing project and keeps what is there, adding the skeleton under a new name
    ("Skeleton renamed: hero -> hero2"), so a rebuild left a stale copy in the file; it now imports into a fresh
    file that then replaces the old one. Reports any repairs the importer made (e.g. "Fixed invalid
    triangulation"), which mean the JSON was not what the editor expects."""
    out = Path(out_spine)
    out.parent.mkdir(parents=True, exist_ok=True)
    fresh = out.with_name(out.stem + ".importing.spine")
    fresh.unlink(missing_ok=True)
    r = _run(["-i", runtime_json, "-o", str(fresh), "-r"])
    log = _clean(r.stdout + r.stderr)
    repairs = [l for l in log.splitlines() if any(k in l.lower() for k in ("fixed", "invalid", "warning", "error"))]
    ok = fresh.exists() and r.returncode == 0
    if ok:
        os.replace(fresh, out)
    else:
        fresh.unlink(missing_ok=True)
    return {"ok": ok, "project": out_spine, "repairs": repairs, "log": log}


def export_project(project: str, out_dir: str, fmt: str = "json") -> dict:
    """Export a .spine project: fmt json | binary, or a path to an export settings JSON."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    r = _run(["-i", project, "-o", out_dir, "-e", fmt])
    return {"ok": r.returncode == 0, "out_dir": out_dir, "log": _clean(r.stdout + r.stderr)}


def info(path: str) -> str:
    return _clean(_run(["-i", path]).stdout)
