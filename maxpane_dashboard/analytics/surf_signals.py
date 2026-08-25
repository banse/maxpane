"""Signal analytics for the surfsurf.eth ("SURF") dashboard — PURE functions.

No I/O, no clients, no cache, no Textual, no ``time``.  Everything here takes
plain values and returns plain values, which is what lets the nine detectors
be tested against fixed fixtures at a fixed instant, and what lets the
manager, the widgets and the screen all replay the same 2026-08-07 sequence.

Three public pieces:

* :func:`decode_utf8_calldata` — the dev's own monitoring spec (channel nonce
  2, 2026-05-21) says "decode the transaction input/data field as UTF-8 text
  when possible".  *When possible* is the hard half: one of the 21 channel txs
  is an ABI-encoded ``register(string)`` call and must decode to ``None``.
* :func:`classify_channel_tx` — ``self`` / ``reply`` / ``answer`` / ``action``
  / ``fund``.
  The channel is permissionless: anyone can post, and a scam reply and a
  begging tx are already in it (PRD §6.4).
* :func:`build_signals` — the nine detectors of PRD §3 as one state machine
  over (persisted baselines, this refresh's readings, injected clock).  The
  last three (DECOY POOL, BURN READY, HOT COIN) are the v4-launchpad
  additions: LP MIGRATION fired on 2026-08-17 and the migration it watched
  for is finished, so its slot is re-aimed at the v4 position (``lp`` stays
  the payload prefix) rather than re-armed for a second launch.

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

from maxpane_dashboard.analytics.surf_launchpad import HOT_MAX_AGE_S, hot_coin_threshold
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
    # NEW REPLY's stream: the channel rows that are somebody answering or
    # being answered -- ``kind in {reply, answer}`` -- newest last. An event
    # stream rather than a counter because the row has to quote the message,
    # and because a count read off a capped page saturates in silence.
    "channel_threads",      # [{ts, tx_hash, kind, text}] replies and answers
    "lp_liquidity",         # NFPM.positions(LP_POSITION_ID).liquidity, raw uint128
    # Final fix wave (C2). PositionManager.balanceOf(OPS_WALLET) on the v4
    # side -- how many v4 LP positions frenpet.eth holds. This is LP MOVE's
    # numeric subject; `lp_liquidity` above is the BURNED v3 position and can
    # only ever read `None` now, which is why the row could never fire.
    "lp_position_count",    # v4 PositionManager.balanceOf(OPS_WALLET)
    "ops_nonce",            # eth_getTransactionCount(OPS_WALLET) -- frenpet.eth
    "dev_nonce",            # eth_getTransactionCount(DEV_WALLET) -- surfsurf.eth
    "v4_hook_pools",        # [{ts, tx_hash, hooks}] PoolManager Initialize, IMD
    "gate_open",            # IdentityRegistry.identityAllowed()
    "identities_written",   # distinct tokens in IdentityHashUpdated logs
    "deploy_events",        # [{ts, tx_hash, kind, label, wallet_label}]
    "bridge_mints",         # [{ts, tx_hash, amount, to_label}] OFT mints to dev
    "burn_transfers",       # [{ts, tx_hash, amount}] IMD -> BurnExecutor
    "imd_supply",           # IMD.totalSupply() in whole tokens
    # -- v4-launchpad additions (Task 7): fed by surf_manager._readings()
    # off the launchpad slot and the flat hero payload, not READING_KEYS'
    # own six original sources above.
    "decoy_pool_count",         # count of third-party ETH/IMD-look-alike pools
    "decoy_newest_fee_bps",     # fee tier of the newest decoy pool, if read
    "burn_ready",               # tri-state: previewBridge() would send > 0
    "burn_accrued",             # imdToBurn in whole IMD, awaiting the burn bridge
    "burn_bridgeable",          # previewBridge().amountToSend in whole IMD
    "launchpad_swaps_by_coin",  # {pool_id: swap_count} -- the FULL in-window population
    "launchpad_coin_tickers",   # {pool_id: ticker} -- the LABEL map, joins on nothing
    # Final fix wave (C1). When the sweep that produced the distribution above
    # actually ran, epoch seconds -- the launchpad slot's own ``LastGood.ts``.
    # ``launchpad_swaps_by_coin`` is served from a last-good slot that never
    # expires, so without this the row cannot tell "40 swaps this hour" from
    # "40 swaps in an hour that ended yesterday": see ``HOT_MAX_AGE_S``.
    "launchpad_swaps_ts",       # float | None — when the distribution was read
)

#: Scalar baselines: copied from the matching reading, only when it is not
#: ``None``.
BASELINE_SCALARS: tuple[str, ...] = (
    "announce_nonce",
    "channel_tx_count",
    # What NEW POST actually compares against. The nonce alone cannot tell a
    # post from an answer or a contract call -- all three are txs the announce
    # wallet sent -- so firing on the nonce quoted ``announce_last_text``,
    # which is the newest *self-post*, for events that were not one.
    "announce_last_ts",
    "lp_liquidity",
    # Final fix wave (C2): LP MOVE compares against this, not against the
    # burned v3 position's liquidity.
    "lp_position_count",
    "ops_nonce",
    "dev_nonce",
    "gate_open",
    "identities_written",
    "imd_supply",
    "decoy_pool_count",
    # fix round 1: BURN READY became an edge detector and needs a baseline
    # to tell "already reported" from "just became callable" (see
    # _detect_burn_ready).
    "burn_ready",
    # Final fix wave (C1): HOT COIN became an edge for the same reason, and
    # needs to remember WHICH coin was over the bar (by ``pool_id``, its
    # identity -- see I1). Unlike every other entry
    # here this one is **derived, not read**: no source hands us "who is hot",
    # it is this module's own conclusion about the distribution. It is computed
    # once in ``build_signals`` -- through the same ``_hot_leader_name`` helper
    # the detector's own verdict comes from, so the row and the baseline can
    # never disagree about who was hot -- and injected into the readings there.
    "hot_leader",
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
    "announce_last_ts": lambda value: _as_float(value),
    "lp_liquidity": lambda value: _as_int(value),
    "lp_position_count": lambda value: _as_int(value),
    "ops_nonce": lambda value: _as_int(value),
    "dev_nonce": lambda value: _as_int(value),
    "gate_open": lambda value: value if isinstance(value, bool) else None,
    "identities_written": lambda value: _as_int(value),
    "imd_supply": lambda value: _as_float(value),
    "decoy_pool_count": lambda value: _as_int(value),
    "burn_ready": lambda value: value if isinstance(value, bool) else None,
    # The hot coin's *identity* -- its ``pool_id`` -- never its ticker (final
    # fix wave, I1): two coins can share a ticker, and an edge keyed on the
    # label would miss the lead changing hands between them. It is persisted
    # to disk, so it is accepted only as a bounded str; a read-back value of
    # any other shape is treated as a failed read and the previous leader
    # survives rather than being overwritten with something no detector could
    # have produced. The bound is generous against a 66-char pool id and
    # exists so a decoder change upstream cannot grow the cache file without
    # limit.
    "hot_leader": lambda value: (
        value if isinstance(value, str) and len(value) <= 80 else None
    ),
}

#: Event streams: ``reading key -> (tx key, ts key, sequence key)``.  Three
#: keys per stream rather than one:
#:
#: * ``tx`` alone cannot tell a *rolled* window (the newest row we can still
#:   see is older than the one we already saw) from a new event;
#: * ``ts`` alone is **not a total order over these rows**, and the ties are
#:   ordinary rather than exotic.  ``_log_ts`` stamps a whole group with one
#:   observation clock whenever the endpoint omits ``blockTimestamp`` (drpc
#:   does; tenderly does not — both are in the logs pool), and two events in
#:   one block carry identical real timestamps whatever the endpoint sends.
#:   Under either, ``max(rows, key=ts)`` returns the FIRST maximal row, which
#:   for the ascending order ``eth_getLogs`` serves is the *oldest* — the one
#:   the baseline already holds — so a genuinely new event behind it was
#:   invisible, and then fired hours later when the old row rolled out.
#: * ``sequence`` is ``[block, log_index]``, which the client preserves
#:   verbatim on every row and the manager's decoders now carry through.  It is
#:   a real chain ordering rather than list position: ``deploy_events`` is
#:   sorted newest-first by the manager while the log streams stay ascending,
#:   so position means opposite things on one code path.
BASELINE_EVENT_KEYS: dict[str, tuple[str, str, str]] = {
    "bridge_mints": ("bridge_tx", "bridge_ts", "bridge_seq"),
    "deploy_events": ("deploy_tx", "deploy_ts", "deploy_seq"),
    "v4_hook_pools": ("v4_tx", "v4_ts", "v4_seq"),
    "burn_transfers": ("burn_tx", "burn_ts", "burn_seq"),
    "channel_threads": ("thread_tx", "thread_ts", "thread_seq"),
}

#: Counters that can only go up.  A lagging RPC replica that answers with an
#: older nonce must not drag the baseline down — the next correct answer would
#: then read as a brand-new post that already happened (a false NEW POST, and
#: the feed body would be a repeat).
MONOTONIC_BASELINES: tuple[str, ...] = (
    "announce_nonce",
    "channel_tx_count",
    # A post does not become older. A page that comes back one post short
    # while the nonce still matches would otherwise drag this down, and the
    # next correct read would then re-fire a post already reported.
    "announce_last_ts",
    "dev_nonce",
    "ops_nonce",
    "identities_written",
    # Nobody "un-deploys" a Uniswap pool: a lagging scan replica that answers
    # with a smaller decoy count must not drag this baseline down either, for
    # the same reason as the five counters above it.
    "decoy_pool_count",
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
    success: bool | None = None,
) -> str:
    """One of :data:`CHANNEL_KINDS` for a tx involving the announce channel.

    Order matters, and it is the dev's own filter order (channel nonce 2):

    0. ``success is False`` -> ``failed``, before anything else is asked.
       A reverted tx changed nothing on chain, so every question below it —
       was this a post, an answer, a call — is a question about an intention
       rather than an event. 0xTXT gates on ``receiptSuccess`` in exactly
       this position (`0x/packages/protocol/src/surf.ts`) and drops the row;
       this keeps it and labels it, because a dev whose call reverted is
       worth seeing and a silently vanished row is the failure mode this
       repo keeps recording. It costs no width: ``FAILED`` is six characters
       like ``ANSWER`` and ``ACTION``, and the badge cell is already six.

       The two shapes it protects fail differently. A reverted ``answer``
       would print a body nobody successfully published. A reverted
       ``action`` is worse: NEW DEPLOY selects ``kind == "action"``, so it
       would fire "new contract" for a deployment that did not happen — the
       same defect the ``answer`` split fixed, by the same mechanism, since
       the filter needs no change once the kind stops matching.

       ``None`` is not ``False``. An unstated status leaves the tx classified
       on its own shape, because "the page did not say" and "the chain
       rejected it" are different facts and only the second is a failure.
    1. ``from == to == channel`` -> ``self``.  A post.
    2. ``from == channel``, ``value == 0`` and the calldata decodes as text
       -> ``answer``.  0xTXT (`0x/packages/protocol/src/surf.ts`,
       ``classifySurfTransaction``) calls this shape ``legacy-reply``: an
       *authenticated* answer from the announce wallet to somebody who wrote
       to it — channel nonce 23 answering nonce 17's question is the real
       example.  Both guards are the reference implementation's own:
       ``transaction.value === 0n`` (nonce 16 sent 0.05 ETH with empty
       calldata and is a payment, not a message — it must stay ``action``)
       and calldata that fails to decode is a contract call, not a reply.
       Classifying this shape ``action`` used to be more than a mislabel: NEW
       DEPLOY reads ``action`` rows off the channel and labels them with the
       decoded method or the first four calldata bytes, so a dev answer
       beginning "Yes the goal is…" entered that stream labelled
       ``0x59657320`` — the ASCII for "Yes " — and could fire the detector on
       a sentence.
    3. ``from == channel`` otherwise -> ``action``.  The channel EOA doing
       something onchain that is neither a self-post nor an answer — the
       ERC-8004 ``register()`` at nonce 4 is this, and NEW DEPLOY watches for
       the next one.  ``to = None`` (a deployment) lands here too.
    4. ``from`` is a dev wallet **and** (value moved **or** the calldata is not
       a message) -> ``fund``.  A dev wallet that writes a readable message is
       a ``reply``, because the feed prints these kinds next to the message and
       calling a message "fund" would be wrong on screen.
    5. everything else -> ``reply``.

    ``value_wei`` never promotes a stranger: the begging tx sent 1e13 wei and
    is still a reply.  Nothing here raises — a missing address is ``""``, a
    missing value is ``0`` — because this runs inside the feed builder.
    """
    if success is False:
        return "failed"
    src = _addr(from_addr)
    dst = _addr(to_addr)
    if src == _CHANNEL:
        if dst == _CHANNEL:
            return "self"
        if (_as_int(value_wei) or 0) == 0 and decode_utf8_calldata(input_hex) is not None:
            return "answer"
        return "action"
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


#: Characters a launched coin's ticker may keep in a HOT COIN detail.
#: Everything else -- brackets, quotes, slashes, unicode look-alikes, control
#: characters -- is dropped outright rather than kept-but-escaped.  This is
#: deliberately narrower than "escaping": the widget's own ``safe_markup``
#: call (applied to every detector's detail, uniformly, downstream) only ever
#: *prepends* a backslash to a ``[`` -- it cannot remove the bracket, so
#: ``"[/x]"`` in is ``"[/x]"`` out, fully legible on screen.  That is correct
#: for every other third-party string in this module (a Blockscout ``label``
#: is passed through raw and escaped only at the widget -- see
#: ``_detect_deploy``), but ``launch(string,string)`` is permissionless and
#: unpriced beyond gas (CLAUDE.md), so a ticker is the single most
#: attacker-chosen string this dashboard ever shows, and HOT COIN is the
#: first detector whose detail contains one.
_TICKER_SAFE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.$"
)

#: A ticker with nothing safe left in it still needs a word in the detail.
_TICKER_FALLBACK = "coin"

#: Space budget for a ticker inside a HOT COIN detail: generous next to real
#: symbols (``IMD``, ``ICE``, ``K-256``) but bounded, so a long safe-looking
#: string cannot crowd the swap count and threshold off the row.
_TICKER_LIMIT = 16


def _safe_ticker(value: Any) -> str:
    """A launched coin's ticker, filtered to :data:`_TICKER_SAFE_CHARS`.

    A real ticker (``IMD``, ``FP``, ``K-256``) survives untouched.  A hostile
    one built to read as ``"[/x]"`` on screen loses every character that made
    it hostile and, if nothing safe is left, renders as :data:`_TICKER_FALLBACK`
    rather than an empty string.
    """
    text = value if isinstance(value, str) else ""
    kept = "".join(ch for ch in text if ch in _TICKER_SAFE_CHARS)[:_TICKER_LIMIT]
    return kept or _TICKER_FALLBACK


# ---------------------------------------------------------------------------
# The nine detectors
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


#: Sorts below every real block/log index, so a row that carries neither orders
#: under one that does rather than jumping ahead of it.
_NO_POSITION = -1


def _order_key(row: Any) -> tuple[float, int, int]:
    """``(ts, block, log_index)`` — the total order over one event stream.

    ``ts`` first because it is what a user reads and what the FIRED age is
    measured from; ``(block, log_index)`` after it because ``ts`` is *not*
    total over these rows (see :data:`BASELINE_EVENT_KEYS`).  Deliberately not
    list position: the streams disagree about what position means.

    Rows that carry no chain position — ``deploy_events`` and
    ``burn_transfers`` come off Blockscout transaction pages, which have no log
    index — fall back to :data:`_NO_POSITION` for both, so they compare exactly
    as they did before this key existed.
    """
    row = row if isinstance(row, dict) else {}
    block = _as_int(row.get("block"))
    log_index = _as_int(row.get("log_index"))
    return (
        _as_float(row.get("ts")) or 0.0,
        _NO_POSITION if block is None else block,
        _NO_POSITION if log_index is None else log_index,
    )


def _baseline_order_key(base: dict, ts_key: str, seq_key: str) -> tuple[float, int, int]:
    """The recorded event's order key, from the two baseline entries.

    A baseline written before ``seq_key`` existed — every cache file on disk
    today — reads back as :data:`_NO_POSITION` for both positions. That is the
    right direction: a same-``ts`` row with a real position then counts as
    newer, which is precisely the event the old ordering swallowed, and the
    ``tx`` check above still stops the recorded row itself from re-firing.
    """
    raw = base.get(seq_key)
    seq = list(raw) if isinstance(raw, (list, tuple)) else []
    block = _as_int(seq[0]) if len(seq) > 0 else None
    log_index = _as_int(seq[1]) if len(seq) > 1 else None
    return (
        _as_float(base.get(ts_key)) or 0.0,
        _NO_POSITION if block is None else block,
        _NO_POSITION if log_index is None else log_index,
    )


def _newest(rows: list[dict]) -> dict | None:
    """The row with the highest :func:`_order_key`; ``None`` for an empty list."""
    if not rows:
        return None
    return max(rows, key=_order_key)


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


def _fresh_event(
    base: dict, tx_key: str, ts_key: str, seq_key: str, rows: list[dict] | None
) -> dict | None:
    """The newest event that is genuinely new, or ``None``.

    Three ways this returns ``None``, and each one is a bug that would
    otherwise ship:

    * ``rows is None`` — the read failed.  An outage detects nothing.
    * the baseline key is **absent** — this is the first successful read of
      this window ever, so it *seeds*.  Without this, an empty cache reports
      every historical event as breaking news on first launch.
    * the newest row is the one already recorded, or is **not after** it in
      :func:`_order_key` — the log window rolled, and a window that lost its
      newest row must not make the second-newest look new.

    The last comparison is on the whole order key, not on ``ts`` alone.  ``ts``
    ties are ordinary (see :data:`BASELINE_EVENT_KEYS`), and a strict ``ts >``
    against a tie means the second of two events **in one block** can never
    fire — not late, never.
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
    if _order_key(newest) <= _baseline_order_key(base, ts_key, seq_key):
        return None
    return newest


