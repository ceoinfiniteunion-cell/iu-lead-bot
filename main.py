import asyncio
import threading
import uvicorn
import os
import logging
from api import app as fastapi_app
from bot.main import main as bot_main

logging.basicConfig(level=logging.INFO)

def run_api():
    port = int(os.environ.get("PORT", 8000))
    logging.info(f"Starting FastAPI on port {port}")
    try:
        uvicorn.run(fastapi_app, host="0.0.0.0", port=port)
    except Exception as e:
        logging.error(f"FastAPI error: {e}")

async def main():
    thread = threading.Thread(target=run_api, daemon=True)
    thread.start()
    await bot_main()

if __name__ == "__main__":
    asyncio.run(main())
