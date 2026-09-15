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
  the honest render names the way to fix it instead -- the screen's ``w`` key,
  and the environment variable that overrides whatever it saves.

Width behaviour
---------------

Each row is a fixed head (glyph + padded label) and a value made of ``·``
separated parts.  The head never shrinks — it is the row's identity.  Parts
are dropped from the **end** when the value does not fit, and the title
grows ``‹ widen`` whenever **any** part was dropped from **any** row: a
half-rendered row is not self-describing, and the widest row here is the one
carrying the reader's own next move.

The rail needs :data:`SIGNALS_FULL_WIDTH` columns to render every part of
every row **at every magnitude this contract can produce**, and
:func:`measure_signals_width` answers the narrower question — what it needs
for one payload in hand.  The two are different numbers and conflating them
is what this module got wrong twice; :data:`SIGNALS_FULL_WIDTH`'s own
docstring is the record.

HOUR SAVED and WHALE carry the only two addresses on this rail, and their
identity part is a real, clickable ``address_text`` rather than the
unclickable ``short_label`` string this module built until the copy-icon
conversion's own 2026-09-14 fix round (Task 3) — built by
:func:`_identity_row`, and measured by :func:`measure_signals_width`
through the exact same rendering path (:func:`_hour_saved_content` /
:func:`_whale_content`), so the published :data:`SIGNALS_FULL_WIDTH` counts
the icon.  It does not move: both rows sit 30+ columns under YOU, the
rail's actual binding row, in both the published worst case and the
captured payload, so the two extra icon columns never overtake it.

Primitives only — this module imports nothing from ``data/`` or ``analytics/``.
"""

from __future__ import annotations

import re

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import QueryError
from textual.widgets import Static

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.curator._fmt import (
    COMPACT_ETH_PROBE,
    DASH,
    EMDASH,
    NAME_COLS,
    as_float,
    fmt_age,
    fmt_countdown,
    fmt_eth,
    fmt_pct,
    fmt_points,
)
from maxpane_dashboard.widgets.curator.hero import PHASE_UNAVAILABLE, PHASES
from maxpane_dashboard.widgets.markup_safety import visible_len

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
#:
#: Unknown had ``●`` — the **same** glyph as ``ok`` — so on the two rows that
#: carry no "unknown" word (``at_risk`` during grace, and after settlement)
#: colour really was the sole carrier, which this module's docstring promises
#: it never is.  A hollow ``○`` is the honest one: unknown is the absence of
#: the reading ``ok`` asserts, and it now reads as that in greyscale.
_STATE_STYLE = {
    "fired": ("▶", "bold $error"),
    "watch": ("◐", "$warning"),
    "ok": ("●", "$success"),
    None: ("○", "dim"),
}

#: The unknown glyph, named so tests and the screen assert it rather than
#: retyping a character that is one code point from ``●``.
UNKNOWN_GLYPH = _STATE_STYLE[None][0]

#: The ``degraded`` group the HOUR SAVED, WHALE and FARM rows are folded from.
#:
#: Three of the seven rows read the deposit and ``HourSaved`` logs, and two of
#: them have no representable "read it, found nothing but a zero" value the way
#: FARM's ``clusters_count == 0`` does: ``last_saved_hour`` and
#: ``whale_amount_eth`` are ``None`` both when the chain is quiet and when the
#: pool is down.  So this row alone needs the health flag to tell the two
#: apart, and it is the only member of ``META_KEYS`` any widget receives.
#: Restated rather than imported from ``data/curator_models``'s
#: ``CURATOR_DEGRADED_GROUPS`` -- widgets may not import ``data/`` -- with the
#: agreement asserted in the suite.
LOGS_GROUP = "logs"

#: Explicit never-fired / no-wallet copy, tested verbatim.
NEVER_SAVED = "none yet"
NO_WHALE = "none this hour"
#: The no-wallet YOU row, in three parts so a narrow rail sheds the least
#: useful one first (parts drop from the end).
#:
#: The state comes first because it is what the row *is*; then the fix, which
#: says what the key does rather than only naming it -- ``press w`` alone told a
#: reader to press something without saying what it would set; then the
#: environment variable, which is last because it is the slowest fix and the
#: only one you cannot do from here.  It stays named at all because it
#: **overrides** the saved file, so it is what explains a wallet the reader did
#: not expect.
NO_WALLET_PARTS = (
    "no wallet set",
    "press w to set one",
    "or MAXPANE_WALLET",
)

#: The whole line, for the callers and tests that want one string.
NO_WALLET = " · ".join(NO_WALLET_PARTS)
NO_CLUSTERS = "no fan-out patterns"

#: Head furniture: two leading spaces, the glyph, a space, the label cell and
#: the two-column gap before the value.
_HEAD_COLS = 2 + 1 + 1 + LABEL_COLS + 2

#: The widest ETH magnitude any cell in this package is sized against, reused
#: rather than restated: ``_fmt`` documents why the tuple ends where it does.
#: The rail renders ETH through :func:`fmt_eth`, so this magnitude costs nine
#: columns here where ``fmt_eth_compact`` spends six.
_WIDEST_ETH = max(COMPACT_ETH_PROBE)

#: The highest score ``_curve`` can return on this deployment.
#:
#: A **ceiling the contract guarantees**, not a headroom guess: a wallet's
#: lifetime credit telescopes to at most ``creditCap`` (``_credit`` takes
#: ``min(amount, cap) - min(old, cap)``, so the ladder sums to
#: ``min(final high-water, cap)``), the early-bird multiplier tops out at 2×,
#: and ``_curve`` is ``isqrt(weight) * POINTS_PER_ETH / 1e9``.  With
#: ``creditCap == 1000e18`` and ``POINTS_PER_ETH == 1000`` that is
#: ``isqrt(2e21) * 1000 // 1e9``.  ``leaderboard._POINTS_COLS`` is sized from
#: the same ceiling; the suite asserts both against
#: ``analytics.curator_signals.points_for_weight``, since a widget may not
#: import it.
MAX_CURVE_POINTS = 44_721

# SIGNALS_FULL_WIDTH is defined at the foot of this module, because it is
# *derived* from WIDTH_PROBE through the seven builders rather than typed.
# Both live next to the builders they measure.


def _state_of(value) -> str | None:
    """The payload's state word, or ``None`` for unknown — never ``ok``."""
    text = str(value or "").strip().lower()
    return text if text in SIGNAL_STATES else None