# --- 1. NEW POST -----------------------------------------------------------


def _detect_post(base: dict, read: dict, now: float) -> _Det:
    """A new **self-post** from the announce wallet (PRD §3 #1).

    These txs emit **no logs**, so every event-driven watcher is structurally
    blind to them; this row is what sees them.

    It used to fire on ``announce_nonce`` alone, and that was wrong in a way
    that got worse as the channel got busier. The nonce counts what the
    announce wallet *sent*, and it sends three different things: a self-post,
    an **answer** addressed to a reader who asked something, and the odd
    contract call. All three move it. So an answer fired NEW POST — quoting
    ``announce_last_text``, which is the newest *self-post*, and dating the
    FIRED row to that post's timestamp. Brand-new news, rendered as a
    message nobody had just written. Real instance: channel nonce 23,
    2026-08-22, the dev answering "will my IMD NFT generate me $IMD
    rewards?".

    The subject is therefore the newest self-post's own timestamp. An answer
    does not move it, and NEW REPLY owns answers now; a contract call does
    not move it either, and NEW DEPLOY owns those.

    The nonce is **not** also required. It is monotonic and advances on every
    successful read, including the cycle where the nonce had moved but
    Blockscout had not yet published the body — so an "and the nonce moved"
    clause would have gone false by the time the body arrived, and the post
    would never fire at all.

    The old ``channel_tx_count`` WATCH — "somebody else wrote to the channel"
    — moved to :func:`_detect_thread`, which can say who and quote what. What
    is left here is a WATCH this row can actually mean: the nonce moved and
    the page has **not**, so we know the wallet sent something and cannot yet
    tell whether it was a post. Once the page does move without a newer
    self-post, the answer is known — it was an answer or a call — and this row
    goes quiet rather than warning about a post that never existed.
    """
    nonce = _as_int(read.get("announce_nonce"))
    if nonce is None:
        return _dead("channel unavailable")

    base_nonce = _as_int(base.get("announce_nonce"))
    if base_nonce is None:
        return _ok(f"nonce {nonce} · baseline set")

    last_ts = _as_float(read.get("announce_last_ts"))
    base_last_ts = _as_float(base.get("announce_last_ts"))
    if last_ts is not None and base_last_ts is not None and last_ts > base_last_ts:
        text = read.get("announce_last_text")
        body = f' "{_truncate(text)}"' if isinstance(text, str) and text.strip() else ""
        return _fired(f"#{nonce}{body}", last_ts)

    tx_count = _as_int(read.get("channel_tx_count"))
    base_txs = _as_int(base.get("channel_tx_count"))
    page_moved = tx_count is not None and base_txs is not None and tx_count > base_txs
    if nonce > base_nonce and not page_moved:
        return _watch(f"nonce {nonce} · post not on the page yet")

    return _ok(f"nonce {nonce} · no new post")


