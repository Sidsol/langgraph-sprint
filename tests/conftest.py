from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from agent import build_graph


@pytest.fixture
def offline_graph(tmp_path: Path):
    db_path = tmp_path / ".checkpoints" / "agent.sqlite"
    graph = build_graph(mode="offline", db_path=str(db_path))
    return graph, db_path


@pytest.fixture
def temp_outbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outbox_root = tmp_path / "outbox"
    publisher_module = importlib.import_module("publisher.publisher")
    monkeypatch.setattr(publisher_module, "OUTBOX_ROOT", outbox_root)
    return outbox_root
