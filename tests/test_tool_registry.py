from pathlib import Path

import pytest

from app.tools.registry import ToolRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_tool_registry_lists_supported_tools() -> None:
    registry = ToolRegistry()

    assert registry.list_tools() == [
        "knowledge_tool.query_policy",
        "order_tool.change_address",
        "order_tool.query_order",
        "ticket_tool.create_ticket",
    ]


def test_tool_registry_checks_tool_existence() -> None:
    registry = ToolRegistry()

    assert registry.has_tool("knowledge_tool.query_policy") is True
    assert registry.has_tool("unknown_tool.export_all_users") is False


def test_tool_registry_returns_handler_for_known_tool(tmp_path: Path) -> None:
    registry = ToolRegistry(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)
    handler = registry.get_handler("knowledge_tool.query_policy")

    result = handler({"query": "七天无理由"})

    assert result.success is True
    assert result.tool_name == "knowledge_tool.query_policy"
    assert result.data["sources"]


def test_tool_registry_raises_key_error_for_unknown_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.get_handler("unknown_tool.export_all_users")
