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
from typing import Any

from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, OPS_WALLET
from maxpane_dashboard.data.surf_models import CHANNEL_KINDS

__all__ = [
    "FIRED_TTL_S",
    "STATE_OK",
    "STATE_WATCH",
    "STATE_FIRED",
    "DETAIL_LIMIT",
    "READING_KEYS",
    "BASELINE_SCALARS",
    "BASELINE_EVENT_KEYS",
    "MONOTONIC_BASELINES",
    "decode_utf8_calldata",
    "CHANNEL_KINDS",
    "classify_channel_tx",
    "parity_pct",
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
