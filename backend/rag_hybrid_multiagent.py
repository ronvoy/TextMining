# backend/rag_hybrid_multiagent.py
#
# Hybrid Multi-Agent RAG:
#   - Retrieval pipeline from Hybrid (LLM metadata extraction, heuristic DB
#     selection, two-phase fallback, similarity reranking)
#   - Cross-encoder reranking for improved context precision
#   - Answer generation from Multi-Agent (per-DB sub-agents with isolated
#     context windows + supervisor synthesis)

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from .config import RAGConfig
from .embeddings import get_embedding_model
from .llm_provider import LLMBackend

from .hybrid_rag import (
    _get_vector_db_dirs,
    _describe_databases,
    _extract_legal_metadata_from_query,
    _build_metadata_filter,
    _heuristic_db_candidates,
    _retrieve_from_db_hybrid,
    _build_context,
    _build_observation_text,
    _build_agent_config_log,
)

# Singleton cache so the cross-encoder is loaded only once
_CROSS_ENCODER_CACHE: Dict[str, CrossEncoder] = {}


def _get_cross_encoder(model_name: str) -> CrossEncoder:
    if model_name not in _CROSS_ENCODER_CACHE:
        _CROSS_ENCODER_CACHE[model_name] = CrossEncoder(model_name)
    return _CROSS_ENCODER_CACHE[model_name]


