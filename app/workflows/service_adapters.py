from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.action_plan import ActionPlan
from app.core.action_plan_validator import ActionPlanValidator
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.logging_service import LoggingService
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService


@dataclass
class SafeAgentWorkflowServices:
    """Workflow 节点依赖的 service 集合。

    这里是薄 adapter，不重新实现任何业务规则。节点通过它复用现有
    Intent、Planner、Validator、PolicyService、ToolGateway 等服务。
    """

    trace_service: TraceService
    intent_classifier: RuleBasedIntentClassifier
    action_planner: RuleBasedActionPlanner
    action_plan_validator: ActionPlanValidator
    policy_service: PolicyService
    tool_gateway: ToolGateway
    failure_handler: FailureHandler
    pending_action_service: PendingActionService

    @classmethod
    def create_default(
        cls,
        db_path: str | Path | None = None,
        mock_dir: str | Path | None = None,
        log_path: str | Path | None = None,
    ) -> "SafeAgentWorkflowServices":
        repository = RepositoryService(mock_dir=mock_dir, db_path=db_path)
        return cls(
            trace_service=TraceService(
                db_path=db_path,
                logging_service=LoggingService(log_path=log_path),
            ),
            intent_classifier=RuleBasedIntentClassifier(),
            action_planner=RuleBasedActionPlanner(),
            action_plan_validator=ActionPlanValidator(),
            policy_service=PolicyService(repository=repository),
            tool_gateway=ToolGateway(db_path=db_path, mock_dir=mock_dir),
            failure_handler=FailureHandler(db_path=db_path),
            pending_action_service=PendingActionService(db_path=db_path),
        )


def build_workflow_tool_args(
    action_plan: ActionPlan,
    customer_user_id: str,
    risk_level: str,
    source_run_id: str,
) -> dict[str, Any]:
    """为 ToolGateway 补齐系统可信上下文。

    Planner 生成的 tool_args 只是候选参数。Workflow 与 /api/chat 一样，
    在进入 ToolGateway 前必须补充用户、动作、目标、风险和 source_run_id。
    """
    tool_args = dict(action_plan.tool_args)
    tool_args.update(
        {
            "user_id": customer_user_id,
            "customer_user_id": customer_user_id,
            "action": action_plan.action,
            "target_type": action_plan.target_type,
            "target_id": action_plan.target_id,
            "risk_level": risk_level,
            "source_run_id": source_run_id,
        }
    )
    return tool_args

