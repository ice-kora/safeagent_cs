from app.core.action_plan import ActionPlan
from app.core.constants import PolicyDecisionType
from app.core.policy import PolicyDecision
from app.core.risk import RiskLevel
from app.core.security_context import SecurityContext
from app.services.policy_rules import PolicyEvaluationContext, PolicyRuleRegistry
from app.services.repository_service import RepositoryService


class PolicyService:
    """权限与风险裁决服务。

    PolicyService 是 ActionPlan 之后的可信边界：它可以读取只读权限上下文，
    判断当前用户能不能继续这个计划，但不能调用业务工具、修改订单或创建工单。

    P0 阶段是客户自助客服入口，customer_user_id 表示当前登录客户 ID，
    不是客服人员 ID。本阶段只做客户本人资源归属校验，防止 A 客户访问
    B 客户订单。

    身份语义：
    - customer_user_id：当前发起咨询的客户/买家 ID。
    - merchant_tenant_id：订单所属商家/租户 ID。
    - session_tenant_id：当前客服入口所属商家/租户 ID。
    - support_agent_id / actor_id / actor_role：客服后台操作身份，P0 不实现。

    v0.4C 起，具体 action 的裁决逻辑迁移到 PolicyRuleRegistry 和独立
    PolicyRule 中。PolicyService 保持入口职责，负责构造上下文和执行统一
    安全前置检查。
    """

    def __init__(
        self,
        repository: RepositoryService | None = None,
        rule_registry: PolicyRuleRegistry | None = None,
    ) -> None:
        self.repository = repository or RepositoryService()
        self.rule_registry = rule_registry or PolicyRuleRegistry()

    def evaluate(
        self,
        action_plan: ActionPlan,
        customer_user_id: str,
        security_context: SecurityContext | None = None,
    ) -> PolicyDecision:
        """对候选计划做真实权限与风险裁决。

        v0.4B 起内部支持 SecurityContext，但外部调用仍可只传
        customer_user_id。当前默认语义仍是客户自助入口。
        """
        security_guard = self._validate_security_context(
            customer_user_id,
            security_context,
        )
        if security_guard:
            return security_guard

        context = PolicyEvaluationContext(
            action_plan=action_plan,
            customer_user_id=customer_user_id,
            repository=self.repository,
            security_context=security_context,
        )
        return self.rule_registry.evaluate(context)

    def _validate_security_context(
        self,
        customer_user_id: str,
        security_context: SecurityContext | None,
    ) -> PolicyDecision | None:
        """校验执行身份上下文是否符合当前客户自助阶段边界。

        当前还没有客服后台代客操作模型，因此只接受客户本人自助上下文。
        这里先做统一前置拦截，避免单个 PolicyRule 误放行非自助身份。
        """
        if security_context is None:
            return None
        if security_context.subject_user_id != customer_user_id:
            return self._deny(RiskLevel.L5, "客户身份上下文不一致，拒绝执行")
        if not security_context.is_self_service():
            return self._deny(RiskLevel.L5, "当前仅支持客户本人自助操作，拒绝执行")
        return None

    @staticmethod
    def _deny(risk_level: RiskLevel, reason: str) -> PolicyDecision:
        return PolicyDecision(PolicyDecisionType.DENY, risk_level, reason)
