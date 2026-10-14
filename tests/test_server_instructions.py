from claude_spine import server


def test_start_from_stored_rule_is_in_the_server_instructions():
    text = server.mcp.instructions or ""
    assert "never build an FX from zero" in text
    for tool in ("ae_template", "ae_library", "fx_recipe"):
        assert tool in text
