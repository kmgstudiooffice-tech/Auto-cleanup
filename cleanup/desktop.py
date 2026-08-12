"""Desktop entry point: run the app as a native GUI window (packaged .exe).

This starts the same FastAPI engine used by ``cleanup web`` on a private
localhost port, waits for it to come up, then shows it inside a native
desktop window via ``pywebview`` — so the packaged ``.exe`` looks and feels
like a normal desktop application rather than a browser tab.

Robustness matters here because the packaged exe has *no console*: any
unhandled error would otherwise make it look like "nothing happens" when
double-clicked. So every stage is logged to a file, and if the native
window cannot be created (e.g. the WebView2 runtime / pythonnet backend is
missing on the machine) we fall back to opening the user's default browser
at the same local URL — guaranteeing the UI always appears somewhere.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from pathlib import Path

APP_TITLE = "Auto-Cleanup"

logger = logging.getLogger("auto-cleanup.desktop")


def _log_path() -> Path:
    """A writable path for the startup log (next to the exe, else temp)."""

    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).with_name("Auto-Cleanup.log"))
    candidates.append(Path(tempfile.gettempdir()) / "auto-cleanup.log")
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8"):
                pass
            return path
        except OSError:
            continue
    return Path(tempfile.gettempdir()) / "auto-cleanup.log"


def _setup_logging() -> Path:
    path = _log_path()
    handlers: list[logging.Handler] = [logging.FileHandler(path, encoding="utf-8")]
    # Also log to stderr if a console happens to be attached (dev runs).
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )
    return path


def _free_port() -> int:
    """Ask the OS for an unused localhost port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(host: str, port: int) -> None:
    try:
        import uvicorn

        # Absolute import: under PyInstaller this module runs as __main__, so
        # a relative import would have no parent package.
        from cleanup.web.server import _build_app

        uvicorn.run(_build_app(), host=host, port=port, log_level="warning")
    except Exception:  # noqa: BLE001 - logged; console-less app must not die silently
        # The server runs in a background thread; log so a crash here is not
        # invisible (it would otherwise look like the app "did nothing").
        logger.error("server thread crashed:\n%s", traceback.format_exc())


def _wait_until_up(url: str, timeout: float = 20.0) -> bool:
    """Poll the local server until it answers or the timeout elapses."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):  # localhost only
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _run_in_browser(url: str) -> int:
    import webbrowser

    logger.info("opening in default browser: %s", url)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - logged; console-less app must not die silently
        logger.error("failed to open browser:\n%s", traceback.format_exc())
    print(f"{APP_TITLE} を起動しました: {url}", flush=True)
    print("このウィンドウ/プロセスを終了するとアプリも停止します。", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def _run_native_window(url: str) -> bool:
    """Try to show a native desktop window. Returns False if unavailable."""

    try:
        import webview  # pywebview
    except Exception:  # noqa: BLE001 - logged; console-less app must not die silently
        logger.info("pywebview not importable; using browser fallback")
        return False

    try:
        logger.info("opening native window: %s", url)
        webview.create_window(APP_TITLE, url, width=1000, height=720, min_size=(720, 520))
        webview.start()
        return True
    except Exception:  # noqa: BLE001 - logged; console-less app must not die silently
        # Missing WebView2 runtime / pythonnet backend, etc. Fall back.
        logger.error("native window failed, falling back to browser:\n%s", traceback.format_exc())
        return False


def main() -> int:
    log_path = _setup_logging()
    logger.info("=== %s starting (frozen=%s, pid=%s) ===", APP_TITLE, getattr(sys, "frozen", False), os.getpid())

    try:
        host, port = "127.0.0.1", _free_port()
        url = f"http://{host}:{port}/"

        server = threading.Thread(target=_serve, args=(host, port), daemon=True)
        server.start()

        if not _wait_until_up(url):
            logger.error("server did not come up at %s within timeout", url)
            print(f"起動に失敗しました。ログを確認してください: {log_path}", flush=True)
            return 1

        logger.info("server up at %s", url)

        # Prefer a native window; fall back to the browser if it is not
        # available on this machine.
        if _run_native_window(url):
            return 0
        return _run_in_browser(url)
    except Exception:  # noqa: BLE001 - logged; console-less app must not die silently
        logger.error("fatal startup error:\n%s", traceback.format_exc())
        print(f"起動中にエラーが発生しました。ログ: {log_path}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
