"""Detect long-unused installed applications (detection + advice only).

Uninstalling software is inherently HIGH risk and OS-specific, so this
scanner never removes anything itself: it emits candidates with an
``uninstall_hint`` (the command a user could run) and leaves the decision
to an explicit, per-item confirmation.
"""

from __future__ import annotations

import time
from pathlib import Path

from .. import platform_paths
from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult


def scan(config: Config) -> ScanResult:
    osname = platform_paths.current_os()
    if osname == "macos":
        return _scan_macos(config)
    if osname == "windows":
        return _scan_windows(config)
    return _scan_linux(config)


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


def _scan_macos(config: Config) -> ScanResult:
    result = ScanResult()
    now = time.time()
    apps_dir = Path("/Applications")
    if not apps_dir.exists():
        return result
    try:
        entries = list(apps_dir.iterdir())
    except OSError as exc:
        result.errors.append(f"list /Applications: {exc}")
        return result
    for app in entries:
        if app.suffix != ".app":
            continue
        try:
            stat = app.stat()
        except OSError:
            continue
        last_used = max(stat.st_atime, stat.st_mtime)
        if now - last_used < config.app_unused_after_seconds:
            continue
        days = int((now - last_used) // 86400)
        result.add(
            Candidate(
                path=str(app),
                size=_dir_size(app),
                category=Category.UNUSED_APP,
                risk=RiskLevel.HIGH,
                reason=f"約 {days} 日間未使用のアプリ",
                action=Action.UNINSTALL,
                last_access=last_used,
                is_dir=True,
                uninstall_hint=f'アプリを終了してから "{app.name}" をゴミ箱へ移動',
            )
        )
    return result


def _scan_windows(config: Config) -> ScanResult:
    result = ScanResult()
    try:
        import winreg  # type: ignore
    except ImportError:  # not on Windows
        return result

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
                size = int(info.get("EstimatedSize", 0) or 0) * 1024  # KB -> bytes
                result.add(
                    Candidate(
                        path=display,
                        size=size,
                        category=Category.UNUSED_APP,
                        risk=RiskLevel.HIGH,
                        reason="インストール済みアプリ(最終使用日時は要確認)",
                        action=Action.UNINSTALL,
                        is_dir=True,
                        uninstall_hint=uninstall,
                    )
                )
    return result


def _read_reg_values(winreg, key) -> dict:
    out: dict = {}
    for i in range(winreg.QueryInfoKey(key)[1]):
        try:
            name, value, _ = winreg.EnumValue(key, i)
            out[name] = value
        except OSError:
            continue
    return out


def _scan_linux(config: Config) -> ScanResult:
    """Linux: list user-level flatpak apps as an advisory example.

    Distro package managers vary too much to reliably infer "unused", so we
    surface installed flatpaks (which track last-used) and leave system
    packages to the native tools.
    """

    result = ScanResult()
    import shutil
    import subprocess

    flatpak = shutil.which("flatpak")
    if not flatpak:
        return result
    try:
        proc = subprocess.run(
            [flatpak, "list", "--app", "--columns=application,size"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result.errors.append(f"flatpak list: {exc}")
        return result
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        app_id = parts[0].strip()
        result.add(
            Candidate(
                path=app_id,
                size=0,
                category=Category.UNUSED_APP,
                risk=RiskLevel.HIGH,
                reason="インストール済み flatpak アプリ(使用状況は要確認)",
                action=Action.UNINSTALL,
                is_dir=True,
                uninstall_hint=f"flatpak uninstall {app_id}",
            )
        )
    return result
