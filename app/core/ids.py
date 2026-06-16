from uuid import uuid4


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def generate_request_id() -> str:
    return _generate_id("req")


def generate_run_id() -> str:
    return _generate_id("run")


def generate_trace_node_id() -> str:
    return _generate_id("tn")


def generate_pending_action_id() -> str:
    return _generate_id("pa")


def generate_ticket_id() -> str:
    return _generate_id("tk")
