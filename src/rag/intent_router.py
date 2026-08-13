from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.engine.llm import llm_synth

intent_prompt = ChatPromptTemplate.from_template(
    "You are an intelligent router. Decide whether the user's question is about: "
    "1) The structured SQL database containing application data (return 'schema_rag') "
    "2) The unstructured uploaded documents, PDFs, or CSV files (return 'doc_rag'). "
    "Return only the exact string 'schema_rag' or 'doc_rag'."
    "\n\nQuestion: {question}"
)

intent_chain = intent_prompt | llm_synth | StrOutputParser()

async def route_intent(user_query: str) -> str:
    """Returns 'schema_rag' or 'doc_rag'."""
    res = await intent_chain.ainvoke({"question": user_query})
    return res.strip().lower()
