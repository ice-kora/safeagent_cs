from app.core.tool_allowlist import ALLOWED_TOOL_NAMES, is_tool_allowed


def test_allowlist_contains_four_mock_tools() -> None:
    assert ALLOWED_TOOL_NAMES == {
        "knowledge_tool.query_policy",
        "order_tool.query_order",
        "order_tool.change_address",
        "ticket_tool.create_ticket",
    }


def test_is_tool_allowed_true_for_known_mock_tools() -> None:
    assert is_tool_allowed("knowledge_tool.query_policy") is True
    assert is_tool_allowed("ticket_tool.create_ticket") is True


def test_is_tool_allowed_false_for_unknown_tool() -> None:
    assert is_tool_allowed("unknown_tool.export_all_users") is False


def test_is_tool_allowed_false_for_external_stub_names() -> None:
    """外部 stub adapter 名不在默认白名单里，保证 fail-closed。"""
    assert is_tool_allowed("external_order_tool") is False
    assert is_tool_allowed("external_ticket_tool") is False
