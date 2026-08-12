"""Smoke test for the optional web API (skipped if deps are missing)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from cleanup.web.server import _build_app


def test_scan_and_dry_run_clean(sandbox):
    (sandbox / "big.bin").write_bytes(b"\0" * 200_000)
    client = TestClient(_build_app())

    r = client.post("/api/scan", json={"paths": [str(sandbox)], "categories": ["large_file"]})
    assert r.status_code == 200
    data = r.json()
    # config default large threshold is 100MB; override via query is not
    # exposed, so just assert the endpoint shape is correct.
    assert "candidates" in data and "total_size" in data and "count" in data

    r2 = client.post("/api/clean", json={"ids": [], "apply": False})
    assert r2.status_code == 200
    assert r2.json()["dry_run"] is True


def test_index_served():
    client = TestClient(_build_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "Auto-Cleanup" in r.text


def test_clean_sessions_restore_flow(sandbox, monkeypatch):
    """Apply a cleanup via the API, see it in sessions, then restore it."""

    # Lower the large-file threshold so a small temp file qualifies by
    # making Config.load() return a tuned config.
    from cleanup.core.config import Config

    monkeypatch.setattr(Config, "load", classmethod(lambda cls: Config(large_file_min_bytes=1000)))

    demo = sandbox / "demo"
    demo.mkdir()
    f = demo / "big.bin"
    f.write_bytes(b"\0" * 5000)

    client = TestClient(_build_app())
    scan = client.post("/api/scan", json={"paths": [str(demo)], "categories": ["large_file"]}).json()
    ids = [c["id"] for c in scan["candidates"]]
    assert ids, "expected the large file to be found"

    clean = client.post("/api/clean", json={"ids": ids, "apply": True}).json()
    assert clean["quarantined"] == 1
    assert clean["session_id"] and clean["quarantine_dir"]
    assert not f.exists()  # moved to quarantine

    sessions = client.get("/api/sessions").json()["sessions"]
    assert any(s["id"] == clean["session_id"] and s["count"] == 1 for s in sessions)

    restore = client.post("/api/restore", json={"session_id": clean["session_id"]}).json()
    assert len(restore["restored"]) == 1
    assert not restore["failed"]
    assert f.exists()  # back in place
