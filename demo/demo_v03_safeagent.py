from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.workflows.checkpoint_store import InMemoryCheckpointStore
from app.workflows.langgraph_chat_workflow import run_langgraph_chat_workflow
from app.workflows.langgraph_state_schema import state_to_json_safe_dict
from app.workflows.safeagent_state import SafeAgentWorkflowState
from app.workflows.safeagent_workflow import build_safeagent_workflow
from app.workflows.service_adapters import SafeAgentWorkflowServices


PROJECT_ROOT = Path(__file__).resolve().parent
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"
SESSION_ID = "sess_v03_demo_001"
USER_ID = "u_1001"
TENANT_ID = "t_001"


def run_demo(print_output: bool = True) -> list[dict[str, Any]]:
    """运行 SafeAgent-CS v0.3 本地演示。

    Demo 直接调用项目内 Workflow 与 service adapter，不启动 Web 服务、不接外部
    网络、不接真实 LLM，并使用临时 SQLite，避免污染生产数据。
    """
    results: list[dict[str, Any]] = []
    with TemporaryDirectory(
        prefix="safeagent_v03_demo_",
        ignore_cleanup_errors=True,
    ) as tmp_dir:
        tmp_path = Path(tmp_dir)
        services = _create_services(tmp_path)
        workflow = build_safeagent_workflow(services)
        try:
            for title, message in (
                ("1. policy_query 成功", "你们支持七天无理由退货吗？"),
                ("2. order_query 本人订单成功", "帮我查一下订单 O10086"),
                ("3. order_query 他人订单 DENY", "帮我查一下订单 O10087"),
                ("4. address_change CONFIRM_REQUIRED", "订单 O10086 的地址填错了，帮我改一下"),
                ("5. refund_request HUMAN_REQUIRED", "订单 O10086 我要退款"),
            ):
                state = workflow.run(
                    session_id=SESSION_ID,
                    user_id=USER_ID,
                    tenant_id=TENANT_ID,
                    message=message,
                )
                results.append(_state_result(title, "workflow-style", state))

            langgraph_state = run_langgraph_chat_workflow(
                session_id=SESSION_ID,
                user_id=USER_ID,
                tenant_id=TENANT_ID,
                message="帮我查一下订单 O10086",
                services=services,
            )
            results.append(
                _state_result(
                    "6. langgraph engine 运行一次",
                    "langgraph",
                    langgraph_state,
                )
            )

            snapshot = state_to_json_safe_dict(langgraph_state, route="ALLOW")
            results.append(
                {
                    "title": "7. checkpoint snapshot 生成",
                    "status": "CHECKPOINT_READY",
                    "run_id": snapshot["run_id"],
                    "schema_version": snapshot["schema_version"],
                    "action": (snapshot.get("action_plan") or {}).get("action"),
                    "message": "JSON-safe checkpoint snapshot 已生成",
                }
            )

            store = InMemoryCheckpointStore()
            record = store.save_state_checkpoint(
                state=langgraph_state,
                node_name="policy_node",
                route="ALLOW",
            )
            results.append(
                {
                    "title": "8. checkpoint store 保存",
                    "status": "CHECKPOINT_SAVED",
                    "run_id": record.run_id,
                    "checkpoint_id": record.checkpoint_id,
                    "message": "checkpoint 已保存到内存 store",
                }
            )

            policy_dry_run = store.dry_run_resume(
                checkpoint_id=record.checkpoint_id,
                next_node="policy_node",
            )
            results.append(
                {
                    "title": "9. resume dry-run 到 policy_node",
                    "status": "DRY_RUN_ALLOWED" if policy_dry_run.decision.allowed else "DRY_RUN_DENIED",
                    "run_id": record.run_id,
                    "checkpoint_id": record.checkpoint_id,
                    "next_node": "policy_node",
                    "allowed": policy_dry_run.decision.allowed,
                    "message": policy_dry_run.decision.reason,
                }
            )

            tool_dry_run = store.dry_run_resume(
                checkpoint_id=record.checkpoint_id,
                next_node="tool_gateway_node",
            )
            results.append(
                {
                    "title": "10. resume dry-run 到 tool_gateway_node 被拒绝",
                    "status": "DRY_RUN_ALLOWED" if tool_dry_run.decision.allowed else "DRY_RUN_DENIED",
                    "run_id": record.run_id,
                    "checkpoint_id": record.checkpoint_id,
                    "next_node": "tool_gateway_node",
                    "allowed": tool_dry_run.decision.allowed,
                    "message": tool_dry_run.decision.reason,
                }
            )
        finally:
            _close_logging_handlers(services)

    if print_output:
        _print_results(results)
    return results


def main() -> list[dict[str, Any]]:
    """命令行入口，返回结果便于测试复用。"""
    return run_demo(print_output=True)


def _create_services(tmp_path: Path) -> SafeAgentWorkflowServices:
    return SafeAgentWorkflowServices.create_default(
        db_path=tmp_path / "safeagent_v03_demo.db",
        mock_dir=MOCK_DIR,
        log_path=tmp_path / "application.log",
    )


def _close_logging_handlers(services: SafeAgentWorkflowServices) -> None:
    """释放 Demo 自己创建的临时日志文件句柄，便于 Windows 清理临时目录。"""
    logger = services.trace_service.logging_service.logger
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _state_result(
    title: str,
    engine: str,
    state: SafeAgentWorkflowState,
) -> dict[str, Any]:
    return {
        "title": title,
        "engine": engine,
        "status": state.final_status,
        "run_id": state.run_id,
        "pending_action_id": state.pending_action_id,
        "intent": state.intent_result,
        "action": state.action_plan.action if state.action_plan else None,
        "message": state.final_response,
    }


def _print_results(results: list[dict[str, Any]]) -> None:
    print("SafeAgent-CS v0.3 Demo")
    for result in results:
        print(f"\n=== {result['title']} ===")
        print(f"status: {result.get('status')}")
        print(f"run_id: {result.get('run_id')}")
        if result.get("pending_action_id"):
            print(f"pending_action_id: {result['pending_action_id']}")
        if result.get("checkpoint_id"):
            print(f"checkpoint_id: {result['checkpoint_id']}")
        if "allowed" in result:
            print(f"allowed: {result['allowed']}")
            print(f"next_node: {result.get('next_node')}")
        print(f"message: {result.get('message')}")


if __name__ == "__main__":
    main()
