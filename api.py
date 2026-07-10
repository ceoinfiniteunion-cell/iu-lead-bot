import os
import json
import time
import hmac
import hashlib
import logging
import asyncio
import signal
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

# ── Circuit breaker ───────────────────────────────────────────────────
_cb_failures = 0
_cb_open_until = 0.0
CB_THRESHOLD = 3
CB_TIMEOUT = 60

def cb_is_open() -> bool:
    return time.time() < _cb_open_until

def cb_record_failure():
    global _cb_failures, _cb_open_until
    _cb_failures += 1
    if _cb_failures >= CB_THRESHOLD:
        _cb_open_until = time.time() + CB_TIMEOUT
        logger.warning("[CIRCUIT_BREAKER] Opened — blocking for %ds", CB_TIMEOUT)

def cb_record_success():
    global _cb_failures, _cb_open_until
    _cb_failures = 0
    _cb_open_until = 0.0

# ── Dead letter queue ─────────────────────────────────────────────────
DLQ_KEY = "dlq:leads"

async def dlq_push(r: aioredis.Redis, lead_data: dict):
    try:
        await r.rpush(DLQ_KEY, json.dumps(lead_data))  # type: ignore[misc]
        logger.warning("[DLQ] Lead pushed to dead letter queue: %s", lead_data.get("name"))
    except Exception:
        logger.exception("[DLQ] Failed to push to DLQ — lead LOST: %s", lead_data)

