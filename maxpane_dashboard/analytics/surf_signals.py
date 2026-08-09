"""Signal analytics for the surfsurf.eth ("SURF") dashboard — PURE functions.

No I/O, no clients, no cache, no Textual, no ``time``.  Everything here takes
plain values and returns plain values, which is what lets the six detectors be
tested against fixed fixtures at a fixed instant, and what lets the manager,
the widgets and the screen all replay the same 2026-08-07 sequence.

Three public pieces:

* :func:`decode_utf8_calldata` — the dev's own monitoring spec (channel nonce
  2, 2026-05-21) says "decode the transaction input/data field as UTF-8 text
  when possible".  *When possible* is the hard half: one of the 21 channel txs
  is an ABI-encoded ``register(string)`` call and must decode to ``None``.
* :func:`classify_channel_tx` — ``self`` / ``reply`` / ``action`` / ``fund``.
  The channel is permissionless: anyone can post, and a scam reply and a
  begging tx are already in it (PRD §6.4).
* :func:`build_signals` — the six detectors of PRD §3 as one state machine over
  (persisted baselines, this refresh's readings, injected clock).

The rule this module exists to enforce
--------------------------------------

**A baseline advances only on a successful read, and ``None`` never compares
against a number.**  The failure it prevents is concrete: ``totalSupply()``
returns ``None`` during an RPC outage, a naive detector reads that as ``0``,
sees 2,376,731 → 0 and fires BURN — and then *persists* the zero, so the
corruption outlives the outage (CLAUDE.md; research §Hazards 5).  The mirror
image is just as bad: an outage must not *un-fire* a FIRED row, because the
one thing a front-runner's dashboard may not do is quietly retract the event it
just reported.  Both cases have dedicated regression tests with recorded
mutation checks (``tests/analytics/test_surf_signals.py``).

FIRED display semantics (PRD §3)
--------------------------------

Baselines advance immediately on the successful read that detects an event — so
a signal re-fires only on a *new* event — but the rendered ``fired`` state
persists for :data:`FIRED_TTL_S` with its age, then relaxes to the live state
with a ``last: …`` detail.  The event timestamps live in the persisted cache,
so a restart neither resurrects nor loses a FIRED display.

Pattern: ``maxpane_dashboard/analytics/fwa_signals.py``.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, OPS_WALLET
from maxpane_dashboard.data.surf_models import CHANNEL_KINDS

__all__ = [
    # constants
    "FIRED_TTL_S",
    "STATE_OK",
    "STATE_WATCH",
    "STATE_FIRED",
    "DETAIL_LIMIT",
    "CHANNEL_KINDS",  # re-export of data.surf_models.CHANNEL_KINDS (WP0)
    "READING_KEYS",
    "BASELINE_SCALARS",
    "BASELINE_EVENT_KEYS",
    "MONOTONIC_BASELINES",
    "SIGNAL_NAMES",
    "SIGNAL_OUTPUT_KEYS",
    # pure functions
    "decode_utf8_calldata",
    "classify_channel_tx",
    "parity_pct",
    "build_signals",
]


#: A rendered ``fired`` row stays ``fired`` for 24 h, then relaxes (PRD §3).
FIRED_TTL_S = 86400

STATE_OK = "ok"
STATE_WATCH = "watch"
STATE_FIRED = "fired"

#: One-line detail budget.  The signals panel gets ~55 columns at the pinned
#: full-layout width, so a message body is truncated to this before the label
#: and quotes are added around it.
DETAIL_LIMIT = 48

#: Every key :func:`build_signals` reads.  Absent **or ``None`` means the read
#: failed** — that is the only outage encoding.  Never ``0``, ``[]`` or
#: ``False``, all of which are legitimate successful values here.
READING_KEYS: tuple[str, ...] = (
    "announce_nonce",       # eth_getTransactionCount(ANNOUNCE) -- the feed number
    "channel_tx_count",     # Blockscout tx count for ANNOUNCE (posts AND replies)
    "announce_last_text",   # decoded body of the newest self-post
    "announce_last_ts",     # unix ts of the newest self-post
    "lp_liquidity",         # NFPM.positions(LP_POSITION_ID).liquidity, raw uint128
    "ops_nonce",            # eth_getTransactionCount(OPS_WALLET) -- frenpet.eth
    "dev_nonce",            # eth_getTransactionCount(DEV_WALLET) -- surfsurf.eth
    "v4_hook_pools",        # [{ts, tx_hash, hooks}] PoolManager Initialize, IMD
    "gate_open",            # IdentityRegistry.identityAllowed()
    "identities_written",   # distinct tokens in IdentityHashUpdated logs
    "deploy_events",        # [{ts, tx_hash, kind, label, wallet_label}]
    "bridge_mints",         # [{ts, tx_hash, amount, to_label}] OFT mints to dev
    "burn_transfers",       # [{ts, tx_hash, amount}] IMD -> BurnExecutor
    "imd_supply",           # IMD.totalSupply() in whole tokens
)

#: Scalar baselines: copied from the matching reading, only when it is not
#: ``None``.
BASELINE_SCALARS: tuple[str, ...] = (
    "announce_nonce",
    "channel_tx_count",
    "lp_liquidity",
    "ops_nonce",
    "dev_nonce",
    "gate_open",
    "identities_written",
    "imd_supply",
)

#: Per-scalar coercion applied by :func:`_advance` *before* the ``is None``
#: check, so persistence is exactly as strict as the matching detector.  A
#: coercer that returns ``None`` makes ``_advance`` treat the reading like a
#: failed read: the previous baseline value is left untouched, never
#: overwritten with something malformed.
#:
#: **Every** :data:`BASELINE_SCALARS` key has an entry here — this is
#: enforced by ``test_every_baseline_scalar_has_a_coercer`` — because the
#: earlier, narrower version of this table (``gate_open`` and ``imd_supply``
#: only) left the other six keys exactly as permissive as before a coercer
#: existed anywhere, and a reviewer proved that gap is exploitable, not just
#: theoretical:
#:
#: * ``gate_open`` was the first case that bit us: ``_detect_gate`` already
#:   refuses a non-``bool`` reading (an int ``0`` is not ``False``), but
#:   ``_advance``'s only guard used to be "not ``None``", so a stray ``0``
#:   sailed straight into the persisted baseline and *changed its type*. The
#:   next cycle's genuine ``False -> True`` flip then read that corrupted
#:   baseline as unset, silently re-seeded, and never fired -- one bad read
#:   permanently disarmed the one transition this detector exists to catch.
#: * ``imd_supply`` needs the mirror-image protection: BURN and BRIDGE STAGE
#:   already refuse to *compare* a non-numeric baseline (both read it through
#:   ``_as_float``, which turns garbage into ``None``), but without a coercer
#:   here ``_advance`` would still persist that garbage raw. The corrupted
#:   baseline would then read back as ``None`` on the very cycle a real burn
#:   or bridge mint lands, and both detectors treat an unset baseline as
#:   "seed, don't fire" -- so a real event is silently swallowed.
#: * every counter -- ``dev_nonce``, ``announce_nonce``, ``channel_tx_count``,
#:   ``ops_nonce``, ``identities_written`` -- had *no* coercer at all until
#:   this table grew to cover them, which was worse than either case above:
#:   ``_as_int(True)`` is ``None`` (a bool is never a nonce), so a bool
#:   reading not only sailed past the "not ``None``" guard but also **bypassed
#:   the ``MONOTONIC_BASELINES`` down-guard** in the same motion -- that guard
#:   compares ``_as_int`` of both sides, and ``current is not None`` was
#:   already ``False`` for a bool, so "don't move backward" never even ran,
#:   and the raw ``True`` sailed straight into ``out[key] = value``.  The
#:   corrupted baseline then reads back as ``None`` on the next cycle,
#:   the same "unset -> silently re-seed, never fire" swallow as the
#:   ``imd_supply`` case, for five more keys.
#:
#: The rule is now general, not key-by-key: add a new key to
#: :data:`BASELINE_SCALARS` and the test above forces a matching entry here in
#: the same change, rather than depending on someone remembering to add one.
#: ``_as_int``/``_as_float`` are looked up by name inside each lambda rather
#: than imported at definition time, which is fine: this dict is only ever
#: consulted from ``_advance``, well after the whole module -- including both
#: helpers -- has finished loading.
_SCALAR_COERCERS: dict[str, Any] = {
    "announce_nonce": lambda value: _as_int(value),
    "channel_tx_count": lambda value: _as_int(value),
    "lp_liquidity": lambda value: _as_int(value),
    "ops_nonce": lambda value: _as_int(value),
    "dev_nonce": lambda value: _as_int(value),
    "gate_open": lambda value: value if isinstance(value, bool) else None,
    "identities_written": lambda value: _as_int(value),
    "imd_supply": lambda value: _as_float(value),
}

#: Event streams: ``reading key -> (tx baseline key, ts baseline key)``.  Two
#: keys per stream rather than one, so a log window that *rolls* (the newest
#: row we can still see is older than the one we already saw) cannot look like
#: a new event.
BASELINE_EVENT_KEYS: dict[str, tuple[str, str]] = {
    "bridge_mints": ("bridge_tx", "bridge_ts"),
    "deploy_events": ("deploy_tx", "deploy_ts"),
    "v4_hook_pools": ("v4_tx", "v4_ts"),
    "burn_transfers": ("burn_tx", "burn_ts"),
}

#: Counters that can only go up.  A lagging RPC replica that answers with an
#: older nonce must not drag the baseline down — the next correct answer would
#: then read as a brand-new post that already happened (a false NEW POST, and
#: the feed body would be a repeat).
MONOTONIC_BASELINES: tuple[str, ...] = (
    "announce_nonce",
    "channel_tx_count",
    "dev_nonce",
    "ops_nonce",
    "identities_written",
)

#: Control characters a real post may legitimately contain.  Everything else
#: below U+0020 means "this is not text".
_ALLOWED_CONTROLS = frozenset({"\n", "\t"})


def decode_utf8_calldata(hex_str: str) -> str | None:
    """Channel calldata as UTF-8 text, or ``None`` when it is not text.

    ``None`` — never a placeholder string, never ``errors="replace"`` — for:
    empty calldata (a plain value transfer), malformed hex, calldata that is
    not valid UTF-8 (the ABI-encoded ``register(string)`` call at nonce 4), and
    text containing NUL, which is what ABI zero-padding decodes to.

    The text is returned **raw**: typographic quotes, em-dashes and embedded
    newlines are preserved byte-for-byte and nothing is escaped.  Escaping is
    the widget layer's job (``widgets/markup_safety.safe_markup``); escaping
    here would double-escape downstream.  CRLF is normalised to LF and the
    result is stripped, because the feed renders one message per row.
    """
    if not isinstance(hex_str, str):
        return None
    body = hex_str.strip()
    if body[:2].lower() == "0x":
        body = body[2:]
    if not body or len(body) % 2:
        return None
    try:
        raw = bytes.fromhex(body)
    except ValueError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if any(ch < " " and ch not in _ALLOWED_CONTROLS for ch in text):
        return None
    text = text.strip()
    return text or None


# The four feed kinds (PRD §4) come from WP0's data/surf_models.py and are
# re-exported above, never redefined.  ``self`` is the dev's broadcast,
# ``action`` is the channel EOA doing something onchain, ``fund`` is a dev
# wallet paying the channel's gas, ``reply`` is everyone else — and everyone
# else can write anything, so replies are rendered distinctly and never as the
# dev's words.

_CHANNEL = ANNOUNCE.lower()
_DEV_WALLETS = frozenset({DEV_WALLET.lower(), OPS_WALLET.lower()})


def _as_int(value: Any) -> int | None:
    """Coerce to ``int``; ``None`` when missing or unparseable.

    ``bool`` is rejected: ``True`` is never a nonce, and reading it as ``1`` is
    exactly how a failed read becomes a plausible number.  Hex strings are
    accepted because raw ``eth_call`` returns arrive that way.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == int(value) else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError:
            return None
    return None


