import asyncpg
from bot.config import DB_URL

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(DB_URL)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          SERIAL PRIMARY KEY,
            user_id     BIGINT,
            username    TEXT,
            name        TEXT,
            service     TEXT,
            budget      TEXT,
            timeline    TEXT,
            contact     TEXT,
            status      TEXT DEFAULT 'new',
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)

async def add_lead(user_id, username, name, service, budget, timeline, contact):
    return await pool.fetchval(
        """INSERT INTO leads (user_id, username, name, service, budget, timeline, contact)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        user_id, username, name, service, budget, timeline, contact
    )

async def get_leads(status: str):
    return await pool.fetch(
        "SELECT * FROM leads WHERE status=$1 ORDER BY created_at DESC LIMIT 30", status
    )

async def get_lead(lead_id: int):
    return await pool.fetchrow("SELECT * FROM leads WHERE id=$1", lead_id)

async def set_status(lead_id: int, status: str):
    await pool.execute("UPDATE leads SET status=$1 WHERE id=$2", status, lead_id)

async def get_stats():
    return await pool.fetchrow("""
        SELECT
            COUNT(*)                                      AS total,
            COUNT(*) FILTER (WHERE status='new')          AS new,
            COUNT(*) FILTER (WHERE status='in_progress')  AS in_progress,
            COUNT(*) FILTER (WHERE status='closed')       AS closed
        FROM leads
    """)
