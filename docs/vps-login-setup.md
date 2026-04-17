# Logowanie na VPS bez UI

VPS nie ma interfejsu graficznego, więc `--setup` (headful login) trzeba uruchomić lokalnie i skopiować sesję.

## Krok 1 — zaloguj się lokalnie (na komputerze z UI)

```bash
uv sync && playwright install chromium
python -m znany_lekarz_scheduler.main --setup
```

Przeglądarka otworzy się, zaloguje automatycznie i zapisze ciasteczka do `data/cookies/session.json`.

## Krok 2 — prześlij sesję na VPS

```bash
scp data/cookies/session.json user@vps:/path/to/app/data/cookies/session.json
```

## Krok 3 — uruchom na VPS

```bash
# Docker
docker compose up -d

# lub bez Dockera
python -m znany_lekarz_scheduler.main run
```

Aplikacja wczyta `session.json` przy starcie i pominie logowanie.

## Co gdy sesja wygaśnie?

`SessionManager` automatycznie próbuje ponownie zalogować się headlessly — ale może to nie zadziałać przez FriendlyCaptcha. W takim przypadku powtórz kroki 1–2.

Warto mieć włączone powiadomienia — przy `session_refresh_failed` dostaniesz alert że trzeba ręcznie odnowić sesję.