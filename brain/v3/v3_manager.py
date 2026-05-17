"""Façade défensive du brain v3."""
from __future__ import annotations

import threading
import time

from brain.calibration import env_bool, env_float
from brain.v3 import adapters, neuromodulation
from brain.v3.attention import AttentionField
from brain.v3.habituation import HabituationTracker
from brain.v3.policy import AttentionBudget, ReactionPolicy
from brain.v3.traces import ShortTermMemory
from brain.v3.types import ReactionDecision


class V3Manager:
    """Point d'entrée défensif pour piloter attention, politique et traces v3."""

    def __init__(self, limbic_ref) -> None:
        self._limbic = limbic_ref
        self._attention = AttentionField()
        self._habituation = HabituationTracker(
            halflife_sec=env_float("BRAIN_V3_HABITUATION_HALFLIFE", 120.0),
            max_keys=int(env_float("BRAIN_V3_HABITUATION_MAX_KEYS", 256.0)),
        )
        self._budget = AttentionBudget(
            initial=env_float("BRAIN_V3_ATTENTION_BUDGET_INIT", 1.0),
            max_budget=env_float("BRAIN_V3_ATTENTION_BUDGET_MAX", 1.5),
        )
        self._policy = ReactionPolicy()
        self._traces = ShortTermMemory(window_sec=60.0)
        self._tick_budget_ms = env_float("BRAIN_V3_TICK_BUDGET_MS", 3.0)
        self._degraded_until = 0.0
        self._stop_event = threading.Event()
        self._refill_thread: threading.Thread | None = None
        self._start_refill_loop()

    @property
    def enabled(self) -> bool:
        return env_bool("BRAIN_V3_ENABLED", False) and not self._is_degraded()

    @property
    def shadow_mode(self) -> bool:
        return env_bool("BRAIN_V3_SHADOW_MODE", True)

    def process(self, payload: dict, channel: str) -> ReactionDecision | None:
        try:
            start = time.perf_counter()
            stimulus = adapters.from_payload(payload, channel)
            modulation = neuromodulation.derive(self._limbic.get_snapshot())
            spike = self._attention.tick(stimulus, modulation, self._habituation)
            familiarity = self._habituation.familiarity(stimulus.canonical_id)
            decision = self._policy.decide(
                stimulus,
                spike=spike,
                familiarity=familiarity,
                modulation=modulation,
                budget=self._budget,
                threshold=self._policy.threshold,
            )
            self._traces.append(stimulus, decision)
            self._habituation.imprint(stimulus.canonical_id)
            if decision.action == "REACT":
                self._budget.consume(decision.cost)

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if elapsed_ms > self._tick_budget_ms:
                self._degraded_until = time.monotonic() + 5.0
                print(f"V3Manager degraded: slow tick {elapsed_ms:.2f}ms")
            return decision
        except Exception as exc:
            self._degraded_until = time.monotonic() + 30.0
            print(f"V3Manager degraded: process error {exc}")
            return None

    def observe(self, payload: dict, channel: str) -> None:
        try:
            stimulus = adapters.from_payload(payload, channel)
            modulation = neuromodulation.derive(self._limbic.get_snapshot())
            self._attention.tick(stimulus, modulation, self._habituation)
            self._habituation.imprint(stimulus.canonical_id)
            self._traces.append(
                stimulus,
                ReactionDecision("OBSERVE", 0.0, "passive_observe", 0.0, None),
            )
        except Exception as exc:
            print(f"V3Manager observe error: {exc}")

    def get_debug_state(self) -> dict:
        return {
            "enabled": self.enabled,
            "shadow_mode": self.shadow_mode,
            "degraded": self._is_degraded(),
            "budget": self._budget.level,
            "habituation_size": self._habituation.size(),
            "attention_state": self._attention.get_state(),
            "recent_decisions": self._traces.recent(n=10),
        }

    def stop(self) -> None:
        self._stop_event.set()
        if self._refill_thread is not None and self._refill_thread.is_alive():
            self._refill_thread.join(timeout=1.0)

    def _is_degraded(self) -> bool:
        return time.monotonic() < self._degraded_until

    def _start_refill_loop(self) -> None:
        def _loop() -> None:
            while not self._stop_event.wait(5.0):
                try:
                    modulation = neuromodulation.derive(self._limbic.get_snapshot())
                    self._budget.refill(modulation.budget_refill * 5.0)
                except Exception:
                    pass

        self._refill_thread = threading.Thread(
            target=_loop,
            name="V3BudgetRefill",
            daemon=True,
        )
        self._refill_thread.start()
