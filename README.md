# IU Lead Bot

Telegram-бот та FastAPI сервер для обробки заявок Infinite Union.

## Стек

- Python 3.11
- aiogram 3 — Telegram бот
- FastAPI — HTTP API
- asyncpg — PostgreSQL
- Redis — FSM стани + rate-limit
- Railway — деплой

## Запуск локально

```bash
pip install -r requirements.txt
uvicorn api:app --reload &
python -m bot.main
```

## Змінні середовища

| Змінна | Де використовується | Обов'язкова | Що станеться якщо не задати |
|---|---|---|---|
| `BOT_TOKEN` | `bot/config.py`, `api.py` | ✅ | Бот не стартує (RuntimeError) |
| `DATABASE_URL` | `bot/config.py`, `api.py` lifespan | ✅ | Сервер не стартує (RuntimeError) |
| `REDIS_URL` | `bot/config.py`, rate-limit | ✅ | Бот не стартує, rate-limit вимкнено |
| `ADMIN_IDS | `12345678,87654321` | Telegram user IDs через запятую (обязательная)
| `ANTHROPIC_API_KEY` | `api.py` `/generate` | ✅ | `/generate` повертає 503 |
| `BUH_BOT_TOKEN` | `bot/handlers/admin.py` | ⚠️ | Відправка в бухгалтерію не працює |
| `BUH_API_URL` | `bot/handlers/admin.py` | ⚠️ | Відправка в бухгалтерію не працює |

## API ендпоінти

| Метод | Шлях | Опис |
|---|---|---|
| `POST` | `/lead` | Прийом заявки з сайту |
| `POST` | `/generate` | Проксі до Anthropic API (rate-limit: 3 req/IP/24г) |
| `GET` | `/health` | Перевірка статусу сервісу |

## Безпека

- CORS обмежений доменом `ceoinfiniteunion-cell.github.io`
- Rate-limit на `/generate` через Redis (3 запити/IP/24 години)
- Honeypot перевірка на `/lead`
- Pydantic валідація всіх вхідних даних
- `html.escape()` санітизація перед збереженням в БД
- Секрети тільки в Railway env vars

## Тести

```bash
pytest tests/ -v
```

## Domain & Deployment

- **Bot API**: deployed on [Railway](https://railway.app) — project `brave-renewal`
- **Website**: currently on GitHub Pages (`ceoinfiniteunion-cell.github.io/iuwebsite`)
- **Production domain**: `infiniteunion.com.ua` — DNS migration in progress

> Note: canonical URL in `index.html` already points to `infiniteunion.com.ua`.
> GitHub Pages will be replaced with the production domain shortly.
