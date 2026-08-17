"""The seven-row signal rail for THE LIST (PRD §4).

``SETTLED · HOUR AT RISK · HOUR SAVED · WHALE · FARM · FORCED ETH · YOU`` —
the order is ``data/curator_models.SIGNAL_ROWS`` and it is an interface, not
a preference.  ``YOU`` is **last**, and last is the hazardous position: a
rail inside a fixed-height row loses its bottom row first (the FWA
coverage-badge bug), so the row carrying the reader's own standing is the
one that silently disappears.  All seven are pinned against the compositor
at the rail's real height.

State vocabulary
----------------

``sig_settled_state`` and ``sig_at_risk_state`` are the two rows whose colour
is a *judgement* rather than an observation, and they carry
``"ok" | "watch" | "fired" | None``.  ``None`` is unknown and renders the
unknown row — **never** ``ok``.  Colour is never the sole carrier: every
state also carries a glyph and a word, so the rail reads correctly in
greyscale.

What each row refuses to say
----------------------------

* **HOUR AT RISK** never goes blank during grace.  ``ethNeededThisHour()``
  answers ``0`` through the whole grace period, so "0 needed" there is not
  "safe", it is "not yet judged" — the row says ``n/a until hour N`` with N
  read from the payload (``first_judged_hour``), never from a literal 24.
* **HOUR SAVED** and **FORCED ETH** describe events that have never fired on
  chain and may never.  A permanently blank row is indistinguishable from a
  broken one, so both render an explicit never-fired state.  ``FORCED ETH``
  is the anomaly row: ``0`` is the healthy, expected reading and renders
  quietly as ``—``; anything nonzero is loud, and it is **forced** ETH — the
  contract refunds every deposit in-transaction, so its balance is never
  anyone's deposit and never a TVL.
* **FARM** is pattern language only.  ``fan-out`` describes the shape in the
  event data; ``sybil``/``fraud``/``cheat``/``attack`` are accusations this
  dashboard has no standing to make, and the contract's own docs delegate
  the analysis to consumers rather than asserting intent.
* **YOU** with every field ``None`` means no wallet is configured, not a
  wallet with no score.  ``rank --, 0 pts`` would be a claim about somebody;
  the honest render names the environment variable instead.

Width behaviour
---------------

Each row is a fixed head (glyph + padded label) and a value made of ``·``
separated parts.  The head never shrinks — it is the row's identity.  Parts
are dropped from the **end** when the value does not fit, and the title
grows ``‹ widen`` only when a row was left with nothing but its head, which
is the one loss a reader cannot see for themselves.

Primitives only — this module imports nothing from ``data/`` or ``analytics/``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import QueryError
from textual.widgets import Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_age,
    fmt_countdown,
    fmt_eth,
    fmt_pct,
    fmt_points,
    short_addr,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len

#: Panel title.  The hint is appended, never substituted.
SIGNALS_TITLE = "SIGNALS"

#: Marker appended when a row lost every part of its value.
WIDEN_HINT = "‹ widen"

#: The seven rows, in render order, keyed exactly as
#: ``data/curator_models.SIGNAL_ROWS`` spells them.  Widgets may not import
#: ``data/``, so the tuple is restated and
#: ``test_the_rail_renders_exactly_the_frozen_signal_rows`` asserts the two
#: agree.  There is deliberately no ``rescued`` row: ``rescued_total_eth``
#: renders **inside** FORCED ETH — forced in, swept out, one anomaly with two
#: numbers — rather than spending a row of a rail already one row from
#: clipping.
SIGNAL_KEYS = (
    "settled",
    "at_risk",
    "hour_saved",
    "whale",
    "clusters",
    "forced_eth",
    "you",
)

#: The rendered label per row, aligned 1:1 with :data:`SIGNAL_KEYS`.  These
#: are an interface — the screen tests assert these exact strings reach the
#: compositor — so importers use this tuple instead of retyping them, and
#: they are never shortened to save columns.
SIGNAL_LABELS = (
    "SETTLED",
    "HOUR AT RISK",
    "HOUR SAVED",
    "WHALE",
    "FARM",
    "FORCED ETH",
    "YOU",
)

#: The label cell, sized to the widest label the rail actually renders.  Not
#: a remembered width: ``max(len(...))`` over the tuple above, so a label
#: change cannot leave the cell one column short (the ``fwa clai`` defect).
LABEL_COLS = max(len(label) for label in SIGNAL_LABELS)

#: The three states the analytics layer may emit, plus ``None`` = unknown.
#: A fourth spelling is a silent fallback arm; asserted against
#: ``CURATOR_SIGNAL_STATES``.
SIGNAL_STATES = ("ok", "watch", "fired")

#: Glyph and style per state.  The glyph is what carries the state in
#: greyscale; the colour is redundant on purpose.
_STATE_STYLE = {
    "fired": ("▶", "bold $error"),
    "watch": ("◐", "$warning"),
    "ok": ("●", "$success"),
    None: ("●", "dim"),
}

#: Explicit never-fired / no-wallet copy, tested verbatim.
NEVER_SAVED = "none yet"
NO_WHALE = "none this hour"
NO_WALLET = "set MAXPANE_WALLET"
NO_CLUSTERS = "no fan-out patterns"

#: Head furniture: two leading spaces, the glyph, a space, the label cell and
#: the two-column gap before the value.
_HEAD_COLS = 2 + 1 + 1 + LABEL_COLS + 2


def _state_of(value) -> str | None:
    """The payload's state word, or ``None`` for unknown — never ``ok``."""
    text = str(value or "").strip().lower()
    return text if text in SIGNAL_STATES else None


