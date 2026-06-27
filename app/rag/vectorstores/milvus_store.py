import json
from typing import Any

from app.rag.vectorstores.base import (
    VectorRecord,
    VectorSearchResult,
    VectorStoreUnavailable,
)


TEXT_MAX_LENGTH = 8192
SHORT_TEXT_MAX_LENGTH = 1024
ID_MAX_LENGTH = 512


class MilvusVectorStore:
    """Milvus vector store for real SafeAgent-CS knowledge chunks."""

    name = "milvus"
    vector_field = "embedding"

    def __init__(
        self,
        uri: str | None,
        collection: str,
        dimension: int | None,
        *,
        auto_create: bool = True,
    ) -> None:
        if not uri:
            raise VectorStoreUnavailable("SAFEAGENT_RAG_MILVUS_URI is required")
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise VectorStoreUnavailable(
                "pymilvus is required for SAFEAGENT_RAG_VECTOR_STORE=milvus. "
                "Install it with: pip install pymilvus"
            ) from exc
        self.uri = uri
        self.collection = collection
        self.dimension = dimension
        try:
            self._client = MilvusClient(uri=uri)
            if auto_create:
                self.ensure_collection(dimension=dimension)
        except Exception as exc:
            raise VectorStoreUnavailable(f"Milvus connection failed: {exc}") from exc

    def has_collection(self) -> bool:
        return bool(self._client.has_collection(self.collection))

    def drop_collection(self) -> None:
        if self.has_collection():
            self._client.drop_collection(self.collection)

    def rebuild_collection(self, dimension: int | None = None) -> None:
        self.drop_collection()
        self.ensure_collection(dimension=dimension or self.dimension)

    def ensure_collection(self, dimension: int | None = None) -> None:
        if self.has_collection():
            if hasattr(self._client, "load_collection"):
                self._client.load_collection(self.collection)
            return
        selected_dimension = dimension or self.dimension
        if not selected_dimension:
            raise VectorStoreUnavailable(
                "Milvus collection does not exist and vector dimension is unknown"
            )
        self.dimension = selected_dimension
        self._create_collection(selected_dimension)

    def collection_stats(self) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "collection": self.collection,
            "exists": self.has_collection(),
            "dimension": self.dimension,
        }
        if not stats["exists"]:
            return stats
        try:
            stats["row_count"] = self._client.get_collection_stats(
                collection_name=self.collection
            ).get("row_count")
        except Exception:
            stats["row_count"] = None
        if stats["row_count"] in {0, "0", None}:
            try:
                rows = self._client.query(
                    collection_name=self.collection,
                    filter="",
                    output_fields=["id"],
                    limit=16384,
                )
                stats["query_count"] = len(rows)
            except Exception:
                stats["query_count"] = None
        return stats

    def insert(self, records: list[VectorRecord]) -> None:
        self.upsert(records)

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        first_dimension = len(records[0].vector)
        if not self.has_collection():
            self.ensure_collection(dimension=first_dimension)
        data = [self._record_to_row(record) for record in records]
        try:
            self._client.upsert(collection_name=self.collection, data=data)
        except Exception:
            # MilvusClient upsert is preferred. Some older deployments only expose
            # insert; demo ingest normally rebuilds the collection before insert.
            self._client.insert(collection_name=self.collection, data=data)
        if hasattr(self._client, "flush"):
            self._client.flush(collection_name=self.collection)

    def search(self, query_vector: list[float], top_k: int) -> list[VectorSearchResult]:
        if not self.has_collection():
            raise VectorStoreUnavailable(
                f"Milvus collection {self.collection!r} does not exist"
            )
        rows = self._client.search(
            collection_name=self.collection,
            data=[query_vector],
            anns_field=self.vector_field,
            limit=top_k,
            output_fields=[
                "chunk_id",
                "doc_id",
                "title",
                "category",
                "content",
                "content_preview",
                "source_path",
                "file_type",
                "metadata_json",
            ],
            search_params={"metric_type": "COSINE", "params": {}},
        )
        results: list[VectorSearchResult] = []
        for row in rows[0] if rows else []:
            entity = row.get("entity") or {}
            payload = dict(entity)
            metadata_json = payload.pop("metadata_json", "{}")
            try:
                payload["metadata"] = json.loads(metadata_json or "{}")
            except json.JSONDecodeError:
                payload["metadata"] = {}
            result_id = str(payload.get("chunk_id") or row.get("id"))
            results.append(
                VectorSearchResult(
                    id=result_id,
                    score=float(row.get("distance", 0.0)),
                    payload=payload,
                )
            )
        return results

    def _create_collection(self, dimension: int) -> None:
        try:
            from pymilvus import DataType, MilvusClient
        except ImportError as exc:
            raise VectorStoreUnavailable("pymilvus is not installed") from exc

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=ID_MAX_LENGTH,
        )
        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.VARCHAR,
            max_length=ID_MAX_LENGTH,
        )
        schema.add_field(
            field_name="doc_id",
            datatype=DataType.VARCHAR,
            max_length=ID_MAX_LENGTH,
        )
        schema.add_field(
            field_name="title",
            datatype=DataType.VARCHAR,
            max_length=SHORT_TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name="category",
            datatype=DataType.VARCHAR,
            max_length=SHORT_TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name="content_preview",
            datatype=DataType.VARCHAR,
            max_length=SHORT_TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name="source_path",
            datatype=DataType.VARCHAR,
            max_length=TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name="file_type",
            datatype=DataType.VARCHAR,
            max_length=SHORT_TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name="metadata_json",
            datatype=DataType.VARCHAR,
            max_length=TEXT_MAX_LENGTH,
        )
        schema.add_field(
            field_name=self.vector_field,
            datatype=DataType.FLOAT_VECTOR,
            dim=dimension,
        )
        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name=self.vector_field,
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        self._client.create_collection(
            collection_name=self.collection,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
        )
        if hasattr(self._client, "load_collection"):
            self._client.load_collection(self.collection)

    def _record_to_row(self, record: VectorRecord) -> dict[str, Any]:
        payload = dict(record.payload)
        doc_id = str(payload.get("doc_id") or payload.get("source") or record.id)
        chunk_id = str(payload.get("chunk_id") or record.id)
        content = str(payload.get("content") or payload.get("text") or "")
        preview = str(payload.get("content_preview") or content[:220])
        metadata = payload.get("metadata") or {}
        return {
            "id": _clip(record.id, ID_MAX_LENGTH),
            "chunk_id": _clip(chunk_id, ID_MAX_LENGTH),
            "doc_id": _clip(doc_id, ID_MAX_LENGTH),
            "title": _clip(str(payload.get("title") or doc_id), SHORT_TEXT_MAX_LENGTH),
            "category": _clip(
                str(payload.get("category") or "policy"),
                SHORT_TEXT_MAX_LENGTH,
            ),
            "content": _clip(content, TEXT_MAX_LENGTH),
            "content_preview": _clip(preview, SHORT_TEXT_MAX_LENGTH),
            "source_path": _clip(str(payload.get("source_path") or ""), TEXT_MAX_LENGTH),
            "file_type": _clip(
                str(payload.get("file_type") or "text"),
                SHORT_TEXT_MAX_LENGTH,
            ),
            "metadata_json": _clip(
                json.dumps(metadata, ensure_ascii=False, default=str),
                TEXT_MAX_LENGTH,
            ),
            self.vector_field: [float(value) for value in record.vector],
        }


def _clip(value: str, max_length: int) -> str:
    return value[:max_length]
