import asyncio
import json


def _call(name, **args):
    from claude_spine.server import mcp
    res = asyncio.run(mcp.call_tool(name, args))
    content = res[0] if isinstance(res, tuple) else res
    return json.loads(content[0].text)


def test_tools_are_registered_with_docs():
    from claude_spine.server import mcp
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    for n in ["rig_mesh", "rig_ik", "rig_physics", "rig_strand", "rig_turn", "juice_apply", "fx_generate",
              "qa_budget", "validate", "preview", "pack_atlas", "make_editable", "import_psd"]:
        assert n in names
    assert all(t.description for t in tools)


def test_tool_chain_on_a_sample(tmp_path):
    s = _call("make_sample", kind="symbol", out_dir=str(tmp_path / "g"))
    proj = s["project"]
    assert _call("rig_mesh", project=proj, slot="gem")["vertices"] > 10
    assert "win" in _call("juice_apply", project=proj, fx=True, shine_slot="gem")["clips"]
    assert _call("fx_generate", project=proj, preset="coin_burst", into="win")["animation"] == "win"
    assert _call("validate", project=proj, runtime_check=False)["ok"]
    b = _call("qa_budget", project=proj)
    assert "draw_calls" in b["metrics"]
    k = _call("add_keys", project=proj, animation="custom", bone="root", timeline="rotate",
              keys=[[0, 0], [0.5, 15, "back_out"], [1, 0]])
    assert k["duration"] == 1


def test_preview_and_pack_tools_write_files(tmp_path):
    from claude_spine import runtime
    import pytest
    if not runtime.available():
        pytest.skip("Node not installed")
    s = _call("make_sample", kind="symbol", out_dir=str(tmp_path / "g"))
    _call("juice_apply", project=s["project"], clips=["win"])
    pv = _call("preview", project=s["project"], animations=["win"], size=96)
    assert (tmp_path / "g" / "previews" / "setup.png").exists() and pv["win"]["gif"]
    pk = _call("pack_atlas", project=s["project"])
    assert (tmp_path / "g" / "export" / "gem.atlas").exists() and pk["json"].endswith("gem.json")
