from dataclasses import dataclass
from enum import Enum

from app.core.action_plan import ActionPlan


class ValidationStatus(str, Enum):
    VALID = "VALID"
    PLAN_INVALID = "PLAN_INVALID"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    FORBIDDEN_ACTION = "FORBIDDEN_ACTION"


@dataclass
class ValidationResult:
    status: ValidationStatus
    reason: str

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID


class ActionPlanValidator:
    """校验候选 ActionPlan 的结构合法性。

    Validator 是 LLM / Planner 与 PolicyService 之间的第一道闸门。
    它只判断“计划是否像一个合法计划”，不判断“当前用户是否有权限做”。
    订单归属、tenant_id、业务状态和是否转人工都留给 PolicyService。
    """

    ALLOWED_ACTIONS = {
        "query_policy",
        "query_order",
        "change_address",
        "request_refund",
        "create_complaint_ticket",
        "security_risk",
        "unknown_action",
    }
    FORBIDDEN_ACTIONS = {
        "export_all_users",
        "modify_permission",
        "read_system_prompt",
    }
    ALLOWED_TARGET_TYPES = {
        "policy",
        "order",
        "ticket",
        "security",
    }
    ALLOWED_TOOLS = {
        "knowledge_tool.query_policy",
        "order_tool.query_order",
        "order_tool.change_address",
        "ticket_tool.create_ticket",
    }
    ACTION_TOOL_MAP = {
        "query_policy": "knowledge_tool.query_policy",
        "query_order": "order_tool.query_order",
        "change_address": "order_tool.change_address",
        "request_refund": "ticket_tool.create_ticket",
        "create_complaint_ticket": "ticket_tool.create_ticket",
        "security_risk": None,
        "unknown_action": None,
    }
    REQUIRED_TOOL_ARGS = {
        "query_policy": ("query",),
        "query_order": ("order_id",),
        "change_address": ("order_id",),
        "request_refund": ("ticket_type", "order_id", "description"),
        "create_complaint_ticket": ("ticket_type", "description"),
    }

    def validate(self, action_plan: ActionPlan) -> ValidationResult:
        """返回 ActionPlan 的结构校验结果。"""
        action = action_plan.action
        if action in self.FORBIDDEN_ACTIONS:
            return ValidationResult(
                ValidationStatus.FORBIDDEN_ACTION,
                f"危险动作不允许进入后续流程: {action}",
            )
        if action not in self.ALLOWED_ACTIONS:
            return ValidationResult(
                ValidationStatus.UNKNOWN_ACTION,
                f"未知动作: {action}",
            )

        target_type_result = self._validate_target_type(action_plan)
        if not target_type_result.is_valid:
            return target_type_result

        tool_result = self._validate_tool(action_plan)
        if not tool_result.is_valid:
            return tool_result

        args_result = self._validate_required_args(action_plan)
        if not args_result.is_valid:
            return args_result

        return ValidationResult(ValidationStatus.VALID, "ActionPlan 结构合法")

    def _validate_target_type(self, action_plan: ActionPlan) -> ValidationResult:
        if action_plan.action == "unknown_action":
            return ValidationResult(ValidationStatus.VALID, "unknown_action 不要求 target_type")
        if action_plan.target_type not in self.ALLOWED_TARGET_TYPES:
            return ValidationResult(
                ValidationStatus.PLAN_INVALID,
                f"非法 target_type: {action_plan.target_type}",
            )
        return ValidationResult(ValidationStatus.VALID, "target_type 合法")

    def _validate_tool(self, action_plan: ActionPlan) -> ValidationResult:
        expected_tool = self.ACTION_TOOL_MAP[action_plan.action]
        if expected_tool is None:
            if action_plan.tool_name is not None:
                return ValidationResult(
                    ValidationStatus.PLAN_INVALID,
                    f"{action_plan.action} 不应携带 tool_name",
                )
            return ValidationResult(ValidationStatus.VALID, "该动作不需要工具")

        if action_plan.tool_name not in self.ALLOWED_TOOLS:
            return ValidationResult(
                ValidationStatus.PLAN_INVALID,
                f"未知工具: {action_plan.tool_name}",
            )
        if action_plan.tool_name != expected_tool:
            return ValidationResult(
                ValidationStatus.PLAN_INVALID,
                f"action 与 tool_name 不匹配: {action_plan.action} -> {action_plan.tool_name}",
            )
        return ValidationResult(ValidationStatus.VALID, "tool_name 合法")

    def _validate_required_args(self, action_plan: ActionPlan) -> ValidationResult:
        required_args = self.REQUIRED_TOOL_ARGS.get(action_plan.action, ())
        for arg_name in required_args:
            value = action_plan.tool_args.get(arg_name)
            if value is None or value == "":
                return ValidationResult(
                    ValidationStatus.PLAN_INVALID,
                    f"缺少必要参数: {arg_name}",
                )
        return ValidationResult(ValidationStatus.VALID, "必要参数完整")
