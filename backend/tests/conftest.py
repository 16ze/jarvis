"""Fixtures pytest partagées pour les tests de la couche vision YOLO."""
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def fake_frame_bgr() -> np.ndarray:
    """Frame BGR 480x640 noire (placeholder)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def fake_frame_bgr_with_pattern() -> np.ndarray:
    """Frame BGR 480x640 avec un carré blanc au centre (debug visuel)."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[200:280, 280:360] = 255
    return frame


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Chemin vers une SQLite temporaire, supprimée à la fin du test."""
    return str(tmp_path / "test_vision.db")


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    """MemoryManager mocké avec une collection vision_objects no-op."""
    mock = MagicMock()
    mock.vision_collection = MagicMock()
    mock.vision_collection.add = MagicMock(return_value=None)
    mock.vision_collection.query = MagicMock(
        return_value={"ids": [[]], "documents": [[]], "metadatas": [[]]}
    )
    return mock


@pytest.fixture
def fixtures_dir() -> Path:
    """Chemin vers le dossier de fixtures images."""
    return Path(__file__).parent / "fixtures"
