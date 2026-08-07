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
  - `storage.py` — sqlite key-value store under both managers, plus the one-shot
    import of the pickleDB-era JSON files
- `tests/` — pytest, one package per area: `parser/`, `formatter/`, `storage/`,
  `rates/`, `bot/`, `config/`, plus `test_currencies_reference.py` at the root
  - a package gets a `conftest.py` only when it has fixtures of its own (`bot/`,
    `formatter/`, `rates/`, `storage/`) and a `doubles.py` only when it has test doubles
    (`bot/`, `rates/`, `storage/`) — a plain module rather than `conftest`, so
    `--import-mode=importlib` keeps working. `parser/` and `config/` have neither.
  - `tests/bot/conftest.py` additionally imports `src.bot` once, at collection time,
    with the module's import-time side effects neutralised
  - `stubs.py` — the one double shared across packages (`StubCurrencyParser`, behind the
    root `parser` fixture); `logcapture.py` — `capture_logs()` / `assert_no_logs()` for
    asserting on what a module logs
  - the root `conftest.py` sets the required ENV vars before `src.settings` is
    imported, and defines the shared `parser` fixture below that block
- `data/` — runtime state (gitignored, mounted as a docker volume)
- `main.py` — thin entry point over `src/`

## Setup
**Python 3.11+ is required.** `src/currency_parser.py` relies on possessive quantifiers
(`\d{1,3}+`, `\d++`), which `re` only supports from 3.11 — on 3.10 the module raises
`re.error` at import time, before any test runs. Dockerfile and CI both use 3.11; if
`make install` picks up an older system `python3`, that is the cause.

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
  reach the log that way.
- On top of that, `src/bot.py` installs a redaction layer that masks the bot token as
  `<BOT_TOKEN>`, `API_KEY` as `<API_KEY>` and `INFLUX_TOKEN` as `<INFLUX_TOKEN>`: a
  filter on LOGGING HANDLERS — message, args, the rendered traceback of `exc_info` and
  `stack_info` — plus `sys.excepthook` and `threading.excepthook` for uncaught exceptions
  in the main thread and in telebot workers. That is the path that used to leak:
  `requests` puts the full request URL into its exception text.
  `Logger.callHandlers` goes from the emitting logger UP to the root, so a handler on
  some other logger runs BEFORE the root handlers (`telebot` adds one to the `TeleBot`
  logger at import) — the filter therefore goes on the handlers of every logger that
  already exists, and `Logger.addHandler` is wrapped so handlers attached later are
  covered as well. It covers what goes through `logging` and the two hooks, and it is
  NOT a proof that the token cannot leak: a `print()`, a direct write to `stdout` or a
  C-level library never reaches the filter — so still never log credentials on purpose,
  and prefer `exc_info=True` over interpolating `str(exc)` into the message.
- No default/example credentials in code; missing ENV var → fail at startup.
- Code comments are in English.
- All repeated actions (env setup, tests, run) go through `make` targets — add or
  extend a target instead of running ad-hoc commands.
- Python always runs inside a local `.venv`, created automatically by `make` on
  first use (`make test` / `make run` bootstrap it) — never the system Python.
- Minimum Python is **3.11** (see Setup): the parser's possessive quantifiers are a
  3.11 `re` feature, so anything older fails at import. Do not lower it in the
  Dockerfile or CI without rewriting `self.number` in `src/currency_parser.py`.
- Tests are required for new code; in CI `build` depends on `test`.
- No `EXPOSE` in the Dockerfile — the bot polls Telegram and has no inbound port.
- The container runs as non-root user `app` (uid 1000) — the entrypoint starts as
  root, fixes `/app/data` ownership and drops privileges via gosu. Do not add a
  `USER` directive to the Dockerfile and do not remove the entrypoint.
