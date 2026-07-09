import asyncpg
from bot.config import DB_URL

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB_URL)
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT,
                username   TEXT,
                name       TEXT,
                service    TEXT,
                budget     TEXT,
                timeline   TEXT,
                contact    TEXT,
                status     TEXT DEFAULT 'new',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                extra      jsonb DEFAULT '{}'
            )
        """)
        await conn.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS extra jsonb DEFAULT '{}'")

async def add_lead(user_id, username, name, service, budget, timeline, contact):
    pool = await get_pool()
    return await pool.fetchval(
        """INSERT INTO leads (user_id, username, name, service, budget, timeline, contact)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        user_id, username, name, service, budget, timeline, contact
    )

async def get_leads(status: str):
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM leads WHERE status=$1 ORDER BY created_at DESC LIMIT 30", status
    )

async def get_lead(lead_id: int):
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM leads WHERE id=$1", lead_id)

async def set_status(lead_id: int, status: str):
    pool = await get_pool()
    await pool.execute("UPDATE leads SET status=$1 WHERE id=$2", status, lead_id)

async def get_stats():
    pool = await get_pool()
    return await pool.fetchrow("""
        SELECT
            COUNT(*)                                      AS total,
            COUNT(*) FILTER (WHERE status='new')          AS new,
            COUNT(*) FILTER (WHERE status='in_progress')  AS in_progress,
            COUNT(*) FILTER (WHERE status='closed')       AS closed
        FROM leads
    """)

async def update_lead_extra(lead_id: int, field: str, value: str):
    allowed = {"phone", "tg_username", "project_type", "buh_budget", "deadline"}
    if field not in allowed:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE leads SET extra = COALESCE(extra, '{}') || jsonb_build_object($1::text, $2::text) WHERE id = $3",
            field, value, lead_id
        )

async def get_lead_extra(lead_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT extra FROM leads WHERE id = $1", lead_id)
        if row and row["extra"]:
            val = row["extra"]
            if isinstance(val, dict):
                return val
            import json
            try:
                return json.loads(val)
            except Exception:
                return {}
        return {}
