# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | ✅        |

## Reporting a Vulnerability

If you discover a security vulnerability, **do not open a public GitHub issue**.

Please report it privately:

- Telegram: [@infiniteunion_manager](https://t.me/infiniteunion_manager)
- Response time: within 24 hours

## What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

## Security measures in this project

- CORS restricted to production domain only
- Rate limiting via Redis (3 req/IP/24h on AI endpoints)
- Honeypot field on all public forms
- Pydantic input validation + `html.escape()` sanitization
- Parameterized SQL queries (asyncpg) — SQL injection impossible
- Secrets via Railway environment variables only — never in code
- Audit log for all API events
- Circuit breaker on external AI API calls
