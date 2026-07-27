#!/usr/bin/env python
"""Réautorise Ada auprès de Google (Gmail + Agenda).

À lancer quand le diagnostic signale « mon accès à Gmail et à l'agenda a
expiré ». Ouvre le navigateur, demande ton accord, puis réécrit
backend/google_token.json.

    conda activate ada_v2 && python reauth_google.py
"""

import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE / "backend"))

TOKEN = RACINE / "backend" / "google_token.json"


def main() -> int:
    if not (RACINE / "backend" / "google_credentials.json").exists():
        print("❌ backend/google_credentials.json manquant.")
        print("   Télécharge-le depuis Google Cloud → API et services → "
              "Identifiants → ID client OAuth (application de bureau).")
        return 1

    # Le jeton révoqué doit disparaître, sinon la bibliothèque retente un
    # rafraîchissement voué à l'échec au lieu de proposer l'autorisation.
    if TOKEN.exists():
        sauvegarde = TOKEN.with_suffix(".json.old")
        TOKEN.replace(sauvegarde)
        print(f"Ancien jeton mis de côté : {sauvegarde.name}")

    print("Ouverture du navigateur pour l'autorisation Google…")
    from google_agent import get_google_services

    try:
        get_google_services()
    except Exception as exc:
        print(f"❌ Autorisation échouée : {exc}")
        return 1

    print(f"✅ Accès Google rétabli — jeton écrit dans {TOKEN}")
    print("   Redémarre Ada pour qu'elle le prenne en compte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
