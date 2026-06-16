from pathlib import Path
from uuid import uuid4

from app.core.failure_result import (
    FailureHandlingResult,
    FailureHandlingStatus,
    FailureNextAction,
)
from app.core.tool_result import ToolResult
from app.storage.db import get_connection, init_db


class FailureHandler:
    """基础失败处理服务。

    本阶段 FailureHandler 只处理 ToolGateway 返回的失败 ToolResult：判断是否
    retryable、生成后续建议动作，并写入 failure_logs。它不做权限判断，不调用
    PolicyService，也不会绕过 ToolGateway 直接调用任何 Mock Tool。
    """

    SOURCE_TOOL_GATEWAY = "tool_gateway"

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        init_db(self.db_path)

    def handle_tool_result(
        self,
        run_id: str,
        session_id: str,
        tool_result: ToolResult,
        source: str = SOURCE_TOOL_GATEWAY,
    ) -> FailureHandlingResult:
        """处理一次工具结果。

        成功结果不是失败事件，因此不写 failure_logs；失败结果才会落库。
        retry_count 在 P4A 固定为 0,后续真正重试由 FailureHandler 的增强版本
        或主 Workflow 再次调用 ToolGateway 来完成。
        """
        if tool_result.success:
            return FailureHandlingResult(
                status=FailureHandlingStatus.NO_FAILURE,
                retryable=False,
                next_action=FailureNextAction.NO_FAILURE,
                reason="工具调用成功，无需失败处理。",
                final_tool_result=tool_result,
            )

        failure_type = self._get_failure_type(tool_result)
        retryable = bool(tool_result.error.retryable) if tool_result.error else False
        if retryable:
            status = FailureHandlingStatus.RETRY_REQUIRED
            next_action = FailureNextAction.RETRY
            reason = f"工具失败可重试: {failure_type}"
        else:
            status = FailureHandlingStatus.FAILED
            next_action = FailureNextAction.FAILED
            reason = f"工具失败不可重试: {failure_type}"

        result = FailureHandlingResult(
            status=status,
            retryable=retryable,
            next_action=next_action,
            reason=reason,
            final_tool_result=tool_result,
        )
        self._write_failure_log(
            run_id=run_id,
            session_id=session_id,
            failure_type=failure_type,
            source=source,
            retryable=retryable,
            retry_count=0,
            fallback_action=next_action.value,
            final_status=status.value,
        )
        return result

    def handle_with_retry(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict,
        first_result: ToolResult,
        tool_gateway,
        current_attempt_no: int = 1,
    ) -> FailureHandlingResult:
        """处理工具失败，并在允许时通过 ToolGateway 重试一次。

        重试必须走 ToolGateway，这样第二次调用会自然写入 tool_call_logs；
        FailureHandler 不直接调用任何 Mock Tool，也不做权限判断。
        """
        if first_result.success:
            return FailureHandlingResult(
                status=FailureHandlingStatus.NO_FAILURE,
                retryable=False,
                next_action=FailureNextAction.NO_FAILURE,
                reason="工具调用成功，无需失败处理。",
                final_tool_result=first_result,
            )

        retryable = bool(first_result.error.retryable) if first_result.error else False
        if not retryable:
            return self.handle_tool_result(
                run_id=run_id,
                session_id=session_id,
                tool_result=first_result,
            )

        second_result = tool_gateway.call_tool(
            run_id=run_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=tool_args,
            attempt_no=current_attempt_no + 1,
        )
        failure_type = self._get_failure_type(first_result)
        if second_result.success:
            status = FailureHandlingStatus.RECOVERED
            next_action = FailureNextAction.NO_FAILURE
            reason = f"工具失败后重试成功: {failure_type}"
            fallback_action = FailureNextAction.RETRY.value
        else:
            status = FailureHandlingStatus.FAILED
            next_action = FailureNextAction.FAILED
            reason = f"工具重试后仍失败: {failure_type}"
            fallback_action = FailureNextAction.RETRY.value

        result = FailureHandlingResult(
            status=status,
            retryable=retryable,
            next_action=next_action,
            reason=reason,
            final_tool_result=second_result,
        )
        self._write_failure_log(
            run_id=run_id,
            session_id=session_id,
            failure_type=failure_type,
            source=self.SOURCE_TOOL_GATEWAY,
            retryable=retryable,
            retry_count=1,
            fallback_action=fallback_action,
            final_status=status.value,
        )
        return result

    @staticmethod
    def _get_failure_type(tool_result: ToolResult) -> str:
        if tool_result.error_type:
            return tool_result.error_type
        if tool_result.error:
            return tool_result.error.failure_type
        return "UNKNOWN_FAILURE"

    def _write_failure_log(
        self,
        run_id: str,
        session_id: str,
        failure_type: str,
        source: str,
        retryable: bool,
        retry_count: int,
        fallback_action: str,
        final_status: str,
    ) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO failure_logs (
                    id, run_id, session_id, failure_type, source,
                    retryable, retry_count, fallback_action, final_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._generate_log_id(),
                    run_id,
                    session_id,
                    failure_type,
                    source,
                    1 if retryable else 0,
                    retry_count,
                    fallback_action,
                    final_status,
                ),
            )
            connection.commit()

    @staticmethod
    def _generate_log_id() -> str:
        return f"fl_{uuid4().hex[:16]}"
