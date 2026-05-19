"""
flask_app.py — Native WSGI Flask app replacing the Streamlit interface.

Routes:
  GET  /               Landing page
  GET  /chatbot        Chat interface
  GET  /evaluation     RAGAS evaluation page
  POST /api/config     Save sidebar config to session
  POST /api/chat       Ask a question → JSON response
  POST /api/clear      Clear conversation
  GET  /api/export     Download conversation as JSON
  POST /api/evaluate   Run RAGAS evaluation
"""

import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Env setup before any backend import ──────────────────────────────────────
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import (
    Flask, render_template, request, jsonify,
    send_file, session
)
from flask_session import Session

from backend.config import RAGConfig
from backend.rag_pipeline import answer_question

# ── App setup ─────────────────────────────────────────────────────────────────

APP_DIR    = os.path.dirname(os.path.abspath(__file__))
APP_PORT   = int(os.environ.get("APP_PORT", 5000))
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Server-side session (filesystem) avoids the 4 KB cookie limit
app.config["SESSION_TYPE"]           = "filesystem"
app.config["SESSION_FILE_DIR"]       = os.path.join(APP_DIR, ".flask_sessions")
app.config["SESSION_PERMANENT"]      = False
app.config["SESSION_USE_SIGNER"]     = True
app.config["SESSION_FILE_THRESHOLD"] = 200

Session(app)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_docs(docs):
    """Convert LangChain Document objects to plain dicts."""
    if not docs:
        return []
    out = []
    for doc in docs:
        meta = doc.metadata or {}
        out.append({
            "db_name": meta.get("db_name", Path(meta.get("source", "")).parent.name),
            "country": meta.get("country", "unknown"),
            "law":     meta.get("law", "unknown"),
            "source":  Path(meta.get("source", "")).name,
            "snippet": (doc.page_content or "")[:300],
            "page_content": doc.page_content or "",
            "metadata": {k: str(v) for k, v in meta.items()},
        })
    return out


def _get_config() -> RAGConfig:
    """Build RAGConfig from the stored session params."""
    config = RAGConfig()
    p = session.get("config_params", {})

    agent_mode = p.get("agent_mode", "single")
    if agent_mode == "single":
        config.agentic_mode  = "react"
        config.use_multiagent = False
    elif agent_mode == "multi":
        config.agentic_mode  = "react"
        config.use_multiagent = True
    elif agent_mode == "hybrid_multi":
        config.agentic_mode  = "hybrid_multiagent"
        config.use_multiagent = False
    else:  # "hybrid"
        config.agentic_mode  = "hybrid_rag"
        config.use_multiagent = False

    config.top_k        = int(p.get("top_k", 30))
    config.top_k_final  = int(p.get("top_k_final", 10))
    config.use_rerank   = bool(p.get("use_rerank", True))
    config.rerank_metric = p.get("rerank_metric", "cosine")
    return config


_DEFAULT_PARAMS = {
    "agent_mode":    "single",
    "top_k":         30,
    "top_k_final":   10,
    "use_rerank":    True,
    "rerank_metric": "cosine",
    "show_reasoning": False,
}

# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def home():
    config = RAGConfig()
    return render_template("home.html", num_dbs=len(config.vector_store_dirs))


@app.route("/chatbot")
def chatbot():
    config   = RAGConfig()
    params   = session.get("config_params", _DEFAULT_PARAMS)
    db_names = sorted([Path(p).name for p in config.vector_store_dirs])
    return render_template(
        "chatbot.html",
        params=params,
        db_names=db_names,
        llm_model=config.llm_model_name,
        embedding_model=config.embedding_model_name,
    )


