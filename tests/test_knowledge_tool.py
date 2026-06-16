from app.tools.knowledge_tool import query_policy


def test_query_policy_returns_answer_and_sources() -> None:
    result = query_policy("你们支持七天无理由退货吗？")

    assert result.success is True
    assert result.tool_name == "knowledge_tool.query_policy"
    assert result.safe_for_llm is True
    assert result.data["answer"]
    assert result.data["sources"]
    assert result.summary == result.data["answer"]
