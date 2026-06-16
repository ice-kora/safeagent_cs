from enum import Enum


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TraceStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    CLOSED = "CLOSED"


class PendingActionStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
