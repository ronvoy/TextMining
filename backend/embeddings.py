from typing import List

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

from backend.config import RAGConfig

# BGE models benefit from a query instruction prefix at retrieval time.
# The instruction is prepended only when encoding queries (not passages).
# See: https://huggingface.co/BAAI/bge-base-en-v1.5
_BGE_QUERY_INSTRUCTION = (
    "Represent this sentence for searching relevant passages: "
)


class _BGEEmbeddings(HuggingFaceEmbeddings):
    """
    Thin wrapper around HuggingFaceEmbeddings that prepends the BGE
    query instruction at *query time only*.

    Newer versions of langchain-huggingface use a strict Pydantic v2 model
    that forbids extra constructor fields (such as `query_instruction`), so
    the prefix is applied manually in embed_query() instead.
    """

    _instruction: str = _BGE_QUERY_INSTRUCTION

    def embed_query(self, text: str) -> List[float]:
        return super().embed_query(self._instruction + text)


def get_embedding_model(config: RAGConfig) -> Embeddings:
    """
    Returns a LangChain Embeddings object based on config.

    - embedding_provider == "huggingface":
        Uses HuggingFaceEmbeddings with device forced to CPU to avoid
        issues like "Cannot copy out of meta tensor; no data!" on some setups.
        For private/gated models, set HUGGINGFACEHUB_API_TOKEN or HF_TOKEN.

    BGE-specific behaviour:
        BAAI/bge-* models require a query_instruction prefix for retrieval
        queries.  Passage embeddings (index time) do NOT use the prefix.
        _BGEEmbeddings handles this by overriding embed_query() only.
    """
    model_name = config.embedding_model_name
    is_bge = "bge" in model_name.lower()

    base_kwargs = dict(
        model_name=model_name,
        model_kwargs={"device": "cpu"},                # Force CPU – avoids meta-tensor errors
        encode_kwargs={"normalize_embeddings": True},  # L2-normalise → cosine via dot product
    )

    if is_bge:
        return _BGEEmbeddings(**base_kwargs)

    return HuggingFaceEmbeddings(**base_kwargs)

