import pytest
import asyncio
from src.engine.validator import validate_and_format_sql
from src.engine.errors import SecurityViolationError

@pytest.mark.asyncio
async def test_validate_and_format_sql_select():
    sql = "SELECT id, name FROM customers"
    result = await validate_and_format_sql(sql)
    assert "SELECT" in result.upper()
    assert "LIMIT" in result.upper()

@pytest.mark.asyncio
async def test_validate_and_format_sql_block_create():
    sql = "CREATE TABLE test (id INT)"
    with pytest.raises(SecurityViolationError) as exc_info:
        await validate_and_format_sql(sql)
    assert "Create" in str(exc_info.value)

@pytest.mark.asyncio
async def test_validate_and_format_sql_block_drop():
    sql = "DROP TABLE customers"
    with pytest.raises(SecurityViolationError):
        await validate_and_format_sql(sql)

@pytest.mark.asyncio
async def test_validate_and_format_sql_block_pragma():
    sql = "PRAGMA journal_mode = WAL"
    with pytest.raises(SecurityViolationError):
        await validate_and_format_sql(sql)

@pytest.mark.asyncio
async def test_validate_and_format_sql_block_cross_join():
    sql = "SELECT * FROM customers, orders"
    with pytest.raises(SecurityViolationError):
        await validate_and_format_sql(sql)
