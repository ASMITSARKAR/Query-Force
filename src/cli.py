from src.utils import suppress_chromadb_telemetry
suppress_chromadb_telemetry()

import asyncio
from tabulate import tabulate

from src.engine.orchestrator import execute_pipeline_with_retry
from src.db.telemetry import init_telemetry_db
from src.engine.errors import QueryExecutionError, SecurityViolationError

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
CYAN = "\033[96m"

def colorize_sql(sql: str) -> str:
    """Applies basic ANSI color coding to SQL keywords for better readability."""
    import re as _re
    keywords_green = ["SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "LIMIT", "WITH", "AS"]
    keywords_yellow = ["INNER JOIN", "LEFT JOIN", "JOIN", "ON", "AND", "OR"]
    
    all_keywords = [(kw, GREEN) for kw in sorted(keywords_green, key=len, reverse=True)] + \
                   [(kw, YELLOW) for kw in sorted(keywords_yellow, key=len, reverse=True)]
    
    colored_sql = sql
    for kw, color in all_keywords:
        pattern = _re.compile(rf'\b{_re.escape(kw)}\b', _re.IGNORECASE)
        colored_sql = pattern.sub(f"{color}{kw}{RESET}", colored_sql)
        
    return colored_sql

async def main_loop():
    await init_telemetry_db()
    
    print(f"{CYAN}=========================================={RESET}")
    print(f"{CYAN}  QueryForce CLI (RAG Vector Router)      {RESET}")
    print(f"{CYAN}=========================================={RESET}")
    print("Initializing Vector Store RAG Router...")
    
    print(f"{GREEN}Ready! Type 'exit' to quit.{RESET}\n")
    
    while True:
        try:
            user_query = input(f"{CYAN}QueryForce > {RESET}")
            if user_query.lower() in ('exit', 'quit'):
                print("Goodbye!")
                break
            if not user_query.strip():
                continue
            
            try:
                result = await execute_pipeline_with_retry(user_query)
                
                print(f"{YELLOW}RAG Confidence: {result['confidence'] * 100:.1f}%{RESET}")
                
                if result['retries'] > 0:
                    print(f"{YELLOW}Warning: AI generated invalid SQL initially. Resolved after {result['retries']} retries.{RESET}")
                
                print(f"\n{colorize_sql(result['sql'])}\n")
                
                first_chunk = result.get('first_chunk', [])
                all_results = list(first_chunk)
                async for chunk in result['results_stream']:
                    all_results.extend(chunk)
                    
                if not all_results:
                    print("Result: No rows returned.")
                else:
                    headers = all_results[0].keys()
                    rows = [list(r.values()) for r in all_results]
                    print(tabulate(rows, headers=headers, tablefmt="pretty"))
                    
                print(f"\n{CYAN}Execution Time: {result['latency_ms']:.0f} ms{RESET}\n")
                
            except ValueError as e:
                print(f"\n{RED}{e}{RESET}\n")
            except QueryExecutionError as e:
                print(f"\n{RED}Execution Error: {e}{RESET}\n")
            except SecurityViolationError as e:
                print(f"\n{RED}Security Blocked: {e}{RESET}\n")
            except Exception as e:
                print(f"\n{RED}Unexpected Error: {e}{RESET}\n")

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\nExiting...")
