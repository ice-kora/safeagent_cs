# Advanced RAG Architecture

`knowledge_tool.query_policy` remains the only RAG entry in the main chain. It is called through ToolGateway by `KnowledgeToolAdapter`.

RAGService returns:

```json
{
  "answer": "...",
  "evidence": [],
  "citations": [],
  "sources": [],
  "matched_chunks": [],
  "retrieval_mode": "hybrid",
  "embedding_model": "mock-hash-embedding",
  "vector_store": "memory",
  "no_answer": false
}
```

Hybrid score:

```text
hybrid_score = dense_weight * dense_score + keyword_weight * keyword_score
final_score = hybrid_score
```

Supported defaults:

- Vector store: `memory`
- Optional vector store: `milvus`
- Embedding: `mock`
- Optional embedding: `sentence_transformers`

File loaders support txt, md, html, csv and optional pdf/docx/xlsx dependencies. Image OCR and audio ASR are explicit disabled skeletons.
