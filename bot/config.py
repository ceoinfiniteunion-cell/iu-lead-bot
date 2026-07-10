import os
import logging

logger = logging.getLogger(__name__)

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

BOT_TOKEN  = require_env("BOT_TOKEN")
DB_URL     = require_env("DATABASE_URL")
REDIS_URL  = require_env("REDIS_URL")
if not os.getenv("ADMIN_IDS"):
    raise RuntimeError("Missing required environment variable: ADMIN_IDS")
ADMIN_IDS  = [int(x) for x in os.environ["ADMIN_IDS"].split(",") if x]
