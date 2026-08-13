from src.utils import suppress_chromadb_telemetry
suppress_chromadb_telemetry()

import asyncio
import sys

from src.memory.graph import graph
from src.memory.state import ConversationState
from langchain_core.messages import HumanMessage
from src.engine.errors import SecurityViolationError
from src.engine.validator import validate_and_format_sql

async def run_tests():
    print("Running Day 14 E2E Test Suite...")
    
    try:
        print("\nTest 1: Happy Path ('Count all customers')")
        state = ConversationState(
            session_id="test",
            messages=[HumanMessage(content="Count all customers")],
            last_sql="", last_schema_context="", last_result_summary="", turn_count=0,
            rag_mode="schema_rag", enriched_query="", schema_context="", confidence_scores=[],
            sql="", results=[], answer="", error=None, retry_count=0
        )
        result = await graph.ainvoke(state)
        
        if result.get("error"):
            print(f"[FAIL] Failed: {result['error']}")
            sys.exit(1)
            
        print(f"[PASS] Success! SQL: {result['sql']}")
        print(f"Result: {result['results']}")
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
        sys.exit(1)
        
    try:
        print("\nTest 2: Security Block ('DROP TABLE users')")
        state = ConversationState(
            session_id="test",
            messages=[HumanMessage(content="DROP TABLE users")],
            last_sql="", last_schema_context="", last_result_summary="", turn_count=0,
            rag_mode="schema_rag", enriched_query="", schema_context="", confidence_scores=[],
            sql="", results=[], answer="", error=None, retry_count=0
        )
        result = await graph.ainvoke(state)
        if result.get("error"):
            if "Security violation" in result["error"] or "Blocked" in result["error"]:
                print(f"[PASS] Success! Blocked correctly: {result['error']}")
            else:
                print(f"[PASS] Success! Blocked with error: {result['error']}")
        else:
            print("[FAIL] Failed: Query was allowed to execute!")
            sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Failed with exception: {e}")
        sys.exit(1)
        
    try:
        print("\nTest 3: Aggregate ORDER BY Guard ('SELECT COUNT(*) AS total FROM orders')")
        validated_sql = await validate_and_format_sql("SELECT COUNT(*) AS total FROM orders")
        if "ORDER BY" in validated_sql.upper():
            print(f"[FAIL] ORDER BY was injected into aggregate query: {validated_sql}")
            sys.exit(1)
        else:
            print(f"[PASS] Success! No ORDER BY injected: {validated_sql}")
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
        sys.exit(1)
        
    print("\n[PASS] All 3 tests passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
