#!/usr/bin/env bash
# Arrêt propre d'Ada — symétrique de start_ada.sh.
#
# start_ada.sh lance le backend et le frontend dans DEUX Terminals distincts :
# un Ctrl+C dans l'un ne touche pas l'autre, et fermer la fenêtre Electron ne
# suffit pas (les helpers audio/GPU survivent et gardent le micro).
# Ce script coupe tout ce qui appartient à CE dossier, et rien d'autre.

set -u

JARVIS_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173

echo "🛑 Arrêt d'Ada…"

# 1. Processus rattachés au dossier du projet (backend, vite, electron, helpers).
#    Le filtre par chemin garantit qu'on ne touche à aucun autre projet.
pkill -f "$JARVIS_ROOT" 2>/dev/null

# 2. Le backend peut tourner via conda sans que le chemin projet apparaisse
#    dans sa ligne de commande : on cible aussi server.py de ce dossier.
pkill -f "python .*${JARVIS_ROOT}/backend/server.py" 2>/dev/null
pkill -f "npm exec electron" 2>/dev/null
# Electron lancé depuis ce projet (argv contient le chemin du projet).
pkill -f "[Ee]lectron .*${JARVIS_ROOT}" 2>/dev/null

sleep 2

# 3. Insistance seulement sur ce qui résiste encore.
if pgrep -f "$JARVIS_ROOT" >/dev/null 2>&1; then
    echo "   … certains processus résistent, arrêt forcé"
    pkill -9 -f "$JARVIS_ROOT" 2>/dev/null
    sleep 1
fi

# 3bis. Filet de sécurité DÉCISIF : tuer ce qui écoute encore sur les ports.
#    Lancé via start_ada.sh (osascript → Terminal → conda → python server.py),
#    le backend n'expose ni le chemin projet ni le chemin complet dans argv :
#    les pkill ci-dessus le ratent. On tue donc par PORT, ce qui ne rate jamais.
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    pids=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "   → port $port occupé, arrêt forcé (PID: $(echo "$pids" | tr '\n' ' '))"
        echo "$pids" | xargs kill -9 2>/dev/null
    fi
done
sleep 1

# 4. Vérification par les ports : c'est le seul contrôle qui compte vraiment.
restants=0
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "   ⚠️  le port $port écoute encore"
        restants=1
    fi
done

if pgrep -f "$JARVIS_ROOT" >/dev/null 2>&1; then
    echo "   ⚠️  processus restants :"
    pgrep -fl "$JARVIS_ROOT" | sed 's/^/      /'
    restants=1
fi

if [ "$restants" -eq 0 ]; then
    echo "✅ Ada est arrêtée (ports $BACKEND_PORT et $FRONTEND_PORT libres, micro relâché)."
else
    echo "❌ Arrêt incomplet — relance ce script ou vérifie les processus ci-dessus."
    exit 1
fi
