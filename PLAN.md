# Monitor Dostepnosci Terminow na znany lekarz.pl

## Spis tresci

1. [Analiza problemu i ryzyka](#1-analiza-problemu-i-ryzyka)
2. [Architektura](#2-architektura)
3. [Kluczowe klasy i moduly](#3-kluczowe-klasy-i-moduly)
4. [Mechanizmy anty-blokadowe](#4-mechanizmy-anty-blokadowe)
5. [Plan implementacji - fazy](#5-plan-implementacji---fazy)
6. [Deployment](#6-deployment)
7. [Ryzyka i mitygacje](#7-ryzyka-i-mitygacje)

---

## 1. Analiza problemu i ryzyka

### Mechanizmy ochronne znany lekarz.pl (przypuszczalne)

| Mechanizm | Ryzyko | Mitygacja |
|---|---|---|
| Rate limiting po IP | Wysokie | Losowe opoznienia, ograniczenie czestotliwosci |
| Wykrywanie botow (fingerprinting) | Wysokie | Playwright z ludzkim profilem przegladarki |
| Captcha (reCAPTCHA / hCaptcha) | Srednie | Playwright, degradacja graceful |
| Analiza naglowkow HTTP | Srednie | Realistyczne User-Agent, Accept-Language |
| Wykrywanie automatycznych klikniec | Srednie | Losowe ruchy myszy, czasy reakcji |
| Blokada konta po naduzywaniu sesji | Krytyczne | Monitorowanie z konta zwyklego uzytkownika, limity |
| Zakaz TOS | Prawne | Umiarkowana czestotliwosc, tylko odczyt |

### Zasady bezpieczenstwa konta

- Nigdy nie wykonuj wiecej niz 1 zapytanie na sesje co 30 sekund
- Nie monitoruj wiecej niz 10 lekarzy w jednym przebiegu
- Przerwy nocne (23:00 - 7:00) - brak aktywnosci
- Symuluj ludzkie zachowanie: scrollowanie, losowe pauzy
- Przechowuj ciasteczka sesji miedzy uruchomieniami

---

## 2. Architektura

### Stack technologiczny

```
Python 3.13
playwright          # pip install playwright && playwright install chromium
pydantic            # walidacja konfiguracji
pydantic-settings   # konfiguracja z .env
apscheduler         # harmonogram zadan
apprise             # powiadomienia (email, SMS, Telegram, Pushover, etc.)
structlog           # logowanie strukturalne
rich                # ladne logi w terminalu
tomllib             # parsowanie konfiguracji (wbudowane w Python 3.11+)
pytest + pytest-asyncio
```

### Struktura projektu

```
znany_lekarz_scheduler/
├── pyproject.toml
├── config.toml                    # Konfiguracja uzytkownika
├── config.example.toml            # Przykladowa konfiguracja
├── .env                           # Dane wrazliwe (login, tokeny powiadomien)
├── .env.example
├── .gitignore                     # Wyklucza .env, data/, __pycache__
├── PLAN.md
├── data/
│   ├── cookies/                   # Zapisane sesje przegladarki
│   │   └── session.json
│   ├── state/                     # Ostatnio widziane terminy (diff)
│   │   └── known_slots.json
│   └── logs/
│       └── monitor.log
└── src/
    └── znany_lekarz_scheduler/
        ├── __init__.py
        ├── main.py                # Punkt wejscia, CLI (--setup, --test-notify, run)
        ├── config/
        │   ├── __init__.py
        │   ├── models.py          # Pydantic modele konfiguracji
        │   └── loader.py          # Ladowanie config.toml + .env
        ├── browser/
        │   ├── __init__.py
        │   ├── manager.py         # Zarzadzanie instancja Playwright
        │   ├── anti_detection.py  # Techniki anty-wykrycia (webdriver, fingerprint)
        │   └── human_behavior.py  # Symulacja ludzkiego zachowania
        ├── scraper/
        │   ├── __init__.py
        │   ├── login.py           # Logowanie do portalu, zapis/odczyt sesji
        │   ├── doctor_page.py     # Nawigacja i ekstrakcja terminow
        │   └── slots_parser.py    # Parsowanie kalendarza -> lista AppointmentSlot
        ├── monitor/
        │   ├── __init__.py
        │   ├── scheduler.py       # APScheduler - harmonogram z jitterem
        │   ├── session.py         # Zarzadzanie sesja monitorowania
        │   └── state_manager.py   # Diff terminow (nowe vs znane)
        ├── notifier/
        │   ├── __init__.py
        │   ├── base.py            # Abstrakcyjna klasa notifiera
        │   ├── apprise_notifier.py # Integracja z Apprise
        │   └── formatter.py       # Formatowanie wiadomosci
        └── utils/
            ├── __init__.py
            ├── delays.py          # Losowe opoznienia
            ├── rate_limiter.py    # Token bucket rate limiter
            └── logger.py          # Konfiguracja structlog + rich
```

### Schemat dzialania

```
Uruchomienie
    |
    v
Wczytaj config.toml + .env
    |
    v
Uruchom przegladarke Playwright (headless Chromium)
    |
    v
Zaladuj zapisana sesje (cookies)?
   [TAK] --> Sprawdz czy sesja wazna --> [NIE] --> Zaloguj sie ponownie
   [NIE] --> Zaloguj sie --> Zapisz sesje
    |
    v
Uruchom APScheduler
    |
    v
[CO check_interval +/- jitter MINUT, tylko w active_hours]:
    Dla kazdego lekarza (z losowym offsetem miedzy nimi):
        1. Przejdz na strone lekarza
        2. Poczekaj losowy czas (2-5s) po zaladowaniu
        3. Scrolluj strone naturalnie
        4. Wyodrebnij dostepne terminy z kalendarza
        5. Porownaj z ostatnim stanem (StateManager)
        6. Jesli nowe terminy -> wyslij powiadomienie
        7. Zapisz nowy stan
        8. Poczekaj 30-90s przed nastepnym lekarzem
    |
    v
[Kontynuuj az do zatrzymania / bledu krytycznego]
```

### Konfiguracja (`config.toml`)

```toml
[schedule]
check_interval_minutes = 45
active_hours_start = "07:00"
active_hours_end = "22:30"
active_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
jitter_percent = 25

[browser]
headless = true
browser_type = "chromium"
locale = "pl-PL"
timezone = "Europe/Warsaw"
# user_data_dir = "/home/user/.config/google-chrome/Default"  # Opcjonalnie

[notifications]
cooldown_minutes = 120
apprise_urls = [
    "tgram://BOT_TOKEN/CHAT_ID",
    # "mailto://user:app_pass@gmail.com?to=me@gmail.com",
    # "pover://USER_KEY@APP_TOKEN",
]

[[doctors]]
name = "Dr Jan Kowalski"
url = "https://www.znanylekarz.pl/jan-kowalski/kardiolog/warszawa"
speciality = "Kardiologia"
check_priority = 1

[[doctors]]
name = "Dr Anna Nowak"
url = "https://www.znanylekarz.pl/anna-nowak/dermatolog/krakow"
speciality = "Dermatologia"
check_priority = 2
```

### Dane wrazliwe (`.env`)

```env
ZNANY_LEKARZ_EMAIL=twoj@email.pl
ZNANY_LEKARZ_PASSWORD=twoje_haslo
```

---

## 3. Kluczowe klasy i moduly

### `config/models.py`

```python
class DoctorConfig(BaseModel):
    name: str
    url: str
    speciality: str | None = None
    check_priority: int = 1           # 1=wysoki, 3=niski

class ScheduleConfig(BaseModel):
    check_interval_minutes: int = 45
    active_hours_start: time = time(7, 0)
    active_hours_end: time = time(22, 30)
    active_days: list[str] = ["mon","tue","wed","thu","fri","sat","sun"]
    jitter_percent: int = 25

class BrowserConfig(BaseModel):
    headless: bool = True
    browser_type: Literal["chromium","firefox"] = "chromium"
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "pl-PL"
    timezone: str = "Europe/Warsaw"
    user_data_dir: str | None = None

class NotificationConfig(BaseModel):
    apprise_urls: list[str] = []
    cooldown_minutes: int = 120

class AppConfig(BaseModel):
    doctors: list[DoctorConfig]
    schedule: ScheduleConfig
    browser: BrowserConfig
    notifications: NotificationConfig
    login_email: str       # z .env
    login_password: str    # z .env
```

### `browser/manager.py`

```python
class BrowserManager:
    """Singleton zarzadzajacy instancja Playwright."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def get_page(self) -> Page: ...
    async def save_session(self, path: Path) -> None: ...
    async def load_session(self, path: Path) -> bool: ...
    async def is_session_valid(self) -> bool: ...
```

### `browser/anti_detection.py`

```python
async def apply_stealth_settings(page: Page) -> None:
    """
    1. Nadpisanie navigator.webdriver = false
    2. Ustawienie realistycznych plugins i mimeTypes
    3. Canvas fingerprint randomizacja
    4. AudioContext fingerprint randomizacja
    5. WebGL vendor/renderer spoofing
    6. Realistyczny User-Agent
    """
```

### `browser/human_behavior.py`

```python
class HumanBehaviorSimulator:
    async def random_delay(self, min_ms=500, max_ms=3000) -> None: ...
    async def move_mouse_naturally(self, page, target_x, target_y) -> None: ...
    async def scroll_page_naturally(self, page) -> None: ...
    async def type_slowly(self, element, text: str) -> None: ...
    async def random_pause_before_click(self) -> None: ...
```

### `scraper/doctor_page.py`

```python
class DoctorPageScraper:
    async def get_available_slots(self, doctor: DoctorConfig) -> list[AppointmentSlot]: ...
    async def _navigate_to_doctor(self, url: str) -> None: ...
    async def _wait_for_calendar(self) -> None: ...
    async def _extract_slots_from_calendar(self) -> list[AppointmentSlot]: ...
    async def _handle_pagination(self) -> bool: ...  # Nastepny tydzien
```

### `monitor/state_manager.py`

```python
@dataclass
class AppointmentSlot:
    doctor_name: str
    doctor_url: str
    datetime: datetime
    slot_id: str
    location: str | None = None

class StateManager:
    """Porownuje aktualny stan z poprzednim - wykrywa nowe terminy."""

    def load_known_slots(self) -> set[str]: ...
    def save_known_slots(self, slots: set[str]) -> None: ...
    def find_new_slots(
        self,
        current: list[AppointmentSlot],
        known: set[str]
    ) -> list[AppointmentSlot]: ...
```

### `monitor/scheduler.py`

```python
class MonitorScheduler:
    def __init__(self, config: AppConfig): ...

    def start(self) -> None:
        """Uruchamia scheduler. Dodaje zadania dla kazdego lekarza
        z roznymi offsetami, zeby nie uderzyc wszystkich na raz."""

    def _calculate_next_check(self, doctor: DoctorConfig) -> datetime:
        """Oblicza nastepny czas sprawdzenia z jitterem (+/- X%)."""

    async def _check_doctor_job(self, doctor: DoctorConfig) -> None:
        """Glowne zadanie: sprawdz terminy -> porownaj -> powiadom."""
```

### `notifier/apprise_notifier.py`

```python
class AppriseNotifier:
    def __init__(self, urls: list[str]): ...

    async def notify_new_slots(self, slots: list[AppointmentSlot]) -> None:
        title = f"Nowe terminy ({len(slots)}) - znany lekarz.pl"
        # Wyslij przez Apprise do wszystkich skonfigurowanych kanalow
```

Obslugiwane kanaly: Telegram, Gmail, Pushover, Slack, Discord, Twilio SMS i 80+ innych.

---

## 4. Mechanizmy anty-blokadowe

### Rate limiting i opoznienia

```python
# utils/delays.py
async def human_delay(base_seconds: float = 2.0, jitter: float = 0.5) -> None:
    """Czeka base +/- jitter sekund."""
    delay = base_seconds + random.uniform(-jitter, jitter)
    await asyncio.sleep(max(0.5, delay))

async def between_doctors_delay() -> None:
    """30-90 sekund miedzy sprawdzaniem lekarzy."""
    await asyncio.sleep(random.uniform(30, 90))

async def post_login_delay() -> None:
    """Po zalogowaniu czekaj jak czlowiek (3-8 sekund)."""
    await asyncio.sleep(random.uniform(3, 8))

# utils/rate_limiter.py
class RateLimiter:
    """Token bucket - max N zapytan na minute."""

    def __init__(self, max_per_minute: int = 2): ...
    async def acquire(self) -> None: ...
```

### Harmonogram sprawdzania

```
check_interval_minutes: 45       # Co 45 minut
jitter_percent: 25               # faktycznie co 34-56 min
active_hours: 07:00 - 22:30     # Tylko w godzinach aktywnosci
between_doctors_delay: 30-90s   # Miedzy lekarzami
max_doctors_per_session: 10

Przykladowy timeline dla 3 lekarzy:
07:00 - Dr Kowalski (check #1)
07:38 - Dr Nowak    (check #1, losowy offset)
08:21 - Dr Wisniewski (check #1)
08:49 - Dr Kowalski (check #2)
...
```

### Obsluga bledow

```
1. Blad sieci / timeout
   -> Retry x3 z exponential backoff (5s, 15s, 45s)
   -> Jesli nadal fail: pomin lekarza w tej turze, loguj

2. Strona zmienila strukture (selektor nie dziala)
   -> Alert do uzytkownika
   -> Zatrzymaj monitorowanie dla tego lekarza

3. Captcha wykryta
   -> Zatrzymaj sesje na 2-4 godziny
   -> Wyslij powiadomienie o problemie
   -> Opcjonalnie: przelacz na tryb headful

4. Sesja wygasla / wylogowanie
   -> Zaloguj sie ponownie automatycznie (max 3 proby)

5. Blad krytyczny
   -> Loguj crash, systemd restartuje proces
```

### Logowanie (structlog)

```python
log.info("slots_checked",
    doctor="Dr Jan Kowalski",
    slots_found=3,
    new_slots=1,
    duration_ms=1240,
    next_check_in_minutes=47,
)
log.warning("captcha_detected",
    doctor="Dr Anna Nowak",
    pausing_hours=3,
)
```

---

## 5. Plan implementacji - fazy

### Faza 1: Fundament projektu

**Cel:** Dzialajacy szkielet aplikacji z konfiguracją i logowaniem.

- [ ] Inicjalizacja projektu: `uv init`, `pyproject.toml`, struktura katalogow `src/`
- [ ] Dodanie zaleznosci: `uv add playwright pydantic pydantic-settings apscheduler apprise structlog rich`
- [ ] `playwright install chromium`
- [ ] Implementacja `config/models.py` - modele Pydantic (DoctorConfig, ScheduleConfig, BrowserConfig, NotificationConfig, AppConfig)
- [ ] Implementacja `config/loader.py` - ladowanie `config.toml` + zmienne z `.env`
- [ ] Implementacja `utils/logger.py` - konfiguracja structlog z rich console output i plikiem logu
- [ ] Stworzenie `config.example.toml` i `.env.example`
- [ ] Stworzenie `.gitignore` (wykluczenie `.env`, `data/`, `__pycache__`)
- [ ] Szkielet `main.py` z CLI (argumenty: `--setup`, `--test-notify`, `run`)

**Weryfikacja:** `python -m znany_lekarz_scheduler.main --help` dziala, konfiguracja sie laduje.

---

### Faza 2: Przeglądarka i anty-wykrycie

**Cel:** Uruchomienie Playwright z pelnymi srodkami anty-wykrycia.

- [ ] Implementacja `browser/manager.py` - start/stop przegladarki, zarzadzanie kontekstem i strona
- [ ] Implementacja `browser/anti_detection.py`:
  - Nadpisanie `navigator.webdriver` przez `page.add_init_script`
  - Realistyczne `navigator.plugins`, `mimeTypes`
  - Canvas fingerprint randomizacja
  - WebGL vendor/renderer spoofing
  - Realistyczny User-Agent zgodny z Chromium
- [ ] Implementacja `browser/human_behavior.py`:
  - `random_delay()` - losowe opoznienia
  - `move_mouse_naturally()` - bezierowe ruchy myszy
  - `scroll_page_naturally()` - scrollowanie ze zmiennym tempem
  - `type_slowly()` - pisanie z losowymi przerwami miedzy klawiszami
- [ ] Implementacja `utils/rate_limiter.py` - token bucket
- [ ] Implementacja `utils/delays.py` - `human_delay`, `between_doctors_delay`, `post_login_delay`
- [ ] Test: otworz strone i sprawdz czy `navigator.webdriver === false`

**Weryfikacja:** Playwright odpala Chromium, odwiedza znany lekarz.pl bez wykrycia bota (brak Captcha przy pierwszej wizycie).

---

### Faza 3: Logowanie i zarzadzanie sesja

**Cel:** Aplikacja potrafi sie zalogowac i przechowywac sesje miedzy uruchomieniami.

- [ ] Implementacja `scraper/login.py`:
  - Nawigacja do strony logowania
  - Wypelnienie formularza (`type_slowly`)
  - Klikniecie z `random_pause_before_click`
  - Weryfikacja poprawnosci logowania (sprawdzenie elementu po zalogowaniu)
  - Obsluga bledu logowania
- [ ] Implementacja `browser/manager.py` - metody `save_session` / `load_session` (storage state Playwright)
- [ ] Implementacja `monitor/session.py` - logika: sprobuj zaladowac sesje -> sprawdz waznosc -> jesli wygasla, zaloguj ponownie
- [ ] Komenda `--setup`: pierwsze uruchomienie headful (z oknem), zapis sesji do `data/cookies/session.json`

**Weryfikacja:** Po `--setup` kolejne uruchomienie nie pyta o haslo, sesja jest wazna.

---

### Faza 4: Scraping terminow

**Cel:** Aplikacja pobiera liste dostepnych terminow dla wskazanego lekarza.

- [ ] Analiza struktury HTML strony lekarza na znany lekarz.pl (selektory CSS/XPath kalendarza i terminow) - **UWAGA: wymaga recznej analizy przed implementacja**
- [ ] Implementacja `scraper/slots_parser.py` - parsowanie elementow kalendarza -> lista `AppointmentSlot`
- [ ] Implementacja `scraper/doctor_page.py`:
  - `_navigate_to_doctor()` - nawigacja z ludzkimi opoznieniami
  - `_wait_for_calendar()` - czekanie az kalendarz sie zaladuje (Playwright `wait_for_selector`)
  - `_extract_slots_from_calendar()` - wywolanie parsera
  - `_handle_pagination()` - przejscie do nastepnego tygodnia/miesiaca jesli potrzeba
  - `get_available_slots()` - glowna metoda publiczna
- [ ] Testy jednostkowe parsera na zapisanych przykladach HTML

**Weryfikacja:** Dla konkretnego URL lekarza aplikacja zwraca liste terminow zgodna z tym co widac w przegladarce.

---

### Faza 5: Monitorowanie i diff stanu

**Cel:** Aplikacja wykrywa nowe terminy porownujac aktualny stan z poprzednim.

- [ ] Implementacja `monitor/state_manager.py`:
  - `load_known_slots()` - wczytuje `data/state/known_slots.json`
  - `save_known_slots()` - zapisuje do pliku
  - `find_new_slots()` - roznica miedzy aktualnym stanem a zapisanym
  - Unikalny klucz slotu: `f"{doctor_url}_{slot_datetime.isoformat()}"`
- [ ] Logika pierwszego uruchomienia: przy braku pliku stanu - zapis bez powiadomien (nie bombarduj uzytkownika przy starcie)
- [ ] Testy jednostkowe diff-u

**Weryfikacja:** Przy dwukrotnym uruchomieniu z tymi samymi terminami nie wysyla powiadomien. Przy nowym terminie wykrywa go poprawnie.

---

### Faza 6: Powiadomienia

**Cel:** Uzytkownik dostaje powiadomienie gdy pojawi sie nowy termin.

- [ ] Implementacja `notifier/formatter.py` - formatowanie wiadomosci (lista terminow z data, godziną, lekarzem, miejscem)
- [ ] Implementacja `notifier/apprise_notifier.py` - integracja z Apprise, cooldown miedzy powiadomieniami o tym samym terminie
- [ ] Komenda `--test-notify`: wyslij testowe powiadomienie do wszystkich skonfigurowanych kanalow
- [ ] Obsluga cooldownu: nie wysylaj powiadomienia o tym samym terminie czesciej niz `cooldown_minutes`

**Weryfikacja:** `--test-notify` dostarcza wiadomosc na Telegram/email/itp. Powiadomienie o nowym terminie trafia w ciagu 1 minuty od wykrycia.

---

### Faza 7: Harmonogram i orchestracja

**Cel:** Aplikacja dziala autonomicznie 24/7 zgodnie z harmonogramem.

- [ ] Implementacja `monitor/scheduler.py` z APScheduler:
  - Zadania dla kazdego lekarza z roznym offsetem startowym (rozlozone rownomiernie)
  - Jitter (+/- `jitter_percent`%) dla kazdego nastepnego sprawdzenia
  - Respektowanie `active_hours` i `active_days` - brak sprawdzen w nocy
  - `between_doctors_delay` miedzy kolejnymi lekarzami w tej samej turze
- [ ] Pelna orchestracja w `main.py` (`run`): start przegladarki -> sesja -> scheduler -> petla
- [ ] Graceful shutdown (SIGTERM/SIGINT): zapis stanu, zamkniecie przegladarki
- [ ] Obsluga bledow w petli schedulera (retry z backoff, pomijanie przy bloku, alert przy captchy)

**Weryfikacja:** Aplikacja dziala przez 24h bez restartu, sprawdza lekarzy zgodnie z harmonogramem, nie dziala w nocy.

---

### Faza 8: Deployment i testy E2E

**Cel:** Aplikacja dziala stabilnie jako serwis systemowy.

- [ ] Konfiguracja `systemd` service unit
- [ ] Testy E2E: pelny przeplyw od startu do powiadomienia w srodowisku zbliozonym do produkcji
- [ ] Weryfikacja logow po 48h dzialania
- [ ] Dokumentacja `README.md`: instalacja, konfiguracja, pierwsze uruchomienie

**Weryfikacja:** `systemctl status znany-lekarz-monitor` - active (running). Powiadomienia przychodza, konto nie zostalo zablokowane.

---

## 6. Deployment

### systemd (rekomendowane)

```ini
# /etc/systemd/system/znany-lekarz-monitor.service
[Unit]
Description=Znany Lekarz Monitor
After=network.target

[Service]
Type=simple
User=kamil
WorkingDirectory=/home/kamil/repos/znany_lekarz_scheduler
ExecStart=/home/kamil/repos/znany_lekarz_scheduler/.venv/bin/python -m znany_lekarz_scheduler.main run
Restart=on-failure
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now znany-lekarz-monitor
journalctl -u znany-lekarz-monitor -f
```

---

## 7. Ryzyka i mitygacje

| Ryzyko | Prawdopodobienstwo | Wplyw | Mitygacja |
|---|---|---|---|
| Blokada IP | Srednie | Wysoki | Niskie czestotliwosci, delays, unikaj VPS datacenter |
| Blokada konta | Niskie (przy zachowaniu zasad) | Krytyczny | Konserwatywne limity, przerwy nocne, symulacja czlowieka |
| Zmiana struktury strony | Srednie | Wysoki | Alert przy bladzie selectora, modularny parser |
| Captcha | Srednie | Sredni | Playwright (trudny do wykrycia), graceful pause 2-4h |
| Naruszenie TOS | Pewne | Prawny | Umiarkowana czestotliwosc, tylko odczyt, cel prywatny |
| Wyciek hasel | Niskie | Krytyczny | Hasla tylko w .env, .gitignore, nie commituj |
| Brak powiadomienia | Niskie | Sredni | Test przed uruchomieniem (`--test-notify`), backup kanal |

---

*Plan przygotowany: 2026-03-13 | Wersja: 2.0 (Playwright)*
