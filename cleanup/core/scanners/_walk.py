"""Shared, safety-aware filesystem walk used by the file scanners."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from ..config import Config
from ..safety import is_protected


def iter_files(roots: list[Path], config: Config, errors: list[str]) -> Iterator[os.DirEntry]:
    """Yield ``os.DirEntry`` for every regular file under ``roots``.

    Protected directories are pruned so we never even descend into them,
    and per-entry OS errors (permissions, races) are collected rather than
    raised so one bad file cannot abort a whole scan.
    """

    seen: set[str] = set()
    for root in roots:
        if is_protected(root, config):
            continue
        yield from _walk(root, config, errors, seen)


def _walk(directory: Path, config: Config, errors: list[str], seen: set[str]) -> Iterator[os.DirEntry]:
    # Guard against symlink loops / re-visiting the same real dir.
    try:
        key = os.path.realpath(directory)
    except OSError:
        key = str(directory)
    if key in seen:
        return
    seen.add(key)

    try:
        scandir = os.scandir(directory)
    except (OSError, PermissionError) as exc:
        errors.append(f"skip {directory}: {exc}")
        return

    with scandir:
        for entry in scandir:
            try:
                if entry.is_symlink() and not config.follow_symlinks:
                    continue
                if is_protected(Path(entry.path), config):
                    continue
                if entry.is_dir(follow_symlinks=config.follow_symlinks):
                    yield from _walk(Path(entry.path), config, errors, seen)
                elif entry.is_file(follow_symlinks=config.follow_symlinks):
                    yield entry
            except (OSError, PermissionError) as exc:
                errors.append(f"skip {entry.path}: {exc}")
                continue