# --- 2. NEW REPLY ----------------------------------------------------------


def _detect_thread(base: dict, read: dict, now: float) -> _Det:
    """A reply or an answer landed on the channel (2026-08-24).

    The feed collapses a post's replies behind a toggle, which is the right
    default — a dev post with a tail of strangers' questions is one
    conversation, not six rows — but it also means the reader cannot tell a
    thread that grew from one that did not without opening it. This row is
    what tells them, and it is why the two halves of the channel finally have
    a detector each: NEW POST for what the dev broadcast, NEW REPLY for what
    the thread did.

    Both kinds share the row because both are the same news to a reader
    watching for movement, and the detail says which landed. An **answer**
    (the announce wallet writing back to somebody who asked) is deliberately
    not split off into its own row: the rail sits above the dev-activity
    table and must not eat it, and two rows firing on one exchange would cost
    two lines to say one thing.

    The WATCH is the page lagging its own counter. ``channel_tx_count`` is
    ``len(rows)`` off the channel page and moves the moment a stranger writes;
    the rows themselves are what carry the text. When the count has moved but
    no new thread row is on the page yet, that is real news we cannot quote —
    so it is a WATCH, not silence, and not a fabricated body. NEW POST holds
    the mirror-image WATCH, keyed on the nonce rather than the count, and the
    two cannot both be right about one event: a reply moves the count without
    the nonce, a post moves the nonce and only then the count.
    """
    rows = _event_rows("channel_threads", read.get("channel_threads"))
    if rows is None:
        return _dead("channel unavailable")

    fresh = _fresh_event(base, *BASELINE_EVENT_KEYS["channel_threads"], rows)
    if fresh is not None:
        kind = "answer" if str(fresh.get("kind") or "") == "answer" else "reply"
        text = fresh.get("text")
        body = f' "{_truncate(text)}"' if isinstance(text, str) and text.strip() else ""
        return _fired(f"{kind}{body}", _as_float(fresh.get("ts")))

    tx_count = _as_int(read.get("channel_tx_count"))
    base_txs = _as_int(base.get("channel_tx_count"))
    if tx_count is not None and base_txs is not None and tx_count > base_txs:
        return _watch(f"{tx_count} txs on channel · reply not on the page yet")

    return _ok("no new replies")


