# Playwright + Docker: problem z uprawnieniami przy non-root userze

## Problem

Kontener startował w pętli restartu z komunikatem:

```
║ Looks like Playwright was just installed or updated.       ║
║ Please run the following command to download new browsers: ║
║                                                            ║
║     playwright install                                     ║
```

## Przyczyna

Playwright instaluje przeglądarki do katalogu domowego użytkownika, który wywołał `playwright install`. Domyślna ścieżka to `~/.cache/ms-playwright`.

Oryginalna kolejność kroków w Dockerfile:

```dockerfile
# Krok 1 — install jako root
RUN uv run playwright install-deps chromium \
 && uv run playwright install chromium       # instaluje do /root/.cache/ms-playwright

# Krok 2 — dopiero teraz tworzony jest user app
RUN useradd -m -u 1000 app ...

USER app   # od tej chwili kontener działa jako UID 1000
```

Chromium było zainstalowane w `/root/.cache/ms-playwright`, do którego user `app` (UID 1000) nie ma dostępu. Playwright przy każdym uruchomieniu wykrywał brak przeglądarki i żądał ponownej instalacji — której nie mógł wykonać bez uprawnień do zapisu.

## Dlaczego nie można po prostu przenieść całości przed `USER app`?

`playwright install-deps` wywołuje `apt-get` i wymaga uprawnień roota — musi zostać uruchomiony przed przełączeniem na unprivileged usera.

`playwright install` (sama przeglądarka) natomiast powinien być uruchomiony **przez tego samego użytkownika**, który będzie uruchamiał testy/scraper — inaczej ścieżka instalacji jest niedostępna.

## Rozwiązanie

Podzielić dwa kroki instalacji:

```dockerfile
# 1. System dependencies — wymaga roota (apt-get)
RUN uv run playwright install-deps chromium

# 2. Stwórz non-root usera
RUN useradd -m -u 1000 app \
 && mkdir -p data/cookies data/state data/logs \
 && chown -R app:app /app

USER app

# 3. Przeglądarka instalowana jako app — trafia do /home/app/.cache/ms-playwright
RUN uv run playwright install chromium
```

Teraz Chromium jest w `/home/app/.cache/ms-playwright` — dostępnym dla usera `app` zarówno podczas budowania, jak i w runtime.

## Rebuild po zmianie

```bash
docker compose build --no-cache scheduler
docker compose up -d scheduler
```

### Co robi `docker compose build --no-cache scheduler`

- **`docker compose build`** — buduje image dla wskazanego serwisu na podstawie `Dockerfile` i kontekstu z `docker-compose.yml`
- **`scheduler`** — ogranicza build tylko do serwisu `scheduler`; bez tego argumentu Docker budowałby wszystkie serwisy zdefiniowane w `docker-compose.yml`
- **`--no-cache`** — wymusza wykonanie każdego kroku `RUN`/`COPY` od nowa, ignorując wszystkie zapisane warstwy (cache)

#### Dlaczego `--no-cache` jest tu konieczne

Docker cache działa warstwami: jeśli instrukcja i jej kontekst nie zmieniły się od poprzedniego buildu, Docker ponownie używa starej warstwy zamiast ją wykonywać. W tym przypadku warstwy z błędną kolejnością (`playwright install` jako root) były już zapisane w cache. Bez `--no-cache` Docker użyłby ich ponownie — pomimo zmian w Dockerfile — bo hashuje tylko treść instrukcji, nie jej semantykę. `--no-cache` gwarantuje wykonanie nowej, poprawnej kolejności kroków.
