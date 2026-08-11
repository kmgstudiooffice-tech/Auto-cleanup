"""Shared fixtures: point quarantine/config at a temp dir so tests are hermetic."""

from __future__ import annotations

import pytest

from cleanup.core import config as config_mod
from cleanup.core import executor as executor_mod
from cleanup.core import safety as safety_mod


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect quarantine root into ``tmp_path`` for every module that uses it."""

    quarantine = tmp_path / "quarantine"
    monkeypatch.setattr(config_mod, "QUARANTINE_ROOT", quarantine)
    monkeypatch.setattr(safety_mod, "QUARANTINE_ROOT", quarantine)
    monkeypatch.setattr(executor_mod, "QUARANTINE_ROOT", quarantine)
    return tmp_path
