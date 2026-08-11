"""Scan OS cache / temp / log directories for regenerable junk (SAFE)."""

from __future__ import annotations

from pathlib import Path

from .. import platform_paths
from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult
from ._walk import iter_files


def scan(config: Config) -> ScanResult:
    result = ScanResult()
    roots = platform_paths.junk_roots()
    for entry in iter_files(roots, config, result.errors):
        try:
            stat = entry.stat()
        except OSError as exc:
            result.errors.append(f"stat {entry.path}: {exc}")
            continue
        # Everything under a junk root is regenerable, hence SAFE risk.
        result.add(
            Candidate(
                path=str(Path(entry.path)),
                size=stat.st_size,
                category=Category.SYSTEM_JUNK,
                risk=RiskLevel.SAFE,
                reason="キャッシュ/一時ファイル(再生成される)",
                action=Action.QUARANTINE,
                last_access=stat.st_atime,
            )
        )
    return result
