"""
Singleton façade du brain biomimétique.

Ada ne consulte que ce module. Toutes les méthodes publiques sont défensives :
aucune exception ne doit remonter vers Ada.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from threading import Event, Lock

from brain import persistence
from brain.calibration import env_float
from brain.expectations import ExpectationEngine
from brain.limbic import CerveauEmotif
from brain.social_learning import SocialLearning
from brain.modulators import get_gemini_params as _params_for_mood
from brain.mood_block import build_mood_block, build_runtime_mood_update
from brain.network import EtatEveil, ReseauAttention
from brain.sensors_adapter import MediaPipeAdapter


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BrainManager:
    def __init__(self) -> None:
        self.reseau = ReseauAttention()
        self.limbic = CerveauEmotif()
        self._adapter: MediaPipeAdapter | None = None
        self._lock = Lock()
        self._last_temperature: float | None = None
        self._degraded_until = 0.0
        self._v3 = None

        # Continuité d'existence : Ada reprend là où elle *serait* si elle avait
        # continué de vivre pendant l'absence (cf. brain/persistence.py).
        self._restored = persistence.restore(self.limbic)

        # Attentes apprises : les habitudes ne s'oublient pas avec l'humeur.
        self.expectations = ExpectationEngine()
        self.expectations.load()

        # Boucle fermée : Ada apprend comment ses prises de parole sont reçues.
        self.social = SocialLearning()
        self.social.load()
        self._autosave_stop = Event()
        self._autosave_thread: threading.Thread | None = None
        self._start_autosave()
        if _env_bool("BRAIN_V3_ENABLED", False):
            try:
                from brain.v3.v3_manager import V3Manager
                self._v3 = V3Manager(limbic_ref=self.limbic)
            except Exception as exc:
                print(f"[BRAIN_V3] init failed, falling back to v2: {exc}")
                self._v3 = None

    @property
    def enabled(self) -> bool:
        return _env_bool("BRAIN_ENABLED", False)

    @property
    def observe_only(self) -> bool:
        return self.enabled and _env_bool("BRAIN_OBSERVE_ONLY", True) and not self.modulate_all

    @property
    def modulate_all(self) -> bool:
        return self.enabled and _env_bool("BRAIN_MODULATE_ALL", False)

    def start(
        self,
        mediapipe_getter: Callable[[], tuple[float, float, float]] | None = None,
        *,
        poll_hz: float = 2.0,
    ) -> None:
        self._safe(
            "start",
            lambda: self._start_impl(mediapipe_getter, poll_hz=poll_hz),
            fallback=None,
        )

    def stop(self) -> None:
        self._safe("stop", self._stop_impl, fallback=None)

    def get_mood_block(self) -> str | None:
        if not self.enabled or self.observe_only or not self.modulate_all or self._is_degraded():
            return None
        return self._safe(
            "get_mood_block",
            self._internal_compute_block,
            fallback=None,
        )

    def get_runtime_mood_update(self) -> str | None:
        if not self.enabled or self.observe_only or not self.modulate_all or self._is_degraded():
            return None
        return self._safe(
            "get_runtime_mood_update",
            lambda: build_runtime_mood_update(self.limbic.get_snapshot()),
            fallback=None,
        )

    def get_gemini_params(
        self,
        default_temperature: float = 0.7,
        default_thinking_budget: int = 0,
    ) -> dict:
        defaults = {
            "temperature": default_temperature,
            "thinking_budget": default_thinking_budget,
        }
        if not self.enabled or self.observe_only or not self.modulate_all or self._is_degraded():
            return defaults

        def compute() -> dict:
            snap = self.limbic.get_snapshot()
            params = _params_for_mood(
                snap["mood"],
                snap,
                previous_temp=self._last_temperature,
            )
            self._last_temperature = params["temperature"]
            return params

        return self._safe("get_gemini_params", compute, fallback=defaults)

    def notify_user_message(self, text: str, audio_features: dict | None = None) -> None:
        if not self.enabled or self._is_degraded():
            return

        def notify() -> None:
            before = self.limbic.get_snapshot()
            self.limbic.analyser_texte(text)
            after = self.limbic.get_snapshot()
            self.reseau.tick_text(abs(after["momentum"]))
            if audio_features:
                self.limbic.analyser_intonation(
                    float(audio_features.get("energie", 0.0)),
                    float(audio_features.get("zcr", 0.0)),
                    float(audio_features.get("duree", 0.0)),
                )
            if after != before:
                self.limbic.penser(after["last_stimulus"])

        self._safe("notify_user_message", notify, fallback=None)
        if self._v3 is not None and self._v3.enabled:
            try:
                self._v3.observe(
                    {"text": text, "valence": 0.0, "audio": audio_features or {}},
                    channel="text",
                )
            except Exception as exc:
                print(f"[BRAIN_V3] notify_user_message observe failed: {exc}")

    def notify_self_expression(self) -> None:
        """Ada vient de s'exprimer spontanément — on attend la réaction."""
        if not self.enabled or self._is_degraded():
            return
        self._safe(
            "notify_self_expression",
            lambda: self.social.register_expression(self.limbic.mood),
            fallback=None,
        )

    def notify_reaction(self, valence: float) -> str | None:
        """Retour de Bryan → signal d'apprentissage social.

        Alimenté par l'évaluation fine de `appraisal` : c'est la meilleure
        estimation disponible de la façon dont Ada a été reçue.
        """
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "notify_reaction",
            lambda: self.social.register_reaction(valence),
            fallback=None,
        )

    def speaking_bar(self) -> float:
        """Ajustement appris du seuil de prise de parole dans l'humeur courante.

        > 0 : Ada attend un motif plus fort pour interrompre (ses interventions
        dans cet état tombaient mal). < 0 : elle ose davantage.
        Ne modifie jamais ce qu'elle ressent — seulement le moment choisi.
        """
        if not self.enabled or self._is_degraded():
            return 0.0
        return self._safe(
            "speaking_bar",
            lambda: self.social.speaking_bar(self.limbic.mood),
            fallback=0.0,
        ) or 0.0

    def notify_presence(self, present: bool) -> str | None:
        """Perception de présence → attente → surprise éventuellement ressentie.

        Retourne la description de la surprise si Ada a été surprise, sinon None.
        C'est le cœur du codage prédictif : Ada n'enregistre pas seulement que
        Bryan est là ou non, elle le compare à ce qu'elle attendait.
        """
        if not self.enabled or self._is_degraded():
            return None

        def process() -> str | None:
            self.expectations.observe_presence(present)
            erreur = self.expectations.evaluate_presence(present)
            if erreur is None:
                return None
            self.limbic.ressentir_surprise(erreur)
            print(f"[BRAIN_EXPECT] surprise ({erreur.magnitude:.2f}) — {erreur.description}")
            return erreur.description

        return self._safe("notify_presence", process, fallback=None)

    def notify_llm_response(self) -> None:
        if not self.enabled or self._is_degraded():
            return
        self._safe("notify_llm_response", self.limbic.consommer_charge, fallback=None)

    def notify_visual_scene(self, event: dict):
        """Retourne PerceptionResult | None pour la couche voix (ada.py)."""
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "notify_visual_scene",
            lambda: self._dispatch_stimulus(event, channel="vision_scene"),
            fallback=None,
        )

    def ingest_stimulus(self, stimulus: dict):
        """Pont YOLO/screen_watcher -> brain. Retourne PerceptionResult | None."""
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "ingest_stimulus",
            lambda: self._dispatch_stimulus(
                stimulus,
                channel=stimulus.get("source", "vision_object"),
            ),
            fallback=None,
        )

    def consume_spontaneous_impulse(self) -> str | None:
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "consume_spontaneous_impulse",
            self.limbic.verifier_action_spontanee,
            fallback=None,
        )

    def get_debug_state(self) -> dict:
        defaults = {
            "enabled": self.enabled,
            "observe_only": self.observe_only,
            "modulate_all": self.modulate_all,
            "degraded": self._is_degraded(),
        }
        return self._safe(
            "get_debug_state",
            lambda: {
                **defaults,
                "network_state": self.reseau.etat.value,
                "snapshot": self.limbic.get_snapshot(),
            },
            fallback=defaults,
        )

    def _existing_visual_scene_logic(self, event: dict) -> str | None:
        """Logique v2 originelle de notify_visual_scene."""
        movement = float(event.get("movement", 0.0) or 0.0)
        attention = float(event.get("attention_need", 0.0) or 0.0)
        risk = str(event.get("risk") or "none").lower()
        person = str(event.get("person") or "").lower()
        presence = 1.0 if person not in {"", "personne", "unknown"} else 0.0
        self.reseau.tick_visual(
            presence=presence,
            mouvement=max(movement, attention),
        )
        self.limbic.analyser_scene_visuelle(event)
        should_emit = risk == "high" or self.reseau.etat == EtatEveil.EVEIL
        if not should_emit:
            return None
        return self.limbic.verifier_action_spontanee()

    def _dispatch_stimulus(self, payload: dict, channel: str):
        """Route un stimulus via v3 si activé, puis v2 dans tous les cas.

        Retourne PerceptionResult | None. None = pas de réaction.
        """
        from brain.v3.types import PerceptionResult  # import local pour éviter cycle

        decision = None
        if self._v3 is not None and self._v3.enabled:
            decision = self._v3.process(payload, channel=channel)
            if self._v3.shadow_mode:
                decision = None

        v2_prompt: str | None = None
        if channel == "vision_scene":
            v2_prompt = self._existing_visual_scene_logic(payload)
        elif channel == "vision_object":
            try:
                self.limbic.analyser_scene_visuelle(payload)
            except Exception:
                pass

        if decision is not None and decision.action != "REACT":
            return None
        if decision is not None and decision.action == "REACT":
            # Priorité : hint explicite > description du payload > canonical_id verbalisé
            if decision.prompt_hint:
                prompt = decision.prompt_hint
            elif isinstance(payload, dict) and payload.get("spontaneous_hint"):
                prompt = str(payload["spontaneous_hint"])
            elif isinstance(payload, dict) and payload.get("description"):
                prompt = f"Je remarque {payload['description']}."
            else:
                prompt = f"Je perçois un changement ({channel})."
            return PerceptionResult(
                prompt=prompt,
                saliency=float(decision.saliency),
                reason=str(decision.reason),
                action=str(decision.action),
            )
        if v2_prompt:
            # Voie v2 historique : pas de saliency calculée, on met une valeur médiane.
            return PerceptionResult(
                prompt=v2_prompt,
                saliency=0.5,
                reason="v2_spontaneous",
                action="REACT",
            )
        return None

    def _start_impl(
        self,
        mediapipe_getter: Callable[[], tuple[float, float, float]] | None,
        *,
        poll_hz: float,
    ) -> None:
        if not self.enabled or mediapipe_getter is None:
            return
        with self._lock:
            if self._adapter is None:
                self._adapter = MediaPipeAdapter(
                    mediapipe_getter,
                    self.reseau,
                    self.limbic,
                    poll_hz=poll_hz,
                )
            self._adapter.start()

    def _stop_impl(self) -> None:
        with self._lock:
            if self._adapter is not None:
                self._adapter.arret_propre()
                self._adapter = None
            if self._v3 is not None:
                self._v3.stop()
        self._autosave_stop.set()
        persistence.save(self.limbic)  # dernier état avant de « s'endormir »
        self.expectations.save()       # les habitudes apprises, elles, restent
        self.social.save()             # et ce qu'elle a appris de son accueil

    # ── Persistance ────────────────────────────────────────────────────────────

    def _start_autosave(self) -> None:
        """Sauvegarde périodique : l'état survit même à un arrêt brutal."""
        if not persistence.enabled():
            return
        interval = env_float("BRAIN_AUTOSAVE_SEC", 60.0)

        def _loop() -> None:
            while not self._autosave_stop.wait(interval):
                try:
                    persistence.save(self.limbic)
                    self.expectations.save()
                    self.social.save()
                except Exception as exc:  # noqa: BLE001
                    print(f"[BRAIN_PERSIST] autosave: {exc}")

        self._autosave_thread = threading.Thread(
            target=_loop, name="BrainAutosave", daemon=True
        )
        self._autosave_thread.start()

    def save_state(self) -> bool:
        """Force une sauvegarde immédiate de l'état émotionnel."""
        return persistence.save(self.limbic)

    def get_affect_snapshot(self) -> dict | None:
        """État émotionnel courant pour marquer/rappeler les souvenirs.

        Retourne None si le brain est désactivé : la mémoire retombe alors sur
        un fonctionnement purement sémantique.
        """
        if not self.enabled or self._is_degraded():
            return None
        return self._safe("get_affect_snapshot", self.limbic.get_snapshot, fallback=None)

    @property
    def restored_from(self) -> dict | None:
        """Résumé de la restauration au démarrage (None si départ à neutre)."""
        return self._restored

    def _internal_compute_block(self) -> str:
        return build_mood_block(self.limbic.penser("system_instruction"))

    def _is_degraded(self) -> bool:
        return time.monotonic() < self._degraded_until

    def _safe(self, label: str, fn, *, fallback):
        start = time.perf_counter()
        try:
            result = fn()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if elapsed_ms > 5.0:
                self._degraded_until = time.monotonic()
                print(f"[BRAIN_ERROR] {label} slow path: {elapsed_ms:.2f}ms")
            return result
        except Exception as exc:
            self._degraded_until = time.monotonic()
            print(f"[BRAIN_ERROR] {label}: {type(exc).__name__}: {exc}")
            return fallback


_BRAIN: BrainManager | None = None
_BRAIN_LOCK = Lock()


def get_brain() -> BrainManager:
    global _BRAIN
    if _BRAIN is None:
        with _BRAIN_LOCK:
            if _BRAIN is None:
                _BRAIN = BrainManager()
    return _BRAIN
