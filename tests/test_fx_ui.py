"""UI and symbol polish: button_press, idle_shimmer, focus_glow, padlock, popup (module fx_ui)."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_recipes as R, fx_ui, qa, runtime
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node

CASES = [("button_press", {}), ("idle_shimmer", {}), ("focus_glow", {}), ("focus_glow", {"phase": "enter"}),
         ("focus_glow", {"phase": "exit"}), ("padlock", {}), ("padlock", {"mode": "lock"}), ("padlock", {"mode": "break"}),
         ("popup", {}), ("popup", {"phase": "out"})]
IDS = [n + ("-" + "-".join(map(str, o.values())) if o else "") for n, o in CASES]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def ui(tmp_path):
    """A screen bone with a button bone and a panel bone, each with a region slot of art, and a symbol slot."""
    p = Project(tmp_path / "ui.json", new_skeleton("ui", 720, 720))
    sk = p.data
    sk.bones.append(Bone(name="screen", parent="root"))
    sk.bones.append(Bone(name="btn", parent="screen", x=40, y=-100))
    sk.bones.append(Bone(name="panel", parent="screen", x=0, y=120))
    sk.bones.append(Bone(name="sym", parent="screen", x=-200, y=0, rotation=10))
    for name, bone, w, h in (("btn", "btn", 200, 80), ("panel", "panel", 300, 160), ("sym", "sym", 140, 140)):
        p.write_image(name, Image.new("RGBA", (w, h), (200, 60, 60, 255)))
        sk.add_slot(Slot(name=name, bone=bone, attachment=name))
        sk.set_attachment(name, name, RegionAttachment(path=name, width=w, height=h))
    return p


def _xy(keys, rest):
    t = np.array([k.time for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _val(keys, rest=0.0):
    return np.array([k.time for k in keys]), np.array([rest if k.value is None else float(k.value) for k in keys])


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _events(proj, anim, name):
    return [e.time for e in proj.data.animations[anim].events if e.name == name]


# ---------------------------------------------------------------- every recipe
@pytest.mark.parametrize("name,opts", CASES, ids=IDS)
def test_builds_validates_hides_and_orders_blends(proj, name, opts):
    res = R.apply(proj, name, options=opts)
    assert res["animation"] == f"fx_{name}" and res["event"] == f"fx_{name}" and res["slots"]
    sk = proj.data
    assert all(s.attachment is None for s in sk.slots), "FX slots must be hidden in the setup pose"
    blends = [sk.slot(s).blend for s in res["slots"]]
    assert set(blends) <= {"additive", "normal"}
    if "normal" in blends:
        assert R.RECIPES[name].get("normal_blend")
        assert blends == sorted(blends, key=lambda b: b != "normal"), "normal-blend layers lead the run"
    assert [s.name for s in sk.slots] == res["slots"], "one contiguous run, in creation order"
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    assert qa.budget(sk, "desktop")["metrics"]["draw_calls"] <= 3


@needs_node
@pytest.mark.parametrize("name,opts", CASES, ids=IDS)
def test_plays_in_the_spine_core_runtime(proj, name, opts):
    res = R.apply(proj, name, options=opts)
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"][res["animation"]]["frames"]
    assert dump["animations"][res["animation"]]["duration"] == pytest.approx(res["duration"], abs=0.02)


def test_registry_lists_options_roles_and_tiers():
    lst = R.list_recipes()
    for n in ("button_press", "idle_shimmer", "focus_glow", "padlock", "popup"):
        assert n in lst and lst[n]["art_roles"]
    assert "shine_rays" in lst["popup"]["art_roles"] and "puff_ring" in lst["popup"]["art_roles"]
    assert set(R.RECIPES["popup"]["tiers"]) == {"small", "big", "mega", "epic"}
    assert all(set(t) <= set(R.RECIPES["popup"]["options"]) for t in R.RECIPES["popup"]["tiers"].values())


# ---------------------------------------------------------------- spring maths
@pytest.mark.parametrize("os_,hz", [(0.05, 2.0), (0.14, 3.2), (0.45, 6.0), (0.8, 9.0)])
def test_step_spring_overshoots_exactly(os_, hz):
    f, tp = fx_ui._step(os_, hz)
    ts = np.linspace(0, 4 * tp, 4001)
    v = np.array([f(t) for t in ts])
    assert v.max() == pytest.approx(1 + os_, abs=1e-6) and ts[np.argmax(v)] == pytest.approx(tp, abs=tp / 1000)
    assert f(0) == 0 and f(40 * tp) == pytest.approx(1, abs=1e-3)
    s = fx_ui._settled(f, tp, 3 * tp)
    assert s(3 * tp) == pytest.approx(1, abs=1e-12) and s(tp) == pytest.approx(1 + os_)


def test_breath_curve_is_exactly_periodic_and_spans_0_to_1():
    assert fx_ui.breath(0) == pytest.approx(0, abs=1e-12) and fx_ui.breath(1) == pytest.approx(0, abs=1e-12)
    assert fx_ui.breath(0.5) == pytest.approx(1)
    x = np.linspace(0, 1, 2001)
    b = np.array([fx_ui.breath(q) for q in x])
    assert np.all(b >= -1e-12) and np.all(b <= 1 + 1e-12)
    # exp(sin): the bright half is shorter than the dim half (it lingers dim, peaks briefly)
    assert np.mean(b > 0.5) < 0.42


# ---------------------------------------------------------------- button_press
def test_button_press_squash_is_volume_preserving_and_springs_back_with_exact_overshoot(proj):
    res = R.apply(proj, "button_press", options=dict(depth=0.2, overshoot=0.4, press=0.08, hold=0.05))
    t, sx, sy = _xy(proj.data.animations["fx_button_press"].bones[res["button_bone"]]["scale"], 1.0)
    assert np.allclose(sx * sx * sy, 1, atol=4e-3), "squash keeps volume: sx^2 * sy = 1"
    assert sy.min() == pytest.approx(0.8, abs=1e-3)
    assert np.all(np.abs(sy[(t >= 0.08) & (t <= 0.13)] - 0.8) < 1e-3), "held at the bottom"
    assert sy.max() == pytest.approx(1 + 0.2 * 0.4, abs=1.5e-3), "overshoot is exactly 40% of the depth"
    assert t[np.argmax(sy)] == pytest.approx(res["peak_at"], abs=0.006)
    v = np.diff(sy[t <= 0.08]) / np.diff(t[t <= 0.08])
    assert v[0] < 1.5 * v[-1] - 0.5 and abs(v[-1]) < 0.25 * abs(v[0]), "press decelerates into the bottom (quarter SHM)"
    assert (sx[-1], sy[-1]) == (1, 1) and t[-1] == pytest.approx(res["duration"])
    assert _events(proj, "fx_button_press", "fx_button_down") == [0.0]
    assert _events(proj, "fx_button_press", "fx_button_up") == [pytest.approx(0.13)]


def test_button_ripple_spreads_like_sqrt_t_and_fades_as_one_over_perimeter(proj):
    res = R.apply(proj, "button_press", options=dict(width=200, height=80, ripple_size=40, shine=False))
    a = proj.data.animations["fx_button_press"]
    ring = res["ripple_slot"]
    tr_ = next(b for b in a.bones if b.endswith("ring_tr"))
    t, x, y = _xy(a.bones[tr_]["translate"], 0.0)
    q = t - t[0]
    r_ = x
    assert np.allclose(x, y) and r_[0] == 0 and r_[-1] == pytest.approx(40, abs=0.01)
    i1, i4 = np.argmin(np.abs(q - 0.05)), np.argmin(np.abs(q - 0.2))
    assert r_[i4] / r_[i1] == pytest.approx(math.sqrt(q[i4] / q[i1]), rel=1e-3), "front ~ sqrt(t)"
    ta, al = _alpha(a.slots[ring]["rgba"])
    mid = (ta - t[0] > 0.03) & (ta - t[0] < 0.24)
    P0 = 2 * (200 + 80)
    energy = al[mid] * (P0 + 2 * math.pi * np.interp(ta[mid], t, r_))
    assert energy.std() / energy.mean() < 0.01, "ring brightness x perimeter is constant (energy shared along the front)"
    assert al[0] == 0 and al[-1] == 0


def test_button_carrier_leaves_the_artists_keys_and_presses_multiply(ui):
    sk = ui.data
    before = {n: (w.x, w.y) for n, w in sk.world().items()}
    AnimBuilder(sk, "idle", replace=False).bone("btn", "rotate", [(0, 0), (0.4, 5)])
    r1 = R.apply(ui, "button_press", parent="screen", x=40, y=-100, into="idle", front_of="btn",
                 options=dict(button="btn", width=200, height=80))
    car = r1["button_bone"]
    assert r1["carrier"] and sk.bone("btn").parent == car and sk.bone(car).parent == "screen"
    w = sk.world()
    assert (w["btn"].x, w["btn"].y) == pytest.approx(before["btn"]), "inserting the carrier moves nothing"
    assert (w[car].x, w[car].y) == pytest.approx((40, -140)), "pivot at the button's base"
    assert [k.time for k in sk.animations["idle"].bones["btn"]["rotate"]] == [0, 0.4]
    r2 = R.apply(ui, "button_press", parent="screen", x=40, y=-100, into="idle", start=1.0, front_of=r1["slots"][-1],
                 options=dict(button="btn", width=200, height=80))
    assert r2["button_bone"] == car, "the second press drives the same carrier"
    t, _, sy = _xy(sk.animations["idle"].bones[car]["scale"], 1.0)
    assert np.interp(0.13, t, sy) == pytest.approx(0.86, abs=2e-3) and np.interp(1.13, t, sy) == pytest.approx(0.86, abs=2e-3)
    assert qa.validate(sk)["ok"]


def test_button_bad_inputs_are_clear_errors(ui):
    for opts, msg in ((dict(depth=0.8), "depth"), (dict(overshoot=1.2), "overshoot"), (dict(pivot="top"), "pivot"),
                      (dict(button="nope"), "no bone"), (dict(width=-5), "width"), (dict(bounce=0), "Hz")):
        with pytest.raises(ValueError, match=msg):
            R.apply(ui, "button_press", options=opts)


# ---------------------------------------------------------------- idle_shimmer
def test_shimmer_band_moves_as_r_sin_phi_and_the_glint_fires_where_it_crosses_the_hotspot(proj):
    res = R.apply(proj, "idle_shimmer", options=dict(width=200, height=160, angle=25, hotspot=[-0.2, 0.22], sweep=0.6, lead=0.25))
    a = proj.data.animations["fx_idle_shimmer"]
    b = proj.data.slot(res["band_slot"]).bone
    t, x, y = _xy(a.bones[b]["translate"], 0.0)
    d = np.array([math.cos(math.radians(-25)), math.sin(math.radians(-25))])
    s = x * d[0] + y * d[1]
    assert np.allclose(x * d[1] - y * d[0], 0, atol=0.02), "travels perpendicular to the band"
    L = s[-1]
    assert s[0] == pytest.approx(-L) and L > 0 and t[0] == 0 and t[-1] == pytest.approx(2.4), "left -> right, keyed over the whole loop"
    phi = -math.pi / 2 + math.pi * np.clip((t - 0.25) / 0.6, 0, 1)            # rests at the rims outside the sweep
    assert np.allclose(s, L * np.sin(phi), atol=0.1), "R sin(phi) (times are rounded to 0.1 ms)"
    sw = (t >= 0.25) & (t <= 0.85)
    v = np.abs(np.diff(s[sw]) / np.diff(t[sw]))
    assert v[len(v) // 2] > 5 * v[0] and v[len(v) // 2] > 5 * v[-1], "fast over the middle, lingering at the rims"
    hot = np.array([-0.2 * 200, 0.22 * 160]) @ d
    tg = _events(proj, "fx_idle_shimmer", "fx_shimmer_glint")
    assert tg == [pytest.approx(res["glint_at"])]
    assert np.interp(tg[0], t, s) == pytest.approx(hot, abs=0.6), "the glint fires when the band is on the hotspot"
    ta, al = _alpha(a.slots[res["band_slot"]]["rgba"])
    assert al[0] == 0 and al[-1] == 0 and ta[np.argmax(al)] == pytest.approx(tg[0], abs=0.03), "brightest on the hotspot"


def test_shimmer_loops_exactly_with_a_rest_gap_and_clips_to_its_box(proj):
    res = R.apply(proj, "idle_shimmer", duration=3.0, options=dict(width=180, height=180, corner=30))
    sk = proj.data
    a = sk.animations["fx_idle_shimmer"]
    assert res["loop"] == 3.0 and res["duration"] == 3.0
    clip = sk.attachment(res["clip_slot"], "fx")
    assert clip.type == "clipping" and clip.end == res["band_slot"] and clip.vertexCount <= 32
    vs = np.array(clip.vertices).reshape(-1, 2)
    assert vs[:, 0].max() == pytest.approx(90) and vs[:, 1].min() == pytest.approx(-90)
    for s in res["slots"]:
        if s in a.slots and "rgba" in a.slots[s]:
            _, al = _alpha(a.slots[s]["rgba"])
            assert al[0] == 0 and al[-1] == 0, f"{s}: dark at both ends of the loop"
        att = a.slots[s].get("attachment") if s in a.slots else None
        if att:
            assert att[0].name is None and att[-1].name is None and att[-1].time < 3.0 - 0.005
    sweep = res["sweep"]
    assert sweep[0] > 0.2 and sweep[1] < 1.0, "sweep, glint, then a long rest"
    with pytest.raises(ValueError, match="too short"):
        R.apply(proj, "idle_shimmer", options=dict(period=0.7))


def test_shimmer_clips_to_a_slots_own_outline(ui):
    res = R.apply(ui, "idle_shimmer", parent="screen", x=-200, into="sym_idle", options=dict(slot="sym", angle=20))
    sk = ui.data
    assert res["mode"] == "slot"
    names = [s.name for s in sk.slots]
    assert names[names.index("sym") + 1] == res["clip_slot"] and names[names.index("sym") + 2] == res["band_slot"]
    clip = sk.attachment(res["clip_slot"], "clip")
    assert clip.vertexCount == 4 and clip.end == res["band_slot"]
    assert sk.attachment(res["band_slot"], "fx").path == "fx/ui_sheen"
    bb = sk.bone(sk.slot(res["band_slot"]).bone)
    assert bb.parent == "sym" and bb.rotation == pytest.approx(70 - 10), "band leans 20 deg from vertical in the world"
    t, x, y = _xy(sk.animations["sym_idle"].bones[bb.name]["translate"], 0.0)
    ax = np.array([math.cos(math.radians(bb.rotation)), math.sin(math.radians(bb.rotation))])
    assert np.allclose(x * ax[0] + y * ax[1], 0, atol=0.02), "travel is across the band, not along it"
    assert not [e for e in sk.animations["sym_idle"].events if e.name == "fx_shine" and e.time < res["glint_at"] - 0.1]
    assert qa.validate(sk)["ok"]
    with pytest.raises(ValueError, match="no slot"):
        R.apply(ui, "idle_shimmer", options=dict(slot="nope"))


# ---------------------------------------------------------------- focus_glow
def _all_values(a, slots, bones):
    out = {}
    for s in slots:
        for tl, ks in a.slots.get(s, {}).items():
            if tl == "rgba":
                out[(s, tl)] = [k.color for k in ks]
    for b in bones:
        for tl, ks in a.bones.get(b, {}).items():
            out[(b, tl)] = [(getattr(k, "x", None), getattr(k, "y", None), getattr(k, "value", None)) for k in ks]
    return out


def test_focus_glow_breathes_on_the_led_curve_and_loops_exactly(proj):
    res = R.apply(proj, "focus_glow", duration=1.6, options=dict(depth=0.5))
    a = proj.data.animations["fx_focus_glow"]
    assert res["loop"] == 1.6
    vals = _all_values(a, res["slots"], list(a.bones))
    assert vals and all(v[0] == v[-1] for v in vals.values()), "first and last keys equal on every timeline"
    line = res["slots"][-1]
    t, al = _alpha(a.slots[line]["rgba"])
    want = np.array([0.5 + 0.5 * fx_ui.breath(q / 1.6) for q in t])
    assert np.allclose(al, want, atol=1 / 255 + 1e-6)
    assert al.min() == pytest.approx(0.5, abs=0.005) and t[np.argmax(al)] == pytest.approx(0.8, abs=0.03)
    assert len(res["corner_bones"]) == 4 and len(res["glow_corner_bones"]) == 4


def test_focus_enter_and_exit_hand_off_exactly_to_the_loop(tmp_path):
    def build(phase):
        p = Project(tmp_path / f"{phase}.json", new_skeleton("t", 720, 720))
        res = R.apply(p, "focus_glow", options=dict(phase=phase))
        return p.data.animations["fx_focus_glow"], res
    loop, rl = build("loop")
    enter, re_ = build("enter")
    exit_, rx = build("exit")
    for s in rl["slots"]:
        c_loop = loop.slots[s]["rgba"][0].color
        assert enter.slots[s]["rgba"][-1].color == c_loop, f"{s}: enter ends where the loop starts"
        assert exit_.slots[s]["rgba"][0].color == c_loop, f"{s}: exit starts where the loop starts"
        assert exit_.slots[s]["rgba"][-1].color.endswith("00"), "exit fades to exactly 0"
    grp = next(b for b in enter.bones if b.endswith("_focus"))
    t, sx, _ = _xy(enter.bones[grp]["scale"], 1.0)
    assert sx[0] > 1.05 and sx[-1] == 1 and np.all(np.diff(sx) <= 1e-9), "settles from outside, critically damped: no pop"
    line = rl["slots"][-1]
    ta, al = _alpha(enter.slots[line]["rgba"])
    assert al.max() == pytest.approx(1.0) and ta[np.argmax(al)] <= 0.031, "the enter flash attacks within 30 ms"
    assert re_["duration"] == pytest.approx(0.35) and rx["duration"] == pytest.approx(0.3)
    with pytest.raises(ValueError, match="phase"):
        R.apply(Project(tmp_path / "x.json", new_skeleton("t", 720, 720)), "focus_glow", options=dict(phase="hover"))


# ---------------------------------------------------------------- padlock
def test_unlock_shackle_springs_open_with_exact_overshoot_and_the_body_jiggles(proj):
    res = R.apply(proj, "padlock", options=dict(mode="unlock", open=40, overshoot=0.3, size=120))
    a = proj.data.animations["fx_padlock"]
    t, rot = _val(a.bones[res["shackle_bone"]]["rotate"])
    assert rot.max() == pytest.approx(40 * 1.3, abs=0.02), "swing overshoots exactly 30% past open"
    assert np.all(rot[t <= 0.35] == 0), "nothing moves before the release"
    assert rot[-1] == pytest.approx(40, abs=1e-3)
    _, _, ly = _xy(a.bones[res["shackle_bone"]]["translate"], 0.0)
    assert ly.max() == pytest.approx(0.2 * 120 * 1.22, abs=0.02) and ly[-1] == pytest.approx(24, abs=1e-3)
    tj, jr = _val(a.bones[res["body_bone"]]["rotate"])
    early = np.abs(jr[(tj > 0.3) & (tj < 0.45)]).max()
    late = np.abs(jr[(tj > 0.55) & (tj < 0.7)]).max()
    assert early > 4 and late < 0.3 * early and jr[-1] == 0
    rel = _events(proj, "fx_padlock", "fx_unlock")
    pop = _events(proj, "fx_padlock", "fx_lock_pop")
    assert rel == [pytest.approx(res["release_at"])] and pop == [pytest.approx(res["pop_at"])] and rel[0] < pop[0]
    for s in res["slots"][:2]:
        _, al = _alpha(a.slots[s]["rgba"])
        assert al[0] == 1 and al[-1] == 0, "the lock pops off"


def test_lock_drops_in_free_fall_and_bounces_with_restitution(proj):
    res = R.apply(proj, "padlock", options=dict(mode="lock", size=100))
    a = proj.data.animations["fx_padlock"]
    t, _, y = _xy(a.bones[res["shackle_bone"]]["translate"], 0.0)
    click = res["click_at"]
    assert _events(proj, "fx_padlock", "fx_lock") == [pytest.approx(click)]
    assert np.interp(click, t, y) == pytest.approx(0, abs=1e-3) and y[0] == pytest.approx(20)
    b1, b2 = res["bounces"]
    h1 = y[(t > b1) & (t < b2)].max()
    h2 = y[t > b2].max()
    assert h2 / h1 == pytest.approx(0.35 ** 2, rel=0.08), "each hop is e^2 the height of the last"
    _, rot = _val(a.bones[res["shackle_bone"]]["rotate"])
    assert rot[0] == pytest.approx(38) and rot[-1] == 0 and y[-1] == 0
    att = a.slots[res["slots"][0]]["attachment"]
    assert att[-1].name == "fx", "a locked padlock stays on screen"


def test_break_cracks_then_shards_fly_on_gravity_parabolas(proj):
    res = R.apply(proj, "padlock", count=8, options=dict(mode="break", size=120))
    a = proj.data.animations["fx_padlock"]
    crack, brk = _events(proj, "fx_padlock", "fx_lock_crack"), _events(proj, "fx_padlock", "fx_lock_break")
    assert crack[0] < brk[0] == pytest.approx(res["break_at"])
    shards = [s for s in res["slots"] if "_shard" in s]
    assert len(shards) == res["shards"] >= 5
    g = res["gravity"]
    for s in shards:
        att = a.slots[s]["attachment"]
        assert [k.name for k in att] == [None, "fx", None] and att[1].time == pytest.approx(brk[0])
        t, x, y = _xy(a.bones[proj.data.slot(s).bone]["translate"], 0.0)
        dt = np.diff(t)
        acc = np.diff(np.diff(y) / dt) / dt[1:]
        assert np.allclose(acc, -g, rtol=0.03), "constant downward acceleration"
        assert np.allclose(np.diff(np.diff(x) / dt), 0, atol=0.05), "no horizontal force"
    body = res["slots"][1]
    assert a.slots[body]["attachment"][-1].time == pytest.approx(brk[0]), "the body is replaced by its shards"
    with pytest.raises(ValueError, match="mode"):
        R.apply(proj, "padlock", options=dict(mode="smash"))


def test_padlock_art_body_is_what_shatters(proj, tmp_path):
    f = tmp_path / "box.png"
    Image.new("RGBA", (100, 80), (30, 200, 90, 255)).save(f)
    res = R.apply(proj, "padlock", options=dict(mode="break"), art={"body": {"path": str(f), "blend": "normal"}})
    assert res["art"]["body"] == "fx/art_padlock_body"
    shard = next(s for s in res["slots"] if "_shard" in s)
    im = proj.image(proj.data.attachment(shard, "fx").path)
    px = np.asarray(im)[..., :3][np.asarray(im)[..., 3] > 200]
    assert len(px) and np.all(px == [30, 200, 90])


# ---------------------------------------------------------------- popup
def test_popup_springs_in_with_exact_overshoot_and_a_volume_preserving_wobble(ui):
    res = R.apply(ui, "popup", parent="screen", y=120, start=0.5, into="toast", front_of="panel",
                  options=dict(panel="panel", width=300, height=160, overshoot=0.14, wobble=0.06, under="panel"))
    sk = ui.data
    car = res["panel_bone"]
    assert res["carrier"] and sk.bone("panel").parent == car
    t, sx, sy = _xy(sk.animations["toast"].bones[car]["scale"], 1.0)
    assert (t[0], sx[0], sy[0]) == (0, 0, 0), "hidden from the start of the clip until it pops"
    s = np.cbrt(sx * sx * sy)
    assert s.max() == pytest.approx(1.14, abs=2e-3) and t[np.argmax(s)] == pytest.approx(res["peak_at"], abs=0.006)
    big = sx > 0.05
    assert np.abs(sy[big] / sx[big] - 1).max() > 0.02, "the jelly wobble squashes and stretches"
    assert (sx[-1], sy[-1]) == (1, 1) and t[-1] == pytest.approx(0.5 + 0.9)
    assert _events(ui, "toast", "fx_popup_in") == [0.5]
    names = [s_.name for s_ in sk.slots]
    puff = [s_ for s_ in res["slots"] if "_puff_" in s_]
    shine = [s_ for s_ in res["slots"] if "_shine_" in s_]
    assert puff and shine
    assert all(names.index(p_) < names.index("panel") for p_ in puff), "under=: the puff ring passes behind the panel"
    assert all(names.index(s_) > names.index("panel") for s_ in shine), "the shine sparkles in front"
    assert "ae_hint" in res and "smoke" in res["ae_hint"]["note"]
    assert qa.validate(sk)["ok"]


def test_popup_out_anticipates_then_collapses_to_nothing(proj):
    res = R.apply(proj, "popup", options=dict(phase="out", anticipation=0.08, exit=0.3))
    t, sx, sy = _xy(proj.data.animations["fx_popup"].bones[res["panel_bone"]]["scale"], 1.0)
    assert sx.max() == pytest.approx(1.08, abs=1e-3) and np.allclose(sx, sy)
    i = np.argmax(sx)
    assert 0 < t[i] <= 0.1 and sx[-1] == 0 and t[-1] == pytest.approx(0.3)
    v = np.diff(sx) / np.diff(t)
    assert abs(v[i]) < 0.15 * abs(v[-1]), "zero speed at the turn, fastest as it vanishes (constant acceleration)"
    assert _events(proj, "fx_popup", "fx_popup_out") == [0.0] and res["gone_at"] == pytest.approx(0.3)


def test_popup_sub_recipe_art_is_prefixed(proj, tmp_path):
    f = tmp_path / "star.png"
    Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(f)
    res = R.apply(proj, "popup", art={"shine_rays": str(f)})
    assert res["art"] == {"shine_rays": "fx/art_shine_rays"}
    with pytest.raises(ValueError, match="art role"):
        R.apply(proj, "popup", art={"rays": str(f)})
    with pytest.raises(ValueError, match="phase"):
        R.apply(proj, "popup", options=dict(phase="sideways"))


@needs_node
def test_a_ui_clip_with_everything_plays_in_the_runtime(ui):
    R.apply(ui, "button_press", parent="screen", x=40, y=-100, into="ui", front_of="btn", options=dict(button="btn", width=200, height=80))
    R.apply(ui, "popup", parent="screen", y=120, start=0.4, into="ui", front_of="panel", options=dict(panel="panel", width=300, height=160))
    R.apply(ui, "idle_shimmer", parent="screen", x=-200, into="ui", options=dict(slot="sym"))
    R.apply(ui, "focus_glow", parent="screen", x=40, y=-100, start=1.0, into="ui", options=dict(phase="enter"))
    R.apply(ui, "padlock", parent="screen", x=200, start=0.2, into="ui", options=dict(mode="break"))
    assert qa.validate(ui.data)["ok"]
    ui.save()
    dump = runtime.run(ui, animations=["ui"], fps=20, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"]["ui"]["duration"] == pytest.approx(2.4, abs=0.02)
