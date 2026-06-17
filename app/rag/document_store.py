from app.rag.policy_corpus import load_policy_documents
from app.rag.rag_models import PolicyDocument


class PolicyDocumentStore:
    """本地政策文档仓库。"""

    def __init__(self, documents: list[PolicyDocument] | None = None) -> None:
        self._documents = documents or load_policy_documents()

    def list_documents(self) -> list[PolicyDocument]:
        return list(self._documents)