# --- 3. LP MOVE --------------------------------------------------------------


def _detect_lp(base: dict, read: dict, now: float) -> _Det:
    """The dev's v4 LP position count (PRD §9, re-aimed — and finally repointed).

    LP MIGRATION — the v3→v4 event this row used to watch for, a PoolManager
    ``Initialize`` for IMD with ``hooks != 0x0`` — already fired: the ops
    wallet withdrew and burned v3 position #1167726 on 2026-08-17, and the v4
    IMD/ETH pool now exists.  That is a completed migration, not a repeating
    one, so the hooked-``Initialize`` branch this row used to check first is
    gone rather than re-armed for a second launch that is not coming;
    ``v4_hook_pools``/``BASELINE_EVENT_KEYS["v4_hook_pools"]`` stay wired
    (``surf_manager.py`` still produces the reading) but nothing in this
    function consults them any more.

    **The repoint, which the rename shipped without** (final fix wave, C2).
    Until now the only numeric input here was ``lp_liquidity``, off
    ``NFPM.positions(LP_POSITION_ID)`` — *the position the dev burned*. That
    call reverts, so the value is ``None`` forever, no comparison was ever
    reachable, and the row rendered a permanently dark ``● LP MOVE --`` whose
    unknown-state string blamed a v4 position nothing had tried to read. An
    earlier version of this docstring said the hero payload "already carries"
    ``lp_position_count``; that sentence was the reasoning that left this
    unwired, and it was doubly false by the time it was read — the flat key
    had been removed in fix round 12a, and no detector consumed it either.

    So the subject is now ``lp_position_count`` —
    ``PositionManager.balanceOf(OPS_WALLET)`` on the v4 side, which already
    rides in the same ``aggregate3`` as every other chain scalar and costs no
    request. It is coarser than v3 liquidity was (a position's size can move
    without the count moving) but it is *real*, which the old input is not: a
    position leaving the ops wallet is exactly the "LP moved" event this row
    is named for, and it has a **representable zero** — 0 held is a fact, not
    an outage.

    Fewer positions FIREs, more positions WATCHes (a fresh mint is news but
    not an exit), and any frenpet.eth nonce movement still WATCHes as the
    cheap precursor.  The payload prefix stays ``lp`` (Task 9's row alignment
    depends on it).  An unset baseline seeds without firing, the rule every
    edge on this rail keeps.  A count of ``None`` produces no comparison at
    all, and it cannot un-fire anything: the FIRED store is applied by
    :func:`build_signals` independently of what this returns.
    """
    count = _as_int(read.get("lp_position_count"))
    base_count = _as_int(base.get("lp_position_count"))
    if count is not None and base_count is not None:
        if count < base_count:
            return _fired(f"v4 position OUT · {base_count}→{count} held", now)
        if count > base_count:
            return _watch(f"v4 position IN · {base_count}→{count} held")

    ops_nonce = _as_int(read.get("ops_nonce"))
    base_ops = _as_int(base.get("ops_nonce"))
    if ops_nonce is not None and base_ops is not None and ops_nonce > base_ops:
        return _watch(f"frenpet.eth active · nonce {ops_nonce}")

    if count is None:
        return _dead("v4 position count unavailable")
    if base_count is None:
        return _ok(f"{count} v4 held · baseline set")
    return _ok(f"{count} v4 position{'' if count == 1 else 's'} held")


