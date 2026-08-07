# Agent Instructions — currva_converter_bot

Telegram bot that finds amounts of money in chat messages and replies with the same
amount converted into other currencies. Also works in inline mode.

## Project structure
- `src/` — application code
  - `settings.py` — the single config entry point (pydantic-settings)
  - `bot.py` — telebot handlers, watchdog auto-restart, `main()`
  - `currencies.py` — the currency reference book (`CURRENCIES`)
  - `currency_parser.py` — finds amounts + currencies in free text
  - `currency_formatter.py` — renders the conversion message
  - `exchange_rates_manager.py` — rates from apilayer + on-disk cache
  - `statistics_manager.py` — usage counters + optional InfluxDB reporting
  - `user_settings_manager.py` — per-user / per-chat currency lists
- `tests/` — pytest (`stubs.py` holds the shared test doubles; `conftest.py` only sets
  the required ENV vars before `src.settings` is imported)
- `data/` — runtime state (gitignored, mounted as a docker volume)
- `main.py` — thin entry point over `src/`

## Setup
All routine actions go through the `Makefile` — run `make help` to list targets.
```bash
make install           # create .venv and install dev/test deps
cp .env.example .env   # then fill in the values  (shortcut: make env)
```

## Running tests
```bash
make test              # runs .venv/bin/pytest
```

## Running the app
```bash
make run               # runs .venv/bin/python main.py
```

## Conventions
- The currency reference book is the single source of truth in `src/currencies.py`;
  the parser and the formatter take currencies only from there. Adding a currency
  means adding one entry to `CURRENCIES` — it then gets an ISO-code parser pattern
  and becomes a valid `/currencies` target automatically.
- All mutable state goes under `data/`.
- All config comes from ENV / `.env` (see `.env.example`), read through `Settings`.
- Credentials go ONLY into `.env` (never into code, never via inline env vars) and are
  never written to the log through a logger — not even partially. `LOG_LEVEL=DEBUG`
  does not switch on HTTP request logging (the HTTP client loggers are clamped to
  `max(INFO, LOG_LEVEL)`), so the bot token embedded in every Telegram API URL does not
  reach the log that way. An uncaught exception is a different path: `requests` puts the
  full request URL into its message, so a traceback printed to stderr can still expose
  the token regardless of `LOG_LEVEL`.
- No default/example credentials in code; missing ENV var → fail at startup.
- Code comments are in English.
- All repeated actions (env setup, tests, run) go through `make` targets — add or
  extend a target instead of running ad-hoc commands.
- Python always runs inside a local `.venv`, created automatically by `make` on
  first use (`make test` / `make run` bootstrap it) — never the system Python.
- Tests are required for new code; in CI `build` depends on `test`.
- No `EXPOSE` in the Dockerfile — the bot polls Telegram and has no inbound port.
- The container runs as non-root user `app` (uid 1000) — the entrypoint starts as
  root, fixes `/app/data` ownership and drops privileges via gosu. Do not add a
  `USER` directive to the Dockerfile and do not remove the entrypoint.
