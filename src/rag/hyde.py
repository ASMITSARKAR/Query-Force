from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.engine.llm import llm_synth
from src.rag.router import route_relevant_schemas

hyde_prompt = ChatPromptTemplate.from_template(
    "Please write a hypothetical SQL query snippet that would answer the user's question. "
    "Do not include any explanations, just the SQL snippet. "
    "Question: {question}"
)

hyde_chain = hyde_prompt | llm_synth | StrOutputParser()

async def generate_hyde_and_retrieve(user_query: str) -> tuple[str, list[float]]:
    """
    1. Generates a hypothetical SQL query using a fast LLM.
    2. Performs retrieval using that hypothetical document.
    """
    hypothetical_sql = await hyde_chain.ainvoke({"question": user_query})
    
    enriched_hyde_query = f"{user_query}\n\nHypothetical SQL:\n{hypothetical_sql}"
    
    return await route_relevant_schemas(enriched_hyde_query)
