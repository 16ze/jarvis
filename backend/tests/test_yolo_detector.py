"""Tests unitaires YoloDetector (modèle ultralytics mocké)."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from yolo_detector import Detection, YoloDetector


def _make_fake_ultralytics_result(detections: list[tuple]):
    """Construit un faux objet Results compatible avec l'API ultralytics.

    `detections` est une liste de tuples
    (cls_id, conf, x_center, y_center, w, h, track_id).
    Toutes les valeurs bbox sont normalisées [0,1].
    """
    fake_result = MagicMock()
    if not detections:
        fake_result.boxes = None
        fake_result.names = {}
        return [fake_result]

    cls_ids = np.array([d[0] for d in detections])
    confs = np.array([d[1] for d in detections])
    xywhn = np.array([[d[2], d[3], d[4], d[5]] for d in detections])
    has_track = detections[0][6] is not None
    track_ids = np.array([d[6] for d in detections]) if has_track else None

    fake_result.boxes = MagicMock()
    fake_result.boxes.cls = MagicMock(
        cpu=lambda: MagicMock(numpy=lambda: cls_ids)
    )
    fake_result.boxes.conf = MagicMock(
        cpu=lambda: MagicMock(numpy=lambda: confs)
    )
    fake_result.boxes.xywhn = MagicMock(
        cpu=lambda: MagicMock(numpy=lambda: xywhn)
    )
    if track_ids is not None:
        fake_result.boxes.id = MagicMock(
            cpu=lambda: MagicMock(numpy=lambda: track_ids)
        )
    else:
        fake_result.boxes.id = None
    fake_result.names = {0: "Mobile phone", 1: "Cat", 2: "Person"}
    return [fake_result]


def test_detection_dataclass_is_frozen():
    d = Detection(
        class_id=0, class_name="Mobile phone", class_fr="téléphone",
        confidence=0.9, bbox=(0.5, 0.5, 0.1, 0.2), track_id=1,
    )
    with pytest.raises(Exception):
        d.confidence = 0.5  # type: ignore[misc]


@patch("yolo_detector.YOLO")
def test_detector_loads_model_with_configured_device(mock_yolo_cls):
    YoloDetector(model_path="yolov8m-oiv7.pt", device="mps", confidence_min=0.45)
    mock_yolo_cls.assert_called_once_with("yolov8m-oiv7.pt")


@patch("yolo_detector.YOLO")
def test_detect_returns_empty_list_for_no_detections(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(return_value=_make_fake_ultralytics_result([]))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert detections == []


@patch("yolo_detector.YOLO")
def test_detect_returns_detections_with_french_translation(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(return_value=_make_fake_ultralytics_result([
        (0, 0.91, 0.5, 0.5, 0.1, 0.2, 7),
        (1, 0.78, 0.3, 0.4, 0.15, 0.25, 12),
    ]))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert len(detections) == 2
    assert detections[0].class_name == "Mobile phone"
    assert detections[0].class_fr == "téléphone"
    assert detections[0].confidence == pytest.approx(0.91)
    assert detections[0].track_id == 7
    assert detections[1].class_fr == "chat"


@patch("yolo_detector.YOLO")
def test_detect_filters_by_confidence_threshold(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(return_value=_make_fake_ultralytics_result([
        (0, 0.91, 0.5, 0.5, 0.1, 0.2, 7),
        (1, 0.30, 0.3, 0.4, 0.15, 0.25, 12),
    ]))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert len(detections) == 1
    assert detections[0].class_fr == "téléphone"


@patch("yolo_detector.YOLO")
def test_detect_returns_empty_list_on_exception(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(side_effect=RuntimeError("CUDA OOM"))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert detections == []
