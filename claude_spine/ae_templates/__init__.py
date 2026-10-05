"""After Effects FX templates: ExtendScript that builds one ready-to-render comp in the open AE project.

Each ``<name>.jsx`` starts with ``/*TEMPLATE {...} */`` giving its description and default parameters. A
template is parameterised, not a fixed comp: ``build_script`` merges your parameters over the defaults, writes
one self-contained script (parameters + ``_lib.jsx`` + the template) and returns its path. Run that script in
After Effects (the ``ae_run_script`` tool, or File > Scripts > Run Script File); it creates the comp inside an
``ae_fx_templates`` folder of the open project and returns a JSON line naming the comp, size, fps and frame
count. Save the project and hand the comp to ``ae_fx_to_spine``.

Every template renders on a transparent background (``mode="alpha"``) unless its doc says otherwise.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_HEADER = re.compile(r"/\*TEMPLATE\s*(\{.*?\})\s*\*/", re.S)


def _meta(path: Path) -> dict:
    m = _HEADER.search(path.read_text())
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
    body = (HERE / f"{name}.jsx").read_text()
    save = ""
    if merged.get("save_as"):
        save = f"\napp.project.save(new File({json.dumps(str(Path(merged['save_as']).expanduser()))}));"
    # the template ends in `return <json string>`, so wrap it in a function and save after it ran
    src = (f"var P = {json.dumps(merged)};\n{(HERE / '_lib.jsx').read_text()}\n"
           f"var __r = (function () {{\n{body}\n}})();{save}\n__r;\n")
    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="ae_tpl_"))
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.jsx"
    path.write_text(src)
    return {"template": name, "script": str(path), "params": merged,
            "run_with": f'return String($.evalFile(new File({json.dumps(str(path))})));'}
