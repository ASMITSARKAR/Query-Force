from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class ConversationState(TypedDict):
    session_id: str
    messages: Annotated[list[BaseMessage], add_messages]
    last_sql: str
    last_schema_context: str
    last_result_summary: str
    turn_count: int
    enriched_query: str
    schema_context: str
    confidence_scores: list[float]
    sql: str
    results: list[dict]
    answer: str
    error: str | None
    retry_count: int
    rag_mode: str  # 'schema_rag' | 'doc_rag'
