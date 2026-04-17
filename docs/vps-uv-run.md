# Uruchamianie poleceń na VPS — uv run vs python

## Problem

Wywołanie z katalogu głównego projektu:

```bash
python -m znany_lekarz_scheduler.main --test-notify
```

Skutkuje błędem:

```
ModuleNotFoundError: No module named 'znany_lekarz_scheduler'
```

## Przyczyna

Projekt używa layoutu `src/` — kod źródłowy leży w `src/znany_lekarz_scheduler/`, a nie w katalogu głównym. Systemowy `python` (ani ten z pyenv) nie ma tego katalogu w `sys.path` i nie wie, że paczka w ogóle istnieje.

Dodatkowo zależności projektu są zarządzane przez `uv` i zainstalowane w izolowanym środowisku wirtualnym (`.venv/`). Wywołanie `python` spoza tego środowiska nie widzi ani paczki, ani jej zależności.

## Rozwiązanie

Zawsze używaj `uv run` zamiast bezpośredniego `python`:

```bash
uv run python -m znany_lekarz_scheduler.main --test-notify
uv run python -m znany_lekarz_scheduler.main --setup
uv run python -m znany_lekarz_scheduler.main run
```

`uv run` automatycznie:
- aktywuje środowisko wirtualne `.venv/`
- ustawia poprawny `sys.path` uwzględniający `src/`
- używa interpretera zdefiniowanego w `pyproject.toml`

## Alternatywa: uv sync + aktywacja środowiska

Zamiast poprzedzać każde polecenie `uv run`, można jednorazowo przygotować środowisko i aktywować je w shellu:

```bash
uv sync
source .venv/bin/activate
```

Po aktywacji zwykłe `python` działa poprawnie:

```bash
python -m znany_lekarz_scheduler.main --test-notify
```

### Co robi `uv sync`

1. **Tworzy `.venv/`** — jeśli nie istnieje, zakłada nowe środowisko wirtualne z interpreterem zgodnym z `pyproject.toml`
2. **Instaluje zależności** — czyta `uv.lock` i instaluje dokładnie te wersje paczek, które są tam przypięte (deterministyczny install)
3. **Instaluje sam projekt** — rejestruje `znany_lekarz_scheduler` jako paczkę w trybie editable (`pip install -e`), co sprawia że `src/` trafia do `sys.path`
4. **Usuwa nadmiarowe paczki** — jeśli coś jest w `.venv/` a nie ma w `uv.lock`, zostaje odinstalowane (środowisko jest zsynchronizowane z lock file, stąd nazwa)

Flaga `--no-dev` (używana w Dockerfile) pomija zależności developerskie (pytest itp.) — przydatne w produkcji.

### Kiedy używać której opcji

| Sytuacja | Polecenie |
|----------|-----------|
| Jednorazowe wywołanie | `uv run python -m ...` |
| Sesja interaktywna / wiele poleceń | `uv sync && source .venv/bin/activate` |
| Docker / CI | `uv sync --no-dev --frozen` |
