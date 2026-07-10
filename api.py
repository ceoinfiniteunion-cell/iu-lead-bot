import os
import json
import time
import hmac
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import aiohttp
import asyncpg
import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Circuit breaker state ─────────────────────────────────────────────
_cb_failures = 0
_cb_open_until = 0.0
CB_THRESHOLD = 3
CB_TIMEOUT = 60  # секунд

def cb_is_open() -> bool:
    return time.time() < _cb_open_until

def cb_record_failure():
    global _cb_failures, _cb_open_until
    _cb_failures += 1
    if _cb_failures >= CB_THRESHOLD:
        _cb_open_until = time.time() + CB_TIMEOUT
        logger.warning("[CIRCUIT_BREAKER] Opened — Anthropic API failing, blocking for %ds", CB_TIMEOUT)

def cb_record_success():
    global _cb_failures, _cb_open_until
    _cb_failures = 0
    _cb_open_until = 0.0

# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
    logger.info("Creating DB connection pool")
    app.state.pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    from bot.database import init_db, init_audit_and_idempotency
    await init_db()
    await init_audit_and_idempotency()
    logger.info("DB pool ready")
    yield
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
    allow_headers=["Content-Type", "X-Signature", "X-Timestamp"],
)

RATE_LIMIT = 3
RATE_WINDOW = 86400
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x]
SIGNING_SECRET = os.environ.get("SIGNING_SECRET", "")

# ── Dependencies ──────────────────────────────────────────────────────
async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool

async def get_redis() -> aioredis.Redis:
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        raise HTTPException(status_code=503, detail="Cache unavailable")
    return aioredis.from_url(redis_url, decode_responses=True)

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]