def _head(label: str, state) -> str:
    glyph, style = _STATE_STYLE[_state_of(state)]
    return f"  [{style}]{glyph}[/] [{style}]{label:<{LABEL_COLS}}[/]"


#: ``_STATE_STYLE``'s three theme tokens, with a plain Rich colour name as
#: the last-resort fallback (the ``surf/pool4u_hero`` "$ trap": Rich's own
#: ``Text.from_markup`` -- unlike Textual's ``Content.from_markup``, which
#: ``Static.update(str)`` uses for the other five rows -- does not resolve a
#: ``$``-prefixed variable and raises ``MarkupError`` on it instead of
#: degrading).  Used only by :func:`_identity_row`'s two callers: HOUR SAVED
#: and WHALE are the two rows this dashboard's copy-icon conversion (Task 3)
#: builds as a real ``Text`` rather than handing ``Static`` a markup string.
_TOKEN_FALLBACK = {"error": "red", "warning": "yellow", "success": "green"}


#: A whole ``$token``: hyphens belong to the name, so ``$success-darken-2`` is
#: one token and never ``$success`` followed by ``-darken-2``.
_TOKEN_RE = re.compile(r"\$([A-Za-z_][\w-]*)")


def _resolved_markup(markup: str, colors: dict[str, str] | None) -> str:
    """*markup* with ``$token`` references swapped for concrete colours.

    Matched as whole tokens: a plain ``str.replace("$success", …)`` turned
    ``$success-darken-2`` into ``green-darken-2``, which is no colour at all.
    A token the app's current theme defines takes that colour; one of
    :data:`_TOKEN_FALLBACK`'s three takes its fallback name (before the first
    mount, or a bare harness with no theme wired); any other is left as it
    was."""

    def swap(match: re.Match) -> str:
        name = match.group(1)
        if colors and name in colors:
            return colors[name]
        return _TOKEN_FALLBACK.get(name, match.group(0))

    return _TOKEN_RE.sub(swap, markup)


