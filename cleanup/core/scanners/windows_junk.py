"""Scan well-known Windows junk locations (regenerable, SAFE, no admin)."""

from __future__ import annotations

from pathlib import Path

from .. import platform_paths
from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult
from ._walk import iter_files


def scan(config: Config, roots: list[Path] | None = None) -> ScanResult:
    result = ScanResult()
    roots = roots if roots is not None else platform_paths.windows_junk_roots()
    for entry in iter_files(roots, config, result.errors):
        try:
            stat = entry.stat()
        except OSError as exc:
            result.errors.append(f"stat {entry.path}: {exc}")
            continue
        result.add(
            Candidate(
                path=str(Path(entry.path)),
                size=stat.st_size,
                category=Category.WINDOWS_JUNK,
                risk=RiskLevel.SAFE,
                reason="Windows定番の不要ファイル(キャッシュ/一時/クラッシュログ等)",
                action=Action.QUARANTINE,
                last_access=stat.st_atime,
            )
        )
    return result
