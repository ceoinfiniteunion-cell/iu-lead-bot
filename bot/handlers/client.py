from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bot.states.quiz import Quiz
from bot.keyboards.client_kb import start_kb, service_kb, budget_kb, timeline_kb, confirm_kb
from bot.config import ADMIN_IDS
from bot import database as db

router = Router()

SERVICE_LABELS = {
    "site": "🌐 Сайт", "bot": "🤖 Telegram-бот",
    "ecosystem": "⚡ Екосистема", "other": "💬 Інше",
}
BUDGET_LABELS = {
    "lt500": "до $500", "500_1k": "$500–$1 000",
    "1k_3k": "$1 000–$3 000", "3kplus": "$3 000+",
}
TIMELINE_LABELS = {
    "urgent": "🔥 Терміново", "twoweeks": "📅 1–2 тижні", "nohurry": "🗓 Не поспішаю",
}

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "👋 Привіт! Я бот <b>Infinite Union</b>\n\n"
        "Розробляємо сайти, Telegram-боти та цифрові екосистеми під ключ.\n\n"
        "Натисни кнопку нижче — я допоможу оформити заявку за 1 хвилину 🚀",
        parse_mode="HTML",
        reply_markup=start_kb()
    )

@router.callback_query(F.data == "quiz:start")
async def quiz_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Quiz.service)
    await cb.message.edit_text("Що потрібно зробити? 👇", reply_markup=service_kb())

@router.callback_query(Quiz.service, F.data.startswith("s:"))
async def quiz_service(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    await state.update_data(service=SERVICE_LABELS.get(val, val))
    await state.set_state(Quiz.budget)
    await cb.message.edit_text("Який бюджет на проект? 💵", reply_markup=budget_kb())

@router.callback_query(Quiz.budget, F.data.startswith("b:"))
async def quiz_budget(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    await state.update_data(budget=BUDGET_LABELS.get(val, val))
    await state.set_state(Quiz.timeline)
    await cb.message.edit_text("Коли потрібно? ⏰", reply_markup=timeline_kb())

@router.callback_query(Quiz.timeline, F.data.startswith("t:"))
async def quiz_timeline(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    await state.update_data(timeline=TIMELINE_LABELS.get(val, val))
    await state.set_state(Quiz.name)
    await cb.message.edit_text("Як тебе звати? ✍️\n\nНапиши ім'я або назву компанії:")

@router.message(Quiz.name)
async def quiz_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(Quiz.contact)
    await msg.answer("Як з тобою зв'язатись? 📞\n\nНапиши Telegram @username або номер телефону:")

@router.message(Quiz.contact)
async def quiz_contact(msg: Message, state: FSMContext):
    await state.update_data(contact=msg.text.strip())
    data = await state.get_data()
    await state.set_state(Quiz.confirm)
    await msg.answer(
        f"📋 <b>Перевір заявку:</b>\n\n"
        f"📦 Послуга: {data['service']}\n"
        f"💵 Бюджет: {data['budget']}\n"
        f"⏰ Терміни: {data['timeline']}\n"
        f"👤 Ім'я: {data['name']}\n"
        f"📞 Контакт: {data['contact']}",
        parse_mode="HTML",
        reply_markup=confirm_kb()
    )

@router.callback_query(Quiz.confirm, F.data == "c:yes")
async def quiz_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = cb.from_user
    lead_id = await db.add_lead(
        user.id, user.username,
        data["name"], data["service"],
        data["budget"], data["timeline"], data["contact"]
    )
    await state.clear()
    await cb.message.edit_text(
        f"✅ <b>Заявку #{lead_id} надіслано!</b>\n\n"
        "Наша команда зв'яжеться з тобою протягом 15 хвилин 🚀",
        parse_mode="HTML"
    )
    notify = (
        f"🔔 <b>Нова заявка #{lead_id}</b>\n\n"
        f"👤 {data['name']} (@{user.username or '—'})\n"
        f"📦 {data['service']}\n"
        f"💵 {data['budget']}\n"
        f"⏰ {data['timeline']}\n"
        f"📞 {data['contact']}"
    )
    for admin_id in ADMIN_IDS:
        try:
            from bot.keyboards.admin_kb import lead_kb
            await bot.send_message(admin_id, notify, parse_mode="HTML", reply_markup=lead_kb(lead_id, "new"))
        except Exception:
            pass

@router.callback_query(Quiz.confirm, F.data == "c:restart")
async def quiz_restart(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Quiz.service)
    await cb.message.edit_text("Що потрібно зробити? 👇", reply_markup=service_kb())