# --- 4. GATE OPEN ------------------------------------------------------------


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


# --- 5. NEW DEPLOY -----------------------------------------------------------


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
    fresh = _fresh_event(base, *BASELINE_EVENT_KEYS["deploy_events"], events)
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


# --- 6. BRIDGE STAGE -------------------------------------------------------


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
    fresh = _fresh_event(base, *BASELINE_EVENT_KEYS["bridge_mints"], mints)
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


# --- 7. BURN ---------------------------------------------------------------


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
    fresh = _fresh_event(base, *BASELINE_EVENT_KEYS["burn_transfers"], transfers)
    if fresh is not None:
        amount = _as_float(fresh.get("amount"))
        rendered = _fmt_amount(amount) if amount is not None else "?"
        return _watch(f"{rendered} IMD → BurnExecutor")

    if supply is None:
        return _dead("supply unavailable")
    if base_supply is None:
        return _ok("supply baseline set")
    return _ok("supply flat")


# --- 8. DECOY POOL -----------------------------------------------------------


def _detect_decoy(base: dict, read: dict, now: float) -> _Det:
    """A new third-party pool joins the decoy count, or an existing scan
    read stays unchanged (the v4-launchpad addition, Task 7).

    ``LaunchpadHook.imdEthPoolId()`` names the *real* IMD/ETH pool; the other
    37 pools competing for the same pair are third-party impostors, each free
    to set its own fee tier to look attractive.  Nobody "un-deploys" a
    Uniswap pool, so a rising count is unambiguous and fires on its own —
    unlike DECOY's siblings below, this needs a baseline (``decoy_pool_count``
    is in :data:`BASELINE_SCALARS` and :data:`MONOTONIC_BASELINES`), because
    the signal *is* the delta, not a level.

    The newest pool's fee is read alongside the count and, when that second
    read also succeeded, goes into the FIRED detail.  A count that moved but
    whose fee could not be read is still worth a row — just not a confident
    one, mirroring BURN READY's own "both inputs must read to fire" rule —
    so it renders WATCH instead of FIRED rather than being swallowed.
    """
    count = _as_int(read.get("decoy_pool_count"))
    if count is None:
        return _dead("decoy scan unavailable")

    base_count = _as_int(base.get("decoy_pool_count"))
    if base_count is None:
        return _ok(f"{count} decoy pools · baseline set")

    if count > base_count:
        fee_bps = _as_int(read.get("decoy_newest_fee_bps"))
        if fee_bps is not None:
            return _fired(f"decoy #{count} · fee {fee_bps / 100.0:.1f}%", now)
        return _watch(f"decoy #{count} · fee unknown")

    return _ok(f"{count} decoy pools")


