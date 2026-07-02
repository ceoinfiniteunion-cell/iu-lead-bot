import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from bot.config import BOT_TOKEN, REDIS_URL
from bot.database import init_db
from bot.handlers.client import router as client_router
from bot.handlers.admin import router as admin_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    storage = RedisStorage.from_url(REDIS_URL)
    dp = Dispatcher(storage=storage)
    dp.include_router(admin_router)
    dp.include_router(client_router)
    logging.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
