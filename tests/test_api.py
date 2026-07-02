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
    with patch("api.notify_admins", new_callable=AsyncMock):
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
