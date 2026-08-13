import time
from typing import Literal
from langgraph.graph import StateGraph, END
from src.memory.state import ConversationState
from src.config import settings
from src.rag.rules import inject_business_rules
from src.rag.router import route_relevant_schemas
from src.rag.hyde import generate_hyde_and_retrieve
from src.rag.intent_router import route_intent
from src.rag.doc_retriever import retrieve_documents
from src.engine.llm import generate_sql_only, synthesize_results
from src.engine.validator import validate_and_format_sql
from src.db.executor import execute_readonly_query
from src.engine.errors import SecurityViolationError
from src.db.telemetry import log_execution_metric
from langchain_core.messages import HumanMessage, AIMessage

async def intent_router_node(state: ConversationState) -> dict:
    user_query = state["messages"][-1].content if state["messages"] else ""
    rag_mode = await route_intent(user_query)
    return {"rag_mode": rag_mode}

async def rules_node(state: ConversationState) -> dict:
    user_query = state["messages"][-1].content if state["messages"] else ""
    enriched = inject_business_rules(user_query, state.get("rag_mode", "schema_rag"))
    return {"enriched_query": enriched}

async def schema_rag_node(state: ConversationState) -> dict:
    ctx, scores = await route_relevant_schemas(state["enriched_query"])
    return {"schema_context": ctx, "confidence_scores": scores}

async def hyde_rag_node(state: ConversationState) -> dict:
    ctx, scores = await generate_hyde_and_retrieve(state["enriched_query"])
    return {"schema_context": ctx, "confidence_scores": scores}

async def llm_sql_node(state: ConversationState) -> dict:
    retry_ctx = state.get("error", "") if state.get("retry_count", 0) > 0 else ""
    
    messages = state.get("messages", [])
    prior_context = "\n".join([f"{m.type.capitalize()}: {m.content}" for m in messages[:-1]]) if len(messages) > 1 else ""

    sql = await generate_sql_only(
        prompt=state["enriched_query"], 
        schema_context=state["schema_context"], 
        retry_context=retry_ctx,
        prior_context=prior_context
    )
    return {"sql": sql}

async def ast_node(state: ConversationState) -> dict:
    try:
        secure_sql = await validate_and_format_sql(state["sql"])
        return {"sql": secure_sql, "error": None}
    except SecurityViolationError as e:
        return {"error": f"FATAL:{str(e)}"}
    except Exception as e:
        retry_count = state.get("retry_count", 0) + 1
        if retry_count > settings.MAX_RETRIES:
            return {"error": f"FATAL:Max retries exceeded. {str(e)}"}
        return {"error": str(e), "retry_count": retry_count}

async def exec_node(state: ConversationState) -> dict:
    try:
        gen = execute_readonly_query(state["sql"])
        results = [chunk async for chunk in gen]
        flat_results = [item for sublist in results for item in sublist]
        return {"results": flat_results}
    except Exception as e:
        return {"error": f"FATAL:Execution error: {str(e)}"}

async def doc_rag_node(state: ConversationState) -> dict:
    user_query = state["messages"][-1].content if state["messages"] else ""
    docs = await retrieve_documents(user_query)
    results = [{"content": doc.page_content, "metadata": doc.metadata} for doc in docs]
    return {"results": results, "sql": "N/A (Document RAG)"}

async def synth_node(state: ConversationState) -> dict:
    user_query = state["messages"][-1].content if state["messages"] else ""
    if state.get("error") and state["error"].startswith("FATAL:"):
        ans = f"Error: {state['error'][6:]}"
    else:
        messages = state.get("messages", [])
        prior_context = "\n".join([f"{m.type.capitalize()}: {m.content}" for m in messages[:-1]]) if len(messages) > 1 else ""
        
        ans = await synthesize_results(user_query, state.get("sql", ""), state.get("results", []), prior_context=prior_context)
    
    return {"answer": ans, "messages": [AIMessage(content=ans)]}

async def memory_node(state: ConversationState) -> dict:
    from src.memory.session_store import save_session
    await save_session(state)
    return {"session_id": state.get("session_id", "default")}

def mode_router(state: ConversationState) -> Literal["schema_rag", "doc_rag"]:
    return state.get("rag_mode", "schema_rag")

def confidence_router(state: ConversationState) -> Literal["low", "ok"]:
    max_conf = max(state.get("confidence_scores", [0.0])) if state.get("confidence_scores") else 0.0
    if max_conf < settings.HYDE_CONFIDENCE_THRESHOLD:
        return "low"
    return "ok"

def security_router(state: ConversationState) -> Literal["ok", "blocked", "fatal"]:
    err = state.get("error")
    if not err:
        return "ok"
    if err.startswith("FATAL:"):
        return "fatal"
    return "blocked"

builder = StateGraph(ConversationState)
builder.add_node("intent_router", intent_router_node)
builder.add_node("rules", rules_node)
builder.add_node("schema_retriever", schema_rag_node)
builder.add_node("hyde_retriever", hyde_rag_node)
builder.add_node("llm_sql", llm_sql_node)
builder.add_node("ast_validate", ast_node)
builder.add_node("execute", exec_node)
builder.add_node("doc_retriever", doc_rag_node)
builder.add_node("synthesize", synth_node)
builder.add_node("save_memory", memory_node)

builder.set_entry_point("intent_router")
builder.add_conditional_edges("intent_router", mode_router,
    {"schema_rag": "rules", "doc_rag": "doc_retriever"})
builder.add_edge("rules", "schema_retriever")
builder.add_conditional_edges("schema_retriever", confidence_router,
    {"low": "hyde_retriever", "ok": "llm_sql"})
builder.add_edge("hyde_retriever", "llm_sql")
builder.add_edge("llm_sql", "ast_validate")
builder.add_conditional_edges("ast_validate", security_router,
    {"ok": "execute", "blocked": "llm_sql", "fatal": END})
builder.add_edge("execute", "synthesize")
builder.add_edge("doc_retriever", "synthesize")
builder.add_edge("synthesize", "save_memory")
builder.add_edge("save_memory", END)

graph = builder.compile()
