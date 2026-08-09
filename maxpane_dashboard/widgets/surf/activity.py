"""Recent transactions of both dev wallets, poisoning-defended.

One line per tx, newest first::

    08-07 04:23  ops           lp        NFPM  33.250 ETH
    08-07 04:21  ops           bridge    OFT endpoint
    07-17 04:12  ops           transfer  0x61CC704c…73f14E  8.000 ETH

``wallet_label`` is the producer's two-value vocabulary -- ``"dev"`` /
``"ops"``, from ``surf_client._DEV_WALLET_LABELS``, re-checked by the
manager against the address each label names.  It is deliberately *not* an
ENS name: the ENS spellings live in ``KNOWN_LABELS`` ("dev · surfsurf.eth"
/ "ops · frenpet.eth") and reach the user through the hero's ``owner ✓``
line.  This widget renders whatever string it is handed, so if the labels
should ever read as ENS names that is a change to the producer, not here.

Rendering rules (PRD §4, address-poisoning defense -- live spoofs of both
fee recipients exist in frenpet.eth's history today):

* ``counterparty_known`` truthy -> ``counterparty`` is a label from the
  vendored ``KNOWN_LABELS`` map, resolved upstream; rendered cyan.  The
  map itself lives in ``data/surf_addresses.py`` and is deliberately NOT
  imported here -- widgets receive primitives only.
* unknown -> dimmed ``0x`` + first 8 + ``…`` + last 6, never styled as
  trusted.  The window is wide enough to distinguish the live spoof pair
  (``0xF3084Bc7…D60eE6`` vs ``0xF3083828…f60Ee6``), which the classic
  first-6/last-4 short form is not.
* dust never renders: ``kind == "dust"`` rows are dropped outright, and a
  zero-value ``transfer`` from an unknown counterparty -- exactly the
  poisoning shape -- is dropped even if the manager's own filter missed
  it.  Defense in depth; the manager keys on tx sender (PRD §6.5), this
  widget keys on the rendered row.

``dev_activity=None`` -> explicit unavailable state; ``[]`` -> genuinely
quiet wallets.  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    hhmm,
    long_addr,
    mmdd,
)

#: Max rows rendered per refresh.
_MAX_ROWS = 25

#: The explicit degraded line.  Tested verbatim.
UNAVAILABLE_LINE = "activity unavailable"


def _row_markup(row) -> str | None:
    """Format one activity row; ``None`` drops it (malformed or poisonous)."""
    if not isinstance(row, dict):
        return None
    try:
        kind = str(row.get("kind") or "").strip().lower()
        if kind == "dust":
            return None
        known = bool(row.get("counterparty_known"))
        value = as_float(row.get("value_eth"))
        if kind == "transfer" and not known and not value:
            # Zero-value transfer from an unknown counterparty: the
            # address-poisoning shape.  Never rendered (PRD §4).
            return None

        stamp = f"{mmdd(row.get('ts'))} {hhmm(row.get('ts'))}"
        # Pad raw, escape after -- padding an escaped string misaligns it.
        wallet = safe_markup(f"{str(row.get('wallet_label') or DASH)[:12]:<12}")
        kind_cell = safe_markup(f"{(kind or DASH)[:8]:<8}")
        if known:
            who = f"[cyan]{safe_markup(str(row.get('counterparty') or DASH))}[/]"
        else:
            who = f"[dim]{safe_markup(long_addr(row.get('counterparty')))}[/]"
        amount = f"  {value:,.3f} ETH" if value else ""
        return f"{stamp}  [bold]{wallet}[/]  [dim]{kind_cell}[/]  {who}{amount}"
    except Exception:
        # A single malformed row must never take down the panel.
        return None


class SurfDevActivity(Vertical):
    """Feed of both dev wallets' recent transactions."""

    DEFAULT_CSS = """
    SurfDevActivity > .surf-activity-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfDevActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("DEV ACTIVITY", classes="surf-activity-title", id="surf-act-title")
        yield Static(" ", classes="surf-activity-spacer")
        yield RichLog(
            id="surf-activity-log",
            wrap=False,
            highlight=False,
            markup=True,
            max_lines=200,
        )

    def update_data(self, dev_activity=None, **_kwargs) -> None:
        """Rewrite the log.  ``dev_activity`` is the PRD §5 activity key."""
        try:
            log = self.query_one("#surf-activity-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False

        if dev_activity is None:
            log.write(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
            return

        try:
            rows = list(dev_activity)[:_MAX_ROWS]
        except TypeError:
            rows = []

        lines = [m for m in (_row_markup(row) for row in rows) if m is not None]
        if not lines:
            log.write("[dim]  no recent activity[/]")
            return
        for line in lines:
            log.write(line)
        self.call_after_refresh(log.scroll_home, animate=False)
