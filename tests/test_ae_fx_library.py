"""After Effects FX library: index consistency, portable builders, build scripts, textures and the Spine handoff
(no After Effects needed; the library was checked in AE 2026 by building entries into an empty project from these
files and comparing the renders with the originals: pixel-identical except the random Advanced Lightning arcs)."""
import asyncio
import json
import re
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_fx_library as L

NODE = shutil.which("node")
LIB = L.library()


def test_index_is_consistent():
    assert len(LIB) >= 50
    comps = set()
    for n, e in LIB.items():
        assert (L.JSX / f"{e['builder']}.jsx").exists(), n
        assert e["comp"].endswith(f"_v{e['version']}"), n
        assert e["blend"] in ("normal", "additive") and e["look"] in ("cel", "realistic"), n
        assert e["kind"] in ("hero", "clip", "glow", "element"), n
        assert e["fps"] and e["frames"], n
        for d in e["needs"]:
            assert d in LIB, (n, d)
        assert e["comp"] not in comps, f"two entries build {e['comp']}"
        comps.add(e["comp"])
        if n.startswith("re_"):
            assert n[3:] in e["needs"], "a realistic effect is driven by its cel comp"
        if e["textures"]:
            assert e["look"] == "realistic"
    assert {e["kind"] for e in LIB.values()} == {"hero", "clip", "glow", "element"}


