"""Tests du VisionObjectAgent (orchestration + mode PULL + throttling)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yolo_detector import Detection
from vision_deduplicator import EventType, ObjectEvent
from vision_object_agent import VisionObjectAgent, _classify_risk


def _det(track_id=1, cls_fr="téléphone", conf=0.9, cls_name="Mobile phone"):
    return Detection(
        class_id=0, class_name=cls_name, class_fr=cls_fr,
        confidence=conf, bbox=(0.5, 0.5, 0.1, 0.1), track_id=track_id,
    )


def _evt(event_type=EventType.APPEARED, cls_fr="téléphone", cls_name="Mobile phone"):
    return ObjectEvent(
        event_id="x", event_type=event_type, source="camera", timestamp=1000.0,
        detection=_det(cls_fr=cls_fr, cls_name=cls_name),
        track_id=1,
    )


@pytest.fixture(autouse=True)
def _reset_singleton():
    VisionObjectAgent._singleton = None
    yield
    VisionObjectAgent._singleton = None


def test_singleton_returns_same_instance(mock_memory_manager, temp_db_path):
    with patch("vision_object_agent.YoloDetector"):
        a1 = VisionObjectAgent.get_or_create_singleton(
            memory_manager=mock_memory_manager, db_path=temp_db_path,
        )
        a2 = VisionObjectAgent.get_or_create_singleton(
            memory_manager=mock_memory_manager, db_path=temp_db_path,
        )
    assert a1 is a2


async def test_detect_on_demand_returns_french_summary(mock_memory_manager, temp_db_path, fake_frame_bgr):
    with patch("vision_object_agent.YoloDetector") as MockDetector:
        MockDetector.return_value.detect = MagicMock(return_value=[
            _det(track_id=1, cls_fr="téléphone", conf=0.91),
            _det(track_id=2, cls_fr="chat", cls_name="Cat", conf=0.85),
        ])
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.detect_on_demand(source="camera", filter_class=None, max_results=10)

    assert isinstance(result, str)
    assert "téléphone" in result
    assert "chat" in result


async def test_detect_on_demand_filters_by_class(mock_memory_manager, temp_db_path, fake_frame_bgr):
    with patch("vision_object_agent.YoloDetector") as MockDetector:
        MockDetector.return_value.detect = MagicMock(return_value=[
            _det(track_id=1, cls_fr="téléphone"),
            _det(track_id=2, cls_fr="chat", cls_name="Cat"),
        ])
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.detect_on_demand(source="camera", filter_class="chat", max_results=10)

    assert "chat" in result
    assert "téléphone" not in result


async def test_detect_on_demand_returns_message_when_no_frame(mock_memory_manager, temp_db_path):
    with patch("vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=None)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.detect_on_demand(source="camera", filter_class=None, max_results=10)

    assert isinstance(result, str)
    assert "pas" in result.lower() or "indispon" in result.lower()


async def test_throttling_per_class(mock_memory_manager, temp_db_path):
    """Même classe envoyée 5x rapidement → callback brain appelé 1 seule fois."""
    callback = AsyncMock()

    with patch("vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
            on_object_event=callback,
            brain_throttle_sec=10.0,
        )
        for _ in range(5):
            await agent._propagate_to_brain(_evt(EventType.APPEARED, cls_fr="livre"))

    assert callback.call_count == 1


async def test_high_priority_class_bypasses_throttling(mock_memory_manager, temp_db_path):
    """Person/Cat/Dog/Fire/Knife/Gun → toujours propagé."""
    callback = AsyncMock()

    with patch("vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
            on_object_event=callback,
            brain_throttle_sec=10.0,
        )
        for _ in range(3):
            await agent._propagate_to_brain(_evt(EventType.APPEARED, cls_fr="chat", cls_name="Cat"))

    assert callback.call_count == 3


def test_classify_risk_fire_is_high():
    assert _classify_risk(_evt(cls_fr="feu", cls_name="Fire")) == "high"


def test_classify_risk_phone_is_none():
    assert _classify_risk(_evt(cls_fr="téléphone", cls_name="Mobile phone")) == "none"


async def test_query_history_returns_string(mock_memory_manager, temp_db_path):
    with patch("vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.query_history(object_query="téléphone", since=None, max_results=5)
    assert isinstance(result, str)


async def test_count_seen_returns_string(mock_memory_manager, temp_db_path):
    with patch("vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.count_seen(object_class="chat", period="today")
    assert isinstance(result, str)


async def test_camera_loop_calls_detector_when_frame_available(mock_memory_manager, temp_db_path, fake_frame_bgr):
    """Boucle camera : au moins 1 inférence si la frame est disponible."""
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])

    with patch("vision_object_agent.YoloDetector", return_value=detector):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        await agent.start_camera_loop(fps=20)
        await asyncio.sleep(0.2)
        await agent.stop()

    assert detector.detect.call_count >= 1


async def test_camera_loop_skips_when_frame_is_none(mock_memory_manager, temp_db_path):
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])

    with patch("vision_object_agent.YoloDetector", return_value=detector):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=None)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        await agent.start_camera_loop(fps=20)
        await asyncio.sleep(0.15)
        await agent.stop()

    assert detector.detect.call_count == 0


async def test_camera_loop_does_not_double_start(mock_memory_manager, temp_db_path, fake_frame_bgr):
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])

    with patch("vision_object_agent.YoloDetector", return_value=detector):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        await agent.start_camera_loop(fps=10)
        first_task = agent._camera_task
        await agent.start_camera_loop(fps=10)
        assert agent._camera_task is first_task
        await agent.stop()


async def test_cleanup_loop_triggers_storage_cleanup(mock_memory_manager, temp_db_path):
    with patch("vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        agent._storage = MagicMock()
        agent._storage.cleanup_older_than = MagicMock(return_value=42)

        # Force le déclenchement immédiat (sans attendre 4h du matin)
        await agent.start_cleanup_loop(interval_sec=0.05, retention_days=30)
        await asyncio.sleep(0.15)
        await agent.stop()

    assert agent._storage.cleanup_older_than.call_count >= 1