def _addr(value: Any) -> str:
    """Lowercased address, or ``""``.

    Case matters here and only here: the RPC answers lowercase, Blockscout
    answers checksummed, and a case-sensitive comparison would classify the
    same tx differently depending on which source fetched it.
    """
    return value.strip().lower() if isinstance(value, str) else ""


def classify_channel_tx(
    from_addr: str,
    to_addr: str,
    value_wei: int,
    input_hex: str,
) -> str:
    """One of :data:`CHANNEL_KINDS` for a tx involving the announce channel.

    Order matters, and it is the dev's own filter order (channel nonce 2):

    1. ``from == to == channel`` -> ``self``.  A post.
    2. ``from == channel`` -> ``action``.  The channel EOA doing something
       onchain — the ERC-8004 ``register()`` at nonce 4 is this, and NEW DEPLOY
       watches for the next one.  ``to = None`` (a deployment) lands here too.
    3. ``from`` is a dev wallet **and** (value moved **or** the calldata is not
       a message) -> ``fund``.  A dev wallet that writes a readable message is
       a ``reply``, because the feed prints these kinds next to the message and
       calling a message "fund" would be wrong on screen.
    4. everything else -> ``reply``.

    ``value_wei`` never promotes a stranger: the begging tx sent 1e13 wei and
    is still a reply.  Nothing here raises — a missing address is ``""``, a
    missing value is ``0`` — because this runs inside the feed builder.
    """
    src = _addr(from_addr)
    dst = _addr(to_addr)
    if src == _CHANNEL:
        return "self" if dst == _CHANNEL else "action"
    if src in _DEV_WALLETS:
        value = _as_int(value_wei) or 0
        if value > 0 or decode_utf8_calldata(input_hex) is None:
            return "fund"
    return "reply"


