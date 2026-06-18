from app.core.security_context import (
    ActorRole,
    SecurityContext,
    build_customer_self_service_context,
)


def test_build_customer_self_service_context_sets_actor_id() -> None:
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    assert context.actor_id == "u_1001"


def test_build_customer_self_service_context_defaults_role_to_customer() -> None:
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    assert context.actor_role == ActorRole.CUSTOMER


def test_build_customer_self_service_context_sets_subject_user_id() -> None:
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    assert context.subject_user_id == "u_1001"


def test_build_customer_self_service_context_keeps_tenant_and_session() -> None:
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    assert context.tenant_id == "t_001"
    assert context.session_id == "sess_001"


def test_self_service_context_returns_true() -> None:
    context = build_customer_self_service_context(
        user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    assert context.is_self_service() is True


def test_non_self_service_context_returns_false() -> None:
    context = SecurityContext(
        actor_id="agent_001",
        actor_role=ActorRole.CUSTOMER_SERVICE,
        subject_user_id="u_1001",
        tenant_id="t_001",
        session_id="sess_001",
    )

    assert context.is_self_service() is False
