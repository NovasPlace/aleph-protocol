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
    grep -v '^ALEPH_ROOT_SEED=' .env 2>/dev/null > .env.tmp || true
    mv .env.tmp .env 2>/dev/null || touch .env
    echo "ALEPH_ROOT_SEED=$ALEPH_ROOT_SEED" >> .env
else
    echo "[*] ROOT_SEED already exists. Preserving config..."
fi

grep -q '^ALEPH_OPERATOR=' .env || echo "ALEPH_OPERATOR=${ALEPH_OPERATOR:-$(whoami)}" >> .env
grep -q '^ALEPH_NODE_URL=' .env || echo "ALEPH_NODE_URL=${ALEPH_NODE_URL:-http://localhost:8801}" >> .env
grep -q '^ALEPH_DATA_DIR=' .env || echo "ALEPH_DATA_DIR=/home/aleph/data" >> .env
grep -q '^DB_PATH=' .env || echo "DB_PATH=/home/aleph/data/aleph.db" >> .env

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
