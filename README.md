# znany-lekarz-scheduler

Monitors appointment availability on [znany lekarz.pl](https://www.znany lekarz.pl) and sends notifications (Telegram, email, etc.) when new slots appear. Uses stealth Playwright/Chromium automation.

## Requirements

- Docker + Docker Compose
- A znany lekarz.pl account
- A notification channel (e.g. Telegram bot token + chat ID)

## Quick start

### 1. Configure

```bash
cp config.example.toml config.toml
cp .env.example .env
```

Edit `config.toml` — set your notification URLs and the doctors to monitor:

```toml
[notifications]
apprise_urls = ["tgram://BOT_TOKEN/CHAT_ID"]

[[doctors]]
name = "Dr Jan Kowalski"
url = "https://www.znany lekarz.pl/jan-kowalski/kardiolog/warszawa"
speciality = "Kardiologia"
```

Edit `.env` — set your credentials:

```env
ZNANY_LEKARZ_EMAIL=twoj@email.pl
ZNANY_LEKARZ_PASSWORD=twoje_haslo
```

### 2. First-time login (saves browser session)

The monitor reuses a saved browser session to avoid logging in on every run. To create it:

**On Linux (X11):**

```bash
xhost +local:docker
docker compose run --rm setup
```

A browser window will open. Log in manually, then press Enter in the terminal.

**Without a display (headless workaround):**

Run setup locally (requires Python 3.13 + uv):

```bash
uv sync && playwright install chromium
python -m znany_lekarz_scheduler.main --setup
```

The session is saved to `data/cookies/session.json`, which is mounted into the container automatically.

### 3. Build and run

```bash
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f scheduler
```

Stop:

```bash
docker compose down
```

## Configuration reference

### `config.toml`

| Key | Default | Description |
|-----|---------|-------------|
| `schedule.check_interval_minutes` | `45` | How often to check each doctor |
| `schedule.active_hours_start` | `"07:00"` | No checks before this time |
| `schedule.active_hours_end` | `"22:30"` | No checks after this time |
| `schedule.active_days` | all days | Days to check (e.g. `["mon","tue","wed","thu","fri"]`) |
| `schedule.jitter_percent` | `25` | Random ± spread on interval to avoid patterns |
| `browser.headless` | `true` | Run browser without GUI |
| `browser.locale` | `"pl-PL"` | Browser locale |
| `browser.timezone` | `"Europe/Warsaw"` | Browser timezone |
| `notifications.apprise_urls` | `[]` | [Apprise](https://github.com/caronc/apprise) notification URLs |
| `notifications.cooldown_minutes` | `120` | Minimum time between repeat notifications per doctor |
| `doctors[].name` | required | Display name |
| `doctors[].url` | required | Full znany lekarz.pl doctor URL |
| `doctors[].speciality` | optional | For display only |
| `doctors[].check_priority` | `1` | 1 = highest priority |

### `.env`

| Variable | Description |
|----------|-------------|
| `ZNANY_LEKARZ_EMAIL` | Login email |
| `ZNANY_LEKARZ_PASSWORD` | Login password |

## Data persistence

The container mounts `./data/` from the host:

```
data/
├── cookies/session.json   # saved browser session (created by --setup)
├── state/known_slots.json # tracks which slots have already been notified
└── logs/monitor.log       # structured JSON log
```

Back up `data/` to preserve state across container rebuilds.

## Development

```bash
# Install dependencies
uv sync
playwright install chromium

# Run tests
pytest

# Run monitor locally
python -m znany_lekarz_scheduler.main run

# Test notifications
python -m znany_lekarz_scheduler.main --test-notify
```

## Notification examples

Apprise URL formats for common channels:

```toml
apprise_urls = [
    "tgram://BOT_TOKEN/CHAT_ID",                          # Telegram
    "mailto://user:app_pass@gmail.com?to=me@gmail.com",   # Gmail
    "pover://USER_KEY@APP_TOKEN",                          # Pushover
    "slack://TokenA/TokenB/TokenC/CHANNEL",               # Slack
]
```

See the full [Apprise URL list](https://github.com/caronc/apprise/wiki).

## Architecture

```
config/ ──► browser/ ──► scraper/ ──► monitor/ ──► notifier/
  │                          │            │
  └── config.toml + .env     │            └── state/ (known slots)
                             └── cookies/ (session)
```

- **browser/** — Playwright manager with anti-detection and human behaviour simulation
- **scraper/** — Logs in, navigates doctor pages, parses appointment slots
- **monitor/** — APScheduler orchestrator, session refresh, state diff
- **notifier/** — Apprise multi-channel notification with per-doctor cooldown

## Anti-detection rules

The scheduler enforces these limits to avoid being blocked:

- Max 2 requests per minute across all doctors
- 30–90 s random delay between doctor checks
- No activity between 23:00–07:00
- Max 10 doctors per configuration
- Human-like mouse movement, scroll, and typing via `HumanBehaviorSimulator`