# --- 9. BURN READY ------------------------------------------------------------


def _detect_burn_ready(base: dict, read: dict, now: float) -> _Det:
    """The burn pipeline's own gate: ``previewBridge()`` would send something
    (the v4-launchpad addition, Task 7; repointed 2026-08-25).

    The reading behind this row used to be ``imdToBurn >= max(minBridgeAmount,
    1)`` and it reported READY minutes after a burn -- ``imdToBurn`` is the
    *hook's* accrual and the bridge spends the *executor's* balance,
    ``minBridgeAmount`` is genuinely ``0`` on chain, and the ``1`` standing in
    for it was invented. ``surf_manager.py``'s own comment on ``burn_ready``
    carries the full autopsy. Nothing in this detector changed: it reads the
    tri-state it is handed, which is the point of the split.

    **An EDGE detector with a baseline, not a level check** (fix round 1).
    The first cut of this row fired on every cycle ``burn_ready`` read
    ``True``, which is wrong for two reasons at once: it violates the "an
    outage is never read as an event" invariant every other detector in this
    file holds, because the launchpad slot's last-good is deliberately still
    served through an otherwise-total outage, so a stale-but-true reading
    kept firing straight through one (caught by
    ``tests/data/test_surf_manager.py::test_no_signal_fires_and_no_
    baseline_moves_under_a_total_outage`` — a manager-owned test, not
    touched); and it broke this rail's own vocabulary, where FIRED means
    "something happened" (a *transition*), not "a condition holds" — NEW
    POST fires on a *new* post, BRIDGE STAGE on a *new* mint, BURN on a
    supply *decrease*, never on a level that merely continues to be true.

    So ``burn_ready`` now has its own boolean baseline (``BASELINE_SCALARS``,
    coerced like ``gate_open``): ``True`` while the baseline says ``False``
    is the transition and FIRES; ``True`` while the baseline is already
    ``True`` is WATCH — still callable, nobody has fired it, and the dev
    asked publicly for a bot to call it, so a persistently-callable pipeline
    is genuinely worth a resting row rather than silence.  An **unset**
    baseline (first successful read ever) seeds and reports WATCH rather
    than firing — the same false-first-sweep guard ``_detect_gate`` uses for
    ``gate_open`` — so day one does not report a gate that has been callable
    for hours as breaking news.

    ``burn_ready`` is tri-state (``surf_manager.py``'s own doc: "we cannot
    tell" is not "not ready"): ``None`` means the gate itself could not be
    read and must render unknown, never a quiet OK.  ``False`` is always OK
    — "we looked, it is not ready" — whatever is or is not accrued; the
    accrued amount still rides along in the detail so the row never goes
    silent about the thing it watches.
    """
    ready = read.get("burn_ready")
    ready = ready if isinstance(ready, bool) else None
    accrued = _as_float(read.get("burn_accrued"))
    # The headline quantity is what the bridge would SEND, not what the hook
    # has accrued: those are two contracts' balances and a sweep moves them in
    # opposite directions, so the instant this row goes READY is the instant
    # the accrual is smallest. Reporting the accrual here read as
    # "ready to burn 0.05 IMD" while 1.25 sat staged and callable. The accrual
    # still follows it -- it is what is building toward the next burn -- and
    # either half may be unreadable without silencing the row.
    sendable = _as_float(read.get("burn_bridgeable"))
    parts = []
    if sendable is not None:
        parts.append(f"{_fmt_amount(sendable)} IMD")
    if accrued is not None:
        parts.append(f"{_fmt_amount(accrued)} IMD accruing")
    amount = " · ".join(parts) if parts else "amount unread"

    if ready is None:
        return _dead("burn readiness unavailable")

    if not ready:
        if accrued is not None and accrued > 0:
            return _ok(f"not ready · {_fmt_amount(accrued)} IMD accrued")
        return _ok("not ready")

    base_ready = base.get("burn_ready")
    base_ready = base_ready if isinstance(base_ready, bool) else None

    if base_ready is None or base_ready:
        # Unset baseline (first successful read: seed, don't fire) or already
        # True (still callable, already reported) -- either way, WATCH.
        return _watch(f"ready to burn · {amount}")

    return _fired(f"ready to burn · {amount}", now)


