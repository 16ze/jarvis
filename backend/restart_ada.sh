#!/bin/bash
# Redémarre Ada après auto-évolution — lancé en arrière-plan (detached)
sleep 3
pkill -f "python server.py" 2>/dev/null || true
pkill -f "uvicorn server" 2>/dev/null || true
sleep 2
# Chemin relatif au script — le projet vit sur le disque externe,
# l'ancien chemin en dur /Users/bryandev/jarvis/backend est vide.
cd "$(cd "$(dirname "$0")" && pwd)"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ada_v2
nohup python server.py >> /tmp/ada_server.log 2>&1 &
echo "[restart_ada] Redémarrage lancé (PID: $!)"
