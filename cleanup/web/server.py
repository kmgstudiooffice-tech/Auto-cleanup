"""Local web UI backend.

This is a thin HTTP layer over the same ``core`` engine the CLI uses. The
browser shows scan results with checkboxes; only the ids the user ticks are
sent to ``/api/clean``, and HIGH-risk items require an explicit extra
confirmation in the front-end before their ids are included.

Bind to localhost only — this exposes filesystem actions and must never be
reachable from the network.
"""

from pathlib import Path

from pydantic import BaseModel

from ..core import scanner
from ..core.config import Config
from ..core.executor import Executor
from ..core.models import Candidate


# Request models live at module level so FastAPI can resolve the annotations
# (defining them inside the factory breaks annotation resolution).
class ScanRequest(BaseModel):
    paths: list[str] | None = None
    categories: list[str] | None = None


class CleanRequest(BaseModel):
    ids: list[str]
    apply: bool = False


class RestoreRequest(BaseModel):
    session_id: str


class PurgeRequest(BaseModel):
    session_id: str


def _build_app():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    app = FastAPI(title="Auto-Cleanup", docs_url=None, redoc_url=None)
    static_dir = Path(__file__).parent / "static"

    # Cache the most recent scan so /api/clean can map ids back to paths
    # without trusting client-supplied paths.
    state: dict[str, Candidate] = {}

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    @app.post("/api/scan")
    def api_scan(req: ScanRequest):
        from ..core.models import Category

        config = Config.load()
        cats = None
        if req.categories:
            cats = [Category(c) for c in req.categories]
        result = scanner.scan(config, categories=cats, roots=req.paths or None)
        state.clear()
        for c in result.candidates:
            state[c.id] = c
        return JSONResponse(result.to_dict())

    @app.post("/api/clean")
    def api_clean(req: CleanRequest):
        config = Config.load()
        selected = [state[i] for i in req.ids if i in state]
        executor = Executor(config, dry_run=not req.apply)
        report = executor.execute(selected)
        from ..core.config import QUARANTINE_ROOT

        quarantine_dir = str(QUARANTINE_ROOT / report.session_id) if report.session_id else None
        return JSONResponse(
            {
                "quarantined": len(report.quarantined),
                "quarantined_paths": report.quarantined,
                "freed_bytes": report.freed_bytes,
                "skipped": report.skipped,
                "session_id": report.session_id,
                "quarantine_dir": quarantine_dir,
                "dry_run": not req.apply,
                "manual_uninstalls": [c.to_dict() for c in report.manual_uninstalls],
            }
        )

    @app.get("/api/sessions")
    def api_sessions():
        return {"sessions": Executor.session_details()}

    @app.post("/api/restore")
    def api_restore(req: RestoreRequest):
        restored, failed = Executor.restore(req.session_id)
        return {"restored": restored, "failed": failed}

    @app.post("/api/purge")
    def api_purge(req: PurgeRequest):
        # Irreversible: permanently delete a quarantine session's files.
        existed = req.session_id in Executor.list_sessions()
        Executor.purge(req.session_id)
        return {"purged": existed, "session_id": req.session_id}

    return app


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("安全のため localhost 以外へのバインドは許可されていません。")
    uvicorn.run(_build_app(), host=host, port=port)