# --- 10. HOT COIN ---------------------------------------------------------------


def _hot_state(readings: dict, now: float) -> tuple[str, str, int, int] | None:
    """``(pool_id, safe_ticker, swaps, threshold)`` for the hour's busiest coin.

    ``None`` when the hour cannot be judged at all, which is three different
    situations the caller separates by re-inspecting its inputs: the
    distribution was never read, it is older than :data:`HOT_MAX_AGE_S`, or
    fewer than ``HOT_MIN_ACTIVE`` coins traded.

    The distribution is keyed by ``pool_id`` — the coin's identity — and the
    ticker is looked up purely to *label* the row (final fix wave, I1);
    ``launch(string,string)`` is permissionless, so a ticker is a display
    string two coins can share and it may never decide anything. A pool with
    no label falls back to :data:`_TICKER_FALLBACK` rather than printing a
    66-character pool id at a detector row.

    One implementation, called from both :func:`_detect_hot_coin` and
    :func:`_hot_leader_name`, so the row the reader sees and the baseline the
    next refresh compares against can never disagree about who was hot.
    """
    counts = readings.get("launchpad_swaps_by_coin")
    if not isinstance(counts, dict):
        return None
    ts = _as_float(readings.get("launchpad_swaps_ts"))
    if ts is None or now - ts > HOT_MAX_AGE_S:
        return None
    active = {
        pool_id: n
        for pool_id, n in counts.items()
        if isinstance(pool_id, str) and isinstance(n, int) and not isinstance(n, bool) and n > 0
    }
    threshold = hot_coin_threshold(active)
    if threshold is None:
        return None
    pool_id, count = max(active.items(), key=lambda pair: pair[1])
    tickers = readings.get("launchpad_coin_tickers")
    ticker = tickers.get(pool_id) if isinstance(tickers, dict) else None
    return pool_id, _safe_ticker(ticker), count, threshold


def _hot_leader_name(readings: dict, now: float) -> str | None:
    """Which coin is over this hour's bar, as the persisted baseline stores it.

    Three values, and the difference between the last two is the whole edge:

    * the coin's ``pool_id`` — it is over the bar.  Its **identity**, never its
      ticker: two coins can share a label, and an edge keyed on the label
      would miss the lead changing hands between them (final fix wave, I1);
    * ``""`` — the hour **was** judged and nobody cleared the bar;
    * ``None`` — the hour could not be judged (unread, stale or too thin), so
      :func:`_advance` leaves the previous leader untouched rather than
      seeding a conclusion out of a read that did not happen.
    """
    state = _hot_state(readings, now)
    if state is None:
        return None
    pool_id, _name, count, threshold = state
    return pool_id if count >= threshold else ""


