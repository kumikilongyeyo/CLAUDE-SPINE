"""Payout moments: coin_fountain (drag parabolas, apex hang time, tumbling flipbook coins, restitution bounces, friction
slide, Euler's-disk rattle) and cascade_pop (Voronoi shards with drag + gravity, puff + hit burst, symbols above dropping
through carrier bones with exact restitution hops and a squash spring)."""
import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

from claude_spine import fx_payouts as F  # noqa: F401  registers the recipes
from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def grid(tmp_path):
    """A symbol grid: 'grid' container, three symbols in the top row (y=150) that will drop into the middle row."""
    p = Project(tmp_path / "g.json", new_skeleton("g", 720, 720))
    p.data.bones.append(Bone(name="grid", parent="root", y=40))
    for i in range(3):
        p.data.bones.append(Bone(name=f"top{i}", parent="grid", x=(i - 1) * 150, y=150))
    return p


def _xy(keys, rest):
    t = np.array([k.time for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _val(keys, rest=0.0):
    return np.array([k.time for k in keys]), np.array([rest if k.value is None else float(k.value) for k in keys])


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _common(p, res, anim):
    sk = p.data
    assert qa.validate(sk)["ok"]
    blends = [sk.slot(s).blend for s in res["slots"]]
    assert blends == sorted(blends, key=lambda b: b != "normal"), "normal-blend layers first, then the additive ones"
    assert all(sk.slot(s).attachment is None for s in res["slots"]), "FX slots are hidden in the setup pose"
    assert anim in sk.animations


def _coin(p, anim, i=0):
    a = p.data.animations[anim]
    return a.bones[f"fx_coin_fountain_c{i}"]


# ---------------------------------------------------------------- coin_fountain
def test_coin_fountain_builds_two_batches_hidden_and_fires_its_events(proj):
    res = R.apply(proj, "coin_fountain", count=20, options=dict(landings=6))
    _common(proj, res, "fx_coin_fountain")
    assert qa.budget(proj.data, "desktop")["metrics"]["draw_calls"] == 2
    assert res["coins"] == 20 and res["shadows"] == 20
    ev = proj.data.animations["fx_coin_fountain"].events
    assert [e.time for e in ev if e.name == "fx_coin_fountain"] == [0.0]
    lands = [e.time for e in ev if e.name == "fx_coin_land"]
    assert len(lands) == 6 and lands == pytest.approx(res["landings"]), "first landings thinned to `landings`"
    assert "emitter" in res["engine_hint"]["note"] and res["engine_hint"]["restitution"] == 0.38
    sk = proj.data
    coins = [s for s in res["slots"] if "_c" in s and sk.slot(s).blend == "normal" and "_sh" not in s]
    att = sk.skin("default").attachments[coins[0]]["fx"]
    assert att.path == "fx/coin_" and att.sequence.count == 8, "the fx.py coin flipbook"


def test_coin_flight_is_a_drag_free_parabola_when_drag_and_hang_are_off(proj):
    R.apply(proj, "coin_fountain", count=1, options=dict(drag=0, hang=0, depth=0, gravity=2000, floor=-80))
    t, x, y = _xy(_coin(proj, "fx_coin_fountain")["translate"], 0.0)
    hit = int(np.argmax(np.isclose(y, -80) & (t > 0.05)))
    a, b, c0 = np.polyfit(t[:hit + 1], y[:hit + 1], 2)
    assert a == pytest.approx(-1000, rel=0.002), "y = vy t - g t^2 / 2"
    assert y.max() <= 330 + 1, "the apex is the coin's chosen height (<= height)"
    assert np.polyfit(t[:hit + 1], x[:hit + 1], 2)[0] == pytest.approx(0, abs=0.5), "no drag: constant sideways speed"


def test_coin_drag_slows_the_sideways_speed_exponentially(proj):
    R.apply(proj, "coin_fountain", count=1, options=dict(drag=1.5, hang=0, depth=0, floor=-80))
    t, x, y = _xy(_coin(proj, "fx_coin_fountain")["translate"], 0.0)
    hit = int(np.argmax(np.isclose(y, -80) & (t > 0.05)))
    v = np.diff(x[:hit + 1]) / np.diff(t[:hit + 1])
    tm = (t[:hit] + t[1:hit + 1]) / 2
    k = -np.polyfit(tm, np.log(np.abs(v)), 1)[0]
    assert k == pytest.approx(1.5, rel=0.03), "vx = vx0 e^-kt"


def test_hang_time_stretches_the_apex_but_not_the_path(proj, tmp_path):
    other = Project(tmp_path / "o.json", new_skeleton("o", 720, 720))
    R.apply(proj, "coin_fountain", count=1, options=dict(hang=0, depth=0))
    R.apply(other, "coin_fountain", count=1, options=dict(hang=1.5, depth=0))
    t0, x0, y0 = _xy(_coin(proj, "fx_coin_fountain")["translate"], 0.0)
    t1, x1, y1 = _xy(_coin(other, "fx_coin_fountain")["translate"], 0.0)
    assert y1.max() == pytest.approx(y0.max(), abs=0.01) and x1[-1] == pytest.approx(x0[-1], abs=0.01), "same path"
    top = lambda t, y: np.sum(np.diff(t)[(y[1:] > 0.9 * y.max()) & (y[:-1] > 0.9 * y.max())])  # noqa: E731
    assert top(t1, y1) > 1.8 * top(t0, y0), "the coin hangs at the top (the clock runs 1/(1+hang) there)"
    near = lambda t, y: np.ptp(t[y > 0.98 * y.max()])  # noqa: E731
    assert near(t1, y1) > 2.0 * near(t0, y0), "right at the top the clock runs ~1/(1+hang) as fast"
    # away from the apex the warp is gone: the landing speed is the real one
    h0, h1 = int(np.argmax(np.isclose(y0, y0.min()))), int(np.argmax(np.isclose(y1, y1.min())))
    vl0 = (y0[h0] - y0[h0 - 1]) / (t0[h0] - t0[h0 - 1])
    vl1 = (y1[h1] - y1[h1 - 1]) / (t1[h1] - t1[h1 - 1])
    assert vl1 == pytest.approx(vl0, rel=0.01), "away from the apex the clock runs at 1: the landing speed is real"


def test_bounces_lose_e_squared_height_and_take_friction_then_slide_to_rest(proj):
    e = 0.5
    res = R.apply(proj, "coin_fountain", count=1, options=dict(restitution=e, bounces=3, depth=0, floor=-80, friction=0.1))
    t, x, y = _xy(_coin(proj, "fx_coin_fountain")["translate"], 0.0)
    on = np.where(np.isclose(y, -80, atol=1e-6))[0]
    touch = [on[0]] + [j for i, j in zip(on, on[1:]) if j != i + 1]          # each landing on the counter
    hops = []
    for a_, b_ in zip(touch, touch[1:]):
        hops.append((t[b_] - t[a_], y[a_:b_ + 1].max() + 80))
    assert len(hops) >= 2
    (d1, h1), (d2, h2) = hops[0], hops[1]
    assert d2 / d1 == pytest.approx(e, abs=0.01), "each hop leaves at e x the speed it came in with"
    assert h2 / h1 == pytest.approx(e * e, rel=0.06), "so the hop heights fall by e^2"
    # the slide: on the counter, constant deceleration, ends still
    s0 = touch[len(hops)]
    ts, xs = t[s0:], x[s0:]
    assert np.allclose(y[s0:], -80)
    v = np.diff(xs) / np.diff(ts)
    if len(v) > 3 and abs(v[0]) > 1:
        acc = np.diff(v) / np.diff((ts[1:] + ts[:-1]) / 2)
        assert np.ptp(acc) < 0.05 * abs(acc).mean() + 1e-6, "Coulomb friction: constant deceleration"
        assert abs(v[-1]) < 0.15 * abs(v[0])
    assert res["rest"][0] < 3.8


def test_coin_lands_flat_level_and_still_then_fades(proj):
    res = R.apply(proj, "coin_fountain", count=3, options=dict(flat=0.4))
    a = proj.data.animations["fx_coin_fountain"]
    for i in range(3):
        b = a.bones[f"fx_coin_fountain_c{i}"]
        _, rot = _val(b["rotate"])
        assert rot[-1] % 360 == pytest.approx(0, abs=1e-6) or rot[-1] % 360 == pytest.approx(360, abs=1e-6), "rests level (whole turns)"
        _, sx, sy = _xy(b["scale"], 1.0)
        assert (sx[-1], sy[-1]) == (1.0, 0.4), "lying flat on the counter"
    for s in [s for s in res["slots"] if s.startswith("fx_coin_fountain_c")]:
        ta, al = _alpha(a.slots[s]["rgba"])
        assert al[-1] == 0 and ta[-1] == pytest.approx(3.8)
        seq = a.attachments["default"][s]["fx"]["sequence"]
        assert seq[0].mode == "loop" and seq[-1].mode == "hold", "the flipbook tumbles in the air and holds face-on at rest"
    assert max(res["rest"]) <= 3.8 - 0.35 + 1e-6, "every coin is at rest before the fade"


def test_euler_wobble_dies_while_its_frequency_rises():
    w = F.euler_wobble(0.5, 5.0, 10.0)
    t = np.array([p[0] for p in w])
    a = np.array([p[1] for p in w])
    assert t[0] == 0 and t[-1] == 0.5 and a[-1] == 0 and a[0] == 0
    peaks = np.abs(a[1::2])
    assert np.all(np.diff(peaks[:-1]) < 0), "the rattle dies as (1 - t/T)^(1/3)"
    gaps = np.diff(t[:-1])
    assert gaps[-1] < 0.8 * gaps[0], "and speeds up as (1 - t/T)^(-1/6)"


def test_shower_rains_from_above_toward_terminal_speed(proj):
    res = R.apply(proj, "coin_fountain", count=8, options=dict(mode="shower", height=500, drag=2.0, gravity=2000, depth=0, floor=-100))
    _common(proj, res, "fx_coin_fountain")
    for i in range(8):
        t, x, y = _xy(_coin(proj, "fx_coin_fountain", i)["translate"], 0.0)
        assert y[0] >= 500
        hit = int(np.argmax(np.isclose(y, -100)))
        v = -np.diff(y[:hit + 1]) / np.diff(t[:hit + 1])
        assert v.max() <= 2000 / 2.0 + 1e-6, "never faster than the terminal speed g/k"
        assert v[-1] > 0.6 * 1000
    assert not any("glow" in s for s in res["slots"]), "no spout in a shower"


def test_coin_fountain_tiers_scale_up_and_build(proj):
    tiers = R.RECIPES["coin_fountain"]["tiers"]
    assert set(tiers) == {"small", "big", "mega", "epic"}
    counts = [tiers[t]["count"] for t in ("small", "big", "mega", "epic")]
    assert counts == sorted(counts) and counts[0] < R.RECIPES["coin_fountain"]["count"] < counts[1]
    for name, tr in tiers.items():
        o = {k: v for k, v in tr.items() if k not in ("count", "duration")}
        res = R.apply(proj, "coin_fountain", into=name, count=tr["count"], duration=tr["duration"], options=o)
        assert res["coins"] == tr["count"] and res["duration"] == tr["duration"]
    assert qa.validate(proj.data)["ok"]


def test_coin_fountain_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="mode"):
        R.apply(proj, "coin_fountain", options=dict(mode="geyser"))
    with pytest.raises(ValueError, match="emitter"):
        R.apply(proj, "coin_fountain", count=200)
    with pytest.raises(ValueError, match="restitution"):
        R.apply(proj, "coin_fountain", options=dict(restitution=1.2))
    with pytest.raises(ValueError, match="too short"):
        R.apply(proj, "coin_fountain", duration=1.0)
    with pytest.raises(ValueError, match="floor"):
        R.apply(proj, "coin_fountain", options=dict(floor=40))


def test_coin_art_replaces_the_flipbook_with_a_scalex_flip(proj, tmp_path):
    png = tmp_path / "coin.png"
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([2, 2, 61, 61], fill=(240, 200, 60, 255))
    im.save(png)
    res = R.apply(proj, "coin_fountain", count=2, art={"coin": str(png)})
    assert res["art"]["coin"].startswith("fx/art_coin_fountain")
    s = [s for s in res["slots"] if s.startswith("fx_coin_fountain_c")][0]
    att = proj.data.skin("default").attachments[s]["fx"]
    assert att.sequence is None
    _, sx, _ = _xy(_coin(proj, "fx_coin_fountain", 0)["scale"], 1.0)
    assert sx.min() < 0.2 and sx.max() == pytest.approx(1.12), "it turns edge-on in the air"


# ---------------------------------------------------------------- cascade_pop
CELLS = [[-150, 0, 150, 150], [0, 0, 150, 150], [150, 0, 150, 150]]


def test_cascade_pop_builds_two_batches_with_puff_and_hit(grid):
    res = R.apply(grid, "cascade_pop", y=40, parent="grid", options=dict(cells=CELLS))
    _common(grid, res, "fx_cascade_pop")
    assert qa.budget(grid.data, "desktop")["metrics"]["draw_calls"] == 2, "every normal slot (puff lobes too) leads the run"
    ev = [e.name for e in grid.data.animations["fx_cascade_pop"].events]
    assert ev.count("fx_cascade_pop") == 1 and ev.count("fx_cascade_shatter") == 3
    assert ev.count("fx_puff") >= 3 and ev.count("fx_hit_burst") == 3
    assert res["breaks"] == pytest.approx([0.14, 0.19, 0.24])
    assert len(res["slots"]) <= 80, "3 cells fit the mobile_banner slot budget"


def test_shards_fall_under_gravity_and_drag_eats_their_speed(proj):
    R.apply(proj, "cascade_pop", options=dict(drag=0, gravity=2400, puff=False, hit=False))
    a = proj.data.animations["fx_cascade_pop"]
    shards = [b for b in a.bones if b.startswith("fx_cascade_pop_s0_")]
    assert len(shards) >= 5
    for b in shards:
        t, x, y = _xy(a.bones[b]["translate"], 0.0)
        assert np.polyfit(t, y, 2)[0] == pytest.approx(-1200, rel=0.01), "y = vy t - g t^2 / 2"
        assert np.polyfit(t, x, 2)[0] == pytest.approx(0, abs=0.5), "no drag: constant sideways speed"
    other = Project(proj.path.with_name("d.json"), new_skeleton("d", 720, 720))
    R.apply(other, "cascade_pop", options=dict(drag=3.0, puff=False, hit=False))
    a = other.data.animations["fx_cascade_pop"]
    t, x, _ = _xy(a.bones["fx_cascade_pop_s0_1"]["translate"], 0.0)
    v = np.diff(x) / np.diff(t)
    tm = (t[1:] + t[:-1]) / 2
    assert -np.polyfit(tm, np.log(np.abs(v)), 1)[0] == pytest.approx(3.0, rel=0.03), "vx = vx0 e^-kt"
    shard_slots = [s for s in proj.data.slots if s.bone.startswith("fx_cascade_pop_s0_")]
    assert all(s.blend == "normal" for s in shard_slots)


def test_shards_tile_the_symbol_and_the_symbol_hides_as_they_appear(proj):
    res = R.apply(proj, "cascade_pop", count=8, options=dict(puff=False, hit=False))
    sk = proj.data
    a = sk.animations["fx_cascade_pop"]
    sym = [s for s in res["slots"] if sk.slot(s).bone == "fx_cascade_pop_sym0"][0]
    offs = [k for k in a.slots[sym]["attachment"] if k.name is None]
    assert offs[-1].time == pytest.approx(0.14)
    shard_slots = [s for s in res["slots"] if sk.slot(s).bone.startswith("fx_cascade_pop_s0_")]
    assert 6 <= len(shard_slots) <= 8
    for s in shard_slots:
        on = [k.time for k in a.slots[s]["attachment"] if k.name == "fx"]
        assert on == [pytest.approx(0.14)]
    xs = [sk.bone(sk.slot(s).bone).x for s in shard_slots]
    assert min(xs) < -20 and max(xs) > 20, "the shards sit where they were in the picture"


def test_symbols_above_drop_through_carriers_with_exact_restitution_hops(grid):
    sk = grid.data
    before = {n: (w.x, w.y) for n, w in sk.world().items()}
    AnimBuilder(sk, "win", replace=False).bone("top1", "rotate", [(0, 0), (0.5, 9)])         # the artist's own key
    e, d, g = 0.3, 150.0, 2600.0
    res = R.apply(grid, "cascade_pop", y=40, parent="grid", into="win",
                  options=dict(cells=CELLS, drop=[["top0", d], ["top1", d], ["top2", d, 150]], restitution=e, gravity=g,
                               squash=0.16, delay=0.12, drop_stagger=0.035))
    assert res["carriers"] == ["fx_drop_top0", "fx_drop_top1", "fx_drop_top2"]
    w = sk.world()
    assert (w["top1"].x, w["top1"].y) == pytest.approx(before["top1"]), "inserting the carrier moves nothing"
    assert (w["fx_drop_top1"].x, w["fx_drop_top1"].y) == pytest.approx((0, 190 - 75)), "it pivots on the symbol's base"
    a = sk.animations["win"]
    assert [k.time for k in a.bones["top1"]["rotate"]] == [0, 0.5], "the artist's keys are untouched"
    tf = math.sqrt(2 * d / g)
    t0 = 0.24 + 0.12
    for i in range(3):
        car = f"fx_drop_top{i}"
        t, x, y = _xy(a.bones[car]["translate"], 0.0)
        assert y[0] == 0 and t[0] == pytest.approx(t0 + 0.035 * i)
        land = t0 + 0.035 * i + tf
        assert res["lands"][i] == pytest.approx(land, abs=1e-3)
        after = t > land + 1e-3
        assert y[after].max() + d == pytest.approx(e * e * d, abs=0.1), "the first hop is exactly e^2 of the drop"
        assert y[-1] == pytest.approx(-d) and np.all(y >= -d - 1e-6), "it lands on the symbol below and stays there"
        _, sx, sy = _xy(a.bones[car]["scale"], 1.0)
        assert sy.min() == pytest.approx(1 - 0.16, abs=0.01), "squashed onto the symbol below"
        assert np.allclose(sx * sy, 1, atol=1e-3), "area preserving"
        assert (sx[-1], sy[-1]) == (1, 1)
    lands = [e_.time for e_ in a.events if e_.name == "fx_cascade_land"]
    assert lands == pytest.approx(res["lands"])
    assert qa.validate(sk)["ok"]


def test_cascade_pop_cuts_the_users_symbol_art(proj, tmp_path):
    png = tmp_path / "seven.png"
    im = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([20, 20, 180, 140], fill=(255, 190, 40, 255))
    im.save(png)
    res = R.apply(proj, "cascade_pop", count=6, options=dict(puff=False, hit=False), art={"symbol": str(png)})
    assert res["art"]["symbol"].startswith("fx/art_cascade_pop_symbol")
    sk = proj.data
    sym = [s for s in res["slots"] if sk.slot(s).bone == "fx_cascade_pop_sym0"][0]
    att = sk.skin("default").attachments[sym]["fx"]
    assert att.width == pytest.approx(135) and att.height == pytest.approx(108), "keeps the art's aspect inside the cell"
    shards = [s for s in res["slots"] if "shard" in (sk.skin("default").attachments[s]["fx"].path or "")]
    assert len(shards) >= 4 and all("art_cascade_pop_symbol" in sk.skin("default").attachments[s]["fx"].path for s in shards)


def test_cascade_pop_retimes_as_a_one_shot(proj):
    res = R.apply(proj, "cascade_pop", duration=2.6, options=dict(puff=False, hit=False))
    assert res["breaks"] == [pytest.approx(0.28)]


def test_cascade_pop_bad_inputs_are_clear_errors(grid):
    with pytest.raises(ValueError, match="no bone"):
        R.apply(grid, "cascade_pop", options=dict(drop=[["nope", 150]]))
    with pytest.raises(ValueError, match="distance"):
        R.apply(grid, "cascade_pop", options=dict(drop=[["top0", -5]]))
    with pytest.raises(ValueError, match="cell"):
        R.apply(grid, "cascade_pop", options=dict(cells=[[0, 0, 150]]))
    with pytest.raises(ValueError, match="restitution"):
        R.apply(grid, "cascade_pop", options=dict(restitution=1.0))
    with pytest.raises(ValueError, match="root"):
        R.apply(grid, "cascade_pop", options=dict(drop=[["root", 100]]))


@needs_node
def test_payouts_play_in_the_spine_core_runtime(grid):
    R.apply(grid, "cascade_pop", y=40, parent="grid", into="win",
            options=dict(cells=CELLS, drop=[["top0", 150], ["top1", 150], ["top2", 150]]))
    R.apply(grid, "coin_fountain", y=-200, into="coins", count=12)
    R.apply(grid, "coin_fountain", y=-200, into="rain", count=8, options=dict(mode="shower", height=420))
    assert qa.validate(grid.data)["ok"]
    grid.save()
    dump = runtime.run(grid, animations=["win", "coins", "rain"], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"]["coins"]["duration"] == pytest.approx(3.8, abs=0.01)
    assert dump["animations"]["win"]["duration"] > 1.0
