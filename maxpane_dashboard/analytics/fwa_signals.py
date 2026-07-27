"""Signal analytics for the Fake World Assets (FWA) "Gacha Terminal" dashboard.

Five signal rows, five builders, one contract.  Every builder returns an
:class:`~maxpane_dashboard.data.fwa_models.FWASignal` — ``label``,
``value_str``, ``indicator``, ``color`` — with ``color`` restricted to
:data:`SIGNAL_COLORS`, i.e. the **theme variables** ``$success | $warning |
$error`` plus the ``dim`` style.  Never the CSS colour names ``green`` /
``yellow`` / ``red``: Textual resolves content markup through the CSS name
table, where ``green`` is ``#008000`` — 3.52:1 on the ``fwa`` surface and only
4.09:1 against pure black, so it fails WCAG AA on *every* possible background
and no palette can rescue it (WP-19).  Colour is never the sole carrier of
meaning either: each ``value_str`` spells the state out in words, so the panel
survives greyscale and colour-blind viewing (PRD §11).

Everything here is pure.  No network, no clients, no cache, no Textual.  The one
file this module touches is the vendored ``abis/fwa/config_keys.json`` key map,
read once and lazily by :func:`config_key_meta`, which fails soft to an empty
map — the builders themselves take their inputs as arguments and never read it
implicitly at call time.

The five rows
-------------

1. :func:`pool_temp_signal` — which way the 10% surcharge is flowing right now.
2. :func:`buy_gate_signal` — ``FWATokenHook.externalBuysEnabled()``.
3. :func:`emissions_signal` — the $FWA emission window.
4. :func:`vrf_queue_signal` — acquisition queue depth and subscription solvency.
5. :func:`param_drift_signal` — owner parameter changes, from ``ConfigSet`` logs.

Four traps these builders encode
--------------------------------

1. **The post-emissions state is the PRIMARY case, not the exception.**  The
   hard stop is ``1785870083`` = 2026-08-04T19:01:23Z — it lands *during* this
   build, so both branches are real: the countdown is what renders today, and
   the ended state is what the dashboard will spend virtually all of its life
   in.  :func:`emissions_signal` is written ended-first and can never render a
   negative countdown, and it takes its clock as an argument so neither branch
   depends on when the process happens to run.  The row is called *emissions
   status*, not *emissions countdown*, for that reason (PRD §8, §12.6).

2. **The live ``tokenShareBps`` always wins over the ramp.**  The documented
   ramp — 100% to depositors at ≤60 s since the last request, 100% to the
   purchaser's $FWA allowance at ≥3600 s — is linear only by assumption; only
   the two endpoints were verified (PRD §4 implementation note, §13).  So
   :func:`fwa_ev.surcharge_ramp_share` is a **fallback label only**, and when it
   is used :attr:`PoolTemp.share_estimated` is set to ``True`` rather than the
   caveat being smuggled into a string.

3. **The ``ConfigSet`` launch write must be filtered out.**  There are 27
   ``ConfigSet`` logs; 21 of them are a single constructor-time write at one
   block and only **6** are genuine post-launch changes (findings §13.11).
   Without the filter the drift row reports 21 spurious drifts on first load.
   The launch block is identified *exactly* rather than heuristically: keys 1,
   24 and 63 are constructor-only (``settable: false`` in ``config_keys.json``,
   findings §13.3), so any block carrying one of them is the launch write.
   Those keys are also labelled constructor-only wherever they surface, so the
   row never implies the owner can still change them.

4. **Nothing documented is hardcoded.**  Every parameter is compared against
   on-chain ``ConfigSet`` history, never against a documented default — the
   crown tithe is documented at 5% but live at 1% (PRD §7 rule 6).  The
   before/after values in the drift row come out of the launch write's own event
   data.  Likewise there is no harmonic/arithmetic gap constant anywhere in this
   module: that ratio is live (findings §13.7-13.8).

Pattern: ``maxpane_dashboard/analytics/talismans_signals.py``,
``maxpane_dashboard/analytics/ttt_signals.py``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.data.fwa_models import ConfigParam, FWASignal, PoolTemp

__all__ = [
    # constants
    "SIGNAL_COLORS",
    "SIGNAL_GOOD",
    "SIGNAL_WARN",
    "SIGNAL_BAD",
    "SIGNAL_MUTED",
    "INDICATOR",
    "BUY_GATE_FOOTNOTE",
    "QUEUE_DEPTH_OK",
    "DOCUMENTED_EMISSION_START",
    "DOCUMENTED_EMISSION_DURATION",
    "DOCUMENTED_EMISSION_STOP",
    "DEGRADED_LABELS",
    # config-key metadata
    "config_key_meta",
    "config_key_name",
    "is_settable",
    "launch_write_blocks",
    # pool temperature
    "resolve_pool_temp",
    "pool_temp_signal",
    "pool_temp_signal_for",
    # the five builders
    "buy_gate_signal",
    "emissions_signal",
    "vrf_queue_signal",
    "param_drift_signal",
    # parameter resolution
    "resolve_config_params",
    "post_launch_changes",
    # scalar helpers
    "invariant_summary",
    "degraded_label",
    "as_of_label",
]


# ---------------------------------------------------------------------------
# Presentation constants
# ---------------------------------------------------------------------------

#: Good / neutral-warning / bad / muted, as Textual **theme variables**.
#:
#: These are markup tokens, and which table Textual resolves them through
#: matters more than it looks.  ``Static``/``Content`` markup resolves colour
#: *names* through the CSS name table — ``green`` is ``#008000``, whose contrast
#: peaks at 4.09:1 against pure black, so it fails WCAG AA 4.5:1 on every
#: background that exists and no theme palette can fix it.  ``$success`` /
#: ``$warning`` / ``$error`` are resolved per theme instead, are required
#: ``Theme`` fields (so they are defined under all ten registered themes), and
#: measure 10.39 / 6.97 / 6.78 under ``fwa`` against ``green`` / ``yellow`` /
#: ``red``'s 3.52 / 16.85 / 4.53.  Measured off ``_compositor.render_strips()``,
#: not off the source markup (WP-19).
SIGNAL_GOOD = "$success"
SIGNAL_WARN = "$warning"
SIGNAL_BAD = "$error"
#: Degraded, not invisible: ``dim`` is a style rather than a colour, so it
#: tracks the theme foreground instead of pinning a hex value.
SIGNAL_MUTED = "dim"

#: The only colours an :class:`FWASignal` may carry.
SIGNAL_COLORS: frozenset[str] = frozenset(
    {SIGNAL_GOOD, SIGNAL_WARN, SIGNAL_BAD, SIGNAL_MUTED}
)

#: Every FWA signal row uses the same dot, per the Talismans panel convention.
INDICATOR = "●"

#: DexScreener reports ~11.4k "buys" while ``externalBuysEnabled()`` is false.
#: Those are FWARewards-routed protocol distributions, not open-market
#: purchases (findings §9.2).  Without this note the UI reads as a
#: contradiction, so the gated row carries it inline — kept short enough that
#: it survives the signals panel's line width rather than being clipped off.
BUY_GATE_FOOTNOTE = 'DEX "buys" are FWARewards payouts'

#: Queue depth (``lastIssuedSequence - nextSequenceToProcess``) at or below
#: which the sequencer is considered to be keeping up.  A *presentation*
#: threshold, not a protocol parameter: the live queue runs 15-19 and the
#: contract defines no "deep" value, so this is a UI judgement and is named
#: rather than buried in a comparison.
QUEUE_DEPTH_OK = 25

#: $FWA emission window, for documentation and for tests that need a realistic
#: clock.  **Never used as a default** — :func:`emissions_signal` degrades to an
#: explicit unavailable row rather than substituting these for a failed read
#: (PRD §7 rule 6).
DOCUMENTED_EMISSION_START = 1_784_574_083      # 2026-07-20T19:01:23Z
DOCUMENTED_EMISSION_DURATION = 15 * 24 * 3_600  # 15 days
DOCUMENTED_EMISSION_STOP = DOCUMENTED_EMISSION_START + DOCUMENTED_EMISSION_DURATION
#: == 1785870083 == 2026-08-04T19:01:23Z.  Mid-build; see trap 1.

#: Exact strings the widgets render for a dead source (PRD §9, plan §12).
DEGRADED_LABELS: dict[str, str] = {
    "logs": "logs unavailable — activity paused",
    "log": "logs unavailable — activity paused",
    "chain": "chain unavailable",
    "state": "chain unavailable",
    "rpc": "chain unavailable",
    "market": "market data unavailable",
    "floors": "floor prices unavailable",
    "floor": "floor prices unavailable",
    "cache": "cache unavailable",
}


# ---------------------------------------------------------------------------
# Small formatting / coercion helpers
# ---------------------------------------------------------------------------


def _signal(label: str, value_str: str, color: str) -> FWASignal:
    """Build a row, defending the colour vocabulary at the construction site."""
    if color not in SIGNAL_COLORS:  # pragma: no cover - guards a typo, not a state
        raise ValueError(f"colour {color!r} is not one of {sorted(SIGNAL_COLORS)}")
    return FWASignal(label=label, value_str=value_str, indicator=INDICATOR, color=color)


def _unavailable(label: str, what: str) -> FWASignal:
    """The defined unavailable state every builder shares.

    Dim, and it says the word "unavailable".  A dead source is never allowed to
    look like a value (PRD §9).
    """
    return _signal(label, f"{what} unavailable", SIGNAL_MUTED)


def _as_int(value: Any) -> int | None:
    """Coerce a JSON-RPC-ish scalar to ``int``; ``None`` when it cannot be.

    Handles plain ints, ``"0x1f"`` hex strings and decimal strings.  ``bool`` is
    accepted (``True`` -> 1) because ``setBool`` config values arrive that way
    from some decoders.  Floats are rejected rather than truncated.
    """
    if value is None or isinstance(value, float):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError:
            return None
    return None


def _fmt_duration(seconds: float) -> str:
    """``12s`` / ``41m`` / ``1h 12m`` / ``21d``.  Never negative.

    Clamped at zero on purpose: a negative duration is the exact bug this
    dashboard is required not to render (PRD §8).
    """
    total = int(max(0, seconds))
    if total < 60:
        return f"{total}s"
    if total < 3_600:
        return f"{total // 60}m"
    if total < 86_400:
        hours, minutes = divmod(total // 60, 60)
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, remainder = divmod(total, 86_400)
    hours = remainder // 3_600
    return f"{days}d {hours}h" if hours else f"{days}d"


def _fmt_bps(bps: int) -> str:
    """``100`` -> ``1%``, ``3450`` -> ``34.5%``.  Whole percents lose the ``.0``."""
    if bps % 100 == 0:
        return f"{bps // 100}%"
    return f"{bps / 100:.1f}%"


def _fmt_eth(wei: int | float) -> str:
    """Wei -> a short ETH string for the one row that shows a balance."""
    return f"{wei / 1e18:.2f}"


# ---------------------------------------------------------------------------
# ConfigSet key metadata  (abis/fwa/config_keys.json)
# ---------------------------------------------------------------------------

_CONFIG_KEYS_PATH = Path(__file__).resolve().parent.parent / "abis" / "fwa" / "config_keys.json"

_CONFIG_KEY_META: dict[int, dict[str, Any]] | None = None

#: Short human aliases for the keys a user actually cares about.  Names, not
#: values — nothing here is a parameter default.
_KEY_ALIASES: dict[int, str] = {
    13: "surcharge",
    15: "crown tithe",
    16: "crown threshold",
    17: "sellback payout",
    18: "owner acq fee",
    19: "owner settle fee",
    22: "min backing",
    41: "acquisitions",
    42: "withdraw-only",
    43: "whitelist",
    44: "accept-bid-as-$FWA",
}

#: Economic parameters — preferred when choosing which change to name in the
#: one-line drift row, because a tithe move matters more to a reader than a
#: toggle flip.
_ECONOMIC_KEYS: frozenset[int] = frozenset({13, 14, 15, 16, 17, 18, 19, 22, 23})


def config_key_meta() -> dict[int, dict[str, Any]]:
    """The vendored ``ConfigSet`` key map, ``{key: {name, value_type, settable}}``.

    Read once and cached.  Fails soft to ``{}`` if the asset is missing or
    corrupt: an absent key map degrades the drift row to raw key numbers, it
    never raises inside a render path.
    """
    global _CONFIG_KEY_META
    if _CONFIG_KEY_META is None:
        loaded: dict[int, dict[str, Any]] = {}
        try:
            raw = json.loads(_CONFIG_KEYS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            for key_text, meta in raw.items():
                key = _as_int(key_text)
                if key is not None and isinstance(meta, dict):
                    loaded[key] = meta
        _CONFIG_KEY_META = loaded
    return _CONFIG_KEY_META


def config_key_name(key: int, *, short: bool = False) -> str:
    """Resolved label for a config key, e.g. ``TOP_LISTING_SHARE_BPS``.

    ``short=True`` prefers the human alias (``crown tithe``) where one exists.
    Unknown keys render ``key N`` — the honest fallback, never a guess.
    """
    if short and key in _KEY_ALIASES:
        return _KEY_ALIASES[key]
    meta = config_key_meta().get(key)
    name = meta.get("name") if isinstance(meta, dict) else None
    return str(name) if name else f"key {key}"


def is_settable(key: int) -> bool:
    """Whether the owner can still write this key after deployment.

    Keys 1 (``CALLBACK_GAS_LIMIT``), 24 (``VRF_KEY_HASH``) and 63
    (``VRF_SERVICE``) are emitted through ``ConfigSet`` by the constructor but
    rejected by ``setUint``/``setAddr`` (findings §13.3).  Read from the
    ``settable`` flag, not from the findings §8 table, which mis-groups them.

    Unknown keys are reported settable — the conservative direction, since the
    alternative is silently hiding a genuine owner change.
    """
    meta = config_key_meta().get(key)
    if not isinstance(meta, dict) or "settable" not in meta:
        return True
    return bool(meta["settable"])


def _key_value_type(key: int) -> str:
    meta = config_key_meta().get(key)
    value_type = meta.get("value_type") if isinstance(meta, dict) else None
    return str(value_type) if value_type else "uint256"


def _fmt_config_value(key: int, value: int) -> str:
    """Render a config value the way its type reads.

    Bools become ``on``/``off``, addresses and bytes32 are truncated — a
    150-digit ``VRF_SUB_ID`` in a signal row helps nobody.
    """
    value_type = _key_value_type(key)
    if value_type == "bool":
        return "on" if value else "off"
    if value_type == "address":
        text = f"{value:040x}"
        return f"0x{text[:4]}..{text[-4:]}"
    if value_type == "bytes32":
        text = f"{value:064x}"
        return f"0x{text[:4]}..{text[-4:]}"
    return str(value)


# ---------------------------------------------------------------------------
# ConfigSet event normalisation
# ---------------------------------------------------------------------------


class _ConfigChange:
    """One normalised ``ConfigSet`` log: key, value, block, stable order."""

    __slots__ = ("key", "value", "block", "order")

    def __init__(self, key: int, value: int, block: int, order: int) -> None:
        self.key = key
        self.value = value
        self.block = block
        self.order = order

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.block, self.order)


def _field(event: Any, *names: str) -> Any:
    """Pull the first present field from a mapping or an object."""
    if isinstance(event, Mapping):
        for name in names:
            if name in event:
                return event[name]
        return None
    for name in names:
        if hasattr(event, name):
            return getattr(event, name)
    return None


def _normalise_events(events: Iterable[Any] | None) -> list[_ConfigChange]:
    """Coerce whatever the log layer hands over into sorted ``_ConfigChange``.

    Accepts mappings (``{"key": 15, "value": 100, "blockNumber": ...}``, either
    snake or camel case, hex or decimal) and plain objects with the same
    attribute names.  Anything unparseable is dropped rather than raising: a
    single malformed log must not take the row down.
    """
    if not events:
        return []
    out: list[_ConfigChange] = []
    for index, event in enumerate(events):
        key = _as_int(_field(event, "key", "config_key"))
        value = _as_int(_field(event, "value", "config_value"))
        block = _as_int(_field(event, "block_number", "blockNumber", "block"))
        order = _as_int(_field(event, "log_index", "logIndex", "index"))
        if key is None or value is None or block is None:
            continue
        out.append(_ConfigChange(key, value, block, index if order is None else order))
    out.sort(key=lambda change: change.sort_key)
    return out


def launch_write_blocks(events: Iterable[Any] | None) -> set[int]:
    """Blocks carrying the constructor's bulk parameter write.

    Identified **exactly**, not by counting: keys 1, 24 and 63 can only ever be
    written by the constructor (``settable: false``), so any block containing
    one of them is a launch-write block.  If the key map failed to load — or the
    caller handed over a tail slice that happens to exclude those three keys —
    this falls back to "the earliest block, if it carries a bulk write" (the
    real one carries 21 logs).

    Returns an empty set when no launch write is present, which is the normal
    case for an incremental tail fetch.
    """
    changes = _normalise_events(events)
    if not changes:
        return set()

    blocks = {change.block for change in changes if not is_settable(change.key)}
    if blocks:
        return blocks

    # Fallback: a bulk write at the earliest block we can see.  The threshold is
    # deliberately well above any plausible multi-key owner transaction and well
    # below the 21 logs the real launch write carries.
    earliest = min(change.block for change in changes)
    if sum(1 for change in changes if change.block == earliest) >= 8:
        return {earliest}
    return set()


def post_launch_changes(
    events: Iterable[Any] | None,
    *,
    launch_block: int | None = None,
) -> list[dict[str, Any]]:
    """Genuine owner parameter changes: every ``ConfigSet`` minus the launch write.

    The full history has 27 logs and exactly **6** of them are post-launch
    changes (findings §13.11).  Skipping this filter is what makes a fresh
    dashboard scream 21 drifts on first load.

    Args:
        events: raw ``ConfigSet`` logs, any of the shapes
            :func:`_normalise_events` accepts.
        launch_block: pin the launch write explicitly.  Defaults to
            :func:`launch_write_blocks`.

    Returns:
        ``[{"key", "name", "value", "block_number", "settable"}]``, oldest
        first.
    """
    changes = _normalise_events(events)
    excluded = {launch_block} if launch_block is not None else launch_write_blocks(events)
    return [
        {
            "key": change.key,
            "name": config_key_name(change.key),
            "value": change.value,
            "block_number": change.block,
            "settable": is_settable(change.key),
        }
        for change in changes
        if change.block not in excluded
    ]


def _live_map(live_params: Any) -> dict[int, int]:
    """Normalise live parameter values into ``{key: value}``.

    Accepts a mapping keyed by int or by string, or a sequence of
    :class:`ConfigParam`-shaped objects.
    """
    out: dict[int, int] = {}
    if live_params is None:
        return out
    if isinstance(live_params, Mapping):
        items: Iterable[tuple[Any, Any]] = live_params.items()
        for raw_key, raw_value in items:
            key = _as_int(raw_key)
            value = _as_int(raw_value)
            if key is not None and value is not None:
                out[key] = value
        return out
    if isinstance(live_params, Sequence) and not isinstance(live_params, (str, bytes)):
        for param in live_params:
            key = _as_int(_field(param, "key"))
            value = _as_int(_field(param, "value"))
            if key is not None and value is not None:
                out[key] = value
    return out


def resolve_config_params(
    config_events: Iterable[Any] | None,
    live_params: Any = None,
    *,
    launch_block: int | None = None,
) -> list[ConfigParam]:
    """Live parameters resolved against ``ConfigSet`` history.

    One :class:`ConfigParam` per key for which a **live** value is known — the
    model's ``value`` field means the live read, so a key we never read is
    omitted rather than back-filled from a log (which would present history as
    present state).

    ``block_number`` is the block of the last ``ConfigSet`` that touched the key
    (0 if the key has no history in the supplied window), and ``is_drift`` is
    ``live != that event's value`` — **never** a comparison against a documented
    default (PRD §7 rule 6).

    Rows are ordered by key so the table is stable across polls.
    """
    # The launch write is real history and is a key's last written value until
    # something overwrites it.  It is excluded from the *change count* in
    # `param_drift_signal`, never from this resolution -- which is why
    # `launch_block` is accepted here only for signature symmetry.
    _ = launch_block

    changes = _normalise_events(config_events)
    last_by_key: dict[int, _ConfigChange] = {}
    for change in changes:
        last_by_key[change.key] = change

    live = _live_map(live_params)
    params: list[ConfigParam] = []
    for key in sorted(live):
        last = last_by_key.get(key)
        params.append(
            ConfigParam(
                key=key,
                name=config_key_name(key),
                value=live[key],
                block_number=last.block if last is not None else 0,
                is_drift=last is not None and last.value != live[key],
            )
        )
    return params


# ---------------------------------------------------------------------------
# 1. Pool temperature
# ---------------------------------------------------------------------------


def resolve_pool_temp(
    seconds_since_last_request: int | None,
    token_share_bps: int | None = None,
    hot_gap: int = 0,
    cold_gap: int = 0,
    forced_bps: int = -1,
) -> PoolTemp | None:
    """Assemble a :class:`PoolTemp`, falling back to the ramp only if forced to.

    Resolution order for the purchaser's surcharge share:

    1. ``forced_bps >= 0`` — an owner override pins the split regardless of
       temperature.  ``forced_bps`` is a **signed int256**; ``-1`` is the normal
       dynamic case and ``2**256 - 1`` is a decode bug, not a huge share.
    2. the live ``tokenShareBps(gap)`` read, which always wins over the ramp.
    3. :func:`fwa_ev.surcharge_ramp_share` — the documented ramp, used as a
       **label only** because its linearity is unconfirmed.  Taking this branch
       sets ``share_estimated=True``.

    ``hot_gap`` / ``cold_gap`` of ``0`` mean "not read"; the documented 60/3600
    endpoints are then used to word the temperature, which the ``PoolTemp``
    contract permits as a static label.  They are not written back into the
    model, so a documented number can never masquerade as a live read.

    Returns ``None`` when ``seconds_since_last_request`` is unknown — with no
    clock there is no temperature, and inventing one would be the exact class of
    silently-wrong number PRD §9 forbids.
    """
    gap = _as_int(seconds_since_last_request)
    if gap is None:
        return None
    gap = max(0, gap)

    live_bps = _as_int(token_share_bps)
    forced = _as_int(forced_bps)
    forced = -1 if forced is None else forced
    # A decoded-unsigned int256 -1 is astronomically larger than BPS; treat any
    # nonsensical override as "no override" rather than as a 1e75% share.
    if forced > fwa_ev.BPS:
        forced = -1

    estimated = False
    if forced >= 0:
        share_bps = forced
    elif live_bps is not None:
        share_bps = max(0, min(live_bps, fwa_ev.BPS))
    else:
        hot, cold = _ramp_endpoints(hot_gap, cold_gap)
        share_bps = round(fwa_ev.surcharge_ramp_share(gap, hot, cold) * fwa_ev.BPS)
        estimated = True

    return PoolTemp(
        seconds_since_last_request=gap,
        token_share_bps=share_bps,
        hot_gap=max(0, _as_int(hot_gap) or 0),
        cold_gap=max(0, _as_int(cold_gap) or 0),
        forced_share_bps=forced,
        share_estimated=estimated,
    )


def _ramp_endpoints(hot_gap: Any, cold_gap: Any) -> tuple[int, int]:
    """Effective ramp endpoints, documented values only where nothing was read."""
    hot = _as_int(hot_gap) or 0
    cold = _as_int(cold_gap) or 0
    if hot <= 0:
        hot = fwa_ev.HOT_GAP_SECONDS
    if cold <= 0:
        cold = fwa_ev.COLD_GAP_SECONDS
    return hot, cold


def pool_temp_signal_for(temp: PoolTemp | None) -> FWASignal:
    """Render an already-assembled :class:`PoolTemp` as a signal row.

    The row must answer one question at a glance: **which way is the surcharge
    flowing?**  So it always carries a direction in words (``→ YOU`` /
    ``→ depositors``) alongside the colour, and the temperature word alongside
    the elapsed time::

        HOT 12s · surcharge → depositors                    (dim)
        WARM 12m · surcharge → YOU ~34% est                 (yellow)
        COLD 41m · surcharge → YOU (100%)                   (green)
        OVERRIDE 12m · surcharge → YOU 34% (dial pinned)    (yellow)

    Colour tracks the *share*, since that is the part that moves the reader's
    money; the temperature word tracks the *clock*, which is the definition of
    pool temperature.  In the normal case they agree, and when the live share
    contradicts the ramp the live share is what is shown.
    """
    label = "POOL TEMP"
    if temp is None:
        return _unavailable(label, "pool temp")

    gap = max(0, temp.seconds_since_last_request)
    share_bps = temp.token_share_bps
    if share_bps is None:
        return _unavailable(label, "pool temp")
    share_bps = max(0, min(share_bps, fwa_ev.BPS))

    hot, cold = _ramp_endpoints(temp.hot_gap, temp.cold_gap)
    if gap <= hot:
        word = "HOT"
    elif gap >= cold:
        word = "COLD"
    else:
        word = "WARM"

    overridden = temp.forced_share_bps >= 0
    if overridden:
        word = "OVERRIDE"

    if share_bps <= 0:
        direction = "surcharge → depositors"
        color = SIGNAL_MUTED
    elif share_bps >= fwa_ev.BPS:
        direction = "surcharge → YOU (100%)"
        color = SIGNAL_GOOD
    else:
        marker = "~" if temp.share_estimated else ""
        direction = f"surcharge → YOU {marker}{_fmt_bps(share_bps)}"
        color = SIGNAL_WARN

    if overridden:
        color = SIGNAL_WARN  # the dial is pinned; that is worth noticing either way

    value = f"{word} {_fmt_duration(gap)} · {direction}"
    if temp.share_estimated:
        value = f"{value} est"
    if overridden:
        value = f"{value} (dial pinned)"
    return _signal(label, value, color)


def pool_temp_signal(
    seconds_since_last_request: int | None = None,
    token_share_bps: int | None = None,
    hot_gap: int = 0,
    cold_gap: int = 0,
    forced_bps: int = -1,
) -> FWASignal:
    """Pool-temperature row — the timing dial nobody is trading (PRD §4).

    Thin wrapper over :func:`resolve_pool_temp` + :func:`pool_temp_signal_for`
    so a caller holding raw reads and a caller holding a :class:`PoolTemp` reach
    the same row.  With no clock read at all the row is an explicit dim
    ``pool temp unavailable``.
    """
    return pool_temp_signal_for(
        resolve_pool_temp(
            seconds_since_last_request,
            token_share_bps=token_share_bps,
            hot_gap=hot_gap,
            cold_gap=cold_gap,
            forced_bps=forced_bps,
        )
    )


# ---------------------------------------------------------------------------
# 2. Buy gate
# ---------------------------------------------------------------------------


def buy_gate_signal(external_buys_enabled: bool | None = None) -> FWASignal:
    """``FWATokenHook.externalBuysEnabled()`` as a red/green badge (PRD §8).

    Outside buys are currently blocked, which makes DexScreener's ~11.4k "buys"
    look like a contradiction — they are FWARewards-routed distributions
    (findings §9.2).  The gated row therefore carries
    :data:`BUY_GATE_FOOTNOTE` inline, because an ``FWASignal`` has nowhere else
    to put it and a user staring at a green volume chart deserves the
    explanation on the same line.

    Flipping this flag is the single biggest scheduled event for the token, so
    the open state is loud rather than silent.
    """
    label = "BUY GATE"
    if external_buys_enabled is None:
        return _unavailable(label, "buy gate")
    if external_buys_enabled:
        return _signal(label, "OPEN — outside buys enabled", SIGNAL_GOOD)
    return _signal(label, f"GATED — no outside buys · {BUY_GATE_FOOTNOTE}", SIGNAL_BAD)


# ---------------------------------------------------------------------------
# 3. Emissions status  — the ENDED branch is the primary case
# ---------------------------------------------------------------------------


def emissions_signal(
    now_ts: float | None = None,
    emission_start: int | None = None,
    emission_duration: int | None = None,
    current_epoch: int | None = None,
) -> FWASignal:
    """$FWA emission status — three states, ended written first (PRD §8, §12.6).

    The window closes at ``emission_start + emission_duration`` =
    :data:`DOCUMENTED_EMISSION_STOP` = 2026-08-04T19:01:23Z, which falls *inside*
    this build.  Both branches are therefore live code: the countdown is what
    renders right now, and the ended state is what the dashboard will show for
    the rest of its life, so it is the one written and tested first::

        emissions ended · 21d ago            (dim,    primary)
        emissions live · 8d 4h left          (yellow, current reality)
        emissions status unavailable         (dim)

    **The clock is injected, never read here.**  ``now_ts`` is a required input
    with no wall-clock fallback, which is what lets the manager, the widget
    tests and the screen tests pin any moment they like and get identical
    results before and after the stop.  Omitting it yields the unavailable row.

    The countdown branch is reachable only while ``now_ts`` is strictly before
    the stop, so **a negative countdown cannot be rendered** — the elapsed
    figure in the ended branch is likewise clamped at zero by
    :func:`_fmt_duration`.  WP-11's belt-and-braces rewrite of negative
    countdowns should never have anything to catch here.  This is a signal row
    and never a hero tile.

    ``emission_start`` / ``emission_duration`` are live reads; a missing one
    degrades to the unavailable row rather than falling back to the documented
    constants above.
    """
    label = "EMISSIONS"
    now = None if now_ts is None else float(now_ts)
    start = _as_int(emission_start)
    duration = _as_int(emission_duration)
    if now is None or start is None or duration is None or start <= 0 or duration < 0:
        return _unavailable(label, "emissions status")

    stop = start + duration
    epoch = _as_int(current_epoch)
    suffix = f" · epoch {epoch}" if epoch is not None else ""

    # PRIMARY: the window has closed.
    if now >= stop:
        return _signal(label, f"emissions ended · {_fmt_duration(now - stop)} ago{suffix}", SIGNAL_MUTED)

    # SECONDARY / legacy: still running.  `stop - now` is strictly positive here.
    return _signal(label, f"emissions live · {_fmt_duration(stop - now)} left{suffix}", SIGNAL_WARN)


# ---------------------------------------------------------------------------
# 4. VRF queue depth
# ---------------------------------------------------------------------------


def vrf_queue_signal(
    last_issued: int | None = None,
    next_to_process: int | None = None,
    pending: int | None = None,
    unsettled: int | None = None,
    unfulfilled_vrf: int | None = None,
    subscription_balance: int | None = None,
    minimum_buffer: int | None = None,
    selection_timeout_blocks: int | None = None,
) -> FWASignal:
    """Acquisition queue depth and VRF subscription solvency (findings §7).

    Depth is ``lastIssuedSequence() - nextSequenceToProcess()`` (live 15-19).

    **A depleted subscription outranks everything else**: when
    ``subscription_balance < minimum_buffer`` the VRF service cannot fund a
    request and *every* acquisition stalls, so that condition takes the row red
    regardless of how shallow the queue looks.

    ``subscription_balance`` and ``minimum_buffer`` are **wei** — the same unit
    as the rest of the model layer.  Both are compared and only rendered
    together, so a caller that passes matching units of anything else still gets
    a correct verdict, just a mislabelled balance.

    A negative depth means ``nextSequenceToProcess`` overtook
    ``lastIssuedSequence``, which is a decode error rather than an empty queue;
    it degrades to unavailable instead of being clamped into a plausible zero.
    """
    label = "VRF QUEUE"

    balance = _as_int(subscription_balance)
    buffer_ = _as_int(minimum_buffer)
    if balance is not None and buffer_ is not None and balance < buffer_:
        return _signal(
            label,
            f"SUBSCRIPTION LOW {_fmt_eth(balance)} < {_fmt_eth(buffer_)} Ξ "
            "— acquisitions stall",
            SIGNAL_BAD,
        )

    issued = _as_int(last_issued)
    next_seq = _as_int(next_to_process)
    if issued is None or next_seq is None:
        return _unavailable(label, "VRF queue")
    depth = issued - next_seq
    if depth < 0:
        return _unavailable(label, "VRF queue")

    parts = [f"depth {depth}"]
    open_requests = _as_int(pending)
    if open_requests is not None:
        parts.append(f"{open_requests} open")
    unsettled_count = _as_int(unsettled)
    if unsettled_count is not None:
        parts.append(f"{unsettled_count} unsettled")
    outstanding = _as_int(unfulfilled_vrf)
    if outstanding:
        parts.append(f"{outstanding} vrf out")

    if depth <= QUEUE_DEPTH_OK:
        color = SIGNAL_GOOD
    else:
        color = SIGNAL_WARN
        timeout = _as_int(selection_timeout_blocks)
        if timeout:
            parts.append(f"stall after {timeout} blk")

    return _signal(label, " · ".join(parts), color)


# ---------------------------------------------------------------------------
# 5. Parameter drift
# ---------------------------------------------------------------------------


def param_drift_signal(
    config_events: Iterable[Any] | None = None,
    live_params: Any = None,
    *,
    launch_block: int | None = None,
) -> FWASignal:
    """Owner parameter changes, measured against on-chain history only.

    The owner is a plain EOA with no multisig and no timelock, and has already
    moved the crown tithe mid-flight, so this row exists to make that visible::

        params nominal                                   (green)
        1 change · crown tithe 500→100                   (yellow)
        4 changes · crown tithe 500→100                  (yellow)
        live ≠ onchain history · 1 key                   (red)
        config history unavailable                       (dim)

    Three things it does **not** do:

    * It never compares against a documented value (PRD §7 rule 6).  The
      ``500→100`` above is the launch write's own emitted value against the
      later ``ConfigSet``; nothing in this module knows what the docs claim.
    * It never counts the launch write.  21 of the 27 ``ConfigSet`` logs are one
      constructor-time write and would otherwise read as 21 drifts
      (findings §13.11).
    * It never implies the owner can still change a constructor-only key.  Keys
      1, 24 and 63 are ``settable: false``; a change involving one is labelled
      ``constructor-only`` explicitly.

    The red branch — live state disagreeing with the last ``ConfigSet`` — is a
    genuine anomaly (a non-emitting write path, or a decode bug on our side) and
    is reported as such rather than being resolved in favour of either source.
    Following the Talismans ``conservation_signal`` posture, an absent live read
    is *not* treated as a mismatch: with nothing to compare, the row reports the
    change count and stays quiet.
    """
    label = "PARAM DRIFT"
    changes = _normalise_events(config_events)
    if not changes:
        return _unavailable(label, "config history")

    excluded = {launch_block} if launch_block is not None else launch_write_blocks(config_events)
    post_launch = [change for change in changes if change.block not in excluded]

    # Values as of the launch write, used purely as the "before" side of a
    # rendered transition.
    launch_values: dict[int, int] = {
        change.key: change.value for change in changes if change.block in excluded
    }

    # Live vs. the last ConfigSet for that key — the only drift comparison.
    last_by_key: dict[int, _ConfigChange] = {change.key: change for change in changes}
    live = _live_map(live_params)
    mismatched = sorted(
        key
        for key, value in live.items()
        if key in last_by_key and last_by_key[key].value != value
    )
    if mismatched:
        names = ", ".join(config_key_name(key, short=True) for key in mismatched[:2])
        more = "" if len(mismatched) <= 2 else f" +{len(mismatched) - 2}"
        plural = "" if len(mismatched) == 1 else "s"
        return _signal(
            label,
            f"live ≠ onchain history · {names}{more} ({len(mismatched)} key{plural})",
            SIGNAL_BAD,
        )

    if not post_launch:
        return _signal(label, "params nominal", SIGNAL_GOOD)

    highlight = _pick_highlight(post_launch)
    count = len(post_launch)
    plural = "" if count == 1 else "s"
    detail = _describe_change(highlight, launch_values, post_launch)
    return _signal(label, f"{count} change{plural} · {detail}", SIGNAL_WARN)


def _pick_highlight(changes: Sequence[_ConfigChange]) -> _ConfigChange:
    """Which change to name in a one-line row.

    Economic parameters beat toggles and addresses — a tithe move tells a reader
    more than the tenth flip of an enable flag — and within a tier the most
    recent change wins.
    """
    economic = [change for change in changes if change.key in _ECONOMIC_KEYS]
    pool = economic or list(changes)
    return max(pool, key=lambda change: change.sort_key)


def _describe_change(
    change: _ConfigChange,
    launch_values: Mapping[int, int],
    post_launch: Sequence[_ConfigChange],
) -> str:
    """``crown tithe 500→100`` — the before value taken from on-chain history."""
    name = config_key_name(change.key, short=True)
    after = _fmt_config_value(change.key, change.value)

    # The "before" is the most recent write to this key preceding `change`,
    # which is the launch write in the common single-change case.
    earlier = [
        other
        for other in post_launch
        if other.key == change.key and other.sort_key < change.sort_key
    ]
    if earlier:
        before_value = max(earlier, key=lambda other: other.sort_key).value
    elif change.key in launch_values:
        before_value = launch_values[change.key]
    else:
        before_value = None

    suffix = "" if is_settable(change.key) else " (constructor-only)"
    if before_value is None or before_value == change.value:
        return f"{name} → {after}{suffix}"
    return f"{name} {_fmt_config_value(change.key, before_value)}→{after}{suffix}"


# ---------------------------------------------------------------------------
# Scalar helpers the manager needs
# ---------------------------------------------------------------------------


def invariant_summary(
    swept_total_weight: int | None = None,
    chain_total_weight: int | None = None,
    swept_weighted_backing: int | None = None,
    chain_weighted_backing: int | None = None,
    derived_fee_wei: int | None = None,
    chain_fee_wei: int | None = None,
    fee_share_total: int | None = None,
    active_listing_count: int | None = None,
) -> bool:
    """``True`` when no runtime invariant has been contradicted.

    Four bit-exact pairs, each checked only when both sides are present:

    * ``Σ(1e36 // backing)`` vs ``totalWeight()``
    * ``Σ(weight × backing)`` vs ``weightedBackingTotal()``
    * the reproduced ``acquisitionFee()`` vs the chain's
    * ``feeShareTotal()`` vs ``activeListingCount()`` (free, always available)

    Every comparison is ``==`` on integers.  A partial sweep that lands on a
    *plausible* total is the most dangerous failure this dashboard has — the
    naive sweep misses 255 slots and is off by exactly ``255e36``, which looks
    fine (PRD §7 rule 11) — so approximate agreement is never accepted.

    Returns ``False`` on any contradiction.  With nothing comparable supplied it
    returns ``True``: this reports "no invariant was violated", and the caller
    signals a *missing* sweep through ``degraded_sources``, not through this
    flag.
    """
    pairs = (
        (swept_total_weight, chain_total_weight),
        (swept_weighted_backing, chain_weighted_backing),
        (derived_fee_wei, chain_fee_wei),
        (fee_share_total, active_listing_count),
    )
    for left, right in pairs:
        if left is None or right is None:
            continue
        if int(left) != int(right):
            return False
    return True


def degraded_label(source: str) -> str:
    """The exact string a widget renders when ``source`` is dead (PRD §9).

    ``"logs"`` -> ``logs unavailable — activity paused``,
    ``"chain"`` -> ``chain unavailable``.  An unrecognised source still gets an
    explicit unavailable string; it never falls through to a blank, and a blank
    row is the one thing degradation may not look like.
    """
    if not source:
        return "unavailable"
    key = str(source).strip().lower()
    return DEGRADED_LABELS.get(key, f"{key} unavailable")


def as_of_label(ts: float | None = None) -> str:
    """``as of 14:32`` for a stale-data header; ``as of --:--`` when unknown.

    Local time, matching every other activity feed in the app
    (``widgets/activity_feed.py``).  An unusable timestamp degrades to the
    placeholder rather than raising inside a render path.
    """
    if ts is None:
        return "as of --:--"
    try:
        return time.strftime("as of %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError, OverflowError):
        return "as of --:--"
