# PLAN — Accès complet aux fichiers & données d'apps pour Ada

> Spec prête à coder (pour Cursor). Objectif : Ada peut **lire n'importe quel fichier et
> n'importe quelle donnée d'app** sur le Mac de Bryan (accès complet, racine `/` comprise).
> LECTURE seulement — on ne touche PAS aux garde-fous d'écriture/suppression existants.
> Règles projet inchangées : asyncio pur, tout outil retourne une `str`, jamais d'exception
> non catchée, câblage en 3 points.

---

## 0. Pré-requis macOS (étape utilisateur, pas du code)

macOS bloque la lecture des dossiers protégés (Messages, Mail, Photos, Localiser/Find My,
Safari, etc.) tant que le process qui lance Ada n'a pas **Accès complet au disque** :
Réglages Système → Confidentialité et sécurité → **Accès complet au disque** → ajouter
**Terminal** (et l'exécutable Python de l'env `ada_v2` si listé), puis relancer Ada.
Sans ça, Ada lira les fichiers normaux mais pas les apps sensibles.

---

## 1. Nouveau module : `backend/filesystem_access.py`

Module pur, testable, **stdlib uniquement** (os, pathlib, sqlite3, mimetypes, fnmatch).
Accès NON restreint (pas de scope `JARVIS_ROOT`). Chaque fonction retourne une `str`
(texte ou JSON formaté) et **ne lève jamais** (toute erreur → message FR clair en `str`).

Fonctions (toutes avec `os.path.expanduser` + `os.path.realpath` en entrée) :

- `list_dir(path, show_hidden=True, max_entries=500) -> str`
  Liste un dossier : nom, type (dir/file/symlink), taille, date de modif. Tri dossiers puis
  fichiers. Tronque à `max_entries` (indiquer si tronqué).

- `read_file(path, max_bytes=2_000_000) -> str`
  Lit un fichier texte (détection binaire via mimetypes + sniff de bytes nuls). Si binaire →
  renvoyer les métadonnées (type, taille) au lieu des octets. Si > `max_bytes` → renvoyer le
  début + note « tronqué à X / Y octets ». Gérer l'encodage (`errors="replace"`).

- `search_files(query, root="~", mode="name", max_results=100, max_depth=8, timeout_s=20) -> str`
  Recherche récursive. `mode="name"` : match `fnmatch`/sous-chaîne sur le nom. `mode="content"` :
  grep texte (ignorer binaires, borner la taille lue/fichier). Ignorer par défaut les gros
  dossiers système inutiles (`/System`, `/private/var/vm`, `node_modules`, `.git`, caches de
  build) SAUF si `root` pointe explicitement dedans. Respecter `timeout_s` (borne dure) et
  `max_results`. Retour : liste de chemins (+ ligne/extrait en mode content).

- `read_sqlite(path, query=None, max_rows=200) -> str`
  Lire une base SQLite d'app en **lecture seule, non bloquante** :
  `sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)`. IMPORTANT : `immutable=1`
  pour ne jamais verrouiller/modifier une base d'app vivante (Notes, Messages, searchpartyd…).
  Si `query` absent → lister les tables (`SELECT name FROM sqlite_master WHERE type='table'`).
  Sinon exécuter `query` (lecture seule) et renvoyer les lignes (tronquées à `max_rows`).
  Refuser toute requête qui n'est pas un `SELECT`/`PRAGMA` (sécurité d'intégrité, pas un
  garde-fou utilisateur).

Guards = robustesse uniquement (tailles, timeouts, binaire, ro) — PAS des restrictions d'accès.

---

## 2. Déclarations Gemini — `backend/mcp_tools_declarations.py`

Ajouter 4 outils (format `{"name","description","parameters":{"type":"OBJECT",...}}`) :

- `ada_list_dir` : params `path` (string, requis), `show_hidden` (bool, opt).
- `ada_read_file` : params `path` (string, requis).
- `ada_search_files` : params `query` (string, requis), `root` (string, opt), `mode`
  (string enum name|content, opt), `max_results` (int, opt).
