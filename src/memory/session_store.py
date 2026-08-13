import uuid
import boto3
import json
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.messages import BaseMessage, messages_from_dict, message_to_dict
from src.config import settings
from src.memory.state import ConversationState

try:
    dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
    table = dynamodb.Table(settings.DYNAMODB_SESSION_TABLE)
except Exception:
    # Fallback for local testing or when AWS is not configured
    table = None

_local_store = {}

async def create_session() -> str:
    return str(uuid.uuid4())

async def load_session(session_id: str) -> Optional[ConversationState]:
    if not table:
        return _local_store.get(session_id)
        
    try:
        response = table.get_item(Key={'session_id': session_id})
        item = response.get('Item')
        
        if not item:
            return None
            
        state: ConversationState = {
            "session_id": item["session_id"],
            "messages": messages_from_dict(json.loads(item.get("messages", "[]"))),
            "last_sql": item.get("last_sql", ""),
            "last_schema_context": item.get("last_schema_context", ""),
            "last_result_summary": item.get("last_result_summary", ""),
            "turn_count": item.get("turn_count", 0),
            "rag_mode": item.get("rag_mode", "schema_rag"),
            "enriched_query": "",
            "schema_context": "",
            "confidence_scores": [],
            "sql": "",
            "results": [],
            "answer": "",
            "error": None,
            "retry_count": 0
        }
        return state
    except Exception as e:
        print(f"Error loading session: {e}")
        return _local_store.get(session_id)

async def save_session(state: ConversationState) -> None:
    if not table:
        _local_store[state["session_id"]] = state
        return
        
    try:
        expires_at = int((datetime.now() + timedelta(hours=24)).timestamp())
        
        item = {
            'session_id': state["session_id"],
            'messages': json.dumps([message_to_dict(m) for m in state.get("messages", [])]),
            'last_sql': state.get("sql", state.get("last_sql", "")),
            'last_schema_context': state.get("schema_context", state.get("last_schema_context", "")),
            'last_result_summary': str(state.get("results", []))[:500] if state.get("results") else state.get("last_result_summary", ""),
            'turn_count': state.get("turn_count", 0) + 1,
            'rag_mode': state.get("rag_mode", "schema_rag"),
            'expires_at': expires_at
        }
        table.put_item(Item=item)
    except Exception as e:
        print(f"Error saving session: {e}")
        _local_store[state["session_id"]] = state
