import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
import os

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_IDS", "123456789")

from api import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_lead_valid():
    with patch("api.notify_admins", new_callable=AsyncMock), \
         patch("api.save_to_db", new_callable=AsyncMock, return_value=1):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/lead", json={"name": "Єгор", "contact": "@test", "project": "Сайт"})
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
    with patch("api.check_rate_limit", new_callable=AsyncMock) as mock_rl:
        mock_rl.side_effect = [None, None, None]  # перші 3 — ок
        with patch("api.os.environ.get", return_value=""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                r = await ac.post("/generate", json={"prompt": "Тест сайт"})
        assert r.status_code in (200, 503)  # 503 бо немає ключа, але rate-limit пропустив

@pytest.mark.asyncio
async def test_generate_rate_limit_blocked():
    from fastapi import HTTPException
    with patch("api.check_rate_limit", new_callable=AsyncMock) as mock_rl:
        mock_rl.side_effect = HTTPException(status_code=429, detail="Rate limit exceeded. Try again tomorrow.")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post("/generate", json={"prompt": "Тест сайт"})
    assert r.status_code == 429
