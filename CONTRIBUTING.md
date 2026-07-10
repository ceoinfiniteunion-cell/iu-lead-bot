# Contributing to IU Lead Bot

## Development setup

```bash
git clone https://github.com/ceoinfiniteunion-cell/iu-lead-bot.git
cd iu-lead-bot
pip install -r requirements.txt
```

## Environment variables

Copy and fill in all required variables (see README.md for full table):

```bash
export BOT_TOKEN=...
export DATABASE_URL=...
export REDIS_URL=...
export ADMIN_IDS=...
```

## Running locally

```bash
uvicorn api:app --reload &
python -m bot.main
```

## Before submitting a PR

```bash
mypy api.py --ignore-missing-imports
pytest tests/ -v
```

Both must pass with 0 errors.

## Code standards

- Type hints on all function signatures
- No `except: pass` — always log with `logger.exception()`
- No secrets in code — use environment variables
- Every new endpoint needs a test in `tests/test_api.py`
- Follow existing module structure (see README.md)
