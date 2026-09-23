# personal-ai-assistant

**Current reality:** a small authenticated **SMS API stub** (FastAPI) with a pluggable provider interface. The historical README claimed a multi-model ChatGPT/Claude assistant — that application does **not** exist in this repository yet.

## What works today

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /health` | Public | Liveness |
| `POST /sms/send` | API key | Send SMS via configured provider |
| `POST /sms/schedule` | API key | Schedule SMS |
| `POST /sms/details` | API key | Mobile lookup (provider-dependent) |
| `GET /sms/validate/{phone}` | API key | Format check |
| `GET /sms/status` | API key | Stub status |

## Security model (live-ready path)

1. **API key required** on all `/sms/*` routes via `Authorization: Bearer <key>` or `X-API-Key`.
2. **Fail closed:** if `ENV=production` or `REQUIRE_AUTH=1` (default) and `API_KEY` is unset → SMS routes return `503`.
3. **Secrets are server-side only.** Request bodies must **not** include Way2sms usernames/passwords (`extra=forbid`).
4. **HTTPS preferred** for Way2sms. Cleartext HTTP is refused unless `ALLOW_INSECURE_SMS_HTTP=1`.
5. **No shared authenticated HTTP session** across requests — each send/schedule uses an isolated client and checks login success **before** send.
6. **Generic client errors**; phones/passwords redacted from logs.
7. **Message `max_length=160`** and a simple **in-memory rate limit** per API key (`RATE_LIMIT_PER_MINUTE`, default 30). Use Redis for multi-instance deployments.

## Provider note (important live risk)

The default provider (`SMS_PROVIDER=way2sms`) scrapes a third-party web UI. That is fragile and historically used cleartext HTTP. **For real production SMS, implement `providers/twilio.py` (or another official HTTPS API)** behind the existing `SmsProvider` interface. Do not fabricate Twilio credentials in this repo.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set API_KEY and WAY2SMS_* (or switch provider later)

uvicorn main:app --host 127.0.0.1 --port 8000
```

Example authenticated send:

```bash
curl -sS -X POST http://127.0.0.1:8000/sms/send \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"recipient":"9876543210","message":"hello"}'
```

## Tests

```bash
pytest -q
```

## Environment

See `.env.example` for all variables. Never commit `.env`.

## Roadmap (not implemented)

- Multi-model chat assistant (ChatGPT / Claude)
- Twilio (or other official) SMS provider
- Redis-backed rate limiting
