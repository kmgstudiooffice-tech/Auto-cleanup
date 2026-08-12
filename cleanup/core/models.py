"""Data models shared across scanners, the executor and every front-end.

Everything the engine produces is expressed with these plain dataclasses /
enums so the CLI and the web UI can render the same information without
depending on any scanner internals.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Category(str, enum.Enum):
    """What kind of cleanup a candidate belongs to."""

    LARGE_FILE = "large_file"
    DUPLICATE = "duplicate"
    STALE_FILE = "stale_file"
    UNUSED_APP = "unused_app"
    LARGE_APP = "large_app"
    SYSTEM_JUNK = "system_junk"
    WINDOWS_JUNK = "windows_junk"

    @property
    def label(self) -> str:
        return {
            Category.LARGE_FILE: "大容量ファイル",
            Category.DUPLICATE: "重複ファイル",
            Category.STALE_FILE: "長期間未使用ファイル",
            Category.UNUSED_APP: "未使用アプリ",
            Category.LARGE_APP: "大容量アプリ",
            Category.SYSTEM_JUNK: "システムのゴミ(キャッシュ/一時)",
            Category.WINDOWS_JUNK: "Windows定番の不要ファイル",
        }[self]


class RiskLevel(int, enum.Enum):
    """How dangerous it is to remove a candidate.

    ``HIGH`` items must always be confirmed one-by-one; they are never
    swept up by a bulk "yes to everything" approval.
    """

    SAFE = 0  # regenerable junk: caches, temp files, thumbnails
    LOW = 1   # probably fine but user-owned (big downloads, old archives)
    HIGH = 2  # could matter: documents, apps, anything ambiguous

    @property
    def label(self) -> str:
        return {RiskLevel.SAFE: "安全", RiskLevel.LOW: "低", RiskLevel.HIGH: "高"}[self]


class Action(str, enum.Enum):
    """What the executor should do when a candidate is approved."""

    QUARANTINE = "quarantine"  # move to quarantine (reversible, default)
    UNINSTALL = "uninstall"    # print/run an OS uninstall command (apps)


@dataclass
class Candidate:
    """A single thing the engine proposes to clean up."""

    path: str
    size: int
    category: Category
    risk: RiskLevel
    reason: str
    action: Action = Action.QUARANTINE
    last_access: float | None = None  # epoch seconds, if known
    group_id: str | None = None       # duplicate group key
    is_dir: bool = False
    # For UNUSED_APP: the suggested command a user could run to remove it.
    uninstall_hint: str | None = None

    @property
    def id(self) -> str:
        """Stable identifier used to approve a subset from a UI."""
        import hashlib

        return hashlib.blake2b(self.path.encode("utf-8", "surrogatepass"), digest_size=8).hexdigest()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "path": self.path,
            "size": self.size,
            "category": self.category.value,
            "category_label": self.category.label,
            "risk": self.risk.value,
            "risk_label": self.risk.label,
            "reason": self.reason,
            "action": self.action.value,
            "last_access": self.last_access,
            "group_id": self.group_id,
            "is_dir": self.is_dir,
            "uninstall_hint": self.uninstall_hint,
        }


@dataclass
class ScanResult:
    """Everything a scan found, plus convenience aggregates."""

    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, candidate: Candidate) -> None:
        self.candidates.append(candidate)

    def extend(self, other: ScanResult) -> None:
        self.candidates.extend(other.candidates)
        self.errors.extend(other.errors)

    @property
    def total_size(self) -> int:
        return sum(c.size for c in self.candidates)

    def by_category(self) -> dict[Category, list[Candidate]]:
        out: dict[Category, list[Candidate]] = {}
        for c in self.candidates:
            out.setdefault(c.category, []).append(c)
        return out

    def to_dict(self) -> dict:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "errors": self.errors,
            "total_size": self.total_size,
            "count": len(self.candidates),
        }


def human_size(num_bytes: int) -> str:
    """Format a byte count as a short human-readable string (1.5 GB)."""

    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(size) < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} EB"
