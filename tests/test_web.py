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
