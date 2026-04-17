# Docker: uprawnienia, grupy i właściciel plików przy non-root kontenerze

## Problem

Gdy kontener działa jako non-root user (np. `app` z UID 1000), a dane są montowane z hosta przez bind mount (`./data:/app/data`), mogą pojawić się konflikty uprawnień — kontener nie może pisać do plików należących do innego UID na hoście.

## Trzy podejścia

### Podejście 1: Dopasuj UID kontenera do hosta (zalecane przy bind mountach)

Zamiast hardkodować UID w Dockerfile, przekaż UID hosta jako build argument:

```bash
docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g) scheduler
```

```dockerfile
ARG UID=1000
ARG GID=1000
RUN useradd -m -u $UID -g $GID app
```

Kontener i host mają tego samego właściciela plików — brak problemów z `chown` i `chmod`.

### Podejście 2: Named volume zamiast bind mount (Docker-native)

Zamiast montować katalog z hosta:
```yaml
volumes:
  - ./data:/app/data          # bind mount — problemy z UID
```

Użyj named volume:
```yaml
volumes:
  - app_data:/app/data        # Docker zarządza właścicielem

volumes:
  app_data:
```

Docker sam ustawia uprawnienia, kontener pisze bez problemów.
Wada: trudniejszy dostęp do plików z hosta — wymaga `docker cp` lub `docker exec`.

### Podejście 3: fixuid (dev tooling)

Narzędzie które przy starcie kontenera dynamicznie zmienia UID procesu na UID właściciela zamontowanego volume. Używane m.in. przez VS Code Dev Containers. Nadmiarowe dla prostych deploymentów produkcyjnych.

## Kiedy które podejście

| Scenariusz | Zalecane |
|---|---|
| Produkcja, dane tylko w kontenerze | Named volume |
| Produkcja, dane dostępne z hosta (scp, edycja) | `--build-arg UID=$(id -u)` |
| Dev environment | `fixuid` lub named volume |

## Ten projekt

Dane muszą być dostępne z hosta — `session.json` jest kopiowany przez `scp`, logi przeglądane bezpośrednio. Dlatego użyte jest podejście 1: `--build-arg UID`.

Dockerfile przyjmuje `UID`/`GID` z domyślną wartością `1000`. Na VPS przy każdym buildzie należy przekazać właściwe wartości:

```bash
docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g) scheduler
```

Lub ustawić je raz w `.env` i odwołać w `docker-compose.yml`:

```yaml
build:
  context: .
  args:
    UID: ${UID:-1000}
    GID: ${GID:-1000}
```
