import uuid
import aiosqlite
from pathlib import Path
from src.config import settings

_db_initialized = False
_pg_pool = None

async def _get_pg_pool():
    global _pg_pool
    if not _pg_pool:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(settings.TELEMETRY_DSN)
    return _pg_pool

async def get_connection():
    if settings.TELEMETRY_DSN:
        return await _get_pg_pool()
        
    global _db_initialized
    db_path = Path(settings.TELEMETRY_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = await aiosqlite.connect(db_path)

    if not _db_initialized:
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA synchronous = NORMAL;")
        _db_initialized = True

    return conn

async def init_telemetry_db():
    if settings.TELEMETRY_DSN:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS execution_logs (
                id TEXT PRIMARY KEY,
                prompt TEXT,
                sql TEXT,
                ast_status TEXT,
                retries INTEGER,
                latency_ms REAL,
                success BOOLEAN,
                error_trace TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
        return

    conn = await get_connection()
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_logs (
            id TEXT PRIMARY KEY,
            prompt TEXT,
            sql TEXT,
            ast_status TEXT,
            retries INTEGER,
            latency_ms REAL,
            success BOOLEAN,
            error_trace TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await conn.commit()
    finally:
        await conn.close()

async def log_execution_metric(
    prompt: str, 
    sql: str | None = None, 
    ast_status: str = "CLEAN", 
    retries: int = 0, 
    latency_ms: float = 0.0, 
    success: bool = True, 
    error_trace: str | None = None
) -> str:
    log_id = str(uuid.uuid4())
    
    if settings.TELEMETRY_DSN:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO execution_logs (id, prompt, sql, ast_status, retries, latency_ms, success, error_trace)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, log_id, prompt, sql, ast_status, retries, latency_ms, success, error_trace)
        return log_id
        
    conn = await get_connection()
    try:
        await conn.execute("""
        INSERT INTO execution_logs (id, prompt, sql, ast_status, retries, latency_ms, success, error_trace)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, prompt, sql, ast_status, retries, latency_ms, success, error_trace))
        await conn.commit()
        return log_id
    finally:
        await conn.close()

async def get_recent_logs(limit: int = 20) -> list[dict]:
    if settings.TELEMETRY_DSN:
        pool = await _get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, prompt, sql, ast_status, retries, latency_ms, success, error_trace, created_at
                FROM execution_logs
                ORDER BY created_at DESC
                LIMIT $1
            """, limit)
            return [dict(row) for row in rows]
            
    conn = await get_connection()
    try:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("""
            SELECT id, prompt, sql, ast_status, retries, latency_ms, success, error_trace, created_at
            FROM execution_logs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_telemetry_db())
    print("Telemetry database initialized.")