# ── Security helpers ──────────────────────────────────────────────────
async def verify_signature(request: Request):
    """HMAC request signing — replay attack protection."""
    if not SIGNING_SECRET:
        return  # якщо секрет не задано — пропускаємо (backward compat)
    sig = request.headers.get("X-Signature", "")
    ts = request.headers.get("X-Timestamp", "")
    if not sig or not ts:
        raise HTTPException(status_code=401, detail="Missing signature")
    try:
        ts_int = int(ts)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")
    if abs(time.time() - ts_int) > 300:  # 5 хвилин вікно
        raise HTTPException(status_code=401, detail="Request expired")
    body = await request.body()
    expected = hmac.new(
        SIGNING_SECRET.encode(),
        f"{ts}:{body.decode()}".encode(),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        logger.warning("[SECURITY] Invalid signature from IP %s", request.client.host)
        raise HTTPException(status_code=401, detail="Invalid signature")

async def check_rate_limit(ip: str, r: aioredis.Redis):
    try:
        key = f"gen_rate:{ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, RATE_WINDOW)
        if count > RATE_LIMIT:
            logger.warning("[SECURITY] Rate limit exceeded for IP %s (count=%d)", ip, count)
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again tomorrow.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("[SECURITY] Redis error for IP %s — blocking", ip)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

async def audit(pool: asyncpg.Pool, event: str, ip: str, payload: dict, result: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_log (event, ip, payload, result) VALUES ($1,$2,$3,$4)",
                event, ip, json.dumps(payload), result
            )
    except Exception:
        logger.exception("Failed to write audit log")

# ── Models ────────────────────────────────────────────────────────────
class Lead(BaseModel):
    name: str
    contact: str
    phone: str = ""
    project_type: str = ""
    budget: str = ""
    deadline: str = ""
    project: str = ""
    website: str = ""  # honeypot
    idempotency_key: str = ""

    @field_validator("name", "contact")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("project")
    @classmethod
    def project_max_length(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("project description too long (max 2000 chars)")
        return v

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

# ── Helpers ───────────────────────────────────────────────────────────
async def notify_admins(text: str):
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return
    async with aiohttp.ClientSession() as session:
        for admin_id in ADMIN_IDS:
            try:
                resp = await session.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"}
                )
                if resp.status != 200:
                    logger.warning("TG notify failed for admin %s: %d", admin_id, resp.status)
            except Exception:
                logger.exception("Failed to notify admin %s", admin_id)

async def save_to_db(pool: asyncpg.Pool, lead: Lead) -> int:
    import html as html_lib
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

# ── Endpoints ─────────────────────────────────────────────────────────
@app.post("/lead")
async def receive_lead(lead: Lead, request: Request, pool: PoolDep):
    ip = request.client.host

    # Honeypot
    if lead.website:
        logger.warning("[SECURITY] Honeypot triggered from IP %s", ip)
        return {"ok": True}

    # Idempotency
    if lead.idempotency_key:
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT lead_id FROM idempotency_keys WHERE key=$1",
                lead.idempotency_key
            )
            if existing:
                logger.info("Duplicate lead rejected (idempotency_key=%s)", lead.idempotency_key)
                return {"ok": True, "lead_id": existing}

    try:
        lead_id = await save_to_db(pool, lead)
        logger.info("Lead #%d saved (name=%s)", lead_id, lead.name)
    except Exception:
        logger.exception("Failed to save lead (name=%s)", lead.name)
        await audit(pool, "lead_save_failed", ip, {"name": lead.name}, "error")
        raise HTTPException(status_code=500, detail="Failed to save lead")

    # Зберігаємо idempotency key
    if lead.idempotency_key:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO idempotency_keys (key, lead_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                    lead.idempotency_key, lead_id
                )
        except Exception:
            logger.exception("Failed to save idempotency key")

    await audit(pool, "lead_created", ip, {"lead_id": lead_id, "name": lead.name}, "ok")

    try:
        text = (
            f"🔔 <b>Нова заявка з сайту #{lead_id}</b>\n\n"
            f"👤 Ім'я: {lead.name}\n"
            f"📞 Телефон: {lead.phone or '—'}\n"
            f"✈️ Telegram: {lead.contact}\n"
            f"🏷 Тип: {lead.project_type or '—'}\n"
            f"📝 Опис: {lead.project or '—'}\n"
            f"💰 Бюджет: {lead.budget or '—'}\n"
            f"📅 Дедлайн: {lead.deadline or '—'}"
        )
        await notify_admins(text)
    except Exception:
        logger.exception("Failed to notify admins for lead #%d", lead_id)

    return {"ok": True, "lead_id": lead_id}

@app.post("/generate")
async def generate_site(req: GenerateRequest, request: Request, r: RedisDep):
    ip = request.client.host

    if cb_is_open():
        logger.warning("[CIRCUIT_BREAKER] Request blocked for IP %s", ip)
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")

    await check_rate_limit(ip, r)
    await r.aclose()

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
            if resp.status != 200:
                cb_record_failure()
                logger.error("Anthropic API error %d for IP %s", resp.status, ip)
                raise HTTPException(status_code=502, detail="AI service error")
            cb_record_success()
            logger.info("Generate OK for IP %s", ip)
            return data
        except HTTPException:
            raise
        except Exception:
            cb_record_failure()
            logger.exception("Anthropic API call failed for IP %s", ip)
            raise HTTPException(status_code=502, detail="AI service error")

@app.get("/health")
async def health(request: Request):
    status = {"status": "ok", "db": "unknown", "redis": "unknown"}

    # DB check
    try:
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        status["db"] = "ok"
    except Exception:
        status["db"] = "error"
        status["status"] = "degraded"
        logger.error("Health check: DB unavailable")

    # Redis check
    try:
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            r = aioredis.from_url(redis_url, decode_responses=True)
            await r.ping()
            await r.aclose()
            status["redis"] = "ok"
        else:
            status["redis"] = "not_configured"
    except Exception:
        status["redis"] = "error"
        status["status"] = "degraded"
        logger.error("Health check: Redis unavailable")

    # Circuit breaker status
    status["circuit_breaker"] = "open" if cb_is_open() else "closed"

    return status
