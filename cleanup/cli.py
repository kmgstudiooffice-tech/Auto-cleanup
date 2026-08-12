"""Command-line interface for auto-cleanup.

Design goals:
  * ``scan`` never changes anything.
  * ``clean`` defaults to a dry-run; ``--apply`` is required to act, and
    even then files are quarantined (reversible), not deleted.
  * SAFE items can be bulk-approved; HIGH-risk items are confirmed one by
    one; apps are only ever printed as advice.
"""

from __future__ import annotations

import argparse
import sys

from .core import scanner
from .core.config import Config
from .core.executor import Executor
from .core.models import Action, Candidate, Category, RiskLevel, ScanResult, human_size

try:  # rich is optional; degrade to plain text if unavailable.
    from rich.console import Console
    from rich.table import Table
    _console = Console()
    _HAVE_RICH = True
except Exception:  # noqa: BLE001  # pragma: no cover - degrade to plain text
    _console = None
    _HAVE_RICH = False


def _print(msg: str = "") -> None:
    if _HAVE_RICH:
        _console.print(msg)
    else:
        print(_strip_markup(msg))


def _strip_markup(msg: str) -> str:
    import re

    return re.sub(r"\[/?[a-z0-9_ ]+\]", "", msg)


_CATEGORY_ALIASES = {
    "junk": Category.SYSTEM_JUNK,
    "winjunk": Category.WINDOWS_JUNK,
    "large": Category.LARGE_FILE,
    "duplicates": Category.DUPLICATE,
    "dupes": Category.DUPLICATE,
    "stale": Category.STALE_FILE,
    "apps": Category.UNUSED_APP,
    "largeapps": Category.LARGE_APP,
}


def _parse_categories(values: list[str] | None) -> list[Category] | None:
    if not values:
        return None
    out: list[Category] = []
    for v in values:
        cat = _CATEGORY_ALIASES.get(v.lower())
        if cat is None:
            raise SystemExit(f"unknown category: {v} (choose from {', '.join(_CATEGORY_ALIASES)})")
        out.append(cat)
    return out


def _render_scan(result: ScanResult) -> None:
    grouped = result.by_category()
    if not result.candidates:
        _print("[green]クリーンアップ候補は見つかりませんでした。[/green]")
        return

    for category, items in grouped.items():
        items_sorted = sorted(items, key=lambda c: c.size, reverse=True)
        subtotal = sum(c.size for c in items_sorted)
        _print(f"\n[bold]{category.label}[/bold]  ({len(items_sorted)} 件 / {human_size(subtotal)})")
        if _HAVE_RICH:
            table = Table(show_header=True, header_style="bold")
            table.add_column("リスク")
            table.add_column("サイズ", justify="right")
            table.add_column("パス")
            table.add_column("理由")
            for c in items_sorted[:50]:
                table.add_row(_risk_markup(c.risk), human_size(c.size), c.path, c.reason)
            _console.print(table)
            if len(items_sorted) > 50:
                _print(f"  … ほか {len(items_sorted) - 50} 件")
        else:
            for c in items_sorted[:50]:
                print(f"  [{c.risk.label}] {human_size(c.size):>10}  {c.path}  ({c.reason})")

    _print(f"\n[bold]合計回収可能サイズ: {human_size(result.total_size)}[/bold]")
    if result.errors:
        _print(f"[yellow]{len(result.errors)} 件のパスをスキップしました(権限など)。[/yellow]")


def _risk_markup(risk: RiskLevel) -> str:
    color = {RiskLevel.SAFE: "green", RiskLevel.LOW: "yellow", RiskLevel.HIGH: "red"}[risk]
    return f"[{color}]{risk.label}[/{color}]"