- `ada_read_sqlite` : params `path` (string, requis), `query` (string, opt).

Descriptions en FR, explicites (« lit n'importe quel fichier du Mac », etc.).

---

## 3. Câblage (2 agents)

- `backend/ada.py` → `_execute_text_tool()` : ajouter les `elif name == "ada_list_dir"` …
  qui appellent `filesystem_access.*` et retournent la `str`.
- `backend/external_bridge.py` → `TextAgent._execute_tool()` : idem (sinon ignoré en texte).

Rappel : un outil déclaré mais non câblé dans l'un des deux agents est silencieusement ignoré.

---

## 4. Tests — `backend/tests/test_filesystem_access.py`

Avec `tmp_path` (jamais le vrai FS de l'utilisateur) :
- `read_file` : texte OK ; binaire → métadonnées ; > max_bytes → tronqué + note ; absent → msg FR.
- `list_dir` : entrées listées, tri, troncature.
- `search_files` : `mode=name` trouve ; `mode=content` trouve une chaîne ; respecte max_results.
- `read_sqlite` : créer une base temp, lister tables, `SELECT` OK, requête non-SELECT refusée,
  ouverture en `mode=ro&immutable=1` (ne modifie pas le fichier).
Doit passer avec le set CI lean (stdlib) → ajouter le fichier à `backend/tests/`, la CI le prend.

---

## 5. « Où est ma femme » — intégration Localiser / Find My (tâche séparée, + dure)

⚠️ Honnêteté : lire la **position des personnes** de Find My est le point difficile — les
données `searchpartyd` sont binaires/chiffrées et non documentées. Deux approches à tester,
dans l'ordre :

A. **Parser les caches Find My** (à explorer avec les nouveaux outils ci-dessus) :
   - `~/Library/Caches/com.apple.icloud.searchpartyd/` (Devices.data, Items.data, OwnedBeacons…)
   - `~/Library/Caches/com.apple.findmy.fmipcore/` (Cache.data, `Items.data`) — parfois du JSON
     lisible avec les positions des amis/appareils. `ada_read_file` / `ada_read_sqlite` dessus.
   Si un de ces fichiers est du JSON clair contenant `location {latitude, longitude}` → parser
   et exposer un outil `find_person_location(nom)`.

B. **Si A est chiffré/illisible** : piloter l'app **Localiser** via computer-use/accessibilité
   (l'app affiche la position en clair) et lire le texte à l'écran. Plus fragile mais fonctionne.

Livrable visé : un outil `find_person_location(name) -> str` qui renvoie l'adresse/les
coordonnées de la personne partagée (ex. la femme de Bryan, qui partage déjà via « Localiser »).
Commencer par A (tester quels fichiers sont lisibles), basculer sur B sinon.

---

## 6. Ce qu'on NE touche PAS

- Les confirmations avant actions irréversibles (mail/suppression) et le hard-block
  catastrophe (`safe_exec`) **restent** — Bryan a confirmé qu'il ne veut PAS les enlever.
- Les outils `jarvis_*` existants (scopés `JARVIS_ROOT`, backup git avant write) restent intacts.
  Les nouveaux `ada_*` sont en LECTURE seule et séparés.

---

## 7. Checklist Cursor

1. `git pull` sur `integration/widget-pc-control`.
2. Créer `backend/filesystem_access.py` (+ tests).
3. Déclarer les 4 outils dans `mcp_tools_declarations.py`.
4. Câbler dans `ada.py` ET `external_bridge.py`.
5. `python -m pytest backend/tests -q` (doit rester vert) + `npm run build`/`test`/`smoke` si frontend touché (ici non).
6. Dire à Bryan d'activer l'**Accès complet au disque** (Terminal + Python) puis relancer Ada.
7. Attaquer la tâche §5 (Localiser) en dernier, approche A puis B.
