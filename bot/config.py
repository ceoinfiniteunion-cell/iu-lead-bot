import os

BOT_TOKEN  = os.environ["BOT_TOKEN"]
DB_URL     = os.environ["DATABASE_URL"]
REDIS_URL  = os.environ["REDIS_URL"]
ADMIN_IDS  = [int(x) for x in os.environ.get("ADMIN_IDS", "8589737416,1065496907,1106261803").split(",") if x]
