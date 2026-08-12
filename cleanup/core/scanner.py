"""Orchestrates the individual scanners into a single scan run."""

from __future__ import annotations

from pathlib import Path

from . import platform_paths
from .config import Config
from .models import Category, ScanResult
from .scanners import (
    duplicates,
    large_apps,
    large_files,
    stale_files,
    system_junk,
    unused_apps,
    windows_junk,
)

ALL_CATEGORIES = [
    Category.SYSTEM_JUNK,
    Category.WINDOWS_JUNK,
    Category.LARGE_FILE,
    Category.DUPLICATE,
    Category.STALE_FILE,
    Category.LARGE_APP,
    Category.UNUSED_APP,
]


def resolve_roots(config: Config, roots: list[str] | None) -> list[Path]:
    """Pick which directories to scan: explicit args, or the OS defaults."""

    if roots:
        return [Path(r).expanduser() for r in roots]
    default = platform_paths.scan_roots()
    default.extend(Path(r).expanduser() for r in config.extra_roots)
    return default


def scan(
    config: Config,
    *,
    categories: list[Category] | None = None,
    roots: list[str] | None = None,
) -> ScanResult:
    """Run the selected scanners and merge their candidates.

    ``roots`` limits file scanners to the given directories (used by the CLI
    ``--path`` flag and by tests). ``categories`` limits which scanners run.
    """

    categories = categories or ALL_CATEGORIES
    file_roots = resolve_roots(config, roots)
    result = ScanResult()

    if Category.SYSTEM_JUNK in categories and not roots:
        # System junk always comes from OS junk roots, not user --path.
        result.extend(system_junk.scan(config))
    if Category.WINDOWS_JUNK in categories and not roots:
        result.extend(windows_junk.scan(config))
    if Category.LARGE_FILE in categories:
        result.extend(large_files.scan(file_roots, config))
    if Category.DUPLICATE in categories:
        result.extend(duplicates.scan(file_roots, config))
    if Category.STALE_FILE in categories:
        result.extend(stale_files.scan(file_roots, config))
    if Category.LARGE_APP in categories and not roots:
        result.extend(large_apps.scan(config))
    if Category.UNUSED_APP in categories and not roots:
        result.extend(unused_apps.scan(config))

    _dedupe(result)
    return result


def _dedupe(result: ScanResult) -> None:
    """Keep one candidate per path, preferring the higher-risk classification.

    A file can match several scanners (e.g. large AND stale); we surface it
    once so the user isn't asked about the same path twice.
    """

    best: dict[str, int] = {}
    ordered = []
    for c in result.candidates:
        prev = best.get(c.path)
        if prev is None:
            best[c.path] = len(ordered)
            ordered.append(c)
        else:
            # Prefer the entry with the higher risk (safer to over-warn).
            if c.risk.value > ordered[prev].risk.value:
                ordered[prev] = c
    result.candidates = ordered