def _row(label: str, state, parts: list[str], width: int) -> tuple[str, bool]:
    """``(markup, starved)`` — the head plus as many parts as fit.

    Parts are dropped from the end, because they are written
    most-important-first.  ``starved`` is True when **any** part had to go.

    It used to be "when *every* part had to go", on the reasoning that a
    half-row is legible on its own.  It is not: the YOU row's last part is
    ``next ≥ 4.10 ETH (+120 pts)``, the only actionable number the rail
    carries, and between 76 and 81 columns it vanished with the title still
    reading a clean ``SIGNALS``.  A partially amputated row is
    indistinguishable from a wallet the manager has no ``requiredNext`` for,
    which is the exact confusion every explicit state in this package exists
    to prevent — and a width sweep cannot catch it, because the rail "fits"
    by amputating itself.
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
    return f"{head}  {' · '.join(kept)}", len(kept) < len(usable)


#: Which payload fields carry the wallet/name pair behind HOUR SAVED's and
#: WHALE's identity part -- the two rows this dashboard's copy-icon
#: conversion (Task 3) gives a real, clickable ``address_text`` instead of
#: an unclickable ``short_label`` string.  Keyed by :data:`SIGNAL_KEYS` entry
#: so :func:`_identity_row` can be called generically from the render loop.
_IDENTITY_FIELDS = {
    "hour_saved": ("last_saved_wallet", "last_saved_ens"),
    "whale": ("whale_wallet", "whale_ens"),
}


def _fit_costed(items: list[tuple[object, int]], width: int) -> tuple[list[object], bool]:
    """:func:`_row`'s drop-from-the-end algorithm, generalised over a
    ``(content, cost)`` pair instead of a bare string.

    ``cost`` lets a caller mix a plain markup string's :func:`visible_len`
    with a pre-built :class:`~rich.text.Text` fragment's own ``cell_len``
    (the identity part, its copy icon included) in the same budget, so the
    part that carries the icon can still be the one dropped first under
    width pressure -- exactly what happened to it as a string before this
    function existed.
    """
    usable = [(c, n) for c, n in items if c]
    if not usable:
        return [], False
    budget = width - _HEAD_COLS if width > 0 else 0
    kept = list(usable)
    if budget > 0:
        def total(rows: list[tuple[object, int]]) -> int:
            return sum(n for _c, n in rows) + 3 * (len(rows) - 1) if rows else 0
        while kept and total(kept) > budget:
            kept.pop()
    return [c for c, _n in kept], len(kept) < len(usable)


def _identity_row(
    label: str, state, lead: list[str], wallet, name, trail: list[str], width: int,
    colors: dict[str, str] | None = None,
) -> tuple[Text, bool]:
    """Like :func:`_row`, but the identity part is a real ``address_text``
    with its own copy icon, dropped from the middle exactly like any other
    part rather than kept as an unclickable ``short_label`` string.

    ``lead``/``trail`` are the parts either side of the identity in the
    builder's own order (``hour``/the amount before it, the age after), so
    the existing drop-from-the-end rule still drops age first and the
    identity next -- unchanged from when the identity was baked into
    ``_hour_saved_row``/``_whale_row``'s own ``parts`` string.

    :func:`measure_signals_width` (and therefore :data:`SIGNALS_FULL_WIDTH`)
    measures exactly this render path (via :func:`_hour_saved_content` /
    :func:`_whale_content`), icon included, since the fix round that closed
    the gap where it measured the old ``short_label`` string instead and
    silently under-counted these two rows by :data:`ICON_COLS`.  The two
    rows this touches are nowhere near that panel's binding row (YOU, the
    widest by 30+ columns in both the worst-case probe and the captured
    payload -- see task-3-report.md), so the published width does not
    actually move even though the measurement now counts the icon.
    """
    items: list[tuple[object, int]] = [(p, visible_len(p)) for p in lead if p]
    if wallet:
        # Lower-cased on purpose, ``leaderboard.py``'s own reason: two
        # sources spell one wallet two ways, and the icon copies whichever
        # spelling this cell was given -- lower-case is an equally valid
        # paste of the same address.
        lowered = wallet.lower() if isinstance(wallet, str) else wallet
        # No colour, on purpose -- reverted in fix round 3. Round 2's own
        # "gap-close" (item 5) painted this identity success green,
        # matching every other converted identity cell's convention, but
        # that convention never applied here: before this task,
        # `f"by {safe_markup(short_label(...))}"` and
        # `safe_markup(short_label(...))` (the pre-Task-3 shape this
        # identity replaces) were never colour-wrapped, so the default
        # foreground is the restoration, not a regression to fix. Success
        # green here would be a new visual design on the rail (a fired row
        # would read: red glyph, default "hour 26", green address, default
        # "12m ago") that the owner never approved -- the same shape as
        # the reverted three-sided list-hero card. The `colors` parameter
        # stays (still used by `_resolved_markup` for the head), unused
        # here now.
        identity = address_text(lowered, label=(name or None), width=NAME_COLS)
        items.append((identity, identity.cell_len))
    items.extend((p, visible_len(p)) for p in trail if p)

    head = _resolved_markup(_head(label, state), colors)
    kept, starved = _fit_costed(items, width)
    out = Text.from_markup(head)
    if not kept:
        return out, starved
    out.append("  ")
    for index, content in enumerate(kept):
        if index:
            out.append(" · ")
        if isinstance(content, Text):
            out.append_text(content)
        else:
            out.append_text(Text.from_markup(content))
    return out, starved


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
    if phase not in PHASES:
        # The arm this row was missing.  ``phase`` is None whenever
        # ``isSettled()`` or the ``once`` tier failed, and the judged branch
        # below reads ``ethNeededThisHour()``, which answers **0** all the
        # way through grace -- so falling through to it rendered a green
        # "hour is safe" for an hour nobody has judged.  The analytics layer
        # answers ``(None, "phase unavailable")`` on the same input; the
        # widget now agrees with it instead of contradicting it.
        return None, [PHASE_UNAVAILABLE]
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


def _logs_are_dead(data: dict) -> bool:
    """Is the group these rows are folded from in ``degraded``?

    ``"logs"`` is restated here rather than imported: a widget may not import
    ``data/``, where ``CURATOR_DEGRADED_GROUPS`` is frozen, and the agreement
    lives in the suite -- the ``MAX_BLOCK_SPAN`` pattern one module over.
    """
    groups = data.get("degraded")
    return isinstance(groups, (list, tuple, set, frozenset)) and LOGS_GROUP in groups


def _hour_saved_row(data: dict) -> tuple[str | None, list[str]]:
    hour = data.get("last_saved_hour")
    if not isinstance(hour, int):
        if _logs_are_dead(data):
            # The read did not happen, so "never" is a claim nobody measured.
            # FARM is fed by the same group and has always said this; these two
            # rows used to disagree with it in green.
            return None, [f"{DASH} unknown"]
        # HourSaved has never fired on chain and may never; a blank row is
        # indistinguishable from a broken one.
        return "ok", [NEVER_SAVED]
    # The identity part is never built here any more (it used to be
    # ``by {short_label(...)}``): ``parts`` is only ever read by
    # :func:`_hour_saved_content` in its *no-wallet* branch, where there was
    # never an identity to add, so building one here was always dead once
    # a wallet is present -- the icon-carrying identity is built directly
    # by :func:`_identity_row` instead.
    parts = [f"hour {hour}"]
    age = fmt_age(data.get("last_saved_age_s"))
    if age != DASH:
        parts.append(f"{age} ago")
    return "fired", parts


def _whale_row(data: dict) -> tuple[str | None, list[str]]:
    amount = as_float(data.get("whale_amount_eth"))
    if amount is None:
        if _logs_are_dead(data):
            # "no whale in the last five minutes" is a statement about the
            # deposit log.  With that pool down we did not look, and last-good
            # events are older than the window the row is about.
            return None, [f"{DASH} unknown"]
        return "ok", [NO_WHALE]
    # See `_hour_saved_row`'s own note: the identity part is never built
    # here -- `_identity_row` builds the icon-carrying one directly.
    parts = [f"[bold]{fmt_eth(amount)} ETH[/]"]
    age = fmt_age(data.get("whale_age_s"))
    if age != DASH:
        parts.append(f"{age} ago")
    return "watch", parts


def _hour_saved_content(
    label: str, data: dict, width: int, colors: dict[str, str] | None = None,
) -> tuple[Text, bool]:
    """:func:`_hour_saved_row`'s row, rendered with a real, clickable
    identity (:func:`_identity_row`) instead of a ``short_label`` string.

    This is also :func:`measure_signals_width`'s own measurement path for
    this row now, so the identity's icon counts toward
    :data:`SIGNALS_FULL_WIDTH`.  The lead/trail parts are restated here
    rather than threaded out of ``_hour_saved_row``'s own ``parts`` list,
    because building the identity there would still leave the *no-wallet*
    branch's plain-string ``parts`` (used below) needing the same shape
    either way; see :func:`_identity_row`'s own docstring for the rest.
    """
    state, parts = _hour_saved_row(data)
    hour = data.get("last_saved_hour")
    wallet = data.get("last_saved_wallet") if isinstance(hour, int) else None
    if not wallet:
        markup, starved = _row(label, state, parts, width)
        return Text.from_markup(_resolved_markup(markup, colors)), starved
    age = fmt_age(data.get("last_saved_age_s"))
    return _identity_row(
        label, state, [f"hour {hour}"], wallet, data.get("last_saved_ens"),
        [f"{age} ago"] if age != DASH else [], width, colors,
    )


def _whale_content(
    label: str, data: dict, width: int, colors: dict[str, str] | None = None,
) -> tuple[Text, bool]:
    """:func:`_whale_row`'s row, rendered with a real, clickable identity —
    see :func:`_hour_saved_content` for why the lead/trail parts are
    restated rather than shared."""
    state, parts = _whale_row(data)
    amount = as_float(data.get("whale_amount_eth"))
    wallet = data.get("whale_wallet") if amount is not None else None
    if not wallet:
        markup, starved = _row(label, state, parts, width)
        return Text.from_markup(_resolved_markup(markup, colors)), starved
    age = fmt_age(data.get("whale_age_s"))
    return _identity_row(
        label, state, [f"[bold]{fmt_eth(amount)} ETH[/]"], wallet,
        data.get("whale_ens"), [f"{age} ago"] if age != DASH else [], width, colors,
    )


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
        return None, list(NO_WALLET_PARTS)
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


# -- how wide the rail is ------------------------------------------------


def measure_signals_width(payload: dict) -> int:
    """Widget columns the rail needs to render **this** payload whole.

    ``padding: 0 1`` on every row is the ``+ 2``; the rest is the widest row
    the seven builders produce, measured at ``width=0`` (which
    :func:`_row` reads as "not laid out yet" and therefore drops nothing).

    Public because "what does the rail need?" has two answers and a consumer
    usually wants this one.  :data:`SIGNALS_FULL_WIDTH` is the *worst case*
    over every magnitude the contract can produce and is the wrong number to
    size a slot from — a screen that budgeted it would be 20 columns wider
    than any dashboard in this app.  A screen budgets against the state the
    data is normally in and lets the ``‹ widen`` marker cover the tail, the
    way CLAUDE.md's 143 clears every *layout* rather than every possible
    string.

    HOUR SAVED and WHALE are measured through :func:`_hour_saved_content`
    and :func:`_whale_content` -- the same functions ``_render_view`` calls
    to paint them -- rather than through the plain-string ``_BUILDERS`` +
    :func:`_row` path the other five rows still use: this rail's real,
    icon-carrying identity is a ``Text``, and this function used to measure
    the ``short_label`` string that identity replaced, silently
    under-counting the two rows that ever carry a copy icon by
    :data:`ICON_COLS`.  ``colors=None`` is fine for a *measurement* -- a
    resolved colour changes no cell's width, only its foreground -- so the
    icon-side fallback colours (:data:`_TOKEN_FALLBACK`) are never resolved
    here.
    """
    widest = 0
    for key, label in zip(SIGNAL_KEYS, SIGNAL_LABELS):
        if key == "hour_saved":
            content, _starved = _hour_saved_content(label, payload, 0)
        elif key == "whale":
            content, _starved = _whale_content(label, payload, 0)
        else:
            state, parts = _BUILDERS[key](payload)
            markup, _starved = _row(label, state, parts, 0)
            content = markup
        width = content.cell_len if isinstance(content, Text) else visible_len(content)
        widest = max(widest, width)
    return widest + 2


#: The widest value each field of the payload can carry — a **probe**, in the
#: sense ``_fmt.COMPACT_ETH_PROBE`` is one, not a fixture and not a capture.
#:
#: Every entry has a reason, because a probe assembled from plausible-looking
#: numbers is exactly the mistake it exists to correct:
#:
#: * the ETH amounts are ``max(COMPACT_ETH_PROBE)`` — the same magnitude the
#:   rest of this package sizes its ETH cells from, already documented there
#:   as "an order of magnitude past anything this game has routed".  Note the
#:   rail renders them through :func:`_fmt.fmt_eth`, not ``fmt_eth_compact``,
#:   so the same magnitude costs **nine** columns here and six in a table;
#: * the point counts are ``44_721``, and that one is a **hard bound**, not
#:   headroom: lifetime weight telescopes to at most ``2 * creditCap`` (the
#:   contract's own argument for the ``uint96`` cast in ``_credit``), and
#:   ``_curve`` is ``isqrt(weight) * POINTS_PER_ETH / 1e9``, so at this
#:   deployment's 1000 ETH cap and ``POINTS_PER_ETH == 1000`` no wallet can
#:   score past ``isqrt(2e21) * 1000 // 1e9``.  ``leaderboard._POINTS_COLS``
#:   is sized from the same ceiling, and the test module asserts both against
#:   ``analytics.curator_signals.points_for_weight`` — the widgets may not
#:   import it, so the agreement lives in the suite;
#: * ``you_rank`` is bounded by ``totalContributors``, which nothing bounds.
#:   Five digits is a decade past the 2 291 wallets on the captured list, the
#:   same headroom the ETH probe carries;
#: * the hour indices are ~14 months of hours, the ages ~3 years, and
#:   ``hour_seconds_left`` is 99 hours: ``hourDuration`` is an immutable, so
#:   the countdown is not guaranteed to be the 3600 this deployment uses.
WIDTH_PROBE = {
    # `address_text`'s `label=` is capped at NAME_COLS (12) here (see
    # `_identity_row`'s own `width=NAME_COLS` call); these two probe values
    # are 11, one column under that cap and already the widest an ENS name
    # can be measured at without moving `_IDENTITY_FIELDS`-shaped values
    # here, so ENS still cannot move the measured worst case (PRD §13 A9).
    "whale_ens": "w" * 11,
    "last_saved_ens": "s" * 11,
    "phase": "judged",
    "settled": True,
    "settled_hour": 9_999,
    "sig_settled_state": "fired",
    "sig_at_risk_state": "fired",
    "first_judged_hour": 9_999,
    "hour_needed_eth": _WIDEST_ETH,
    "hour_seconds_left": 359_999,
    "last_saved_hour": 9_999,
    "last_saved_wallet": "0x" + "a" * 40,
    "last_saved_age_s": 999 * 86_400,
    "whale_amount_eth": _WIDEST_ETH,
    "whale_wallet": "0x" + "b" * 40,
    "whale_age_s": 999 * 86_400,
    "clusters_count": 9_999,
    "flagged_points_share_pct": 100.0,
    "forced_eth": _WIDEST_ETH,
    "rescued_total_eth": _WIDEST_ETH,
    "you_rank": 99_999,
    "you_points": MAX_CURVE_POINTS,
    "you_credit_eth": _WIDEST_ETH,
    "you_required_next_eth": _WIDEST_ETH,
    "you_marginal_points": MAX_CURVE_POINTS,
    #: Empty **on purpose**, and it is the one probe entry that is not a
    #: maximum: a degraded group only ever replaces a row's parts with
    #: ``-- unknown``, which is narrower than every value it stands in for.
    #: The widest rail is the healthy one, and the suite asserts that a
    #: ``["logs"]`` probe measures no wider.
    "degraded": [],
}

#: Widget columns the rail needs for the widest row it can **ever** render,
#: ``padding: 0 1`` included.  Derived from :data:`WIDTH_PROBE` through the
#: seven builders, so no example row can set it again — the ``dev``/``ops``
#: lesson in CLAUDE.md, and the reason ``_fmt.COMPACT_ETH_COLS``,
#: :data:`LABEL_COLS` and ``activity._KIND_COLS`` are all derived too.
#:
#: **Three numbers have stood here and the history is the documentation.**
#: The wp4 hand-off published **76**, read off an example in a docstring; at
#: 76 the rail rendered by silently dropping ``next ≥ 4.10 ETH (+120 pts)``,
#: the only actionable number it carries.  That was corrected to **82** by
#: measuring the builders — but against ``_signals_full()``, an invented
#: four-figure wallet, so the number was still a fixture's and not the
#: panel's: WP6's screen sweep, run against the capture's **rank-1** wallet
#: (``490.90 credit`` / ``next ≥ 491.00 ETH``), needed **84** and reported it.
#: Re-measuring against one *better* fixture would have repeated the mistake
#: a third time, because the YOU row's width is a function of the reader's
#: own credit and the reader is not on the captured list.  So the constant is
#: now the worst case over the producer's whole vocabulary, and the answer
#: for any particular payload comes from :func:`measure_signals_width`.
#:
#: It is **not** a slot budget.  No layout in this app is this wide, and none
#: should grow to be: the marker is what covers a reader whose own credit
#: outgrows the rail, exactly as surf's announce feed lights ``‹ widen`` at
#: the full-layout width for a post that links a transaction.
SIGNALS_FULL_WIDTH = measure_signals_width(WIDTH_PROBE)


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
        last_saved_ens=None,
        last_saved_age_s=None,
        whale_amount_eth=None,
        whale_wallet=None,
        whale_ens=None,
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
        degraded=None,
        **_kwargs,
    ) -> None:
        """Refresh all seven rows from the flat ``CURATOR_KEYS`` payload.

        ``degraded`` is the one health key any widget takes: see
        :data:`LOGS_GROUP` for why two of these rows cannot be honest without
        it.
        """
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
            "last_saved_ens": last_saved_ens,
            "last_saved_age_s": last_saved_age_s,
            "whale_amount_eth": whale_amount_eth,
            "whale_wallet": whale_wallet,
            "whale_ens": whale_ens,
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
            "degraded": list(degraded) if degraded else [],
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

    def _theme_colors(self) -> dict[str, str]:
        """The app's current concrete colours for :data:`_TOKEN_FALLBACK`'s
        three tokens, or ``{}`` when unavailable (not yet mounted, or a bare
        harness with no theme) -- :func:`_resolved_markup` falls back to the
        plain colour names in that case."""
        try:
            return self.app.get_css_variables()
        except Exception:
            return {}

    def _render_view(self) -> None:
        payload = self._payload
        width = max(self.content_size.width - 2, 0)
        starved = False
        # Resolved once per refresh, only for the two rows that build a real
        # ``Text`` (see ``_TOKEN_FALLBACK``): the other five keep handing
        # ``Static`` the plain markup string it has always used, parsed by
        # Textual's own ``$``-aware ``Content.from_markup`` exactly as before.
        colors = self._theme_colors()

        for key, label in zip(SIGNAL_KEYS, SIGNAL_LABELS):
            try:
                if key == "hour_saved":
                    content, row_starved = _hour_saved_content(
                        label, payload, width, colors
                    )
                elif key == "whale":
                    content, row_starved = _whale_content(
                        label, payload, width, colors
                    )
                else:
                    state, parts = _BUILDERS[key](payload)
                    content, row_starved = _row(label, state, parts, width)
            except Exception:
                # One malformed value costs its row's value, never the rail
                # (CLAUDE.md: never a blank panel) -- the pre-Task-3 shape,
                # restored: the head plus the explicit unknown value, not a
                # bare head with nothing after it.
                content, row_starved = _row(label, None, [f"{DASH} unknown"], width)
            starved = starved or row_starved
            try:
                row = self.query_one(f"#curator-sig-{key}", Static)
            except QueryError:
                return  # not composed yet; none of the rows are
            try:
                row.update(content)
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
