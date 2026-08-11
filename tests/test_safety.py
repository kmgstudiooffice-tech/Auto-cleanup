"""Tests for the safety layer: protected paths must never be proposed."""

from __future__ import annotations

from pathlib import Path

from cleanup.core.config import Config
from cleanup.core.models import RiskLevel
from cleanup.core.safety import classify_risk, is_protected


def test_extra_protected_path(tmp_path):
    protected = tmp_path / "keep"
    protected.mkdir()
    (protected / "important.bin").write_bytes(b"x")
    config = Config(extra_protected=[str(protected)])

    assert is_protected(protected / "important.bin", config)
    assert not is_protected(tmp_path / "other.bin", config)


def test_classify_risk_extensions(tmp_path):
    assert classify_risk(Path("a.docx"), base_risk=RiskLevel.SAFE) == RiskLevel.HIGH
    assert classify_risk(Path("a.zip"), base_risk=RiskLevel.SAFE) == RiskLevel.LOW
    assert classify_risk(Path("a.unknown"), base_risk=RiskLevel.LOW) == RiskLevel.LOW


def test_walk_prunes_protected(tmp_path):
    from cleanup.core.scanners import large_files

    protected = tmp_path / "vault"
    protected.mkdir()
    (protected / "big.bin").write_bytes(b"\0" * 5000)
    (tmp_path / "big.bin").write_bytes(b"\0" * 5000)

    config = Config(large_file_min_bytes=1024, extra_protected=[str(protected)])
    result = large_files.scan([tmp_path], config)
    paths = {c.path for c in result.candidates}

    assert str(tmp_path / "big.bin") in paths
    assert str(protected / "big.bin") not in paths
