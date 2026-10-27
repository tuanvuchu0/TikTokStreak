import asyncio
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parent)
if sys.path[0] != _src_dir:
    if _src_dir in sys.path:
        sys.path.remove(_src_dir)
    sys.path.insert(0, _src_dir)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich.console import Console
from rich.table import Table

from storage import (
    DEFAULT_MESSAGE,
    LOG_DIR,
    PROJECT_ROOT,
    RecipientExistsError,
    RecipientNotFoundError,
    add_recipient,
    initialize_storage,
    is_sent_today,
    list_recipients,
    load_recipients,
    load_settings,
    mark_as_sent,
    notify,
    remove_recipient,
    save_settings,
    set_recipient_message,
    update_recipient_user_id,
)
from tiktok import (
    get_user_id,
    login as login_browser,
    open_authenticated_page,
    send_direct_message,
)

VBS_FILENAME = "TikTokStreakSaver.vbs"
BAT_FILENAME = "TikTokStreakSaver.bat"
LOG_FILENAME = "autostart.log"


def get_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def get_vbs_path() -> Path:
    return get_startup_dir() / VBS_FILENAME


def get_bat_path() -> Path:
    return get_startup_dir() / BAT_FILENAME


def get_log_path() -> Path:
    return LOG_DIR / LOG_FILENAME


