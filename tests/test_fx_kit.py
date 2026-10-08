"""kit="realistic": the bundled CC0 kit fills the art roles nobody supplied, by role name; the caller's art wins;
every recipe still builds with it; bundles pass it on; and the kit stays small, white (tintable) and licensed."""
import asyncio
import json

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_kit, fx_recipes as R, qa
from claude_spine.ir import new_skeleton
from claude_spine.project import Project

ALL = list(R.RECIPES)


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _paths(p):
    return {s.name: a.path for s in p.data.slots for a in p.data.skin().attachments.get(s.name, {}).values()}


# ---------------------------------------------------------------- the kit itself
def test_every_mapped_picture_exists():
    pics = set(fx_kit.pictures())
    used = {p for p, _ in fx_kit.ROLE_PICS.values()}
    used |= {v[0] for d in fx_kit.RECIPE_ROLES.values() for v in d.values() if v}
    assert used <= pics, sorted(used - pics)
    for p in used:
        assert fx_kit.path(p).exists()


def test_kit_is_small_licensed_and_has_no_library_pictures():
    files = list(fx_kit.KIT_DIR.glob("*.png"))
    assert sum(f.stat().st_size for f in files) < 6e6
    assert not [f.name for f in files if f.name.startswith("lib_") or f.name == "reticle.png"]
    lic = (fx_kit.KIT_DIR / "LICENSE-kenney.txt").read_text()
    assert "CC0" in lic and "Particle Pack" in lic and "Smoke" in lic
    credits = (fx_kit.KIT_DIR / "CREDITS.md").read_text()
    assert all(f.stem in credits or f.stem.rstrip("0123456789_") in credits for f in files)
    for f in files:
        im = Image.open(f)
        assert im.mode == "RGBA" and max(im.size) <= 512, f.name


def test_white_pictures_are_white_and_the_tuned_glow_is_tighter():
    for n in ("glow_s", "ring_s", "star_05", "smoke_07", "spark_01", "bolt_h5", "trace_01"):
        a = np.asarray(Image.open(fx_kit.path(n)), np.float32)
        vis = a[..., 3] > 8
        assert a[..., :3][vis].min() >= 250, n           # the slot colour tints it exactly
    g = np.asarray(Image.open(fx_kit.path("glow_s")), np.float32)[..., 3] / 255
    assert g.max() <= 0.76 and g.mean() < 0.2            # alpha^1.9 x 0.75: no haze when it is big
    assert np.asarray(Image.open(fx_kit.path("flash_s")))[..., :3].std() > 5   # painted puff keeps its colour


def test_orientation_variants():
    w, h = Image.open(fx_kit.path("trace_01")).size
    assert w > 3 * h                                     # light_streak: horizontal
    w, h = Image.open(fx_kit.path("bolt_h5")).size
    assert w > 2 * h                                     # link bolts lie along +x
    a = np.asarray(Image.open(fx_kit.path("trail_r")), np.float32)[..., 3]
    assert a[:, a.shape[1] // 2:].sum() > 1.5 * a[:, :a.shape[1] // 2].sum()   # comet head on the RIGHT
    a = np.asarray(Image.open(fx_kit.path("trail_up")), np.float32)[..., 3]
    assert a[:a.shape[0] // 2].sum() > 1.5 * a[a.shape[0] // 2:].sum()         # head at the TOP


# ---------------------------------------------------------------- filling roles
def test_kit_fills_roles_and_reports_them(proj):
    res = R.apply(proj, "hit_burst", kit="realistic")
    assert res["kit"] == {"name": "realistic", "roles": {"glow": "glow_s", "ring": "ring_s", "starburst": "star_09",
                                                         "core": "flare_01", "mote": "star_05"}}
    paths = set(_paths(proj).values())
    assert {"fx/kit_glow_s", "fx/kit_ring_s", "fx/kit_star_09", "fx/kit_flare_01", "fx/kit_star_05"} <= paths
    assert (proj.images_dir / "fx" / "kit_glow_s.png").exists()
    glow = next(a for s, a in _paths(proj).items() if a == "fx/kit_glow_s")
    att = proj.data.skin().attachments[[s for s, a in _paths(proj).items() if a == glow][0]]["fx"]
    assert att.width == pytest.approx(260 * 1.8 * 0.7, abs=0.01)     # the recipe's width x the kit scale


def test_user_art_wins_over_the_kit(proj, tmp_path):
    mine = tmp_path / "glow.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(mine)
    res = R.apply(proj, "hit_burst", kit="realistic", art={"glow": str(mine)})
    assert "glow" not in res["kit"]["roles"] and res["art"] == {"glow": "fx/art_hit_burst_glow"}
    assert "ring" in res["kit"]["roles"]


def test_game_art_and_9_slice_roles_stay_procedural(proj):
    res = R.apply(proj, "crosshair", kit="realistic")
    assert "reticle" not in res["kit"]["roles"] and res["kit"]["roles"]
    res = R.apply(proj, "cell_glow", kit="realistic")
    assert not {"frame", "fill"} & set(res["kit"]["roles"])
    assert fx_kit.pick("cascade_pop", "symbol") is None and fx_kit.pick("hold_respin", "ring") is None
    assert fx_kit.pick("rune_ring", "ring") == ("ring_floor", 1.0)
    assert fx_kit.pick("wild_merge", "cell_glow") == ("ring_s", 1.0)     # round, not a square cell


def test_no_kit_changes_nothing(proj, tmp_path):
    a = R.apply(proj, "explosion")
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 720))
    b = R.apply(q, "explosion", kit="none")
    assert "kit" not in a and "kit" not in b
    assert proj.data.to_dict() == q.data.to_dict()


