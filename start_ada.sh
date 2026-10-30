#!/bin/bash
# ─── Ada Launcher ─────────────────────────────────────────────────────────────
# Lance le backend Python + le frontend Vite en séquence.
# Le frontend attend que le backend soit prêt avant de démarrer.

JARVIS_ROOT="$(cd "$(dirname "$0")" && pwd)"
CONDA_ENV="ada_v2"
BACKEND_PORT=8000
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}/status"
MAX_WAIT=60  # secondes max avant abandon
ADA_BRAIN_ENV="export BRAIN_ENABLED=true BRAIN_MODULATE_ALL=true BRAIN_OBSERVE_ONLY=false BRAIN_V3_ENABLED=true BRAIN_V3_SHADOW_MODE=false BRAIN_V3_REACTION_THRESHOLD=0.35 BRAIN_V3_PROB_GATE_SLOPE=3.5 BRAIN_V3_COST_OBJECT_NORMAL=0.10 BRAIN_V3_COST_SCENE_NORMAL=0.15 BRAIN_V3_ATTENTION_BUDGET_INIT=1.4 BRAIN_V3_ATTENTION_BUDGET_MAX=2.0 BRAIN_V3_REFRACTORY_VISION_OBJECT=0.8 BRAIN_V3_REFRACTORY_VISION_SCENE=3.0 BRAIN_V3_REFRACTORY_TEXT=0.15 VISION_OBJECT_ENABLED=true"

# ── 0. Nettoyage : garantir qu'aucun backend ne tient déjà le port 8000 ───────
# Idempotent : relançable sans laisser de zombie ni déclencher
# « [Errno 48] address already in use ». `xargs -r`/garde explicite si vide.
EXISTING_PIDS=$(lsof -ti:"$BACKEND_PORT" 2>/dev/null)
if [ -n "$EXISTING_PIDS" ]; then
    echo "♻️  Port $BACKEND_PORT déjà occupé (PID : $(echo "$EXISTING_PIDS" | tr '\n' ' '))— arrêt du backend précédent…"
    echo "$EXISTING_PIDS" | xargs kill -9 2>/dev/null
    # Attendre la libération effective du port avant de relancer.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        lsof -ti:"$BACKEND_PORT" >/dev/null 2>&1 || break
        sleep 0.5
    done
    echo "✅ Port $BACKEND_PORT libéré."
fi

# ── 1. Backend ────────────────────────────────────────────────────────────────
echo "🚀 Démarrage du backend Ada..."

# Ouvrir un nouvel onglet Terminal pour le backend
osascript <<EOF
tell application "Terminal"
    activate
    do script "$ADA_BRAIN_ENV && conda activate $CONDA_ENV && cd \"$JARVIS_ROOT/backend\" && python server.py"
end tell
EOF

# ── 2. Attendre que le backend réponde ────────────────────────────────────────
echo "⏳ Attente du backend..."
ELAPSED=0
until curl -s "$BACKEND_URL" > /dev/null 2>&1; do
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo "❌ Timeout : le backend n'a pas démarré en ${MAX_WAIT}s."
        exit 1
    fi
done
echo "✅ Backend prêt (${ELAPSED}s)"

# ── 3. Frontend ───────────────────────────────────────────────────────────────
echo "🌐 Démarrage du frontend..."
osascript <<EOF
tell application "Terminal"
    activate
    do script "export ADA_BACKEND_EXTERNAL=1 && cd \"$JARVIS_ROOT\" && npm run dev"
end tell
EOF

echo "✅ Ada est lancée."
