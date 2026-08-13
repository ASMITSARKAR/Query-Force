from src.utils import suppress_chromadb_telemetry
suppress_chromadb_telemetry()

import json
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import chromadb
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.db.inspector import get_connection
from src.db.telemetry import get_recent_logs, init_telemetry_db
from src.memory.graph import graph
from src.memory.session_store import create_session, load_session
from src.memory.state import ConversationState
from langchain_core.messages import HumanMessage
from src.engine.llm import synthesize_results
from src.api.auth import verify_api_key
from src.engine.errors import QueryExecutionError, SecurityViolationError
from src.config import settings



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize required resources on startup."""
    await init_telemetry_db()
    yield


app = FastAPI(
    title="QueryForce API", 
    description="FastAPI Backend for QueryForce AI Analytics Engine",
    version="1.0.0",
    lifespan=lifespan
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Custom rate limit handler replacing slowapi's private _rate_limit_exceeded_handler."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"}
    )
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS.split(","), 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")



@app.get("/")
async def serve_ui():
    return FileResponse("ui/index.html")

class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Query cannot be empty')
        if len(v) > 2000:
            raise ValueError('Query exceeds maximum length of 2000 characters')
        return v

async def stream_generator(user_query: str, session_id: str | None = None):
    """
    Day 16: Server-Sent Events (SSE) generator.
    Yields JSON events piece-by-piece so the UI can show live progress.
    """
    try:
        state = await load_session(session_id) if session_id else None
        if not state:
            state = ConversationState(
                session_id=session_id or "default",
                messages=[],
                last_sql="",
                last_schema_context="",
                last_result_summary="",
                turn_count=0,
                rag_mode="schema_rag",
                enriched_query="",
                schema_context="",
                confidence_scores=[],
                sql="",
                results=[],
                answer="",
                error=None,
                retry_count=0
            )
            
        state["messages"].append(HumanMessage(content=user_query))

        yield f"event: status\ndata: {json.dumps({'step': 'router', 'msg': 'Routing to relevant tables...'})}\n\n"
        
        t0 = time.monotonic()
        result_state = await graph.ainvoke(state)
        latency_ms = round((time.monotonic() - t0) * 1000)
        
        err = result_state.get("error")
        if err:
            if "Confidence too low" in err:
                raise ValueError("Confidence too low. The question does not appear to be related to the database schema.")
            elif "Security violation" in err or "Blocked" in err:
                raise SecurityViolationError(err)
            else:
                raise QueryExecutionError(err)
        
        metadata_payload = {
            "sql": result_state.get("sql", ""),
            "latency_ms": latency_ms,
            "confidence": max(result_state.get("confidence_scores", [0.0])) if result_state.get("confidence_scores") else 0.0,
            "retries": result_state.get("retry_count", 0),
            "rag_mode": result_state.get("rag_mode", "schema_rag")
        }
        
        results = result_state.get("results", [])
        
        first_data = {
            "results": results[:50] if results else [],
            **metadata_payload
        }
        yield f"event: data_chunk\ndata: {json.dumps(first_data)}\n\n"
        
        if len(results) > 50:
            for i in range(50, len(results), 50):
                chunk = results[i:i+50]
                data_payload = {
                    "results": chunk,
                    **metadata_payload
                }
                yield f"event: data_chunk\ndata: {json.dumps(data_payload)}\n\n"
        
        yield f"event: status\ndata: {json.dumps({'step': 'llm', 'msg': 'Synthesizing final answer...'})}\n\n"
        
        answer = result_state.get("answer", "")
        
        yield f"event: complete\ndata: {json.dumps({'answer': answer})}\n\n"
        
    except ValueError as e: # Confidence rejection
        yield f"event: error\ndata: {json.dumps({'msg': str(e)})}\n\n"
    except SecurityViolationError as e:
        yield f"event: error\ndata: {json.dumps({'msg': f'Security Blocked: {str(e)}'})}\n\n"
    except QueryExecutionError as e:
        yield f"event: error\ndata: {json.dumps({'msg': f'Execution Error: {str(e)}'})}\n\n"
    except Exception as e:
        error_str = str(e)
        if '429' in error_str or 'rate_limit' in error_str.lower():
            yield f"event: error\ndata: {json.dumps({'msg': 'The AI service is temporarily overloaded. Please wait a moment and try again.'})}\n\n"
        elif '503' in error_str or '502' in error_str or 'unavailable' in error_str.lower():
            yield f"event: error\ndata: {json.dumps({'msg': 'The AI service is temporarily unavailable. Please try again shortly.'})}\n\n"
        elif 'api_key' in error_str.lower() or '401' in error_str:
            yield f"event: error\ndata: {json.dumps({'msg': 'AI service authentication failed. Please check the GROQ_API_KEY configuration.'})}\n\n"
        else:
            yield f"event: error\ndata: {json.dumps({'msg': f'Unexpected Error: {error_str}'})}\n\n"

@app.post("/api/v1/sessions", dependencies=[Depends(verify_api_key)])
async def create_new_session():
    session_id = await create_session()
    return {"session_id": session_id}

@app.get("/api/v1/sessions/{session_id}/history", dependencies=[Depends(verify_api_key)])
async def get_session_history(session_id: str):
    state = await load_session(session_id)
    if not state:
        return JSONResponse(status_code=404, content={"detail": "Session not found"})
    from langchain_core.messages import message_to_dict
    messages = [message_to_dict(m) for m in state.get("messages", [])]
    return {"messages": messages}

@app.post("/api/v1/stream", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def stream_query(req: QueryRequest, request: Request):
    """
    The main streaming endpoint for the frontend.
    """
    return StreamingResponse(
        stream_generator(req.query, req.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx proxy buffering
        }
    )

@app.get("/api/v1/health", dependencies=[Depends(verify_api_key)])
async def health_check():
    """
    Day 15: Basic health endpoint to verify the API, Database, and Vector Store are reachable.
    """
    db_status = "unreachable"
    try:
        conn = await get_connection()
        try:
            await conn.execute("SELECT 1")
            db_status = "healthy"
        finally:
            await conn.close()
    except Exception as e:
        db_status = f"error: {str(e)}"
        
    return {
        "status": "online",
        "database": db_status,
        "chromadb_version": chromadb.__version__
    }

@app.get("/api/v1/history", dependencies=[Depends(verify_api_key)])
async def query_history(limit: int = 20):
    """
    Day 16: Returns recent telemetry logs as JSON.
    Powers the frontend's telemetry panel.
    """
    logs = await get_recent_logs(limit=limit)
    return {"logs": logs}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=True)