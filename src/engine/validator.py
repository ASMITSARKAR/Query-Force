import sqlglot
import aiosqlite
from pathlib import Path
from src.config import settings
from sqlglot import exp
from src.engine.errors import SecurityViolationError

async def validate_and_format_sql(sql: str, enforce_limit: int = 500) -> str:
    """
    Parses the SQL using sqlglot to ensure it is syntactically valid SQLite.
    Walks the Abstract Syntax Tree (AST) to block all writing/modifying commands.
    Implements the T8 fix to block dangerous PRAGMA statements.
    Injects a LIMIT if missing to prevent terminal flooding.
    """
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except Exception as e:
        raise SecurityViolationError(f"Failed to parse SQL: {str(e)}")

    forbidden_types = (
        exp.Create,
        exp.Drop,
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.AlterTable,
        exp.Pragma,  # T8 Fix: Strict PRAGMA prevention
        exp.Commit,
        exp.Rollback,
        exp.Transaction
    )

    forbidden_nodes = list(parsed.find_all(forbidden_types))
    if forbidden_nodes:
        offending_type = forbidden_nodes[0].__class__.__name__
        raise SecurityViolationError(f"Security violation: Found forbidden command type '{offending_type}'. Only SELECT is allowed.")

    db_uri = f"file:{Path(settings.ANALYTICS_DB_PATH).absolute().as_posix()}?mode=ro"
    async with aiosqlite.connect(db_uri, uri=True) as conn:
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        rows = await cursor.fetchall()
        allowed_tables = {row[0].lower() for row in rows}

    cte_aliases = {cte.alias.lower() for cte in parsed.find_all(exp.CTE)}
    allowed = allowed_tables.union(cte_aliases)

    for table_node in parsed.find_all(exp.Table):
        if table_node.name.lower() not in allowed:
            raise ValueError(f"Unknown table: '{table_node.name}'. Please only query from the provided schema tables.")

    # NOTE: We intentionally do NOT do column-level validation here.

    for join_node in parsed.find_all(exp.Join):
        on_clause = join_node.args.get("on")
        if not on_clause:
            raise SecurityViolationError("Algorithmic Denial of Service Blocked: CROSS JOIN or missing ON clause detected.")
        if not any(isinstance(node, exp.EQ) for node in on_clause.walk()):
            raise SecurityViolationError("Algorithmic Denial of Service Blocked: JOIN condition lacks a strict equality (=) comparison.")

    has_agg = bool(list(parsed.find_all(exp.AggFunc)))
    has_group = bool(parsed.args.get("group"))
    
    if not (has_agg and not has_group):
        limit_node = parsed.args.get("limit")
        if not limit_node:
            parsed = parsed.limit(enforce_limit)
        else:
            try:
                limit_val = int(limit_node.expression.this)
                if limit_val > enforce_limit:
                    limit_node.set("expression", exp.Literal.number(enforce_limit))
            except Exception:
                limit_node.set("expression", exp.Literal.number(enforce_limit))
        
    return parsed.sql(dialect="sqlite")

if __name__ == "__main__":
    import asyncio
    async def test():
        print("Testing Valid Query...")
        print(await validate_and_format_sql("SELECT * FROM customers"))
        
        print("\nTesting Forbidden Query (T8 Pragma)...")
        try:
            await validate_and_format_sql("PRAGMA journal_mode = WAL;")
        except Exception as e:
            print("Blocked successfully:", e)
    asyncio.run(test())
