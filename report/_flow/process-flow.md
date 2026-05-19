# Complete Search Process Flow with Dense + BM25 + RRF

## Stage 0 — Mode Router
**File:** `backend/rag_pipeline.py`

| Parameter | Value | Source |
|---|---|---|
| `agentic_mode` | `"standard_rag"` / `"hybrid_rag"` / `"hybrid_multiagent"` | `config.py` |
| Routes to | `hybrid_answer_question()` or `hybrid_multiagent_answer_question()` | `rag_pipeline.py:answer_question()` |

---

## Stage 1 — Intelligent Router (LLM: Legal vs. General)
**File:** `backend/hybrid_rag.py` — used in `hybrid_rag` / `hybrid_multiagent` modes

- LLM decides if query is a legal question or chitchat
- If **General** → answer from LLM internal knowledge, **no retrieval**
- If **Legal** → continue to Stage 2

---

## Stage 2 — LLM Metadata Extraction
**Function:** `_extract_legal_metadata_from_query()` + `_classify_law()`

| Step | Mechanism | Parameters |
|---|---|---|
| 2a. Law classification | Heuristic keywords first | `succession_kw`, `divorce_kw` hardcoded lists |
| 2b. Ambiguous → LLM | `llm_backend.chat()` | `llm_model_name = "openai/gpt-4o-mini"`, `temperature = 0.2` |
| 2c. Full schema extraction | LLM + `LEGAL_METADATA_SCHEMA` | Extracts: `law`, `civil_codes_used`, `cost`, `duration`, etc. |
| Output | `{"law": "Divorce/Inheritance", "civil_codes_used": [...], ...}` | Mandatory field: `law` |

---

## Stage 3 — Metadata Filter Building
**Function:** `_build_metadata_filter()`

```
filter = {"law": "Divorce|Inheritance"}
         + {"civil_codes_used": codes[0]}   ← if codes present
```

---

## Stage 4 — Heuristic DB Selection
**Function:** `_heuristic_db_candidates()`

| Logic | Keywords matched |
|---|---|
| `law = "Inheritance"` | `inherit`, `succession`, `successione`, `eredit` |
| `law = "Divorce"` | `divorce`, `divorz`, `separat`, `separazione` |
| No match | Fallback → **ALL DBs** |

DBs available: `divorce_cases/`, `divorce_codes/`, `inheritance_cases/`, `inheritance_codes/`

---

## Stage 5 — Retrieval per DB (Core Search)
**Function:** `_retrieve_from_db_hybrid()` — called once per selected DB

### 5a. FAISS Dense Retrieval (Phase 1: Full Filter)

| Parameter | Value | Config key |
|---|---|---|
| `k_base` | `max(top_k × 3, top_k)` = **90** | derived from `top_k = 30` |
| Filter | `{"law": ..., "civil_codes_used": ...}` (full) | `_build_metadata_filter()` |
| Backend | FAISS L2 index (`index.faiss`) | `vector_store.py:load_vector_store()` |
| Embedding model | `all-MiniLM-L6-v2` (384-dim) | `config.embedding_model_name` |
| Embeddings normalized | Yes (`normalize_embeddings=True`) | `embeddings.py` |
| Device | CPU | forced in `embeddings.py` |

### 5b. Fallback (Phase 2) — if `len(docs) < top_k`

| Trigger | Condition |
|---|---|
| Full filter too strict | `len(docs) < 30` |
| Fallback filter | Mandatory `law` only (drops `civil_codes_used`) |
| Same `k_base` | 90 |

---

## Stage 6 — BM25 + RRF Fusion (Sparse + Dense Hybrid)
**Function:** `_bm25_rrf_rerank()` — active when `use_bm25 = True`

| Step | Detail | Parameter |
|---|---|---|
| Tokenization | `doc.page_content.lower().split()` | whitespace, no stemming |
| BM25 model | `BM25Okapi` from `rank_bm25` | — |
| Dense rank | From FAISS retrieval order (best-first = rank 1) | `dense_order = list(range(len(docs)))` |
| BM25 rank | Sorted by `bm25.get_scores(q_tokens)` descending | — |
| **RRF formula** | `score(d) = 1/(k + rank_dense(d)) + 1/(k + rank_bm25(d))` | `k_rrf = 60` (hardcoded) |
| Output | Docs re-sorted by RRF score descending | — |

> **Why k=60?** Softens rank differences; standard RRF default from the original paper.

