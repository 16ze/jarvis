#!/bin/bash
# ─── Ada Launcher ─────────────────────────────────────────────────────────────
# Lance le backend Python + le frontend Vite en séquence.
# Le frontend attend que le backend soit prêt avant de démarrer.

JARVIS_ROOT="/Users/bryandev/jarvis"
CONDA_ENV="ada_v2"
BACKEND_URL="http://127.0.0.1:8000/status"
MAX_WAIT=60  # secondes max avant abandon

# ── 1. Backend ────────────────────────────────────────────────────────────────
echo "🚀 Démarrage du backend Ada..."

# Ouvrir un nouvel onglet Terminal pour le backend
osascript <<EOF
tell application "Terminal"
    activate
    do script "conda activate $CONDA_ENV && cd $JARVIS_ROOT/backend && python server.py"
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
    do script "cd $JARVIS_ROOT && npm run dev"
end tell
EOF

echo "✅ Ada est lancée."
