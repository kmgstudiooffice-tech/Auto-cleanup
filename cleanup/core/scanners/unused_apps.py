"""Enumerate installed apps and flag the long-unused ones (advisory only).

Uninstalling software is inherently HIGH risk and OS-specific, so these
scanners never remove anything themselves: they emit candidates with an
``uninstall_hint`` (the command/steps to remove it) and an ``UNINSTALL``
action, which the UI shows unchecked and never auto-processes.

``enumerate_apps`` is the shared source of app records; :func:`scan` here
keeps only apps we believe are *not recently used*, and the sibling
``large_apps`` scanner keeps the *space-hungry* ones.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .. import platform_paths
from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult


@dataclass
class AppRecord:
    name: str          # display name / path used as the candidate path
    size: int          # bytes on disk (0 if unknown)
    last_used: float | None  # epoch seconds, or None if unknown
    uninstall_hint: str | None


def enumerate_apps(config: Config) -> tuple[list[AppRecord], list[str]]:
    osname = platform_paths.current_os()
    if osname == "macos":
        return _enumerate_macos()
    if osname == "windows":
        return _enumerate_windows()
    return _enumerate_linux()


def scan(config: Config) -> ScanResult:
    """Propose apps that have not been used for a long time.

    Only apps with a *known* last-used time older than the configured
    threshold are proposed, so we surface genuinely idle apps rather than
    dumping the entire installed list.
    """

    result = ScanResult()
    records, result.errors = enumerate_apps(config)
    now = time.time()
    for app in records:
        if app.last_used is None:
            continue  # unknown usage -> don't guess it's unused
        idle = now - app.last_used
        if idle < config.app_unused_after_seconds:
            continue
        days = int(idle // 86400)
        result.add(
            Candidate(
                path=app.name,
                size=app.size,
                category=Category.UNUSED_APP,
                risk=RiskLevel.HIGH,
                reason=f"約 {days} 日間使用されていないアプリ",
                action=Action.UNINSTALL,
                last_access=app.last_used,
                is_dir=True,
                uninstall_hint=app.uninstall_hint,
            )
        )
    return result


# -- per-OS enumeration --------------------------------------------------
def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _enumerate_macos() -> tuple[list[AppRecord], list[str]]:
    records: list[AppRecord] = []
    errors: list[str] = []
    apps_dir = Path("/Applications")
    if not apps_dir.exists():
        return records, errors
    try:
        entries = list(apps_dir.iterdir())
    except OSError as exc:
        errors.append(f"list /Applications: {exc}")
        return records, errors
    for app in entries:
        if app.suffix != ".app":
            continue
        try:
            stat = app.stat()
        except OSError:
            continue
        records.append(
            AppRecord(
                name=str(app),
                size=_dir_size(app),
                last_used=max(stat.st_atime, stat.st_mtime),
                uninstall_hint=f'アプリを終了してから "{app.name}" をゴミ箱へ移動',
            )
        )
    return records, errors


def _enumerate_windows() -> tuple[list[AppRecord], list[str]]:
    records: list[AppRecord] = []
    errors: list[str] = []
    try:
        import winreg  # type: ignore
    except ImportError:  # not on Windows
        return records, errors

    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, subkey in keys:
        try:
            hive = winreg.OpenKey(root, subkey)
        except OSError:
            continue
        with hive:
            for i in range(winreg.QueryInfoKey(hive)[0]):
                try:
                    name = winreg.EnumKey(hive, i)
                    app_key = winreg.OpenKey(hive, name)
                except OSError:
                    continue
                with app_key:
                    info = _read_reg_values(winreg, app_key)
                display = info.get("DisplayName")
                uninstall = info.get("UninstallString")
                if not display or not uninstall:
                    continue
                if int(info.get("SystemComponent", 0) or 0):
                    continue  # hidden system components
                size = int(info.get("EstimatedSize", 0) or 0) * 1024  # KB -> bytes
                records.append(
                    AppRecord(
                        name=display,
                        size=size,
                        last_used=_windows_last_used(info),
                        uninstall_hint=uninstall,
                    )
                )
    return records, errors


def _windows_last_used(info: dict) -> float | None:
    """Best-effort last-used estimate from the install folder's timestamps."""

    location = info.get("InstallLocation")
    if not location:
        return None
    try:
        stat = Path(location).stat()
    except OSError:
        return None
    return max(stat.st_atime, stat.st_mtime)


def _read_reg_values(winreg, key) -> dict:
    out: dict = {}
    for i in range(winreg.QueryInfoKey(key)[1]):
        try:
            name, value, _ = winreg.EnumValue(key, i)
            out[name] = value
        except OSError:
            continue
    return out


def _enumerate_linux() -> tuple[list[AppRecord], list[str]]:
    records: list[AppRecord] = []
    errors: list[str] = []
    import shutil
    import subprocess

    flatpak = shutil.which("flatpak")
    if not flatpak:
        return records, errors
    try:
        proc = subprocess.run(
            [flatpak, "list", "--app", "--columns=application,size"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"flatpak list: {exc}")
        return records, errors
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        app_id = parts[0].strip()
        size = _parse_size(parts[1]) if len(parts) > 1 else 0
        records.append(
            AppRecord(
                name=app_id,
                size=size,
                last_used=None,  # flatpak does not expose last-used here
                uninstall_hint=f"flatpak uninstall {app_id}",
            )
        )
    return records, errors


def _parse_size(text: str) -> int:
    """Parse a human size like '1.2 GB' / '512 MB' into bytes (best effort)."""

    text = text.strip()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for unit in ("TB", "GB", "MB", "KB", "B"):
        if text.upper().endswith(unit):
            num = text[: -len(unit)].strip().replace(",", "")
            try:
                return int(float(num) * units[unit])
            except ValueError:
                return 0
    return 0
