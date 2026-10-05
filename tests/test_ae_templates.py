"""AE FX templates: the scripts are generated and parameterised here; running them needs After Effects."""
import json
import shutil
import subprocess

import pytest

from claude_spine import ae_templates

NODE = shutil.which("node")


def test_every_template_has_a_header_and_defaults():
    t = ae_templates.list_templates()
    assert {"glow_pulse", "shockwave", "sparkle", "relief_shimmer", "fire", "lightning", "burst", "splash"} <= set(t)
    for name, meta in t.items():
        assert meta["doc"] and meta["params"], name
        assert meta["params"].get("duration", 1) > 0


def test_script_merges_params_over_defaults(tmp_path):
    r = ae_templates.build_script("burst", {"n": 5, "comp": "my_burst"}, tmp_path)
    assert r["params"]["n"] == 5 and r["params"]["speed"] == ae_templates.list_templates()["burst"]["params"]["speed"]
    src = open(r["script"]).read()
    assert "var P = " in src and '"comp": "my_burst"' in src and "AEFX.burst" in src
    assert r["run_with"].startswith("return String($.evalFile(")


def test_unknown_template_or_param_is_a_clear_error(tmp_path):
    with pytest.raises(ValueError, match="unknown template"):
        ae_templates.build_script("nope", {}, tmp_path)
    with pytest.raises(ValueError, match="no parameter"):
        ae_templates.build_script("fire", {"colour": "FF0000"}, tmp_path)


def test_save_as_is_appended_after_the_template_runs(tmp_path):
    r = ae_templates.build_script("glow_pulse", {"save_as": str(tmp_path / "x.aep")}, tmp_path)
    src = open(r["script"]).read()
    assert src.index("var __r = (function") < src.index("app.project.save(")


@pytest.mark.skipif(NODE is None, reason="Node not installed")
@pytest.mark.parametrize("name", sorted(ae_templates.list_templates()))
def test_generated_scripts_are_valid_javascript(name, tmp_path):
    r = ae_templates.build_script(name, {"image": "/x.png"} if name == "relief_shimmer" else {}, tmp_path)
    js = tmp_path / f"{name}.js"                       # node refuses to check a .jsx file
    js.write_text(open(r["script"]).read())
    p = subprocess.run([NODE, "--check", str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_tool_lists_and_builds(tmp_path):
    import asyncio
    from claude_spine.server import mcp

    def call(args):
        out = asyncio.run(mcp.call_tool("ae_template", args))
        return json.loads((out[0] if isinstance(out, tuple) else out)[0].text)
    assert "fire" in call({})["templates"]
    r = call({"name": "lightning", "params": {"seed": 9}, "out_dir": str(tmp_path)})
    assert r["params"]["seed"] == 9 and (tmp_path / "lightning.jsx").exists()
