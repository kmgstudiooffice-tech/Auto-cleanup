"""Find individual files that occupy a lot of space."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult
from ..safety import classify_risk
from ._walk import iter_files


def scan(roots: list[Path], config: Config) -> ScanResult:
    result = ScanResult()
    for entry in iter_files(roots, config, result.errors):
        try:
            stat = entry.stat()
        except OSError as exc:
            result.errors.append(f"stat {entry.path}: {exc}")
            continue
        if stat.st_size < config.large_file_min_bytes:
            continue
        path = Path(entry.path)
        # Large user files default to LOW; documents get bumped to HIGH.
        risk = classify_risk(path, base_risk=RiskLevel.LOW)
        result.add(
            Candidate(
                path=str(path),
                size=stat.st_size,
                category=Category.LARGE_FILE,
                risk=risk,
                reason=f"{stat.st_size // (1024 * 1024)} MB の大容量ファイル",
                action=Action.QUARANTINE,
                last_access=stat.st_atime,
            )
        )
    return result