async def dlq_worker(pool: asyncpg.Pool, r: aioredis.Redis):
    """Фоновий worker — ретраїть ліди з DLQ."""
    import html as html_lib
    while True:
        try:
            item = await r.lpop(DLQ_KEY)  # type: ignore[misc]
            if not item:
                await asyncio.sleep(30)
                continue
            data = json.loads(item)
            logger.info("[DLQ] Retrying lead: %s", data.get("name"))
            async with pool.acquire() as conn:
                lead_id = await conn.fetchval(
                    """INSERT INTO leads (user_id, username, name, service, budget, timeline, contact, extra)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
                    0, "dlq_retry",
                    html_lib.escape(data.get("name", "")),
                    html_lib.escape(data.get("project_type") or "З сайту"),
                    html_lib.escape(data.get("budget") or "—"),
                    "—",
                    html_lib.escape(data.get("contact", "")),
                    json.dumps(data)
                )
            logger.info("[DLQ] Lead #%d recovered from DLQ", lead_id)
        except Exception:
            logger.exception("[DLQ] Worker error")
            await asyncio.sleep(10)

# ── Pool monitor ──────────────────────────────────────────────────────
async def pool_monitor(pool: asyncpg.Pool):
    """Логує стан пулу кожні 30 секунд."""
    while True:
        try:
            size = pool.get_size()
            idle = pool.get_idle_size()
            used = size - idle
            pct = (used / size * 100) if size else 0
            if pct >= 80:
                logger.warning("[POOL] High usage: %d/%d connections (%.0f%%)", used, size, pct)
            else:
                logger.info("[POOL] %d/%d connections used (%.0f%%)", used, size, pct)
        except Exception:
            logger.exception("[POOL] Monitor error")
        await asyncio.sleep(30)

# ── Graceful shutdown ─────────────────────────────────────────────────
_shutdown_event = asyncio.Event()

def handle_sigterm():
    logger.info("[SHUTDOWN] SIGTERM received — starting graceful shutdown")
    _shutdown_event.set()

# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")

    logger.info("Creating DB connection pool")
    app.state.pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)

    from bot.database import init_db, init_audit_and_idempotency
    await init_db()  # type: ignore[misc]
    await init_audit_and_idempotency()  # type: ignore[misc]
    logger.info("DB pool ready")

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, handle_sigterm)

    # Фонові задачі
    redis_url = os.environ.get("REDIS_URL", "")
    background_tasks = []
    if redis_url:
        r = aioredis.from_url(redis_url, decode_responses=True)
        background_tasks.append(asyncio.create_task(dlq_worker(app.state.pool, r)))
        logger.info("DLQ worker started")

    background_tasks.append(asyncio.create_task(pool_monitor(app.state.pool)))
    logger.info("Pool monitor started")

    yield

    # Shutdown
    logger.info("[SHUTDOWN] Stopping background tasks")
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    logger.info("[SHUTDOWN] Closing DB pool")
    await app.state.pool.close()
    logger.info("[SHUTDOWN] Done")

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

# ── Security ──────────────────────────────────────────────────────────
async def check_rate_limit(ip: str, r: aioredis.Redis):
    try:
        key = f"gen_rate:{ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, RATE_WINDOW)
        if count > RATE_LIMIT:
            logger.warning("[SECURITY] Rate limit exceeded IP %s (count=%d)", ip, count)
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again tomorrow.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("[SECURITY] Redis error IP %s — blocking", ip)
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
async def notify_admins_with_backoff(text: str, max_retries: int = 3):
    """Exponential backoff на Telegram notify."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return
    for admin_id in ADMIN_IDS:
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    resp = await session.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"}
                    )
                    if resp.status == 200:
                        break
                    logger.warning("TG notify attempt %d failed for admin %s: %d",
                                   attempt + 1, admin_id, resp.status)
            except Exception:
                logger.exception("TG notify attempt %d exception for admin %s",
                                 attempt + 1, admin_id)
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.info("Retrying admin %s notify in %ds", admin_id, wait)
                await asyncio.sleep(wait)
        else:
            logger.error("Failed to notify admin %s after %d attempts", admin_id, max_retries)

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
async def receive_lead(lead: Lead, request: Request, pool: PoolDep, r: RedisDep):
    ip = request.client.host if request.client else "unknown"

    if lead.website:
        logger.warning("[SECURITY] Honeypot triggered from IP %s", ip)
        return {"ok": True}

    # Rate-limit на /lead: 10 заявок з одного IP за 24 години
    try:
        lead_key = f"lead_rate:{ip}"
        lead_count = await r.incr(lead_key)
        if lead_count == 1:
            await r.expire(lead_key, 86400)
        if lead_count > 10:
            logger.warning("[SECURITY] Lead rate limit exceeded for IP %s (count=%d)", ip, lead_count)
            return {"ok": True}  # тихо ігноруємо, не розкриваємо ліміт
    except Exception:
        logger.exception("[SECURITY] Redis error on lead rate-limit for IP %s", ip)
    finally:
        await r.aclose()

    # Idempotency check
    if lead.idempotency_key:
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT lead_id FROM idempotency_keys WHERE key=$1",
                lead.idempotency_key
            )
            if existing:
                logger.info("Duplicate lead rejected (key=%s)", lead.idempotency_key)
                return {"ok": True, "lead_id": existing}

    try:
        lead_id = await save_to_db(pool, lead)
        logger.info("Lead #%d saved (name=%s)", lead_id, lead.name)
    except Exception:
        logger.exception("Failed to save lead (name=%s)", lead.name)
        await audit(pool, "lead_save_failed", ip, {"name": lead.name}, "error")
        # Dead letter queue — не втрачаємо ліда
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            r = aioredis.from_url(redis_url, decode_responses=True)
            await dlq_push(r, {
                "name": lead.name, "contact": lead.contact,
                "phone": lead.phone, "project_type": lead.project_type,
                "budget": lead.budget, "deadline": lead.deadline,
                "project": lead.project
            })
            await r.aclose()
        raise HTTPException(status_code=500, detail="Failed to save lead")

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
        await notify_admins_with_backoff(text)
    except Exception:
        logger.exception("Failed to notify admins for lead #%d", lead_id)

    return {"ok": True, "lead_id": lead_id}

@app.post("/generate")
async def generate_site(req: GenerateRequest, request: Request, r: RedisDep):
    ip = request.client.host if request.client else "unknown"

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
    status: dict[str, object] = {
        "status": "ok",
        "db": "unknown",
        "redis": "unknown",
        "circuit_breaker": "open" if cb_is_open() else "closed",
        "cb_failures": _cb_failures,
    }

    try:
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        size = pool.get_size()
        idle = pool.get_idle_size()
        status["db"] = "ok"
        status["db_pool"] = {"size": size, "idle": idle, "used": size - idle}
    except Exception:
        status["db"] = "error"
        status["status"] = "degraded"
        logger.error("Health check: DB unavailable")

    try:
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            r = aioredis.from_url(redis_url, decode_responses=True)
            await r.ping()  # type: ignore[misc]
            dlq_size = await r.llen(DLQ_KEY)
            await r.aclose()
            status["redis"] = "ok"
            status["dlq_size"] = dlq_size
            if dlq_size > 0:
                logger.warning("[DLQ] %d leads pending in queue", dlq_size)
        else:
            status["redis"] = "not_configured"
    except Exception:
        status["redis"] = "error"
        status["status"] = "degraded"
        logger.error("Health check: Redis unavailable")

    return status
