from pathlib import Path
from typing import Any, Callable

from app.core.tool_result import ToolResult
from app.tools import knowledge_tool, order_tool, ticket_tool


ToolHandler = Callable[[dict[str, Any]], ToolResult]


class ToolRegistry:
    """代码级工具注册表。

    这里的 Registry 只是 P0 内部的确定性路由表，不是 MCP，不做动态插件加载，
    也不从数据库读取工具定义。它只回答“这个 tool_name 有没有对应处理函数”，
    不负责权限、风险、重试、转人工或日志写入。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        mock_dir: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.mock_dir = Path(mock_dir) if mock_dir else None
        self._handlers: dict[str, ToolHandler] = {
            "knowledge_tool.query_policy": self._call_query_policy,
            "order_tool.query_order": self._call_query_order,
            "order_tool.change_address": self._call_change_address,
            "ticket_tool.create_ticket": self._call_create_ticket,
        }

    def has_tool(self, tool_name: str) -> bool:
        """判断工具是否存在于代码级白名单。"""
        return tool_name in self._handlers

    def get_handler(self, tool_name: str) -> ToolHandler:
        """返回工具处理函数；未知工具交由调用方决定如何拒绝。"""
        return self._handlers[tool_name]

    def list_tools(self) -> list[str]:
        """列出当前 P0 支持的工具名，方便测试和后续文档生成。"""
        return sorted(self._handlers)

    @staticmethod
    def _call_query_policy(tool_args: dict[str, Any]) -> ToolResult:
        return knowledge_tool.query_policy(query=str(tool_args.get("query", "")))

    def _call_query_order(self, tool_args: dict[str, Any]) -> ToolResult:
        return order_tool.query_order(
            order_id=str(tool_args.get("order_id", "")),
            mock_dir=self.mock_dir,
            db_path=self.db_path,
        )

    def _call_change_address(self, tool_args: dict[str, Any]) -> ToolResult:
        return order_tool.change_address(
            order_id=str(tool_args.get("order_id", "")),
            new_address=tool_args.get("new_address"),
            mock_dir=self.mock_dir,
            db_path=self.db_path,
        )

    def _call_create_ticket(self, tool_args: dict[str, Any]) -> ToolResult:
        return ticket_tool.create_ticket(
            user_id=str(tool_args.get("user_id", "")),
            action=str(tool_args.get("action", "")),
            target_type=str(tool_args.get("target_type", "")),
            target_id=tool_args.get("target_id"),
            ticket_type=str(tool_args.get("ticket_type", "general")),
            risk_level=str(tool_args.get("risk_level", "L4")),
            description=tool_args.get("description"),
            db_path=self.db_path,
            source_run_id=tool_args.get("source_run_id"),
            parent_run_id=tool_args.get("parent_run_id"),
            pending_action_id=tool_args.get("pending_action_id"),
        )
