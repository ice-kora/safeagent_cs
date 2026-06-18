from dataclasses import dataclass
from enum import Enum


class ActorRole(str, Enum):
    """执行者角色枚举。

    v0.4B 只启用 customer self-service 映射；其他角色为后续客服后台、
    管理员和系统任务预留，不在本阶段扩展权限。
    """

    CUSTOMER = "customer"
    CUSTOMER_SERVICE = "customer_service"
    ADMIN = "admin"
    SYSTEM = "system"


@dataclass(frozen=True)
class SecurityContext:
    """一次策略裁决使用的安全身份上下文。"""

    actor_id: str
    actor_role: ActorRole
    subject_user_id: str
    tenant_id: str | None
    session_id: str | None = None

    def is_self_service(self) -> bool:
        return (
            self.actor_role == ActorRole.CUSTOMER
            and self.actor_id == self.subject_user_id
        )


def build_customer_self_service_context(
    *,
    user_id: str,
    tenant_id: str | None,
    session_id: str | None,
) -> SecurityContext:
    """把现有 customer user_id 映射为 v0.4B SecurityContext。

    当前外部 API 不变：请求里的 user_id 同时代表 actor 和 subject。
    """
    return SecurityContext(
        actor_id=user_id,
        actor_role=ActorRole.CUSTOMER,
        subject_user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
    )
