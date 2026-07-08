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
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logging.info(f"PORT={port}")
    thread = threading.Thread(target=run_api, daemon=True)
    thread.start()
    logging.info("FastAPI thread started")
    asyncio.run(bot_main())
