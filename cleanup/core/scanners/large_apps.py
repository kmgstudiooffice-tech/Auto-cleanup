"""Flag installed apps that take up a lot of disk space (advisory only)."""

from __future__ import annotations

from ..config import Config
from ..models import Action, Candidate, Category, RiskLevel, ScanResult
from .unused_apps import enumerate_apps


def scan(config: Config) -> ScanResult:
    result = ScanResult()
    records, result.errors = enumerate_apps(config)
    for app in records:
        if app.size < config.large_app_min_bytes:
            continue
        result.add(
            Candidate(
                path=app.name,
                size=app.size,
                category=Category.LARGE_APP,
                risk=RiskLevel.HIGH,
                reason=f"{app.size // (1024 * 1024)} MB を占める大容量アプリ",
                action=Action.UNINSTALL,
                last_access=app.last_used,
                is_dir=True,
                uninstall_hint=app.uninstall_hint,
            )
        )
    return result
