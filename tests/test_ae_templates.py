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


def test_metal_sparks_is_ccpw_with_echo_streaks(tmp_path):
    t = ae_templates.list_templates()
    assert "metal_sparks" in t and "additive" in t["metal_sparks"]["doc"]
    d = t["metal_sparks"]["params"]
    assert (d["size"], d["duration"], d["fps"], d["rate"], d["echoes"]) == (512, 0.8, 30, 0.7, 14)
    r = ae_templates.build_script("metal_sparks", {"rate": 1.1, "droplets": 0, "center_x": 0.3, "comp": "hit"}, tmp_path)
    assert r["params"]["rate"] == 1.1 and r["params"]["velocity"] == d["velocity"]
    src = open(r["script"]).read()
    assert '"mode":"additive"' in src and "CC Particle World" in src
    for mn in ("0004", "0005", "0007", "0008", "0010", "0015", "0016", "0018", "0041", "0019", "0020", "0023",
               "0024", "0025", "0026", "0027", "0029", "0030", "0104", "0055", "0060", "0061"):
        assert f'S("{mn}"' in src or f'"CC Particle World-{mn}"' in src, mn
    assert 'S("0050"' not in src and 'S("0062"' not in src          # groups: setting them throws
    assert "KeyframeInterpolationType.HOLD" in src                 # the birth burst
    assert '"ADBE Echo"' in src and '"Echo Operator", 2' in src and "-1 / 240" in src
    assert '"CC Force Motion Blur")' not in src            # it averaged the sparks to invisibility
    assert '"ADBE Glo2"' in src and "02_CORE_contact" in src
    assert ".forEach" not in src and "JSON." not in src


def test_frost_creep_is_luma_alpha_frost_revealed_by_a_gradient_wipe(tmp_path):
    t = ae_templates.list_templates()
    assert "frost_creep" in t and "face bone" in t["frost_creep"]["doc"].lower()
    d = t["frost_creep"]["params"]
    assert d["size"] == 560 and round(d["size"] * d["radius"], 3) == 262 and d["grow"] == [0.05, 1.5]
    assert d["from"] == "bottom" and d["color"] == "E2F2FF"
    r = ae_templates.build_script("frost_creep", {"from": "rim", "grow": [0, 1.2], "seed": 4}, tmp_path)
    assert r["params"]["from"] == "rim" and r["params"]["density"] == 1.0
    src = open(r["script"]).read()
    assert '"mode":"alpha"' in src
    for key in ('"ADBE Shift Channels"', '"Take Alpha From", LUMA', "LUMA = 5", '"ADBE Fill"', '"ADBE Gradient Wipe"',
                '"Transition Completion"', '"Transition Softness", 0.07', '"ADBE Find Edges"', '"ADBE Invert"',
                '"ADBE Fractal Noise"', '"Fractal Type", type', "TrackMatteType.ALPHA", "ADBE Mask Atom",
                "rim_density", "05_LIGHTING_front", "_map", "_ice", "BlendingMode.ADD"):
        assert key in src, key
    assert ".forEach" not in src and "JSON." not in src
    for side in ("bottom", "top", "left", "right", "rim"):
        assert f"{side}:" in src or f'"{side}"' in src


def test_new_templates_are_in_the_tool_listing():
    import asyncio
    from claude_spine.server import mcp
    out = asyncio.run(mcp.call_tool("ae_template", {}))
    listing = json.loads((out[0] if isinstance(out, tuple) else out)[0].text)["templates"]
    assert {"metal_sparks", "frost_creep"} <= set(listing)
