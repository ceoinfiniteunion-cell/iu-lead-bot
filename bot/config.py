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
ADMIN_IDS  = [int(x) for x in os.environ.get("ADMIN_IDS", "8589737416,1065496907,1106261803").split(",") if x]
