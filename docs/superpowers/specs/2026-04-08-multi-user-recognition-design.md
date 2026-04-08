# Design — Reconnaissance multi-utilisateurs Ada
Date : 2026-04-08

## Objectif

Ada identifie qui lui parle (voix) et qui elle voit (visage/caméra), charge les préférences
de la personne identifiée, et adapte ses réponses en conséquence. Deux utilisateurs principaux :
Bryan et Rose. Les invités sont reconnus comme inconnus, Ada leur demande leur prénom et crée
un profil persistant.

---

## Utilisateurs

| Rôle | Nom | Profil |
|---|---|---|
| Owner | Bryan | Profil complet, préférences persistantes |
| Owner | Rose | Profil complet, préférences persistantes |
| Guest | Prénom demandé par Ada | Profil persistant créé à la première visite |

---

## Architecture générale

### Nouveaux fichiers

```
backend/
  voice_recognizer.py         ← Enrollment + identification voix (resemblyzer)
  presence_manager.py         ← Fusionne voix + visage → active_speakers[]
  user_profile_manager.py     ← CRUD profils Bryan / Rose / invités
  enroll.py                   ← Script one-shot d'enrollment vocal + photo

backend/memory/users/
  bryan.json                  ← Profil + préférences Bryan
  rose.json                   ← Profil + préférences Rose
  guests/
    {prenom}.json             ← Profils invités persistants

backend/memory/voice_prints/
  bryan.npy                   ← Empreinte vocale Bryan (resemblyzer, 256 dims)
  rose.npy                    ← Empreinte vocale Rose
  guests/
    {prenom}.npy              ← Empreintes vocales invités

backend/memory/face_refs/
  bryan.jpg                   ← Photo référence Bryan
  rose.jpg                    ← Photo référence Rose
```

### Fichiers modifiés

```
authenticator.py              ← Multi-utilisateurs + retourne qui est vu + label caméra
ada.py                        ← Injecte contexte utilisateur actif dans le system prompt
external_bridge.py            ← Même injection pour Telegram/WhatsApp
mcp_tools_declarations.py     ← Nouveaux outils : remember_for_user, enroll_voice, who_is_speaking
settings.json                 ← Ajout config caméras avec labels de pièce
```

---

## Flux de données

### Identification temps réel

```
Audio stream (micro)
       │
       ▼
voice_recognizer.py
  → extrait embedding audio toutes les 2s (resemblyzer)
  → compare avec bryan.npy, rose.npy, guests/*.npy (cosine similarity)
  → retourne: [{"user": "bryan", "confidence": 0.92}]
       │
       ▼
presence_manager.py  ←──── authenticator.py (caméra)
  → fusionne voix + visage       └─ {"user": "rose", "location": "bureau"}
  → active_speakers = [
      {"user": "bryan", "source": "voice", "confidence": 0.92},
      {"user": "rose",  "source": "face",  "location": "bureau"}
    ]
       │
       ▼
ada.py → _build_user_context(active_speakers)
  → charge bryan.json + rose.json
  → construit bloc [UTILISATEURS ACTIFS] injecté dans system prompt Gemini
```

### Bloc injecté dans le system prompt Gemini

```
[UTILISATEURS ACTIFS]
- Bryan (voix, confiance 92%) — préférences : ...
- Rose (caméra bureau) — préférences : ...
→ Si les deux parlent en même temps : réponds à chacun explicitement.
```

### Invité détecté

```
Voix inconnue (confiance < 0.6 sur tous les profils connus)
       │
       ▼
Ada : "Je ne reconnais pas ta voix, comment tu t'appelles ?"
       │
       ▼
Prénom capturé → user_profile_manager.create_guest(prenom)
  → crée memory/users/guests/{prenom}.json
  → enregistre empreinte vocale dans memory/voice_prints/guests/{prenom}.npy
  → profil actif immédiatement + persistant pour les prochaines visites
```

---

## Structure des profils

### Profil owner (`memory/users/bryan.json`)

```json
{
  "id": "bryan",
  "name": "Bryan",
  "role": "owner",
  "preferences": [],
  "habits": [],
  "goals": [],
  "facts": [],
  "created_at": "2026-04-08T00:00:00"
}
```

### Profil invité (`memory/users/guests/marco.json`)

```json
{
  "id": "marco",
  "name": "Marco",
  "role": "guest",
  "preferences": [],
  "habits": [],
  "facts": [],
  "created_at": "2026-04-08T20:00:00",
  "last_seen": "2026-04-08T20:45:00"
}
```

### Migration

`backend/memory/procedural.json` (profil unique Bryan actuel) est migré vers
`backend/memory/users/bryan.json` — aucune donnée perdue.

---

## Configuration caméras (`settings.json`)

```json
{
  "cameras": [
    {"id": 0, "type": "webcam", "label": "bureau"}
  ]
}
```

Extensible : ajouter une caméra = ajouter une entrée avec `label` de pièce.
`authenticator.py` retourne `{"user": "rose", "location": "bureau"}` dès qu'un label est défini,
`null` sinon.

---

## Enrollment initial

```bash
# Voix — parler 20-30 secondes
python backend/enroll.py --user bryan
python backend/enroll.py --user rose

# Visage — capture photo de référence
python backend/capture_face.py --user bryan
python backend/capture_face.py --user rose
```

---

## Nouveaux outils Ada

| Outil | Rôle |
|---|---|
| `remember_for_user` | Sauvegarde une préférence pour l'utilisateur actif identifié |
| `enroll_voice` | Lance l'enrollment vocal depuis une commande orale à Ada |
| `who_is_speaking` | Ada peut demander explicitement si la confiance est trop basse |

---

## Cas limites

| Situation | Comportement |
|---|---|
| Voix inconnue | Ada demande le prénom → crée profil invité persistant |
| Confiance < 60% | Ada reste neutre, n'injecte pas de profil |
| Bryan + Rose en même temps | Ada répond aux deux explicitement : "Bryan... Rose..." |
| Invité revient → voix reconnue | Charge profil existant, accueille par prénom |
| Caméra éteinte | Mode voix uniquement, localisation désactivée |
| Personne détectée | Ada en veille passive |

---

## Ce qui n'est PAS dans le scope

- Détection d'émotion dans la voix
- Diarization (transcription différenciée par locuteur)
- Interface admin pour gérer les profils (tout se fait oralement via Ada)

---

## Dépendance à ajouter

```
resemblyzer
```
