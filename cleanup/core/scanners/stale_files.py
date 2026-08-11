"""Find files that have not been touched for a long time."""

from __future__ import annotations

import time
from pathlib import Path

from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult
from ..safety import classify_risk
from ._walk import iter_files


def scan(roots: list[Path], config: Config) -> ScanResult:
    result = ScanResult()
    now = time.time()
    cutoff = config.stale_after_seconds
    for entry in iter_files(roots, config, result.errors):
        try:
            stat = entry.stat()
        except OSError as exc:
            result.errors.append(f"stat {entry.path}: {exc}")
            continue
        # Use the most recent of access/modification so actively-read files
        # are not flagged even if never rewritten.
        last_used = max(stat.st_atime, stat.st_mtime)
        idle = now - last_used
        if idle < cutoff:
            continue
        path = Path(entry.path)
        days = int(idle // 86400)
        result.add(
            Candidate(
                path=str(path),
                size=stat.st_size,
                category=Category.STALE_FILE,
                risk=classify_risk(path, base_risk=RiskLevel.LOW),
                reason=f"約 {days} 日間アクセスなし",
                action=Action.QUARANTINE,
                last_access=last_used,
            )
        )
    return result
