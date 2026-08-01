#!/usr/bin/env python
"""Render the FWA dashboard headlessly against **live** data and print it.

A way to check a change without staring at a TUI: it drives the real screen
through Textual's headless harness at a chosen size and dumps what the
compositor actually produced -- the same source the screen tests assert
against, so a line that appears here is genuinely on screen rather than merely
present in some widget's content.

    .venv/bin/python scripts/fwa_preview.py                # 200x48, live data
    .venv/bin/python scripts/fwa_preview.py --size 140x42  # the narrow tier
    .venv/bin/python scripts/fwa_preview.py --cycles 3     # let sweeps land
    .venv/bin/python scripts/fwa_preview.py --json         # payload, not pixels

Two refresh cycles are the default because several things this dashboard shows
only exist on the *second* pass: the collection-name and ENS sweeps run
detached from the render, and the live ``surchargeBps`` is lifted from log
history by one cycle and consumed by the next one's sweep.

Hits the network. Nothing under ``tests/`` does -- this is a manual tool and
lives here for that reason (``scripts/`` is imported by nothing).

**Each run pays for a cold sweep.** The position sweep scans ~5,000 free-list
slots through keyless public endpoints and takes 60-90 s; the running app
amortises that behind its 60 s medium tier, but this script starts from
nothing every time. Several invocations back to back will get throttled, and a
throttled run renders the honest unavailable state -- which looks exactly like
a regression and is not one. If the boards come up empty, wait a minute rather
than re-running immediately, and prefer the real app for repeated looks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from textual.app import App  # noqa: E402

from maxpane_dashboard.data.fwa_manager import FWAManager  # noqa: E402
from maxpane_dashboard.screens.fwa import FWAScreen  # noqa: E402

_TCSS = (
    Path(__file__).resolve().parents[1]
    / "maxpane_dashboard" / "themes" / "minimal.tcss"
)


class _Harness(App):
    """Push a single FWAScreen, with the real stylesheet loaded."""

    CSS_PATH = str(_TCSS)

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x")
        return int(width), int(height)
    except Exception:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {value!r}")


async def _run(args) -> int:
    manager = FWAManager(poll_interval=30)

    # The screen does not retain the dict it renders, so capture it on the way
    # through rather than fetching a second time (which would double the load
    # and could legitimately return different numbers).
    captured: dict = {}
    _fetch = manager.fetch_and_compute

    async def _spy():
        data = await _fetch()
        captured.clear()
        captured.update(data or {})
        return data

    manager.fetch_and_compute = _spy  # type: ignore[method-assign]

    screen = FWAScreen(manager, poll_interval=30, name="fwa")
    app = _Harness(screen)

    try:
        async with app.run_test(size=args.size) as pilot:
            await pilot.pause()
            # The position sweep is single-flight: a sweep still running when
            # the next tick fires is *skipped*, not queued. A fixed cycle count
            # therefore renders an empty odds board roughly at random, which
            # reads as a regression rather than as timing. Keep refreshing
            # until a sweep actually publishes, bounded.
            for i in range(args.cycles):
                print(
                    f"[cycle {i + 1}/{args.cycles}] fetching…",
                    file=sys.stderr, flush=True,
                )
                await screen._do_refresh()
                await pilot.pause()
                # Let the detached name / floor sweeps finish so their results
                # are visible on the next cycle rather than the next launch.
                for attr in ("_floor_task", "_name_task"):
                    task = getattr(manager, attr, None)
                    if task is not None:
                        await asyncio.gather(task, return_exceptions=True)
                if captured.get("collection_odds") and not captured.get("odds_stale"):
                    print(
                        f"[cycle {i + 1}] sweep published — rendering",
                        file=sys.stderr, flush=True,
                    )
                    break
            else:
                if not captured.get("collection_odds"):
                    print(
                        "note: no sweep completed in "
                        f"{args.cycles} cycles — the odds and chase boards will "
                        "render their unavailable state. Retry with --cycles 4.",
                        file=sys.stderr, flush=True,
                    )
            payload = dict(captured)
            text = _screen_text(app)
    finally:
        await manager.close()

    if args.json:
        print(json.dumps(payload, indent=2, default=str, sort_keys=True))
        return 0

    print(text)
    print()
    print("-" * args.size[0])
    named = [
        r for r in (payload.get("collection_odds") or [])
        if not str(r.get("name", "")).startswith("0x")
    ]
    total = len(payload.get("collection_odds") or [])
    feed = payload.get("draw_events") or []
    ens_hits = [r for r in feed if r.get("purchaser_name")]
    print(
        f"named collections {len(named)}/{total} · "
        f"ENS in feed {len(ens_hits)}/{len(feed)} · "
        f"surchargeBps {manager._live_surcharge_bps} · "
        f"odds stale {payload.get('odds_stale')} · "
        f"errors {payload.get('error_count')}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--size", type=_size, default=(200, 48),
                        help="terminal size as WIDTHxHEIGHT (default 200x48)")
    parser.add_argument("--cycles", type=int, default=4,
                        help="max refresh cycles to wait for a sweep (default 4)")
    parser.add_argument("--json", action="store_true",
                        help="print the manager payload instead of the render")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), stream=sys.stderr)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
