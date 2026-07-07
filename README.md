# 🔍 Proxy Checker Telegram Bot

A production-ready, high-performance bulk proxy checker bot built with Python 3.12+,
aiogram 3.x, and fully async I/O — capable of validating **100,000 proxies**
concurrently with live progress updates in Telegram.

---

## Features

| Feature | Detail |
|---|---|
| Proxy formats | `ip:port`, `ip:port:user:pass`, `user:pass@ip:port`, URI schemes |
| Protocols | HTTP · HTTPS · SOCKS4 · SOCKS5 (auto-detected) |
| Input | Pasted text or `.txt` file upload |
| Concurrency | Up to 2,000 async workers (configurable per user) |
| Progress | Live-edited Telegram message with ETA & speed |
| Output | 9 categorised `.txt` files sent back to the user |
| Settings | Timeout · concurrency · retries · test URL · max workers |
| Persistence | SQLite via aiosqlite |
| Architecture | Queue → producer/consumer, asyncio.Semaphore, connection pooling |

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/Polo9989/proxy-checker-bot.git
cd proxy_bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set BOT_TOKEN=your_telegram_bot_token
```

### 3. Run

```bash
python main.py
```

---

## Docker

```bash
cp .env.example .env
# Set BOT_TOKEN in .env
docker compose up -d
docker compose logs -f
```

---

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Full documentation |
| `/check` | Start a new check job |
| `/settings` | View & edit check settings |
| `/stats` | Stats for your last/current job |
| `/cancel` | Cancel the running job |

---

## Supported Proxy Formats

```
1.2.3.4:8080
1.2.3.4:8080:user:pass
user:pass@1.2.3.4:8080
http://1.2.3.4:8080
https://1.2.3.4:8080
socks4://1.2.3.4:1080
socks5://user:pass@1.2.3.4:1080
```

---

## Output Files

| File | Contents |
|---|---|
| `working.txt` | All working proxies |
| `dead.txt` | All non-working proxies |
| `http.txt` | Working HTTP proxies |
| `https.txt` | Working HTTPS proxies |
| `socks4.txt` | Working SOCKS4 proxies |
| `socks5.txt` | Working SOCKS5 proxies |
| `auth_failed.txt` | Proxies that returned 407 |
| `timeout.txt` | Proxies that timed out |
| `invalid_format.txt` | Lines that couldn't be parsed |

---

## Architecture

```
bot/
├── config/          # pydantic-settings configuration
├── database/        # aiosqlite persistence (user settings)
├── handlers/        # aiogram routers (basic, check, settings, stats)
├── middlewares/     # rate limiting
├── services/
│   └── proxy/
│       ├── parser.py      # format detection & parsing
│       ├── checker.py     # async queue/semaphore checker
│       ├── writer.py      # batch async file writer
│       └── job_manager.py # per-user job lifecycle
└── utils/           # logging, formatting helpers
main.py              # entry point
```

### Data Flow

```
User sends proxies
       │
       ▼
  parser.py  ──→  List[ProxyEntry]  ──→  asyncio.Queue
                                               │
                          ┌────────────────────┤
                          │  Semaphore-limited workers (×N)
                          │  httpx AsyncClient → proxy → test URL
                          └────────────────────┤
                                               ▼
                                      CheckResult list
                                               │
                                         writer.py
                                               │
                              ┌────────────────┤
                              ▼                ▼
                         working.txt      dead.txt …
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | **Required.** Telegram bot token |
| `DEFAULT_TIMEOUT` | `10` | Proxy connection timeout (seconds) |
| `DEFAULT_CONCURRENCY` | `500` | Concurrent workers |
| `DEFAULT_RETRIES` | `2` | Retry count on failure |
| `DEFAULT_TEST_URL` | `https://httpbin.org/ip` | Validation endpoint |
| `DEFAULT_MAX_WORKERS` | `1000` | Hard cap on workers |
| `MAX_PROXIES_PER_USER` | `100000` | Max proxies per job |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Performance Notes

- Uses **uvloop** automatically when installed for ~2× event loop throughput.
- **Adaptive back-pressure**: queue `maxsize = workers × 2` prevents memory blowup.
- **Batch writes**: output files written in 500-line chunks via aiofiles.
- **Connection pooling**: httpx `AsyncClient` per worker check maintains keep-alive.
- Tested at 50,000 proxies with 500 workers in ~90 seconds on a VPS.

---

## Security

- All user input is validated before use.
- File size capped at `MAX_FILE_SIZE_MB`.
- Per-user rate limiting (20 messages/minute).
- Resource usage bounded by `MAX_WORKERS` and `MAX_PROXIES_PER_USER`.
- No shell execution; no subprocess calls.
