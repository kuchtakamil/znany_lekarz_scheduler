FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ARG UID=1000
ARG GID=1000

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Install Playwright system dependencies (requires root)
RUN uv run playwright install-deps chromium

# Copy application source
COPY src/ src/

# Create non-root user and runtime data directories
RUN groupadd -g $GID app \
 && useradd -m -u $UID -g $GID app \
 && mkdir -p data/cookies data/state data/logs \
 && chown -R app:app /app

USER app

# Install Chromium browser as app user
RUN uv run playwright install chromium

CMD ["uv", "run", "python", "-m", "znany_lekarz_scheduler.main", "run"]