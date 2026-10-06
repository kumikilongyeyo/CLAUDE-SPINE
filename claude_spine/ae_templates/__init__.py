"""After Effects FX templates: ExtendScript that builds one ready-to-render comp in the open AE project.

Each ``<name>.jsx`` starts with ``/*TEMPLATE {...} */`` giving its description and default parameters. A
template is parameterised, not a fixed comp: ``build_script`` merges your parameters over the defaults, writes
one self-contained script (parameters + ``_lib.jsx`` + the template) and returns its path. Run that script in
After Effects (the ``ae_run_script`` tool, or File > Scripts > Run Script File); it creates the comp inside an
``ae_fx_templates`` folder of the open project and returns a JSON line naming the comp, size, fps and frame
count. Save the project and hand the comp to ``ae_fx_to_spine``.

Running it from a shell: ``AfterFX.exe -r script.jsx`` hands the script to an AE that is already open, and on
some machines that hand-off silently never runs it (``-m`` does not start a second instance either), so ask the
artist to run it from File > Scripts. A failing template first leaves a comp named
``CLAUDE_ERR <template>: <message>`` and still saves (save_as), then re-raises; ``ae_bridge.check_aep`` reads the
error back from the saved .aep together with the comps that were made.

Every template renders on a transparent background (``mode="alpha"``) unless its doc says otherwise.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_HEADER = re.compile(r"/\*TEMPLATE\s*(\{.*?\})\s*\*/", re.S)

# @P@ parameters, @LIB@ _lib.jsx, @USES@ inlined helper templates, @BODY@ the template, @NAME@ its name,
# @SAVE@ the optional save + restore
_WRAP = """var P = @P@;
@LIB@
@USES@var __orig = app.project.file, __dirty = app.project.dirty, __err = null;
var __r = (function () {
  try {
    return (function () {
@BODY@
    })();
  } catch (__e) {
    __err = __e;
    var __m = String(__e) + ' @' + __e.line;
    try { app.project.items.addComp(('CLAUDE_ERR @NAME@: ' + __m).substr(0, 250), 4, 4, 1, 1, 1); } catch (__x) {}
    return '{"error":"' + __m.replace(/["\\\\]/g, "'") + '"}';
  }
})();
@SAVE@if (__err) throw __err;
__r;
"""


def _meta(path: Path) -> dict:
    m = _HEADER.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name} has no /*TEMPLATE {{...}} */ header")
    return json.loads(m.group(1))


def list_templates() -> dict[str, dict]:
    return {p.stem: _meta(p) for p in sorted(HERE.glob("*.jsx")) if not p.stem.startswith("_")}


def build_script(name: str, params: dict | None = None, out_dir: str | Path | None = None) -> dict:
    """Write the runnable script for ``name`` and return ``{script, comp_hint, params, run_with}``."""
    templates = list_templates()
    if name not in templates:
        raise ValueError(f"unknown template {name!r}; one of {sorted(templates)}")
    meta = templates[name]
    given = dict(params or {})
    unknown = sorted(set(given) - set(meta["params"]) - {"comp", "save_as"})
    if unknown:
        raise ValueError(f"template {name!r} has no parameter(s) {unknown}; it takes {sorted(meta['params'])}")
    merged = {**meta["params"], **given}
    body = (HERE / f"{name}.jsx").read_text(encoding="utf-8")
    # "uses": other templates this one builds on, inlined as AEFX.T_<name>(P) (returns that template's JSON line)
    # with their defaults as AEFX.D_<name>, so a composite template reuses them instead of copying their code
    uses = "".join(f"AEFX.D_{u} = {json.dumps(templates[u]['params'])};\n"
                   f"AEFX.T_{u} = function (P) {{\n{(HERE / f'{u}.jsx').read_text(encoding='utf-8')}\n}};\n"
                   for u in meta.get("uses", []))
    save = ""
    if merged.get("save_as"):
        # save to the .aep aerender reads; if the artist's own project was saved and clean before, reopen it so
        # they end up exactly where they were (with unsaved edits they stay in the copy: nothing is lost)
        save = ("app.project.save(new File(" + json.dumps(str(Path(merged["save_as"]).expanduser())) + "));\n"
                "if (__orig && __dirty === false) app.open(__orig);\n")
    src = (_WRAP.replace("@P@", json.dumps(merged)).replace("@LIB@", (HERE / "_lib.jsx").read_text(encoding="utf-8"))
           .replace("@USES@", uses).replace("@NAME@", name).replace("@SAVE@", save).replace("@BODY@", body))
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="ae_tpl_"))
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.jsx"
    path.write_text(src, encoding="utf-8")
    return {"template": name, "script": str(path), "params": merged,
            "run_with": f'return String($.evalFile(new File({json.dumps(str(path))})));'}
