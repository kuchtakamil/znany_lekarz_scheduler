FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Install Playwright system dependencies and Chromium browser
RUN uv run playwright install-deps chromium \
 && uv run playwright install chromium

# Copy application source
COPY src/ src/

# Create runtime data directories and non-root user
RUN useradd -m -u 1000 app \
 && mkdir -p data/cookies data/state data/logs \
 && chown -R app:app /app

USER app

CMD ["uv", "run", "python", "-m", "znany_lekarz_scheduler.main", "run"]