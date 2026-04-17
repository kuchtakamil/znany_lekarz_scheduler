#!/usr/bin/env bash
# VPS first-time setup script for znany_lekarz_scheduler
# Run as kamilk (with sudo access) from the project root:
#   bash scripts/vps-setup.sh

set -euo pipefail

APP_USER="kamilk"
DOCKER_UID=1000
DOCKER_GID=1000
DOCKER_GROUP="debian"   # group with GID 1000 on this VPS

echo "==> Creating data directories..."
mkdir -p data/cookies data/state data/logs

echo "==> Setting ownership to docker app user (UID $DOCKER_UID)..."
sudo chown -R "$DOCKER_UID:$DOCKER_GID" data/

echo "==> Setting group-write permissions on data/..."
sudo chmod -R 775 data/

echo "==> Adding $APP_USER to group $DOCKER_GROUP..."
sudo usermod -aG "$DOCKER_GROUP" "$APP_USER"

echo ""
echo "==> Done. IMPORTANT: log out and back in (or run 'newgrp $DOCKER_GROUP')"
echo "    for the group change to take effect in your current shell."
echo ""
echo "==> Next steps:"
echo "    1. Copy session: scp data/cookies/session.json $APP_USER@<vps>:/path/data/cookies/"
echo "    2. Copy config:  scp config.toml .env $APP_USER@<vps>:/path/"
echo "    3. Start:        docker compose up -d scheduler"
