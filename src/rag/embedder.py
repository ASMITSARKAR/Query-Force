import os
os.environ["CHROMA_TELEMETRY"] = "False" # Suppress the known ChromaDB bug
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from pathlib import Path
from src.config import settings

_chroma_client = None
_embedding_func = None

def _get_client():
    """Returns a singleton ChromaDB PersistentClient."""
    global _chroma_client
    if _chroma_client is None:
        chroma_dir = Path(settings.CHROMA_DIR).absolute().as_posix()
        _chroma_client = chromadb.PersistentClient(
            path=chroma_dir,
            settings=Settings(anonymized_telemetry=False)
        )
    return _chroma_client

def _get_embedding_func():
    """Returns a singleton DefaultEmbeddingFunction (ONNX)."""
    global _embedding_func
    if _embedding_func is None:
        _embedding_func = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_func

class LangchainEmbeddingAdapter:
    """Adapts Chroma's embedding function to LangChain's Embeddings interface."""
    def __init__(self, chroma_ef):
        self.chroma_ef = chroma_ef
        
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.chroma_ef(texts)
        
    def embed_query(self, text: str) -> list[float]:
        return self.chroma_ef([text])[0]

def get_langchain_embedding_func():
    return LangchainEmbeddingAdapter(_get_embedding_func())

def get_or_create_collection(collection_name: str = "schema_catalog") -> chromadb.Collection:
    """
    Initializes ChromaDB PersistentClient and returns the target collection.
    Applies the G3 Fix to ensure cosine space is used for 0-1 bounded confidence scores.
    Uses module-level singletons for the client and embedding function to avoid
    expensive re-initialization on every query.
    """
    client = _get_client()
    embedding_func = _get_embedding_func()
    
    try:
        collection = client.get_collection(
            name=collection_name,
            embedding_function=embedding_func
        )
    except ValueError:
        collection = client.create_collection(
            name=collection_name,
            embedding_function=embedding_func,
            metadata={
                "hnsw:space": "cosine",
                "collection_version": "v1.0" # Track schema generation versions
            }
        )
        
    return collection

if __name__ == "__main__":
    print("Initializing Vector Store...")
    col = get_or_create_collection()
    print(f"Collection '{col.name}' loaded successfully with {col.count()} documents.")
