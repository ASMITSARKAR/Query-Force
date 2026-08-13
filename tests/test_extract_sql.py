import pytest
from src.engine.llm import extract_sql

def test_extract_sql_fenced():
    raw = "Here is the SQL:\n```sql\nSELECT * FROM users;\n```\nEnjoy!"
    assert extract_sql(raw) == "SELECT * FROM users;"

def test_extract_sql_unfenced_select():
    raw = "Sure! SELECT id FROM orders;"
    assert extract_sql(raw) == "SELECT id FROM orders;"

def test_extract_sql_malformed_fence():
    raw = "```\nSELECT 1;\n```"
    assert extract_sql(raw) == "SELECT 1;"

def test_extract_sql_with_clause():
    raw = "WITH cte AS (SELECT 1) SELECT * FROM cte;"
    assert extract_sql(raw) == "WITH cte AS (SELECT 1) SELECT * FROM cte;"