def _head(label: str, state) -> str:
    glyph, style = _STATE_STYLE[_state_of(state)]
    return f"  [{style}]{glyph}[/] [{style}]{label:<{LABEL_COLS}}[/]"


def _row(label: str, state, parts: list[str], width: int) -> tuple[str, bool]:
    """``(markup, starved)`` — the head plus as many parts as fit.

    Parts are dropped from the end, because they are written
    most-important-first.  ``starved`` is True when *every* part had to go:
    that is the only loss the reader cannot infer from what is left, and it
    is what lights the title's marker.
    """
    head = _head(label, state)
    usable = [p for p in parts if p]
    if not usable:
        return head, False
    budget = width - _HEAD_COLS if width > 0 else 0
    kept = list(usable)
    if budget > 0:
        while kept and visible_len(" · ".join(kept)) > budget:
            kept.pop()
    if not kept:
        return head, True
    return f"{head}  {' · '.join(kept)}", False


# -- the seven builders --------------------------------------------------
#
# Each returns ``(state, parts)``.  ``parts`` are ordered most important
# first; everything in them is already escaped and already formatted.


def _settled_row(data: dict) -> tuple[str | None, list[str]]:
    settled = data.get("settled")
    state = _state_of(data.get("sig_settled_state"))
    if settled is True:
        hour = data.get("settled_hour")
        where = f"at hour {int(hour)}" if isinstance(hour, int) else ""
        return state or "fired", [f"[bold]list FROZEN[/] {where}".strip()]
    if settled is False:
        return state or "ok", ["list open"]
    # None: three states, and this is the third.  Never "ok".
    return None, [f"{DASH} unknown"]


def _at_risk_row(data: dict) -> tuple[str | None, list[str]]:
    phase = str(data.get("phase") or "").strip().lower()
    state = _state_of(data.get("sig_at_risk_state"))
    if phase == "settled":
        return state, ["game over"]
    if phase == "grace":
        first = data.get("first_judged_hour")
        hour = str(int(first)) if isinstance(first, int) else DASH
        # 0 needed during grace is REAL, and it is not "safe" -- the hour is
        # not judged yet.  Never blank, never green.
        return state, [f"n/a until hour {hour}"]
    needed = as_float(data.get("hour_needed_eth"))
    left = data.get("hour_seconds_left")
    if needed is None:
        return None, [f"{DASH} unknown"]
    if needed > 0:
        return state or "fired", [
            f"needs {fmt_eth(needed)} ETH",
            f"{fmt_countdown(left)} left",
        ]
    return state or "ok", ["hour is safe", f"{fmt_countdown(left)} left"]


