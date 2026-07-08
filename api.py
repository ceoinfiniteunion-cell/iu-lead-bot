import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import aiohttp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = [int(x) for x in os.environ["ADMIN_IDS"].split(",") if x]

class Lead(BaseModel):
    name: str
    contact: str
    project: str = ""
    @field_validator("name", "contact")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

async def notify_admins(text: str):
    async with aiohttp.ClientSession() as session:
        for admin_id in ADMIN_IDS:
            await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"}
            )

@app.post("/lead")
async def receive_lead(lead: Lead):
    text = (
        f"🔔 <b>Нова заявка з сайту</b>\n\n"
        f"👤 Ім'я: {lead.name}\n"
        f"📞 Контакт: {lead.contact}\n"
        f"💬 Проект: {lead.project or '—'}"
    )
    await notify_admins(text)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok"}
