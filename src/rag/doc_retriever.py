from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, csv_loader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from src.rag.embedder import _get_client, get_langchain_embedding_func

def get_doc_vectorstore() -> Chroma:
    client = _get_client()
    try:
        client.get_collection("documents")
    except ValueError:
        client.create_collection("documents")
        
    return Chroma(
        client=client,
        collection_name="documents",
        embedding_function=get_langchain_embedding_func()
    )

def ingest_document(file_path: str):
    path = Path(file_path)
    if path.suffix.lower() == '.pdf':
        loader = PyPDFLoader(file_path)
    elif path.suffix.lower() == '.csv':
        loader = csv_loader.CSVLoader(file_path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")
        
    docs = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    
    vectorstore = get_doc_vectorstore()
    vectorstore.add_documents(splits)
    return len(splits)

async def retrieve_documents(query: str, top_k: int = 5) -> list[Document]:
    vectorstore = get_doc_vectorstore()
    results = await vectorstore.asimilarity_search_with_score(query, k=top_k)
    docs = [doc for doc, score in results]
    return docs
