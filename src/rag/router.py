from src.rag.embedder import get_or_create_collection
from src.db.inspector import get_full_schema

from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from typing import List, Any
from src.engine.llm import llm_synth

class ChromaTableRetriever(BaseRetriever):
    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> List[Document]:
        collection = get_or_create_collection()
        results = collection.query(query_texts=[query], n_results=3)
        if not results['ids'] or not results['ids'][0]:
            return []
            
        docs = []
        for i, table_name in enumerate(results['ids'][0]):
            dist = results['distances'][0][i]
            conf = max(0.0, 1.0 - dist)
            docs.append(Document(page_content=table_name, metadata={"confidence": conf}))
        return docs

async def route_relevant_schemas(user_query: str, top_k: int = 3) -> tuple[str, list[float]]:
    """
    Uses MultiQueryRetriever to perform semantic search and retrieve the most relevant tables.
    Implements the G1 Adaptive top_k with Foreign Key expansion fallback.
    """
    retriever = ChromaTableRetriever()
    unique_docs = await retriever.ainvoke(user_query)
    
    if not unique_docs:
        return "", []
        
    retrieved_table_names = set(doc.page_content for doc in unique_docs)
    
    confidence_scores = [doc.metadata.get("confidence", 0.0) for doc in unique_docs]
    

    full_schema = await get_full_schema()
    
    expanded = True
    while expanded:
        expanded = False
        tables_to_add = set()
        
        for table_name in retrieved_table_names:
            if table_name in full_schema:
                for fk in full_schema[table_name]["foreign_keys"]:
                    fk_target = fk["table"]
                    if fk_target not in retrieved_table_names and fk_target not in tables_to_add:
                        tables_to_add.add(fk_target)
                        expanded = True
                        
        retrieved_table_names.update(tables_to_add)
        
    ddl_blocks = []
    for table_name in retrieved_table_names:
        if table_name in full_schema:
            ddl_blocks.append(f"-- Table: {table_name}\n{full_schema[table_name]['ddl']}")
            
    final_schema_context = "\n\n".join(ddl_blocks)
    
    return final_schema_context, confidence_scores

if __name__ == "__main__":
    import asyncio
    async def test():
        q = "Show me the top products purchased by customers in Canada"
        context, scores = await route_relevant_schemas(q)
        print(f"Confidence Scores (0-1): {scores}")
        print(f"\nConstructed Context sent to LLM:\n{context}")
    asyncio.run(test())
