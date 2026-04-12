"""Launch the MaxPane dashboard: python -m maxpane_dashboard"""
import argparse
import logging
import os
import sys
import warnings

warnings.filterwarnings("ignore")

from maxpane_dashboard.app import MaxPaneApp


_DEFAULT_FONT_SIZE = 17


def _maximize_terminal() -> None:
    """Maximize the terminal window and set font size before launching the TUI."""
    term = os.environ.get("TERM_PROGRAM", "")
    if term == "iTerm.app":
        # Set font size via iTerm2 proprietary escape sequence
        sys.stdout.write(f"\033]1337;SetFontSize={_DEFAULT_FONT_SIZE}\a")
        sys.stdout.write("\033]1337;SetFullscreen=true\a")
        sys.stdout.flush()
    elif term == "Apple_Terminal":
        # Terminal.app: use AppleScript to set font size and maximize
        import subprocess
        subprocess.run(
            ["osascript", "-e",
             f'tell application "Terminal" to set font size of front window to {_DEFAULT_FONT_SIZE}'],
            capture_output=True,
        )
        sys.stdout.write("\033[9;1t")
        sys.stdout.flush()
    else:
        # Generic: just maximize
        sys.stdout.write("\033[9;1t")
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="MaxPane Dashboard")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Poll interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--theme",
        default="matrix",
        choices=["matrix", "minimal", "bloomberg", "htop", "retro", "bakery", "frenpet", "base"],
    )
    parser.add_argument(
        "--game",
        default="bakery",
        choices=["bakery", "frenpet", "base", "cattown", "ocm", "dota"],
        help="Which game dashboard to show first (default: bakery)",
    )
    parser.add_argument(
        "--wallet",
        default=os.environ.get("MAXPANE_WALLET", ""),
        help="Wallet address for FrenPet pet view",
        # TODO: make configurable via settings screen or config file
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    args = parser.parse_args()

    # Log to file to prevent warnings from bleeding into the TUI
    log_file = os.path.join(os.path.expanduser("~"), ".maxpane", "maxpane.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        filename=log_file,
        filemode="w",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("pydantic").setLevel(logging.ERROR)

    _maximize_terminal()

    app = MaxPaneApp(
        poll_interval=args.poll_interval,
        theme=args.theme,
        initial_game=args.game,
        wallet_address=args.wallet,
    )
    app.run()


if __name__ == "__main__":
    main()
