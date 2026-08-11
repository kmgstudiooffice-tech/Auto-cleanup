"""User-tunable thresholds and paths, with sensible cross-OS defaults.

Config is loaded from ``~/.config/auto-cleanup/config.json`` if present and
merged over the defaults, so a user can raise the "large file" threshold or
add extra roots without touching code.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "auto-cleanup"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Quarantine lives under the home dir so restores work even after a reboot.
QUARANTINE_ROOT = Path.home() / ".auto-cleanup-quarantine"

MB = 1024 * 1024
DAY = 86400  # seconds


@dataclass
class Config:
    # A file is "large" at or above this many bytes.
    large_file_min_bytes: int = 100 * MB
    # A file is "stale" if not accessed/modified for this many seconds.
    stale_after_seconds: int = 180 * DAY
    # An app is "unused" if not launched for this many seconds.
    app_unused_after_seconds: int = 180 * DAY
    # Minimum size for a duplicate group to be worth reporting.
    duplicate_min_bytes: int = 1 * MB
    # Follow symlinks while walking (kept off for safety).
    follow_symlinks: bool = False
    # Extra roots to scan in addition to the OS defaults.
    extra_roots: list[str] = field(default_factory=list)
    # Extra path substrings to always protect (never propose for deletion).
    extra_protected: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> Config:
        cfg = cls()
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(cfg, key):
                        setattr(cfg, key, value)
        except (json.JSONDecodeError, OSError):
            # A broken config file should never block a scan; fall back to
            # defaults rather than crashing.
            pass
        return cfg

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
