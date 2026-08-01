"""Launch the MaxPane dashboard: python -m maxpane_dashboard"""
import argparse
import logging
import os
import platform
import sys
import warnings

warnings.filterwarnings("ignore")

from maxpane_dashboard import __version__
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


#: Smallest accepted ``--poll-interval``.  Below this the flag stops being a
#: tuning knob and becomes a way to break the app (see :func:`_poll_interval`);
#: it is also the floor at which polling every public API stays polite.
_MIN_POLL_INTERVAL = 5


def _poll_interval(value: str) -> int:
    """Parse ``--poll-interval``, rejecting values that break the TUI.

    Every screen passes this straight to Textual's ``set_interval``, and
    non-positive intervals do not merely poll fast -- they break the timer:

    * ``0`` -> ``Timer._run`` computes ``int((now - start) / _interval + 1)``
      in its skip branch and raises ``ZeroDivisionError``.  The timer task
      dies unobserved, so the dashboard silently stops auto-refreshing after
      the initial fetch and the stored exception resurfaces as a traceback
      on exit.
    * negatives -> the same skip branch recomputes the identical count and
      ``continue``s with no ``await``, starving the asyncio event loop and
      freezing the whole UI.

    Both reproduced against Textual 8.1.1 (LOW-3).  Rejecting at the parser
    keeps the failure a one-line usage error instead of a frozen terminal.
    """
    try:
        seconds = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid int value: {value!r}"
        ) from None
    if seconds < _MIN_POLL_INTERVAL:
        raise argparse.ArgumentTypeError(
            f"must be at least {_MIN_POLL_INTERVAL} seconds (got {seconds}); "
            "values below that stop the refresh timer instead of speeding "
            "it up"
        )
    return seconds


def _version_text() -> str:
    """Build the ``--version`` banner.

    The interpreter line is not decoration.  ``pipx`` and ``uv`` both expose
    their shims from ``~/.local/bin`` and neither will overwrite a ``maxpane``
    it does not own -- the second installer warns and declines.  Whichever
    installed first therefore keeps the name, so a months-old build can go on
    answering to ``maxpane`` while a freshly installed one sits unreachable.
    That is indistinguishable from a broken release until you compare install
    directories by hand.  Naming the interpreter that is actually running
    makes it a one-command diagnosis.

    The first line stays exactly ``maxpane <version>`` so ``--version | head -1``
    remains machine-readable.
    """
    return (
        f"maxpane {__version__}\n"
        f"Python {platform.python_version()} ({sys.executable})"
    )


class _VersionAction(argparse.Action):
    """Print :func:`_version_text` verbatim on stdout, then exit 0.

    Not ``action="version"``: argparse runs that string through the help
    formatter's ``_fill_text``, which is ``textwrap.fill`` -- it collapses the
    newline and reflows both lines into one paragraph, so the interpreter path
    ends up glued to the version number.  The documented workaround is to swap
    the parser's ``formatter_class``, but that ties this flag's layout to how
    ``--help`` wraps its description; a later formatting change would silently
    re-break it.  Doing our own printing keeps the two independent.

    ``parser.exit(message=...)`` is also avoided deliberately -- it writes to
    *stderr*, which would break ``maxpane --version | head -1``.
    """

    def __init__(self, option_strings, dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS, help=None):
        super().__init__(
            option_strings=option_strings, dest=dest, default=default,
            nargs=0, help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        print(_version_text())
        parser.exit()


def main():
    parser = argparse.ArgumentParser(description="MaxPane Dashboard")
    # Declared first, and deliberately an ``action="version"``: argparse prints
    # and exits from inside ``parse_args()``, which is *before* main() sets up
    # logging.  That ordering matters -- ``logging.basicConfig`` below opens the
    # log with ``filemode="w"``, so a --version that ran any later would
    # silently truncate ~/.maxpane/maxpane.log every time someone checked which
    # build they had installed.
    parser.add_argument(
        "-V",
        "--version",
        action=_VersionAction,
        help="Show the version and the interpreter running it, then exit",
    )
    parser.add_argument(
        "--poll-interval",
        type=_poll_interval,
        default=30,
        help=f"Poll interval in seconds (default: 30, minimum: {_MIN_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--theme",
        default="matrix",
        choices=["matrix", "minimal", "bloomberg", "htop", "retro", "bakery", "frenpet", "base", "talismans", "fwa"],
    )
    # Only games that GameSelectScreen actually offers belong here. The three
    # FrenPet variants (frenpet_full / frenpet_wallet / frenpet_perf) are
    # commented out of screens/game_select.py's GAMES and out of
    # MaxPaneApp._GAME_CYCLE, and the menu always dismisses with a concrete
    # visible id -- so app.py's `if game_id is None: game_id = initial_game`
    # fallback never fires and those dashboards cannot be reached. Accepting
    # them here only bought a prefetch (including extra on-chain reward calls)
    # whose results were never displayed (MEDI-5). Re-add them here when the
    # views are re-enabled in GAMES.
    parser.add_argument(
        "--game",
        default="bakery",
        choices=["bakery", "frenpet", "base", "cattown", "ocm", "ttt", "talismans", "fwa"],
        help=(
            "Which game dashboard to preload (default: bakery). The game "
            "selection menu still appears at startup; this only warms that "
            "game's data first."
        ),
    )
    parser.add_argument(
        "--wallet",
        default=None,
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

    # Wallet: CLI flag > env var > saved config
    from maxpane_dashboard.config import get_wallet
    wallet = args.wallet or get_wallet()

    app = MaxPaneApp(
        poll_interval=args.poll_interval,
        theme=args.theme,
        initial_game=args.game,
        wallet_address=wallet,
    )
    app.run()


if __name__ == "__main__":
    main()