def test_builders_are_portable_and_not_traced():
    for f in L.JSX.glob("*.jsx"):
        s = f.read_text()
        assert not re.search(r"/Users/|[A-Z]:\\\\|fx1008", s), f"{f.name} has a machine-specific path or job name"
        assert "trace/" not in s and "_traced" not in f.name, f"{f.name}: traced data is not part of the library"
        if f.stem not in ("fxlib", "times", "re_kit", "gl_kit", "el_kit"):
            assert "function BUILD(V)" in s, f.name


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_builders_are_valid_javascript(tmp_path):
    bad = []
    for f in sorted(L.JSX.glob("*.jsx")):
        js = tmp_path / f"{f.stem}.js"                    # node refuses to check a .jsx file
        js.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(js)], capture_output=True, text=True)
        if r.returncode:
            bad.append(f"{f.name}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
    assert not bad, bad


def test_build_order_puts_dependencies_first():
    order = [e["name"] for e in L.build_order(["re_fs_transition", "re_fire_rose_burst", "fire_rose_burst"])]
    assert order.index("sunburst_loop") < order.index("fs_transition")
    assert order.index("re_sunburst_loop") < order.index("re_fs_transition")
    assert order.index("fire_rose_burst") < order.index("re_fire_rose_burst")
    assert len(order) == len(set(order))
    with pytest.raises(KeyError):
        L.build_order(["no_such_effect"])


def test_script_builds_missing_comps_and_keeps_existing(tmp_path):
    s = L.script(["re_target_ring"], textures_dir=str(tmp_path / "tex"))
    assert "var FXLIB_DIR" in s and "FXLIB_TEXTURES" in s and "fxlib.jsx" in s and "times.jsx" in s
    assert s.index('"target_ring.jsx"') < s.index('"re_target_ring.jsx"')
    assert '!has("tr_target_ring_v4")' in s and "BUILD(4)" in s and "BUILD(5)" in s
    assert "app.project.save()" in s
    assert "true || !has" in L.script(["target_ring"], rebuild=True)
    assert "new File(" in L.script(["target_ring"], save_as=str(tmp_path / "x.aep"))
    with pytest.raises(ValueError):
        L.script(["el_fire_burst"])                       # textures needed but no folder given


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_generated_script_runs_its_control_flow(tmp_path):
    """The generated script against a tiny stand-in for AE: builders are stubbed, so this checks the wrapper:
    dependency order, skipping existing comps, error capture and the JSON it returns."""
    s = L.script(["re_target_ring", "sun_rune_burst"], textures_dir="/tex/")
    stub = """
var built = [], items = [{name: "sr_sun_rune_v3"}];
function CompItem() {} items[0].__proto__ = CompItem.prototype;
var app = {project: {get numItems() { return items.length; }, item: function (i) { return items[i - 1]; },
                     file: null, save: function () {}}};
function Folder(p) { this.exists = true; }
function File(p) { this.p = p; }
var FX = {cleanSolids: function () {}};
var $ = {evalFile: function (p) { var b = String(p).split("/").pop();
  if (b === "re_target_ring.jsx") { BUILD = function () { throw new Error("boom"); }; return; }
  if (b.indexOf("kit") < 0 && b !== "fxlib.jsx" && b !== "times.jsx")
    BUILD = function (V) { built.push(b + V); return '{"comp":"' + b + V + '"}'; }; }};
var BUILD;
"""
    js = tmp_path / "run.js"
    js.write_text(stub + s.replace("(function () {", "var RESULT = (function () {", 1) +
                  "console.log(RESULT); console.log(JSON.stringify(built));\n")
    r = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out, built = r.stdout.strip().splitlines()
    res = json.loads(out)
    assert json.loads(built) == ["target_ring.jsx4"]
    assert res[0] == {"comp": "target_ring.jsx4"}
    assert "error" in res[1] and "boom" in res[1]["error"]
    assert res[2] == {"comp": "sr_sun_rune_v3", "kept": True}


def test_unmultiply_recovers_light_on_black():
    rgb = np.zeros((4, 4, 3), np.float32)
    rgb[1, 1] = [0.5, 0.25, 0.0]                         # half-bright orange on black
    rgba = L.unmultiply(rgb, 0)
    assert rgba.shape == (4, 4, 4)
    assert rgba[0, 0, 3] == 0 and abs(rgba[1, 1, 3] - 0.5) < 1e-6
    assert np.allclose(rgba[1, 1, :3], [1.0, 0.5, 0.0])


def test_fetch_textures_without_download(tmp_path):
    for pack in L.KENNEY:                                 # pretend the packs are there; no network in tests
        (tmp_path / pack).mkdir()
        Image.new("RGBA", (4, 4)).save(tmp_path / pack / "x.png")
    r = L.fetch_textures(str(tmp_path), download=False)
    assert r["packs"] == {k: "present" for k in L.KENNEY}
    for n in L.UNMULT:
        im = Image.open(tmp_path / "ready" / f"{n}.png")
        assert im.mode == "RGBA"
    for n in L.OPAQUE:
        assert (tmp_path / "ready" / f"{n}.jpg").exists()
    rows = (tmp_path / "CREDITS_photos.csv").read_text().splitlines()
    assert len(rows) - 1 == r["photos"] == len(list((L.LIB / "textures" / "photo").glob("*.jpg")))
    for line in rows[1:]:
        assert ",cc0," in line.lower() or "public domain" in line.lower() or ",pdm," in line.lower(), line


def _frames(d, n=6, size=96, light=True):
    d.mkdir(parents=True)
    for i in range(n):
        a = np.zeros((size, size, 4), np.uint8)
        r = 8 + i * 5
        yy, xx = np.mgrid[:size, :size]
        m = (yy - size / 2) ** 2 + (xx - size / 2) ** 2 < r * r
        a[m] = [255, 200, 60, 255]
        Image.fromarray(a if not light else a, "RGBA").save(d / f"f_{i:05d}.png")
    return d


def test_to_spine_makes_one_skeleton_per_effect(tmp_path):
    fr = _frames(tmp_path / "frames")
    r = L.to_spine("fire_rose_burst", str(tmp_path / "out"), frames_dir=str(fr), spine_project=False)
    assert r["frames_in"] == 6 and r["pages"] >= 1 and r["gpu_mb"] > 0 and r["blend"] == "alpha"
    sk = json.loads((tmp_path / "out" / "fire_rose_burst" / "fx_fire_rose_burst.json").read_text())
    assert list(sk["animations"]) == ["fire_rose_burst"]
    assert any(b["name"] == "fx" for b in sk["bones"])
    assert list((tmp_path / "out" / "fire_rose_burst" / "export").glob("*.atlas"))
    r2 = L.to_spine("gl_win_glow_gold", str(tmp_path / "out"), frames_dir=str(fr), spine_project=False)
    assert r2["blend"] == "additive" and r2["texture"] <= 384   # the entry's budget caps soft glows


def test_mcp_tools_are_registered(tmp_path):
    from claude_spine.server import mcp

    async def call(tool, /, **args):
        res = await mcp.call_tool(tool, args)
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"ae_library", "ae_library_textures", "ae_library_to_spine"} <= names
    lst = asyncio.run(call("ae_library", kind="element"))
    assert lst["count"] == 8 and all(r["name"].startswith("el_") for r in lst["effects"])
    w = asyncio.run(call("ae_library", names=["target_ring"], out_dir=str(tmp_path)))
    assert w["builds"] == ["tr_target_ring_v4"] and "run_with" in w
