import asyncio
import threading
import uvicorn
import os
from api import app as fastapi_app
from bot.main import main as bot_main

def run_api():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)

async def main():
    loop = asyncio.get_event_loop()
    thread = threading.Thread(target=run_api, daemon=True)
    thread.start()
    await bot_main()

if __name__ == "__main__":
    asyncio.run(main())
