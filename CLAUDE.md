# CLAUDE.md — znany_lekarz_scheduler

## Project overview

A Playwright-based monitor that checks appointment availability on znany lekarz.pl and sends notifications when new slots appear. Uses stealth browser automation to avoid bot detection.

## Tech stack

- Python 3.13, `uv` for package management
- `playwright` (Chromium) — browser automation
- `apscheduler` — scheduling
- `apprise` — multi-channel notifications (Telegram, email, etc.)
- `pydantic` / `pydantic-settings` — config validation
- `structlog` + `rich` — structured logging
- `pytest` + `pytest-asyncio` — tests

## Commands

```bash
# Install dependencies
uv sync
playwright install chromium

# Run CLI
python -m znany_lekarz_scheduler.main --help
python -m znany_lekarz_scheduler.main --setup        # headful login, saves session
python -m znany_lekarz_scheduler.main --test-notify  # test notification channels
python -m znany_lekarz_scheduler.main run            # start monitoring

# Tests
pytest
```

## Project structure

```
src/znany_lekarz_scheduler/
├── config/         # Pydantic models + config.toml / .env loader
├── browser/        # Playwright manager, anti-detection, human behavior simulation
├── scraper/        # Login, doctor page scraping, slots parser
├── monitor/        # Session manager, scheduler, state diff
├── notifier/       # Apprise integration, message formatter
├── utils/          # Delays, rate limiter, logger
└── main.py         # CLI entry point (argparse)
```

## Configuration

- `config.toml` — schedule, browser, notifications, doctors list (see `config.example.toml`)
- `.env` — credentials: `ZNANY_LEKARZ_EMAIL`, `ZNANY_LEKARZ_PASSWORD`
- Session stored in `data/cookies/session.json`
- State (known slots) in `data/state/known_slots.json`

## Implementation status (as of 2026-03-13)

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project foundation (config, logger, CLI) | Done |
| 2 | Browser + anti-detection + human behavior | Done |
| 3 | Login + session management | Done |
| 4 | Scraping appointment slots (`doctor_page.py`, `slots_parser.py`) | Done |
| 5 | State diff (`state_manager.py`) | Done |
| 6 | Notifications (`apprise_notifier.py`, `formatter.py`) | Done |
| 7 | Scheduler orchestration (`scheduler.py`, full `run`) | Done |
| 8 | Deployment (Docker, E2E tests, README) | Done |

## Key constraints (anti-blocking rules)

- Max 1 request per session every 30 seconds
- Max 10 doctors per run
- No activity between 23:00–07:00
- 30–90s delay between doctors
- Always use `HumanBehaviorSimulator` methods for navigation/input

## AppointmentSlot model (Phase 4+)

```python
@dataclass
class AppointmentSlot:
    doctor_name: str
    doctor_url: str
    datetime: datetime
    slot_id: str
    location: str | None = None
```

Slot unique key: `f"{doctor_url}_{slot_datetime.isoformat()}"`

## Phase 4 note — HTML analysis required

Before implementing `slots_parser.py` and `doctor_page.py`, the actual DOM structure of a znany lekarz.pl doctor page must be inspected manually to identify correct CSS selectors for the calendar and appointment slots.


## An Example Pages

A page automatically shows the nearest available date, so wait a few seconds after requesting/loading the page.

https://www.znanylekarz.pl/ewa-krajewska-siuda-2/endokrynolog/krakow - the page with a singel location
the html is saved in html/strona_lekarza.txt file
available dates on 16 Mar:
8:30, 9:00, 11:00, 11:30
unavailable dates on 16 Mar:
8:00, 9:30, 10:30


https://www.znanylekarz.pl/sylwia-kuzniarz-rymarz/endokrynolog-internista/zabierzow - the page with the multiple locations
the html is saved in html/strona_lekarza2.txt file
available dates on 16 Mar:
11:20, 13:20, 
unavailable dates on 16 Mar:
11:00, 11:40, 12:00, 12:40, 13:00




