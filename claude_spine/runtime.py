"""Bridge to the official spine-core runtime (Node) in ``validator/``.

``load_check`` proves a skeleton loads and every animation applies without
non-finite vertices; ``pose_dump`` returns posed triangles for previews.
The runtime is installed on first use with ``npm install`` (one small package,
pinned in validator/package.json).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import atlas as atlas_mod
from .project import Project


def validator_dir() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "validator", here / "_validator"):
        if (cand / "pose.mjs").exists():
            return cand
    raise FileNotFoundError("validator/pose.mjs not found next to the package")


def node_bin() -> str | None:
    return os.environ.get("NODE_BIN") or shutil.which("node")


def ensure_runtime() -> Path:
    vd = validator_dir()
    if (vd / "node_modules" / "@esotericsoftware" / "spine-core").exists():
        return vd
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("Node/npm not found; install Node 18+ to run runtime validation and previews")
    subprocess.run([npm, "install", "--silent", "--no-audit", "--no-fund"], cwd=vd, check=True,
                   capture_output=True, text=True, timeout=300)
    return vd


def available() -> bool:
    return node_bin() is not None


def _atlas_for(project: Project, atlas_path: str | None, work: Path) -> str:
    if atlas_path:
        return atlas_path
    res = atlas_mod.pack(project, out_dir=work, name=project.name, pma=False)
    return res["atlas"]


def run(project: Project, atlas_path: str | None = None, animations: list[str] | None = None,
        fps: float = 30, frames: int = 0, geometry: bool = False, timeout: int = 180) -> dict:
    node = node_bin()
    if not node:
        raise RuntimeError("node not found on PATH (set NODE_BIN)")
    vd = ensure_runtime()
    with tempfile.TemporaryDirectory(prefix="claude-spine-") as td:
        work = Path(td)
        a = _atlas_for(project, atlas_path, work)
        js = work / f"{project.name}.json"
        project.data.save(js, indent=None)
        out = work / "dump.json"
        cmd = [node, str(vd / "pose.mjs"), str(js), a, "--fps", str(fps), "--out", str(out)]
        if animations:
            cmd += ["--anim", ",".join(animations)]
        if frames:
            cmd += ["--frames", str(frames)]
        if geometry:
            cmd.append("--geometry")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if not out.exists():
            return {"ok": False, "stage": "node", "error": (r.stderr or r.stdout)[-2000:]}
        res = json.loads(out.read_text())
        res["_atlas"] = a
        if geometry:
            res["_page_files"] = {p: str(Path(a).parent / p) for p in res.get("pages", {})}
            res["_pma"] = "pma: true" in Path(a).read_text()
            # keep the page images alive past the temp dir
            keep = Path(tempfile.mkdtemp(prefix="claude-spine-pages-"))
            for p, f in list(res["_page_files"].items()):
                dst = keep / p
                shutil.copy(f, dst)
                res["_page_files"][p] = str(dst)
        return res


def load_check(project: Project, atlas_path: str | None = None) -> dict:
    res = run(project, atlas_path, fps=30, geometry=False)
    res.pop("_atlas", None)
    return res
