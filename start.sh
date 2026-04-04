#!/bin/bash
# Starta hela AI-systemet (API + Telegram-bot)
# Krav: .env konfigurerat, pip install -r requirements.txt

set -e

echo "=== Startar AI-routing-system ==="

# Starta API-servern i bakgrunden
echo "[1/2] Startar FastAPI (port 8000)..."
uvicorn api:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 2

# Verifiera att API svarar
curl -sf http://localhost:8000/health > /dev/null && echo "API OK" || { echo "API startade inte!"; kill $API_PID; exit 1; }

# Starta Telegram-boten
echo "[2/2] Startar Telegram-bot..."
python telegram_bot.py

# Städa upp vid avslut
trap "kill $API_PID 2>/dev/null" EXIT
