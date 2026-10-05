"""Saber port: the Spine recipe (glow falloff, distortion, flicker, draw on/off, closed rings) and the AE template
(every preset and core, run against the mock AE object model)."""
import json
import math
import re
import shutil
import subprocess

import numpy as np
import pytest

from claude_spine import ae_templates, fx_recipes as R, qa, runtime
from claude_spine.fx_saber import CAP, presets
from claude_spine.ir import new_skeleton
from claude_spine.project import Project
from conftest import needs_node

NODE = shutil.which("node")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _xy(keys):
    v = lambda k, f: 0.0 if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return np.array([k.time for k in keys]), np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


# ---------------------------------------------------------------- presets: one table for both halves
def test_presets_are_read_from_the_ae_template_and_complete():
    pre = presets()
    assert {"default", "red", "green", "purple", "gold", "neon", "laser", "electric", "fire", "energy", "plasma", "haze"} <= set(pre)
    keys = {"color", "core_color", "core_size", "intensity", "spread", "bias", "distortion", "noise_size", "noise_speed", "flicker", "haze"}
    assert all(set(v) == keys for v in pre.values())
    assert all(isinstance(v["noise_speed"], int) for v in pre.values()), "integer cycles per loop"


@pytest.mark.parametrize("preset", sorted(presets()))
@pytest.mark.parametrize("core", ["line", "points", "circle", "rect"])
def test_every_preset_and_core_builds_and_validates(proj, preset, core):
    opts = dict(preset=preset, core=core)
    if core == "points":
        opts["points"] = [[-200, -40], [-60, 60], [80, -60], [220, 40]]
    res = R.apply(proj, "saber", options=opts)
    assert res["animation"] == "fx_saber" and res["event"] == "fx_saber"
    assert all(s.blend == "additive" and s.attachment is None for s in proj.data.slots)
    assert qa.validate(proj.data)["ok"]
    assert qa.budget(proj.data, "desktop")["metrics"]["draw_calls"] == 1


def test_style_options_win_over_the_preset(proj):
    res = R.apply(proj, "saber", color="00FF00", options=dict(preset="red", core_size=12.0, distortion=0.0))
    p = res["ae_hint"]["params"]
    assert p["color"] == "00FF00" and p["core_size"] == 12.0 and p["spread"] == presets()["red"]["spread"]


# ---------------------------------------------------------------- physics
def test_glow_falloff_follows_the_bias_law(proj):
    R.apply(proj, "saber", name="a", options=dict(preset="default", flicker=0.0, bias=1.0, glow_layers=4))
    R.apply(proj, "saber", name="b", options=dict(preset="default", flicker=0.0, bias=0.5, glow_layers=4))
    sk = proj.data

    def peaks(anim):
        a = sk.animations[anim]
        bands = sorted([s for s in a.slots if "_saber" in s], key=lambda s: [x.name for x in sk.slots].index(s))
        return [_alpha(a.slots[s]["rgba"])[1].max() for s in bands[:-1]]   # widest first, core last
    pa, pb = peaks("fx_a"), peaks("fx_b")
    # widest band first: k = 3, 2, 1, 0; peak (r0 / r_k)^bias = 2^(-k bias)
    assert pa == pytest.approx([2 ** -3, 2 ** -2, 2 ** -1, 1.0], abs=0.01), "bias 1: every octave halves (1/r)"
    assert pb == pytest.approx([2 ** -1.5, 2 ** -1, 2 ** -0.5, 1.0], abs=0.01), "bias 0.5: a wider haze"
    widths = []
    for s in [x for x in sk.slots if x.name.startswith("fx_a_saber")][:-1]:
        v = sk.skins[0].attachments[s.name]["fx"].vertices
        ys = [v[i + 3] for i in range(0, len(v), 5)]
        widths.append(max(ys) - min(ys))
    ratios = [widths[i] / widths[i + 1] for i in range(len(widths) - 1)]
    assert ratios == pytest.approx([2, 2, 2], rel=0.02), "bands at doubling widths"


