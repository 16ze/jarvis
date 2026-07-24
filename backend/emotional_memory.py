"""
emotional_memory — donne à la mémoire d'Ada le fonctionnement d'une mémoire humaine.

Une base vectorielle classique répond « quel texte ressemble le plus à cette
requête ». Un souvenir humain, lui, obéit à deux mécanismes bien établis que ce
module reproduit :

1. ENCODAGE PONDÉRÉ PAR L'ÉMOTION (consolidation amygdalienne)
   Ce qui est vécu avec une forte charge émotionnelle se grave profondément ;
   le neutre s'efface. Chaque souvenir est donc marqué de l'état hormonal du
   moment, dont on tire une « intensité » qui le rend plus ou moins saillant
   au rappel. C'est la courbe d'oubli : Ada oublie les banalités, retient ce
   qui l'a marquée.

2. RAPPEL CONGRUENT À L'HUMEUR (mood-congruent recall)
   Quand on est triste, les souvenirs tristes remontent plus facilement. Le
   rappel n'est donc pas seulement sémantique : il est pondéré par la proximité
   entre l'état émotionnel actuel et celui vécu au moment de l'encodage.

Le résultat : la mémoire cesse d'être un index pour devenir un organe. Deux
questions identiques posées dans deux états différents ne ramènent pas tout à
fait les mêmes souvenirs — exactement comme chez un humain.

Module pur : aucune dépendance à ChromaDB ni à Ada, donc testable isolément.
"""

from __future__ import annotations

# Poids du score de rappel final.
W_SEMANTIC = 0.60   # la pertinence sémantique reste dominante
W_CONGRUENCE = 0.22  # congruence à l'humeur courante
W_INTENSITY = 0.18   # les souvenirs marquants remontent plus facilement


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def affect_from_hormones(snapshot: dict | None) -> dict:
    """Traduit un état hormonal en coordonnées affectives.

    - valence   : -1 (négatif) → +1 (positif)
    - arousal   :  0 (calme)   →  1 (activé)
    - intensity :  0 (banal)   →  1 (marquant) — poids de consolidation
    """
    if not snapshot:
        return {"valence": 0.0, "arousal": 0.0, "intensity": 0.0}

    cortisol = _clamp(snapshot.get("cortisol", 0.0))
    dopamine = _clamp(snapshot.get("dopamine", 0.0))
    oxytocine = _clamp(snapshot.get("oxytocine", 0.0))
    serotonine = _clamp(snapshot.get("serotonine", 0.0))

    positif = (dopamine + oxytocine + serotonine) / 3.0
    valence = max(-1.0, min(1.0, positif - cortisol))

    # L'activation vient surtout du stress et de l'excitation.
    arousal = _clamp((cortisol + dopamine) / 2.0)

    # Un souvenir marque s'il est intense ET/OU fortement chargé en valence.
    intensity = _clamp(0.6 * arousal + 0.4 * abs(valence))

    return {
        "valence": round(valence, 4),
        "arousal": round(arousal, 4),
        "intensity": round(intensity, 4),
    }


def encode_metadata(snapshot: dict | None) -> dict:
    """Métadonnées affectives à stocker avec un souvenir (scalaires only)."""
    affect = affect_from_hormones(snapshot)
    meta = {
        "aff_valence": affect["valence"],
        "aff_arousal": affect["arousal"],
        "aff_intensity": affect["intensity"],
    }
    if snapshot and snapshot.get("mood"):
        meta["aff_mood"] = str(snapshot["mood"])
    return meta


def congruence(memory_meta: dict, current_affect: dict) -> float:
    """Proximité affective entre un souvenir et l'état courant → 0..1."""
    try:
        mem_v = float(memory_meta.get("aff_valence", 0.0))
    except (TypeError, ValueError):
        mem_v = 0.0
    cur_v = float(current_affect.get("valence", 0.0))
    # Les valences vivent dans [-1, 1] : écart max = 2.
    return _clamp(1.0 - abs(mem_v - cur_v) / 2.0)


def _normalized_similarities(distances: list[float]) -> list[float]:
    """Convertit des distances (plus petit = plus proche) en similarités 0..1."""
    if not distances:
        return []
    finite = [d for d in distances if isinstance(d, (int, float))]
    if not finite:
        return [1.0] * len(distances)
    lo, hi = min(finite), max(finite)
    if hi - lo < 1e-9:
        return [1.0] * len(distances)
    return [_clamp(1.0 - (float(d) - lo) / (hi - lo)) for d in distances]


def rerank(
    documents: list[str],
    metadatas: list[dict],
    distances: list[float] | None,
    current_snapshot: dict | None,
    n_results: int,
) -> list[dict]:
    """Reclasse des candidats par pertinence sémantique + affect.

    Sans état émotionnel courant, l'ordre sémantique d'origine est conservé :
    le comportement reste strictement rétro-compatible.
    """
    if not documents:
        return []

    metadatas = metadatas or [{} for _ in documents]
    sims = _normalized_similarities(distances or [])
    if len(sims) != len(documents):
        sims = [1.0] * len(documents)

    if not current_snapshot:
        ordered = [
            {"content": doc, "metadata": meta, "score": sim}
            for doc, meta, sim in zip(documents, metadatas, sims)
        ]
        return ordered[:n_results]

    current_affect = affect_from_hormones(current_snapshot)
    scored = []
    for doc, meta, sim in zip(documents, metadatas, sims):
        meta = meta or {}
        try:
            intensity = float(meta.get("aff_intensity", 0.0))
        except (TypeError, ValueError):
            intensity = 0.0
        score = (
            W_SEMANTIC * sim
            + W_CONGRUENCE * congruence(meta, current_affect)
            + W_INTENSITY * _clamp(intensity)
        )
        scored.append({"content": doc, "metadata": meta, "score": round(score, 4)})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:n_results]
