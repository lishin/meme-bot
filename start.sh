#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PYTHON="/home/lishin/miniforge3/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Python not found at $PYTHON"
    exit 1
fi

echo "Starting 4-Chain Memecoin Bot (Robinhood, BSC, Solana, Arc)..."
exec "$PYTHON" multichain_bot.py