def test_distortion_writhes_sideways_and_loops_exactly(proj):
    res = R.apply(proj, "saber", duration=2.0, options=dict(preset="electric", start=[-250, 0], end=[250, 0]))
    a = proj.data.animations["fx_saber"]
    rows = [b for b in a.bones if re.fullmatch(r"fx_saber_r\d+", b)]
    assert len(rows) == res["rows"]
    t, x, y = _xy(a.bones[rows[len(rows) // 2]]["translate"])
    assert np.abs(y).max() > 5 and np.abs(x).max() < 1e-6, "a horizontal beam writhes vertically only"
    assert (x[0], y[0]) == pytest.approx((x[-1], y[-1]), abs=1e-3) and t[-1] == pytest.approx(2.0)
    ys = np.array([_xy(a.bones[b]["translate"])[2][len(t) // 3] for b in rows])
    assert np.sum(np.diff(np.sign(ys)) != 0) >= 4, "travelling waves along the beam"


def test_flicker_loops_and_stays_within_its_depth(proj):
    R.apply(proj, "saber", duration=2.0, options=dict(preset="electric"))
    a = proj.data.animations["fx_saber"]
    for s in a.slots:
        t, al = _alpha(a.slots[s]["rgba"])
        assert al[0] == pytest.approx(al[-1], abs=1 / 255)
        assert al.min() >= al.max() * (1 - presets()["electric"]["flicker"]) - 2 / 255


def test_draw_on_grows_from_the_start_and_fires_its_event(proj):
    R.apply(proj, "saber", duration=2.0, options=dict(preset="default", draw="on", draw_time=0.6, start=[-200, 0], end=[200, 0]))
    a = proj.data.animations["fx_saber"]
    rows = sorted([b for b in a.bones if re.fullmatch(r"fx_saber_r\d+", b)], key=lambda b: int(b.split("_r")[-1]))
    last = proj.data.bone(rows[-1])
    t, x, _ = _xy(a.bones[rows[-1]]["translate"])
    assert last.x + x[0] == pytest.approx(-200, abs=1e-3), "at t=0 the far end sits on the start (collapsed)"
    assert np.interp(0.6, t, x) == pytest.approx(0, abs=1e-3), "drawn out by draw_time"
    ts, sx, _ = _xy(a.bones[rows[-1]]["scale"])
    assert sx[0] == 0 and np.interp(0.65, ts, sx) == 1
    ev = {e.name: e.time for e in a.events}
    assert ev["fx_saber_on"] == pytest.approx(0.6)


def test_draw_off_leaves_nothing_and_closed_rings_have_no_seam(proj):
    R.apply(proj, "saber", name="off", duration=2.0, options=dict(preset="default", draw="off", draw_time=0.5))
    a = proj.data.animations["fx_off"]
    rows = sorted([b for b in a.bones if re.fullmatch(r"fx_off_r\d+", b)], key=lambda b: int(b.split("_r")[-1]))
    assert all(_xy(a.bones[b]["scale"])[1][-1] == 0 for b in rows), "every row has shrunk away at the end"
    res = R.apply(proj, "saber", name="ring", duration=2.0, options=dict(preset="fire", core="circle", radius=120))
    b = proj.data.animations["fx_ring"]
    rr = sorted([x for x in b.bones if re.fullmatch(r"fx_ring_r\d+", x)], key=lambda x: int(x.split("_r")[-1]))
    first, lastb = proj.data.bone(rr[0]), proj.data.bone(rr[-1])
    for (t0, x0, y0), (t1, x1, y1) in [(_xy(b.bones[rr[0]]["translate"]), _xy(b.bones[rr[-1]]["translate"]))]:
        assert np.allclose(first.x + x0, lastb.x + x1, atol=1e-3) and np.allclose(first.y + y0, lastb.y + y1, atol=1e-3), \
            "the ring's two ends move together (whole waves around it)"
    assert (lastb.rotation - first.rotation) % 360 == pytest.approx(0, abs=1e-6)
    us = proj.data.skins[0].attachments[res["slots"][0]]["fx"].uvs[0::2]
    assert min(us) >= CAP - 1e-6 and max(us) <= 1 - CAP + 1e-6, "a ring stays inside the texture's uniform middle"


def test_wide_bands_never_fold_in_a_tight_ring(proj):
    res = R.apply(proj, "saber", options=dict(preset="haze", core="circle", radius=60, distortion=0.0))
    for s in res["slots"]:
        v = proj.data.skins[0].attachments[s]["fx"].vertices
        half = max(abs(v[i + 3]) for i in range(0, len(v), 5))
        assert half <= 0.65 * 60 * 1.01 or half < 10


def test_bad_options(proj):
    with pytest.raises(ValueError, match="preset"):
        R.apply(proj, "saber", options=dict(preset="jedi"))
    with pytest.raises(ValueError, match="text is After Effects only"):
        R.apply(proj, "saber", options=dict(core="text"))
    with pytest.raises(ValueError, match="draw"):
        R.apply(proj, "saber", options=dict(draw="sideways"))
    with pytest.raises(ValueError, match="points"):
        R.apply(proj, "saber", options=dict(core="points", points=[[0, 0]]))


@needs_node
def test_saber_plays_in_the_spine_core_runtime(proj):
    R.apply(proj, "saber", options=dict(preset="electric", draw="on_off"))
    proj.save()
    dump = runtime.run(proj, animations=["fx_saber"], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")


# ---------------------------------------------------------------- the AE half
def test_ae_hint_maps_the_geometry_into_the_comp(proj):
    res = R.apply(proj, "saber", x=40, y=-10, options=dict(preset="laser", start=[-200, 50], end=[180, -30], px=2.0))
    h = res["ae_hint"]
    p = h["params"]
    assert h["template"] == "saber" and h["mode"] == "additive" and h["seq_mode"] == "loop" and h["scale"] == 0.5
    W, H = p["width"], p["height"]
    assert p["start"] == [W / 2 - 400, H / 2 - 100] and p["end"] == [W / 2 + 360, H / 2 + 60], "y flips, px scales"
    assert p["core_size"] == presets()["laser"]["core_size"] * 2
    assert 0 < p["start"][0] < W and 0 < p["start"][1] < H
    ae_templates.build_script("saber", p)


def _mock_src():
    from test_fx_ambient import MOCK
    m = MOCK.replace(
        "addShape() { return new Node(\"shape\"); } };",
        "addShape() { return new Node(\"shape\"); },\n"
        "                    addText(s) { if (typeof s !== 'string' || !s) throw new Error('text'); const l = new Node('text');\n"
        "                      const td = { text: s }; l.property('ADBE Text Properties').property('ADBE Text Document').value = td;\n"
        "                      return l; } };")
    assert m != MOCK, "the mock changed shape; update the patch"
    return m + "\nconst ParagraphJustification = { CENTER_JUSTIFY: 'C', LEFT_JUSTIFY: 'L', RIGHT_JUSTIFY: 'R' };\n"


VARIANTS = [dict(preset=p) for p in sorted(presets())] + [
    dict(core="points", points=[[100, 200], [300, 60], [500, 200]]), dict(core="circle", radius=90, preset="fire"),
    dict(core="rect", rect=[500, 160, 30], preset="neon"), dict(core="text", text="WIN", preset="gold", draw="on"),
    dict(draw="on_off", preset="electric"), dict(draw="off", preset="laser", glow_layers=3)]


@pytest.mark.skipif(NODE is None, reason="Node not installed")
@pytest.mark.parametrize("opts", VARIANTS, ids=[json.dumps(v, sort_keys=True)[:60] for v in VARIANTS])
def test_template_runs_against_a_mock_after_effects(tmp_path, opts):
    r = ae_templates.build_script("saber", opts, tmp_path)
    src = open(r["script"]).read().replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
    D = r["params"]["duration"]
    js = tmp_path / "run.js"
    js.write_text(_mock_src() + src + f"""
const out = [];
for (const e of rec.expressions) {{
  const f = new Function("time", "value", "return (" + e + ");");
  out.push([e, [0, {D / 2}, {D}].map((t) => f(t, 80))]);
}}
console.log(JSON.stringify({{ r: JSON.parse(__r), ex: out, comps: rec.comps }}));
""")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o["r"]["mode"] == "additive" and o["r"]["frames"] == round(D * r["params"]["fps"])
    assert o["r"]["seq_mode"] == ("loop" if opts.get("draw", "none") == "none" else "once")
    assert any(c.endswith("_core") for c in o["comps"]), "the core lives in its own comp, sampled by every glow"
    for e, vals in o["ex"]:
        assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals), e
        assert vals[0] == pytest.approx(vals[2], abs=1e-9), "flicker loops exactly"
        assert all(0 <= v <= 80 + 1e-9 for v in vals)


@pytest.mark.skipif(NODE is None, reason="Node not installed")
def test_template_rejects_bad_choices(tmp_path):
    for bad, msg in ((dict(preset="jedi"), "preset must be"), (dict(core="star"), "core must be"), (dict(draw="up"), "draw must be")):
        r = ae_templates.build_script("saber", bad, tmp_path)
        src = open(r["script"]).read().replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
        js = tmp_path / "bad.js"
        js.write_text(_mock_src() + src)
        p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
        assert p.returncode != 0 and msg in p.stderr
