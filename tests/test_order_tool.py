import json
import shutil
from pathlib import Path

from app.tools.order_tool import change_address, query_order


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_query_order_returns_safe_order_summary(tmp_path: Path) -> None:
    result = query_order(
        "O10086",
        mock_dir=MOCK_DIR,
        db_path=tmp_path / "test.db",
    )

    assert result.success is True
    assert result.tool_name == "order_tool.query_order"
    assert result.data == {
        "order_id": "O10086",
        "order_status": "PAID",
        "delivery_status": "PENDING_SHIPMENT",
        "refund_status": "NONE",
        "safe_summary": result.data["safe_summary"],
    }
    assert result.summary == result.data["safe_summary"]


def test_query_order_does_not_return_sensitive_fields(tmp_path: Path) -> None:
    result = query_order(
        "O10086",
        mock_dir=MOCK_DIR,
        db_path=tmp_path / "test.db",
    )

    result_json = json.dumps(result.to_dict(), ensure_ascii=False)

    assert "phone" not in result.data
    assert "address" not in result.data
    assert "payment_info" not in result.data
    assert "13800001234" not in result_json
    assert "Henan Zhengzhou Jinshui Road 100" not in result_json
    assert "card_123456" not in result_json


def test_change_address_does_not_modify_mock_orders_json(tmp_path: Path) -> None:
    mock_dir = tmp_path / "mock_platform"
    mock_dir.mkdir()
    shutil.copy(MOCK_DIR / "mock_orders.json", mock_dir / "mock_orders.json")
    before = (mock_dir / "mock_orders.json").read_text(encoding="utf-8")

    result = change_address(
        "O10086",
        new_address="Very Sensitive New Address 999",
        mock_dir=mock_dir,
        db_path=tmp_path / "test.db",
    )

    after = (mock_dir / "mock_orders.json").read_text(encoding="utf-8")
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)

    assert result.success is True
    assert before == after
    assert result.data["request_status"] == "RECEIVED"
    assert "Very Sensitive New Address 999" not in result_json
