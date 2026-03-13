from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config.loader import load_config
from .utils.logger import get_logger, setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor dostepnosci terminow na znany lekarz.pl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  run           Start the monitoring scheduler (default)
  --setup       First-time setup: opens browser with GUI to log in and save session
  --test-notify Send a test notification to all configured channels
        """,
    )
    parser.add_argument("command", nargs="?", default="run", choices=["run"], help="Command to execute")
    parser.add_argument("--setup", action="store_true", help="Run first-time setup (headful browser, save session)")
    parser.add_argument("--test-notify", action="store_true", help="Send a test notification")
    parser.add_argument("--config", default="config.toml", help="Path to config file (default: config.toml)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


async def run_setup(config_path: Path) -> None:
    from .browser.manager import BrowserManager
    from .config.loader import load_config
    from .config.models import BrowserConfig

    log = get_logger("setup")
    config = load_config(config_path)

    # Force headful mode for setup
    browser_config = BrowserConfig(**{**config.browser.model_dump(), "headless": False})
    manager = BrowserManager(browser_config)

    log.info("setup_start", msg="Opening browser for login. Please log in manually.")
    await manager.start()
    page = await manager.get_page()
    await page.goto("https://www.znanylekarz.pl/logowanie", wait_until="domcontentloaded")

    log.info("waiting_for_login", msg="Please log in in the browser window. Press Enter when done.")
    input("Press Enter after logging in...")

    session_path = Path("data/cookies/session.json")
    await manager.save_session(session_path)
    log.info("session_saved", path=str(session_path))

    await manager.stop()
    log.info("setup_complete", msg="Session saved. You can now run 'run' command.")


async def run_test_notify(config_path: Path) -> None:
    from .config.loader import load_config
    from .notifier.apprise_notifier import AppriseNotifier

    log = get_logger("test-notify")
    config = load_config(config_path)
    notifier = AppriseNotifier(config.notifications)
    await notifier.send_test()
    log.info("test_notify_done")


async def run_monitor(config_path: Path) -> None:
    import signal

    from .browser.manager import BrowserManager
    from .monitor.scheduler import MonitorScheduler
    from .monitor.session import SessionManager
    from .monitor.state_manager import StateManager
    from .notifier.apprise_notifier import AppriseNotifier
    from .scraper.login import LoginManager

    log = get_logger("monitor")
    config = load_config(config_path)

    manager = BrowserManager(config.browser)
    login_manager = LoginManager(config.login_email, config.login_password)
    session_manager = SessionManager(manager, login_manager)
    state_manager = StateManager()
    notifier = AppriseNotifier(config.notifications)

    log.info("browser_starting")
    await manager.start()

    scheduler: MonitorScheduler | None = None
    try:
        await session_manager.ensure_session()
        page = await manager.get_page()

        scheduler = MonitorScheduler(config, page, session_manager, state_manager, notifier)

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, scheduler.stop)

        log.info("monitor_starting", doctors=len(config.doctors))
        scheduler.start()
        await scheduler.wait_until_stopped()
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("shutdown_requested")
    finally:
        if scheduler:
            scheduler.stop()
        await manager.stop()
        log.info("monitor_stopped")


def main() -> None:
    args = parse_args()
    setup_logging(level=args.log_level)
    log = get_logger("main")
    config_path = Path(args.config)

    try:
        if args.setup:
            asyncio.run(run_setup(config_path))
        elif args.test_notify:
            asyncio.run(run_test_notify(config_path))
        else:
            asyncio.run(run_monitor(config_path))
    except FileNotFoundError as e:
        log.error("config_not_found", error=str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("shutdown", msg="Interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
