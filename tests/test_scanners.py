"""Tests for the individual scanners against a synthetic directory tree."""

from __future__ import annotations

import os
import time

from cleanup.core.config import Config
from cleanup.core.models import Category, RiskLevel
from cleanup.core.scanners import duplicates, large_files, stale_files


def _write(path, size=0, content=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        path.write_bytes(content)
    else:
        path.write_bytes(b"\0" * size)
    return path


def test_large_files_threshold(tmp_path):
    config = Config(large_file_min_bytes=1024)
    _write(tmp_path / "big.bin", size=4096)
    _write(tmp_path / "small.bin", size=100)

    result = large_files.scan([tmp_path], config)
    paths = {c.path for c in result.candidates}

    assert str(tmp_path / "big.bin") in paths
    assert str(tmp_path / "small.bin") not in paths
    assert all(c.category == Category.LARGE_FILE for c in result.candidates)


def test_large_file_document_is_high_risk(tmp_path):
    config = Config(large_file_min_bytes=1024)
    _write(tmp_path / "report.pdf", size=4096)
    _write(tmp_path / "archive.zip", size=4096)

    result = large_files.scan([tmp_path], config)
    by_name = {c.path.rsplit("/", 1)[-1]: c for c in result.candidates}

    assert by_name["report.pdf"].risk == RiskLevel.HIGH
    assert by_name["archive.zip"].risk == RiskLevel.LOW


def test_duplicates_detected_and_keeps_one(tmp_path):
    config = Config(duplicate_min_bytes=8)
    payload = b"the-same-bytes-repeated" * 100
    a = _write(tmp_path / "a.dat", content=payload)
    b = _write(tmp_path / "sub" / "b.dat", content=payload)
    _write(tmp_path / "unique.dat", content=b"different" * 100)

    result = duplicates.scan([tmp_path], config)
    dup_paths = {c.path for c in result.candidates}

    # Exactly one of the two identical files is proposed (the other kept).
    assert len(dup_paths) == 1
    assert dup_paths <= {str(a), str(b)}
    assert all(c.group_id for c in result.candidates)


def test_duplicates_ignores_same_size_different_content(tmp_path):
    config = Config(duplicate_min_bytes=8)
    _write(tmp_path / "x.dat", content=b"A" * 500)
    _write(tmp_path / "y.dat", content=b"B" * 500)  # same size, different bytes

    result = duplicates.scan([tmp_path], config)
    assert result.candidates == []


def test_stale_files(tmp_path):
    config = Config(stale_after_seconds=100 * 86400)
    old = _write(tmp_path / "old.txt", size=10)
    _write(tmp_path / "new.txt", size=10)

    old_time = time.time() - 200 * 86400
    os.utime(old, (old_time, old_time))

    result = stale_files.scan([tmp_path], config)
    paths = {c.path for c in result.candidates}

    assert str(old) in paths
    assert str(tmp_path / "new.txt") not in paths
