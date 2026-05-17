"""Déduplicateur IoU pour la couche vision objet.

Reçoit des `Detection` (sortie YOLO + ByteTrack) frame par frame,
maintient un état par (source, track_id), et émet des `ObjectEvent`
quand un objet apparaît / disparaît / se déplace significativement /
voit sa confidence varier fortement.
"""
from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum

from yolo_detector import Detection


class EventType(str, Enum):
    APPEARED = "appeared"
    DISAPPEARED = "disappeared"
    MOVED = "moved"
    UPDATED = "updated"


@dataclass(frozen=True)
class ObjectEvent:
    event_id: str
    event_type: EventType
    source: str
    timestamp: float
    detection: Detection
    track_id: int | None
    location_hint: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class DedupConfig:
    iou_moved_threshold: float = 0.5
    disappear_grace_frames: int = 5
    confidence_update_threshold: float = 0.2
    max_tracked_objects: int = 100


@dataclass
class _TrackedObject:
    detection: Detection
    last_seen_ts: float
    consecutive_misses: int = 0


def _iou(
    b1: tuple[float, float, float, float],
    b2: tuple[float, float, float, float],
) -> float:
    """IoU entre deux bbox au format (x_center, y_center, w, h) normalisées."""
    def _to_corners(b):
        xc, yc, w, h = b
        return (xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2)

    ax1, ay1, ax2, ay2 = _to_corners(b1)
    bx1, by1, bx2, by2 = _to_corners(b2)
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def _make_event(
    event_type: EventType, source: str, timestamp: float, detection: Detection,
) -> ObjectEvent:
    return ObjectEvent(
        event_id=uuid.uuid4().hex[:12],
        event_type=event_type,
        source=source,
        timestamp=timestamp,
        detection=detection,
        track_id=detection.track_id,
    )


class _DetectionDeduplicator:
    """Maintient l'état des objets vus par (source, track_id) et émet des events."""

    def __init__(self, config: DedupConfig | None = None) -> None:
        self._config = config or DedupConfig()
        self._tracked: OrderedDict[tuple[str, int], _TrackedObject] = OrderedDict()

    def diff(
        self,
        detections: list[Detection],
        source: str,
        timestamp: float | None = None,
    ) -> list[ObjectEvent]:
        """Compare le batch courant à l'état précédent, retourne les events."""
        ts = timestamp if timestamp is not None else time.time()
        events: list[ObjectEvent] = []
        seen_keys: set[tuple[str, int]] = set()

        for det in detections:
            if det.track_id is None:
                events.append(_make_event(EventType.APPEARED, source, ts, det))
                continue

            key = (source, det.track_id)
            seen_keys.add(key)

            if key not in self._tracked:
                events.append(_make_event(EventType.APPEARED, source, ts, det))
                self._tracked[key] = _TrackedObject(detection=det, last_seen_ts=ts)
            else:
                tracked = self._tracked[key]
                iou = _iou(tracked.detection.bbox, det.bbox)
                if iou < self._config.iou_moved_threshold:
                    events.append(_make_event(EventType.MOVED, source, ts, det))
                if abs(tracked.detection.confidence - det.confidence) > self._config.confidence_update_threshold:
                    events.append(_make_event(EventType.UPDATED, source, ts, det))
                tracked.detection = det
                tracked.last_seen_ts = ts
                tracked.consecutive_misses = 0
                self._tracked.move_to_end(key)

        keys_to_delete: list[tuple[str, int]] = []
        for key, tracked in self._tracked.items():
            if key[0] != source:
                continue
            if key in seen_keys:
                continue
            tracked.consecutive_misses += 1
            if tracked.consecutive_misses >= self._config.disappear_grace_frames:
                events.append(_make_event(EventType.DISAPPEARED, source, ts, tracked.detection))
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._tracked[key]

        while len(self._tracked) > self._config.max_tracked_objects:
            self._tracked.popitem(last=False)

        return events
