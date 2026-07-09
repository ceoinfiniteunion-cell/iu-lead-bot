from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import ADMIN_IDS
from bot.keyboards.admin_kb import admin_main_kb, lead_kb
from bot import database as db
import aiohttp, os

router = Router()
BUH_BOT_TOKEN = os.environ.get("BUH_BOT_TOKEN", "")

def is_admin(uid): return uid in ADMIN_IDS

STATUS_UA = {"new":"🆕 Нова","in_progress":"🔄 В роботі","closed":"✅ Закрита"}

FIELD_LABELS = {
    "phone": "📞 Телефон",
    "tg": "✈️ Telegram username (@...)",
    "type": "🏷 Тип проєкту (напр. Telegram-бот)",
    "budget": "💰 Бюджет (напр. 15000 UAH)",
    "deadline": "📅 Дедлайн (напр. 31.08.2026)",
}
FIELD_KEYS = {
    "phone": "phone",
    "tg": "tg_username",
    "type": "project_type",
    "budget": "buh_budget",
    "deadline": "deadline",
}

class AdminFill(StatesGroup):
    waiting = State()

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id): return
    stats = await db.get_stats()
    await msg.answer(
        "🎛 <b>Адмін-панель Infinite Union</b>\n\nВибери розділ:",
        parse_mode="HTML",
        reply_markup=admin_main_kb({"new":stats["new"],"in_progress":stats["in_progress"],"closed":stats["closed"]})
    )

@router.callback_query(F.data.startswith("al:"))
async def leads_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    status = cb.data.split(":")[1]
    leads = await db.get_leads(status)
    if not leads:
        await cb.answer("Немає заявок", show_alert=True); return
    text = f"<b>{STATUS_UA.get(status)} заявки:</b>\n\n"
    for l in leads:
        text += f"#{l['id']} | {l['name']} | {l['service']}\n📞 {l['contact']} | 💵 {l['budget']}\n🕐 {l['created_at'].strftime('%d.%m %H:%M')}\n\n"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=lead_kb(0, status))

@router.callback_query(F.data.startswith("ls:"))
async def lead_set_status(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    _, lead_id, new_status = cb.data.split(":")
    lead_id = int(lead_id)
    await db.set_status(lead_id, new_status)
    await cb.answer(f"Статус → {STATUS_UA.get(new_status)}", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=lead_kb(lead_id, new_status))

@router.callback_query(F.data.startswith("lf:"))
async def lead_fill(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    parts = cb.data.split(":")
    lead_id, field = int(parts[1]), parts[2]

    if field == "send":
        # Відправляємо в бухгалтерію
        lead = dict(await db.get_lead(lead_id) or {})
        extra = await db.get_lead_extra(lead_id)
        text = (
            f"🔔 <b>НОВА ЗАЯВКА</b>\n\n"
            f"👤 Клієнт: {lead.get('name','—')}\n"
            f"📞 Телефон: {extra.get('phone', '—')}\n"
            f"✈️ Telegram: {extra.get('tg_username', '—')}\n"
            f"🏷 Тип проєкту: {extra.get('project_type', lead.get('service','—'))}\n"
            f"📝 Опис: {lead.get('contact','—')}\n"
            f"💰 Бюджет: {extra.get('buh_budget', lead.get('budget','—'))}\n"
            f"📅 Дедлайн: {extra.get('deadline','—')}"
        )
        buh_ids = [int(x) for x in os.environ.get("BUH_OWNER_IDS", "").split(",") if x]
        async with aiohttp.ClientSession() as session:
            for buh_id in buh_ids:
                await session.post(
                    f"https://api.telegram.org/bot{BUH_BOT_TOKEN}/sendMessage",
                    json={"chat_id": buh_id, "text": text, "parse_mode": "HTML"}
                )
        await cb.answer("✅ Відправлено в бухгалтерію!", show_alert=True)
        return

    label = FIELD_LABELS.get(field, field)
    await state.set_state(AdminFill.waiting)
    await state.update_data(lead_id=lead_id, field=field)
    await cb.message.answer(f"Введи значення для поля:\n<b>{label}</b>", parse_mode="HTML")
    await cb.answer()

@router.message(AdminFill.waiting)
async def admin_fill_value(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    data = await state.get_data()
    lead_id = data["lead_id"]
    field = FIELD_KEYS.get(data["field"], data["field"])
    await db.update_lead_extra(lead_id, field, msg.text.strip())
    await state.clear()

    extra = await db.get_lead_extra(lead_id)
    lead = dict(await db.get_lead(lead_id) or {})
    await msg.answer(
        f"✅ Збережено!\n\n"
        f"<b>Поточні дані заявки #{lead_id}:</b>\n"
        f"👤 {lead.get('name','—')}\n"
        f"📞 {extra.get('phone','—')}\n"
        f"✈️ {extra.get('tg_username','—')}\n"
        f"🏷 {extra.get('project_type', lead.get('service','—'))}\n"
        f"💰 {extra.get('buh_budget', lead.get('budget','—'))}\n"
        f"📅 {extra.get('deadline','—')}",
        parse_mode="HTML",
        reply_markup=lead_kb(lead_id, lead.get("status","new"))
    )

@router.callback_query(F.data == "a:stats")
async def admin_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    s = await db.get_stats()
    await cb.message.edit_text(
        f"📊 <b>Статистика</b>\n\nВсього: <b>{s['total']}</b>\n🆕 {s['new']}\n🔄 {s['in_progress']}\n✅ {s['closed']}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "a:back")
async def admin_back(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    stats = await db.get_stats()
    await cb.message.edit_text(
        "🎛 <b>Адмін-панель Infinite Union</b>\n\nВибери розділ:",
        parse_mode="HTML",
        reply_markup=admin_main_kb({"new":stats["new"],"in_progress":stats["in_progress"],"closed":stats["closed"]})
    )