def is_autostart_enabled() -> bool:
    return get_vbs_path().exists() or get_bat_path().exists()


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    try:
        with open(get_log_path(), "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception:
        pass


def wait_for_network(timeout: int = 60, interval: int = 3) -> bool:
    start = time.time()
    targets = [
        ("www.tiktok.com", 443),
        ("1.1.1.1", 53),
        ("8.8.8.8", 53),
    ]
    while time.time() - start < timeout:
        for host, port in targets:
            try:
                with socket.create_connection((host, port), timeout=3):
                    return True
            except OSError:
                pass
        time.sleep(interval)
    return False


def run_startup_job(skip_delay: bool = False) -> int:
    write_log("[AUTOSTART] Windows startup job initiated.")

    settings = load_settings()
    delay = int(settings.get("autostart_delay", 15))
    if not skip_delay and delay > 0:
        write_log(f"[AUTOSTART] Waiting {delay}s for system startup initialization...")
        time.sleep(delay)

    write_log("[AUTOSTART] Checking network connection...")
    if not wait_for_network(timeout=60):
        write_log("[AUTOSTART] [ERROR] Network connection timed out after 60s. Aborting.")
        notify("TikTok Streak CLI", "Không thể gửi streak: Kết nối mạng quá hạn sau 60s.")
        return 1

    write_log("[AUTOSTART] Network is connected. Running streak-saver send...")

    python_exe = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    main_py = Path(__file__).resolve()

    recipients_count = len(load_recipients())
    timeout_seconds = max(300, recipients_count * 35 + 60)

    try:
        result = subprocess.run(
            [str(python_exe), str(main_py), "send"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
        )

        output = result.stdout.strip()
        if output:
            for line in output.splitlines():
                write_log(f"  {line}")

        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                write_log(f"  [STDERR] {line}")

        write_log(f"[AUTOSTART] Finished with exit code {result.returncode}.")
        return result.returncode
    except Exception as exc:
        write_log(f"[AUTOSTART] [EXCEPTION] Error executing send: {exc}")
        notify("TikTok Streak CLI", f"Lỗi khởi động tự động: {exc}")
        return 1


def enable_autostart(delay: int = 15, silent: bool = True) -> tuple[bool, Path]:
    startup_dir = get_startup_dir()
    startup_dir.mkdir(parents=True, exist_ok=True)

    disable_autostart()

    settings = load_settings()
    settings["autostart_enabled"] = True
    settings["autostart_delay"] = delay
    settings["autostart_silent"] = silent
    save_settings(settings)

    python_exe = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    main_py = Path(__file__).resolve()

    if silent:
        vbs_path = get_vbs_path()
        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run chr(34) & "{python_exe}" & chr(34) & " " & chr(34) & "{main_py}" & chr(34) & " autostart run", 0, False\n'
            'Set WshShell = Nothing\n'
        )
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        return True, vbs_path
    else:
        bat_path = get_bat_path()
        bat_content = (
            "@echo off\n"
            f'"{python_exe}" "{main_py}" autostart run\n'
        )
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        return True, bat_path


def disable_autostart() -> bool:
    vbs_path = get_vbs_path()
    bat_path = get_bat_path()
    removed = False

    if vbs_path.exists():
        try:
            vbs_path.unlink()
            removed = True
        except Exception:
            pass

    if bat_path.exists():
        try:
            bat_path.unlink()
            removed = True
        except Exception:
            pass

    settings = load_settings()
    if settings.get("autostart_enabled"):
        settings["autostart_enabled"] = False
        save_settings(settings)

    return removed


def get_recent_logs(lines: int = 15) -> list[str]:
    log_path = get_log_path()
    if not log_path.exists():
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return [line.rstrip() for line in all_lines[-lines:]]
    except Exception:
        return []


app = typer.Typer(
    name="streak-saver",
    help="Manage recipients and TikTok Streak CLI workflows.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

user_app = typer.Typer(help="Manage recipients list.")
app.add_typer(user_app, name="user")

autostart_app = typer.Typer(help="Manage automatic streak message sending on Windows startup.")
app.add_typer(autostart_app, name="autostart")

config_app = typer.Typer(
    help="Display or update settings.",
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(config_app, name="config")

console = Console()


@app.callback()
def main_callback() -> None:
    pass


@config_app.callback()
def config_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        initialize_storage()
        settings = load_settings()

        table = Table(title="Settings")
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        for key, value in settings.items():
            table.add_row(str(key), str(value))

        console.print(table)


@config_app.command("set-msg", help="Set the default streak message.")
def config_set_msg(
    message: str = typer.Argument(..., help="New default message to send."),
) -> None:
    initialize_storage()
    settings = load_settings()
    settings["default_message"] = message
    save_settings(settings)
    console.print(f"[green]Default message updated to: \"{message}\"[/green]")


@app.command(help="Log in to TikTok and save session for reuse.")
def login() -> None:
    initialize_storage()

    try:
        asyncio.run(login_browser())
    except KeyboardInterrupt:
        console.print("\n[yellow]Login stopped.[/yellow]")
    except Exception as exc:
        console.print(f"[red]Login failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc


async def resolve_user_id(username: str) -> str:
    playwright = None
    browser_instance = None
    context = None

    try:
        (
            playwright,
            browser_instance,
            context,
            page,
        ) = await open_authenticated_page(headless=True)

        return await get_user_id(page, username)

    finally:
        if context is not None:
            await context.close()

        if browser_instance is not None:
            await browser_instance.close()

        if playwright is not None:
            await playwright.stop()


@user_app.command("add", help="Add recipient by username and automatically resolve user ID.")
def user_add(
    username: str = typer.Argument(
        ...,
        help="TikTok username, with or without @.",
    ),
    user_id: str | None = typer.Option(
        None,
        "--user-id",
        help="TikTok numeric ID if providing manually.",
    ),
) -> None:
    initialize_storage()

    normalized_username = username.strip().lstrip("@")

    if not normalized_username:
        console.print("[red]Username cannot be empty.[/red]")
        raise typer.Exit(code=1)

    try:
        if user_id is None:
            console.print(
                f"Fetching user ID for @{normalized_username}..."
            )
            user_id = asyncio.run(
                resolve_user_id(normalized_username)
            )

        recipient = add_recipient(normalized_username, user_id)

    except (RecipientExistsError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(
            f"[red]Could not add @{normalized_username}: {exc}[/red]"
        )
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Added @{recipient.username}.[/green]")
    console.print(f"User ID: {recipient.user_id or '-'}")


@user_app.command("list", help="Display saved recipients.")
def user_list() -> None:
    initialize_storage()
    recipients = list_recipients()

    if not recipients:
        console.print(
            "Recipient list is empty. Use: streak-saver user add <username>"
        )
        raise typer.Exit()

    table = Table(title="TikTok recipients")
    table.add_column("Username", style="cyan")
    table.add_column("User ID")
    table.add_column("Message")
    table.add_column("Last sent")

    for item in recipients:
        msg_display = f'"{item.message}"' if item.message else "[dim]Default[/dim]"
        table.add_row(
            f"@{item.username}",
            item.user_id or "-",
            msg_display,
            item.last_sent_date or "-",
        )

    console.print(table)


@user_app.command("remove", help="Remove recipient from list.")
def user_remove(
    username: str = typer.Argument(..., help="Username to remove.")
) -> None:
    initialize_storage()

    try:
        removed = remove_recipient(username)
    except RecipientNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Removed @{removed.username}.[/green]")


@user_app.command("set-msg", help="Set a custom streak message for a specific recipient.")
def user_set_msg(
    username: str = typer.Argument(..., help="TikTok username."),
    message: str = typer.Argument(..., help="Custom message for this user."),
) -> None:
    initialize_storage()
    try:
        recipient = set_recipient_message(username, message)
        console.print(
            f"[green]Updated message for @{recipient.username}: \"{recipient.message}\"[/green]"
        )
    except RecipientNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@user_app.command("clear-msg", help="Clear custom message for a recipient (reverts to default message).")
def user_clear_msg(
    username: str = typer.Argument(..., help="TikTok username."),
) -> None:
    initialize_storage()
    try:
        recipient = set_recipient_message(username, None)
        console.print(
            f"[green]Cleared custom message for @{recipient.username}. Now using default message.[/green]"
        )
    except RecipientNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


async def _execute_send(
    targets: list,
    custom_message: str | None,
    default_msg: str,
) -> None:
    playwright = None
    browser_instance = None
    context = None
    page = None

    try:
        (
            playwright,
            browser_instance,
            context,
            page,
        ) = await open_authenticated_page(headless=True)

        success_count = 0
        fail_count = 0

        for index, recipient in enumerate(targets):
            user_id = recipient.user_id
            username = recipient.username

            if not user_id:
                console.print(f"Fetching user ID for @{username}...")
                try:
                    user_id = await get_user_id(page, username)
                    update_recipient_user_id(username, user_id)
                except Exception as exc:
                    console.print(
                        f"[red]Cannot get user ID for @{username}: {exc}[/red]"
                    )
                    fail_count += 1
                    continue

            msg_to_send = custom_message or recipient.message or default_msg
            console.print(
                f"[{index + 1}/{len(targets)}] Sending message to @{username}..."
            )

            try:
                await send_direct_message(page, user_id, msg_to_send)
                mark_as_sent(username)
                console.print(
                    f"[green]Sent message to @{username}: \"{msg_to_send}\"[/green]"
                )
                success_count += 1
            except Exception as exc:
                console.print(f"[red]Error sending to @{username}: {exc}[/red]")
                fail_count += 1

            if index < len(targets) - 1:
                await asyncio.sleep(2.5)

        console.print(
            f"\n[bold]Completed:[/bold] [green]{success_count} successful[/green], "
            f"[red]{fail_count} failed[/red]."
        )

        if fail_count == 0:
            notify(
                "TikTok Streak CLI",
                f"Đã gửi thành công {success_count}/{len(targets)} tin nhắn giữ streak.",
            )
        else:
            notify(
                "TikTok Streak CLI",
                f"Gửi streak hoàn tất: {success_count} thành công, {fail_count} thất bại.",
            )

    finally:
        if context is not None:
            await context.close()
        if browser_instance is not None:
            await browser_instance.close()
        if playwright is not None:
            await playwright.stop()


@app.command(help="Send streak messages to recipients.")
def send(
    username: str | None = typer.Option(
        None,
        "--user",
        "-u",
        help="Specific username to send to. Leave blank for all recipients.",
    ),
    message: str | None = typer.Option(
        None,
        "--message",
        "-m",
        help="Custom message content (defaults to configured message).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Send again even if already sent today.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Dry run: verify and display target recipients without opening browser.",
    ),
) -> None:
    initialize_storage()
    settings = load_settings()
    default_msg = settings.get("default_message", DEFAULT_MESSAGE)

    recipients = list_recipients()
    if not recipients:
        console.print(
            "[yellow]Recipient list is empty. Use: streak-saver user add <username>[/yellow]"
        )
        raise typer.Exit()

    if username is not None:
        target_name = username.strip().lstrip("@").casefold()
        targets = [r for r in recipients if r.username.casefold() == target_name]
        if not targets:
            console.print(
                f"[red]Could not find @{username} in recipients list.[/red]"
            )
            raise typer.Exit(code=1)
    else:
        targets = recipients

    if not targets:
        console.print("[yellow]Recipient list is empty.[/yellow]")
        raise typer.Exit()

    to_send = []
    skipped = []

    for item in targets:
        if not force and is_sent_today(item.last_sent_date):
            skipped.append(item)
        else:
            to_send.append(item)

    if skipped and not force:
        console.print(
            f"[dim]Skipped {len(skipped)} recipient(s) already sent today. (Use --force to resend)[/dim]"
        )

    if not to_send:
        console.print("[green]All recipients have already received a message today![/green]")
        raise typer.Exit()

    if dry_run:
        table = Table(title="Send list (Dry Run)")
        table.add_column("Username", style="cyan")
        table.add_column("User ID")
        table.add_column("Message")
        table.add_column("Last sent")
        for r in to_send:
            table.add_row(
                f"@{r.username}",
                r.user_id or "[italic red]Needs auto-fetch[/italic red]",
                message or r.message or default_msg,
                r.last_sent_date or "Never",
            )
        console.print(table)
        console.print(f"Total: {len(to_send)} recipient(s).")
        raise typer.Exit()

    try:
        asyncio.run(_execute_send(to_send, message, default_msg))
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        notify("TikTok Streak CLI", "Chưa đăng nhập TikTok! Vui lòng chạy 'streak-saver login'.")
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        console.print("\n[yellow]Canceled message sending.[/yellow]")
    except Exception as exc:
        console.print(f"[red]Execution error: {exc}[/red]")
        notify("TikTok Streak CLI", f"Lỗi gửi tin nhắn streak: {exc}")
        raise typer.Exit(code=1) from exc


@autostart_app.command("enable", help="Enable automatic sending on Windows startup.")
def autostart_enable(
    delay: int = typer.Option(
        15,
        "--delay",
        "-d",
        help="Delay in seconds before checking network and sending (default: 15s).",
    ),
    silent: bool = typer.Option(
        True,
        "--silent/--visible",
        help="Run silently in the background without popping up a console window.",
    ),
) -> None:
    initialize_storage()
    _, script_path = enable_autostart(delay=delay, silent=silent)
    console.print("Autostart on Windows startup has been [bold green]enabled[/bold green].")
    console.print(f"Startup script: {script_path}")
    console.print(f"Log file: {get_log_path()}")
    console.print(f"Startup delay: {delay}s")
    console.print(f"Silent mode: {'Yes' if silent else 'No'}")


@autostart_app.command("disable", help="Disable automatic sending on Windows startup.")
def autostart_disable() -> None:
    initialize_storage()
    disable_autostart()
    console.print("Autostart on Windows startup has been [bold yellow]disabled[/bold yellow].")


@autostart_app.command("status", help="Check Windows autostart status.")
def autostart_status() -> None:
    initialize_storage()
    enabled = is_autostart_enabled()
    settings = load_settings()

    if enabled:
        console.print("Status: [bold green]Enabled[/bold green]")
        script_path = get_vbs_path() if get_vbs_path().exists() else get_bat_path()
        console.print(f"Startup script: {script_path}")
        delay = settings.get("autostart_delay", 15)
        silent = settings.get("autostart_silent", True)
        console.print(f"Startup delay: {delay}s")
        console.print(f"Silent mode: {'Yes' if silent else 'No'}")
    else:
        console.print("Status: [bold yellow]Disabled[/bold yellow]")

    log_path = get_log_path()
    console.print(f"Log file: {log_path}")

    recent_logs = get_recent_logs(lines=10)
    if recent_logs:
        console.print("\n[bold]Recent autostart logs:[/bold]")
        for line in recent_logs:
            console.print(f"  [dim]{line}[/dim]")
    else:
        console.print("[dim]No autostart logs found yet.[/dim]")


@autostart_app.command("run", help="Run the startup job manually or via Windows startup.")
def autostart_run(
    skip_delay: bool = typer.Option(
        False,
        "--skip-delay",
        help="Skip the initial startup delay.",
    ),
) -> None:
    initialize_storage()
    code = run_startup_job(skip_delay=skip_delay)
    if code != 0:
        raise typer.Exit(code=code)


if __name__ == "__main__":
    app()