def test_unknown_kit_is_a_clear_error(proj):
    with pytest.raises(ValueError, match="unknown kit 'photo'"):
        R.apply(proj, "shine", kit="photo")


def test_kit_pictures_by_name_in_art(proj):
    res = R.apply(proj, "shine", art={"glow": "kit:glow_s", "rays": {"path": "kit:star_08", "scale": 0.5}})
    assert res["art"] == {"glow": "fx/kit_glow_s", "rays": "fx/kit_star_08"}
    with pytest.raises(ValueError, match="no kit picture"):
        R.apply(proj, "shine", art={"glow": "kit:nope"})


@pytest.mark.parametrize("name", ALL)
def test_every_recipe_applies_with_the_kit(proj, name):
    res = R.apply(proj, name, kit="realistic")
    assert res["kit"]["name"] == "realistic"
    assert all(s.attachment is None for s in proj.data.slots)
    for role, pic in res["kit"]["roles"].items():
        assert pic in fx_kit.pictures(), (role, pic)
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]


# ---------------------------------------------------------------- bundles
def test_bundles_pass_the_kit_to_every_member(proj):
    R.apply(proj, "magic_reveal", kit="realistic")
    used = {p for p in _paths(proj).values() if p and p.startswith("fx/kit_")}
    assert {"fx/kit_ring_floor", "fx/kit_flare_01", "fx/kit_star_06", "fx/kit_star_05"} <= used
    n0 = len(used)
    steps = [{"recipe": "shine"}, {"recipe": "hit_burst", "start": 0.2, "kit": "none"}]
    q = R.apply(proj, "sequence", kit="realistic", options={"steps": steps}, name="seq")
    assert q["parts"] == ["shine", "hit_burst"]
    hb = [s for s in proj.data.slots if s.name.startswith("fx_hit_burst")]
    assert hb and not any(_paths(proj)[s.name].startswith("fx/kit_") for s in hb)
    assert n0 and not R._KIT                             # the stack is empty again


def test_burst_flare_ring_role_keeps_the_default(proj, tmp_path):
    R.apply(proj, "burst_flare")
    ring = next(s.name for s in proj.data.slots if "_ring" in s.name)
    assert proj.data.skin().attachments[ring]["fx"].path == "fx/ring"
    assert proj.data.skin().attachments[ring]["fx"].width == 420
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 720))
    res = R.apply(q, "burst_flare", kit="realistic")
    assert res["kit"]["roles"]["ring"] == "ring_s"
    ring = next(s.name for s in q.data.slots if "_ring" in s.name)
    assert q.data.skin().attachments[ring]["fx"].path == "fx/kit_ring_s"


# ---------------------------------------------------------------- the MCP tool
def test_the_tool_lists_kits_and_applies_one(tmp_path):
    from claude_spine.server import mcp

    def call(**args):
        res = asyncio.run(mcp.call_tool("fx_recipe", args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)
    assert "realistic" in call()["kits"]
    table = call(recipe="kit")["kit"]
    assert table["roles"]["glow"] == {"picture": "glow_s", "scale": 0.7}
    assert table["by_recipe"]["bolt_link"]["bolt"] == "bolt_h5" and "symbol" not in table["by_recipe"]["cascade_pop"]
    p = Project(tmp_path / "t.json", new_skeleton("t", 720, 720))
    p.save()
    out = call(project=str(p.path), recipe="bolt_link", kit="realistic")
    assert out["kit"]["roles"]["bolt"] == "bolt_h5" and "validation_errors" not in out