def _confirm(prompt: str, *, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


# -- commands ------------------------------------------------------------
def cmd_scan(args: argparse.Namespace) -> int:
    config = Config.load()
    result = scanner.scan(
        config,
        categories=_parse_categories(args.category),
        roots=args.path or None,
    )
    _render_scan(result)
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    config = Config.load()
    result = scanner.scan(
        config,
        categories=_parse_categories(args.category),
        roots=args.path or None,
    )
    if not result.candidates:
        _print("[green]クリーンアップ候補は見つかりませんでした。[/green]")
        return 0

    _render_scan(result)

    # Split by how they must be approved.
    apps = [c for c in result.candidates if c.action == Action.UNINSTALL]
    files = [c for c in result.candidates if c.action != Action.UNINSTALL]
    safe = [c for c in files if c.risk == RiskLevel.SAFE]
    low = [c for c in files if c.risk == RiskLevel.LOW]
    high = [c for c in files if c.risk == RiskLevel.HIGH]

    approved: list[Candidate] = []

    # SAFE + LOW: bulk approval with one prompt.
    bulk = safe + low
    if bulk:
        size = human_size(sum(c.size for c in bulk))
        _print(f"\n[bold]安全〜低リスク {len(bulk)} 件 ({size}) を隔離します。[/bold]")
        if _confirm("この一括処理を承認しますか?", assume_yes=args.yes):
            approved.extend(bulk)

    # HIGH: one confirmation each — never bulk-approved.
    if high:
        _print(f"\n[bold red]高リスク {len(high)} 件は個別に確認します（影響の可能性あり）。[/bold red]")
        for c in high:
            _print(f"  {human_size(c.size)}  {c.path}\n    理由: {c.reason}")
            if _confirm("  → これを隔離しますか?", assume_yes=False):
                approved.append(c)

    if apps:
        _print(f"\n[bold]未使用の可能性があるアプリ {len(apps)} 件（自動削除はしません）:[/bold]")
        for c in apps:
            _print(f"  {c.path}  — 削除するには: {c.uninstall_hint}")

    if not approved:
        _print("\n[yellow]承認された項目はありません。何も変更していません。[/yellow]")
        return 0

    dry_run = not args.apply
    executor = Executor(config, dry_run=dry_run)
    report = executor.execute(approved)

    if dry_run:
        _print(
            f"\n[bold](ドライラン)[/bold] {len(report.quarantined)} 件 / "
            f"{human_size(report.freed_bytes)} を隔離予定。実行するには --apply を付けてください。"
        )
    else:
        _print(
            f"\n[green]{len(report.quarantined)} 件 / {human_size(report.freed_bytes)} を隔離しました。[/green]"
        )
        if report.session_id:
            _print(f"復元するには: [bold]cleanup restore --session {report.session_id}[/bold]")
    if report.skipped:
        _print(f"[yellow]{len(report.skipped)} 件はスキップされました。[/yellow]")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    if args.session:
        restored, failed = Executor.restore(args.session)
        _print(f"[green]{len(restored)} 件を復元しました。[/green]")
        if failed:
            _print(f"[yellow]{len(failed)} 件は復元できませんでした。[/yellow]")
        return 0
    sessions = Executor.list_sessions()
    if not sessions:
        _print("復元可能な隔離セッションはありません。")
        return 0
    _print("隔離セッション:")
    for s in sessions:
        _print(f"  {s}")
    _print("\n復元: cleanup restore --session <ID>")
    return 0


def cmd_purge(args: argparse.Namespace) -> int:
    if not args.session:
        _print("--session <ID> を指定してください。")
        return 2
    if not _confirm(f"セッション {args.session} を完全に削除します（復元不可）。よろしいですか?", assume_yes=args.yes):
        _print("中止しました。")
        return 0
    Executor.purge(args.session)
    _print(f"[green]セッション {args.session} を完全に削除しました。[/green]")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from .core.config import CONFIG_PATH

    config = Config.load()
    for key, value in asdict(config).items():
        _print(f"  {key} = {value}")
    _print(f"\n設定ファイル: {CONFIG_PATH}")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    try:
        from .web.server import run
    except Exception as exc:  # noqa: BLE001  # pragma: no cover - missing web deps
        _print(f"[red]Web UI を起動できません: {exc}[/red]")
        _print("依存関係をインストールしてください: pip install 'auto-cleanup[web]'")
        return 1
    run(host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cleanup", description="安全なクロスOS自動クリーンアップ")
    sub = p.add_subparsers(dest="command", required=True)

    common_scan = argparse.ArgumentParser(add_help=False)
    common_scan.add_argument("--path", action="append", help="走査するディレクトリ(複数指定可)")
    common_scan.add_argument(
        "--category", action="append",
        help="対象カテゴリ: junk/large/duplicates/stale/apps(複数指定可)",
    )

    s_scan = sub.add_parser("scan", parents=[common_scan], help="候補を表示するだけ(削除しない)")
    s_scan.set_defaults(func=cmd_scan)

    s_clean = sub.add_parser("clean", parents=[common_scan], help="確認しながら隔離する")
    s_clean.add_argument("--apply", action="store_true", help="実際に実行(既定はドライラン)")
    s_clean.add_argument("--yes", action="store_true", help="安全〜低リスクの一括処理を自動承認(高リスクは常に確認)")
    s_clean.set_defaults(func=cmd_clean)

    s_restore = sub.add_parser("restore", help="隔離したファイルを復元する")
    s_restore.add_argument("--session", help="復元するセッションID")
    s_restore.set_defaults(func=cmd_restore)

    s_purge = sub.add_parser("purge", help="隔離セッションを完全削除(復元不可)")
    s_purge.add_argument("--session", help="削除するセッションID")
    s_purge.add_argument("--yes", action="store_true", help="確認を省略")
    s_purge.set_defaults(func=cmd_purge)

    s_config = sub.add_parser("config", help="現在の設定を表示")
    s_config.set_defaults(func=cmd_config)

    s_web = sub.add_parser("web", help="ローカルWeb UIを起動")
    s_web.add_argument("--host", default="127.0.0.1")
    s_web.add_argument("--port", type=int, default=8765)
    s_web.set_defaults(func=cmd_web)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
