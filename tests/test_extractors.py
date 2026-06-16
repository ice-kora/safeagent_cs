import pytest

from app.core.extractors import extract_order_id


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("O10086", "O10086"),
        ("o10086", "O10086"),
        ("订单 O10086", "O10086"),
        ("订单号：10086", "O10086"),
        ("订单编号 10086", "O10086"),
    ],
)
def test_extract_order_id_supported_formats(message: str, expected: str) -> None:
    assert extract_order_id(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "我有10086个问题",
        "hello world only has letter o",
    ],
)
def test_extract_order_id_does_not_match_unrelated_text(message: str) -> None:
    assert extract_order_id(message) is None
