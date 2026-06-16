import re


EXPLICIT_ORDER_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])O(?P<number>\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
ORDER_CONTEXT_PATTERN = re.compile(
    r"(?:订单号|订单编号|订单)\s*[:：]?\s*(?P<number>\d+)",
    re.IGNORECASE,
)


def extract_order_id(message: str) -> str | None:
    """提取并归一化 P0 Mock 订单号。

    P0 只支持很窄的规则，避免把任意数字误当成订单号：
    1. 显式 O + 数字，例如 O10086 / o10086；
    2. 数字紧跟在“订单、订单号、订单编号”之后。
    """
    explicit_match = EXPLICIT_ORDER_ID_PATTERN.search(message)
    if explicit_match:
        return f"O{explicit_match.group('number')}"

    context_match = ORDER_CONTEXT_PATTERN.search(message)
    if context_match:
        return f"O{context_match.group('number')}"

    return None
