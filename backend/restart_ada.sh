#!/bin/bash
# Redémarre Ada après auto-évolution — lancé en arrière-plan (detached)
sleep 3
pkill -f "python server.py" 2>/dev/null || true
sleep 2
cd /Users/bryandev/jarvis/backend
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ada_v2
nohup python server.py >> /tmp/ada_server.log 2>&1 &
echo "[restart_ada] Redémarrage lancé (PID: $!)"
