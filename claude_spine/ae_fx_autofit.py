"""Guarded local After Effects execute/render/compare loop.

Runs on the machine where After Effects is installed: macOS through AppleScript (``DoScript``), Windows through
``AfterFX.exe -r``. Every round builds its comp in a NEW project: the artist's open project is left alone when it
is saved and clean (it is reopened afterwards) and refused when it has unsaved changes. Completion is confirmed by
a file the script writes after saving, never by the launcher's exit code. One script at a time across agents:
rounds take the same ``mkdir`` lock as the ``ae_lock.sh`` helpers (``AE_LOCK_DIR``).

With ``template="auto"`` the first step AUDITIONS the best-ranked stored templates for the recipe on a real render
each and keeps the one that scores best, then tunes it round by round.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from . import ae_bridge, ae_fx_memory, ae_fx_template_fit, ae_fx_visual_match


def _wrapper(jsx: Path, aep: Path, ack: Path, previous: Path | None = None) -> str:
    # A separate JSX wrapper ensures that a script is confirmed complete only after After Effects has actually
    # saved the intended project. ``previous`` is accepted for compatibility; every round starts a new project.
    text = """(function () {
    var f = new File(__ACK__);
    function signal(ok, detail) {
        f.encoding = "UTF-8";
        if (!f.open("w")) throw new Error("Cannot create AE acknowledgment file");
        f.writeln(ok ? "OK" : "ERROR");
        f.writeln(detail);
        f.close();
    }
    var p = app.project, orig = p ? p.file : null;
    try {
        if (p && p.dirty && (p.file || p.numItems !== 0))
            throw new Error("AE has unsaved changes: save or close them, or open a new, empty, unsaved AE project before auto-fit.");
        if (p && (p.file || p.numItems !== 0)) app.newProject();
        $.evalFile(new File(__SCRIPT__));
        app.project.save(new File(__PROJECT__));
        signal(true, "Saved");
    } catch (e) {
        signal(false, (e.message ? e.message : "Unknown ExtendScript error") +
               (e.line ? " at line " + e.line : ""));
    }
    try { if (orig && orig.exists) app.open(orig); } catch (ignore) {}
})();"""
    for key, value in {
        "__ACK__": json.dumps(str(ack)),
        "__SCRIPT__": json.dumps(str(jsx)),
        "__PROJECT__": json.dumps(str(aep)),
    }.items():
        text = text.replace(key, value)
    return text


def _mac_app(path: str = "") -> str:
    """The AE application bundle name AppleScript talks to ("Adobe After Effects 2026")."""
    name = path or os.environ.get("AE_APP_NAME", "")
    if name:
        return Path(name).stem if name.endswith(".app") else name
    # the app is named like its folder; the same folder also holds "Adobe After Effects Render Engine <ver>.app",
    # which has no DoScript (AppleScript then fails with a bare syntax error)
    found = sorted(d.name for d in Path("/Applications").glob("Adobe After Effects *")
                   if (d / f"{d.name}.app").is_dir())
    if not found:
        raise RuntimeError("After Effects not found in /Applications; set AE_APP_NAME")
    return found[-1]


def _resolve_afterfx(path: str = "") -> Path | str:
    if sys.platform == "darwin":
        return _mac_app(path)
    name = (path or os.environ.get("AFTERFX_BIN") or
            shutil.which("AfterFX.exe") or shutil.which("AfterFX.com") or
            shutil.which("afterfx") or "")
    if not name or not Path(name).expanduser().is_file():
        raise RuntimeError("Pass afterfx_bin=<full path to AfterFX.exe>, or set AFTERFX_BIN")
    return Path(name).expanduser().resolve()


@contextmanager
def _ae_lock(who: str, wait: float = 600, stale: float = 180):
    """The ae_lock.sh protocol: mkdir is atomic; an owner file older than ``stale`` seconds is taken over."""
    lock = Path(os.environ.get("AE_LOCK_DIR", Path.home() / ".claude-spine" / "ae_lock")).expanduser()
    lock.parent.mkdir(parents=True, exist_ok=True)
    until = time.monotonic() + wait
    while True:
        try:
            lock.mkdir()
            (lock / "owner").write_text(f"{who} {int(time.time())}")
            break
        except FileExistsError:
            try:
                since = int((lock / "owner").read_text().split()[1])
                if time.time() - since > stale:
                    shutil.rmtree(lock, ignore_errors=True)
                    continue
            except (OSError, IndexError, ValueError):
                pass
            if time.monotonic() > until:
                raise TimeoutError(f"After Effects is busy (lock {lock} held)")
            time.sleep(.5)
    try:
        yield
    finally:
        shutil.rmtree(lock, ignore_errors=True)


def _launch(binary: Path | str, wrapper: Path, timeout_seconds: float) -> subprocess.Popen:
    if sys.platform == "darwin":
        code = f'$.evalFile(new File({json.dumps(str(wrapper))}));'
        script = (f'with timeout of {int(timeout_seconds) + 30} seconds\n'
                  f'tell application {json.dumps(str(binary))} to DoScript {json.dumps(code)}\n'
                  f'end timeout')
        return subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # The documented -r command sends a script to an existing AE session and may return before the script
    # finishes. Only the AE-created file is proof.
    return subprocess.Popen([str(binary), "-r", str(wrapper)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _execute(jsx: str, aep: Path, ack: Path, previous: Path | None,
             binary: Path | str, timeout_seconds: float) -> None:
    ack.unlink(missing_ok=True)
    wrapper = ack.with_suffix(".jsx")
    wrapper.write_text(_wrapper(Path(jsx).resolve(), aep.resolve(), ack.resolve()), encoding="utf-8")
    with _ae_lock(f"ae_fx_autofit:{os.getpid()}"):
        proc = _launch(binary, wrapper, timeout_seconds)
        until = time.monotonic() + timeout_seconds
        while time.monotonic() < until:
            if ack.exists():
                try:
                    status = ack.read_text(encoding="utf-8").splitlines()
                    if not status:
                        raise ValueError("empty AE acknowledgement")
                except (OSError, ValueError):
                    time.sleep(.3)
                    continue
                if status[0].lstrip("﻿").strip() != "OK":
                    raise RuntimeError("AE refused the script: " + " ".join(status[1:]))
                if not aep.is_file():
                    raise RuntimeError("AE signaled success without saving its project")
                if proc.poll() is None:   # osascript returns once AE has also reopened the artist's project
                    try:
                        proc.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        pass
                return
            if proc.poll() is not None and proc.returncode != 0:
                err = proc.stderr.read().decode(errors="replace")[-400:] if proc.stderr else ""
                raise RuntimeError("After Effects did not run the script: " + (err or f"exit {proc.returncode}"))
            time.sleep(.3)
    raise TimeoutError("AE did not acknowledge completion; inspect the wrapper JSX and open AE")


def _round(recipe: str, dest: Path, tag: str, built: dict, binary, timeout_seconds: float, iteration: int,
           tuning, kw: dict) -> dict:
    aep = dest / f"{tag}.aep"
    ack = dest / f"{tag}_ack.txt"
    _execute(built["jsx"], aep, ack, None, binary, timeout_seconds)
    render = ae_bridge.render_comp(str(aep), built["comp"], dest / f"{tag}_frames")
    match = ae_fx_visual_match.compare(
        recipe, str(dest / tag.rsplit("_r", 1)[0]), candidate_frames=str(dest / f"{tag}_frames"),
        candidate_fps=render.fps, iteration=iteration, tuning=tuning, **kw)
    return {"aep": aep, "match": match,
            "record": {"iteration": iteration, "project": str(aep), "comp": built["comp"],
                       "template": kw.get("template"), "score": match["score"],
                       "comparison": match["comparison"], "match_report": match["report"]}}


def auto_fit(recipe: str, out_dir: str, afterfx_bin: str = "",
             max_rounds: int = 3, timeout_seconds: float = 180.,
             style: str = "premium", canvas: int = 1024, reference: str = "",
             background: str = "", min_improvement: float = .15,
             max_frames: int = 40, template: str = "auto", audition: int = 3,
             template_params: dict | None = None) -> dict:
    """Build, run inside AE, render, compare, and repeat with feedback.

    ``template`` = a stored AE template, "auto" (audition the ``audition`` best-ranked ones on a real render and
    keep the best) or "shapes" (the plain core / halo / ring / spark rebuild). Needs After Effects + aerender on
    this machine. The artist's open project must be saved (it is reopened after each round) or empty.
    """
    if not 1 <= max_rounds <= 5:
        raise ValueError("max_rounds must be 1..5")
    if not 5 <= timeout_seconds <= 1800:
        raise ValueError("timeout_seconds must be 5..1800")
    if not 0 <= min_improvement <= 15:
        raise ValueError("min_improvement must be 0..15")
    if not 1 <= audition <= 6:
        raise ValueError("audition must be 1..6")
    binary = _resolve_afterfx(afterfx_bin)
    ae_bridge.find_aerender()  # Fail before touching AE when rendering is unavailable.
    dest = Path(out_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    obj = json.loads(Path(recipe).expanduser().read_text(encoding="utf-8"))
    base = {"reference": reference, "background": background, "max_frames": max_frames, "style": style,
            "canvas": canvas, "strength": 1., "speed": 1., "template_params": template_params}
    if template == "auto":
        names = [r["template"] for r in ae_fx_template_fit.rank(obj, audition)]
    else:
        names = [template]
    history, auditions = [], []
    best = None
    # audition: every candidate gets its probe (neutral fit) AND one fitted round before they are compared; an
    # unfitted probe says more about the template's default size than about its look
    for name in names:
        built = ae_fx_memory.remix(recipe, str(dest), style=style, canvas=canvas, strength=1., speed=1.,
                                   comp_name=f"{obj['id']}_{name}_r001", template=name,
                                   template_params=template_params)
        probe = _round(recipe, dest, f"{name}_r001", built, binary, timeout_seconds, 1, None,
                       {**base, "template": name})
        history.append(probe["record"])
        done = probe
        if len(names) > 1 and max_rounds > 1 and not probe["match"]["stop"]:
            nxt = {"jsx": probe["match"]["next_jsx"], "comp": probe["match"]["next_comp"]}
            done = _round(recipe, dest, f"{name}_r002", nxt, binary, timeout_seconds, 2, probe["match"]["tuning"],
                          {**base, "template": name})
            history.append(done["record"])
            if probe["record"]["score"] > done["record"]["score"]:
                done = {**probe, "match": {**done["match"], "stop": True}}
        auditions.append(done)
    lead = max(auditions, key=lambda d: d["record"]["score"])
    current, tuning = lead["match"], None
    winner = lead["record"]["template"]
    best = lead["record"]
    last_score = best["score"]
    start = lead["record"]["iteration"] + 1
    for iteration in range(start, max_rounds + 1):
        if current["stop"]:
            break
        tuning = current["tuning"]
        built = {"jsx": current["next_jsx"], "comp": current["next_comp"]}
        done = _round(recipe, dest, f"{winner}_r{iteration:03d}", built, binary, timeout_seconds, iteration,
                      tuning, {**base, "template": winner})
        history.append(done["record"])
        current = done["match"]
        if done["record"]["score"] > best["score"]:
            best = done["record"]
        if done["record"]["score"] - last_score < min_improvement:
            break
        last_score = done["record"]["score"]
    report = {"rounds": best["iteration"], "renders": len(history), "template": winner,
              "auditioned": [{"template": d["record"]["template"], "score": d["record"]["score"]} for d in auditions],
              "history": history, "best": best,
              "stopped_early": sum(h["template"] == winner for h in history) < max_rounds,
              "note": "Scores represent actual AE renders, not predicted improvements. Artist approval is still required.",
              "next": "Review best.project and best.comp, then use ae_vfx_to_spine."}
    path = dest / "autofit_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report"] = str(path)
    return report