def _hour_saved_row(data: dict) -> tuple[str | None, list[str]]:
    hour = data.get("last_saved_hour")
    if not isinstance(hour, int):
        # HourSaved has never fired on chain and may never; a blank row is
        # indistinguishable from a broken one.
        return "ok", [NEVER_SAVED]
    wallet = data.get("last_saved_wallet")
    parts = [f"hour {hour}"]
    if wallet:
        parts.append(f"by {safe_markup(short_addr(wallet))}")
    age = fmt_age(data.get("last_saved_age_s"))
    if age != DASH:
        parts.append(f"{age} ago")
    return "fired", parts


def _whale_row(data: dict) -> tuple[str | None, list[str]]:
    amount = as_float(data.get("whale_amount_eth"))
    if amount is None:
        return "ok", [NO_WHALE]
    parts = [f"[bold]{fmt_eth(amount)} ETH[/]"]
    wallet = data.get("whale_wallet")
    if wallet:
        parts.append(safe_markup(short_addr(wallet)))
    age = fmt_age(data.get("whale_age_s"))
    if age != DASH:
        parts.append(f"{age} ago")
    return "watch", parts


def _clusters_row(data: dict) -> tuple[str | None, list[str]]:
    count = data.get("clusters_count")
    if not isinstance(count, int):
        return None, [f"{DASH} unknown"]
    if count == 0:
        # A real, meaningful negative: the fold ran and found nothing.
        return "ok", [NO_CLUSTERS]
    share = fmt_pct(data.get("flagged_points_share_pct"))
    plural = "" if count == 1 else "s"
    parts = [f"{count} fan-out group{plural}"]
    if share != DASH:
        parts.append(f"{share} of points")
    return "watch", parts


def _forced_row(data: dict) -> tuple[str | None, list[str]]:
    forced = as_float(data.get("forced_eth"))
    rescued = as_float(data.get("rescued_total_eth"))
    if forced is None:
        return None, [f"{DASH} unknown"]
    if forced <= 0:
        # The healthy state, and the expected one: the contract refunds every
        # deposit in-transaction, so a zero balance is the normal reading.
        parts = [EMDASH]
        if rescued:
            parts.append(f"{fmt_eth(rescued)} ETH swept")
        return "ok", parts
    parts = [f"[bold]{fmt_eth(forced)} ETH forced in[/]"]
    if rescued:
        parts.append(f"{fmt_eth(rescued)} ETH swept")
    return "fired", parts


def _you_row(data: dict) -> tuple[str | None, list[str]]:
    keys = ("you_rank", "you_points", "you_credit_eth", "you_required_next_eth",
            "you_marginal_points")
    if all(data.get(key) is None for key in keys):
        # No wallet configured.  "rank --, 0 pts" would read as a wallet with
        # no score, which is a claim about somebody.
        return None, [NO_WALLET]
    rank = data.get("you_rank")
    parts = [f"rank {int(rank)}" if isinstance(rank, int) else f"rank {DASH}"]
    parts.append(f"{fmt_points(data.get('you_points'))} pts")
    credit = as_float(data.get("you_credit_eth"))
    if credit is not None:
        parts.append(f"{fmt_eth(credit)} credit")
    required = as_float(data.get("you_required_next_eth"))
    if required is not None:
        marginal = data.get("you_marginal_points")
        tail = f"next ≥ {fmt_eth(required)} ETH"
        if isinstance(marginal, int):
            tail += f" (+{marginal:,} pts)"
        parts.append(tail)
    return "ok", parts


_BUILDERS = {
    "settled": _settled_row,
    "at_risk": _at_risk_row,
    "hour_saved": _hour_saved_row,
    "whale": _whale_row,
    "clusters": _clusters_row,
    "forced_eth": _forced_row,
    "you": _you_row,
}


