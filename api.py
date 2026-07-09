import os, time
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import aiohttp
import asyncpg

app = FastAPI()

ALLOWED_ORIGINS = [
    "https://ceoinfiniteunion-cell.github.io",
    "http://localhost:3000",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

# --- Rate limit для /generate: 3 запити на IP за 24 години ---
_rate_store: dict[str, list[float]] = {}
RATE_LIMIT = 3
RATE_WINDOW = 86400  # 24 години в секундах

def check_rate_limit(ip: str):
    now = time.time()
    hits = [t for t in _rate_store.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again tomorrow.")
    hits.append(now)
    _rate_store[ip] = hits

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = [int(x) for x in os.environ["ADMIN_IDS"].split(",") if x]
DB_URL = os.environ["DATABASE_URL"]

class Lead(BaseModel):
    name: str
    contact: str
    phone: str = ""
    project_type: str = ""
    budget: str = ""
    deadline: str = ""
    project: str = ""

    @field_validator("name", "contact")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

async def notify_admins(text: str):
    async with aiohttp.ClientSession() as session:
        for admin_id in ADMIN_IDS:
            await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"}
            )

async def save_to_db(lead: "Lead") -> int:
    from bot.database import get_pool
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        lead_id = await conn.fetchval(
            """INSERT INTO leads (user_id, username, name, service, budget, timeline, contact, extra)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            0, "site", lead.name,
            lead.project_type or "З сайту",
            lead.budget or "—",
            "—",
            lead.contact,
            json.dumps({
                "phone": lead.phone,
                "tg_username": lead.contact,
                "project_type": lead.project_type,
                "buh_budget": lead.budget,
                "deadline": lead.deadline
            })
        )
        return lead_id

@app.post("/lead")
async def receive_lead(lead: Lead):
    lead_id = await save_to_db(lead)
    text = (
        f"🔔 <b>Нова заявка з сайту #{lead_id}</b>\n\n"
        f"👤 Ім'я: {lead.name}\n"
        f"📞 Телефон: {lead.phone or '—'}\n"
        f"✈️ Telegram: {lead.contact}\n"
        f"🏷 Тип проєкту: {lead.project_type or '—'}\n"
        f"📝 Опис: {lead.project or '—'}\n"
        f"💰 Бюджет: {lead.budget or '—'}\n"
        f"📅 Дедлайн: {lead.deadline or '—'}"
    )
    await notify_admins(text)
    return {"ok": True}

class GenerateRequest(BaseModel):
    prompt: str
    system: str = ""

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty")
        if len(v) > 2000:
            raise ValueError("prompt too long (max 2000 chars)")
        return v

    @field_validator("system")
    @classmethod
    def system_max_length(cls, v: str) -> str:
        if len(v) > 3000:
            raise ValueError("system prompt too long")
        return v

@app.post("/generate")
async def generate_site(req: GenerateRequest, request: Request):
    ip = request.client.host
    check_rate_limit(ip)

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Service unavailable")

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4000,
                "system": req.system,
                "messages": [{"role": "user", "content": req.prompt}]
            }
        )
        data = await resp.json()
    return data

@app.get("/health")
async def health():
    return {"status": "ok"}
