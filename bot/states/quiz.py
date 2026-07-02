from aiogram.fsm.state import State, StatesGroup

class Quiz(StatesGroup):
    service  = State()
    budget   = State()
    timeline = State()
    name     = State()
    contact  = State()
    confirm  = State()
