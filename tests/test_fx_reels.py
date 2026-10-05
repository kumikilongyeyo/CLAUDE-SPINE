"""Reel moments: reel_stop (spring thud, squash, dust, shake through carrier bones) and anticipation_reel
(accelerating heartbeat, dimmed neighbours, edge flames / sparks)."""
import math

import numpy as np
import pytest

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project
from conftest import needs_node


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def reels(tmp_path):
    """Three reel bones under a 'reels' container, 162 apart."""
    p = Project(tmp_path / "r.json", new_skeleton("r", 720, 720))
    p.data.bones.append(Bone(name="reels", parent="root", y=20))
    for i in range(3):
        p.data.bones.append(Bone(name=f"reel{i}", parent="reels", x=(i - 1) * 162, y=0))
    return p


def _xy(keys, rest):
    t = np.array([k.time for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


# ---------------------------------------------------------------- reel_stop
def test_reel_stop_spring_overshoots_exactly_and_settles_on_rest(proj):
    res = R.apply(proj, "reel_stop", options=dict(overshoot=40, squash=0.2))
    tl = proj.data.animations["fx_reel_stop"].bones[res["squash_bone"]]
    t, _, y = _xy(tl["translate"], 0.0)
    assert y.min() == pytest.approx(-40, abs=0.6), "the deepest point is exactly the overshoot"
    assert y[np.argmin(y)] < 0 and t[np.argmin(y)] < 0.12, "the strip keeps falling right after it lands"
    assert y.max() > 5, "underdamped: it springs back up past rest"
    assert y[-1] == 0 and t[-1] == pytest.approx(0.9)
    _, sx, sy = _xy(tl["scale"], 1.0)
    assert sy.min() == pytest.approx(0.8, abs=0.01) and sy.max() > 1.02, "squashed at the bottom, stretched on the rebound"
    assert sx[np.argmin(sy)] > 1.05, "it widens as it squashes"
    assert (sx[-1], sy[-1]) == (1, 1)


def test_reel_stop_carrier_keeps_the_reel_in_place_and_pivots_at_its_base(reels):
    sk = reels.data
    before = {n: (w.x, w.y) for n, w in sk.world().items()}
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(sk, "stop", replace=False).bone("reel1", "rotate", [(0, 0), (0.5, 12)])      # the artist's own key
    res = R.apply(reels, "reel_stop", x=0, y=20, into="stop", options=dict(reel="reel1", height=450))
    car = res["squash_bone"]
    assert sk.bone("reel1").parent == car and sk.bone(car).parent == "reels"
    w = sk.world()
    assert (w["reel1"].x, w["reel1"].y) == pytest.approx(before["reel1"]), "inserting the carrier moves nothing"
    assert (w[car].x, w[car].y) == pytest.approx((0, 20 - 225)), "the carrier sits at the strip's base"
    a = sk.animations["stop"]
    assert [k.time for k in a.bones["reel1"]["rotate"]] == [0, 0.5], "the artist's keys are untouched"
    assert set(a.bones[car]) == {"translate", "scale"}
    assert qa.validate(sk)["ok"]


def test_reel_stop_reuses_carriers_and_shakes_add_up(reels):
    one = Project(reels.path.with_name("one.json"), reels.data.model_copy(deep=True))
    R.apply(one, "reel_stop", into="a", options=dict(reel="reel0", shake="reels"))
    single = one.data.animations["a"].bones["fx_shake_reels"]["translate"]
    for i in range(3):
        res = R.apply(reels, "reel_stop", x=(i - 1) * 162, start=0.3 * i, into="stop", options=dict(reel=f"reel{i}", shake="reels"))
    assert res["shake_bone"] == "fx_shake_reels"
    assert [b.name for b in reels.data.bones].count("fx_shake_reels") == 1
    again = R.apply(reels, "reel_stop", into="other", options=dict(reel="reel0"))
    assert again["squash_bone"] == "fx_squash_reel0", "a second stop on the same reel drives the same carrier"
    t, x, y = _xy(reels.data.animations["stop"].bones["fx_shake_reels"]["translate"], 0.0)
    st, sx_, sy_ = _xy(single, 0.0)
    for q in (0.05, 0.33, 0.4):                       # overlapping shakes are the sum of each one alone
        want = np.interp(q, st, sy_) + (np.interp(q - 0.3, st, sy_) if q >= 0.3 else 0.0)
        assert np.interp(q, t, y) == pytest.approx(want, abs=0.15)
    assert y[-1] == 0 and x[-1] == 0 and t[-1] == pytest.approx(1.2)
    assert np.abs(y).max() > 5


def test_reel_stop_shake_is_a_fast_damped_spring(reels):
    R.apply(reels, "reel_stop", options=dict(shake="reels", shake_amp=10, shake_hz=13))
    t, x, y = _xy(reels.data.animations["fx_reel_stop"].bones["fx_shake_reels"]["translate"], 0.0)
    assert y[np.argmax(np.abs(y))] < 0, "the slam pushes the screen down first"
    crossings = np.sum(np.diff(np.sign(y[(t > 0.005) & (t < 0.3)])) != 0)
    assert crossings >= 5, "~13 Hz: several reversals inside 0.3 s"
    early, late = np.abs(y[t < 0.08]).max(), np.abs(y[(t > 0.25) & (t < 0.35)]).max()
    assert late < 0.25 * early, "the amplitude decays fast"


def test_reel_stop_dust_flies_out_sideways_with_drag(proj):
    res = R.apply(proj, "reel_stop", count=6)
    a = proj.data.animations["fx_reel_stop"]
    dust = [b for b in a.bones if b.startswith("fx_reel_stop_d") and b[len("fx_reel_stop_d"):].isdigit()]
    assert len(dust) == 6
    sides = set()
    for b in dust:
        t, x, y = _xy(a.bones[b]["translate"], 0.0)
        sides.add(np.sign(x[-1]))
        v = np.abs(np.diff(x)) / np.diff(t)
        assert v[0] > 3 * v[-1], "air drag: fast out, slowing down"
        assert y[-1] > 0, "the dust rises on the warm air"
    assert sides == {-1.0, 1.0}
    blends = [proj.data.slot(s).blend for s in res["slots"]]
    assert blends == sorted(blends, key=lambda b: b != "normal"), "normal-blend dust first, then the additive layers"
    assert qa.budget(proj.data, "desktop")["metrics"]["draw_calls"] == 2


def test_reel_stop_bad_inputs_are_clear_errors(reels):
    with pytest.raises(ValueError, match="root"):
        R.apply(reels, "reel_stop", options=dict(shake="root"))
    with pytest.raises(ValueError, match="no bone"):
        R.apply(reels, "reel_stop", options=dict(reel="nope"))
    with pytest.raises(ValueError, match="damping"):
        R.apply(reels, "reel_stop", options=dict(damping=1.5))


# ---------------------------------------------------------------- anticipation_reel
def test_anticipation_heartbeat_accelerates_and_fires_a_beat_event_each_time(proj):
    res = R.apply(proj, "anticipation_reel", duration=3.0, options=dict(period=0.6, accel=0.8, min_period=0.25))
    p = res["periods"]
    assert p[0] == pytest.approx(0.6) and p[1] == pytest.approx(0.48) and p[2] == pytest.approx(0.384)
    assert min(p) == pytest.approx(0.25) and all(a >= b for a, b in zip(p, p[1:]))
    gaps = np.diff(res["beats"])
    assert np.allclose(gaps, p[:-1], atol=1e-3)
    ev = [e.time for e in proj.data.animations["fx_anticipation_reel"].events if e.name == "fx_anticipation_beat"]
    assert ev == pytest.approx(res["beats"])


def test_anticipation_glow_pulses_on_the_beat_and_grows(proj):
    res = R.apply(proj, "anticipation_reel", options=dict(edge="none"))
    frame = [s for s in res["slots"] if "frame" in s][0]
    t, a = _alpha(proj.data.animations["fx_anticipation_reel"].slots[frame]["rgba"])
    peaks = [np.interp(b + 0.07, t, a) for b in res["beats"]]
    troughs = [np.interp(b - 0.02, t, a) for b in res["beats"][1:]]
    assert all(pk > tr + 0.15 for pk, tr in zip(peaks[1:], troughs))
    assert peaks[-1] > peaks[0], "the beats get stronger toward the stop"
    assert a[0] == 0 and a[-1] == 0


def test_anticipation_dims_the_neighbours(proj):
    res = R.apply(proj, "anticipation_reel", options=dict(dim=[[-170, 0, 150, 450], [-340, 0, 150, 450], [170, 0, 150, 450]], dim_alpha=0.6))
    assert res["dimmed"] == 3
    sk = proj.data
    dims = [s for s in res["slots"] if sk.slot(s).blend == "normal"]
    assert len(dims) == 3 and res["slots"][:3] == dims, "dim panels lead the run (one normal batch, then additive)"
    t, a = _alpha(sk.animations["fx_anticipation_reel"].slots[dims[0]]["rgba"])
    assert 0.55 <= np.interp(1.2, t, a) <= 0.75 and a[0] == 0 and a[-1] == 0
    w = sk.world()
    xs = sorted(round(w[sk.slot(s).bone].x) for s in dims)
    assert xs == [-340, -170, 170]
    assert qa.budget(sk, "desktop")["metrics"]["draw_calls"] == 2


def test_anticipation_edge_flames_rise_cool_and_respawn_hidden(proj):
    res = R.apply(proj, "anticipation_reel", count=4, options=dict(edge="flames", width=150))
    assert res["tongues"] == 8 and "fire" in res["ae_hint"]["note"]
    sk, a = proj.data, proj.data.animations["fx_anticipation_reel"]
    tongues = [s for s in res["slots"] if "_fl" in s]
    assert len(tongues) == 8
    xs = {round(sk.bone(sk.slot(s).bone).x) for s in tongues}
    assert xs == {-75, 75}, "tongues sit on both side edges"
    for s in tongues:
        b = sk.slot(s).bone
        t, _, y = _xy(a.bones[b]["translate"], 0.0)
        jumps = np.where(np.diff(y) < -1)[0]          # respawn: back down to the edge point
        ta, al = _alpha(a.slots[s]["rgba"])
        for j in jumps:
            assert np.interp(t[j], ta, al) < 0.05 and np.interp(t[j + 1], ta, al) < 0.05, "the jump hides inside alpha 0"
        cols = [k.color[:6] for k in a.slots[s]["rgba"]]
        assert len(set(cols)) > 5, "the flame cools as it rises"


def test_anticipation_edge_sparks_crackle_on_the_beat(proj):
    res = R.apply(proj, "anticipation_reel", options=dict(edge="sparks", sparks=10, width=150, height=450))
    assert res["sparks"] > 0 and "electric_frame" in res["ae_hint"]["note"]
    a = proj.data.animations["fx_anticipation_reel"]
    beats = res["beats"]
    for s in [s for s in res["slots"] if "_sp" in s]:
        att = a.slots[s]["attachment"]
        ons = [k.time for k in att if k.name == "fx"]
        assert all(min(abs(t - b) for b in beats) <= 0.051 for t in ons), "every spark lights on a beat"
        b = proj.data.slot(s).bone
        if b in a.bones:
            _, x, y = _xy(a.bones[b]["translate"], 0.0)
            assert set(np.round(np.abs(x))) == {75} and np.all(np.abs(y) <= 225)


def test_anticipation_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="edge"):
        R.apply(proj, "anticipation_reel", options=dict(edge="smoke"))
    with pytest.raises(ValueError, match="accel"):
        R.apply(proj, "anticipation_reel", options=dict(accel=1.4))


@needs_node
def test_a_spin_clip_with_both_plays_in_the_spine_core_runtime(reels):
    for i in range(2):
        R.apply(reels, "reel_stop", x=(i - 1) * 162, y=20, start=0.3 * i, into="spin", options=dict(reel=f"reel{i}", shake="reels"))
    R.apply(reels, "anticipation_reel", x=162, y=20, start=0.6, duration=2.0, into="spin",
            options=dict(dim=[[-162, 0, 150, 450], [-324, 0, 150, 450]]))
    R.apply(reels, "reel_stop", x=162, y=20, start=2.6, into="spin", options=dict(reel="reel2", shake="reels"))
    assert qa.validate(reels.data)["ok"]
    reels.save()
    dump = runtime.run(reels, animations=["spin"], fps=20, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"]["spin"]["duration"] == pytest.approx(3.5, abs=0.01)


def test_whitespace_strip_never_crops_inside_a_mesh(proj, tmp_path):
    """A 9-slice dim panel's corner UVs reach the texture's transparent border. Stripping that border used to map the
    corner outside the packed region, onto the neighbouring image (a dark speck in every dimmed reel)."""
    from PIL import Image
    from claude_spine import atlas
    from claude_spine.ir import RegionAttachment, Slot
    proj.write_image("solid", Image.new("RGBA", (64, 64), (255, 255, 255, 255)))
    proj.data.add_slot(Slot(name="solid", bone="root", attachment="solid"))
    proj.data.set_attachment("solid", "solid", RegionAttachment(path="solid", width=64, height=64))
    R.apply(proj, "anticipation_reel", options=dict(edge="none", dim=[[0, 0, 150, 450]]))
    ext = atlas.mesh_uv_extent(proj)
    assert ext["fx/cellfill"] == (0.0, 0.0, 1.0, 1.0)
    res = atlas.pack(proj, tmp_path / "exp", strip=True, pma=False)
    regions, cur = {}, None
    for ln in open(res["atlas"]).read().splitlines():
        if ":" not in ln and ln.strip() and not ln.endswith(".png"):
            cur = regions.setdefault(ln.strip(), {})
        elif ":" in ln and cur is not None:
            k, v = ln.split(":", 1)
            cur[k.strip()] = v.strip()
    assert regions["fx/cellfill"]["bounds"].split(",")[2:] == ["192", "192"], "the mesh image keeps its full size"
    assert "offsets" not in regions["fx/cellfill"]
    assert "solid" in regions, "plain regions are still packed"
