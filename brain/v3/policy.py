"""Politique de réaction et budget d'attention du brain v3."""
from __future__ import annotations

import random
import threading

from brain.calibration import env_float
from brain.v3.types import ModulationVector, ReactionDecision, Stimulus


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_valence(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


class AttentionBudget:
    """Budget d'attention thread-safe consommé par les réactions spontanées."""

    def __init__(self, initial: float = 1.0, max_budget: float = 1.5) -> None:
        self._max_budget = max(0.0, float(max_budget))
        self._level = max(0.0, min(float(initial), self._max_budget))
        self._lock = threading.Lock()

    @property
    def level(self) -> float:
        with self._lock:
            return round(self._level, 4)

    def can_afford(self, cost: float) -> bool:
        with self._lock:
            return self._level >= max(0.0, float(cost))

    def consume(self, cost: float) -> None:
        with self._lock:
            self._level = max(0.0, self._level - max(0.0, float(cost)))

    def refill(self, amount: float) -> None:
        with self._lock:
            self._level = min(self._max_budget, self._level + max(0.0, float(amount)))


class ReactionPolicy:
    """Décide si un stimulus observé mérite une réaction spontanée."""

    def __init__(self, threshold: float | None = None) -> None:
        self._threshold = (
            float(threshold)
            if threshold is not None
            else env_float("BRAIN_V3_REACTION_THRESHOLD", 0.55)
        )
        self._prob_slope = env_float("BRAIN_V3_PROB_GATE_SLOPE", 2.0)
        self._cost_object = env_float("BRAIN_V3_COST_OBJECT_NORMAL", 0.20)
        self._cost_scene = env_float("BRAIN_V3_COST_SCENE_NORMAL", 0.30)
        self._cost_high_risk = env_float("BRAIN_V3_COST_HIGH_RISK", 0.05)

    @property
    def threshold(self) -> float:
        return self._threshold

    def decide(
        self,
        stimulus: Stimulus,
        spike: bool,
        familiarity: float,
        modulation: ModulationVector,
        budget: AttentionBudget,
        threshold: float | None,
    ) -> ReactionDecision:
        raw = stimulus.raw
        hint = raw.get("spontaneous_hint") if isinstance(raw, dict) else None

        if stimulus.risk == "high":
            cost = self._cost_high_risk
            return ReactionDecision(
                action="REACT",
                saliency=1.0,
                reason=f"risk_high:{stimulus.canonical_id}",
                cost=cost,
                prompt_hint=hint,
            )

        active_threshold = self._threshold if threshold is None else float(threshold)
        saliency = self._saliency(stimulus, familiarity)
        if not spike or saliency < active_threshold:
            return ReactionDecision(
                action="OBSERVE",
                saliency=saliency,
                reason=f"sub_threshold:{stimulus.canonical_id}",
                cost=0.0,
                prompt_hint=None,
            )

        cost = self._cost_for(stimulus)
        if not budget.can_afford(cost):
            return ReactionDecision(
                action="OBSERVE",
                saliency=saliency,
                reason=f"no_budget:{stimulus.canonical_id}",
                cost=0.0,
                prompt_hint=None,
            )

        p = min(0.95, 0.5 + (saliency - active_threshold) * self._prob_slope)
        if random.random() > p:
            return ReactionDecision(
                action="OBSERVE",
                saliency=saliency,
                reason=f"prob_gate_miss:{stimulus.canonical_id}",
                cost=0.0,
                prompt_hint=None,
            )

        return ReactionDecision(
            action="REACT",
            saliency=saliency,
            reason=f"react:{stimulus.canonical_id}",
            cost=cost,
            prompt_hint=hint,
        )

    def _cost_for(self, stimulus: Stimulus) -> float:
        if stimulus.channel == "vision_scene":
            return self._cost_scene
        return self._cost_object

    def _saliency(self, stimulus: Stimulus, familiarity: float) -> float:
        novelty = 1.0 - _clamp01(familiarity)
        return (
            0.45 * _clamp01(stimulus.intensity)
            + 0.35 * novelty
            + 0.15 * _clamp01(stimulus.attention_need)
            + 0.05 * abs(_clamp_valence(stimulus.valence))
        )
