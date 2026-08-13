CREATE TABLE IF NOT EXISTS execution_logs (
    id UUID PRIMARY KEY,
    prompt TEXT,
    sql TEXT,
    ast_status VARCHAR(50),
    retries INTEGER,
    latency_ms REAL,
    success BOOLEAN,
    error_trace TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
