from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_main_kb(counts: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🆕 Нові ({counts.get('new',0)})", callback_data="al:new")],
        [InlineKeyboardButton(text=f"🔄 В роботі ({counts.get('in_progress',0)})", callback_data="al:in_progress")],
        [InlineKeyboardButton(text=f"✅ Закриті ({counts.get('closed',0)})", callback_data="al:closed")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a:stats")],
    ])

def lead_kb(lead_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if lead_id:
        rows.append([
            InlineKeyboardButton(text="📞 Телефон", callback_data=f"lf:{lead_id}:phone"),
            InlineKeyboardButton(text="✈️ Telegram", callback_data=f"lf:{lead_id}:tg"),
        ])
        rows.append([
            InlineKeyboardButton(text="🏷 Тип проєкту", callback_data=f"lf:{lead_id}:type"),
            InlineKeyboardButton(text="💰 Бюджет", callback_data=f"lf:{lead_id}:budget"),
            InlineKeyboardButton(text="📅 Дедлайн", callback_data=f"lf:{lead_id}:deadline"),
        ])
        rows.append([InlineKeyboardButton(text="📤 Відправити в бухгалтерію", callback_data=f"lf:{lead_id}:send")])
        if status == "new":
            rows.append([InlineKeyboardButton(text="🔄 В роботу", callback_data=f"ls:{lead_id}:in_progress")])
        elif status == "in_progress":
            rows.append([InlineKeyboardButton(text="✅ Закрити", callback_data=f"ls:{lead_id}:closed")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="a:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
