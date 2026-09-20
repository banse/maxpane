"""Activity feed for the Talismans dashboard.

Renders the most recent operations (newest-first) in a ``RichLog``.  Four
operation types are formatted with a per-type color tag:

* ``"bond"``   -> violet BOND  (forges a Mythic from two inputs).
* ``"cleave"`` -> cyan   CLEAVE.
* ``"cut"``    -> amber  CUT.
* ``"merge"``  -> green  MERGE.

Every formatter is exception-safe: missing or malformed fields collapse
to dashes rather than crashing the RichLog write.

The log, the write contract and the placeholder are
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed`'s (Branch 7, WP-B);
``_event_to_text`` below is this dashboard's ``format_row`` hook and the
``HH:MM`` cell is ``widgets/fmt.hhmm``.

**A stream, not a snapshot** (``SNAPSHOT`` stays ``False``): every row is
one operation that happened at a stated time, and a bond that was forged
an hour ago is still true when the next poll brings nothing. Nothing in a
row expires. A snapshot is the other kind -- dota's hero roster, where
every row carries an HP that is only true of the poll it came from -- and
marking this feed one would mean re-painting it whole every poll and
telling ``[]`` from ``None``, a distinction the operations log does not
have.

``dedupe_key`` returns ``None``: these events carry no key this panel
trusts to be unique, so every poll is treated as all-new and redraws --
which is exactly what the copy this replaces did with its unconditional
``clear()``.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.fmt import DASH, hhmm, safe_get
from maxpane_dashboard.widgets.panels import RichLogFeed

_OP_COLORS = {
    "bond": "#8a6fd6",
    "cleave": "cyan",
    "cut": "#f59e0b",
    "merge": "green",
}

#: How many operations the panel shows. The log itself keeps 200 lines;
#: this is what one poll is allowed to paint.
_ROW_CAP = 25


# -- helpers -----------------------------------------------------------


def _id_str(value) -> str:
    if value is None:
        return DASH
    try:
        return str(int(value))
    except (TypeError, ValueError):
        s = str(value).strip()
        return s if s else DASH


# -- per-type formatters ----------------------------------------------


def _fmt_bond(event: dict, ts: str) -> str:
    a = _id_str(safe_get(event, "token_id_a"))
    b = _id_str(safe_get(event, "token_id_b"))
    result = _id_str(safe_get(event, "result_id"))
    color = _OP_COLORS["bond"]
    return (
        f"{ts} [{color}]BOND  [/] #{a} + #{b} → #{result} · Mythic"
    )


def _fmt_cleave(event: dict, ts: str) -> str:
    a = _id_str(safe_get(event, "token_id_a"))
    result = _id_str(safe_get(event, "result_id"))
    color = _OP_COLORS["cleave"]
    return f"{ts} [{color}]CLEAVE[/] #{a} → #{result}"


def _fmt_cut(event: dict, ts: str) -> str:
    a = _id_str(safe_get(event, "token_id_a"))
    result = _id_str(safe_get(event, "result_id"))
    color = _OP_COLORS["cut"]
    return f"{ts} [{color}]CUT   [/] #{a} → #{result}"


def _fmt_merge(event: dict, ts: str) -> str:
    a = _id_str(safe_get(event, "token_id_a"))
    b = _id_str(safe_get(event, "token_id_b"))
    result = _id_str(safe_get(event, "result_id"))
    color = _OP_COLORS["merge"]
    return f"{ts} [{color}]MERGE [/] #{a} + #{b} → #{result}"


def _event_to_markup(event: dict) -> str | None:
    """Format one activity event; ``None`` to skip malformed input."""
    if not isinstance(event, dict):
        return None
    ts = hhmm(event.get("timestamp"))
    op_type = (event.get("op_type") or "").lower()

    try:
        if op_type == "bond":
            return _fmt_bond(event, ts)
        if op_type == "cleave":
            return _fmt_cleave(event, ts)
        if op_type == "cut":
            return _fmt_cut(event, ts)
        if op_type == "merge":
            return _fmt_merge(event, ts)
    except Exception:
        # Never let a single malformed event take down the whole panel.
        return None
    # Unknown type -- render a generic dim row rather than skipping.
    return f"{ts} [dim]{op_type.upper():<6}[/] [dim]--[/]"


def _event_to_text(event: dict) -> Text | None:
    """The ``format_row`` hook: one composited line, or ``None`` to skip.

    A ``Text``, never a markup string: ``RichLogFeed`` writes what this
    returns straight into the log, and parsing the markup *here* keeps a
    malformed row inside the panel's own guard instead of deferring it.
    """
    markup = _event_to_markup(event)
    if markup is None:
        return None
    return Text.from_markup(markup)


# -- widget ------------------------------------------------------------


class TalismansActivityFeed(RichLogFeed):
    """Auto-scrolling activity feed for Talismans operations."""

    TITLE = "ACTIVITY"

    LOG_ID = "tal-activity-log"

    #: Columnar rows: a wrapped one would put a result tokenId under the
    #: timestamp and the columns would stop being columns.
    WRAP = False

    #: The rows colour themselves by operation type; Rich's repr
    #: highlighter would recolour the tokenIds on top of that.
    HIGHLIGHT = False

    MAX_LINES = 200

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this log's colours.
    DEFAULT_CSS = """
    TalismansActivityFeed > RichLog {
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
        """Rewrite the log with the supplied events (newest-first)."""
        events = activity_events or []
        try:
            capped = list(events)[:_ROW_CAP]
        except TypeError:
            capped = []
        self.render_events(capped)
