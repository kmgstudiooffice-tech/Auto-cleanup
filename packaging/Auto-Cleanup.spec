# PyInstaller spec: builds a single-file Auto-Cleanup.exe (Windows GUI app).
#
# Build (on Windows):
#   pip install -e ".[web,desktop]" pyinstaller
#   pyinstaller packaging/Auto-Cleanup.spec
# The result is dist/Auto-Cleanup.exe
#
# This is also driven automatically by .github/workflows/build-windows.yml.

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("../cleanup/web/static", "cleanup/web/static")]
binaries = []
hiddenimports = []

# uvicorn/fastapi/pydantic/pywebview pull in modules dynamically; collect them
# so the frozen exe finds everything at runtime.
for pkg in ("uvicorn", "fastapi", "pydantic", "starlette", "anyio", "webview"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        # webview is optional; skip if not installed in the build env.
        pass

datas += collect_data_files("rich")


a = Analysis(
    ["../cleanup/desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["cleanup", "cleanup.web.server"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Auto-Cleanup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
