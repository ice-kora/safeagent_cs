import socket

import demo_v03_safeagent


def test_demo_v03_module_can_be_imported() -> None:
    assert callable(demo_v03_safeagent.run_demo)
    assert callable(demo_v03_safeagent.main)


def test_demo_v03_run_demo_returns_expected_scenarios() -> None:
    results = demo_v03_safeagent.run_demo(print_output=False)

    assert len(results) >= 10
    titles = {result["title"] for result in results}
    assert "1. policy_query 成功" in titles
    assert "6. langgraph engine 运行一次" in titles
    assert "10. resume dry-run 到 tool_gateway_node 被拒绝" in titles


def test_demo_v03_covers_main_statuses() -> None:
    results = demo_v03_safeagent.run_demo(print_output=False)
    statuses = {result["status"] for result in results}

    assert {"SUCCESS", "DENY", "CONFIRM_REQUIRED", "HUMAN_REQUIRED"}.issubset(statuses)


def test_demo_v03_checkpoint_dry_run_policy_node_allowed() -> None:
    results = demo_v03_safeagent.run_demo(print_output=False)
    policy_dry_run = _find_result(results, "9. resume dry-run 到 policy_node")

    assert policy_dry_run["allowed"] is True
    assert policy_dry_run["status"] == "DRY_RUN_ALLOWED"


def test_demo_v03_checkpoint_dry_run_tool_gateway_denied() -> None:
    results = demo_v03_safeagent.run_demo(print_output=False)
    tool_dry_run = _find_result(
        results,
        "10. resume dry-run 到 tool_gateway_node 被拒绝",
    )

    assert tool_dry_run["allowed"] is False
    assert tool_dry_run["status"] == "DRY_RUN_DENIED"


def test_demo_v03_main_prints_summary(capsys) -> None:
    results = demo_v03_safeagent.main()
    output = capsys.readouterr().out

    assert len(results) >= 10
    assert "SafeAgent-CS v0.3 Demo" in output
    assert "langgraph engine" in output
    assert "tool_gateway_node" in output


def test_demo_v03_does_not_require_external_network(monkeypatch) -> None:
    def fail_connect(*args, **kwargs):
        raise AssertionError("demo_v03_safeagent must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)

    results = demo_v03_safeagent.run_demo(print_output=False)

    assert len(results) >= 10


def _find_result(results: list[dict], title: str) -> dict:
    for result in results:
        if result["title"] == title:
            return result
    raise AssertionError(f"missing demo result: {title}")
