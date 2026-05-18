Récap pour reprendre plus tard

  État actuel :
  - Branche active : feature/yolo-vision-layer
  - 18 commits, 41/41 tests verts, ~2200 lignes
  - main non touché par YOLO (juste le commit WIP b2fbefa d'avant)
  - VISION_OBJECT_ENABLED=false par défaut → Ada démarre exactement comme avant

  Pour tester quand tu veux :
  # Active YOLO en mode PULL seul (pas de boucle continue)
  echo "VISION_OBJECT_ENABLED=true" >> .env
  echo "VISION_OBJECT_CAMERA_LOOP=false" >> .env
  bash start_ada.sh
  # Puis dis à Ada : "Tu vois mon téléphone ?"

  
  Pour revenir sur ce contexte plus tard :
  git checkout feature/yolo-vision-layer
  cat docs/superpowers/specs/2026-05-17-yolo-vision-layer-design.md
  cat docs/superpowers/plans/2026-05-17-yolo-vision-layer-implementation.md

  ★ Insight ─────────────────────────────────────
  - Le pattern "branche dormante" est sûr : tant que tu ne merges pas, main continue de vivre normalement avec ton travail d'avant. Tu peux revenir sur feature/yolo-vision-layer dans 1 jour ou 1 mois, c'est figé tel quel.
  - Si entre-temps tu fais des commits sur main (bugfixes, nouvelles features), tu pourras faire git rebase main sur la branche YOLO pour la remettre à jour avant merge — sans perdre les 18 commits.
  - Pense à désactiver GateGuard pour ta prochaine session (ECC_GATEGUARD=off claude au lancement) si tu trouves que ça ralentit trop. Les facts-forcing étaient utiles pour 1-2 edits, mais sur 18 tâches d'affilée c'était de la
  friction pure.


  1. Lance Ada avec la vision YOLO activée.
  2. Observe pendant 2 à 3 minutes sans rien toucher.
  3. Vérifie qu’Ada décrit des changements visibles, pas juste des banalités répétées.
  4. Montre un nouvel objet ou change quelque chose dans le champ de vision.
  5. Vérifie qu’Ada le remarque une seule fois, puis ne spamme pas.
  6. Active hand tracking et fais un geste simple.
  7. Vérifie que le geste répond encore pendant que la vision tourne.
  8. Active hand OS control.
  9. Refais les gestes et vérifie que souris, clics, drag et fenêtre restent stables.
  10. Laisse tout tourner ensemble 5 à 10 minutes.
  11. Le test est bon si:

  - la vision continue reste fluide
  - YOLO ajoute de la précision
  - le SNN réagit en parallèle
  - les gestes et l’OS control ne cassent pas
  - l’UI ne gèle pas
  - Ada parle seulement quand il y a une vraie nouveauté

  Critère d’échec:

  - spam visuel
  - latence vocale
  - gestes cassés
  - écran figé
  - vision qui coupe
  - réactions incohérentes ou répétées