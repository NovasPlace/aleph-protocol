#!/usr/bin/env bash
set -e

echo "==========================================================="
echo "   Nodeus V1 — Autonomous Memory Engine   "
echo "==========================================================="

if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install docker and docker-compose first."
    exit 1
fi

echo "[*] Creating persistent data directory..."
mkdir -p ./data

if [ -f .env ]; then
    echo "[*] Existing .env found. Sourcing values..."
    source .env
fi

if [ -z "$ALEPH_ROOT_SEED" ] || [ "$ALEPH_ROOT_SEED" = "default_seed_replace_me" ]; then
    echo "[*] Generating cryptographically secure ROOT_SEED..."
    export ALEPH_ROOT_SEED=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9_=')
    echo "ALEPH_ROOT_SEED=$ALEPH_ROOT_SEED" > .env
    echo "DB_PATH=/home/aleph/data/aleph.db" >> .env
else
    echo "[*] ROOT_SEED already exists. Preserving config..."
fi

echo "[*] Building and starting Nodeus Docker container..."
docker-compose up --build -d

echo ""
echo "==========================================================="
echo "✅ Nodeus Engine Deployed Successfully!"
echo "==========================================================="
echo "Network Context:"
echo " → Peer discovery logic is running silently in the background."
echo " → The node is bound strictly to: 127.0.0.1:8801"
echo " → You MUST configure a reverse proxy (Nginx/Caddy) with HTTPS to expose it."
echo ""
echo "Your Nodeus Administrative Root Seed is:"
echo "👉 $ALEPH_ROOT_SEED"
echo ""
echo "WARNING: Backup this seed. Loss of this string means total loss of local agent key derivation access."
echo "==========================================================="
