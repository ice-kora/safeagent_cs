import re


ORDER_ID_PATTERN = re.compile(r"\bO\d+\b", re.IGNORECASE)


class RuleBasedIntentClassifier:
    """规则型意图识别器。

    P0 的主链路需要稳定、可测试，所以这里先不用 LLM。
    该分类器只负责把用户文本归入有限 intent 集合，不做权限判断，
    也不决定后续动作是否允许执行。
    """

    SUPPORTED_INTENTS = {
        "policy_query",
        "order_query",
        "address_change",
        "refund_request",
        "complaint",
        "prompt_injection",
        "unknown",
    }

    def classify(self, message: str) -> str:
        """根据关键词识别意图。

        Prompt Injection 优先级最高，因为攻击文本可能伪装成普通查询。
        地址修改要先于订单查询判断，避免“订单地址填错了”被归为查订单。
        """
        text = self._normalize(message)
        if not text:
            return "unknown"

        if self._is_prompt_injection(text):
            return "prompt_injection"
        if self._is_policy_query(text):
            return "policy_query"
        if self._is_complaint(text):
            return "complaint"
        if self._is_refund_request(text):
            return "refund_request"
        if self._is_address_change(text):
            return "address_change"
        if self._is_order_query(text):
            return "order_query"
        return "unknown"

    @staticmethod
    def _normalize(message: str) -> str:
        return message.strip().lower()

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _is_prompt_injection(self, text: str) -> bool:
        attack_keywords = (
            "忽略之前",
            "忽略所有",
            "忽略规则",
            "你现在是管理员",
            "系统提示词",
            "system prompt",
            "导出所有用户",
            "所有用户手机号",
            "所有用户数据",
            "修改权限",
            "绕过",
        )
        return self._contains_any(text, attack_keywords)

    def _is_complaint(self, text: str) -> bool:
        return self._contains_any(text, ("投诉", "举报客服", "客服不处理"))

    def _is_refund_request(self, text: str) -> bool:
        if self._contains_any(text, ("退款政策", "退款规则", "退货政策")):
            return False
        return self._contains_any(text, ("我要退款", "申请退款", "退钱", "给我退款"))

    def _is_address_change(self, text: str) -> bool:
        has_address = self._contains_any(text, ("地址", "收货地址"))
        has_change = self._contains_any(text, ("改", "修改", "填错", "错了", "换"))
        return has_address and has_change

    def _is_order_query(self, text: str) -> bool:
        # 不能用单个字母 o 判断订单相关性；英文普通文本太容易误命中。
        has_order_id = ORDER_ID_PATTERN.search(text) is not None
        if has_order_id:
            return True

        has_order = "订单" in text
        has_query = self._contains_any(
            text,
            ("查", "查询", "状态", "物流", "发货", "到哪", "进度"),
        )
        return has_order and has_query

    def _is_policy_query(self, text: str) -> bool:
        return self._contains_any(
            text,
            (
                "七天无理由",
                "退货政策",
                "退款政策",
                "发票",
                "售后规则",
                "支持退货",
                "怎么退货",
                "规则",
                "政策",
                "说明",
                "订单查询规则",
                "订单规则",
                "投诉工单规则",
                "人工转接",
                "高风险操作",
                "无答案",
                "火星基地",
                "宠物医疗保险",
            ),
        )
