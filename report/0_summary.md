This project is a retrieval-augmented generation system for legal question answering over civil and commercial law datasets from Italy, Slovenia, and Estonia. The corpus is split into two collections: statutory codes and court case judgments, both indexed as FAISS vector stores for dense semantic retrieval.

Four agent architectures are implemented:

- Single Agent: one retriever, one LLM call, straightforward pipeline.
- Multi-Agent: two parallel agents, one querying codes and one querying cases, with outputs merged before final synthesis.
- Hybrid Agent: single-agent structure but retrieval combines FAISS dense search with BM25 sparse search via Reciprocal Rank Fusion (RRF) to capture exact legal terms like article numbers.
- Hybrid Multi-Agent: dual-agent decomposition plus BM25+RRF fusion, followed by cross-encoder reranking with a 0.0 threshold to filter negatively scored passages.

Shared infrastructure and parameters:

- Embedding model: all-MiniLM-L6-v2 (384 dimensions)
- Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
- LLM: meta-llama/llama-3.1-8b-instruct via OpenRouter
- Generation budget: 768 tokens
- Document chunking: 512 tokens, 50-token overlap
- Top-k retrieval candidates: varies per configuration (10, 15, 20, 30)
- Cross-encoder final passage count: 10
- BM25 index: built at query time over the retrieved candidate pool

All agents share the same prompt template that instructs the model to answer strictly from retrieved context and cite article numbers where applicable. Evaluation uses RAGAS metrics across seven configuration variants to compare retrieval quality and generation accuracy.