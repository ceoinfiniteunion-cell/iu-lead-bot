import os
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import html as html_lib
import aiohttp
import asyncpg
import redis.asyncio as aioredis

# ── Логування ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Lifespan — пул створюється один раз при старті ───────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
    logger.info("Creating DB connection pool")
    app.state.pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    logger.info("DB pool ready")
    yield
    logger.info("Closing DB connection pool")
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

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

RATE_LIMIT = 3
RATE_WINDOW = 86400  # 24 години

async def check_rate_limit(ip: str):
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        logger.warning("REDIS_URL not set — rate limit skipped")
        return
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        key = f"gen_rate:{ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, RATE_WINDOW)
        if count > RATE_LIMIT:
            logger.warning("Rate limit exceeded for IP %s (count=%d)", ip, count)
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again tomorrow.")
    finally:
        await r.aclose()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x]

class Lead(BaseModel):
    name: str
    contact: str
    phone: str = ""
    project_type: str = ""
    budget: str = ""
    deadline: str = ""
    project: str = ""
    website: str = ""  # honeypot

    @field_validator("name", "contact")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

async def notify_admins(text: str):
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set — cannot notify admins")
        return
    async with aiohttp.ClientSession() as session:
        for admin_id in ADMIN_IDS:
            try:
                resp = await session.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"}
                )
                if resp.status != 200:
                    logger.warning("TG notify failed for admin %s: status %d", admin_id, resp.status)
            except Exception:
                logger.exception("Failed to notify admin %s", admin_id)

async def save_to_db(request: Request, lead: "Lead") -> int:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        lead_id = await conn.fetchval(
            """INSERT INTO leads (user_id, username, name, service, budget, timeline, contact, extra)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            0, "site", html_lib.escape(lead.name),
            html_lib.escape(lead.project_type or "З сайту"),
            html_lib.escape(lead.budget or "—"),
            "—",
            html_lib.escape(lead.contact),
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
async def receive_lead(lead: Lead, request: Request):
    if lead.website:
        logger.warning("Honeypot triggered from IP %s", request.client.host)
        return {"ok": True}  # тихо ігноруємо бота
    try:
        lead_id = await save_to_db(request, lead)
        logger.info("Lead #%d saved (name=%s)", lead_id, lead.name)
    except Exception:
        logger.exception("Failed to save lead (name=%s)", lead.name)
        raise HTTPException(status_code=500, detail="Failed to save lead")
    try:
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
    except Exception:
        logger.exception("Failed to notify admins for lead #%d", lead_id)
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
    await check_rate_limit(ip)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        logger.error("ANTHROPIC_API_KEY not set")
        raise HTTPException(status_code=503, detail="Service unavailable")
    logger.info("Generate request from IP %s", ip)
    async with aiohttp.ClientSession() as session:
        try:
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
            logger.info("Generate OK for IP %s", ip)
            return data
        except Exception:
            logger.exception("Anthropic API call failed for IP %s", ip)
            raise HTTPException(status_code=502, detail="AI service error")

@app.get("/health")
async def health():
    return {"status": "ok"}
