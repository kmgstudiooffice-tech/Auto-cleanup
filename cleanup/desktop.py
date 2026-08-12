"""Desktop entry point: run the app as a native GUI window (packaged .exe).

This starts the same FastAPI engine used by ``cleanup web`` on a private
localhost port, waits for it to come up, then shows it inside a native
desktop window via ``pywebview`` — so the packaged ``.exe`` looks and feels
like a normal desktop application rather than a browser tab.

If ``pywebview`` is unavailable, it falls back to opening the user's default
web browser at the same local URL.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request

APP_TITLE = "Auto-Cleanup"


def _free_port() -> int:
    """Ask the OS for an unused localhost port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(host: str, port: int) -> None:
    import uvicorn

    # Absolute import: under PyInstaller this module runs as __main__, so a
    # relative import would have no parent package.
    from cleanup.web.server import _build_app

    uvicorn.run(_build_app(), host=host, port=port, log_level="warning")


def _wait_until_up(url: str, timeout: float = 15.0) -> bool:
    """Poll the local server until it answers or the timeout elapses."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):  # localhost only
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> int:
    host, port = "127.0.0.1", _free_port()
    url = f"http://{host}:{port}/"

    # Run the server in a daemon thread so closing the window exits cleanly.
    server = threading.Thread(target=_serve, args=(host, port), daemon=True)
    server.start()

    if not _wait_until_up(url):
        print(f"サーバーの起動に失敗しました ({url})")
        return 1

    try:
        import webview  # pywebview
    except ImportError:
        # No native webview available: fall back to the default browser.
        import webbrowser

        print(f"{APP_TITLE} を起動しました: {url}", flush=True)
        print("終了するには Ctrl+C を押してください。", flush=True)
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0

    # Native desktop window. Closing it returns from webview.start().
    webview.create_window(APP_TITLE, url, width=1000, height=720, min_size=(720, 520))
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