---

## Stage 7 — Bi-Encoder Similarity Reranking
**Function:** `_similarity_rank_and_filter()` — active when `use_rerank = True`

| Step | Detail | Parameter |
|---|---|---|
| Query embedding | `embedding_model.embed_query(question)` | `all-MiniLM-L6-v2` |
| Doc embeddings | `embedding_model.embed_documents([...])` | same model |
| Similarity metric | `_compute_similarity(q_vec, doc_vecs, metric)` | `rerank_metric = "cosine"` (default) |
| **Cosine** | `(q · d) / (‖q‖ ‖d‖)` | formula in `_compute_similarity()` |
| **Dot product** | `d · q` | alt option |
| **Euclidean** | `1 / (1 + ‖L2 dist‖)` | alt option |
| Min threshold | `min_sim = 0.1` | hardcoded in `_retrieve_from_db_hybrid()` |
| Top-k kept | `top_k = 30` | `config.top_k` |

---

## Stage 8 — Cross-Encoder Reranking + Threshold Filter
**Function:** `_cross_encoder_rerank()` — active when `use_cross_encoder = True`

| Step | Detail | Parameter |
|---|---|---|
| Model | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `config.cross_encoder_model` |
| Pairs scored | `(question, doc.page_content)` for every doc | — |
| Output | Raw logits (positive = relevant) | — |
| Threshold | `score >= 0.0` to keep | `config.cross_encoder_threshold = 0.0` |
| Top-k applied | `top_k = 30` | `config.top_k` |
| Model cached | Yes (`_CROSS_ENCODER_CACHE` dict) | module-level global |

---

## Stage 9 — Context Building
**Function:** `_build_context()`

| Parameter | Value |
|---|---|
| `max_chars` | 4000 (hybrid) / 8000 (hybrid_multiagent) |
| Doc header format | `[DOC N | DB: {db_name} | source: {src}]` |
| Context truncation | Stops when cumulative chars exceed `max_chars` |

---

## Stage 10 — Answer Generation
**LLM call with dynamic prompt**

| Condition | Prompt mode |
|---|---|
| Context available | Strict grounding: "STRICTLY limited to provided context, cite source documents" |
| No docs found | Refusal: "No relevant documents found" |

| Parameter | Value |
|---|---|
| `llm_model_name` | `openai/gpt-4o-mini` (via OpenRouter) |
| `llm_temperature` | `0.2` |
| `llm_max_tokens` | `768` |

---

## Summary: Full Retrieval Chain per Query

```
FAISS Dense (k=90, full filter)
        ↓
  [Fallback if < 30 docs: law-only filter]
        ↓
BM25Okapi sparse scores
        ↓
  RRF fusion  (k_rrf=60):
  score = 1/(60+rank_dense) + 1/(60+rank_bm25)
        ↓
Bi-Encoder cosine rerank  (all-MiniLM-L6-v2)
  → threshold: sim ≥ 0.1
  → keep top 30
        ↓
Cross-Encoder rerank  (ms-marco-MiniLM-L-6-v2)
  → threshold: logit ≥ 0.0
  → keep top 30
        ↓
Context (max 4000 / 8000 chars)
        ↓
LLM Answer (gpt-4o-mini, temp=0.2, max_tokens=768)
```

---

## All Config Parameters at a Glance

| Parameter | Value | File |
|---|---|---|
| `top_k` | `30` | `backend/config.py` |
| `top_k_final` | `10` | `backend/config.py` |
| `k_base` (retrieval) | `max(top_k×3, top_k)` = 90 | `backend/hybrid_rag.py` |
| `similarity_threshold` | `0.45` (config) / `0.1` (used in call) | `backend/config.py` |
| `use_rerank` | `True` | `backend/config.py` |
| `rerank_metric` | `"cosine"` | `backend/config.py` |
| `use_bm25` | `True` | `backend/config.py` |
| `k_rrf` | `60` | `backend/hybrid_rag.py` (hardcoded) |
| `use_cross_encoder` | `True` | `backend/config.py` |
| `cross_encoder_model` | `ms-marco-MiniLM-L-6-v2` | `backend/config.py` |
| `cross_encoder_threshold` | `0.0` | `backend/config.py` |
| `embedding_model_name` | `all-MiniLM-L6-v2` | `backend/config.py` |
| `chunk_size` | `512` | `backend/config.py` |
| `chunk_overlap` | `50` | `backend/config.py` |
