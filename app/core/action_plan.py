from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionPlan:
    """Agent 候选执行计划。

    ActionPlan 可以来自规则 Planner，也可以来自后续的 LLM Mode。
    它只表达“打算做什么”，不能被视为可信结果；后续必须经过
    ActionPlanValidator 和 PolicyService，才允许进入工具调用阶段。
    """

    # intent：用户输入的意图分类结果，例如 order_query / refund_request。
    intent: str
    # action：系统候选动作，后续会由 ActionPlanValidator 校验是否在白名单中。
    action: str
    # target_type：动作作用的资源类型，例如 order / policy / ticket。
    target_type: str | None = None
    # target_id：动作作用的资源 ID，例如订单号 O10086；缺失时留给 Validator 处理。
    target_id: str | None = None
    # tool_name：候选工具名称。这里不能直接调用工具，只是声明计划使用哪个工具。
    tool_name: str | None = None
    # tool_args：候选工具参数。参数仍不可信，后续需要校验和脱敏。
    tool_args: dict[str, Any] = field(default_factory=dict)
    # reason：Planner 生成该计划的原因，主要用于 Trace、日志和讲解。
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为可写入 Trace 或日志的普通字典。

        ActionPlan 本身不做权限判断，也不做脱敏；调用方写日志前仍应走
        LoggingService 或 TraceService 的脱敏流程。
        """
        return {
            "intent": self.intent,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "reason": self.reason,
        }
