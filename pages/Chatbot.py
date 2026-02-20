"""
Legal RAG Chatbot - Interactive Interface

Chatbot page for querying the legal RAG system with parameter configuration
and reasoning/sources visualization.
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime
import sys
import os

# 1. IMPORTANT: Load environment variables immediately
from dotenv import load_dotenv
load_dotenv()

# Debug (Optional): Check if keys were loaded
# If you see these errors, the name in .env is different or the file cannot be found
if not os.getenv("OPENROUTER_API_KEY"):
    st.error("⚠️ ERROR: The 'OPENROUTER_API_KEY' key was not found in the .env file!")
if not os.getenv("HUGGINGFACEHUB_API_TOKEN"):
    st.warning("⚠️ WARNING: The 'HUGGINGFACEHUB_API_TOKEN' key was not found (only needed for HuggingFace models).")

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from backend.config import RAGConfig
from backend.rag_pipeline import answer_question


# =====================================================================
# PAGE CONFIGURATION
# =====================================================================

st.set_page_config(
    page_title="Chatbot - Legal RAG",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# SESSION STATE INITIALIZATION
# =====================================================================

def init_session_state():
    """Initialize session state variables"""
    # Always reload config to update vector stores
    st.session_state.config = RAGConfig()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "conversation_log" not in st.session_state:
        st.session_state.conversation_log = []

# =====================================================================
# SIDEBAR CONFIGURATION
# =====================================================================

def render_sidebar():
    """Render configuration sidebar"""
    st.sidebar.title("⚙️ Configuration")

    config = st.session_state.config

    # Agent Mode Selection
    st.sidebar.subheader("Agent Architecture")

    agent_mode = st.sidebar.radio(
        "Select agent type:",
        options=[
            "Single Agent (ReAct)",
            "Multi-Agent (Supervisor)",
            "Hybrid (Metadata + Vector)",
            "Hybrid Multi-Agent",
        ],
        help=(
            "**Single Agent**: One agent with ReAct-style reasoning\n\n"
            "**Multi-Agent**: Supervisor coordinates specialized agents\n\n"
            "**Hybrid**: Metadata filtering + vector similarity (no ReAct)\n\n"
            "**Hybrid Multi-Agent**: Hybrid retrieval (LLM metadata + "
            "two-phase fallback) with per-DB sub-agents and supervisor synthesis"
        )
    )

    if agent_mode == "Single Agent (ReAct)":
        config.agentic_mode = "react"
        config.use_multiagent = False

    elif agent_mode == "Multi-Agent (Supervisor)":
        config.agentic_mode = "react"
        config.use_multiagent = True

    elif agent_mode == "Hybrid Multi-Agent":
        config.agentic_mode = "hybrid_multiagent"
        config.use_multiagent = False

    else:  # Hybrid (Metadata + Vector)
        config.agentic_mode = "hybrid_rag"
        config.use_multiagent = False

    # Show reasoning toggle
    show_reasoning = st.sidebar.checkbox(
        "Show reasoning trace",
        value=False,
        help="Display internal agent reasoning and retrieval logs"
    )

    st.sidebar.divider()

    # Retrieval Parameters
    st.sidebar.subheader("Retrieval Parameters")

    config.top_k = st.sidebar.slider(
        "Initial retrieval (top_k)",
        min_value=5,
        max_value=30,
        value=int(config.top_k),
        help="Number of documents to retrieve initially"
    )

    config.top_k_final = st.sidebar.slider(
        "Final documents (top_k_final)",
        min_value=3,
        max_value=20,
        value=int(config.top_k_final),
        help="Number of documents after reranking (mainly used by agentic modes)"
    )

    config.use_rerank = st.sidebar.checkbox(
        "Enable similarity reranking",
        value=bool(config.use_rerank),
        help="Rerank retrieved documents using a similarity metric"
    )

    if config.use_rerank:
        metric_options = ["cosine", "dot_product", "euclidean"]
        metric_labels = {
            "cosine": "Cosine Similarity",
            "dot_product": "Dot Product",
            "euclidean": "Euclidean Distance",
        }
        current_idx = metric_options.index(config.rerank_metric) if config.rerank_metric in metric_options else 0
        config.rerank_metric = st.sidebar.selectbox(
            "Reranking metric",
            options=metric_options,
            index=current_idx,
            format_func=lambda x: metric_labels[x],
            help=(
                "**Cosine**: angle-based similarity (scale-invariant)\n\n"
                "**Dot Product**: raw inner product (magnitude-sensitive)\n\n"
                "**Euclidean**: inverse of L2 distance (closer = more similar)"
            ),
        )

    st.sidebar.divider()

    # Model Information
    st.sidebar.subheader("Model Info")
    st.sidebar.text(f"LLM: {config.llm_model_name}")
    st.sidebar.text(f"Embeddings: {config.embedding_model_name}")

    # Vector Store Info
    st.sidebar.subheader("Vector Store Info")
    if config.vector_store_dirs:
        st.sidebar.text(f"Vector DBs: {len(config.vector_store_dirs)}")

        db_names = sorted([Path(db_path).name for db_path in config.vector_store_dirs])

        for db_name in db_names:
            if "_codes" in db_name:
                st.sidebar.caption(f" 📝 {db_name} (Codes)")
            elif "_cases" in db_name:
                st.sidebar.caption(f" ⚖️ {db_name} (Cases)")
            else:
                st.sidebar.caption(f" 📁 {db_name}")
    else:
        st.sidebar.warning("Vector DBs list is empty in config.")

    st.sidebar.divider()

    # Export conversation
    if st.sidebar.button("💾 Export Conversation"):
        export_conversation()

    # Clear conversation
    if st.sidebar.button("🗑️ Clear Conversation"):
        st.session_state.messages = []
        st.session_state.conversation_log = []
        st.rerun()

    return show_reasoning

# =====================================================================
# CHAT INTERFACE
# =====================================================================

def render_chat_interface(show_reasoning: bool):
    """Render main chat interface"""

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Show sources if available
            if "sources" in message and message["sources"]:
                with st.expander(f"📚 Sources ({len(message['sources'])} documents)"):
                    for i, doc in enumerate(message["sources"], 1):
                        meta = doc.metadata or {}
                        st.markdown(f"**Document {i}**")
                        db_name = meta.get("db_name", Path(meta.get("source", "")).parent.name)
                        st.caption(f"DB: {db_name}")
                        st.caption(f"Country: {meta.get('country', 'unknown')}")
                        st.caption(f"Law: {meta.get('law', 'unknown')}")
                        st.caption(f"Source: {Path(meta.get('source', '')).name}")

                        snippet = (doc.page_content or "")[:300] + "..."
                        st.text(snippet)
                        st.divider()

            # Show reasoning trace if available
            if "reasoning" in message and message["reasoning"]:
                with st.expander("🔍 Reasoning Trace"):
                    st.markdown(message["reasoning"])

            # Show extracted metadata
            if "metadata" in message and message["metadata"]:
                with st.expander("📋 Extracted Metadata"):
                    st.json(message["metadata"])

    # Chat input
    if prompt := st.chat_input("Ask a legal question..."):
        handle_user_input(prompt, show_reasoning)

def handle_user_input(prompt: str, show_reasoning: bool):
    """Handle user input and generate response"""

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                answer, docs, reasoning, metadata = answer_question(
                    question=prompt,
                    config=st.session_state.config,
                    show_reasoning=show_reasoning
                )

                st.markdown(answer)

                # Display Sources
                if docs:
                    with st.expander(f"📚 Sources ({len(docs)} documents)"):
                        for i, doc in enumerate(docs, 1):
                            meta = doc.metadata or {}
                            st.markdown(f"**Document {i}**")
                            db_name = meta.get("db_name", Path(meta.get("source", "")).parent.name)
                            st.caption(f"DB: {db_name}")
                            st.caption(f"Country: {meta.get('country', 'unknown')}")
                            st.caption(f"Law: {meta.get('law', 'unknown')}")
                            st.caption(f"Source: {Path(meta.get('source', '')).name}")

                            snippet = (doc.page_content or "")[:300] + "..."
                            st.text(snippet)
                            st.divider()

                # Display Reasoning
                if reasoning and show_reasoning:
                    with st.expander("🔍 Reasoning Trace"):
                        st.markdown(reasoning)

                # Display Metadata
                if metadata:
                    with st.expander("📋 Extracted Metadata"):
                        st.json(metadata)

                assistant_message = {
                    "role": "assistant",
                    "content": answer,
                    "sources": docs,
                }

                if reasoning:
                    assistant_message["reasoning"] = reasoning

                if metadata:
                    assistant_message["metadata"] = metadata

                st.session_state.messages.append(assistant_message)

                log_conversation_turn(prompt, answer, docs, metadata)

                st.rerun()

            except Exception as e:
                st.error(f"Error generating response: {e}")

# =====================================================================
# CONVERSATION LOGGING
# =====================================================================

def log_conversation_turn(question: str, answer: str, docs, metadata=None):
    """Log a conversation turn"""
    turn = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "answer": answer,
        "num_sources": len(docs) if docs else 0,
        "raw_sources": [
            {"page_content": d.page_content, "metadata": d.metadata}
            for d in (docs or [])
        ],
        "sources": [
            {
                "db_name": doc.metadata.get("db_name", Path(doc.metadata.get("source", "")).parent.name),
                "country": doc.metadata.get("country"),
                "law": doc.metadata.get("law"),
                "source": Path(doc.metadata.get("source", "")).name,
            }
            for doc in (docs or [])
        ],
    }

    if metadata:
        turn["extracted_metadata"] = metadata

    st.session_state.conversation_log.append(turn)

def export_conversation():
    """Export conversation log to JSON in the specific requested format,
    making source paths relative to the 'Contest_Data' directory.
    """
    if not st.session_state.conversation_log:
        st.sidebar.warning("No conversation to export")
        return

    config = st.session_state.config
    BASE_FOLDER_NAME = Path(config.data_base_dir).name  # 'Contest_Data'

    first_question = st.session_state.conversation_log[0]["question"]
    title = first_question[:60] + "..." if len(first_question) > 60 else first_question

    history = []

    for turn in st.session_state.conversation_log:
        history.append({"role": "user", "content": turn["question"]})

        contexts = []
        source_ids = []

        if "raw_sources" in turn:
            for source in turn["raw_sources"]:
                contexts.append(source.get("page_content", "").strip())

                meta = source.get("metadata", {})
                src_path_abs = meta.get("source", "unknown_source")

                try:
                    normalized_path = src_path_abs.replace("\\\\", "/")
                    start_index = normalized_path.find(BASE_FOLDER_NAME + "/")

                    if start_index != -1:
                        relative_path = normalized_path[start_index:]
                        source_ids.append(relative_path)
                    else:
                        source_ids.append(src_path_abs)
                except Exception:
                    source_ids.append(src_path_abs)

        assistant_message = {
            "role": "assistant",
            "content": turn["answer"],
            "contexts": contexts,
            "source_ids": source_ids,
            "ground_truth": ""
        }
        history.append(assistant_message)

    session_id = int(datetime.now().timestamp())

    session_data = {
        "id": session_id,
        "title": title,
        "history": history
    }

    final_export = [session_data]
    json_str = json.dumps(final_export, indent=2, ensure_ascii=False)

    st.sidebar.download_button(
        label="📥 Download JSON Session",
        data=json_str,
        file_name=f"chat_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )

# =====================================================================
# MAIN
# =====================================================================

def main():
    init_session_state()

    st.title("💬 Legal RAG Chatbot")
    st.caption("Ask questions about divorce and inheritance law across Italy, Estonia, and Slovenia")

    config = st.session_state.config
    if not config.vector_store_dirs:
        st.error(
            "⚠️ **Vector stores not found!**\n\n"
            "Please run `python build_vector_stores.py` first."
        )
        st.stop()

    show_reasoning = render_sidebar()
    render_chat_interface(show_reasoning)

    st.divider()
    st.caption("💡 **Tip**: Toggle 'Show reasoning trace' in the sidebar to see how the agent makes decisions.")

if __name__ == "__main__":
    main()
