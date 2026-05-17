"""Tests du déduplicateur de détections (IoU + ByteTrack)."""
from yolo_detector import Detection
from vision_deduplicator import (
    DedupConfig,
    EventType,
    _DetectionDeduplicator,
)


def _det(
    track_id: int, cls_fr: str = "téléphone",
    bbox=(0.5, 0.5, 0.1, 0.1), conf: float = 0.9,
) -> Detection:
    return Detection(
        class_id=0, class_name="Mobile phone", class_fr=cls_fr,
        confidence=conf, bbox=bbox, track_id=track_id,
    )


def test_first_frame_produces_appeared_events_for_all_detections():
    dedup = _DetectionDeduplicator(DedupConfig())
    events = dedup.diff([_det(1), _det(2, "chat")], source="camera", timestamp=100.0)
    assert len(events) == 2
    assert all(e.event_type == EventType.APPEARED for e in events)


def test_stable_scene_produces_no_events_on_second_frame():
    dedup = _DetectionDeduplicator(DedupConfig())
    dets = [_det(1)]
    dedup.diff(dets, source="camera", timestamp=100.0)
    events_2 = dedup.diff(dets, source="camera", timestamp=100.1)
    assert events_2 == []


def test_significant_bbox_change_produces_moved_event():
    dedup = _DetectionDeduplicator(DedupConfig(iou_moved_threshold=0.5))
    dedup.diff([_det(1, bbox=(0.5, 0.5, 0.1, 0.1))], source="camera", timestamp=100.0)
    events = dedup.diff([_det(1, bbox=(0.9, 0.9, 0.1, 0.1))], source="camera", timestamp=100.1)
    assert len(events) == 1
    assert events[0].event_type == EventType.MOVED


def test_occlusion_within_grace_period_does_not_trigger_disappeared():
    dedup = _DetectionDeduplicator(DedupConfig(disappear_grace_frames=5))
    dedup.diff([_det(1)], source="camera", timestamp=100.0)
    for i in range(1, 4):
        events = dedup.diff([], source="camera", timestamp=100.0 + i * 0.1)
        assert events == []


def test_object_absent_for_grace_period_triggers_one_disappeared():
    dedup = _DetectionDeduplicator(DedupConfig(disappear_grace_frames=5))
    dedup.diff([_det(1)], source="camera", timestamp=100.0)
    events_final: list = []
    # 5 ticks d'absence → DISAPPEARED émis au 5ème (consecutive_misses == grace)
    for i in range(1, 6):
        events_final = dedup.diff([], source="camera", timestamp=100.0 + i * 0.1)
    assert len(events_final) == 1
    assert events_final[0].event_type == EventType.DISAPPEARED


def test_confidence_jump_produces_updated_event():
    dedup = _DetectionDeduplicator(DedupConfig())
    dedup.diff([_det(1, conf=0.9)], source="camera", timestamp=100.0)
    events = dedup.diff([_det(1, conf=0.5)], source="camera", timestamp=100.1)
    types = [e.event_type for e in events]
    assert EventType.UPDATED in types


def test_max_tracked_objects_eviction_lru():
    cfg = DedupConfig(max_tracked_objects=3)
    dedup = _DetectionDeduplicator(cfg)
    dedup.diff([_det(1), _det(2), _det(3)], source="camera", timestamp=100.0)
    dedup.diff([_det(1), _det(2), _det(3), _det(4)], source="camera", timestamp=100.1)
    assert len(dedup._tracked) <= 3


def test_different_sources_have_independent_tracking():
    dedup = _DetectionDeduplicator(DedupConfig())
    e1 = dedup.diff([_det(1)], source="camera", timestamp=100.0)
    e2 = dedup.diff([_det(1)], source="screen", timestamp=100.1)
    assert len(e1) == 1 and len(e2) == 1
    assert e1[0].event_type == EventType.APPEARED
    assert e2[0].event_type == EventType.APPEARED
