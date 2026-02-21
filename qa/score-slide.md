# Slide Notes — RAGAS Evaluation of RAG Architectures

---

## Slide 1: Title Slide

**Title**: RAGAS Evaluation of Legal RAG Architectures

**Details**:
- Evaluation of 5 RAG pipeline configurations for a cross-border Legal AI system
- Domain: Divorce & Inheritance law across Italy, Estonia, and Slovenia
- Framework: RAGAS (Retrieval Augmented Generation Assessment)
- 5 metrics: Context Precision, Context Recall, Faithfulness, Answer Relevancy, Answer Correctness
- LLM: GPT-4o-mini | Embedding: all-MiniLM-L6-v2 | Vector Store: FAISS

---

## Slide 2: Architectures Compared

**Title**: Five RAG Configurations Under Test

**Details**:
- **Single Agent (30/10)**: Simplest pipeline — one retrieval pass, one LLM call. Baseline reference.
- **Multi Agent (30/10)**: Supervisor-subordinate pattern — per-DB sub-agents generate partial answers, supervisor synthesizes final response.
- **Hybrid (30/10)**: LLM-based metadata extraction + heuristic DB routing + two-phase fallback retrieval. Single answer generation.
- **Hybrid Multi-Agent (20/10)**: Combines Hybrid retrieval with Multi-Agent answer generation + cross-encoder reranking. Initial pool of 20, refined to 10.
- **Hybrid Multi-Agent (30/10)**: Same as above but with wider initial retrieval pool (30 docs) refined to 10.
- Key difference: top_k controls how many docs are initially retrieved; top_k_final controls how many survive reranking.

---

## Slide 3: Scores Overview Table

**Title**: Complete RAGAS Scores

**Details**:

| Metric | Single | Multi | Hybrid | HM 20/10 | HM 30/10 |
|--------|:------:|:-----:|:------:|:---------:|:---------:|
| Context Precision | 0.800 | 0.800 | **1.000** | 0.800 | 0.800 |
| Context Recall | 0.742 | 0.767 | **0.867** | 0.767 | 0.750 |
| Faithfulness | 0.780 | 0.653 | 0.633 | 0.763 | **0.802** |
| Answer Relevancy | 0.641 | **0.810** | 0.486 | 0.802 | 0.731 |
| Answer Correctness | **0.695** | 0.628 | 0.608 | 0.619 | 0.639 |
| **Average** | 0.732 | 0.732 | 0.699 | **0.750** | 0.744 |

- No single architecture wins all metrics — each excels in different areas
- Hybrid Multi-Agent (20/10) has the highest average score (0.750)

---

## Slide 4: Context Precision & Recall (Retrieval Quality)

**Title**: How Good Is Our Retrieval?

**Details**:
- **Context Precision** — "Are the retrieved documents relevant?"
  - Hybrid achieves perfect 1.000 — every retrieved doc was useful
  - All other architectures: 0.800 — multi-agent pattern introduces some noise from independent DB querying
- **Context Recall** — "Did we retrieve everything we needed?"
  - Hybrid leads at 0.867 — strict metadata filtering + two-phase fallback ensures comprehensive retrieval
  - More retrieval is NOT always better: HM 30/10 (0.750) has worse recall than HM 20/10 (0.767) because noise pushes out relevant docs during reranking
- **Takeaway**: The Hybrid retrieval pipeline is the strongest at finding and filtering documents. The multi-agent pattern trades some retrieval quality for better answer generation.

---

## Slide 5: Faithfulness (Hallucination Prevention)

**Title**: Does the LLM Stay Grounded in the Evidence?

**Details**:
- **Faithfulness** — "Does the answer contain only facts from the retrieved context?"
- HM 30/10 leads at **0.802** — the combination of:
  1. Cross-encoder reranking surfaces the most relevant docs
  2. Isolated sub-agent contexts force grounding
  3. Strict prompts: "answer ONLY from provided context"
  4. Wider pool (30 docs) gives the cross-encoder more candidates to find exact evidence
- Single Agent is second (0.780) — simplest pipeline = fewest distortion points
- Hybrid and Multi Agent score lowest (0.633, 0.653) — single-context-window truncation and synthesis distortion
- **Takeaway**: Cross-encoder reranking + isolated context windows are the best anti-hallucination combination

---

## Slide 6: Answer Relevancy (Addressing the Question)

