"""SafeAgent workflow 编排模块。

当前阶段实现的是 LangGraph-style 轻量执行闭环，不接入真实 LangGraph，
也不替代 /api/chat 的手写主链路。后续如果引入 LangGraph，应优先复用
本包中的 State、节点和 service adapter。
"""

