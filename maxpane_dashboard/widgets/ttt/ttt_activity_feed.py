"""Heterogeneous activity feed for the TTT dashboard.

Renders the last 25 events from ``cache.activity_log``, descending by
block.  Five event types are formatted with a per-type color tag:

* ``"burn"``    -> yellow BURN, with token symbol, the burn actor's
  address (full ``address_text``, copy icon included) and ``tokenId``.
* ``"swap"``    -> green BUY (positive ETH) or red SELL (negative ETH),
  with current buy-tax %.
* ``"fee"``     -> green FEE, with the 30% holder-pool share.
* ``"buyback"`` -> magenta BBACK, with bounty paid.  (The plan task
  refers to this as ``"bought"`` but the cache emits ``"buyback"``;
  both keys are accepted here.)
* ``"sale"``    -> cyan SALE, with the secondary-market price.

Every formatter is exception-safe: missing or malformed fields collapse
to dashes rather than crashing the RichLog write.  See WP3 schema in
``ttt_models.py::TTTActivityEvent`` for the dict shape.

A burn row is the one site in this module that displays a wallet address
(``actor_address``, the NFT burner); it is built as a ``rich.text.Text``
via ``address_text`` rather than a markup string, so the copy icon's click
meta survives ``RichLog``'s deferred markup parsing (``RichLog._make_renderable``
only parses ``str`` content -- a ``Text`` object passes straight through).
The other four event types render no address, so they build a markup
string and ``_event_to_text`` parses it here, inside this panel's own
guard.

The log, the write contract and the placeholder are
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed`'s (Branch 7,
WP-B); ``_event_to_text`` is this dashboard's ``format_row`` hook and the
``HH:MM`` cell is ``widgets/fmt.hhmm``.

**A stream, not a snapshot** (``SNAPSHOT`` stays ``False``): every row is
one thing that happened at a stated time -- a burn, a swap, a fee
deposit -- and it is still true when the next poll brings nothing.
Nothing in a row expires. A snapshot is the other kind (dota's hero
roster, whose every row carries an HP true only of the poll it came
from), and marking this feed one would mean re-painting it whole every
poll and telling ``[]`` apart from ``None``, a distinction an event log
does not have.

``dedupe_key`` returns ``None``: these events carry no key this panel
trusts to be unique, so every poll is all-new and redraws -- which is
what the copy this replaces did with its unconditional ``clear()``.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import DASH, hhmm, safe_get
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import RichLogFeed
from maxpane_dashboard.widgets.ttt._chain import EXPLORER

_WEI = 10**18

#: How many events one poll is allowed to paint. The log keeps 200 lines.
_ROW_CAP = 25

#: Display budget for the burn actor's address, excluding ICON_COLS (PRD
#: §5): no layout pin governs this RichLog (recipe step 6 does not apply --
#: there is nothing to grow into or shrink against), so this is a fresh,
#: deliberate choice rather than a preserved one. The former display showed
#: only the first 6 hex chars with no tail at all, which is a worse
#: anti-poisoning window than even the banned 6/4 shape (PRD §3.2 AMENDED).
#: 17 reproduces surf's `long_addr` anti-poisoning window (8 head / 6 tail).
_BURN_ACTOR_WIDTH = 17


# -- helpers -----------------------------------------------------------


def _sym(symbol) -> str:
    if symbol is None:
        return DASH
    s = str(symbol).strip()
    return safe_markup(s) if s else DASH


def _wei_to_eth(wei) -> float | None:
    try:
        return float(int(wei)) / _WEI
    except (TypeError, ValueError):
        return None


# -- per-type formatters ----------------------------------------------


def _fmt_burn(event: dict, ts: str, sym: str) -> Text:
    actor = safe_get(event, "actor_address")
    token_id = safe_get(event, "token_id")
    token_id_str = str(token_id) if token_id is not None else DASH
    line = Text.from_markup(f"{ts}  [yellow]BURN [/]  {sym:>6}  by ")
    line.append_text(address_text(actor, width=_BURN_ACTOR_WIDTH, explorer=EXPLORER))
    line.append(f"   tokenId {token_id_str}")
    return line


def _fmt_swap(event: dict, ts: str, sym: str) -> str:
    eth_amount = _wei_to_eth(safe_get(event, "eth_amount_wei", 0))
    extra = safe_get(event, "extra") or {}
    tax_pct = extra.get("tax_pct") if isinstance(extra, dict) else None

    if eth_amount is None:
        eth_str = DASH
        dir_color = "white"
    else:
        dir_color = "green" if eth_amount >= 0 else "red"
        eth_str = f"{eth_amount:+7.4f}"

    if tax_pct is None:
        tax_str = DASH
    else:
        try:
            tax_str = f"{float(tax_pct):.0f}"
        except (TypeError, ValueError):
            tax_str = DASH

    return (
        f"{ts}  [{dir_color}]SWAP [/]  {sym:>6}  "
        f"{eth_str} Ξ  tax {tax_str}%"
    )


def _fmt_fee(event: dict, ts: str, sym: str) -> str:
    eth_amount = _wei_to_eth(safe_get(event, "eth_amount_wei", 0))
    if eth_amount is None:
        eth_str = DASH
    else:
        eth_str = f"{eth_amount:.4f}"
    return f"{ts}  [green]FEE  [/]  {sym:>6}  {eth_str} Ξ → holders"


def _fmt_buyback(event: dict, ts: str, sym: str) -> str:
    extra = safe_get(event, "extra") or {}
    bounty_wei = extra.get("bounty_wei") if isinstance(extra, dict) else None
    if bounty_wei is None:
        # fall back to eth_amount_wei when bounty_wei isn't populated
        bounty = _wei_to_eth(safe_get(event, "eth_amount_wei", 0))
    else:
        bounty = _wei_to_eth(bounty_wei)
    if bounty is None:
        bounty_str = DASH
    else:
        bounty_str = f"{bounty:.5f}"
    return (
        f"{ts}  [magenta]BBACK[/]  {sym:>6}  "
        f"{bounty_str} Ξ bounty paid"
    )


def _fmt_sale(event: dict, ts: str) -> str:
    token_id = safe_get(event, "token_id")
    token_id_str = str(token_id) if token_id is not None else DASH
    extra = safe_get(event, "extra") or {}
    price_eth = extra.get("price_eth") if isinstance(extra, dict) else None
    if price_eth is None:
        # fallback to eth_amount_wei
        price = _wei_to_eth(safe_get(event, "eth_amount_wei", 0))
    else:
        try:
            price = float(price_eth)
        except (TypeError, ValueError):
            price = None
    if price is None:
        price_str = DASH
    else:
        price_str = f"{price:.4f}"
    return (
        f"{ts}  [cyan]SALE [/]  TTT     "
        f"#{token_id_str}  {price_str} Ξ"
    )


def _event_to_line(event: dict) -> str | Text | None:
    """Format one activity event; ``None`` to skip malformed input.

    A burn event returns a ``Text`` (its actor address carries the copy
    icon); every other event type returns a markup ``str``, which
    :func:`_event_to_text` parses before it reaches the log.
    """
    if not isinstance(event, dict):
        return None
    ts = hhmm(event.get("timestamp"))
    sym = _sym(event.get("token_symbol"))
    etype = (event.get("event_type") or "").lower()

    try:
        if etype == "burn":
            return _fmt_burn(event, ts, sym)
        if etype == "swap":
            return _fmt_swap(event, ts, sym)
        if etype == "fee":
            return _fmt_fee(event, ts, sym)
        if etype in ("buyback", "bought", "bback"):
            return _fmt_buyback(event, ts, sym)
        if etype == "sale":
            return _fmt_sale(event, ts)
    except Exception:
        # Never let a single malformed event take down the whole panel.
        return None
    # Unknown type -- render a generic dim row rather than skipping
    return f"{ts}  [dim]{etype.upper():>5}[/]  {sym:>6}  [dim]--[/]"


# -- widget ------------------------------------------------------------


def _event_to_text(event: dict) -> Text | None:
    """The ``format_row`` hook: one composited line, or ``None`` to skip.

    Always a ``Text``. A burn row already built one (its actor address
    carries the copy icon, whose click ``meta`` lives in a ``Style`` that
    markup parsing would flatten); the other four types build a markup
    string and it is parsed **here**, synchronously, so a malformed one
    lands in this panel's guard instead of the message pump.
    """
    line = _event_to_line(event)
    if line is None:
        return None
    if isinstance(line, Text):
        return line
    return Text.from_markup(line)


class TTTActivityFeed(RichLogFeed):
    """Auto-scrolling activity feed for TTT (last 25 events)."""

    TITLE = "ACTIVITY"

    LOG_ID = "ttt-activity-log"

    #: Columnar rows: a wrapped one would put a tokenId under a timestamp
    #: and the columns would stop being columns.
    WRAP = False

    #: The rows colour themselves by event type; Rich's repr highlighter
    #: would recolour the numbers on top of that.
    HIGHLIGHT = False

    MAX_LINES = 200

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this log's colours.
    DEFAULT_CSS = """
    TTTActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    format_row = staticmethod(_event_to_text)

    def dedupe_key(self, event: dict) -> None:
        """No key: every poll is all-new and redraws (see the module docstring)."""
        return None

    def update_data(
        self,
        activity_events=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log with the supplied events (descending order).

        Newest events appear at the top.
        """
        events = activity_events or []
        try:
            capped = list(events)[:_ROW_CAP]
        except TypeError:
            capped = []
        self.render_events(capped)
