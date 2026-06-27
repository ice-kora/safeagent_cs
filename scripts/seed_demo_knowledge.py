import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "docs" / "knowledge"


KNOWLEDGE_DOCS: dict[str, str] = {
    "policy_return_7d.md": """# 七天无理由退货政策

平台支持符合条件的七天无理由退货。商品需保持完好、附件齐全、不影响二次销售。

定制类、鲜活易腐类、已拆封后影响安全卫生的商品，以及明确标注不适用七天无理由的商品，不适用该规则。

客服只能解释退货政策和引导用户提交售后申请，不能绕过售后审核直接执行退款或改库存。
""",
    "policy_refund_sla.md": """# 退款处理时效

退款申请提交后会先进入售后审核。审核通过后，退款通常会在 1 到 3 个工作日内原路退回。

不同支付渠道的到账时间可能略有差异。银行卡、第三方支付、平台余额等渠道以支付平台实际处理时间为准。

SafeAgent-CS demo 不会自动执行真实退款。退款、赔付、撤销支付等高风险资金动作必须转人工或进入受控工具流程。
""",
    "policy_invoice.md": """# 发票开具规则

用户可以在订单完成后申请开具发票。开票需要提供准确的发票抬头、纳税人识别号和接收方式。

发票申请可能需要人工或后续系统流程处理。客服不得在公开对话中展示完整税号、完整手机号或其他敏感信息。
""",
    "policy_address_change.md": """# 地址修改规则

订单未发货前，可以申请修改收货地址，但属于中风险操作，需要用户二次确认。

系统应先校验订单归属、租户边界和订单状态，再通过 pending_action 记录等待用户确认。确认前不能调用地址修改工具。

地址展示必须脱敏，不能在 Console、日志或 RAG evidence 中展示完整手机号和完整地址。
""",
    "policy_shipped_address_change.md": """# 订单发货后地址修改说明

订单发货后，收货地址通常不能由系统直接修改。用户可以联系人工客服，由客服根据物流状态评估是否可以拦截、改派或转寄。

发货后的地址变更不应直接进入自动工具执行。涉及物流拦截、改派、转寄的场景建议转人工处理。
""",
    "policy_after_sales_human.md": """# 售后人工处理规则

涉及退款、投诉、争议处理、异常物流或高风险订单变更的售后请求，通常需要转人工处理。

系统可以提供政策说明和 evidence，但不能自动完成退款、赔付、强制取消、改权限等高风险业务动作。

RAG 不能参与 PolicyDecision，不能执行工具，只能返回 evidence。
""",
    "policy_member_benefits.md": """# 会员权益说明

会员用户可享受部分商品优惠、专属活动提醒和优先客服通道。

具体权益以会员等级和活动规则为准。客服不能承诺未在活动页或订单页展示的权益。
""",
    "policy_logistics_query.md": """# 物流查询说明

用户可以通过订单详情查看物流进度。订单发货后会展示物流公司和运单进度。

如果物流长时间没有更新，建议联系人工客服协助核查。系统不能伪造物流节点或承诺确定送达时间。
""",
    "policy_order_query.md": """# 订单查询规则

订单查询属于低风险只读操作，但必须校验用户身份、订单归属和 tenant_id。

如果订单不存在、用户与订单不匹配、租户不匹配，系统应拒绝返回订单详情，并给出安全的失败说明。

订单查询结果只展示必要状态信息，不展示完整手机号、完整地址、支付流水、银行卡号或内部风控字段。
""",
    "policy_after_sales_rules.md": """# 售后规则

售后请求包括退货、换货、维修、退款咨询和异常物流协查。

系统可以根据订单状态给出政策解释；涉及资金、争议、投诉、强制取消或异常补偿时，应转人工处理。
""",
    "policy_complaint_ticket.md": """# 投诉工单规则

投诉工单属于高风险人工处理场景。用户发起投诉时，系统可以创建或查询工单，但应遵循幂等规则，避免重复创建未关闭投诉。

同一用户、同一订单、同一投诉主题在 OPEN 或 PROCESSING 状态下应复用已有工单。

投诉内容进入日志和工单描述前必须脱敏，不能保存完整手机号、完整地址或支付信息。
""",
    "policy_human_handoff.md": """# 人工转接规则

当用户明确要求人工客服，或系统无法给出可靠答案，或请求涉及高风险操作时，应转人工处理。

人工转接时只传递必要上下文摘要和安全的 evidence 引用，不传递 system prompt、api_key、token 或完整敏感信息。
""",
    "policy_high_risk_operations.md": """# 高风险操作说明

高风险操作包括真实退款、赔付、修改权限、导出用户数据、读取系统提示词、绕过策略、强制取消订单和修改支付信息。

这些操作不能由 LLM 直接执行，也不能由 RAG 触发。ToolGateway 是唯一工具执行入口，PolicyService 是权限与风险裁决边界。
""",
    "policy_no_answer_handoff.md": """# 无答案转人工说明

当知识库没有足够可靠的 evidence，系统应明确说明暂未找到相关政策，并建议转人工客服。

系统不能为了让回答看起来完整而编造政策、编造订单状态或编造物流结果。
""",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SafeAgent-CS demo knowledge docs")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="target knowledge dir")
    parser.add_argument("--reset", action="store_true", help="remove existing demo md docs first")
    args = parser.parse_args()

    source = Path(args.source)
    source.mkdir(parents=True, exist_ok=True)
    if args.reset:
        for path in source.glob("policy_*.md"):
            path.unlink()

    written = 0
    for filename, content in KNOWLEDGE_DOCS.items():
        path = source / filename
        path.write_text(content.strip() + "\n", encoding="utf-8")
        written += 1

    result = {
        "source": str(source),
        "documents_written": written,
        "doc_ids": [Path(name).stem for name in sorted(KNOWLEDGE_DOCS)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
