from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as Btn

def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🚀 Залишити заявку", callback_data="quiz:start")],
    ])

def service_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🌐 Сайт",                    callback_data="s:site")],
        [Btn(text="🤖 Telegram-бот",             callback_data="s:bot")],
        [Btn(text="⚡ Екосистема (сайт + бот)",  callback_data="s:ecosystem")],
        [Btn(text="💬 Інше",                     callback_data="s:other")],
    ])

def budget_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="💵 до $500",         callback_data="b:lt500")],
        [Btn(text="💵 $500 – $1 000",   callback_data="b:500_1k")],
        [Btn(text="💵 $1 000 – $3 000", callback_data="b:1k_3k")],
        [Btn(text="💵 $3 000+",         callback_data="b:3kplus")],
    ])

def timeline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🔥 Терміново (до тижня)", callback_data="t:urgent")],
        [Btn(text="📅 1–2 тижні",            callback_data="t:twoweeks")],
        [Btn(text="🗓 Не поспішаю",          callback_data="t:nohurry")],
    ])

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="✅ Підтвердити і надіслати", callback_data="c:yes")],
        [Btn(text="🔄 Почати знову",            callback_data="c:restart")],
    ])