class CuratorSignals(Vertical):
    """The seven-row rail, ending in YOU."""

    DEFAULT_CSS = """
    CuratorSignals > .curator-signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorSignals > .curator-signals-row {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(
            SIGNALS_TITLE, classes="curator-signals-title", id="curator-sig-title"
        )
        yield Static("", classes="curator-signals-row", id="curator-sig-spacer")
        for key in SIGNAL_KEYS:
            yield Static(
                "", classes="curator-signals-row", id=f"curator-sig-{key}"
            )

    def update_data(
        self,
        phase=None,
        settled=None,
        settled_hour=None,
        sig_settled_state=None,
        sig_at_risk_state=None,
        first_judged_hour=None,
        hour_needed_eth=None,
        hour_seconds_left=None,
        last_saved_hour=None,
        last_saved_wallet=None,
        last_saved_age_s=None,
        whale_amount_eth=None,
        whale_wallet=None,
        whale_age_s=None,
        clusters_count=None,
        flagged_points_share_pct=None,
        forced_eth=None,
        rescued_total_eth=None,
        you_rank=None,
        you_points=None,
        you_credit_eth=None,
        you_required_next_eth=None,
        you_marginal_points=None,
        **_kwargs,
    ) -> None:
        """Refresh all seven rows from the flat ``CURATOR_KEYS`` payload."""
        self._payload = {
            "phase": phase,
            "settled": settled,
            "settled_hour": settled_hour,
            "sig_settled_state": sig_settled_state,
            "sig_at_risk_state": sig_at_risk_state,
            "first_judged_hour": first_judged_hour,
            "hour_needed_eth": hour_needed_eth,
            "hour_seconds_left": hour_seconds_left,
            "last_saved_hour": last_saved_hour,
            "last_saved_wallet": last_saved_wallet,
            "last_saved_age_s": last_saved_age_s,
            "whale_amount_eth": whale_amount_eth,
            "whale_wallet": whale_wallet,
            "whale_age_s": whale_age_s,
            "clusters_count": clusters_count,
            "flagged_points_share_pct": flagged_points_share_pct,
            "forced_eth": forced_eth,
            "rescued_total_eth": rescued_total_eth,
            "you_rank": you_rank,
            "you_points": you_points,
            "you_credit_eth": you_credit_eth,
            "you_required_next_eth": you_required_next_eth,
            "you_marginal_points": you_marginal_points,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-render so the dropped-part marker tracks the width.

        Gated on a payload: before the first fetch the rail must stay blank
        rather than render its never-fired copy.  ``HOUR SAVED — none yet``
        is a true statement about a payload whose ``last_saved_hour`` is
        ``None``; it is not a true statement about a dashboard that has not
        read anything yet.
        """
        if self._payload:
            self._render_view()

    # -- rendering ---------------------------------------------------------

    def _render_view(self) -> None:
        payload = self._payload
        width = max(self.content_size.width - 2, 0)
        starved = False

        for key, label in zip(SIGNAL_KEYS, SIGNAL_LABELS):
            try:
                state, parts = _BUILDERS[key](payload)
            except Exception:
                # One malformed value costs its row's value, never the rail.
                state, parts = None, [f"{DASH} unknown"]
            markup, row_starved = _row(label, state, parts, width)
            starved = starved or row_starved
            try:
                row = self.query_one(f"#curator-sig-{key}", Static)
            except QueryError:
                return  # not composed yet; none of the rows are
            try:
                row.update(markup)
            except Exception:
                # A per-row failure, never a rail-wide one: the head is built
                # entirely from this module's own strings and is always safe.
                try:
                    row.update(_head(label, None))
                except Exception:
                    pass

        try:
            title = self.query_one("#curator-sig-title", Static)
        except QueryError:
            return
        title.update(
            f"{SIGNALS_TITLE}  [yellow]{WIDEN_HINT}[/]" if starved else SIGNALS_TITLE
        )
