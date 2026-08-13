import re
import asyncio
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from src.config import settings
from src.db.telemetry import log_execution_metric
from src.engine.validator import validate_and_format_sql
from src.engine.errors import SecurityViolationError

llm_sql = ChatGroq(
    model=settings.LLM_SQL_MODEL,
    temperature=0.0,
    api_key=settings.GROQ_API_KEY.get_secret_value(),
    max_tokens=1024
)

llm_sql_variety = ChatGroq(
    model=settings.LLM_SQL_MODEL,
    temperature=0.3,
    api_key=settings.GROQ_API_KEY.get_secret_value(),
    max_tokens=1024
)

llm_synth = ChatGroq(
    model=settings.LLM_SYNTH_MODEL,
    temperature=0.3,
    api_key=settings.GROQ_API_KEY.get_secret_value(),
    max_tokens=256
)

def extract_sql(raw_output: str) -> str:
    """
    G4 - Three-tier extraction strategy to prevent LLM chattiness from crashing the AST parser.
    """
    fence_pattern = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
    match = fence_pattern.search(raw_output)
    if match:
        return match.group(1).strip()
        
    keyword_pattern = re.compile(r"\b(SELECT|WITH)\b.*?(?:;|$)", re.IGNORECASE | re.DOTALL)
    match = keyword_pattern.search(raw_output)
    if match:
        return match.group(0).strip()
        
    # Tier 3: Fallback - Strip fences manually if they were malformed
    return re.sub(r"```(?:sql)?|```", "", raw_output).strip()

async def generate_sql_only(prompt: str, schema_context: str, retry_context: str = "", prior_context: str = "") -> str:
    system_prompt = (
        "You are an expert SQLite SQL generator. "
        "Your ONLY job is to write a syntactically correct SQLite SELECT query that answers the user's question, "
        "using ONLY the columns that literally exist in the provided schema. "
        "CRITICAL RULE: Never invent, alias, or rename columns to match the user's wording if those columns do not exist. "
        "If the user asks for 'profit', 'margin', 'cost', or any metric whose column does not exist in the schema, "
        "you MUST output exactly this and nothing else: SELECT 'METRIC_NOT_FOUND' AS error "
        "Do NOT use MySQL, PostgreSQL, or SQL Server specific functions. Stick strictly to SQLite. "
        "IMPORTANT: SQLite is case-sensitive. When doing string equality comparisons, ALWAYS use COLLATE NOCASE or LOWER(). "
        "Do NOT include any explanatory text. Output ONLY the SQL code."
    )
    
    context_str = ""
    if prior_context:
        context_str = f"Prior Conversation:\n{prior_context}\n\n"
        
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", f"{context_str}Schema:\n{{schema}}\n\nQuestion: {{question}}")
    ])
    
    messages = prompt_template.format_messages(schema=schema_context, question=prompt)
    
    if retry_context:
        truncated_error = str(retry_context)[:200]
        messages[-1].content += f"\n\nPrevious attempt failed with:\n{truncated_error}...\nPlease correct the SQL."
        
    responses = await asyncio.gather(
        llm_sql.ainvoke(messages),
        llm_sql_variety.ainvoke(messages)
    )
    
    candidates = [extract_sql(r.content) for r in responses]
    
    best_candidate = candidates[0]
    for sql in candidates:
        try:
            await validate_and_format_sql(sql)
            best_candidate = sql
            break
        except Exception:
            continue
    
    if retry_context:
        await log_execution_metric(
            prompt=f"[RETRY RAW] {prompt}",
            error_trace=best_candidate[:500]
        )
        
    return best_candidate

async def synthesize_results(prompt: str, sql: str, results: list[dict], prior_context: str = "") -> str:
    # Guard: LLM flagged a missing metric
    if results and list(results[0].values()) == ['METRIC_NOT_FOUND']:
        return "I don't have that metric in the database. The available financial column is `total_amount` (order revenue). There is no profit, margin, or cost column in the schema."
    
    # Guard: NULL to $0 Coercion — only trigger on truly empty/all-null results
    if not results:
        return "No matching data found for this query."
    
    first_row = results[0]
    if all(val is None for val in first_row.values()):
        return "No matching data found for this query — the database has no records matching your filters."
        
    system_prompt = (
        "You are a concise data analyst. The user asked a business question, and we ran a SQL query to get the answer. "
        "Your job is to translate the raw JSON results into a clear, natural language sentence. "
        "Do NOT mention the SQL query itself, do NOT say 'Based on the data', just give the direct answer."
    )
    
    results_str = str(results)[:2000] 
    
    context_str = ""
    if prior_context:
        context_str = f"Prior Conversation:\n{prior_context}\n\n"
        
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", f"{context_str}User Question: {{question}}\n\nData Results:\n{{results}}")
    ])
    
    messages = prompt_template.format_messages(question=prompt, results=results_str)
    
    response = await llm_synth.ainvoke(messages)
    answer = response.content.strip()
    
    guardrail_patterns = [
        re.compile(r"\w+\s*\(\s*(?:INTEGER|TEXT|VARCHAR|REAL|FLOAT|BLOB|NUMERIC|BOOLEAN|TIMESTAMP)\s*(?:PRIMARY\s+KEY|NOT\s+NULL|UNIQUE|DEFAULT)?\s*\)", re.IGNORECASE),
        re.compile(r"(?:CREATE|ALTER|DROP)\s+TABLE", re.IGNORECASE),
        re.compile(r"PRAGMA\s+\w+", re.IGNORECASE),
        re.compile(r"FOREIGN\s+KEY\s*\(", re.IGNORECASE),
        re.compile(r"AUTOINCREMENT", re.IGNORECASE),
    ]
    if any(p.search(answer) for p in guardrail_patterns):
        raise SecurityViolationError("Egress Guardrail Blocked: Schema leakage detected in final output.")
        
    return answer

if __name__ == "__main__":
    async def test():
        schema = "CREATE TABLE users (id INTEGER, name TEXT);"
        q = "Count all users"
        sql = await generate_sql_only(q, schema)
        print(f"Generated SQL: {sql}")
    asyncio.run(test())
