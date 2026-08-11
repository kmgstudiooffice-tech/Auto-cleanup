"""The safety layer: decides what is off-limits and how risky a path is.

Every scanner runs its candidates past :func:`is_protected` before emitting
them, and the executor refuses to touch a protected path even if a buggy
scanner slips one through. This is the single choke-point for "do no harm".
"""

from __future__ import annotations

from pathlib import Path

from . import platform_paths
from .config import QUARANTINE_ROOT, Config
from .models import RiskLevel

# File extensions we treat as user content that could really matter.
_HIGH_RISK_EXTS = {
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".pages",
    ".numbers", ".key", ".txt", ".md", ".rtf", ".odt",
    ".jpg", ".jpeg", ".png", ".heic", ".raw", ".psd", ".ai",
    ".sqlite", ".db", ".kdbx", ".pem",
}
# Extensions that are typically regenerable / re-downloadable (lower risk).
_LOW_RISK_EXTS = {
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".iso", ".dmg", ".pkg", ".exe", ".msi", ".deb", ".rpm",
    ".log", ".tmp", ".cache", ".part", ".crdownload",
}


def protected_prefixes(config: Config) -> list[Path]:
    prefixes = list(platform_paths.protected_paths())
    prefixes.append(QUARANTINE_ROOT)  # never re-scan our own quarantine
    prefixes.extend(Path(p) for p in config.extra_protected)
    return [p.resolve() if p.exists() else p for p in prefixes]


def is_protected(path: Path, config: Config) -> bool:
    """True if ``path`` is inside (or equal to) any protected prefix."""

    try:
        target = path.resolve()
    except (OSError, RuntimeError):
        target = path
    for prefix in protected_prefixes(config):
        try:
            target.relative_to(prefix)
            return True
        except ValueError:
            continue
        except OSError:
            continue
    return False


def classify_risk(path: Path, *, base_risk: RiskLevel = RiskLevel.LOW) -> RiskLevel:
    """Refine a candidate's risk from its file extension.

    ``base_risk`` is the category's floor (e.g. SAFE for cache junk); a
    document extension can only raise the risk, never lower it.
    """

    ext = path.suffix.lower()
    if ext in _HIGH_RISK_EXTS:
        return max(base_risk, RiskLevel.HIGH, key=lambda r: r.value)
    if ext in _LOW_RISK_EXTS:
        return max(base_risk, RiskLevel.LOW, key=lambda r: r.value)
    return base_risk
