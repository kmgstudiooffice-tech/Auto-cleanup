"""Tests for the executor: quarantine is reversible and never loses data."""

from __future__ import annotations

from pathlib import Path

from cleanup.core.config import Config
from cleanup.core.executor import Executor
from cleanup.core.models import Action, Candidate, Category, RiskLevel


def _candidate(path: Path, size: int) -> Candidate:
    return Candidate(
        path=str(path),
        size=size,
        category=Category.LARGE_FILE,
        risk=RiskLevel.LOW,
        reason="test",
        action=Action.QUARANTINE,
    )


def test_dry_run_changes_nothing(sandbox):
    f = sandbox / "file.bin"
    f.write_bytes(b"\0" * 100)
    config = Config()
    report = Executor(config, dry_run=True).execute([_candidate(f, 100)])

    assert f.exists()  # untouched
    assert report.freed_bytes == 100
    assert report.session_id is None


def test_quarantine_then_restore_roundtrip(sandbox):
    f = sandbox / "data" / "file.bin"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"hello-world")
    config = Config()

    report = Executor(config, dry_run=False).execute([_candidate(f, 11)])
    assert not f.exists()  # moved to quarantine
    assert report.session_id is not None

    _restored, failed = Executor.restore(report.session_id)
    assert failed == []
    assert f.exists()
    assert f.read_bytes() == b"hello-world"


def test_executor_refuses_protected_path(sandbox):
    protected = sandbox / "vault"
    protected.mkdir()
    f = protected / "keep.bin"
    f.write_bytes(b"x" * 50)
    config = Config(extra_protected=[str(protected)])

    report = Executor(config, dry_run=False).execute([_candidate(f, 50)])

    assert f.exists()  # protected, not moved
    assert any("protected" in reason for _, reason in report.skipped)


def test_uninstall_candidates_are_not_touched(sandbox):
    app = Candidate(
        path="SomeApp",
        size=0,
        category=Category.UNUSED_APP,
        risk=RiskLevel.HIGH,
        reason="unused",
        action=Action.UNINSTALL,
        uninstall_hint="remove it",
    )
    report = Executor(Config(), dry_run=False).execute([app])
    assert report.manual_uninstalls == [app]
    assert report.quarantined == []