def _detect_hot_coin(base: dict, read: dict, now: float) -> _Det:
    """A launched coin *becomes* the one clearing a relative bar (the
    v4-launchpad addition, Task 7; re-shaped in the final fix wave).

    The bar is :func:`surf_launchpad.hot_coin_threshold` — never
    reimplemented here — computed off the *whole* in-window population Task 6
    hands in (``launchpad_swaps_by_coin``), not the rendered top-20 slice.
    ``None`` means the hour is too thin to judge (fewer than five coins
    traded) and renders OK, never a fire: at ~1,170 swaps/day across ~146
    coins a fixed threshold would light this row permanently, and a marker
    that is always on means nothing.

    **This is an EDGE, not a level** (final fix wave, C1 — Ruling D's shape,
    finally applied to BURN READY's sibling).  A level check fired on every
    single refresh for as long as a coin stayed hot, and — because
    ``launchpad_swaps_by_coin`` is served from a last-good slot that never
    expires and is persisted to ``~/.maxpane/surf_cache.json`` — it kept
    firing with a fresh ``age 0.0s`` through a total outage, off a
    distribution read the day before.  So: a *new* leader over the bar FIREs,
    the same leader still over it WATCHes, and the first judgeable hour seeds
    the baseline without firing.  Under an outage no new reading arrives, the
    leader does not change, and nothing fires.

    The edge alone is not enough, because this reading is a **windowed**
    statistic rather than a standing fact: "40 swaps this hour", replayed a
    day later, is a false present-tense claim even as a WATCH.  So the
    distribution is also refused outright once it is older than the window it
    measures (:data:`HOT_MAX_AGE_S`) — reported as explicitly unknown, never
    as a quiet ``ok``.  An *unstamped* distribution takes the same branch: a
    reading that cannot be shown to be current is treated as stale, which is
    the failing-safe direction.

    The busiest coin's ticker is the most attacker-controlled string on this
    dashboard — ``launch(string, string)`` is permissionless and unpriced
    beyond gas — so it is bounded through :func:`_safe_ticker` before the
    detail is built, and the whole detail is flattened and cut through
    :func:`_truncate` last, so a cut can never bisect anything
    :func:`_safe_ticker` left behind.  It is also *only* a label: the
    distribution is keyed by ``pool_id`` and so is the baseline, because two
    coins can carry one ticker and joining on it let a coin cross this bar on
    a stranger's volume (final fix wave, I1).
    """
    counts = read.get("launchpad_swaps_by_coin")
    if not isinstance(counts, dict):
        return _dead("swap distribution unavailable")

    ts = _as_float(read.get("launchpad_swaps_ts"))
    if ts is None or now - ts > HOT_MAX_AGE_S:
        return _dead("swap distribution stale")

    state = _hot_state(read, now)
    if state is None:
        return _ok("hour too thin to judge")
    pool_id, name, count, threshold = state

    if count >= threshold:
        base_leader = base.get("hot_leader")
        base_leader = base_leader if isinstance(base_leader, str) else None
        if base_leader is None:
            # First judgeable hour we have ever seen: seed, report, do not
            # fire (the don't-fire-on-first-sight rule every other edge on
            # this rail follows).
            return _watch(_truncate(f"{name} hot · {count} swaps (≥{threshold})"))
        if base_leader == pool_id:
            return _watch(_truncate(f"{name} still hot · {count} swaps (≥{threshold})"))
        return _fired(_truncate(f"{name} · {count} swaps (≥{threshold})"), now)

    watch_bar = max(1, threshold // 2)
    if count >= watch_bar:
        return _watch(_truncate(f"{name} warming · {count} swaps (<{threshold})"))

    return _ok(f"busiest {count} swaps · below {threshold}")


# --- registry --------------------------------------------------------------

#: ``(name, detector)`` in render order.  :data:`SIGNAL_NAMES` and
#: :data:`SIGNAL_OUTPUT_KEYS` are derived from it, so the module can never
#: advertise a key it does not emit.
_DETECTORS: tuple[tuple[str, Any], ...] = (
    ("post", _detect_post),
    ("thread", _detect_thread),
    ("lp", _detect_lp),
    ("gate", _detect_gate),
    ("deploy", _detect_deploy),
    ("bridge", _detect_bridge),
    ("burn", _detect_burn),
    ("decoy", _detect_decoy),
    ("burnready", _detect_burn_ready),
    ("hot", _detect_hot_coin),
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
            # ``_as_float``, not ``_as_int``: every counter here compares
            # identically either way, but ``announce_last_ts`` is a timestamp,
            # and ``_as_int`` answers ``None`` for anything with a fractional
            # part -- which would skip the guard silently, i.e. leave the one
            # baseline that needed it unprotected.
            previous = _as_float(out.get(key))
            current = _as_float(value)
            if previous is not None and current is not None and current < previous:
                continue
        out[key] = value

    for read_key, (tx_key, ts_key, seq_key) in BASELINE_EVENT_KEYS.items():
        rows = _event_rows(read_key, readings.get(read_key))
        if rows is None:
            continue
        newest = _newest(rows)
        if newest is None:
            if tx_key not in out:
                out[tx_key] = ""
                out[ts_key] = 0.0
                out[seq_key] = [_NO_POSITION, _NO_POSITION]
            continue
        ts, block, log_index = _order_key(newest)
        previous_ts = _as_float(out.get(ts_key))
        # The whole order key, matching `_fresh_event`: a baseline that pins
        # only `ts` cannot advance past a same-`ts` row, so the row that *did*
        # fire this cycle would be re-detected on the next one.
        if previous_ts is None or (ts, block, log_index) >= _baseline_order_key(
            out, ts_key, seq_key
        ):
            out[tx_key] = str(newest.get("tx_hash") or "")
            out[ts_key] = ts
            out[seq_key] = [block, log_index]

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

    # ``hot_leader`` is this module's own conclusion about the swap
    # distribution, not a value any source hands us, so it is derived here --
    # once, from the same helper ``_detect_hot_coin`` reaches its verdict
    # through -- and injected into the readings the detectors and
    # :func:`_advance` both see. Doing it here rather than inside ``_advance``
    # is what gives the derivation access to ``now``, which the staleness bound
    # needs: a distribution too old to render must also be too old to seed a
    # baseline from.
    read = {**read, "hot_leader": _hot_leader_name(read, now)}

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
