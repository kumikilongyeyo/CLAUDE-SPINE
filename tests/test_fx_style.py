"""Global FX style director: profiles, depth manifests, relighting and art-direction QA."""
from __future__ import annotations

import asyncio
import json

import pytest

from claude_spine import fx_recipes as R, fx_style, qa
from claude_spine.ir import RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _hero(p: Project):
    p.data.add_slot(Slot(name="hero", bone="root", attachment="hero"))
    p.data.set_attachment("hero", "hero", RegionAttachment(path="hero", width=180, height=180))


def test_named_profiles_and_realism_mix():
    s = fx_style.resolve("stylized")
    p = fx_style.resolve("premium")
    r = fx_style.resolve("realistic")
    m = fx_style.resolve(realism=0.5)
    assert {s["name"], p["name"], r["name"]} == {"stylized", "premium", "realistic"}
    assert s["shared"]["time"] < p["shared"]["time"] < r["shared"]["time"]
    assert s["shared"]["intensity"] > p["shared"]["intensity"] > r["shared"]["intensity"]
    assert s["shared"]["time"] < m["shared"]["time"] < r["shared"]["time"]
    with pytest.raises(ValueError, match="unknown FX style"):
        fx_style.resolve("cinematic-ish")
    with pytest.raises(ValueError, match="0..1"):
        fx_style.resolve(realism=1.5)


def test_same_recipe_retimes_from_stylized_to_realistic(proj, tmp_path):
    a = R.apply(proj, "hit_burst", name="graphic", style="stylized")
    q = Project(tmp_path / "real.json", new_skeleton("real", 720, 720))
    b = R.apply(q, "hit_burst", name="physical", style="realistic")
    assert a["style"]["name"] == "stylized" and b["style"]["name"] == "realistic"
    assert a["duration"] < b["duration"]
    assert a["depth"] and set(a["depth_groups"]) == {"back", "subject", "front", "lens"}
    assert "front" in set(a["depth"].values())                     # flying motes
    assert qa.validate(proj.data)["ok"] and qa.validate(q.data)["ok"]


def test_explicit_recipe_options_win_over_style(proj):
    res = R.apply(proj, "light_beam", style="realistic", options={"sparks": 3, "wave": 1.7})
    assert res["sparks"] == 3                                     # style may not replace an explicit option
    # The explicit wave is not returned, but the style metadata proves the profile is still active.
    assert res["style"]["name"] == "realistic"


def test_capture_profile_from_reference_metrics():
    out = fx_style.capture({
        "realism": 0.8,
        "glow_spread": 0.3,
        "particle_density": 0.45,
        "motion_exaggeration": 0.25,
        "decay": 0.8,
        "saturation": 0.4,
    })
    p = out["profile"]
    assert out["realism_estimate"] == pytest.approx(0.8)
    assert p["name"] == "captured" and p["source_metrics"]["decay"] == pytest.approx(0.8)
    assert p["shared"]["time"] > 1.0
    with pytest.raises(ValueError, match="normalised"):
        fx_style.capture({"realism": 2})


def test_reactive_relight_uses_the_subject_art_and_keys_it(proj):
    _hero(proj)
    res = R.apply(proj, "hit_burst", style="premium", relight_slots=["hero"], relight_strength=0.6)
    light = res["relight"]
    assert light["source_slots"] == ["hero"] and light["strength"] == pytest.approx(0.6)
    twin = light["slots"][0]
    assert proj.data.slot(twin).attachment is None                 # hidden in setup
    a = proj.data.animations[res["animation"]]
    assert twin in a.slots and "attachment" in a.slots[twin] and "rgba" in a.slots[twin]
    assert a.slots[twin]["attachment"][-1].name is None
    assert qa.validate(proj.data)["ok"]


def test_premium_qa_rewards_integrated_light(proj, tmp_path):
    _hero(proj)
    R.apply(proj, "hit_burst", name="plain")
    plain = fx_style.qa_premium(proj, subject_slots=["hero"])

    q = Project(tmp_path / "lit.json", new_skeleton("lit", 720, 720))
    _hero(q)
    res = R.apply(q, "hit_burst", name="lit", style="premium", relight_slots=["hero"])
    lit = fx_style.qa_premium(q, res["animation"], subject_slots=["hero"])
    assert lit["score"] > plain["score"]
    assert lit["components"]["lighting_integration"] > plain["components"]["lighting_integration"]
    assert lit["reactive_light_slots"]


def test_mcp_style_and_qa_tools_are_registered_and_callable(tmp_path):
    from claude_spine.server import mcp

    async def call(name, **args):
        res = await mcp.call_tool(name, args)
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert {"fx_style_profile", "qa_fx_premium"} <= names

    listing = asyncio.run(call("fx_style_profile"))
    assert {"stylized", "premium", "realistic"} <= set(listing["profiles"])
    captured = asyncio.run(call("fx_style_profile", metrics={"realism": 0.7, "decay": 0.8}))
    assert captured["profile"]["name"] == "captured"

    p = Project(tmp_path / "mcp.json", new_skeleton("mcp", 720, 720))
    _hero(p)
    p.save()
    fx = asyncio.run(call("fx_recipe", project=str(p.path), recipe="hit_burst", style="premium",
                          relight_slots=["hero"]))
    assert fx["style"]["name"] == "premium" and fx["relight"]["slots"]
    qa_out = asyncio.run(call("qa_fx_premium", project=str(p.path), animation=fx["animation"],
                              subject_slots=["hero"]))
    assert qa_out["score"] >= 0
