"""Find duplicate files using a cheap-to-expensive, three-stage compare.

1. Group by size (a free ``stat`` we already need).
2. Within a size group, hash only a small head+tail sample to split it.
3. Only for files that still collide, hash the full contents to confirm.

This avoids reading every byte of every file: unique sizes are eliminated
for free, and full hashing runs only on genuine near-collisions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult
from ..safety import classify_risk
from ._walk import iter_files

_SAMPLE = 64 * 1024  # bytes read from head and tail for the quick hash


def _hash(path: Path, *, partial: bool) -> str | None:
    h = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb") as fh:
            if partial:
                head = fh.read(_SAMPLE)
                h.update(head)
                try:
                    fh.seek(-_SAMPLE, 2)
                    h.update(fh.read(_SAMPLE))
                except OSError:
                    pass  # file smaller than one sample; head is enough
            else:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def scan(roots: list[Path], config: Config) -> ScanResult:
    result = ScanResult()

    by_size: dict[int, list[Path]] = {}
    for entry in iter_files(roots, config, result.errors):
        try:
            size = entry.stat().st_size
        except OSError as exc:
            result.errors.append(f"stat {entry.path}: {exc}")
            continue
        if size < config.duplicate_min_bytes:
            continue
        by_size.setdefault(size, []).append(Path(entry.path))

    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        # Stage 2: split the size group by a cheap partial hash.
        by_partial: dict[str, list[Path]] = {}
        for p in paths:
            ph = _hash(p, partial=True)
            if ph is not None:
                by_partial.setdefault(ph, []).append(p)

        for candidates in by_partial.values():
            if len(candidates) < 2:
                continue
            # Stage 3: confirm with a full hash.
            by_full: dict[str, list[Path]] = {}
            for p in candidates:
                fh = _hash(p, partial=False)
                if fh is not None:
                    by_full.setdefault(fh, []).append(p)

            for full_hash, group in by_full.items():
                if len(group) < 2:
                    continue
                # Keep the oldest (smallest mtime) file; propose the rest.
                group_sorted = sorted(group, key=lambda p: _safe_mtime(p))
                keeper = group_sorted[0]
                for dup in group_sorted[1:]:
                    result.add(
                        Candidate(
                            path=str(dup),
                            size=size,
                            category=Category.DUPLICATE,
                            risk=classify_risk(dup, base_risk=RiskLevel.LOW),
                            reason=f"{keeper.name} と内容が同一の重複",
                            action=Action.QUARANTINE,
                            last_access=_safe_atime(dup),
                            group_id=full_hash[:12],
                        )
                    )
    return result


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_atime(path: Path) -> float | None:
    try:
        return path.stat().st_atime
    except OSError:
        return None
