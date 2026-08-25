"""Command line interface for zai2mihon."""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
import os
from pathlib import Path
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from zai2mihon import __version__
from zai2mihon.client import (
    DEFAULT_BASE_URL,
    KNOWN_DOMAINS,
    ZaiManhuaClient,
    normalize_base_url,
)
from zai2mihon.converter import (
    convert_json_file_to_backup,
    convert_zaimanhua_all_to_backup,
)
from zai2mihon.merger import merge_and_export_tachibk
from zai2mihon.models import (
    DEFAULT_ZAIMANHUA_SOURCE_ID,
    DEFAULT_ZAIMANHUA_SOURCE_NAME,
)
from zai2mihon.parser import clean_path, extract_token
from zai2mihon.proto.serializer import export_to_json, export_to_tachibk, read_tachibk

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(legacy_windows=False)


def generate_default_filename(extension: str = "tachibk") -> str:
    """Generate timestamped default backup filename."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"zaimanhua_backup_{timestamp}.{extension}"


def prompt_for_base_url(default_url: str = DEFAULT_BASE_URL) -> str:
    """Interactive prompt for choosing a domain preset or entering a custom domain."""
    console.print("\n请选择再漫画 API 域名 / 镜像站：")
    for idx, (domain, desc) in enumerate(KNOWN_DOMAINS, start=1):
        console.print(f"  [bold yellow]{idx}[/bold yellow]. {domain} ({desc})")
    custom_opt_idx = len(KNOWN_DOMAINS) + 1
    console.print(f"  [bold yellow]{custom_opt_idx}[/bold yellow]. 自定义输入其他域名\n")

    choices = [str(i) for i in range(1, custom_opt_idx + 1)]
    sel = Prompt.ask("请输入选项", choices=choices, default="1")

    sel_idx = int(sel) - 1
    if sel_idx < len(KNOWN_DOMAINS):
        chosen_url = KNOWN_DOMAINS[sel_idx][0]
    else:
        custom_input = Prompt.ask("请输入自定义域名 (如 https://i.zaimanhua.com)")
        chosen_url = custom_input.strip()

    return normalize_base_url(chosen_url)


def prompt_for_token(provided_token: Optional[str] = None) -> str:
    """Get token from provided arg, environment variable, or masked prompt."""
    token = provided_token or os.environ.get("ZAIMANHUA_TOKEN")
    if token:
        clean = extract_token(token)
        if clean:
            return clean

    token_input = Prompt.ask("请输入再漫画 JWT Token (或 Bearer Token)", password=True)
    clean = extract_token(token_input)
    if not clean:
        console.print("[red]错误: Token 不能为空。[/red]")
        sys.exit(1)
    return clean


def _run_export_pipeline(
    token: str,
    output: str,
    existing_backup: Optional[str] = None,
    category: Optional[str] = "再漫画",
    include_history: bool = True,
    history_only: bool = False,
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID,
    source_name: str = DEFAULT_ZAIMANHUA_SOURCE_NAME,
    base_url: str = DEFAULT_BASE_URL,
    proxy: Optional[str] = None,
    export_json_flag: bool = True,
) -> None:
    """Execute export or merge pipeline."""
    clean_tok = extract_token(token)
    if not clean_tok:
        console.print("[red]错误: Token 不能为空。[/red]")
        sys.exit(1)

    clean_base_url = normalize_base_url(base_url)
    out_clean = clean_path(output)
    output_path = Path(out_clean)

    exist_bk_path = Path(clean_path(existing_backup)) if existing_backup else None
    if exist_bk_path and not exist_bk_path.exists():
        console.print(f"[red]错误: 待合并的备份文件不存在: {exist_bk_path}[/red]")
        sys.exit(1)

    console.print(f"连接再漫画 API: {clean_base_url}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total} 条)"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        subscriptions = []
        reading_records = []

        with ZaiManhuaClient(token=clean_tok, base_url=clean_base_url, proxy=proxy) as client:
            # 1. Fetch subscriptions
            if not history_only:
                sub_task = progress.add_task("获取书架订阅...", total=100)

                def update_sub_progress(completed: int, total: int):
                    progress.update(sub_task, completed=completed, total=total)

                subscriptions = client.fetch_all_subscriptions(
                    progress_callback=update_sub_progress
                )
                console.print(f"[green]已获取 {len(subscriptions)} 本书架漫画[/green]")

            # 2. Fetch reading records
            if include_history:
                rec_task = progress.add_task("获取阅读历史...", total=100)

                def update_rec_progress(completed: int, total: int):
                    progress.update(rec_task, completed=completed, total=total)

                reading_records = client.fetch_all_reading_records(
                    progress_callback=update_rec_progress
                )
                console.print(f"[green]已获取 {len(reading_records)} 条阅读历史[/green]")

            # 3. Merge or Export
            if exist_bk_path:
                console.print(f"合并数据至现有备份: {exist_bk_path}")
                saved_tachibk, stats = merge_and_export_tachibk(
                    input_backup_path=exist_bk_path,
                    output_backup_path=output_path,
                    subscriptions=subscriptions,
                    reading_records=reading_records,
                    source_id=source_id,
                    category_name=category,
                )
                console.print(
                    Panel.fit(
                        f"[bold green]合并完成[/bold green]\n"
                        f"- 输出路径: {saved_tachibk.resolve()}\n"
                        f"- 标记已读章节数: {stats['chapters_marked_read']}\n"
                        f"- 更新收藏书架数: {stats['updated_favorites']}\n"
                        f"- 更新历史记录数: {stats['updated_history']}\n"
                        f"- 新增漫画条目数: {stats['new_manga_added']}",
                        title="合并统计",
                    )
                )
            else:
                backup = convert_zaimanhua_all_to_backup(
                    subscriptions=subscriptions,
                    reading_records=reading_records,
                    source_id=source_id,
                    source_name=source_name,
                    category_name=category,
                )
                saved_tachibk = export_to_tachibk(backup, output_path)
                console.print(f"[green]备份导出完成:[/green] {saved_tachibk.resolve()}")

                if export_json_flag:
                    json_output = output_path.with_suffix(".json")
                    export_to_json(backup, json_output)
                    console.print(f"[green]JSON 文件已保存:[/green] {json_output.resolve()}")

                cat_info = f", 分类: {category}" if category else " (无分类)"
                console.print(
                    Panel.fit(
                        f"[bold green]导出完成[/bold green]\n"
                        f"- 输出文件: {saved_tachibk.resolve()}\n"
                        f"- 漫画总数: {len(backup.backup_manga)} (书架收藏: {len(subscriptions)}, 阅读历史: {len(reading_records)})\n"
                        f"- 漫画源: {source_name} ({source_id}){cat_info}",
                        title="备份信息",
                    )
                )


def export_command(args: argparse.Namespace) -> None:
    """Handle export subcommand."""
    token = prompt_for_token(getattr(args, "token", None))
    include_hist = not args.no_include_history
    if args.history_only:
        include_hist = True

    _run_export_pipeline(
        token=token,
        output=args.output or generate_default_filename("tachibk"),
        existing_backup=getattr(args, "existing_backup", None),
        category=args.category,
        include_history=include_hist,
        history_only=args.history_only,
        source_id=args.source_id,
        source_name=args.source_name,
        base_url=args.base_url,
        proxy=args.proxy,
        export_json_flag=not args.no_export_json,
    )


def merge_command(args: argparse.Namespace) -> None:
    """Handle merge subcommand."""
    token = prompt_for_token(getattr(args, "token", None))
    _run_export_pipeline(
        token=token,
        output=args.output or f"{Path(clean_path(args.backup_file)).stem}_merged.tachibk",
        existing_backup=args.backup_file,
        category=args.category,
        include_history=True,
        history_only=False,
        source_id=args.source_id,
        source_name=args.source_name,
        base_url=args.base_url,
        proxy=args.proxy,
        export_json_flag=False,
    )


def convert_command(args: argparse.Namespace) -> None:
    """Handle convert subcommand for local JSON files."""
    in_clean = clean_path(args.input)
    out_clean = clean_path(args.output or Path(in_clean).with_suffix(".tachibk"))
    input_path = Path(in_clean)
    output_path = Path(out_clean)

    if not input_path.exists():
        console.print(f"[red]错误: 文件不存在: {input_path}[/red]")
        sys.exit(1)

    console.print(f"解析 JSON 文件: {input_path}")
    backup = convert_json_file_to_backup(
        input_path=input_path,
        source_id=args.source_id,
        source_name=args.source_name,
        category_name=args.category,
    )

    saved_path = export_to_tachibk(backup, output_path)
    console.print(f"[green]转换完成:[/green] {saved_path.resolve()}")


def inspect_command(args: argparse.Namespace) -> None:
    """Handle inspect subcommand to inspect existing .tachibk files."""
    file_path = Path(clean_path(args.file))
    if not file_path.exists():
        console.print(f"[red]错误: 文件不存在: {file_path}[/red]")
        sys.exit(1)

    backup_pb = read_tachibk(file_path)

    cats = [f"{c.name}" for c in backup_pb.backupCategories]
    sources = [f"{s.name or '未知'} ({s.sourceId})" for s in backup_pb.backupSources]
    favorites_count = sum(1 for m in backup_pb.backupManga if m.favorite)
    history_count = sum(1 for m in backup_pb.backupManga if len(m.history) > 0)

    console.print(
        Panel.fit(
            f"[bold]文件:[/bold] {file_path.name}\n"
            f"[bold]漫画总数:[/bold] {len(backup_pb.backupManga)}\n"
            f"[bold]书架收藏数:[/bold] {favorites_count}\n"
            f"[bold]阅读历史条目:[/bold] {history_count}\n"
            f"[bold]包含分类:[/bold] {', '.join(cats) if cats else '无'}\n"
            f"[bold]图源列表:[/bold] {', '.join(sources) if sources else '无'}",
            title="Mihon 备份信息",
        )
    )

    if backup_pb.backupManga:
        table = Table(title="漫画列表预览 (前 10 条)")
        table.add_column("标题", style="cyan", no_wrap=True)
        table.add_column("URL (ID)", style="magenta")
        table.add_column("图源 ID", style="green")
        table.add_column("历史记录", style="yellow")
        table.add_column("状态")

        for m in backup_pb.backupManga[:10]:
            h_info = f"{len(m.history)} 条记录" if m.history else "无"
            s_name = "连载中" if m.status == 1 else ("已完结" if m.status == 2 else str(m.status))
            table.add_row(
                m.title or "无标题",
                m.url,
                str(m.source),
                h_info,
                s_name,
            )

        console.print(table)


def interactive_wizard() -> None:
    """Interactive wizard for user-guided operation."""
    console.print(
        Panel.fit(
            "[bold]zai2mihon[/bold] - 再漫画转 Mihon 备份工具\n"
            "支持书架订阅与阅读历史导出为 Mihon (.tachibk) 格式",
            border_style="cyan",
        )
    )

    console.print("\n请选择操作方式：")
    console.print("  [bold yellow]1[/bold yellow]. 输入 Token 导出订阅 + 历史记录 (生成独立备份)")
    console.print("  [bold yellow]2[/bold yellow]. 仅导出订阅 (不含历史记录)")
    console.print("  [bold yellow]3[/bold yellow]. 仅导出阅读历史记录")
    console.print("  [bold yellow]4[/bold yellow]. 合并云端数据到现有 .tachibk 备份 (精准同步云端已读章节与历史)")
    console.print("  [bold yellow]5[/bold yellow]. 转换本地 JSON 文件")
    console.print("  [bold yellow]6[/bold yellow]. 检查已有的 .tachibk 备份文件")
    console.print("  [bold yellow]0[/bold yellow]. 退出\n")

    choice = Prompt.ask("请输入选项", choices=["0", "1", "2", "3", "4", "5", "6"], default="1")

    if choice == "0":
        console.print("已退出。")
        return

    if choice in ("1", "2", "3"):
        token_str = prompt_for_token()
        base_url_input = prompt_for_base_url()

        cat_prompt = Prompt.ask(
            "书架分类名称 (直接回车默认使用 '再漫画'，不设置分类请输入 'none')",
            default="再漫画",
        )

        out_name = Prompt.ask("输出文件名", default=generate_default_filename("tachibk"))

        proxy_input = None
        if Confirm.ask("是否需要配置网络代理 (如 HTTP / SOCKS5)?", default=False):
            proxy_input = Prompt.ask("请输入代理地址 (如 http://127.0.0.1:7890)").strip() or None

        include_hist = choice in ("1", "3")
        hist_only = choice == "3"

        _run_export_pipeline(
            token=token_str,
            output=out_name,
            existing_backup=None,
            category=cat_prompt,
            include_history=include_hist,
            history_only=hist_only,
            source_id=DEFAULT_ZAIMANHUA_SOURCE_ID,
            source_name=DEFAULT_ZAIMANHUA_SOURCE_NAME,
            base_url=base_url_input,
            proxy=proxy_input,
            export_json_flag=True,
        )

    elif choice == "4":
        token_str = prompt_for_token()

        bk_path_str = Prompt.ask("请输入现有 .tachibk 备份文件路径")
        if not bk_path_str.strip():
            console.print("[red]错误: 路径不能为空。[/red]")
            return

        base_url_input = prompt_for_base_url()

        cat_prompt = Prompt.ask(
            "书架分类名称 (直接回车默认使用 '再漫画'，不设置分类请输入 'none')",
            default="再漫画",
        )

        default_out = f"{Path(clean_path(bk_path_str)).stem}_merged.tachibk"
        out_name = Prompt.ask("合并后的输出文件名", default=default_out)

        proxy_input = None
        if Confirm.ask("是否需要配置网络代理 (如 HTTP / SOCKS5)?", default=False):
            proxy_input = Prompt.ask("请输入代理地址 (如 http://127.0.0.1:7890)").strip() or None

        _run_export_pipeline(
            token=token_str,
            output=out_name,
            existing_backup=bk_path_str,
            category=cat_prompt,
            include_history=True,
            history_only=False,
            source_id=DEFAULT_ZAIMANHUA_SOURCE_ID,
            source_name=DEFAULT_ZAIMANHUA_SOURCE_NAME,
            base_url=base_url_input,
            proxy=proxy_input,
            export_json_flag=False,
        )

    elif choice == "5":
        json_file = Prompt.ask("请输入 JSON 文件路径")
        if not json_file.strip():
            console.print("[red]错误: 文件路径不能为空。[/red]")
            return

        clean_in = clean_path(json_file)
        default_out = str(Path(clean_in).with_suffix(".tachibk"))
        out_name = Prompt.ask("输出文件名", default=default_out)

        cat_prompt = Prompt.ask(
            "书架分类名称 (直接回车默认使用 '再漫画'，不设置分类请输入 'none')",
            default="再漫画",
        )

        class Args:
            input = clean_in
            output = out_name
            source_id = DEFAULT_ZAIMANHUA_SOURCE_ID
            source_name = DEFAULT_ZAIMANHUA_SOURCE_NAME
            category = cat_prompt

        convert_command(Args())

    elif choice == "6":
        bk_file = Prompt.ask("请输入 .tachibk 备份文件路径")
        if not bk_file.strip():
            console.print("[red]错误: 文件路径不能为空。[/red]")
            return

        class Args:
            file = clean_path(bk_file)

        inspect_command(Args())


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with common options supported across subcommands."""
    common_p = argparse.ArgumentParser(add_help=False)
    common_p.add_argument(
        "--debug", action="store_true", help="启用调试模式并输出完整错误堆栈"
    )

    parser = argparse.ArgumentParser(
        prog="zai2mihon",
        description="导出再漫画书架和历史记录为 Mihon 备份格式 (.tachibk)",
        parents=[common_p],
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # export
    export_p = subparsers.add_parser("export", help="导出书架与历史记录", parents=[common_p])
    export_p.add_argument(
        "-t", "--token", help="再漫画 Token (也可通过环境变量 ZAIMANHUA_TOKEN 提供)"
    )
    export_p.add_argument("-o", "--output", help="输出 .tachibk 文件路径")
    export_p.add_argument(
        "-b", "--existing-backup", dest="existing_backup", help="待合并的现有 .tachibk 备份文件路径"
    )
    export_p.add_argument(
        "-c", "--category", default="再漫画", help="导入 Mihon 后的分类名 (传 none 禁用分类)"
    )
    export_p.add_argument(
        "--no-include-history", action="store_true", help="不包含阅读历史记录"
    )
    export_p.add_argument(
        "--history-only", action="store_true", help="仅导出阅读历史记录"
    )
    export_p.add_argument(
        "-s", "--source-id", type=int, default=DEFAULT_ZAIMANHUA_SOURCE_ID, help="图源 ID"
    )
    export_p.add_argument(
        "--source-name", default=DEFAULT_ZAIMANHUA_SOURCE_NAME, help="图源名称"
    )
    export_p.add_argument(
        "-u", "--base-url", "--url", default=DEFAULT_BASE_URL, help="再漫画 API 地址"
    )
    export_p.add_argument("--proxy", help="HTTP / SOCKS 代理地址")
    export_p.add_argument(
        "--no-export-json", action="store_true", help="不同时导出 JSON 格式备份"
    )

    # merge
    merge_p = subparsers.add_parser("merge", help="合并云端数据到现有 .tachibk 备份", parents=[common_p])
    merge_p.add_argument(
        "-t", "--token", help="再漫画 Token (也可通过环境变量 ZAIMANHUA_TOKEN 提供)"
    )
    merge_p.add_argument("-b", "--backup-file", required=True, help="现有的 .tachibk 备份文件路径")
    merge_p.add_argument("-o", "--output", help="输出文件路径")
    merge_p.add_argument(
        "-c", "--category", default="再漫画", help="分类名称 (传 none 禁用分类)"
    )
    merge_p.add_argument(
        "-s", "--source-id", type=int, default=DEFAULT_ZAIMANHUA_SOURCE_ID, help="图源 ID"
    )
    merge_p.add_argument(
        "--source-name", default=DEFAULT_ZAIMANHUA_SOURCE_NAME, help="图源名称"
    )
    merge_p.add_argument(
        "-u", "--base-url", "--url", default=DEFAULT_BASE_URL, help="再漫画 API 地址"
    )
    merge_p.add_argument("--proxy", help="HTTP / SOCKS 代理地址")

    # convert
    convert_p = subparsers.add_parser("convert", help="将本地 JSON 文件转为 .tachibk", parents=[common_p])
    convert_p.add_argument("input", help="输入的 JSON 文件路径")
    convert_p.add_argument("-o", "--output", help="输出的 .tachibk 路径")
    convert_p.add_argument(
        "-c", "--category", default="再漫画", help="分类名称 (传 none 禁用分类)"
    )
    convert_p.add_argument(
        "-s", "--source-id", type=int, default=DEFAULT_ZAIMANHUA_SOURCE_ID, help="图源 ID"
    )
    convert_p.add_argument(
        "--source-name", default=DEFAULT_ZAIMANHUA_SOURCE_NAME, help="图源名称"
    )

    # inspect
    inspect_p = subparsers.add_parser("inspect", help="查看 .tachibk 备份文件内容", parents=[common_p])
    inspect_p.add_argument("file", help="待查看的 .tachibk 文件路径")

    return parser


def main() -> None:
    """CLI Entrypoint with unified exception and debug handling."""
    debug_mode = "--debug" in sys.argv or os.environ.get("ZAIMANHUA_DEBUG") == "1"
    if debug_mode:
        logging.basicConfig(level=logging.DEBUG)

    try:
        if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "--debug"):
            interactive_wizard()
            return

        parser = build_parser()
        args = parser.parse_args()

        if getattr(args, "debug", False):
            debug_mode = True
            logging.basicConfig(level=logging.DEBUG)

        if args.command == "export":
            export_command(args)
        elif args.command == "merge":
            merge_command(args)
        elif args.command == "convert":
            convert_command(args)
        elif args.command == "inspect":
            inspect_command(args)
        else:
            parser.print_help()

    except KeyboardInterrupt:
        console.print("\n操作已取消。")
    except Exception as e:
        if debug_mode:
            console.print_exception()
        else:
            console.print(f"[red]执行出错: {e}[/red]")
            console.print("[dim]提示: 添加 --debug 参数可查看完整错误堆栈。[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
