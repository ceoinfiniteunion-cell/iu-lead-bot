from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from bot.config import ADMIN_IDS
from bot.keyboards.admin_kb import admin_main_kb, lead_kb
from bot import database as db

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

STATUS_UA = {"new": "🆕 Нова", "in_progress": "🔄 В роботі", "closed": "✅ Закрита"}

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    stats = await db.get_stats()
    counts = {
        "new": stats["new"],
        "in_progress": stats["in_progress"],
        "closed": stats["closed"],
    }
    await msg.answer(
        "🎛 <b>Адмін-панель Infinite Union</b>\n\nВибери розділ:",
        parse_mode="HTML",
        reply_markup=admin_main_kb(counts)
    )

@router.callback_query(F.data.startswith("al:"))
async def leads_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    status = cb.data.split(":")[1]
    leads = await db.get_leads(status)
    if not leads:
        await cb.answer("Немає заявок у цьому статусі", show_alert=True)
        return
    text = f"<b>{STATUS_UA.get(status, status)} заявки:</b>\n\n"
    for l in leads:
        text += (
            f"#{l['id']} | {l['name']} | {l['service']}\n"
            f"📞 {l['contact']} | 💵 {l['budget']}\n"
            f"🕐 {l['created_at'].strftime('%d.%m %H:%M')}\n\n"
        )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=lead_kb(0, status))

@router.callback_query(F.data.startswith("ls:"))
async def lead_set_status(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    _, lead_id, new_status = cb.data.split(":")
    lead_id = int(lead_id)
    await db.set_status(lead_id, new_status)
    lead = await db.get_lead(lead_id)
    await cb.answer(f"Статус змінено → {STATUS_UA.get(new_status)}", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=lead_kb(lead_id, new_status))

@router.callback_query(F.data == "a:stats")
async def admin_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    s = await db.get_stats()
    await cb.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"Всього заявок: <b>{s['total']}</b>\n"
        f"🆕 Нових: {s['new']}\n"
        f"🔄 В роботі: {s['in_progress']}\n"
        f"✅ Закрито: {s['closed']}",
        parse_mode="HTML",
        reply_markup=None
    )

@router.callback_query(F.data == "a:back")
async def admin_back(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    stats = await db.get_stats()
    counts = {"new": stats["new"], "in_progress": stats["in_progress"], "closed": stats["closed"]}
    await cb.message.edit_text(
        "🎛 <b>Адмін-панель Infinite Union</b>\n\nВибери розділ:",
        parse_mode="HTML",
        reply_markup=admin_main_kb(counts)
    )