@app.route("/evaluation")
def evaluation():
    return render_template("evaluation.html")


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["POST"])
def save_config():
    data = request.json or {}
    session["config_params"] = {
        "agent_mode":    data.get("agent_mode",    "single"),
        "top_k":         int(data.get("top_k",         30)),
        "top_k_final":   int(data.get("top_k_final",   10)),
        "use_rerank":    bool(data.get("use_rerank",   True)),
        "rerank_metric": data.get("rerank_metric", "cosine"),
        "show_reasoning": bool(data.get("show_reasoning", False)),
    }
    session.modified = True
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    data     = request.json or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Empty question"}), 400

    # Caller may push updated params together with the message
    if "config" in data:
        session["config_params"] = data["config"]
        session.modified = True

    show_reasoning = session.get("config_params", {}).get("show_reasoning", False)
    config = _get_config()

    try:
        answer, docs, reasoning, metadata = answer_question(
            question=question,
            config=config,
            show_reasoning=show_reasoning,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    serialized = _serialize_docs(docs)

    # Persist conversation log (compact: no full page_content in "sources" list)
    log = session.get("conversation_log", [])
    log.append({
        "timestamp": datetime.now().isoformat(),
        "question":  question,
        "answer":    answer,
        "num_sources": len(serialized),
        "raw_sources": [
            {
                "page_content": doc.page_content,
                "metadata": {k: str(v) for k, v in (doc.metadata or {}).items()},
            }
            for doc in (docs or [])
        ],
        "sources":           serialized,
        "extracted_metadata": metadata,
    })
    session["conversation_log"] = log
    session.modified = True

    return jsonify({
        "answer":    answer,
        "sources":   serialized,
        "reasoning": reasoning,
        "metadata":  metadata,
    })


@app.route("/api/clear", methods=["POST"])
def clear():
    session["conversation_log"] = []
    session.modified = True
    return jsonify({"ok": True})


@app.route("/api/export")
def export():
    log = session.get("conversation_log", [])
    if not log:
        return jsonify({"error": "No conversation to export"}), 400

    config          = RAGConfig()
    BASE_FOLDER     = Path(config.data_base_dir).name
    first_q         = log[0]["question"]
    title           = first_q[:60] + ("..." if len(first_q) > 60 else "")
    history         = []

    for turn in log:
        history.append({"role": "user", "content": turn["question"]})
        contexts   = []
        source_ids = []
        for src in (turn.get("raw_sources") or []):
            contexts.append(src.get("page_content", "").strip())
            raw_path = (src.get("metadata") or {}).get("source", "unknown_source")
            try:
                norm = raw_path.replace("\\\\", "/")
                idx  = norm.find(BASE_FOLDER + "/")
                source_ids.append(norm[idx:] if idx != -1 else raw_path)
            except Exception:
                source_ids.append(raw_path)
        history.append({
            "role":         "assistant",
            "content":      turn["answer"],
            "contexts":     contexts,
            "source_ids":   source_ids,
            "ground_truth": "",
        })

    payload = [{
        "id":      int(datetime.now().timestamp()),
        "title":   title,
        "history": history,
    }]
    buf = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False).encode())
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name="conversation.json",
    )


@app.route("/api/evaluate", methods=["POST"])
def evaluate_api():
    """Run RAGAS evaluation on the submitted rows."""
    from datasets import Dataset
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import (
        faithfulness, answer_relevancy,
        context_precision, context_recall, answer_correctness,
    )
    from langchain_openai import ChatOpenAI
    from langchain_huggingface import HuggingFaceEmbeddings
    import pandas as pd

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENROUTER_API_KEY not set in environment"}), 500

    rows = (request.json or {}).get("rows", [])
    if not rows:
        return jsonify({"error": "No rows provided"}), 400

    llm = ChatOpenAI(
        model="openai/gpt-4o-mini",
        temperature=0,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://legal-rag-chatbot.local",
            "X-Title": "Legal RAG Evaluation",
        },
    )

    try:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception:
        import torch
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": torch.device("cpu")},
            encode_kwargs={"normalize_embeddings": True},
        )

    ragas_rows = []
    has_gt     = False
    for row in rows:
        contexts = [c.strip() for c in row.get("contexts", []) if c.strip()] or ["No context retrieved"]
        gt       = (row.get("ground_truth") or "").strip()
        if gt:
            has_gt = True
        ragas_rows.append({
            "question":     row["question"],
            "answer":       row["answer"],
            "contexts":     contexts,
            "ground_truth": gt,
        })

    df = pd.DataFrame(ragas_rows).dropna(subset=["question", "answer"])
    if df.empty:
        return jsonify({"error": "No valid rows after filtering"}), 400

    dataset = Dataset.from_pandas(df)
    metrics = [faithfulness, answer_relevancy]
    if has_gt:
        metrics += [context_precision, context_recall, answer_correctness]

    try:
        results    = ragas_evaluate(dataset=dataset, metrics=metrics, llm=llm, embeddings=embeddings, raise_exceptions=False)
        df_results = results.to_pandas()
        metric_cols = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness"]
        scores  = {c: round(float(df_results[c].mean()), 4) for c in metric_cols if c in df_results.columns}
        per_row = df_results[[c for c in metric_cols if c in df_results.columns]].to_dict(orient="records")
        return jsonify({"scores": scores, "per_row": per_row})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
