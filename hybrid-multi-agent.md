Hybrid Multi-Agent:

=> The Hybrid Multi-Agent architecture is used for this project because it combines high-recall retrieval with controlled answer synthesis for cross-border legal questions (Italy, Estonia, Slovenia). This mode works in three coordinated stages:

1. Hybrid retrieval layer: => Extracts legal metadata from the query (country/law intent) by retrieving the candidates with dense FAISS search plus BM25 keyword matching, and uses reranking and cross-encoder filtering to keep only the most relevant evidence.
2. Per-database specialist sub-agents: => Splits retrieved documents by source database (codes/cases, jurisdiction) and lets each sub-agent answer only from its isolated context, reducing source mixing.
3. Supervisor synthesis: => Merges partial answers into one coherent final response and preserves grounding by reconciling overlaps and removing redundancy.

For this project's evaluated question set, Hybrid Multi-Agent provides the best overall balance between faithfulness, relevancy, and correctness, especially on comparative legal questions that require evidence from multiple jurisdictions or document types.

The parameter profile used in the project are: => [top_k: 15], => [top_k_final: 10], => [reranking: enabled], => [metric: cosine], => [BM25 + RRF: enabled], => [cross-encoder threshold: 0.0]
