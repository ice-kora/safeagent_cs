from app.tools.adapter import ToolExecutionContext, ToolRequest
from app.tools.real_adapters import HttpOrderAdapterStub, HttpTicketAdapterStub


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def test_real_order_adapter_stub_is_disabled_by_default() -> None:
    adapter = HttpOrderAdapterStub()

    result = adapter.execute(_request(adapter.name))

    assert result.success is False
    assert result.error_type == "REAL_ADAPTER_DISABLED"


def test_real_ticket_adapter_stub_refuses_missing_base_url() -> None:
    adapter = HttpTicketAdapterStub(enabled=True)

    result = adapter.execute(_request(adapter.name))

    assert result.success is False
    assert result.error_type == "REAL_ADAPTER_NOT_CONFIGURED"


def test_real_adapter_stub_uses_fake_client_without_real_network() -> None:
    client = FakeClient()
    adapter = HttpOrderAdapterStub(
        enabled=True,
        base_url="https://example.invalid",
        client=client,
    )

    result = adapter.execute(_request(adapter.name))

    assert result.success is True
    assert client.calls
    assert client.calls[0]["base_url"] == "https://example.invalid"
    assert client.calls[0]["payload"]["idempotency_key"] == "idem_001"


def _request(tool_name: str) -> ToolRequest:
    return ToolRequest(
        tool_name=tool_name,
        tool_args={"order_id": "O10086"},
        context=ToolExecutionContext(
            run_id="run_001",
            session_id="sess_001",
            user_id="u_1001",
            tenant_id="t_001",
            action_plan=None,
            tool_call_id="tc_001",
            idempotency_key="idem_001",
            action_fingerprint="af_001",
        ),
    )
