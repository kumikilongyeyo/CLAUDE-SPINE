from claude_spine.ae_material import material_plan
from claude_spine.project_clean import _dedupe
from claude_spine.timeline import keys

def test_cleaner_dedupes_interior_holds():
    ks = keys([(0,0),(0.1,0),(0.2,0),(0.3,10)], "rotate", "linear")
    out, removed = _dedupe(ks, "rotate")
    assert removed == 1
    assert [k.time for k in out] == [0, 0.2, 0.3]

def test_material_plan_has_three_texture_scales_and_light():
    p = material_plan("fire", 0.8)
    assert set(p["texture_frequency"]) == {"macro","mid","micro"}
    roles = [x["role"] for x in p["passes"]]
    assert "interaction_light" in roles
    assert "distortion" in roles

def test_secondary_source_keys_stay_sparse():
    ks = keys([(0,0),(0.1,12),(0.28,-4),(0.5,0)], "rotate", "sine_out")
    assert len(ks) == 4
    assert ks[0].curve is not None
