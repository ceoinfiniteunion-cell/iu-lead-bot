import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock
import os

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_IDS", "123456789")
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost/fake")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from api import app

def make_pool_mock():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False)
    ))
    pool.get_size = MagicMock(return_value=5)
    pool.get_idle_size = MagicMock(return_value=4)
    return pool

@pytest.fixture(autouse=True)
def inject_pool():
    app.state.pool = make_pool_mock()
    yield
    del app.state.pool

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert "status" in r.json()

@pytest.mark.asyncio
async def test_lead_valid():
    with patch("api.save_to_db", new_callable=AsyncMock, return_value=1), \
         patch("api.notify_admins_with_backoff", new_callable=AsyncMock), \
         patch("api.audit", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/lead", json={
                "name": "Єгор", "contact": "@test", "project": "Сайт"
            })
    assert r.status_code == 200
    assert r.json()["ok"] is True

@pytest.mark.asyncio
async def test_lead_missing_fields():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/lead", json={"contact": "@test"})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_lead_empty_name():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/lead", json={"name": "", "contact": ""})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_lead_honeypot():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/lead", json={
            "name": "Bot", "contact": "@bot", "website": "http://spam.com"
        })
    assert r.status_code == 200
    assert r.json()["ok"] is True

@pytest.mark.asyncio
async def test_generate_missing_prompt():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/generate", json={"prompt": ""})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_generate_prompt_too_long():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/generate", json={"prompt": "x" * 2001})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_generate_rate_limit():
    with patch("api.check_rate_limit", new_callable=AsyncMock), \
         patch("api.cb_is_open", return_value=False), \
         patch("api.aioredis.from_url") as mock_redis:
        mock_r = AsyncMock()
        mock_r.aclose = AsyncMock()
        mock_redis.return_value = mock_r
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/generate", json={"prompt": "Тест сайт"})
    assert r.status_code in (200, 503)

@pytest.mark.asyncio
async def test_generate_rate_limit_blocked():
    from fastapi import HTTPException
    with patch("api.check_rate_limit", new_callable=AsyncMock) as mock_rl, \
         patch("api.cb_is_open", return_value=False), \
         patch("api.aioredis.from_url") as mock_redis:
        mock_r = AsyncMock()
        mock_r.aclose = AsyncMock()
        mock_redis.return_value = mock_r
        mock_rl.side_effect = HTTPException(status_code=429, detail="Rate limit exceeded. Try again tomorrow.")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/generate", json={"prompt": "Тест сайт"})
    assert r.status_code == 429

@pytest.mark.asyncio
async def test_generate_circuit_breaker():
    with patch("api.cb_is_open", return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/generate", json={"prompt": "Тест сайт"})
    assert r.status_code == 503
    assert "temporarily" in r.json()["detail"]
