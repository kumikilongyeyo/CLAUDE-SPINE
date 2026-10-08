"""Optional guarded local After Effects execute/render/compare loop.

Run only on the workstation where After Effects is installed. Refuses to
modify unrelated open projects. Uses an explicit script acknowledgment, not
the afterfx launch process exit code, to confirm saved AE output.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import ae_bridge, ae_fx_memory, ae_fx_visual_match


def _wrapper(jsx: Path, aep: Path, ack: Path, previous: Path | None = None) -> str:
    # A separate JSX wrapper ensures that a script is confirmed complete only
    # after After Effects has actually saved the intended project.
    text = """(function () {
    var f = new File(__ACK__);
    function signal(ok, detail) {
        f.encoding = "UTF-8";
        if (!f.open("w")) throw new Error("Cannot create AE acknowledgment file");
        f.writeln(ok ? "OK" : "ERROR");
        f.writeln(detail);
        f.close();
    }
    try {
        var previous = __PREVIOUS__, p = app.project;
        if (previous) {
            if (!p.file || p.file.fsName !== new File(previous).fsName)
                throw new Error("Open the previous generated AEP; unrelated projects are protected.");
        } else if (p.numItems !== 0 || p.file) {
            throw new Error("Open a new, empty, unsaved AE project before auto-fit.");
        }
        $.evalFile(new File(__SCRIPT__));
        app.project.save(new File(__PROJECT__));
        signal(true, "Saved");
    } catch (e) {
        signal(false, (e.message ? e.message : "Unknown ExtendScript error") +
               (e.line ? " at line " + e.line : ""));
    }
})();"""
    for key, value in {
        "__ACK__": json.dumps(str(ack)),
        "__PREVIOUS__": json.dumps(str(previous)) if previous else "null",
        "__SCRIPT__": json.dumps(str(jsx)),
        "__PROJECT__": json.dumps(str(aep)),
    }.items():
        text = text.replace(key, value)
    return text


def _resolve_afterfx(path: str = "") -> Path:
    name = (path or os.environ.get("AFTERFX_BIN") or
            shutil.which("AfterFX.exe") or shutil.which("AfterFX.com") or
            shutil.which("afterfx") or "")
    if not name or not Path(name).expanduser().is_file():
        raise RuntimeError("Pass afterfx_bin=<full path to AfterFX.exe>, or set AFTERFX_BIN")
    return Path(name).expanduser().resolve()


def _execute(jsx: str, aep: Path, ack: Path, previous: Path | None,
             binary: Path, timeout_seconds: float) -> None:
    ack.unlink(missing_ok=True)
    wrapper = ack.with_suffix(".jsx")
    wrapper.write_text(_wrapper(Path(jsx).resolve(), aep.resolve(), ack.resolve(),
                                previous.resolve() if previous else None), encoding="utf-8")
    # The documented -r command sends a script to an existing AE session and
    # may return before the script finishes. Only the AE-created file is proof.
    proc = subprocess.Popen([str(binary), "-r", str(wrapper)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            if status[0].lstrip("\ufeff").strip() != "OK":
                raise RuntimeError("AE refused the script: " + " ".join(status[1:]))
            if not aep.is_file():
                raise RuntimeError("AE signaled success without saving its project")
            return
        if proc.poll() is not None and proc.returncode != 0:
            raise RuntimeError("AfterFX failed to start the JSX runner")
        time.sleep(.3)
    raise TimeoutError("AE did not acknowledge completion; inspect the wrapper JSX and open AE")


def auto_fit(recipe: str, out_dir: str, afterfx_bin: str = "",
             max_rounds: int = 3, timeout_seconds: float = 180.,
             style: str = "premium", canvas: int = 1024, reference: str = "",
             background: str = "", min_improvement: float = .15,
             max_frames: int = 40) -> dict:
    """Generate JSX, run inside AE, render, compare, and repeat with feedback.

    Requires local AfterFX executable plus the existing aerender executable.
    First iteration requires an empty, UNSAVED project open in AE. Subsequent
    iterations require the previous generated AEP to be open. Never discards or
    opens over unrelated projects. The generated comps remain fully editable.
    """
    if not 1 <= max_rounds <= 5:
        raise ValueError("max_rounds must be 1..5")
    if not 5 <= timeout_seconds <= 1800:
        raise ValueError("timeout_seconds must be 5..1800")
    if not 0 <= min_improvement <= 15:
        raise ValueError("min_improvement must be 0..15")
    binary = _resolve_afterfx(afterfx_bin)
    ae_bridge.find_aerender()  # Fail before modifying an AE project when rendering is unavailable.
    dest = Path(out_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    current = ae_fx_memory.remix(recipe, str(dest), style=style, canvas=canvas,
                                 strength=1., speed=1., comp_name="reference_autofit_001")
    previous = None
    tuning = None
    history = []
    best = None
    for iteration in range(1, max_rounds+1):
        aep = dest / f"autofit_{iteration:03d}.aep"
        ack = dest / f"autofit_{iteration:03d}.json"
        _execute(current["jsx"], aep, ack, previous, binary, timeout_seconds)
        previous = aep
        folder = dest / f"autofit_{iteration:03d}_frames"
        render = ae_bridge.render_comp(str(aep), current["comp"], folder)
        match = ae_fx_visual_match.compare(
            recipe, str(dest), candidate_frames=str(folder),
            candidate_fps=render.fps, reference=reference,
            background=background, max_frames=max_frames, iteration=iteration,
            style=style, canvas=canvas, strength=1., speed=1., tuning=tuning)
        record = {"iteration": iteration, "project": str(aep),
                  "comp": current["comp"], "score": match["score"],
                  "comparison": match["comparison"], "match_report": match["report"]}
        history.append(record)
        if best is None or record["score"] > best["score"]:
            best = record
        if match["stop"] or (len(history) > 1 and
           record["score"]-history[-2]["score"] < min_improvement):
            break
        current = {"jsx": match["next_jsx"], "comp": match["next_comp"]}
        tuning = match["tuning"]
    report = {"rounds": len(history), "history": history, "best": best,
              "stopped_early": len(history) < max_rounds,
              "note": "Scores represent actual AE renders, not predicted improvements. Artist approval is still required.",
              "next": "Review best.project and best.comp, then use ae_vfx_to_spine."}
    path = dest / "autofit_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report"] = str(path)
    return report