def _cross_encoder_rerank(
    question: str,
    docs: List[Document],
    top_k: int,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> Tuple[List[Document], str]:
    """
    Re-score documents with a cross-encoder and keep the top_k highest.
    Cross-encoders jointly encode (query, document) pairs, producing far
    more accurate relevance scores than bi-encoder cosine similarity.
    """
    if not docs:
        return [], "Cross-encoder rerank: no documents to rerank."

    cross_encoder = _get_cross_encoder(model_name)

    pairs = [(question, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)

    scored = sorted(
        zip(docs, scores), key=lambda x: float(x[1]), reverse=True
    )

    reranked = [doc for doc, _ in scored[:top_k]]

    best = float(scored[0][1])
    worst = float(scored[-1][1])
    cutoff = float(scored[min(top_k - 1, len(scored) - 1)][1])

    log = (
        f"Cross-encoder rerank (model={model_name}):\n"
        f"  Input docs: {len(docs)} → kept top {len(reranked)}\n"
        f"  Score range (all):  [{worst:.4f} … {best:.4f}]\n"
        f"  Cutoff score (rank {min(top_k, len(scored))}): {cutoff:.4f}"
    )
    return reranked, log


# =====================================================================
# 1. Intelligent Router (aligned with all agents)
# =====================================================================

def _decide_need_retrieval(
    question: str,
    llm_backend: LLMBackend,
) -> Tuple[bool, str]:
    system_prompt = (
        "You are an expert query router for a Legal RAG system specialized in "
        "DIVORCE and INHERITANCE law for ITALY, ESTONIA, and SLOVENIA.\n"
        "Your task is to decide if the user question requires retrieving "
        "specific documents from the database.\n"
        "Reply with a single word: YES or NO.\n\n"
        "GUIDELINES:\n"
        "1. REPLY 'YES' (Need Retrieval) IF:\n"
        "   - The question is about specific regulations, procedures, or cases "
        "regarding DIVORCE, FAMILY LAW, or INHERITANCE.\n"
        "   - The question implies or mentions the context of ITALY, ESTONIA, "
        "or SLOVENIA.\n"
        "   - The question asks for a comparison between these jurisdictions.\n\n"
        "2. REPLY 'NO' (No Retrieval) IF:\n"
        "   - The question is general CHITCHAT (e.g., 'Hi', 'Who are you?').\n"
        "   - The question is about GENERAL LEGAL DEFINITIONS or THEORY without "
        "specific country context (e.g., 'What is a void contract?').\n"
        "   - The question is completely OUT OF DOMAIN (e.g., recipes, weather).\n\n"
        "EXAMPLES:\n"
        "User: 'In Estonia, how do I split assets in a divorce?' -> YES\n"
        "User: 'Difference between void and voidable contract?' -> NO\n"
        "User: 'Inheritance taxes in Italy for real estate' -> YES\n"
        "User: 'What is negligence in tort law?' -> NO\n"
        "User: 'Hi, help me please' -> NO"
    )
    user_prompt = f"User Question:\n{question}\n\nDecision (YES/NO):"

    resp = llm_backend.chat(system_prompt, user_prompt).strip().lower()

    if "yes" in resp and "no" not in resp:
        return True, (
            f"Router Decision: SPECIFIC LEGAL query detected ('{resp}'). "
            "Proceed to retrieval."
        )
    if "no" in resp and "yes" not in resp:
        return False, (
            f"Router Decision: GENERAL KNOWLEDGE/CHITCHAT detected ('{resp}'). "
            "Skip retrieval."
        )
    return True, (
        f"Router Decision: Ambiguous ('{resp}'). Defaulting to retrieval."
    )


# =====================================================================
# 2. Per-DB Sub-Agent (uses hybrid retrieval, isolated context)
# =====================================================================

def _run_hybrid_sub_agent(
    question: str,
    db_name: str,
    db_path: str,
    embedding_model,
    config: RAGConfig,
    metadata_filter: Optional[Dict[str, Any]],
) -> Tuple[str, List[Document], str]:
    """
    Sub-agent that uses hybrid's two-phase retrieval for a single DB,
    applies cross-encoder reranking to maximise context precision,
    builds its own isolated context window, and generates a partial answer.
    """
    llm_backend = LLMBackend(config)

    docs, retrieval_log = _retrieve_from_db_hybrid(
        question=question,
        db_name=db_name,
        db_path=db_path,
        embedding_model=embedding_model,
        top_k=config.top_k,
        use_rerank=config.use_rerank,
        rerank_metric=getattr(config, "rerank_metric", "cosine"),
        metadata_filter=metadata_filter,
    )

    # --- Cross-encoder reranking: refine to top_k_final documents ---
    top_k_final = getattr(config, "top_k_final", config.top_k)
    use_ce = getattr(config, "use_cross_encoder", True)
    ce_model = getattr(
        config, "cross_encoder_model", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )

    if use_ce and docs and len(docs) > top_k_final:
        docs, ce_log = _cross_encoder_rerank(
            question=question,
            docs=docs,
            top_k=top_k_final,
            model_name=ce_model,
        )
        retrieval_log += f"\n{ce_log}"
    elif docs and len(docs) > top_k_final:
        docs = docs[:top_k_final]
        retrieval_log += (
            f"\nCross-encoder disabled; truncated to top_k_final={top_k_final}."
        )

    context = _build_context(docs, max_chars=8000)

    if not context:
        return (
            f"No relevant documents found in database '{db_name}' for this query.",
            docs,
            retrieval_log,
        )

    system_prompt = (
        "You are a legal assistant specialized in Italian, Estonian, and "
        "Slovenian civil law (Divorce and Inheritance).\n"
        "Your task is to answer the user's question based ONLY on the "
        f"provided context from database '{db_name}'.\n"
        "RULES:\n"
        "1. Use the provided context as your ONLY source of truth.\n"
        "2. Cite specific articles or case details where appropriate.\n"
        "3. If the context is insufficient, state this clearly.\n"
        "4. Be precise and directly answer what is asked."
    )
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Context from retrieved legal documents:\n{context}\n\n"
        "Provide a clear, concise answer."
    )

    answer = llm_backend.chat(system_prompt, user_prompt)

    return answer, docs, retrieval_log


# =====================================================================
# 3. Supervisor Synthesis
# =====================================================================

def _supervisor_synthesize(
    question: str,
    per_agent_answers: List[Tuple[str, str]],
    llm_backend: LLMBackend,
) -> str:
    agents_block_lines = []
    for db_name, ans in per_agent_answers:
        agents_block_lines.append(f"[Agent: {db_name}]\n{ans}\n")
    agents_block = "\n\n".join(agents_block_lines)

    system_prompt = (
        "You are a supervisor agent coordinating several specialized RAG "
        "agents for Italian, Estonian, and Slovenian civil law.\n"
        "You are given their partial answers to the user's question about "
        "Civil Law (Divorce/Inheritance).\n"
        "Your job is to synthesize a single, clear, non-redundant answer.\n"
        "RULES:\n"
        "1. Merge information from all agents into one coherent response.\n"
        "2. If agents disagree, explain the discrepancy briefly.\n"
        "3. Cite relevant articles or case references from the agents.\n"
        "4. Do not mention internal tools or agents; answer as a single "
        "assistant.\n"
        "5. Be precise — directly answer the question asked."
    )
    user_prompt = (
        f"User question:\n{question}\n\n"
        f"Specialized agent answers:\n{agents_block}\n\n"
        "Now provide a single final answer to the user, in your own words."
    )

    return llm_backend.chat(system_prompt, user_prompt)


# =====================================================================
# 4. Public entrypoint
# =====================================================================

def hybrid_multiagent_answer_question(
    question: str,
    config: RAGConfig,
    show_reasoning: bool = False,
) -> Tuple[str, List[Document], Optional[str], Dict[str, Any]]:
    """
    Hybrid Multi-Agent RAG:

    0. Intelligent Router (Legal vs General/Chitchat)
    1. LLM-based metadata extraction (from hybrid)
    2. Heuristic DB selection (from hybrid)
    3. Per-DB sub-agents, each using hybrid's two-phase retrieval
       with its own isolated 8000-char context window
    4. Supervisor synthesis merges sub-agent answers
    """
    llm_backend = LLMBackend(config)
    embedding_model = get_embedding_model(config)

    db_map = _get_vector_db_dirs(config)
    db_descriptions = _describe_databases(db_map, embedding_model)

    # ---- Step 0: Intelligent Router ----
    need_retrieval, decision_log = _decide_need_retrieval(
        question, llm_backend
    )

    meta: Dict[str, Any] = {}
    metadata_log = ""
    routing_log = ""
    all_docs: List[Document] = []
    chosen_db_names: List[str] = []

    # ---- General Knowledge / Chitchat path ----
    if not need_retrieval:
        system_prompt = (
            "You are a helpful and polite assistant.\n"
            "You can answer general knowledge questions (greetings, "
            "definitions of legal terms, theory) using your internal "
            "knowledge.\n"
            "HOWEVER, do not invent specific laws for Italy, Estonia or "
            "Slovenia if you don't have them.\n"
            "Be accurate and concise."
        )
        answer = llm_backend.chat(
            system_prompt, f"User Question: {question}"
        )

        reasoning_trace = None
        if show_reasoning:
            reasoning_trace = (
                "**Hybrid Multi-Agent**: Router decided NO RETRIEVAL needed.\n"
                f"**Log**: {decision_log}\n"
                "**Action**: Direct answer generated via internal knowledge."
            )
        return answer, [], reasoning_trace, {}

    # ---- Step 1: LLM-based metadata extraction ----
    meta, metadata_log = _extract_legal_metadata_from_query(
        question, llm_backend
    )
    metadata_filter = _build_metadata_filter(meta)

    # ---- Step 2: Heuristic DB selection ----
    chosen_db_names, routing_log = _heuristic_db_candidates(
        meta=meta,
        db_map=db_map,
        db_descriptions=db_descriptions,
    )

    # ---- Step 3: Per-DB Sub-Agents (hybrid retrieval) ----
    per_agent_answers: List[Tuple[str, str]] = []
    sub_traces: Dict[str, str] = {}

    for db_name in chosen_db_names:
        db_path = db_map[db_name]

        sub_answer, sub_docs, sub_log = _run_hybrid_sub_agent(
            question=question,
            db_name=db_name,
            db_path=db_path,
            embedding_model=embedding_model,
            config=config,
            metadata_filter=metadata_filter,
        )

        per_agent_answers.append((db_name, sub_answer))
        all_docs.extend(sub_docs)
        sub_traces[db_name] = sub_log

    # ---- Fallback: no sub-agents produced answers ----
    if not per_agent_answers:
        system_prompt = (
            "You are a legal assistant specialized in Divorce and "
            "Inheritance law for Italy, Estonia, and Slovenia.\n"
            "The user asked a legal question, but no relevant documents "
            "were found in any database.\n"
            "Politely state that you do not have access to specific "
            "documents for this query. Do not hallucinate legal rules."
        )
        answer = llm_backend.chat(
            system_prompt, f"Question: {question}"
        )

        reasoning_trace = None
        if show_reasoning:
            reasoning_trace = (
                "**Hybrid Multi-Agent**: No sub-agents produced results.\n"
                f"**Router**: {decision_log}\n"
                f"**Metadata**: {metadata_log}\n"
                f"**DB Routing**: {routing_log}\n"
                "**Action**: Fallback — no documents found."
            )
        return answer, [], reasoning_trace, meta

    # ---- Step 4: Supervisor Synthesis ----
    final_answer = _supervisor_synthesize(
        question=question,
        per_agent_answers=per_agent_answers,
        llm_backend=llm_backend,
    )

    # ---- Reasoning trace ----
    reasoning_trace: Optional[str] = None
    if show_reasoning:
        observation_str = _build_observation_text(
            used_db_names=chosen_db_names,
            docs=all_docs,
        )

        routing_info = (
            "Supervisor dispatched sub-agents: "
            + ", ".join(f"`{n}`" for n, _ in per_agent_answers)
        )

        per_agent_summary_lines = []
        for db_name, ans in per_agent_answers:
            short_ans = ans[:400] + "..." if len(ans) > 400 else ans
            per_agent_summary_lines.append(
                f"- **Agent `{db_name}`** answer snippet:\n  {short_ans}"
            )
        per_agent_summary = "\n".join(per_agent_summary_lines)

        subagent_log_block = ""
        for db_name, trace in sub_traces.items():
            subagent_log_block += (
                f"\n\n[Sub-agent `{db_name}` retrieval log]\n"
                f"```text\n{trace}\n```"
            )

        agent_config_log = _build_agent_config_log(
            config=config,
            db_map=db_map,
            db_descriptions=db_descriptions,
        )

        reasoning_trace = (
            f"**Hybrid Multi-Agent Trace**\n"
            f"---\n"
            f"1. **Router**: "
            f"{'LEGAL (Retrieve)' if need_retrieval else 'GENERAL'} "
            f"({decision_log})\n"
            f"2. **Metadata Extraction**:\n"
            f"```text\n{metadata_log}\n```\n"
            f"3. **DB Routing**: {routing_log}\n"
            f"4. **Sub-agents**: {routing_info}\n\n"
            f"**Observation**:\n{observation_str}\n\n"
            f"**Sub-agent outputs (summarized)**:\n{per_agent_summary}\n\n"
            f"**Sub-agent Retrieval Logs**:\n{subagent_log_block}\n\n"
            f"**Configuration**:\n```text\n{agent_config_log}\n```"
        )

    return final_answer, all_docs, reasoning_trace, meta
