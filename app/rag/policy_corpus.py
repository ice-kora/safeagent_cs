from app.rag.rag_models import PolicyDocument


POLICY_DOCUMENTS = [
    {
        "source_id": "policy_return_7d",
        "title": "七天无理由退货政策",
        "content": (
            "平台支持符合条件的七天无理由退货。商品需保持完好、附件齐全、"
            "不影响二次销售。部分定制类、鲜活易腐类和已拆封影响安全卫生的商品"
            "不适用七天无理由退货。"
        ),
    },
    {
        "source_id": "policy_refund_sla",
        "title": "退款处理时效",
        "content": (
            "退款申请提交后会先进入售后审核。审核通过后，退款通常会在 1 到 3 个"
            "工作日内原路退回；不同支付渠道到账时间可能略有差异。P0 系统不会自动"
            "执行真实退款。"
        ),
    },
    {
        "source_id": "policy_invoice",
        "title": "发票开具规则",
        "content": (
            "用户可以在订单完成后申请开具发票。开票需要提供准确的发票抬头、"
            "纳税人识别号和接收方式。发票申请可能需要人工或后续系统流程处理。"
        ),
    },
    {
        "source_id": "policy_address_change",
        "title": "地址修改规则",
        "content": (
            "订单未发货前，可以申请修改收货地址，但属于中风险操作，需要用户二次确认。"
            "订单发货后通常不能直接修改地址，需要联系人工客服评估物流拦截或转寄方案。"
        ),
    },
    {
        "source_id": "policy_shipped_address_change",
        "title": "订单发货后地址修改说明",
        "content": (
            "订单发货后，收货地址通常不能由系统直接修改。用户可以联系人工客服，"
            "由客服根据物流状态评估是否可以拦截、改派或转寄。"
        ),
    },
    {
        "source_id": "policy_after_sales_human",
        "title": "售后人工处理规则",
        "content": (
            "涉及退款、投诉、争议处理、异常物流或高风险订单变更的售后请求，通常需要"
            "转人工处理。系统可以提供政策说明，但不能自动完成高风险业务动作。"
        ),
    },
    {
        "source_id": "policy_member_benefits",
        "title": "会员权益说明",
        "content": (
            "会员用户可享受部分商品优惠、专属活动提醒和优先客服通道。具体权益以"
            "会员等级和活动规则为准。"
        ),
    },
    {
        "source_id": "policy_logistics_query",
        "title": "物流查询说明",
        "content": (
            "用户可以通过订单详情查看物流进度。订单发货后会展示物流公司和运单进度；"
            "如果物流长时间没有更新，建议联系人工客服协助核查。"
        ),
    },
]


def load_policy_documents() -> list[PolicyDocument]:
    """加载本地政策语料。"""
    return [
        PolicyDocument(
            source_id=item["source_id"],
            title=item["title"],
            content=item["content"],
        )
        for item in POLICY_DOCUMENTS
    ]
