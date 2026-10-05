"""Measure surf's SWARM (`s`), AGENT (`a`) and BOARD (`b`) bodies at given terminal sizes.

A thin CLI over ``_render()`` in ``tests/screens/test_surf_swarm_layout.py`` -- the same
composite, payloads and geometry checks the layout sweep certifies pins with, so a number read
here is the number the test will see: ``s`` and ``a`` are judged as ``_assert_whole`` judges
them, ``b`` by ``_assert_board_whole`` itself. Committed fixtures only: nothing touches the
network.

    .venv/bin/python scripts/measure_layout.py s capture 136:140x35
    .venv/bin/python scripts/measure_layout.py s worst-s 138x30:36 --expanded
    .venv/bin/python scripts/measure_layout.py a capture 130:150x33 --whole-from
    .venv/bin/python scripts/measure_layout.py b board-worst 140x40 --json

A size is ``WxH``; either side may be a range ``LO:HI`` (inclusive). Each size prints
``whole`` or what breaks it: marked panels (besides the body's named exceptions), CSS-clipped
lines, ``DataTable`` columns hidden behind a scroll, regions past their container, a lit
``‹ taller``, or a cropped status bar. ``--whole-from`` prints the smallest width (or height)
of the range from which every larger one is whole -- a measurement, never a pin: pins move
only through the terminal-layout skill's sweep.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.screens import test_surf_swarm_layout as layout  # noqa: E402

BOARD_KINDS = ("capture", "v4", "worst", "workers-unread", "contributors-unread", "unread")


def payloads() -> dict:
    """Every payload the layout test sweeps, by name; BOARD's carry a ``board-`` prefix."""
    out = dict(layout.PAYLOADS)
    out.update({f"board-{k}": (lambda k=k: layout._board_payload(k)) for k in BOARD_KINDS})
    return out


def parse_span(text: str) -> list[int]:
    lo, _, hi = text.partition(":")
    lo_i, hi_i = int(lo), int(hi or lo)
    if lo_i > hi_i:
        raise ValueError(f"empty range {text}")
    return list(range(lo_i, hi_i + 1))


def parse_size(text: str) -> tuple[list[int], list[int]]:
    w, sep, h = text.lower().partition("x")
    if not sep:
        raise ValueError(f"size must be WxH, got {text!r}")
    return parse_span(w), parse_span(h)


def problems(r: dict) -> list[str]:
    """What keeps one SWARM or AGENT composite from being whole; empty means whole.

    ``_assert_whole``'s four checks plus the region overflow and ``‹ taller`` the sweeps also
    assert. BOARD asks more of its LEADERBOARD: :func:`board_problems`."""
    out = []
    if not r["status_whole"]:
        out.append("status bar cropped")
    if r["marked_besides_exceptions"]:
        out.append(f"marked {sorted(r['marked_besides_exceptions'])}")
    if r["clipped"]:
        out.append(f"clipped {r['clipped']}")
    hidden = {k: v for k, v in r["hidden"].items() if v}
    if hidden:
        out.append(f"hidden columns {hidden}")
    if r["overflow"]:
        out.append(f"overflow {r['overflow']}")
    if r["taller"]:
        out.append("‹ taller lit")
    return out


def board_problems(r: dict, kind: str) -> list[str]:
    """What keeps one BOARD composite of payload *kind* from being whole; empty means whole.

    The verdict is ``_assert_board_whole``'s, called rather than restated: it excuses
    LEADERBOARD's marker on ``worst`` and also requires LEADERBOARD's ``full`` tier, its twelve
    columns and no clipped field beyond what *kind* allows. This only words the verdict."""
    out = [p for p in problems(r) if not p.startswith("marked")]
    try:
        layout._assert_board_whole(r, kind)
    except AssertionError:
        lb = "SurfSwarmLeaderboard"
        out.insert(0, f"not BOARD-whole: marked {sorted(r['marked_besides_exceptions'])}, "
                      f"LEADERBOARD tier {r['tiers'].get(lb)}, "
                      f"{len(r['columns'].get(lb, ()))} columns, "
                      f"clipped fields {sorted(r['clipped_fields'].get(lb, ()))}")
    return out


async def measure(key: str, payload_name: str, sizes: list[tuple[int, int]], *,
                  expanded: bool = False) -> list[dict]:
    build = payloads()[payload_name]
    rows = []
    for size in sizes:
        r = await layout._render(build(), size, key, expanded=expanded)
        found = (board_problems(r, payload_name.removeprefix("board-")) if key == "b"
                 else problems(r))
        rows.append({"size": size, "problems": found, "widths": r["widths"],
                     "heights": r["heights"], "tiers": r["tiers"]})
    return rows


def whole_from(rows: list[dict], axis: int) -> int | None:
    """The smallest value on *axis* from which every measured larger one is whole."""
    best = None
    for row in sorted(rows, key=lambda r: r["size"][axis], reverse=True):
        if row["problems"]:
            break
        best = row["size"][axis]
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("key", choices=("s", "a", "b"))
    parser.add_argument("payload", help="one of: " + ", ".join(payloads()))
    parser.add_argument("size", help="WxH, either side LO:HI")
    parser.add_argument("--expanded", action="store_true", help="press x: THROUGHPUT unfolded")
    parser.add_argument("--whole-from", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.payload not in payloads():
        parser.error(f"unknown payload {args.payload!r}")
    widths, heights = parse_size(args.size)
    if args.whole_from and len(widths) > 1 and len(heights) > 1:
        parser.error("--whole-from needs one fixed side")
    sizes = [(w, h) for w in widths for h in heights]

    rows = asyncio.run(measure(args.key, args.payload, sizes, expanded=args.expanded))
    if args.json:
        print(json.dumps(rows, default=list, indent=1))
    else:
        for row in rows:
            w, h = row["size"]
            print(f"{w}x{h}  " + ("whole" if not row["problems"] else "; ".join(row["problems"])))
    if args.whole_from:
        axis = 0 if len(widths) > 1 else 1
        found = whole_from(rows, axis)
        print(f"whole from {('width', 'height')[axis]} {found}" if found is not None
              else "not whole at the top of the range")
    return 0


if __name__ == "__main__":
    sys.exit(main())
