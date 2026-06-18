from pathlib import Path

from app.core.constants import PolicyDecisionType
from app.core.security_context import (
    ActorRole,
    SecurityContext,
    build_customer_self_service_context,
)
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService


def test_security_context_allows_own_order(tmp_path: Path) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10086")
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.ALLOW


def test_security_context_denies_other_user_order(tmp_path: Path) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10087")
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.DENY
    assert "不属于当前用户" in decision.reason


def test_security_context_missing_tenant_still_denies(tmp_path: Path) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10086")
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id=None,
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.DENY
    assert "租户上下文缺失" in decision.reason


def test_customer_self_service_cannot_operate_other_subject_order(
    tmp_path: Path,
) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10086")
    context = SecurityContext(
        actor_id="u_1001",
        actor_role=ActorRole.CUSTOMER,
        subject_user_id="u_1002",
        tenant_id="t_001",
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.DENY
    assert "身份上下文不一致" in decision.reason


def test_security_context_mismatch_between_customer_and_subject_denies(
    tmp_path: Path,
) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10087")
    context = build_customer_self_service_context(
        user_id="u_1002",
        tenant_id="t_001",
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.DENY
    assert "身份上下文不一致" in decision.reason


def test_customer_service_actor_still_denied_in_self_service_phase(
    tmp_path: Path,
) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10086")
    context = SecurityContext(
        actor_id="agent_001",
        actor_role=ActorRole.CUSTOMER_SERVICE,
        subject_user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.DENY
    assert "客户本人自助操作" in decision.reason


def test_admin_actor_still_denied_in_self_service_phase(tmp_path: Path) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10086")
    context = SecurityContext(
        actor_id="admin_001",
        actor_role=ActorRole.ADMIN,
        subject_user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert decision.decision == PolicyDecisionType.DENY
    assert "客户本人自助操作" in decision.reason


def test_legacy_and_security_context_paths_match_for_allow(
    tmp_path: Path,
) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10086")
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    legacy_decision = service.evaluate(plan, customer_user_id="u_1001")
    context_decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert context_decision.to_dict() == legacy_decision.to_dict()


def test_legacy_and_security_context_paths_match_for_deny(
    tmp_path: Path,
) -> None:
    service = _policy_service(tmp_path)
    plan = _plan("order_query", "帮我查一下订单 O10087")
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    legacy_decision = service.evaluate(plan, customer_user_id="u_1001")
    context_decision = service.evaluate(
        plan,
        customer_user_id="u_1001",
        security_context=context,
    )

    assert context_decision.to_dict() == legacy_decision.to_dict()


def _policy_service(tmp_path: Path) -> PolicyService:
    repository = RepositoryService(db_path=tmp_path / "test.db")
    return PolicyService(repository=repository)


def _plan(intent: str, message: str):
    return RuleBasedActionPlanner().plan(intent=intent, message=message)
