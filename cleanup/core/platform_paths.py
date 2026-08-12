"""OS-specific knowledge: where junk lives, and what must be protected.

Each OS exposes:
  * ``junk_roots()``   – directories safe to look inside for regenerable junk
                         (caches, temp, logs). Contents are SAFE risk.
  * ``scan_roots()``   – user directories worth scanning for large/stale/dup
                         files (Downloads, etc.). Contents are LOW/HIGH risk.
  * ``protected_paths()`` – directories that must NEVER be proposed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _home() -> Path:
    return Path.home()


def current_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _existing(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        try:
            if p.exists():
                out.append(p)
        except OSError:
            continue
    return out


def junk_roots() -> list[Path]:
    """Directories whose contents are regenerable junk (SAFE to remove)."""

    home = _home()
    osname = current_os()
    if osname == "windows":
        localapp = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates = [
            Path(os.environ.get("TEMP", localapp / "Temp")),
            localapp / "Temp",
            localapp / "Microsoft" / "Windows" / "INetCache",
        ]
    elif osname == "macos":
        candidates = [
            home / "Library" / "Caches",
            Path("/private/var/folders"),  # user temp; walked read-mostly
            home / "Library" / "Logs",
        ]
    else:  # linux
        xdg_cache = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
        candidates = [
            xdg_cache,
            Path("/tmp"),
            Path("/var/tmp"),
        ]
    return _existing(candidates)


def windows_junk_roots() -> list[Path]:
    """Well-known, user-writable Windows junk locations (SAFE to clear).

    These are all under the user profile (``%LOCALAPPDATA%``) so clearing
    them needs no admin rights and never touches ``C:\\Windows``. Everything
    here is regenerable: temp files, thumbnail/shader caches, crash dumps
    and error reports.
    """

    if current_os() != "windows":
        return []
    localapp = Path(os.environ.get("LOCALAPPDATA", _home() / "AppData" / "Local"))
    candidates = [
        localapp / "Temp",
        localapp / "CrashDumps",
        localapp / "D3DSCache",                                   # shader cache
        localapp / "Microsoft" / "Windows" / "Explorer",          # thumbnail cache
        localapp / "Microsoft" / "Windows" / "INetCache",         # IE/Edge cache
        localapp / "Microsoft" / "Windows" / "WER",               # error reports
        localapp / "Microsoft" / "Windows" / "WebCache",
        localapp / "Microsoft" / "Terminal Server Client" / "Cache",
        localapp / "NVIDIA" / "DXCache",
        localapp / "NVIDIA" / "GLCache",
    ]
    return _existing(candidates)


def scan_roots() -> list[Path]:
    """User directories worth scanning for large / stale / duplicate files."""

    home = _home()
    candidates = [
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
        home / "Movies",
        home / "Videos",
        home / "Pictures",
    ]
    return _existing(candidates)


def protected_paths() -> list[Path]:
    """Paths that must never be proposed for deletion (system-critical)."""

    home = _home()
    osname = current_os()
    common = [
        home / ".ssh",
        home / ".gnupg",
        home / ".config" / "auto-cleanup",  # our own config
    ]
    if osname == "windows":
        system = [
            Path(os.environ.get("SystemRoot", r"C:\Windows")),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ]
    elif osname == "macos":
        system = [Path("/System"), Path("/Library"), Path("/bin"), Path("/usr"), Path("/Applications")]
    else:
        system = [Path("/bin"), Path("/sbin"), Path("/usr"), Path("/etc"), Path("/boot"), Path("/lib")]
    return common + system
