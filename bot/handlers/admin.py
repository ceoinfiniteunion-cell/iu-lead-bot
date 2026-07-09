from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import ADMIN_IDS
from bot.keyboards.admin_kb import admin_main_kb, lead_kb
from bot import database as db
import aiohttp, os
import logging

logger = logging.getLogger(__name__)
router = Router()
BUH_BOT_TOKEN = os.environ.get("BUH_BOT_TOKEN", "")

def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

# Централізований фільтр — всі хендлери роутера автоматично перевіряють адміна
router.message.filter(lambda m: _is_admin(m.from_user.id))
router.callback_query.filter(lambda c: _is_admin(c.from_user.id))

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
    stats = await db.get_stats()
    await msg.answer(
        "🎛 <b>Адмін-панель Infinite Union</b>\n\nВибери розділ:",
        parse_mode="HTML",
        reply_markup=admin_main_kb({"new":stats["new"],"in_progress":stats["in_progress"],"closed":stats["closed"]})
    )

@router.callback_query(F.data.startswith("al:"))
async def leads_list(cb: CallbackQuery):
    status = cb.data.split(":")[1]
    leads = await db.get_leads(status)
    if not leads:
        await cb.answer("Немає заявок", show_alert=True); return
    text = f"<b>{STATUS_UA.get(status)} заявки:</b>\n\n"
    for l in leads:
        text += f"#{l['id']} | {l['name']} | {l['service']}\n📞 {l['contact']} | 💵 {l['budget']}\n🕐 {l['created_at'].strftime('%d.%m %H:%M')}\n\n"
    # Кнопки для кожної заявки
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = [[InlineKeyboardButton(text=f"#{l['id']} {l['name']}", callback_data=f"lo:{l['id']}")] for l in leads]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="a:back")])
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith("ls:"))
async def lead_set_status(cb: CallbackQuery):
    _, lead_id, new_status = cb.data.split(":")
    lead_id = int(lead_id)
    await db.set_status(lead_id, new_status)
    await cb.answer(f"Статус → {STATUS_UA.get(new_status)}", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=lead_kb(lead_id, new_status))


@router.callback_query(F.data.startswith("lo:"))
async def lead_open(cb: CallbackQuery):
    lead_id = int(cb.data.split(":")[1])
    lead = dict(await db.get_lead(lead_id) or {})
    extra = await db.get_lead_extra(lead_id)
    text = (
        f"📋 <b>Заявка #{lead_id}</b>\n\n"
        f"👤 {lead.get('name','—')}\n"
        f"📞 {extra.get('phone', lead.get('contact','—'))}\n"
        f"✈️ {extra.get('tg_username','—')}\n"
        f"🏷 {extra.get('project_type', lead.get('service','—'))}\n"
        f"📝 {lead.get('contact','—')}\n"
        f"💰 {extra.get('buh_budget', lead.get('budget','—'))}\n"
        f"📅 {extra.get('deadline','—')}\n"
        f"🕐 {lead.get('created_at').strftime('%d.%m %H:%M') if lead.get('created_at') else '—'}"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=lead_kb(lead_id, lead.get("status","new")))

@router.callback_query(F.data.startswith("lf:"))
async def lead_fill(cb: CallbackQuery, state: FSMContext):
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
        buh_url = os.environ.get("BUH_API_URL", "")
        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.post(buh_url, json={
                    "name": lead.get("name","—"),
                    "contact": extra.get("tg_username", lead.get("contact","—")),
                    "phone": extra.get("phone","—"),
                    "project_type": extra.get("project_type", lead.get("service","—")),
                    "budget": extra.get("buh_budget", lead.get("budget","—")),
                    "deadline": extra.get("deadline","—"),
                    "project": lead.get("contact","—")
                })
                if resp.status != 200:
                    logger.warning("Buh API returned %d for lead #%d", resp.status, lead_id)
            logger.info("Lead #%d sent to buh bot", lead_id)
            await cb.answer("✅ Відправлено в бухгалтерію!", show_alert=True)
        except Exception:
            logger.exception("Failed to send lead #%d to buh bot", lead_id)
            await cb.answer("❌ Помилка відправки в бухгалтерію", show_alert=True)
        return

    label = FIELD_LABELS.get(field, field)
    await state.set_state(AdminFill.waiting)
    await state.update_data(lead_id=lead_id, field=field)
    await cb.message.answer(f"Введи значення для поля:\n<b>{label}</b>", parse_mode="HTML")
    await cb.answer()

@router.message(AdminFill.waiting)
async def admin_fill_value(msg: Message, state: FSMContext):
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
    s = await db.get_stats()
    await cb.message.edit_text(
        f"📊 <b>Статистика</b>\n\nВсього: <b>{s['total']}</b>\n🆕 {s['new']}\n🔄 {s['in_progress']}\n✅ {s['closed']}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "a:back")
async def admin_back(cb: CallbackQuery):
    stats = await db.get_stats()
    await cb.message.edit_text(
        "🎛 <b>Адмін-панель Infinite Union</b>\n\nВибери розділ:",
        parse_mode="HTML",
        reply_markup=admin_main_kb({"new":stats["new"],"in_progress":stats["in_progress"],"closed":stats["closed"]})
    )
