"""Wrapper stateless YOLO (ultralytics + ByteTrack) pour la couche vision objet.

Renvoie une liste de `Detection` normalisées (bbox [0,1], translation FR).
Ne maintient aucun état entre frames — c'est le rôle du `_DetectionDeduplicator`.
ByteTrack est utilisé via `model.track()` pour des track_id stables inter-frames.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

from vision_translations import translate_class

_LOG = logging.getLogger("vision_object")


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str          # nom EN OIV7 brut
    class_fr: str            # traduit FR (ou lowercase EN si absent du mapping)
    confidence: float        # 0.0 - 1.0
    bbox: tuple[float, float, float, float]   # (x_center, y_center, w, h) normalisés
    track_id: int | None     # ID stable ByteTrack (None si non-tracké)


class YoloDetector:
    """Wrapper stateless YOLO. Une instance = un modèle chargé en RAM."""

    def __init__(
        self,
        model_path: str = "yolov8m-oiv7.pt",
        device: str = "mps",
        confidence_min: float = 0.45,
    ) -> None:
        self._device = device
        self._confidence_min = confidence_min
        # Téléchargement automatique du modèle si absent (~52 MB pour yolov8m-oiv7)
        self._model = YOLO(model_path)
        _LOG.info(
            "[VISION_OBJ] Model loaded: %s on device=%s confidence_min=%.2f",
            model_path, device, confidence_min,
        )

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Inférence + tracking ByteTrack sur une frame BGR.

        Renvoie toujours une liste (vide si erreur ou aucune détection).
        Ne raise jamais — politique fault-tolerance du projet.
        """
        try:
            results = self._model.track(
                source=frame_bgr,
                device=self._device,
                conf=self._confidence_min,
                persist=True,
                verbose=False,
            )
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Inference failed: %s", exc)
            return []

        if not results:
            return []

        result = results[0]
        if result.boxes is None:
            return []

        try:
            cls_ids = result.boxes.cls.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy().astype(float)
            xywhn = result.boxes.xywhn.cpu().numpy().astype(float)
            track_ids: list[int | None]
            if result.boxes.id is not None:
                track_ids = [int(t) for t in result.boxes.id.cpu().numpy()]
            else:
                track_ids = [None] * len(cls_ids)
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Result parsing failed: %s", exc)
            return []

        names: dict[int, str] = result.names or {}
        detections: list[Detection] = []
        for idx, (cls_id, conf) in enumerate(zip(cls_ids, confs)):
            if conf < self._confidence_min:
                continue
            class_name = names.get(int(cls_id), f"class_{cls_id}")
            xc, yc, w, h = xywhn[idx]
            detections.append(Detection(
                class_id=int(cls_id),
                class_name=class_name,
                class_fr=translate_class(class_name),
                confidence=float(conf),
                bbox=(float(xc), float(yc), float(w), float(h)),
                track_id=track_ids[idx],
            ))
        return detections
