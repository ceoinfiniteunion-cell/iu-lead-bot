from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as Btn

def admin_main_kb(counts: dict):
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text=f"🆕 Нові ({counts.get('new',0)})",          callback_data="al:new")],
        [Btn(text=f"🔄 В роботі ({counts.get('in_progress',0)})", callback_data="al:in_progress")],
        [Btn(text=f"✅ Закриті ({counts.get('closed',0)})",     callback_data="al:closed")],
        [Btn(text="📊 Статистика",                              callback_data="a:stats")],
    ])

def lead_kb(lead_id: int, status: str):
    rows = []
    if status != "in_progress":
        rows.append([Btn(text="🔄 В роботу", callback_data=f"ls:{lead_id}:in_progress")])
    if status != "closed":
        rows.append([Btn(text="✅ Закрити",  callback_data=f"ls:{lead_id}:closed")])
    if status != "new":
        rows.append([Btn(text="🆕 Новий",    callback_data=f"ls:{lead_id}:new")])
    rows.append([Btn(text="◀️ Назад",        callback_data="a:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
