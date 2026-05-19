# Legal RAG System

This project implements an agentic Retrieval-Augmented Generation (RAG) pipeline for legal QA across divorce and inheritance domains in Italy, Estonia, and Slovenia.

## 1) Setup and Run

### Environment variables

Create `.env` in project root:

```ini
OPENROUTER_API_KEY=your_key_here
HUGGINGFACEHUB_API_TOKEN=your_key_here
```

### Data layout

Place JSON corpus under `Contest_Data/` with country and domain subfolders.

### Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Apple Silicon cleanup (if TF stack was already installed)
pip uninstall -y tensorflow tf-keras keras tensorflow-estimator tensorflow-io-gcs-filesystem

streamlit run Home.py
```

### Docker run

```bash
docker build -t agentic-rag-app .
docker run -p 8501:8501 --env-file .env -v $(pwd)/Contest_Data:/app/Contest_Data agentic-rag-app
```

Open: `http://localhost:8501`

## 2) Architectures Used

| Architecture | Core idea | Best use case |
|---|---|---|
| Single Agent | One retrieval pipeline and one grounded answer call | Low-latency baseline |
| Multi-Agent | Supervisor routes to per-DB sub-agents and synthesizes | Mixed-source legal questions |
| Hybrid (Metadata + Vector) | LLM metadata extraction + FAISS + BM25/RRF + filtering | Retrieval-focused diagnostics |
| Hybrid Multi-Agent | Hybrid retrieval + per-DB sub-agents + supervisor merge | Best overall production mode |

### Component matrix

| Component | Single | Multi | Hybrid | Hybrid Multi-Agent |
|---|---|---|---|---|
| Intelligent router | Optional | Yes | Optional | Yes |
| LLM metadata extraction | No | Partial | Yes | Yes |
| FAISS dense retrieval | Yes | Yes | Yes | Yes |
| BM25 + RRF fusion | No | No | Yes | Yes |
| Similarity rerank | Yes | Yes | Yes | Yes |
| Cross-encoder threshold filter | No | No | Yes | Yes |
| Per-DB sub-agents | No | Yes | No | Yes |
| Supervisor synthesis | No | Yes | No | Yes |

## 3) Updated Aggregated Mean Scores

The following values are the updated aggregate metrics to use in reports.

| Metric | Aggregated Mean Score |
|---|---:|
| context_precision | 0.800 |
| context_recall | 0.833 |
| faithfulness | 0.800 |
| answer_relevancy | 0.822 |
| answer_correctness | 0.621 |

## 4) Metric Explanation Table

| Parameter | What it measures | How to read this value | Current implication |
|---|---|---|---|
| context_precision | Share of retrieved docs that are truly relevant | Higher means less retrieval noise | 0.800 indicates good precision with moderate residual noise |
| context_recall | Share of needed evidence actually retrieved | Higher means better evidence coverage | 0.833 indicates strong coverage of relevant legal evidence |
| faithfulness | Portion of answer claims grounded in retrieved context | Higher means fewer hallucinations | 0.800 indicates mostly grounded responses |
| answer_relevancy | How directly the answer addresses the user query | Higher means more focused answers | 0.822 indicates high topical focus |
| answer_correctness | Agreement with expected/ground-truth answer | Higher means stronger factual alignment | 0.621 indicates moderate correctness and room to improve synthesis |

## 5) Recommended Production Parameters

| Parameter | Recommended value |
|---|---|
| agentic_mode | hybrid_multiagent |
| top_k | 15 |
| top_k_final | 10 |
| use_rerank | true |
| rerank_metric | cosine |
| use_bm25 | true |
| cross_encoder_model | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| cross_encoder_threshold | 0.0 |
| similarity_threshold | 0.45 |
| chunk_size | 512 |
| chunk_overlap | 50 |
| max_context_chars | 8000 |

## 6) Mermaid Process Flow Diagrams

### Single Agent

```mermaid
flowchart TD
  Q[User Question] --> S0{Need retrieval?}
  S0 -->|No| S1[Direct LLM answer]
  S0 -->|Yes| S2[Keyword metadata extraction]
  S2 --> S3[Heuristic DB selection]
  S3 --> S4[FAISS retrieval top_k]
  S4 --> S5{Rerank enabled?}
  S5 -->|Yes| S6[Similarity rerank to top_k_final]
  S5 -->|No| S7[Use raw docs]
  S6 --> S8[Build context]
  S7 --> S8
  S8 --> F[Final Answer]
  S1 --> F
```

### Multi-Agent

```mermaid
flowchart TD
  Q[User Question] --> M0[Intelligent router]
  M0 -->|General| M1[Direct LLM answer]
  M0 -->|Legal| M2[Metadata extraction]
  M2 --> M3[Supervisor DB selection]
  M3 --> M4[Sub-agent per selected DB]
  M4 --> MA[Sub-agent DB_1 answer]
  M4 --> MB[Sub-agent DB_2 answer]
  M4 --> MC[Sub-agent DB_N answer]
  MA --> MS[Supervisor synthesis]
  MB --> MS
  MC --> MS
  M1 --> F[Final Answer]
  MS --> F
```

### Hybrid (Metadata + Vector)

```mermaid
flowchart TD
  Q[User Question] --> H1[LLM metadata extraction]
  H1 --> H2[Build metadata filter]
  H2 --> H3[Heuristic DB candidates]
  H3 --> H4[FAISS retrieval full filter]
  H4 --> H5{Enough docs?}
  H5 -->|No| H6[Fallback law-only retrieval]
  H5 -->|Yes| H7[Proceed]
  H6 --> H8[BM25 + RRF fusion]
  H7 --> H8
  H8 --> H9[Similarity rerank]
  H9 --> H10[Cross-encoder threshold filter]
  H10 --> F[Final Answer]
```

### Hybrid Multi-Agent

```mermaid
flowchart TD
  Q[User Question] --> HM0[Intelligent router]
  HM0 -->|General| HM1[Direct LLM answer]
  HM0 -->|Legal| HM2[LLM metadata extraction]
  HM2 --> HM3[Two-phase retrieval per DB]
  HM3 --> HM4[BM25 + RRF fusion]
  HM4 --> HM5[Similarity rerank]
  HM5 --> HM6[Cross-encoder threshold filter]
  HM6 --> HM7[Partition docs by DB]
  HM7 --> HMA[Sub-agent DB_1 answer]
  HM7 --> HMB[Sub-agent DB_2 answer]
  HM7 --> HMC[Sub-agent DB_N answer]
  HMA --> HMS[Supervisor synthesis]
  HMB --> HMS
  HMC --> HMS
  HM1 --> F[Final Answer]
  HMS --> F
```