**Title**: Does the Answer Address What Was Actually Asked?

**Details**:
- **Answer Relevancy** — "How topically aligned is the answer with the question?"
- Multi Agent leads at **0.810**, HM 20/10 close at 0.802
  - Focused sub-agents answer from narrow DB-specific context
  - Supervisor synthesis filters out tangential information
- HM 30/10 drops to 0.731 — broader retrieval introduces tangential info the LLM addresses
- Hybrid scores worst (0.486) — no intelligent router meant theory questions got forced through retrieval, producing irrelevant context
- **Takeaway**: Tighter retrieval (20 > 30) and focused sub-agents produce more relevant answers. Less is more.

---

## Slide 7: Answer Correctness (End-to-End Accuracy)

**Title**: Are the Final Answers Actually Correct?

**Details**:
- **Answer Correctness** — "Does the answer match the ground-truth reference?"
- This is the weakest metric across ALL architectures (none exceed 0.700)
- Single Agent leads at **0.695** — shortest pipeline = least information loss
- Multi-step architectures suffer from:
  1. Synthesis distortion: supervisor merging can lose nuance
  2. Token limit (384 tokens): complex legal answers get truncated
  3. Information loss cascade: each pipeline step can lose critical details
- **Takeaway**: Pipeline complexity is the enemy of correctness. Every additional step (metadata extraction, sub-agent answering, supervisor synthesis) is an opportunity for information loss.

---

## Slide 8: Overall Ranking

**Title**: Which Architecture Wins Overall?

**Details**:

| Rank | Architecture | Avg Score | Best At |
|:----:|-------------|:---------:|---------|
| 1 | HM 20/10 | **0.750** | Best overall balance |
| 2 | HM 30/10 | 0.744 | Faithfulness (0.802) |
| 3 | Single | 0.732 | Correctness (0.695) |
| 4 | Multi | 0.732 | Relevancy (0.810) |
| 5 | Hybrid | 0.699 | Precision (1.000) + Recall (0.867) |

- **Hybrid Multi-Agent (20/10)** is the recommended default — no catastrophic failures on any metric
- The "best" architecture depends on what you optimize for:
  - Need accurate retrieval? Use **Hybrid**
  - Need faithful answers? Use **HM 30/10**
  - Need correct answers? Use **Single Agent**
  - Need relevant answers? Use **Multi Agent**

---

## Slide 9: Key Trade-offs Discovered

**Title**: Three Critical Trade-offs

**Details**:

1. **Retrieval Quality vs Answer Quality**
   - Hybrid has the best retrieval (precision=1.0, recall=0.867) but the worst answers (relevancy=0.486, correctness=0.608)
   - Multi Agent has average retrieval but the best relevancy (0.810)
   - Great retrieval does not guarantee great answers

2. **Pipeline Complexity vs Correctness**
   - Single Agent (simplest) → best correctness (0.695)
   - HM (most complex) → worst correctness (0.619)
   - Every additional LLM call is an opportunity for distortion

3. **Retrieval Breadth vs Focus**
   - top_k=20 → better relevancy (0.802) and recall (0.767)
   - top_k=30 → better faithfulness (0.802) and correctness (0.639)
   - More docs retrieved does not mean better answers

---

## Slide 10: Roadmap for Improvement

**Title**: Next Steps to Push All Metrics Above 0.800

**Details**:

| Priority | Action | Target Metric | Expected Gain |
|:--------:|--------|:-------------:|:-------------:|
| 1 | Increase LLM max_tokens (384 → 512) | Correctness | +0.05-0.08 |
| 2 | Multi-query retrieval (2-3 paraphrases) | Recall | +0.05-0.10 |
| 3 | Cross-encoder score threshold | Precision | +0.05-0.10 |
| 4 | Upgrade embedding (bge-base-en-v1.5) | Recall + Precision | +0.05-0.08 |
| 5 | Tighten sub-agent + supervisor prompts | Relevancy | +0.03-0.05 |
| 6 | Add BM25 + Reciprocal Rank Fusion | Recall | +0.05-0.10 |
| 7 | Adaptive routing (simple Q → Single, complex → HM) | Correctness | +0.05-0.10 |

- Quick wins (Priority 1, 3, 5) can be done in hours
- Medium effort (Priority 2, 4) need a day of work + re-evaluation
- High effort (Priority 6, 7) are architectural changes
