"""Executes approved cleanups safely and reversibly.

The default action moves a file into a timestamped *quarantine* directory
instead of deleting it, recording enough metadata in ``manifest.json`` to
put it back. Nothing is ever permanently lost until the user explicitly
purges a quarantine session.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .config import QUARANTINE_ROOT, Config
from .models import Action, Candidate
from .safety import is_protected


@dataclass
class ExecutionReport:
    quarantined: list[str]
    freed_bytes: int
    skipped: list[tuple[str, str]]  # (path, reason)
    session_id: str | None
    manual_uninstalls: list[Candidate]


class Executor:
    def __init__(self, config: Config, *, dry_run: bool = True):
        self.config = config
        self.dry_run = dry_run

    # -- cleanup ---------------------------------------------------------
    def execute(self, candidates: list[Candidate]) -> ExecutionReport:
        quarantined: list[str] = []
        skipped: list[tuple[str, str]] = []
        manual: list[Candidate] = []
        freed = 0
        session_id = time.strftime("%Y%m%d-%H%M%S")
        session_dir = QUARANTINE_ROOT / session_id
        manifest: list[dict] = []

        for c in candidates:
            # Apps are advisory only: never auto-removed by the executor.
            if c.action == Action.UNINSTALL:
                manual.append(c)
                continue

            path = Path(c.path)
            # Final safety net: refuse protected paths even if approved.
            if is_protected(path, self.config):
                skipped.append((c.path, "protected path"))
                continue
            if not path.exists():
                skipped.append((c.path, "no longer exists"))
                continue

            if self.dry_run:
                quarantined.append(c.path)
                freed += c.size
                continue

            try:
                dest = self._move_to_quarantine(path, session_dir)
            except OSError as exc:
                skipped.append((c.path, str(exc)))
                continue
            manifest.append({"original": str(path), "quarantined": str(dest), "size": c.size})
            quarantined.append(c.path)
            freed += c.size

        if not self.dry_run and manifest:
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return ExecutionReport(
            quarantined=quarantined,
            freed_bytes=freed,
            skipped=skipped,
            session_id=session_id if (not self.dry_run and manifest) else None,
            manual_uninstalls=manual,
        )

    def _move_to_quarantine(self, path: Path, session_dir: Path) -> Path:
        # Mirror the original absolute path under the session dir so two
        # files with the same name never collide.
        rel = Path(*[p for p in path.parts if p not in ("/", path.anchor)])
        dest = session_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        return dest

    # -- restore / purge -------------------------------------------------
    @staticmethod
    def list_sessions() -> list[str]:
        if not QUARANTINE_ROOT.exists():
            return []
        return sorted(p.name for p in QUARANTINE_ROOT.iterdir() if (p / "manifest.json").exists())

    @staticmethod
    def restore(session_id: str) -> tuple[list[str], list[tuple[str, str]]]:
        """Move a quarantined session's files back to their origins."""

        session_dir = QUARANTINE_ROOT / session_id
        manifest_path = session_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"unknown session: {session_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        restored: list[str] = []
        failed: list[tuple[str, str]] = []
        for item in manifest:
            src = Path(item["quarantined"])
            dst = Path(item["original"])
            try:
                if not src.exists():
                    failed.append((item["original"], "missing in quarantine"))
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                restored.append(item["original"])
            except OSError as exc:
                failed.append((item["original"], str(exc)))
        if not failed:
            shutil.rmtree(session_dir, ignore_errors=True)
        return restored, failed

    @staticmethod
    def purge(session_id: str) -> None:
        """Permanently delete a quarantine session (irreversible)."""

        session_dir = QUARANTINE_ROOT / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