def _as_float(value: Any) -> float | None:
    """Coerce to ``float``; ``None`` when missing, unparseable, or not finite.

    ``bool`` is rejected for the same reason as in :func:`_as_int`.  ``inf``,
    ``-inf`` and ``nan`` are rejected too, whether they arrive as a native
    float or by parsing a string: third-party keyless market payloads are not
    under our control, and ``float("1e400")`` overflows to ``inf`` silently
    rather than raising, so an overflowing numeric string would otherwise sail
    straight through as a "valid" price.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            result = float(value)
        except OverflowError:
            return None
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            result = float(int(text, 16)) if text.lower().startswith("0x") else float(text)
        except (ValueError, OverflowError):
            return None
    else:
        return None
    return result if math.isfinite(result) else None


def parity_pct(imd_price_usd: float | None, fp_price_usd: float | None) -> float | None:
    """IMD's premium/discount to FP in percent, signed.  ``None`` if unknown.

    IMD is FP bridged 1:1 (FP locks on Base via the OFT adapter, IMD mints on
    mainnet), so the pair should trade together and the spread is a real health
    metric rather than decoration.  Computed every refresh — the 33.0% bridged
    share and this spread both move with every bridge tx and are never
    hardcoded (PRD §6.2).

    A missing or non-positive FP price yields ``None``, never ``0.0``: on a
    dead market feed "0%" reads as *at parity*, which is a statement the
    dashboard has no basis to make.  Two finite inputs can still divide out to
    a non-finite result (``1e308 / 1e-308`` overflows to ``inf``), so the
    computed ratio is checked too, not just the inputs: ``inf%``/``nan%`` on
    screen would read as a genuine depeg rather than as missing data.
    """
    imd = _as_float(imd_price_usd)
    fp = _as_float(fp_price_usd)
    if imd is None or fp is None or fp <= 0:
        return None
    result = (imd / fp - 1.0) * 100.0
    return result if math.isfinite(result) else None


def _fmt_amount(value: float) -> str:
    """``114366.899256`` -> ``114,367``; small amounts keep two decimals."""
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:,.2f}"


def _truncate(text: str, limit: int = DETAIL_LIMIT) -> str:
    """Collapse whitespace to one line and cut at ``limit`` with an ellipsis.

    Channel messages carry embedded newlines and two-space indentation; a
    signal detail is a single row, so the flattening is part of the contract
    rather than the widget's problem.
    """
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _short_addr(value: Any) -> str:
    """``0x`` + first 8 + ``…`` + last 6 — the PRD §4 untrusted-address form.

    Long enough to compare against a known address by eye, short enough for a
    signal row, and never a label: live look-alike spoofs of both fee
    recipients are in frenpet.eth's history today (research §Hazards 2).
    """
    text = value.strip() if isinstance(value, str) else ""
    if len(text) < 20:
        return text
    return f"{text[:10]}…{text[-6:]}"


# ---------------------------------------------------------------------------
# The six detectors
# ---------------------------------------------------------------------------


class _Det(NamedTuple):
    """One detector's verdict for one refresh.

    ``fired_ts`` set means *this refresh detected the event*; the state machine
    then records it in the persisted fired store.  ``state = None`` means the
    inputs this detector needs were unavailable — explicitly unknown, which is
    a different thing from ``ok``.
    """

    state: str | None
    detail: str
    fired_ts: float | None = None


def _ok(detail: str) -> _Det:
    return _Det(STATE_OK, detail, None)


def _watch(detail: str) -> _Det:
    return _Det(STATE_WATCH, detail, None)


def _fired(detail: str, ts: float | None) -> _Det:
    return _Det(STATE_FIRED, detail, ts)


def _dead(detail: str) -> _Det:
    return _Det(None, detail, None)


def _rows(events: Any) -> list[dict]:
    """The dict rows of an event list; anything else is dropped.

    A single malformed row must not take a detector down — it is a log decode
    away from an attacker-influenced field.
    """
    if not isinstance(events, (list, tuple)):
        return []
    return [row for row in events if isinstance(row, dict)]


def _newest(rows: list[dict]) -> dict | None:
    """The row with the highest ``ts``; ``None`` for an empty list."""
    if not rows:
        return None
    return max(rows, key=lambda row: _as_float(row.get("ts")) or 0.0)


_ZERO_ADDRESS = "0x" + "0" * 40


def _event_rows(read_key: str, events: Any) -> list[dict] | None:
    """Normalised rows for an event stream; ``None`` when the read failed.

    ``v4_hook_pools`` is filtered here rather than in the detector so the
    baseline and the detector agree: all 19 live IMD v4 pools are third-party
    and **hookless**, and a hookless ``Initialize`` is noise, not the launch.
    Filtering in one place only would let noise advance the baseline past a
    real hooked pool.
    """
    if events is None:
        return None
    rows = _rows(events)
    if read_key == "v4_hook_pools":
        rows = [
            row
            for row in rows
            if _addr(row.get("hooks")) not in ("", _ZERO_ADDRESS)
        ]
    return rows


def _fresh_event(base: dict, tx_key: str, ts_key: str, rows: list[dict] | None) -> dict | None:
    """The newest event that is genuinely new, or ``None``.

    Three ways this returns ``None``, and each one is a bug that would
    otherwise ship:

    * ``rows is None`` — the read failed.  An outage detects nothing.
    * the baseline key is **absent** — this is the first successful read of
      this window ever, so it *seeds*.  Without this, an empty cache reports
      every historical event as breaking news on first launch.
    * the newest row is the one already recorded, or is **older** than it — the
      log window rolled, and a window that lost its newest row must not make
      the second-newest look new.
    """
    if not rows:
        return None
    newest = _newest(rows)
    if newest is None:
        return None
    seen_tx = base.get(tx_key)
    if seen_tx is None:
        return None
    if str(newest.get("tx_hash") or "") == str(seen_tx):
        return None
    ts = _as_float(newest.get("ts")) or 0.0
    if ts <= (_as_float(base.get(ts_key)) or 0.0):
        return None
    return newest


# --- 1. NEW POST -----------------------------------------------------------


def _detect_post(base: dict, read: dict, now: float) -> _Det:
    """Channel nonce moved -> the dev posted (PRD §3 #1).

    The cheapest and earliest of the six: these txs emit **no logs**, so every
    event-driven watcher is structurally blind to them and a nonce poll sees a
    post within one refresh interval.  ``channel_tx_count`` moving without the
    nonce means somebody *else* wrote to the channel — worth a WATCH, never a
    post.
    """
    nonce = _as_int(read.get("announce_nonce"))
    if nonce is None:
        return _dead("channel unavailable")

    base_nonce = _as_int(base.get("announce_nonce"))
    if base_nonce is None:
        return _ok(f"nonce {nonce} · baseline set")

    if nonce > base_nonce:
        text = read.get("announce_last_text")
        body = f' "{_truncate(text)}"' if isinstance(text, str) and text.strip() else ""
        return _fired(f"#{nonce}{body}", _as_float(read.get("announce_last_ts")))

    tx_count = _as_int(read.get("channel_tx_count"))
    base_txs = _as_int(base.get("channel_tx_count"))
    if tx_count is not None and base_txs is not None and tx_count > base_txs:
        return _watch(f"reply on channel · {tx_count} txs")

    return _ok(f"nonce {nonce} · no new post")


# --- 2. LP MIGRATION -------------------------------------------------------


def _detect_lp(base: dict, read: dict, now: float) -> _Det:
    """The next launch's watchable precondition (PRD §3 #2).

    Escalating order, strongest first:

    1. a PoolManager ``Initialize`` for IMD with ``hooks != 0x0`` — that log
       *is* the launch.  Hookless initialisations are third-party noise and are
       filtered upstream in :func:`_event_rows`.
    2. liquidity **down** on position #1167726 — the act he promised to
       announce before performing.
    3. liquidity **up**, or any frenpet.eth nonce movement — precursors.  The
       2026-08-07 add was both.

    A liquidity read of ``None`` produces no comparison at all.  It also cannot
    un-fire anything: the FIRED store is applied by :func:`build_signals`
    independently of what this returns.
    """
    hooked = _event_rows("v4_hook_pools", read.get("v4_hook_pools"))
    launch = _fresh_event(base, "v4_tx", "v4_ts", hooked)
    if launch is not None:
        hooks = _short_addr(launch.get("hooks"))
        return _fired(f"V4 LAUNCH · hooks {hooks}", _as_float(launch.get("ts")))

    liquidity = _as_int(read.get("lp_liquidity"))
    base_liquidity = _as_int(base.get("lp_liquidity"))
    if liquidity is not None and base_liquidity is not None and base_liquidity > 0:
        if liquidity < base_liquidity:
            drop = 100.0 * (base_liquidity - liquidity) / base_liquidity
            return _fired(f"LIQUIDITY OUT -{drop:.1f}%", now)
        if liquidity > base_liquidity:
            rise = 100.0 * (liquidity - base_liquidity) / base_liquidity
            return _watch(f"LP added +{rise:.1f}%")

    ops_nonce = _as_int(read.get("ops_nonce"))
    base_ops = _as_int(base.get("ops_nonce"))
    if ops_nonce is not None and base_ops is not None and ops_nonce > base_ops:
        return _watch(f"frenpet.eth active · nonce {ops_nonce}")

    if liquidity is None:
        return _dead("LP state unavailable")
    if base_liquidity is None:
        return _ok("liquidity baseline set")
    return _ok("liquidity holds")


# --- 3. GATE OPEN ------------------------------------------------------------


def _detect_gate(base: dict, read: dict, now: float) -> _Det:
    """``identityAllowed()`` false -> true (PRD §3 #3).

    Closed since 2026-05-14 with one identity written, so ``ok`` is the state
    this row lives in — and it still spells the gate's condition out, because a
    detector row that says nothing about the thing it watches is useless when
    it is quiet.

    An ``IdentityHashUpdated`` count that moves while we still read the gate as
    closed means the gate opened and closed between two polls; that is a WATCH,
    not a miss to be swallowed.  The written count carries no ``/2000``: the
    cap is documented, and documented numbers are read live elsewhere or not
    shown (CLAUDE.md rule 4).
    """
    gate = read.get("gate_open")
    gate = gate if isinstance(gate, bool) else None
    written = _as_int(read.get("identities_written"))
    suffix = f" · {written} written" if written is not None else ""

    if gate is None:
        return _dead(f"gate unavailable{suffix}" if written is not None else "gate unavailable")

    word = "OPEN" if gate else "closed"
    base_gate = base.get("gate_open")
    base_gate = base_gate if isinstance(base_gate, bool) else None
    if base_gate is None:
        return _ok(f"{word}{suffix}")

    if gate and not base_gate:
        return _fired(f"GATE OPEN{suffix}", now)

    base_written = _as_int(base.get("identities_written"))
    if written is not None and base_written is not None and written > base_written:
        return _watch(f"{base_written}→{written} written · gate {word.lower()}")

    return _ok(f"{word}{suffix}")


# --- 4. NEW DEPLOY -----------------------------------------------------------


def _detect_deploy(base: dict, read: dict, now: float) -> _Det:
    """A new contract, or the announce EOA calling one (PRD §3 #4).

    The ERC-8004 registration at channel nonce 4 was the second shape, and the
    "P2P decentralized harness" is expected to surface the same way, so both
    count.  ``dev_nonce`` moving with no contract behind it is a WATCH —
    surfsurf.eth is the deployer wallet; frenpet.eth's movements belong to LP
    MIGRATION.

    ``label`` reaches here from Blockscout and is third-party text; it is
    passed through untouched and escaped at the widget, never here.
    """
    events = _event_rows("deploy_events", read.get("deploy_events"))
    fresh = _fresh_event(base, "deploy_tx", "deploy_ts", events)
    if fresh is not None:
        label = str(fresh.get("label") or "")
        if str(fresh.get("kind") or "") == "action":
            head = f"action {label}" if label else "onchain action"
        else:
            head = f"new contract {_short_addr(label)}" if label else "new contract"
        who = str(fresh.get("wallet_label") or "")
        detail = f"{head} · {who}" if who else head
        return _fired(detail, _as_float(fresh.get("ts")))

    dev_nonce = _as_int(read.get("dev_nonce"))
    base_dev = _as_int(base.get("dev_nonce"))
    if dev_nonce is not None and base_dev is not None and dev_nonce > base_dev:
        return _watch(f"surfsurf.eth nonce {base_dev}→{dev_nonce}")

    if events is None and dev_nonce is None:
        return _dead("dev activity unavailable")
    return _ok("no new contract")


# --- 5. BRIDGE STAGE -------------------------------------------------------


def _detect_bridge(base: dict, read: dict, now: float) -> _Det:
    """OFT bridge-in mints to a dev wallet (PRD §3 #5).

    IMD has no mint function: supply exists only via ``lzReceive`` from an
    owner-set peer, so ``Transfer(from=0x0, to=dev)`` is unambiguous staging.
    On 2026-08-07 the first mint landed 264 s before the LP add and 492 s
    before the announcement — the earliest warning of the five.

    Supply rising with no matching mint means somebody *else* bridged in; that
    is a WATCH, and it is only computed when both supply reads succeeded.
    """
    mints = _event_rows("bridge_mints", read.get("bridge_mints"))
    fresh = _fresh_event(base, "bridge_tx", "bridge_ts", mints)
    if fresh is not None:
        amount = _as_float(fresh.get("amount"))
        rendered = _fmt_amount(amount) if amount is not None else "?"
        who = str(fresh.get("to_label") or "dev wallet")
        return _fired(f"mint {rendered} IMD → {who}", _as_float(fresh.get("ts")))

    supply = _as_float(read.get("imd_supply"))
    base_supply = _as_float(base.get("imd_supply"))
    if supply is not None and base_supply is not None and supply > base_supply:
        return _watch(f"supply +{_fmt_amount(supply - base_supply)} · no dev-wallet mint")

    if mints is None:
        return _dead("bridge logs unavailable")
    return _ok("no mints in window")


# --- 6. BURN ---------------------------------------------------------------


def _detect_burn(base: dict, read: dict, now: float) -> _Det:
    """A verified supply decrease, with a transfer-to-executor precursor.

    **Both reads must have succeeded.**  This is the regression the whole
    module is shaped around: an outage that reads as ``0`` turns 2,376,731 into
    a 100% burn, fires the signal, and then persists the zero.  ``supply is
    None`` therefore never reaches a comparison, and the row degrades to an
    explicit unavailable state instead (CLAUDE.md; research §Hazards 5).

    Informational rather than actionable — it feeds the supply sparkline — but
    a false one would discredit every other row on the panel.
    """
    supply = _as_float(read.get("imd_supply"))
    base_supply = _as_float(base.get("imd_supply"))
    if supply is not None and base_supply is not None and supply < base_supply:
        return _fired(f"burn {_fmt_amount(base_supply - supply)} IMD", now)

    transfers = _event_rows("burn_transfers", read.get("burn_transfers"))
    fresh = _fresh_event(base, "burn_tx", "burn_ts", transfers)
    if fresh is not None:
        amount = _as_float(fresh.get("amount"))
        rendered = _fmt_amount(amount) if amount is not None else "?"
        return _watch(f"{rendered} IMD → BurnExecutor")

    if supply is None:
        return _dead("supply unavailable")
    if base_supply is None:
        return _ok("supply baseline set")
    return _ok("supply flat")


# --- registry --------------------------------------------------------------

#: ``(name, detector)`` in render order.  :data:`SIGNAL_NAMES` and
#: :data:`SIGNAL_OUTPUT_KEYS` are derived from it, so the module can never
#: advertise a key it does not emit.
_DETECTORS: tuple[tuple[str, Any], ...] = (
    ("post", _detect_post),
    ("lp", _detect_lp),
    ("gate", _detect_gate),
    ("deploy", _detect_deploy),
    ("bridge", _detect_bridge),
    ("burn", _detect_burn),
)

SIGNAL_NAMES: tuple[str, ...] = tuple(name for name, _ in _DETECTORS)

#: The PRD §5 signal keys, in order: ``sig_<name>_state|detail|age_s``.
SIGNAL_OUTPUT_KEYS: tuple[str, ...] = tuple(
    f"sig_{name}_{field}"
    for name in SIGNAL_NAMES
    for field in ("state", "detail", "age_s")
)


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------


def _fired_store(baselines: dict) -> dict[str, dict]:
    """The persisted ``{signal: {ts, detail}}`` map, defensively parsed."""
    raw = baselines.get("fired")
    store: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return store
    for name, entry in raw.items():
        if name not in SIGNAL_NAMES or not isinstance(entry, dict):
            continue
        ts = _as_float(entry.get("ts"))
        if ts is None:
            continue
        store[name] = {"ts": ts, "detail": str(entry.get("detail") or "")}
    return store


def _advance(baselines: dict, readings: dict) -> dict:
    """The baselines to persist after this refresh.

    Three rules, and every correctness bug in this module is one of them being
    skipped:

    1. A scalar baseline moves **only** when its reading is not ``None`` --
       and only when it also survives that scalar's own coercer in
       :data:`_SCALAR_COERCERS`, which covers every :data:`BASELINE_SCALARS`
       key, not a chosen few.  A malformed reading is treated exactly like a
       failed one: the previous value is left in place, never overwritten
       with something a detector could not have produced itself (CLAUDE.md; a
       real regression -- see :data:`_SCALAR_COERCERS`).
    2. Counters in :data:`MONOTONIC_BASELINES` never move down.

    Event streams keep ``(tx, ts)``.  A *successful but empty* read seeds the
    pair with ``("", 0.0)`` — "the window was read and held nothing" — which is
    what lets the next event fire; an outage (``None``) leaves the pair alone.
    """
    out = {key: value for key, value in baselines.items() if key != "fired"}

    for key in BASELINE_SCALARS:
        value = readings.get(key)
        coerce = _SCALAR_COERCERS.get(key)
        if coerce is not None:
            value = coerce(value)
        if value is None:
            continue
        if key in MONOTONIC_BASELINES:
            previous = _as_int(out.get(key))
            current = _as_int(value)
            if previous is not None and current is not None and current < previous:
                continue
        out[key] = value

    for read_key, (tx_key, ts_key) in BASELINE_EVENT_KEYS.items():
        rows = _event_rows(read_key, readings.get(read_key))
        if rows is None:
            continue
        newest = _newest(rows)
        if newest is None:
            if tx_key not in out:
                out[tx_key] = ""
                out[ts_key] = 0.0
            continue
        ts = _as_float(newest.get("ts")) or 0.0
        previous_ts = _as_float(out.get(ts_key))
        if previous_ts is None or ts >= previous_ts:
            out[tx_key] = str(newest.get("tx_hash") or "")
            out[ts_key] = ts

    return out


def build_signals(
    baselines: dict,
    readings: dict,
    now_ts: float,
) -> tuple[dict, dict]:
    """The detector rows plus the baselines to persist.

    Returns ``(signals, advanced_baselines)`` where ``signals`` holds exactly
    :data:`SIGNAL_OUTPUT_KEYS`.

    The FIRED store is consulted **before** the live state is rendered and
    regardless of whether this refresh could read anything, which is the rule
    that stops a network blip from silently retracting an event the user was
    already shown.  A relaxed row keeps the event as ``last: …`` and keeps its
    age, so "nothing is happening" and "nothing has *ever* happened" never look
    the same.

    A detector may also *detect* an event that is already older than the TTL —
    a wide log window against a cold cache.  That is recorded as history and
    rendered ``ok`` with a ``last: …`` detail rather than as a fresh FIRED row:
    the same instinct as the first-sweep seeding rule, one layer up.

    ``now_ts`` is injected and there is no wall-clock fallback: that is what
    makes the 2026-08-07 replay reproducible forever.
    """
    base = baselines if isinstance(baselines, dict) else {}
    read = readings if isinstance(readings, dict) else {}
    now = float(now_ts)

    fired = _fired_store(base)
    signals: dict[str, Any] = {}

    for name, detect in _DETECTORS:
        det = detect(base, read, now)
        if det.fired_ts is not None or det.state == STATE_FIRED:
            event_ts = det.fired_ts if det.fired_ts is not None else now
            fired[name] = {"ts": min(float(event_ts), now), "detail": det.detail}

        entry = fired.get(name)
        if entry is not None and now - entry["ts"] < FIRED_TTL_S:
            signals[f"sig_{name}_state"] = STATE_FIRED
            signals[f"sig_{name}_detail"] = entry["detail"]
            signals[f"sig_{name}_age_s"] = max(0.0, now - entry["ts"])
            continue

        state = det.state
        detail = det.detail
        if state == STATE_FIRED:
            # Detected now, but the event itself is older than the TTL -- a wide
            # log window on a cold cache.  That is history, not news: the row
            # must not shout, and the text survives in the `last:` clause.
            state = STATE_OK
            detail = ""
        if entry is not None:
            detail = f"{detail} · last: {entry['detail']}" if detail else f"last: {entry['detail']}"
        signals[f"sig_{name}_state"] = state
        signals[f"sig_{name}_detail"] = detail
        signals[f"sig_{name}_age_s"] = None if entry is None else max(0.0, now - entry["ts"])

    advanced = _advance(base, read)
    advanced["fired"] = {name: dict(entry) for name, entry in fired.items()}
    return signals, advanced
