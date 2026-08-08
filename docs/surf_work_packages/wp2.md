# WP2 — Signals analytics (`analytics/surf_signals.py` + tests)

**Goal:** Build the pure signal layer for the surf dashboard — UTF-8 calldata decoding, channel-tx classification, FP↔IMD parity, and the six-detector state machine with persisted-FIRED semantics and baselines that advance only on successful reads.

**Dependencies:** WP0 only — `maxpane_dashboard/data/surf_addresses.py` (`ANNOUNCE`, `DEV_WALLET`, `OPS_WALLET`) and `maxpane_dashboard/data/surf_models.py` (`CHANNEL_KINDS`, **re-exported here, never redefined**). Both are stdlib-only boundary modules, so importing them does not break the `analytics/` purity rule. Nothing else: this module imports no client, no cache, no manager, no Textual, and no `time`.

**Plan status:** every code block below was executed end to end while writing this plan — the fixture generator against the real captures, the module, and all 135 tests (`135 passed`), plus both required mutation checks. Two design bugs were found that way and are already fixed in the code below: a fired-but-stale detection rendering as `fired` with a duplicated detail, and the real 2026-05-22 `register()` timestamp being unusable as a FIRED vector at a 2026-08-07 clock. Expected counts and failure messages in the steps are the observed ones, not estimates.

Three things changed after that run, all from review, none moving a test count: WP2.1's fixture moved from `tests/fixtures/surf/announce_calldata.json` to `tests/fixtures/surf/signals/announce_calldata.json` and gained a self-describing `_meta` wrapper — **WP2's own provenance convention**, not an inherited one (the generator was re-run against the real captures afterwards and still prints the same seven names; the `_meta` check rides in the existing module-scoped `calldata` fixture, so no test function was added); `CHANNEL_KINDS` became a re-export of WP0's `data/surf_models.CHANNEL_KINDS` instead of a second literal (WP2.2's existing assertion changed from a set comparison to an identity check, so again no new test); and the `SIGNAL_OUTPUT_KEYS ⊆ SURF_KEYS` containment assertion got a named owner outside this WP. All three are explained where they bite: the Owner note, WP2.2, and Open issues.

**Owner note:** This WP owns exactly three paths and touches nothing else:

- `maxpane_dashboard/analytics/surf_signals.py` (create)
- `tests/analytics/test_surf_signals.py` (create)
- `tests/fixtures/surf/signals/announce_calldata.json` (create — a mechanical slice of the committed captures)

**The fixture subdirectory is a hard rule, not a preference.** The *root* of `tests/fixtures/surf/` holds **directories only**. WP0.6's `test_the_fixtures_root_holds_directories_only`, in `tests/data/test_surf_captures.py`, is the guard, and it fails on *any* loose file — a perfect provenance block does not exempt one:

```python
loose = sorted(p.name for p in SURF_FIXTURES.iterdir() if p.is_file())
assert loose == [], f"put these in a per-work-package subdirectory: {loose}"
```

That rule comes straight from WP0's *Fixture ownership* section: WP0 owns `tests/fixtures/surf/captures/` (31 files, pinned by name in `test_the_capture_inventory_is_complete`) and **hands over no fixture file at all** — every consuming WP slices what it needs into its own named subdirectory. WP1 already does this (`tests/fixtures/surf/client/`), WP2 uses `tests/fixtures/surf/signals/`. A root-level `announce_calldata.json` therefore turns WP0's suite red the moment WP2 lands, in a file WP2 may not edit.

The slice carries a `{"_meta": …, "response": …}` wrapper, and that wrapper is **WP2's own provenance convention — not WP0's**. WP0 defines no `_meta` convention anywhere; it pins its captures by name and by fact instead. The wrapper is here so the file records which committed capture it was cut from and that the source was keyless, which makes it readable without this plan; the module-scoped `calldata` fixture asserts it on every read.

It **imports from but never edits** `data/surf_models.py` (**WP0** owns it — `SURF_KEYS` and `CHANNEL_KINDS` both — not WP3), and it does not touch the widgets (WP3), the cache/manager (WP4), the screen (WP5) or any registration surface (WP6). `SIGNAL_OUTPUT_KEYS` is frozen here and consumed downstream; the `set(SIGNAL_OUTPUT_KEYS) <= set(SURF_KEYS)` containment assertion has exactly one named owner — **WP0's `tests/data/test_surf_models.py`** — and Open issues below carries the test verbatim for whoever edits wp0.md.

---

## Contract this WP freezes for WP4 (the manager)

`build_signals(baselines, readings, now_ts)` is the whole interface, and **WP4's manager is its only caller** — the widgets (WP3) never see it, because WP3.8's AST import-hygiene test forbids the widget layer from importing `analytics/` at all. What WP3 consumes from this WP is `SIGNAL_OUTPUT_KEYS`: the 18 `sig_*` names it renders out of the flat dict, nothing more. Three dicts, no objects:

**`readings`** — one refresh's reads. A key that is absent **or `None` means the read failed**; that is the only outage encoding, and it is never `0`, never `[]`, never `False`.

| key | type | source |
|---|---|---|
| `announce_nonce` | `int\|None` | `eth_getTransactionCount(ANNOUNCE)` — the feed sequence number rendered as `feed #N` |
| `channel_tx_count` | `int\|None` | Blockscout tx count for `ANNOUNCE` (posts **and** replies; 21 today vs nonce 14) |
| `announce_last_text` | `str\|None` | decoded body of the newest self-post |
| `announce_last_ts` | `float\|None` | unix ts of the newest self-post |
| `lp_liquidity` | `int\|None` | `NFPM.positions(LP_POSITION_ID).liquidity`, raw uint128 |
| `ops_nonce` | `int\|None` | `eth_getTransactionCount(OPS_WALLET)` (frenpet.eth) |
| `dev_nonce` | `int\|None` | `eth_getTransactionCount(DEV_WALLET)` (surfsurf.eth) |
| `v4_hook_pools` | `list[dict]\|None` | PoolManager `Initialize` rows for IMD: `{ts, tx_hash, hooks}` |
| `gate_open` | `bool\|None` | `IdentityRegistry.identityAllowed()` |
| `identities_written` | `int\|None` | distinct tokens seen in `IdentityHashUpdated` logs |
| `deploy_events` | `list[dict]\|None` | `{ts, tx_hash, kind, label, wallet_label}`, `kind` ∈ `deploy`/`action` |
| `bridge_mints` | `list[dict]\|None` | `{ts, tx_hash, amount, to_label}` — `Transfer(from=0x0, to∈{dev,ops})` |
| `burn_transfers` | `list[dict]\|None` | `{ts, tx_hash, amount}` — IMD → BurnExecutor |
| `imd_supply` | `float\|None` | `IMD.totalSupply()` in whole tokens |

**`baselines`** — the persisted previous state (`SurfCache.get_baselines()` / `set_baselines()`), JSON-serialisable scalars only: the eight scalar keys `announce_nonce, channel_tx_count, lp_liquidity, ops_nonce, dev_nonce, gate_open, identities_written, imd_supply`; four `(tx, ts)` pairs `bridge_tx/bridge_ts, deploy_tx/deploy_ts, v4_tx/v4_ts, burn_tx/burn_ts`; and `fired`, a `{signal_name: {"ts": float, "detail": str}}` map.

**Returns** `(signals, advanced_baselines)`. `signals` holds exactly `SIGNAL_OUTPUT_KEYS` (18 keys, PRD §5); `advanced_baselines` is what the caller persists.

**Values used throughout, all read out of `tests/fixtures/surf/captures/` while writing this plan** (re-verify, do not retype from memory):

| thing | value | capture |
|---|---|---|
| newest self-post | nonce 13, `2026-08-07T04:27:11Z` = `1786076831`, hash `0xe397869a2ed1299f24618c377112a6e9637395d2c1e21e742ce30e6201440055` | `announce_eth_txs.json` |
| bridge mint #1 | `1786076339`, `0x17084b1bfc998a457416c1ba9689f50ca04efc6e160b7e28d4c75dc89bcea85c`, 10,000 IMD → frenpet.eth | `ops_eth_token_transfers.json` |
| bridge mint #2 | `1786076495`, `0xc7acbcc0b164a0eaecb1220484e97d410bb159ca42d3c61165a26fe03c1d0a01`, 114,366.899256 IMD → frenpet.eth | same |
| LP add | `1786076603`, `0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669`, ops nonce 37 | `ops_eth_txs.json` |
| burn transfer 07-31 | `1785464459`, `0xa25b08cfc4b2ca2ada16374001e377961514b50985d887ffcfc60a5194e5cd5c` | same |
| burn transfer 08-05 | `1785903035`, `0x11bf8d3e3fd83538faa906521c5f5f0592f6b6117c3d4967c97f05b3ae753a6e`, 15,745 IMD | `ops_eth_token_transfers.json` |
| ERC-8004 `register()` | `1779469691`, `0xa4ce159e5100eba90d231efb103b2c727a25660bacf9a2f02de569a4a1d1c1c2`, **non-UTF-8 calldata** | `announce_eth_txs.json` |
| IMD live supply | `2376731.868679` | `imd_token.json` |
| IMD / FP price | `0.7074` / `0.7274` → parity `-2.749518834204012` % | `dexscreener_imd.json`, `dexscreener_fp.json` |

---

### Task WP2.1: Calldata fixture slice + `decode_utf8_calldata`

**Files:**
- Create: `tests/fixtures/surf/signals/announce_calldata.json` (**not** the fixtures root — see the Owner note; the root is WP0's and is globbed by two of its tests)
- Create: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (create)

**Interfaces:**
- Consumes: `tests/fixtures/surf/captures/announce_eth_txs.json` (committed, read-only).
- Produces: `decode_utf8_calldata(hex_str: str) -> str | None`; module constants `FIRED_TTL_S = 86400`, `STATE_OK = "ok"`, `STATE_WATCH = "watch"`, `STATE_FIRED = "fired"`, `DETAIL_LIMIT = 48`, `READING_KEYS`, `BASELINE_SCALARS`, `BASELINE_EVENT_KEYS`, `MONOTONIC_BASELINES`.

**Steps:**

- [ ] Read `maxpane_dashboard/analytics/fwa_signals.py` (module docstring + `_as_int` + `_fmt_duration`) and `tests/analytics/test_fwa_signals.py` (header + `_code_only`). This WP mirrors both: prose that explains *why*, coercions that refuse to invent numbers, and structural tests that read the module source.

- [ ] Cut the fixture slice mechanically — no hand-typed hex. Run exactly:

```bash
cd /Library/Vibes/autopull && .venv/bin/python - <<'PY'
import json, pathlib
src = pathlib.Path("tests/fixtures/surf/captures/announce_eth_txs.json")
# signals/, never the fixtures root: the root holds directories only, and
# WP0.6's test_the_fixtures_root_holds_directories_only fails on any loose
# file there — in a suite WP2 does not own.
dst = pathlib.Path("tests/fixtures/surf/signals/announce_calldata.json")
want = {
    ("0x200e710acaa6a93bbc77146026328c40f1d60fb1", 13): "self_lp_add",
    ("0x200e710acaa6a93bbc77146026328c40f1d60fb1", 8): "self_hook_emdash",
    ("0x200e710acaa6a93bbc77146026328c40f1d60fb1", 4): "action_register",
    ("0x200e710acaa6a93bbc77146026328c40f1d60fb1", 0): "self_soon",
    ("0x1c3a0ad54418fe843953c71df23637de732ce159", 0): "reply_pasta",
    ("0xa5b9737dcc2f6a792bc4bca0caad80c8db595470", 25): "reply_begging",
    ("0x047f606fd5b2baa5f5c6c4ab8958e45cb6b054b7", 2266): "fund_ownership_proof",
}
out = {}
for tx in json.loads(src.read_text(encoding="utf-8")):
    name = want.get((tx["from"]["hash"].lower(), tx["nonce"]))
    if name is None:
        continue
    out[name] = {
        "tx_hash": tx["hash"],
        "from": tx["from"]["hash"],
        "to": (tx["to"] or {}).get("hash"),
        "value": tx["value"],
        "raw_input": tx["raw_input"],
        "timestamp": tx["timestamp"],
        "nonce": tx["nonce"],
    }
missing = sorted(set(want.values()) - set(out))
assert not missing, f"captures no longer contain: {missing}"
doc = {
    # WP2's own provenance convention — WP0 defines no _meta anywhere, it pins
    # its captures by name in test_the_capture_inventory_is_complete instead.
    # The point is that this slice records the committed capture it was cut
    # from and that the source was keyless, so the file is readable on its own.
    "_meta": {
        "captured_at": "2026-08-08",
        "keyless": True,
        "source": "tests/fixtures/surf/captures/announce_eth_txs.json (Blockscout REST v2, keyless)",
        "sliced_by": "the WP2.1 generator in this plan",
        "prd_ref": "docs/surf_PRD.md §8",
        "note": "WP2-owned slice; lives in signals/ because the fixtures root "
                "holds directories only (WP0.6's "
                "test_the_fixtures_root_holds_directories_only).",
    },
    "response": out,
}
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print(sorted(out))
PY
```

  Expected output: `['action_register', 'fund_ownership_proof', 'reply_begging', 'reply_pasta', 'self_hook_emdash', 'self_lp_add', 'self_soon']` — re-run against the real captures after the path/wrapper change, so this is still an observed line, not an estimate.

- [ ] Write the failing test. Create `tests/analytics/test_surf_signals.py`:

```python
"""Tests for ``maxpane_dashboard.analytics.surf_signals``.

Zero network, zero wall clock.  Every clock is injected: ``build_signals``
takes ``now_ts`` and nothing in the module under test may call ``time.time()``
(``test_module_is_pure`` enforces that mechanically).  Every payload below is
lifted from ``tests/fixtures/surf/`` — the real 2026-08-08 captures — not
invented; the two synthetic values (a hooked v4 ``Initialize`` row) are marked
SYNTHETIC because the event has not happened on chain yet.

The one committed file this WP owns lives in ``fixtures/surf/signals/``.  The
fixtures *root* holds directories only — WP0.6's
``test_the_fixtures_root_holds_directories_only`` (in
``tests/data/test_surf_captures.py``) fails on any loose file, whatever is in
it — so a WP2 file there would turn red a suite WP2 does not own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import surf_signals as sig

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "surf"


@pytest.fixture(scope="module")
def calldata() -> dict:
    """The seven-tx slice of the announce channel (WP2.1 generator).

    The file carries WP2's own ``{"_meta": …, "response": …}`` provenance
    wrapper — WP0 defines no such convention, it pins its captures by name —
    and is checked for it here rather than in a test of its own: the assertion
    has to run before any decoder test can use the payload anyway, and keeping
    it in the fixture leaves every observed test count in this plan unchanged.
    """
    doc = json.loads(
        (_FIXTURES / "signals" / "announce_calldata.json").read_text(encoding="utf-8")
    )
    meta = doc["_meta"]
    assert meta["keyless"] is True and meta["captured_at"] and meta["source"]
    return doc["response"]


# --- decode_utf8_calldata ---------------------------------------------------
#
# The dev's own monitoring spec (channel nonce 2) is "decode the transaction
# input as UTF-8 text when possible".  "When possible" is the whole job: one of
# the 21 channel txs is an ABI-encoded register() call and must decode to None,
# not to mojibake.


def test_decodes_the_shortest_real_post(calldata: dict):
    """nonce 0, 2026-05-16: the four-byte post that started the channel."""
    assert calldata["self_soon"]["raw_input"] == "0x736f6f6e"
    assert sig.decode_utf8_calldata(calldata["self_soon"]["raw_input"]) == "soon"


def test_decodes_the_lp_add_post_byte_for_byte(calldata: dict):
    """nonce 13 — the post the whole BRIDGE STAGE replay ends on."""
    assert sig.decode_utf8_calldata(calldata["self_lp_add"]["raw_input"]) == (
        "I moved 33 eth to the LP on mainnet https://etherscan.io/tx/"
        "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669. "
        "Hopefully in the coming days will be able to share more what been "
        "working on, as always 0 promises."
    )


def test_decodes_typographic_punctuation_and_newlines_unchanged(calldata: dict):
    """nonce 8: two U+2019 apostrophes, two U+2014 em-dashes, two newlines.

    The decoder returns raw text.  Escaping is the *widget's* job
    (``widgets/markup_safety.safe_markup``); a decoder that pre-escaped would
    double-escape downstream and corrupt the message.
    """
    text = sig.decode_utf8_calldata(calldata["self_hook_emdash"]["raw_input"])
    assert text == (
        "The hook will be highly experimental. I’ll\n"
        "  announce it before moving the LP. I’m also considering limiting "
        "trading to NFT holders for the first few hours—so the risks\n"
        "  are clear—then opening it to everyone. Thoughts?"
    )
    assert "’" in text and "—" in text and "\n" in text


def test_abi_encoded_register_call_is_not_a_message(calldata: dict):
    """nonce 4: ``register(string)`` — selector 0xf2c298be, invalid UTF-8.

    This is the one channel tx that is a contract call rather than a post.  A
    decoder that fell back to ``errors="replace"`` would put a wall of U+FFFD
    into the feed and label a contract call a message.
    """
    raw = calldata["action_register"]["raw_input"]
    assert raw.startswith("0xf2c298be")
    assert sig.decode_utf8_calldata(raw) is None


def test_empty_calldata_is_not_a_message(calldata: dict):
    """The 0.054 ETH funding tx from surfsurf.eth carries no calldata at all."""
    assert calldata["fund_ownership_proof"]["raw_input"] == "0x"
    assert sig.decode_utf8_calldata("0x") is None
    assert sig.decode_utf8_calldata("") is None
    assert sig.decode_utf8_calldata("   ") is None


def test_trailing_whitespace_is_stripped(calldata: dict):
    """The begging reply ends with a space; the feed must not carry it."""
    assert sig.decode_utf8_calldata(calldata["reply_begging"]["raw_input"]) == (
        "Gm Adam. Help me. Donate 10 ETH, to me, pls. Thanks you."
    )


@pytest.mark.parametrize(
    "bad",
    [
        "0xabc",        # odd number of nibbles
        "0xzz",         # not hex
        "not hex",
        "0x610062",     # "a\x00b" -- valid UTF-8, but NUL means ABI padding
        None,
        12345,
        b"0x736f6f6e",
    ],
)
def test_unparseable_calldata_is_none(bad):
    assert sig.decode_utf8_calldata(bad) is None


def test_markup_hostile_text_survives_verbatim():
    """``[/x]`` is returned as-is: escaping belongs to the widget layer.

    Token symbols and channel replies are attacker-controlled (CLAUDE.md), and
    the channel is permissionless by design (PRD §6.4) — so this input is
    realistic, not hypothetical.
    """
    assert sig.decode_utf8_calldata("0x5b2f785d") == "[/x]"
    assert sig.decode_utf8_calldata("0x5b626c696e6b5d") == "[blink]"
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`ModuleNotFoundError: No module named 'maxpane_dashboard.analytics.surf_signals'`** at collection (every test errors).

- [ ] Write the minimal implementation. Create `maxpane_dashboard/analytics/surf_signals.py`:

```python
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

from typing import Any

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
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 14 passed (7 test functions + the 7 parametrised unparseable cases).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py tests/fixtures/surf/signals/announce_calldata.json && git commit -m "feat(surf): decode announce-channel calldata as UTF-8, or as nothing

The dev's own monitoring spec says decode the input field as UTF-8 'when
possible'. One of the 21 channel txs is an ABI-encoded register(string) call:
it decodes to None, not to mojibake. Fixture sliced from the committed
2026-08-08 captures.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.2: `classify_channel_tx`

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (append)

**Interfaces:**
- Consumes: `maxpane_dashboard.data.surf_addresses.{ANNOUNCE, DEV_WALLET, OPS_WALLET}` (WP0); `maxpane_dashboard.data.surf_models.CHANNEL_KINDS` (WP0); `decode_utf8_calldata`.
- Produces: `classify_channel_tx(from_addr: str, to_addr: str, value_wei: int, input_hex: str) -> str` returning one of `"self" | "reply" | "action" | "fund"`. `CHANNEL_KINDS` is **re-exported**, not redefined: WP0 froze it in `data/surf_models.py` and owns its test (`test_channel_tx_kinds_are_the_four_frozen_strings`). A second literal here would be one closed vocabulary with two green tests, so a fifth kind added to one copy would never surface — the same drift WP4 refuses for the counterparty→`kind` map.

**Steps:**

- [ ] Confirm WP0 has landed and the three constants exist:
  `cd /Library/Vibes/autopull && .venv/bin/python -c "from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, OPS_WALLET; print(ANNOUNCE, DEV_WALLET, OPS_WALLET)"`
  Expected: `0x200E710aCAA6A93bbc77146026328C40F1d60fB1 0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7 0xE764dA9bDeA91d845AAc2C7D53A8DfE59A369095`.

- [ ] Confirm the vocabulary this task re-exports is WP0's, so nothing below retypes it:
  `cd /Library/Vibes/autopull && .venv/bin/python -c "from maxpane_dashboard.data.surf_models import CHANNEL_KINDS; print(CHANNEL_KINDS)"`
  Expected: `('self', 'reply', 'action', 'fund')`. If this raises, WP0 has not landed `surf_models.py` yet — wait for it rather than defining a local copy, which is the whole point of the identity assertion below.

- [ ] Write the failing test. Append to `tests/analytics/test_surf_signals.py`:

```python
# --- classify_channel_tx ----------------------------------------------------
#
# The dev's spec: from == to == channel is a post; from == channel to anything
# else is an onchain action; from == a dev wallet is funding; everything else
# is a community reply.  All four kinds exist in the 21 captured txs.


def _kind(row: dict) -> str:
    return sig.classify_channel_tx(
        row["from"], row["to"], int(row["value"]), row["raw_input"]
    )


def test_self_post_is_self(calldata: dict):
    """nonce 13: from == to == 0x200E710a…, value 0."""
    row = calldata["self_lp_add"]
    assert row["from"].lower() == row["to"].lower()
    assert _kind(row) == "self"


def test_outbound_contract_call_is_action(calldata: dict):
    """nonce 4: the channel EOA calling the ERC-8004 registry.

    This is the exact shape the NEW DEPLOY detector watches for (PRD §3 #4).
    """
    row = calldata["action_register"]
    assert row["to"].lower() == "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
    assert _kind(row) == "action"


def test_dev_wallet_value_transfer_is_fund(calldata: dict):
    """0.054 ETH from surfsurf.eth — the tx that proves he owns the channel."""
    row = calldata["fund_ownership_proof"]
    assert int(row["value"]) == 54_000_000_000_000_000
    assert _kind(row) == "fund"


@pytest.mark.parametrize("name", ["reply_pasta", "reply_begging"])
def test_strangers_are_replies_whatever_they_send(calldata: dict, name: str):
    """Both real replies: one value-0, one carrying 1e13 wei of bait.

    Value never promotes a stranger to ``fund``: ``fund`` is about *who*, and
    treating a funded-looking reply as the dev's own tx is how a spoofed feed
    row gets rendered as trusted (PRD §6.4/§6.5).
    """
    assert _kind(calldata[name]) == "reply"


def test_dev_wallet_message_is_not_mislabelled_as_funding():
    """A dev-wallet tx that carries a readable message is a reply, not funding.

    ``fund`` means value moved or empty calldata.  The literal spec says
    "from == dev wallet -> funding", but the feed renders these kinds as words
    next to a message body, and labelling a readable message "fund" would be a
    lie on screen.
    """
    from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET

    assert sig.classify_channel_tx(DEV_WALLET, ANNOUNCE, 0, "0x736f6f6e") == "reply"
    assert sig.classify_channel_tx(DEV_WALLET, ANNOUNCE, 0, "0x") == "fund"


def test_case_and_missing_addresses_never_raise():
    """RPC gives lowercase, Blockscout gives checksummed; both must classify.

    A contract-creation tx has ``to = None``; from the channel that is an
    action, and from a stranger it is not our business but must still return a
    kind rather than raising inside a render path.
    """
    from maxpane_dashboard.data.surf_addresses import ANNOUNCE

    assert sig.classify_channel_tx(ANNOUNCE.lower(), ANNOUNCE.upper(), 0, "0x736f6f6e") == "self"
    assert sig.classify_channel_tx(ANNOUNCE, None, 0, "0x") == "action"
    assert sig.classify_channel_tx(None, None, None, None) == "reply"

    # The vocabulary is WP0's, re-exported — *identity*, not equality.  A second
    # literal here would be a closed vocabulary with two green tests, and a fifth
    # kind added to one copy would pass both suites while the classifier and the
    # models disagreed.  WP0's test_channel_tx_kinds_are_the_four_frozen_strings
    # owns the contents; this line owns the fact that there is only one object.
    from maxpane_dashboard.data import surf_models

    assert sig.CHANNEL_KINDS is surf_models.CHANNEL_KINDS
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`AttributeError: module 'maxpane_dashboard.analytics.surf_signals' has no attribute 'classify_channel_tx'`** (7 new tests fail, the 14 decoder tests still pass).

- [ ] Implement. In `surf_signals.py`, add both WP0 imports under `from typing import Any`, in that order (alphabetical by module — the structural guard in WP2.11 asserts the exact two lines):

```python
from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, OPS_WALLET
from maxpane_dashboard.data.surf_models import CHANNEL_KINDS
```

  Both are stdlib-only boundary modules — no client, no cache, no I/O — so importing them keeps this module pure. `CHANNEL_KINDS` is imported rather than retyped **because WP0 already froze it** and owns its test; there is exactly one tuple in the process, and `classify_channel_tx` is the only function that returns from it.

  Then add `"CHANNEL_KINDS"` and `"classify_channel_tx"` to `__all__` — `CHANNEL_KINDS` as a deliberate re-export, so `from maxpane_dashboard.analytics.surf_signals import CHANNEL_KINDS` keeps working for callers that think of the vocabulary as belonging to the classifier — and append after `decode_utf8_calldata`:

```python
# The four feed kinds (PRD §4) come from WP0's data/surf_models.py and are
# re-exported above, never redefined.  ``self`` is the dev's broadcast,
# ``action`` is the channel EOA doing something onchain, ``fund`` is a dev
# wallet paying the channel's gas, ``reply`` is everyone else — and everyone
# else can write anything, so replies are rendered distinctly and never as the
# dev's words.

_CHANNEL = ANNOUNCE.lower()
_DEV_WALLETS = frozenset({DEV_WALLET.lower(), OPS_WALLET.lower()})


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
```

  and add the shared coercion helper (used from here on) directly above `_addr`:

```python
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
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 21 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "feat(surf): classify channel txs as self/reply/action/fund

The channel is permissionless and already contains a scam reply and a begging
tx. Sender identity decides the kind; value never promotes a stranger to
'fund'. Address comparison is case-folded because the RPC and Blockscout
disagree on casing for the same tx.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.3: `parity_pct` and the detail-formatting helpers

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (append)

**Interfaces:**
- Produces: `parity_pct(imd_price_usd: float | None, fp_price_usd: float | None) -> float | None`; internal `_as_float`, `_fmt_amount`, `_truncate`, `_short_addr`.

**Steps:**

- [ ] Write the failing test. Append:

```python
# --- parity_pct and detail formatting ---------------------------------------
#
# IMD is FP bridged 1:1 (FP locks on Base, IMD mints on mainnet), so the two
# prices should track and the spread is a real arbitrage/health number.  It is
# computed every refresh and never hardcoded: the repo has watched a documented
# "constant" drift three days running (CLAUDE.md rule 4).

# dexscreener_imd.json / dexscreener_fp.json, captured 2026-08-08.
IMD_PRICE_USD = 0.7074
FP_PRICE_USD = 0.7274


def test_parity_uses_the_captured_prices():
    assert sig.parity_pct(IMD_PRICE_USD, FP_PRICE_USD) == pytest.approx(-2.7495188, abs=1e-6)


def test_parity_is_signed_both_ways():
    assert sig.parity_pct(1.10, 1.00) == pytest.approx(10.0)
    assert sig.parity_pct(1.00, 1.00) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "imd,fp",
    [(None, 0.7274), (0.7074, None), (None, None), (0.7074, 0.0), (0.7074, -1.0), ("x", 1.0)],
)
def test_parity_is_none_when_a_price_is_missing_or_impossible(imd, fp):
    """A dead market feed is ``None``, never 0% — 0% would read as 'at parity'."""
    assert sig.parity_pct(imd, fp) is None


def test_amounts_render_without_inventing_precision():
    assert sig._fmt_amount(114_366.899256) == "114,367"
    assert sig._fmt_amount(15_745.0) == "15,745"
    assert sig._fmt_amount(10_000.0) == "10,000"
    assert sig._fmt_amount(0.5) == "0.50"


def test_truncate_flattens_newlines_and_marks_the_cut(calldata: dict):
    """A feed detail is one line: the LP post's two sentences become 48 chars."""
    text = sig.decode_utf8_calldata(calldata["self_lp_add"]["raw_input"])
    assert sig._truncate(text) == "I moved 33 eth to the LP on mainnet https://eth…"
    assert len(sig._truncate(text)) == sig.DETAIL_LIMIT
    assert sig._truncate("soon") == "soon"
    assert sig._truncate("a\nb\n  c") == "a b c"


def test_short_addr_matches_the_prd_poisoning_format():
    """0x + first 8 + … + last 6 (PRD §4) — enough to be checked, never trusted."""
    assert sig._short_addr("0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44") == "0xd6C6d48e…CF7A44"
    assert sig._short_addr("0x8004A169FB4a3325136EB29fA0ceB6D2e539a432") == "0x8004A169…39a432"
    assert sig._short_addr("0x00") == "0x00"
    assert sig._short_addr(None) == ""
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`AttributeError: … has no attribute 'parity_pct'`** (11 new failures).

- [ ] Implement. Add `"parity_pct"` to `__all__` and append after `classify_channel_tx`:

```python
def _as_float(value: Any) -> float | None:
    """Coerce to ``float``; ``None`` when missing or unparseable.  ``bool`` is
    rejected for the same reason as in :func:`_as_int`."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(int(text, 16)) if text.lower().startswith("0x") else float(text)
        except ValueError:
            return None
    return None


def parity_pct(imd_price_usd: float | None, fp_price_usd: float | None) -> float | None:
    """IMD's premium/discount to FP in percent, signed.  ``None`` if unknown.

    IMD is FP bridged 1:1 (FP locks on Base via the OFT adapter, IMD mints on
    mainnet), so the pair should trade together and the spread is a real health
    metric rather than decoration.  Computed every refresh — the 33.0% bridged
    share and this spread both move with every bridge tx and are never
    hardcoded (PRD §6.2).

    A missing or non-positive FP price yields ``None``, never ``0.0``: on a
    dead market feed "0%" reads as *at parity*, which is a statement the
    dashboard has no basis to make.
    """
    imd = _as_float(imd_price_usd)
    fp = _as_float(fp_price_usd)
    if imd is None or fp is None or fp <= 0:
        return None
    return (imd / fp - 1.0) * 100.0


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
```

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 32 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "feat(surf): FP<->IMD parity and the signal-detail formatters

Parity is computed from the two live prices every refresh, and a dead market
feed yields None rather than 0% -- 0% would read as 'at parity'.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.4: `build_signals` — state machine, baseline advance, NEW POST

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (append)

**Interfaces:**
- Produces: `build_signals(baselines: dict, readings: dict, now_ts: float) -> tuple[dict, dict]`; `SIGNAL_NAMES: tuple[str, ...]`; `SIGNAL_OUTPUT_KEYS: tuple[str, ...]`; internal `_Det`, `_ok`, `_watch`, `_fired`, `_dead`, `_rows`, `_newest`, `_event_rows`, `_fresh_event`, `_advance`, `_fired_store`, `_detect_post`, `_DETECTORS`.

**Steps:**

- [ ] Write the failing test. Append the shared harness plus the NEW POST and TTL tests:

```python
# ---------------------------------------------------------------------------
# build_signals — the six detectors
#
# Every payload below is the real 2026-08-07 sequence out of
# tests/fixtures/surf/captures/.  NOW is 2026-08-07T05:20:00Z, 53 minutes after
# the LP-add post, so all of that day's events are inside the 24 h FIRED TTL.
# ---------------------------------------------------------------------------

NOW = 1_786_080_000.0        # 2026-08-07T05:20:00Z

# ops_eth_token_transfers.json — the two OFT bridge-in mints to frenpet.eth.
MINT_1 = {
    "ts": 1_786_076_339.0,
    "tx_hash": "0x17084b1bfc998a457416c1ba9689f50ca04efc6e160b7e28d4c75dc89bcea85c",
    "amount": 10_000.0,
    "to_label": "frenpet.eth",
}
MINT_2 = {
    "ts": 1_786_076_495.0,
    "tx_hash": "0xc7acbcc0b164a0eaecb1220484e97d410bb159ca42d3c61165a26fe03c1d0a01",
    "amount": 114_366.899256,
    "to_label": "frenpet.eth",
}
# ops_eth_txs.json / ops_eth_token_transfers.json — IMD -> BurnExecutor.
BURN_0731 = {
    "ts": 1_785_464_459.0,
    "tx_hash": "0xa25b08cfc4b2ca2ada16374001e377961514b50985d887ffcfc60a5194e5cd5c",
    "amount": 31_064.0,
}
BURN_0805 = {
    "ts": 1_785_903_035.0,
    "tx_hash": "0x11bf8d3e3fd83538faa906521c5f5f0592f6b6117c3d4967c97f05b3ae753a6e",
    "amount": 15_745.0,
}
# announce_eth_txs.json nonce 4 — the ERC-8004 registration, the exact shape
# NEW DEPLOY watches for.
REGISTER_ACTION = {
    "ts": 1_779_469_691.0,
    "tx_hash": "0xa4ce159e5100eba90d231efb103b2c727a25660bacf9a2f02de569a4a1d1c1c2",
    "kind": "action",
    "label": "register()",
    "wallet_label": "announce",
}
# The same call replayed into the current poll window.  The matrix pins one
# clock, and NEW DEPLOY's FIRED row is about an event that just happened; the
# real 2026-05-22 timestamp is exercised by
# ``test_an_event_older_than_the_ttl_renders_as_history_not_news``.
FRESH_ACTION = {**REGISTER_ACTION, "ts": NOW - 240.0}
# announce_eth_txs.json nonce 13.
LP_POST_TS = 1_786_076_831.0
LP_POST_TEXT = (
    "I moved 33 eth to the LP on mainnet https://etherscan.io/tx/"
    "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669. "
    "Hopefully in the coming days will be able to share more what been "
    "working on, as always 0 promises."
)
LP_POST_DETAIL = '#14 "I moved 33 eth to the LP on mainnet https://eth…"'

# SYNTHETIC: no hooked IMD v4 pool exists yet — all 19 live ones have
# hooks=0x0.  The hook address is the dev's *existing* Vibecoins launchpad
# hook, used here only to give the row a realistic non-zero value.
HOOKLESS_POOL = {
    "ts": 1_786_000_000.0,
    "tx_hash": "0x" + "b0" * 32,
    "hooks": "0x0000000000000000000000000000000000000000",
}
HOOKED_POOL = {
    "ts": 1_786_079_000.0,
    "tx_hash": "0x" + "a5" * 32,
    "hooks": "0xd6C6d48e8ff38DD7F242E34442FBdaA10eCF7A44",
}

# Supply before the 2026-08-07 bridge-in: the live 2,376,731.868679 from
# imd_token.json minus the two mints.
SUPPLY_BEFORE = 2_252_364.969423
SUPPLY_AFTER_MINTS = 2_376_731.868679
LP_LIQUIDITY_BEFORE = 1_000_000_000_000
LP_LIQUIDITY_AFTER_ADD = 1_330_000_000_000     # +33.0%


def _baseline(**overrides) -> dict:
    """The persisted state as of 2026-08-06 — the day before the LP add."""
    base = {
        "announce_nonce": 13,
        "channel_tx_count": 20,
        "lp_liquidity": LP_LIQUIDITY_BEFORE,
        "ops_nonce": 36,
        "dev_nonce": 2350,
        "gate_open": False,
        "identities_written": 1,
        "imd_supply": SUPPLY_BEFORE,
        "bridge_tx": "",
        "bridge_ts": 0.0,
        "deploy_tx": "",
        "deploy_ts": 0.0,
        "v4_tx": "",
        "v4_ts": 0.0,
        "burn_tx": BURN_0731["tx_hash"],
        "burn_ts": BURN_0731["ts"],
        "fired": {},
    }
    base.update(overrides)
    return base


def _readings(**overrides) -> dict:
    """A quiet refresh: everything read successfully, nothing moved."""
    read = {
        "announce_nonce": 13,
        "channel_tx_count": 20,
        "announce_last_text": None,
        "announce_last_ts": None,
        "lp_liquidity": LP_LIQUIDITY_BEFORE,
        "ops_nonce": 36,
        "dev_nonce": 2350,
        "v4_hook_pools": [],
        "gate_open": False,
        "identities_written": 1,
        "deploy_events": [],
        "bridge_mints": [],
        "burn_transfers": [],
        "imd_supply": SUPPLY_BEFORE,
    }
    read.update(overrides)
    return read


def _sig(name: str, baselines: dict, readings: dict, now: float = NOW) -> tuple:
    """``(state, detail, age_s)`` for one detector."""
    out, _ = sig.build_signals(baselines, readings, now)
    return (
        out[f"sig_{name}_state"],
        out[f"sig_{name}_detail"],
        out[f"sig_{name}_age_s"],
    )


def test_output_keys_are_exactly_the_prd_contract():
    out, _ = sig.build_signals(_baseline(), _readings(), NOW)
    assert set(out) == set(sig.SIGNAL_OUTPUT_KEYS)
    assert sig.SIGNAL_NAMES == ("post", "lp", "gate", "deploy", "bridge", "burn")


def test_quiet_refresh_leaves_post_ok():
    assert _sig("post", _baseline(), _readings()) == (
        "ok", "nonce 13 · no new post", None
    )


def test_new_post_fires_with_the_decoded_body():
    """The flagship: nonce 13 -> 14 with the LP-add message."""
    state, detail, age = _sig(
        "post",
        _baseline(),
        _readings(
            announce_nonce=14,
            channel_tx_count=21,
            announce_last_text=LP_POST_TEXT,
            announce_last_ts=LP_POST_TS,
        ),
    )
    assert state == "fired"
    assert detail == LP_POST_DETAIL
    assert age == pytest.approx(NOW - LP_POST_TS)


def test_a_reply_is_a_watch_not_a_post():
    """Replies raise the Blockscout tx count without moving the nonce.

    Anyone can write to the channel; a reply is worth surfacing but it is not
    the dev speaking (PRD §6.4).
    """
    assert _sig("post", _baseline(), _readings(channel_tx_count=21)) == (
        "watch", "reply on channel · 21 txs", None
    )


def test_first_ever_read_seeds_the_baseline_and_never_fires():
    """An empty cache must not report the whole history as brand-new.

    This is the false-first-sweep regression that shipped once already
    (2b0b43c, 'stop the first sweep of every launch reporting a false
    mismatch').
    """
    state, detail, age = _sig("post", {}, _readings(announce_nonce=14))
    assert state == "ok"
    assert detail == "nonce 14 · baseline set"
    assert age is None


def test_channel_outage_is_none_not_ok():
    assert _sig(
        "post", _baseline(), _readings(announce_nonce=None, channel_tx_count=None)
    ) == (None, "channel unavailable", None)


def test_baselines_advance_only_on_successful_reads():
    _, advanced = sig.build_signals(
        _baseline(),
        _readings(announce_nonce=None, lp_liquidity=None, imd_supply=None, gate_open=None),
        NOW,
    )
    assert advanced["announce_nonce"] == 13
    assert advanced["lp_liquidity"] == LP_LIQUIDITY_BEFORE
    assert advanced["imd_supply"] == SUPPLY_BEFORE
    assert advanced["gate_open"] is False


def test_a_lagging_replica_cannot_drag_a_nonce_baseline_down():
    """Nonces only go up.

    A replica that answers 13 after we recorded 14 would otherwise reset the
    baseline, and the next correct answer (14) would re-fire NEW POST with a
    message the user already read.
    """
    _, advanced = sig.build_signals(
        _baseline(announce_nonce=14), _readings(announce_nonce=13), NOW
    )
    assert advanced["announce_nonce"] == 14
    state, _, _ = _sig("post", _baseline(announce_nonce=14), _readings(announce_nonce=13))
    assert state == "ok"


def test_fired_persists_for_24h_then_relaxes_with_a_last_detail():
    """PRD §3: FIRED holds for FIRED_TTL_S with its age, then relaxes."""
    fired_at = NOW - 3600.0
    base = _baseline(fired={"post": {"ts": fired_at, "detail": LP_POST_DETAIL}})
    assert _sig("post", base, _readings()) == ("fired", LP_POST_DETAIL, 3600.0)

    # Exactly at the TTL it is no longer FIRED (strict <).
    edge = _baseline(fired={"post": {"ts": NOW - sig.FIRED_TTL_S, "detail": LP_POST_DETAIL}})
    state, detail, age = _sig("post", edge, _readings())
    assert state == "ok"
    assert detail == f"nonce 13 · no new post · last: {LP_POST_DETAIL}"
    assert age == pytest.approx(float(sig.FIRED_TTL_S))


def test_fired_events_survive_a_restart_through_the_returned_baselines():
    """The advanced baselines carry the fired store back to the cache."""
    _, advanced = sig.build_signals(
        _baseline(),
        _readings(announce_nonce=14, announce_last_text="soon", announce_last_ts=LP_POST_TS),
        NOW,
    )
    assert advanced["fired"]["post"]["ts"] == LP_POST_TS
    assert advanced["fired"]["post"]["detail"] == '#14 "soon"'
    # Replayed from the persisted state with no new event: still FIRED.
    assert _sig("post", advanced, _readings(announce_nonce=14))[0] == "fired"
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`AttributeError: … has no attribute 'build_signals'`** (10 new failures).

- [ ] Implement. Add `"SIGNAL_NAMES"`, `"SIGNAL_OUTPUT_KEYS"` and `"build_signals"` to `__all__`, then append:

```python
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


# --- registry --------------------------------------------------------------

#: ``(name, detector)`` in render order.  :data:`SIGNAL_NAMES` and
#: :data:`SIGNAL_OUTPUT_KEYS` are derived from it, so the module can never
#: advertise a key it does not emit.
_DETECTORS: tuple[tuple[str, Any], ...] = (
    ("post", _detect_post),
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

    Two rules, and every correctness bug in this module is one of them being
    skipped:

    1. A scalar baseline moves **only** when its reading is not ``None``.  A
       failed read leaves the previous value in place — it never writes a
       sentinel into persisted state (CLAUDE.md).
    2. Counters in :data:`MONOTONIC_BASELINES` never move down.

    Event streams keep ``(tx, ts)``.  A *successful but empty* read seeds the
    pair with ``("", 0.0)`` — "the window was read and held nothing" — which is
    what lets the next event fire; an outage (``None``) leaves the pair alone.
    """
    out = {key: value for key, value in baselines.items() if key != "fired"}

    for key in BASELINE_SCALARS:
        value = readings.get(key)
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
    """The six detector rows plus the baselines to persist.

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
```

  and extend the typing import at the top to `from typing import Any, NamedTuple`.

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 42 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "feat(surf): signal state machine + NEW POST detector

Baselines advance only on successful reads and nonce counters never move down,
so a lagging replica cannot re-fire a post the user already read. FIRED is
consulted before the live state and persists 24h with its age, then relaxes to
'last: ...'. Clock injected; no wall-clock fallback anywhere.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.5: LP MIGRATION detector

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (append)

**Interfaces:**
- Consumes: `_fresh_event`, `_event_rows`, `_short_addr`.
- Produces: `_detect_lp(base: dict, read: dict, now: float) -> _Det`; `("lp", _detect_lp)` in `_DETECTORS`.

**Steps:**

- [ ] Write the failing test. Append:

```python
# --- 2. LP MIGRATION --------------------------------------------------------
#
# He promised onchain to announce before moving the LP (nonce 8), so the
# decrease is the act itself.  An *increase* is movement worth watching but is
# the opposite event -- that is exactly what 2026-08-07 was.


def test_liquidity_holding_is_ok():
    assert _sig("lp", _baseline(), _readings()) == ("ok", "liquidity holds", None)


def test_liquidity_decrease_fires():
    assert _sig("lp", _baseline(), _readings(lp_liquidity=677_000_000_000)) == (
        "fired", "LIQUIDITY OUT -32.3%", 0.0
    )


def test_liquidity_increase_is_a_watch_not_a_fire():
    """The 2026-08-07 add: 33 ETH *into* the pool, not out of it."""
    assert _sig("lp", _baseline(), _readings(lp_liquidity=LP_LIQUIDITY_AFTER_ADD)) == (
        "watch", "LP added +33.0%", None
    )


def test_any_frenpet_eth_activity_is_a_watch():
    """29 lifetime txs on that wallet: any nonce move is signal (PRD §3 #2)."""
    assert _sig("lp", _baseline(), _readings(ops_nonce=37)) == (
        "watch", "frenpet.eth active · nonce 37", None
    )


def test_hooked_v4_initialize_fires_as_the_launch():
    """SYNTHETIC event, real rule: currency IMD and hooks != 0x0 IS the launch."""
    state, detail, age = _sig("lp", _baseline(), _readings(v4_hook_pools=[HOOKED_POOL]))
    assert state == "fired"
    assert detail == "V4 LAUNCH · hooks 0xd6C6d48e…CF7A44"
    assert age == pytest.approx(NOW - HOOKED_POOL["ts"])


def test_hookless_pools_are_noise():
    """All 19 live IMD v4 pools are third-party and hookless.

    Firing on them would make the flagship detector permanently wrong on day
    one, and would advance the baseline past a real hooked pool.
    """
    state, detail, _ = _sig("lp", _baseline(), _readings(v4_hook_pools=[HOOKLESS_POOL]))
    assert state == "ok"
    assert detail == "liquidity holds"
    _, advanced = sig.build_signals(_baseline(), _readings(v4_hook_pools=[HOOKLESS_POOL]), NOW)
    assert advanced["v4_tx"] == ""


def test_lp_outage_is_none():
    assert _sig(
        "lp",
        _baseline(),
        _readings(lp_liquidity=None, ops_nonce=None, v4_hook_pools=None),
    ) == (None, "LP state unavailable", None)
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`KeyError: 'sig_lp_state'`** in `_sig` (7 new failures).

- [ ] Implement. Insert before the `# --- registry ---` marker:

```python
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
```

  and add `("lp", _detect_lp),` to `_DETECTORS`.

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 49 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "feat(surf): LP MIGRATION detector

A hooked v4 Initialize for IMD is the launch; a liquidity decrease on position
1167726 is the act he promised to announce first; an increase and any
frenpet.eth nonce move are precursors. All 19 live IMD v4 pools are hookless
third-party noise and are filtered before they can advance the baseline.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.6: GATE OPEN and NEW DEPLOY detectors

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (append)

**Interfaces:**
- Produces: `_detect_gate(base, read, now) -> _Det`, `_detect_deploy(base, read, now) -> _Det`; both registered in `_DETECTORS`.

**Steps:**

- [ ] Write the failing test. Append:

```python
# --- 3. GATE OPEN -----------------------------------------------------------
#
# identityAllowed() has been false since 2026-05-14 with 1/2000 written.  The
# moment "the agent" flips it, any IDMD holder can write an identity.
#
# The written count is rendered without a "/2000" denominator on purpose: the
# cap is a documented number and the hero widget reads it live (CLAUDE.md
# rule 4).


def test_closed_gate_is_ok_and_says_so():
    assert _sig("gate", _baseline(), _readings()) == ("ok", "closed · 1 written", None)


def test_gate_flip_fires():
    assert _sig("gate", _baseline(), _readings(gate_open=True)) == (
        "fired", "GATE OPEN · 1 written", 0.0
    )


def test_writes_without_a_flip_we_saw_are_a_watch():
    """The gate opened and closed between two polls — the write proves it."""
    assert _sig("gate", _baseline(), _readings(identities_written=2)) == (
        "watch", "1→2 written · gate closed", None
    )


def test_an_already_open_gate_on_first_read_does_not_fire():
    state, detail, age = _sig("gate", {}, _readings(gate_open=True))
    assert state == "ok"
    assert detail == "OPEN · 1 written"
    assert age is None


def test_gate_outage_is_none():
    assert _sig(
        "gate", _baseline(), _readings(gate_open=None, identities_written=None)
    ) == (None, "gate unavailable", None)


# --- 4. NEW DEPLOY ----------------------------------------------------------
#
# The ERC-8004 registration at channel nonce 4 was exactly this shape: an
# outbound contract call from the announce EOA.  Contract creations by
# surfsurf.eth are the other half.


def test_no_new_contract_is_ok():
    assert _sig("deploy", _baseline(), _readings()) == ("ok", "no new contract", None)


def test_an_outbound_contract_call_fires():
    state, detail, age = _sig("deploy", _baseline(), _readings(deploy_events=[FRESH_ACTION]))
    assert state == "fired"
    assert detail == "action register() · announce"
    assert age == pytest.approx(240.0)


def test_an_event_older_than_the_ttl_renders_as_history_not_news():
    """The real register() call is from 2026-05-22 — detected late, it is not news.

    A cold cache with a wide log window would otherwise shout FIRED about a
    76-day-old transaction: the false-first-sweep bug wearing a different hat.
    The event is still recorded, so the row says what it was.
    """
    state, detail, age = _sig("deploy", _baseline(), _readings(deploy_events=[REGISTER_ACTION]))
    assert state == "ok"
    assert detail == "last: action register() · announce"
    assert age == pytest.approx(NOW - REGISTER_ACTION["ts"])


def test_a_contract_creation_fires():
    event = {
        "ts": NOW - 120.0,
        "tx_hash": "0x" + "c0" * 32,
        "kind": "deploy",
        "label": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        "wallet_label": "surfsurf.eth",
    }
    state, detail, age = _sig("deploy", _baseline(), _readings(deploy_events=[event]))
    assert state == "fired"
    assert detail == "new contract 0x8004A169…39a432 · surfsurf.eth"
    assert age == pytest.approx(120.0)


def test_dev_nonce_movement_alone_is_a_watch():
    assert _sig("deploy", _baseline(), _readings(dev_nonce=2351)) == (
        "watch", "surfsurf.eth nonce 2350→2351", None
    )


def test_deploy_outage_is_none():
    assert _sig(
        "deploy", _baseline(), _readings(deploy_events=None, dev_nonce=None)
    ) == (None, "dev activity unavailable", None)
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`KeyError: 'sig_gate_state'`** (11 new failures).

- [ ] Implement. Insert before the registry marker:

```python
# --- 3. GATE OPEN ----------------------------------------------------------


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


# --- 4. NEW DEPLOY ---------------------------------------------------------


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
```

  and add `("gate", _detect_gate),` and `("deploy", _detect_deploy),` to `_DETECTORS`, in that order after `("lp", …)`.

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 60 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "feat(surf): GATE OPEN and NEW DEPLOY detectors

Gate fires on the false->true flip and watches identity writes that happen
between two polls. Deploy fires on a contract creation or an outbound call from
the announce EOA (the ERC-8004 registration's exact shape) and watches
surfsurf.eth's nonce. The written count carries no hardcoded /2000.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.7: BRIDGE STAGE and BURN detectors

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Test: `tests/analytics/test_surf_signals.py` (append)

**Interfaces:**
- Produces: `_detect_bridge(base, read, now) -> _Det`, `_detect_burn(base, read, now) -> _Det`; both registered in `_DETECTORS`, which is then complete at six.

**Steps:**

- [ ] Write the failing test. Append:

```python
# --- 5. BRIDGE STAGE --------------------------------------------------------
#
# The earliest link in the 2026-08-07 chain: mint 04:18:59 -> mint 04:21:35 ->
# approve 04:22:23 -> add 04:23:23 -> announce 04:27:11.  Staging preceded the
# add by 12 minutes (PRD §3 #5).


def test_no_mints_in_window_is_ok():
    assert _sig("bridge", _baseline(), _readings()) == ("ok", "no mints in window", None)


def test_an_oft_mint_to_a_dev_wallet_fires_on_the_newest_row():
    state, detail, age = _sig("bridge", _baseline(), _readings(bridge_mints=[MINT_1, MINT_2]))
    assert state == "fired"
    assert detail == "mint 114,367 IMD → frenpet.eth"
    assert age == pytest.approx(NOW - MINT_2["ts"])


def test_supply_growth_with_no_dev_mint_is_a_watch():
    """Somebody bridged in, but not to a wallet we track."""
    assert _sig("bridge", _baseline(), _readings(imd_supply=SUPPLY_BEFORE + 10_000.0)) == (
        "watch", "supply +10,000 · no dev-wallet mint", None
    )


def test_bridge_outage_is_none():
    assert _sig(
        "bridge", _baseline(), _readings(bridge_mints=None, imd_supply=None)
    ) == (None, "bridge logs unavailable", None)


# --- 6. BURN ----------------------------------------------------------------
#
# LP fees (IMD side) -> BurnExecutor -> OFT-send to a Base burn receiver ->
# mainnet totalSupply drops.  The transfer to the executor lands *before* the
# supply moves, which is why it is a WATCH rather than nothing.


def test_flat_supply_is_ok():
    assert _sig("burn", _baseline(), _readings()) == ("ok", "supply flat", None)


def test_a_verified_supply_drop_fires():
    """The 2026-08-05 burn: 15,745 IMD, matching announce nonce 12 to the minute."""
    assert _sig("burn", _baseline(), _readings(imd_supply=SUPPLY_BEFORE - 15_745.0)) == (
        "fired", "burn 15,745 IMD", 0.0
    )


def test_a_transfer_to_the_burn_executor_is_a_watch():
    assert _sig("burn", _baseline(), _readings(burn_transfers=[BURN_0805])) == (
        "watch", "15,745 IMD → BurnExecutor", None
    )


def test_burn_outage_is_none():
    assert _sig(
        "burn", _baseline(), _readings(imd_supply=None, burn_transfers=None)
    ) == (None, "supply unavailable", None)
```

- [ ] Run it and watch it fail: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → **`KeyError: 'sig_bridge_state'`** (8 new failures).

- [ ] Implement. Insert before the registry marker:

```python
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
```

  and add `("bridge", _detect_bridge),` and `("burn", _detect_burn),` to `_DETECTORS`, completing the six in PRD order.

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 68 passed (`test_output_keys_are_exactly_the_prd_contract` now covers all 18 keys).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "feat(surf): BRIDGE STAGE and BURN detectors complete the six

Bridge fires on Transfer(from=0x0) to a dev wallet -- IMD has no mint function,
so that log is unambiguous staging, and on 2026-08-07 it landed 264 s ahead of
the LP add. Burn requires two successful supply reads; a None supply never
reaches the comparison.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.8: The 6 × 4 table-driven matrix

**Files:**
- Modify: `tests/analytics/test_surf_signals.py`

**Interfaces:**
- Consumes: `sig.build_signals`, `sig.SIGNAL_NAMES`, the `_baseline` / `_readings` helpers.
- Produces: no production code — this task is a coverage lock. It must **fail** if a seventh detector is added without a matrix row.

**Steps:**

- [ ] Write the test. Append:

```python
# ---------------------------------------------------------------------------
# The matrix: every detector x every state.
#
# PRD §8 asks for exactly this table.  It is a coverage lock as much as a
# behaviour test: `test_the_matrix_covers_every_detector` fails the moment a
# seventh detector lands without its four rows, and the None column is the
# machine-checkable half of success criterion 3.
# ---------------------------------------------------------------------------

MATRIX: tuple[tuple[str, str, dict, str], ...] = (
    # (signal, expected state, reading overrides, expected detail)
    ("post", "ok", {}, "nonce 13 · no new post"),
    ("post", "watch", {"channel_tx_count": 21}, "reply on channel · 21 txs"),
    ("post", "fired",
     {"announce_nonce": 14, "announce_last_text": LP_POST_TEXT, "announce_last_ts": LP_POST_TS},
     LP_POST_DETAIL),
    ("post", None, {"announce_nonce": None, "channel_tx_count": None}, "channel unavailable"),

    ("lp", "ok", {}, "liquidity holds"),
    ("lp", "watch", {"ops_nonce": 37}, "frenpet.eth active · nonce 37"),
    ("lp", "fired", {"lp_liquidity": 677_000_000_000}, "LIQUIDITY OUT -32.3%"),
    ("lp", None, {"lp_liquidity": None, "ops_nonce": None, "v4_hook_pools": None},
     "LP state unavailable"),

    ("gate", "ok", {}, "closed · 1 written"),
    ("gate", "watch", {"identities_written": 2}, "1→2 written · gate closed"),
    ("gate", "fired", {"gate_open": True}, "GATE OPEN · 1 written"),
    ("gate", None, {"gate_open": None, "identities_written": None}, "gate unavailable"),

    ("deploy", "ok", {}, "no new contract"),
    ("deploy", "watch", {"dev_nonce": 2351}, "surfsurf.eth nonce 2350→2351"),
    ("deploy", "fired", {"deploy_events": [FRESH_ACTION]}, "action register() · announce"),
    ("deploy", None, {"deploy_events": None, "dev_nonce": None}, "dev activity unavailable"),

    ("bridge", "ok", {}, "no mints in window"),
    ("bridge", "watch", {"imd_supply": SUPPLY_BEFORE + 10_000.0},
     "supply +10,000 · no dev-wallet mint"),
    ("bridge", "fired", {"bridge_mints": [MINT_1, MINT_2]}, "mint 114,367 IMD → frenpet.eth"),
    ("bridge", None, {"bridge_mints": None, "imd_supply": None}, "bridge logs unavailable"),

    ("burn", "ok", {}, "supply flat"),
    ("burn", "watch", {"burn_transfers": [BURN_0805]}, "15,745 IMD → BurnExecutor"),
    ("burn", "fired", {"imd_supply": SUPPLY_BEFORE - 15_745.0}, "burn 15,745 IMD"),
    ("burn", None, {"imd_supply": None, "burn_transfers": None}, "supply unavailable"),
)


@pytest.mark.parametrize(
    "name,expected_state,overrides,expected_detail",
    MATRIX,
    ids=[f"{row[0]}-{row[1] or 'outage'}" for row in MATRIX],
)
def test_signal_matrix(name, expected_state, overrides, expected_detail):
    state, detail, _ = _sig(name, _baseline(), _readings(**overrides))
    assert state == expected_state
    assert detail == expected_detail


def test_the_matrix_covers_every_detector_and_every_state():
    covered = {(row[0], row[1]) for row in MATRIX}
    expected = {
        (name, state)
        for name in sig.SIGNAL_NAMES
        for state in ("ok", "watch", "fired", None)
    }
    assert covered == expected


@pytest.mark.parametrize("name,expected_state,overrides,_detail", MATRIX,
                         ids=[f"{row[0]}-{row[1] or 'outage'}" for row in MATRIX])
def test_no_row_of_the_matrix_moves_an_unread_baseline(name, expected_state, overrides, _detail):
    """Whatever a detector decides, a ``None`` reading never writes a baseline."""
    base = _baseline()
    _, advanced = sig.build_signals(base, _readings(**overrides), NOW)
    for key, value in overrides.items():
        if value is None and key in sig.BASELINE_SCALARS:
            assert advanced[key] == base[key], key
```

- [ ] Run it and watch it pass first time — and prove it bites before accepting that. Temporarily change the `("burn", "fired", …)` row's expected detail to `"burn 15,746 IMD"`, run
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k "matrix" -v` → expect `AssertionError: assert 'burn 15,745 IMD' == 'burn 15,746 IMD'` on `test_signal_matrix[burn-fired]`. Restore the row.

- [ ] Also prove the coverage lock bites: temporarily delete the four `gate` rows from `MATRIX` and run
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k covers_every -v` → expect `AssertionError` on the set comparison, with the four missing `('gate', …)` pairs in the diff. Restore them.

- [ ] Run to green: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 117 passed (24 matrix rows × 2 parametrised tests + the coverage lock + the 68 from earlier tasks).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add tests/analytics/test_surf_signals.py && git commit -m "test(surf): table-driven matrix, six detectors x four states

PRD §8's table, plus a coverage lock that fails when a seventh detector lands
without its rows, plus a per-row assertion that a None reading never moves a
baseline.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.9: The two poisoned-baseline regressions (mutation-checked)

**Files:**
- Modify: `tests/analytics/test_surf_signals.py`

**Interfaces:**
- Consumes: `sig.build_signals`, `sig.FIRED_TTL_S`.
- Produces: no production code. Two regression tests, each with a **recorded mutation check** (PRD §8; CLAUDE.md "prove a test bites").

**Steps:**

- [ ] Write the false-BURN regression. Append:

```python
# ---------------------------------------------------------------------------
# The two poisoned-baseline regressions.
#
# Both are recorded failures, not hypotheticals: CLAUDE.md's "a failed read is
# None, never 0" exists because a client turned an outage into a zero and the
# zero got persisted, and PRD §6.1 names the supply case specifically.
# ---------------------------------------------------------------------------


def test_a_failed_supply_read_cannot_fire_burn():
    """supply None must not read as 0 and burn 2.37M tokens.

    MUTATION CHECK (run it, watch it go red, restore):
    in ``_detect_burn`` replace

        if supply is not None and base_supply is not None and supply < base_supply:

    with the coercion that shipped in the original bug

        supply = float(supply or 0)
        base_supply = float(base_supply or 0)
        if supply < base_supply:

    -> this test fails with ``AssertionError: assert 'fired' is None``, and the
    detail on that row reads ``burn 2,252,365 IMD``: the entire supply, burned
    by a network hiccup.  ``test_a_failed_supply_read_cannot_poison_the_
    persisted_baseline`` fails with it.
    """
    state, detail, age = _sig("burn", _baseline(), _readings(imd_supply=None))
    assert state is None
    assert detail == "supply unavailable"
    assert age is None


def test_a_failed_supply_read_cannot_poison_the_persisted_baseline():
    """The outage must not survive itself: the old supply stays in the cache."""
    base = _baseline()
    _, advanced = sig.build_signals(base, _readings(imd_supply=None), NOW)
    assert advanced["imd_supply"] == SUPPLY_BEFORE
    # And the next successful read compares against the real previous value,
    # so no burn is invented on recovery either.
    state, _, _ = _sig("burn", advanced, _readings(imd_supply=SUPPLY_BEFORE))
    assert state == "ok"


def test_an_lp_outage_cannot_un_fire_a_migration():
    """A network blip must never retract an event already shown.

    MUTATION CHECK (run it, watch it go red, restore):
    in ``build_signals`` replace

        if entry is not None and now - entry["ts"] < FIRED_TTL_S:

    with

        if det.state is not None and entry is not None and now - entry["ts"] < FIRED_TTL_S:

    -> this test fails with ``AssertionError: assert None == 'fired'``: the
    outage clears a FIRED row that is 1 h old.
    """
    fired_at = NOW - 3600.0
    base = _baseline(fired={"lp": {"ts": fired_at, "detail": "LIQUIDITY OUT -32.3%"}})
    state, detail, age = _sig(
        "lp", base, _readings(lp_liquidity=None, ops_nonce=None, v4_hook_pools=None)
    )
    assert state == "fired"
    assert detail == "LIQUIDITY OUT -32.3%"
    assert age == pytest.approx(3600.0)


def test_an_outage_does_not_extend_or_reset_the_fired_age():
    """The age tracks the event, not the last successful poll."""
    fired_at = NOW - 7200.0
    base = _baseline(fired={"lp": {"ts": fired_at, "detail": "LIQUIDITY OUT -32.3%"}})
    _, advanced = sig.build_signals(base, _readings(lp_liquidity=None), NOW)
    assert advanced["fired"]["lp"]["ts"] == fired_at
    _, _, age = _sig("lp", advanced, _readings(lp_liquidity=None), now=NOW + 600.0)
    assert age == pytest.approx(7800.0)


def test_a_fired_row_relaxes_but_the_event_is_never_forgotten():
    """After the TTL the row is ok/watch again and still names what happened."""
    base = _baseline(
        fired={"lp": {"ts": NOW - sig.FIRED_TTL_S - 1.0, "detail": "LIQUIDITY OUT -32.3%"}}
    )
    state, detail, age = _sig("lp", base, _readings())
    assert state == "ok"
    assert detail == "liquidity holds · last: LIQUIDITY OUT -32.3%"
    assert age == pytest.approx(float(sig.FIRED_TTL_S) + 1.0)
```

- [ ] Run: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 122 passed (the 5 new tests included).

- [ ] **Perform mutation check 1 and record the output.** Apply the `_detect_burn` mutation exactly as written in the docstring, run
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k failed_supply -v`
  → expect **2 failed**: `test_a_failed_supply_read_cannot_fire_burn - AssertionError: assert 'fired' is None` and `test_a_failed_supply_read_cannot_poison_the_persisted_baseline - AssertionError: assert 'fired' == 'ok'`. Restore the original guard **by editing it back by hand** — never `git checkout --` a file in this repo, the working tree may hold another agent's uncommitted work (CLAUDE.md). Re-run to confirm green.

- [ ] **Perform mutation check 2 and record the output.** Apply the `build_signals` mutation exactly as written, run
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k un_fire -v`
  → expect `FAILED … test_an_lp_outage_cannot_un_fire_a_migration - AssertionError: assert None == 'fired'`. Restore by hand and re-run to confirm green.

- [ ] Run the whole file: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 122 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add tests/analytics/test_surf_signals.py && git commit -m "test(surf): the two poisoned-baseline regressions, mutation-checked

A None supply must not fire BURN and must not overwrite the cached supply; an
LP outage must not un-fire a migration or move its age. Both mutation checks
were run: the burn guard flip fires 'burn 2,252,365 IMD', and gating the FIRED
store on a live state clears a 1h-old FIRED row.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.10: Success criteria 2 and 3 — the 2026-08-07 replay and the total outage

**Files:**
- Modify: `tests/analytics/test_surf_signals.py`

**Interfaces:**
- Consumes: `sig.build_signals` only — three sequential calls, feeding each call's `advanced_baselines` into the next, exactly as `SurfManager` will.
- Produces: no production code.

**Steps:**

- [ ] Write the replay test. Append:

```python
# ---------------------------------------------------------------------------
# Success criterion 2 (PRD §11): replay the real 2026-08-07 LP-add sequence and
# assert BRIDGE STAGE fires before NEW POST.
#
# The real choreography, from ops_eth_txs.json / ops_eth_token_transfers.json /
# announce_eth_txs.json:
#
#   04:18:59  OFT mint      10,000.000000 IMD -> frenpet.eth   0x17084b1b…
#   04:21:35  OFT mint     114,366.899256 IMD -> frenpet.eth   0xc7acbcc0…
#   04:22:23  approve      IMD -> NFPM (ops nonce 36)          0x0031c5c8…
#   04:23:23  multicall    increaseLiquidity (ops nonce 37)    0x90a0f8e2…
#   04:27:11  announce     "I moved 33 eth to the LP…"         0xe397869a…
#
# Eight minutes end to end.  BRIDGE STAGE flags it at the first mint, 492 s
# before the announcement everyone else was waiting for.  Each poll
# feeds the previous poll's advanced baselines back in, which is what the
# manager does and what makes the ordering claim real rather than staged.

T1_STAGED = 1_786_076_520.0   # 04:22:00Z -- both mints landed, LP untouched
T2_ADDED = 1_786_076_700.0    # 04:25:00Z -- liquidity added, no post yet
T3_POSTED = 1_786_076_900.0   # 04:28:20Z -- the announcement landed


def test_the_2026_08_07_sequence_fires_bridge_before_post():
    base = _baseline()

    # --- poll 1: 04:22:00Z.  Only the mints have happened.
    out1, base = sig.build_signals(
        base,
        _readings(bridge_mints=[MINT_1, MINT_2], imd_supply=SUPPLY_AFTER_MINTS),
        T1_STAGED,
    )
    assert out1["sig_bridge_state"] == "fired"
    assert out1["sig_bridge_detail"] == "mint 114,367 IMD → frenpet.eth"
    assert out1["sig_bridge_age_s"] == pytest.approx(T1_STAGED - MINT_2["ts"])
    assert out1["sig_post_state"] == "ok"
    assert out1["sig_lp_state"] == "ok"

    # --- poll 2: 04:25:00Z.  33 ETH went in; the LP row escalates to WATCH and
    # BRIDGE stays FIRED without re-firing on the mints it already reported.
    out2, base = sig.build_signals(
        base,
        _readings(
            bridge_mints=[MINT_1, MINT_2],
            imd_supply=SUPPLY_AFTER_MINTS,
            lp_liquidity=LP_LIQUIDITY_AFTER_ADD,
            ops_nonce=38,
        ),
        T2_ADDED,
    )
    assert out2["sig_lp_state"] == "watch"
    assert out2["sig_lp_detail"] == "LP added +33.0%"
    assert out2["sig_bridge_state"] == "fired"
    assert out2["sig_bridge_age_s"] == pytest.approx(T2_ADDED - MINT_2["ts"])
    assert out2["sig_post_state"] == "ok"

    # --- poll 3: 04:28:20Z.  The announcement lands last, as it always does.
    out3, base = sig.build_signals(
        base,
        _readings(
            bridge_mints=[MINT_1, MINT_2],
            imd_supply=SUPPLY_AFTER_MINTS,
            lp_liquidity=LP_LIQUIDITY_AFTER_ADD,
            ops_nonce=38,
            announce_nonce=14,
            channel_tx_count=21,
            announce_last_text=LP_POST_TEXT,
            announce_last_ts=LP_POST_TS,
        ),
        T3_POSTED,
    )
    assert out3["sig_post_state"] == "fired"
    assert out3["sig_post_detail"] == LP_POST_DETAIL
    assert out3["sig_bridge_state"] == "fired"

    # The claim itself: staging was seen first, and is older on screen.
    assert base["fired"]["bridge"]["ts"] < base["fired"]["post"]["ts"]
    assert out3["sig_bridge_age_s"] > out3["sig_post_age_s"]
    # The lead time the dashboard bought, measured from the mint it reported…
    assert base["fired"]["post"]["ts"] - base["fired"]["bridge"]["ts"] == pytest.approx(336.0)
    # …and from the first mint of the pair, which is when the staging began.
    assert LP_POST_TS - MINT_1["ts"] == pytest.approx(492.0)


def test_the_replay_never_re_fires_an_event_it_already_reported():
    """Polling the same window twice reports one event, not two."""
    base = _baseline()
    _, base = sig.build_signals(
        base, _readings(bridge_mints=[MINT_1, MINT_2], imd_supply=SUPPLY_AFTER_MINTS), T1_STAGED
    )
    first_fired = base["fired"]["bridge"]["ts"]
    out, base = sig.build_signals(
        base, _readings(bridge_mints=[MINT_1, MINT_2], imd_supply=SUPPLY_AFTER_MINTS), T2_ADDED
    )
    assert base["fired"]["bridge"]["ts"] == first_fired
    assert out["sig_bridge_age_s"] == pytest.approx(T2_ADDED - MINT_2["ts"])


def test_a_rolled_log_window_does_not_look_like_a_new_event():
    """When the newest mint scrolls out of the window, the older one is not news."""
    base = _baseline()
    _, base = sig.build_signals(base, _readings(bridge_mints=[MINT_1, MINT_2]), T1_STAGED)
    out, advanced = sig.build_signals(base, _readings(bridge_mints=[MINT_1]), T2_ADDED)
    assert out["sig_bridge_state"] == "fired"          # persisted, not re-fired
    assert advanced["fired"]["bridge"]["ts"] == MINT_2["ts"]
    assert advanced["bridge_tx"] == MINT_2["tx_hash"]


# ---------------------------------------------------------------------------
# Success criterion 3 (PRD §11): under a full outage no signal fires and no
# baseline moves.
# ---------------------------------------------------------------------------


def _blackout() -> dict:
    return {key: None for key in sig.READING_KEYS}


def test_total_outage_fires_nothing_and_moves_nothing():
    base = _baseline()
    out, advanced = sig.build_signals(base, _blackout(), NOW)

    for name in sig.SIGNAL_NAMES:
        assert out[f"sig_{name}_state"] is None, name
        assert out[f"sig_{name}_detail"].endswith("unavailable"), name
        assert out[f"sig_{name}_age_s"] is None, name

    assert {k: v for k, v in advanced.items() if k != "fired"} == {
        k: v for k, v in base.items() if k != "fired"
    }
    assert advanced["fired"] == {}


def test_total_outage_keeps_a_recent_fired_row_visible():
    """Criterion 3 says nothing *new* fires — not that history disappears."""
    base = _baseline(fired={"burn": {"ts": NOW - 600.0, "detail": "burn 15,745 IMD"}})
    out, advanced = sig.build_signals(base, _blackout(), NOW)
    assert out["sig_burn_state"] == "fired"
    assert out["sig_burn_age_s"] == pytest.approx(600.0)
    assert advanced["fired"]["burn"]["ts"] == NOW - 600.0
    assert advanced["imd_supply"] == SUPPLY_BEFORE


def test_an_empty_cache_plus_a_full_outage_is_completely_silent():
    """First launch with the network down: six unknowns, no invented state."""
    out, advanced = sig.build_signals({}, _blackout(), NOW)
    assert all(out[f"sig_{name}_state"] is None for name in sig.SIGNAL_NAMES)
    assert advanced == {"fired": {}}
```

- [ ] Run: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 128 passed (the 6 new tests included).

- [ ] Prove the ordering assertion bites: temporarily swap poll 1 and poll 3 in `test_the_2026_08_07_sequence_fires_bridge_before_post` (feed the announce reading at `T1_STAGED` and the mints at `T3_POSTED`), run
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k 2026_08_07 -v` → expect the final `assert base["fired"]["bridge"]["ts"] < base["fired"]["post"]["ts"]` to fail. Restore the original order.

- [ ] Run the whole file: `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 127 passed.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add tests/analytics/test_surf_signals.py && git commit -m "test(surf): replay the 2026-08-07 LP-add sequence and the total outage

Success criterion 2: three sequential polls over the real mint -> add ->
announce choreography, each fed the previous poll's baselines. BRIDGE STAGE
fires 336 s before NEW POST -- 492 s from the first of the two mints. Criterion
3: a full blackout leaves every state
None, every baseline untouched, and any recent FIRED row still on screen.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

### Task WP2.11: Purity guard, key surface, and the WP4/WP3 hand-off

**Files:**
- Modify: `maxpane_dashboard/analytics/surf_signals.py`
- Modify: `tests/analytics/test_surf_signals.py`

**Interfaces:**
- Produces: the final `__all__`; `build_signals` as **WP4's** entry point (the manager is its only caller); `SIGNAL_OUTPUT_KEYS` as the 18 `sig_*` names **WP3's** widgets render out of the flat dict (PRD §5 signal group). WP3 never imports this module — its AST import-hygiene test forbids it — so the key list is the whole of what reaches the widget layer.
- Consumes: nothing new.

**Steps:**

- [ ] Write the structural tests. Append:

```python
# ---------------------------------------------------------------------------
# Structural guards.
#
# This module is required to be pure (CLAUDE.md: analytics/ is "PURE functions:
# signals, EV math. No I/O, no Textual imports.").  "No test touches the
# network" is asserted structurally rather than by mocking, because there is no
# transport here to inject a raising stub into: the assertion is that the
# module cannot reach a network or a clock at all.
# ---------------------------------------------------------------------------

import re

_MODULE_SOURCE = Path(sig.__file__).read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Source with docstrings and comments stripped.

    The guards below assert on what the code *does*; a docstring is allowed to
    name the thing it forbids.
    """
    return re.sub(r"#[^\n]*", "", re.sub(r'"""(?:.|\n)*?"""', "", source))


def test_module_is_pure():
    code = _code_only(_MODULE_SOURCE)
    for forbidden in (
        "import requests", "import httpx", "import aiohttp", "import urllib",
        "import socket", "import time", "import datetime", "import asyncio",
        "from textual", "import textual",
        "time.time(", "datetime.now(", "utcnow(",
        "maxpane_dashboard.data.surf_client", "maxpane_dashboard.data.surf_cache",
    ):
        assert forbidden not in code, forbidden


def test_the_only_data_imports_are_the_two_wp0_boundary_modules():
    """WP0 is the single dependency, and it is exactly two stdlib-only modules.

    ``surf_addresses`` and ``surf_models`` are boundary declarations — constants
    and dataclasses, no I/O — so importing them does not cost this module its
    purity.  The client (WP1), the cache and the manager (WP4) are not importable
    from here at any point, and the list is compared exactly rather than by
    substring so a third import cannot arrive unnoticed.

    The second half is the re-export rule: ``CHANNEL_KINDS`` is frozen once, in
    WP0's models module.  A local literal would give one closed vocabulary two
    green tests — WP0's ``test_channel_tx_kinds_are_the_four_frozen_strings``
    and this suite's — so a fifth kind added to one copy would pass both while
    the classifier and the models disagreed about what may be returned.
    """
    from maxpane_dashboard.data import surf_models

    imports = [line for line in _MODULE_SOURCE.splitlines() if line.startswith("from maxpane")]
    assert imports == [
        "from maxpane_dashboard.data.surf_addresses import ANNOUNCE, DEV_WALLET, OPS_WALLET",
        "from maxpane_dashboard.data.surf_models import CHANNEL_KINDS",
    ]
    assert sig.CHANNEL_KINDS is surf_models.CHANNEL_KINDS
    assert "CHANNEL_KINDS: tuple[str, ...] = (" not in _code_only(_MODULE_SOURCE)


def test_no_live_value_is_hardcoded():
    """CLAUDE.md rule 4: parity, supply, pool composition and burn totals are read.

    The numbers that appear in this module are structural (24 h, 48 columns,
    percent) — never a measured one.
    """
    code = _code_only(_MODULE_SOURCE)
    for measured in ("2376731", "2,376,731", "0.7074", "58849", "33.0", "1148", "2000"):
        assert measured not in code, measured


def test_public_surface_is_the_frozen_one():
    for name in (
        "decode_utf8_calldata", "classify_channel_tx", "parity_pct", "build_signals",
        "FIRED_TTL_S", "SIGNAL_NAMES", "SIGNAL_OUTPUT_KEYS", "READING_KEYS",
    ):
        assert name in sig.__all__, name
        assert hasattr(sig, name), name
    assert sig.FIRED_TTL_S == 86400


def test_signal_output_keys_match_the_prd_naming():
    """PRD §5: ``sig_{post,lp,gate,deploy,bridge,burn}_{state,detail,age_s}``."""
    assert len(sig.SIGNAL_OUTPUT_KEYS) == 18
    assert sig.SIGNAL_OUTPUT_KEYS[:3] == ("sig_post_state", "sig_post_detail", "sig_post_age_s")
    assert set(sig.SIGNAL_OUTPUT_KEYS) == {
        f"sig_{name}_{field}"
        for name in ("post", "lp", "gate", "deploy", "bridge", "burn")
        for field in ("state", "detail", "age_s")
    }


def test_every_state_value_is_one_of_the_four():
    """No detector may invent a fifth state string (PRD §5)."""
    for _name, expected_state, overrides, _detail in MATRIX:
        out, _ = sig.build_signals(_baseline(), _readings(**overrides), NOW)
        for key, value in out.items():
            if key.endswith("_state"):
                assert value in ("ok", "watch", "fired", None), (key, value)


def test_details_fit_the_signals_panel():
    """Every freshly-built detail stays inside a plausible row width.

    The panel gets ~55 columns at the pinned full-layout width; a longer detail
    would leave the panel wearing a permanent ``‹ widen`` marker (the FWA
    buy-gate footnote lesson).  The budget covers what a detector *builds*; the
    composed ``… · last: …`` form deliberately exceeds it when both halves are
    long, and truncating that is the widget's call, not this module's.
    """
    for _name, _state, overrides, _detail in MATRIX:
        out, _ = sig.build_signals(_baseline(), _readings(**overrides), NOW)
        for key, value in out.items():
            if key.endswith("_detail"):
                assert len(value) <= 55, (key, len(value), value)
```

- [ ] Run and watch `test_details_fit_the_signals_panel` and `test_no_live_value_is_hardcoded` report real findings:
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k "pure or hardcoded or surface or naming or state_value or fit or boundary" -v`.
  Expected first-run failure: **`test_the_only_data_imports_are_the_two_wp0_boundary_modules`** passes (both WP0 imports present, in that order, and no local `CHANNEL_KINDS` literal left behind by WP2.2), and any detail longer than 55 columns fails with its exact length. If a detail is too long, shorten the *detector's* string (not the assertion) and re-run the matrix — the expected strings in `MATRIX` must be updated in the same edit.

- [ ] Prove the re-export half bites — the check that a fifth kind cannot hide in a second copy. Paste `CHANNEL_KINDS: tuple[str, ...] = ("self", "reply", "action", "fund", "spam")` back into `surf_signals.py` below the imports, run
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -k "boundary or missing_addresses" -v`
  → both `test_the_only_data_imports_are_the_two_wp0_boundary_modules` (the `is` assertion, then the source check) and WP2.2's `test_case_and_missing_addresses_never_raise` FAIL. Delete the literal and re-run to green.

- [ ] Fix `__all__` so the frozen surface is complete. In `surf_signals.py` the final list is:

```python
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
```

- [ ] Run the full analytics suite plus the whole repo suite to prove nothing else moved:
  `.venv/bin/python -m pytest tests/analytics/test_surf_signals.py -v` → 135 passed;
  `.venv/bin/python -m pytest -q` → the existing ~2100 tests still green (this WP adds no shared-file edits, so any failure elsewhere is somebody else's uncommitted work — report it, do not fix it).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/analytics/surf_signals.py tests/analytics/test_surf_signals.py && git commit -m "test(surf): purity guard and frozen key surface for surf_signals

Structural assertion in place of a raising transport: the module cannot import
a network client, Textual, or a clock, and its only data imports are WP0's two
stdlib-only boundary modules - surf_addresses and surf_models, the latter for
CHANNEL_KINDS, which is re-exported here rather than redefined. Also pins the
18 PRD §5 signal keys and a 55-column budget on every detail string.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TYwckkUCQZRsyRpTKBL6L7"
```

---

## Hand-off notes for the WPs downstream

**WP0 (`data/surf_models.py`, `tests/data/test_surf_models.py`)** must:

1. include all 18 `SIGNAL_OUTPUT_KEYS` in `SURF_KEYS` (it already does — the `sig_*` block) **and own the containment assertion**, `set(surf_signals.SIGNAL_OUTPUT_KEYS) <= set(SURF_KEYS)`. Nobody else can: WP3's `tests/widgets/test_surf_widget_contract.py` imports `SURF_KEYS` alone, and its own AST import-hygiene test forbids the widget layer from touching `analytics/`. The test is spelled out under Open issues.

**WP4 (`data/surf_cache.py` / `data/surf_manager.py`)** must:

1. build the `readings` dict using exactly `READING_KEYS`, with `None` for every failed read and `[]` only for a *successful* empty log window — the difference is what makes BRIDGE STAGE able to fire at all;
2. call `classify_channel_tx` when building `feed_items[].kind` and `deploy_events[].kind`, and `decode_utf8_calldata` for `feed_items[].text`;
3. call `parity_pct(imd_price_usd, fp_price_usd)` for the `parity_pct` key;
4. persist `advanced_baselines` verbatim through `SurfCache.set_baselines()` and pass `get_baselines()` back in — the `fired` sub-dict is part of the payload and must not be stripped.

**WP3 (widgets)** must run every `sig_*_detail` through `safe_markup`: the NEW POST detail embeds an attacker-writable message body.

---

## Open issues

- **Resolved (was: "the containment assertion has to live on WP3's side", with no file named).** `SIGNAL_OUTPUT_KEYS` is frozen here; `SURF_KEYS` is frozen in **WP0's** `data/surf_models.py` — not WP3's, which owns the widgets. WP2's own `test_signal_output_keys_match_the_prd_naming` checks the *shape* of the names, never their agreement with `SURF_KEYS`, so without an owner a rename on either side ships as a widget that silently receives `None`. The assertion's owner is **WP0's `tests/data/test_surf_models.py`**, next to `test_every_signal_has_all_three_facets`, which already reasons about the same `sig_*` block and where `pytest` is already imported. Whoever edits wp0.md adds exactly this:

  ```python
  def test_signal_output_keys_are_a_subset_of_surf_keys() -> None:
      """SIGNAL_OUTPUT_KEYS (WP2) must all exist in SURF_KEYS (this module).

      Skips until WP2 lands ``analytics/surf_signals.py``; from then on this is
      the only test in the repo that compares the two frozen key surfaces, so a
      rename on either side fails here — instead of surfacing as a widget that
      quietly renders ``None`` for a signal nobody notices is missing.
      """
      surf_signals = pytest.importorskip("maxpane_dashboard.analytics.surf_signals")
      from maxpane_dashboard.data.surf_models import SURF_KEYS

      missing = sorted(set(surf_signals.SIGNAL_OUTPUT_KEYS) - set(SURF_KEYS))
      assert not missing, f"signal keys absent from SURF_KEYS: {missing}"
  ```

  Prove it bites the usual way: rename one entry of `SIGNAL_OUTPUT_KEYS` (e.g. `sig_burn_state` → `sig_burns_state`), watch this test go red with that key in the message, restore. Why WP0 and not WP4: WP0's file is where `SURF_KEYS` is frozen, and the guard then runs from the moment WP2's suite is green — including inside WP2's own final `pytest -q`. WP3 cannot host it (its `tests/widgets/test_surf_widget_contract.py` imports `SURF_KEYS` only, and its AST import-hygiene test forbids the widgets from importing `analytics/` at all). If WP0 is already frozen by the time this is read, the fallback owner is **WP4's `tests/data/test_surf_manager.py`**, which hard-imports both surfaces and needs no `importorskip` — put it in one file, not both, and record the choice here and in the owning WP.
- The `v4_hook_pools` fired path is exercised with a **synthetic** row — no hooked IMD v4 pool exists yet (all 19 live ones have `hooks=0x0`). The hookless-noise test uses the real shape; the hooked test is the only unrealised event in the suite and should be re-verified against the real `Initialize` log the day the hook launches.
- `identities_written` is fed from `IdentityHashUpdated` logs by WP1/WP3; if that count turns out to be non-monotonic (a re-write of the same token id), `MONOTONIC_BASELINES` would suppress a legitimate WATCH. The registry has one written identity today, so this is untestable against live data — flagged rather than guessed.
- Burn amount for the 2026-07-31 transfer (31,064 IMD) comes from the research doc, not from a captured `total.value`; it is used only as an opaque baseline seed and no test asserts it.
- **PRD §3 #5 and §1 say staging preceded the LP add by 12 minutes; the captures say 264 s.** The full choreography in `ops_eth_txs.json` / `ops_eth_token_transfers.json` runs 04:18:59 (mint 1) → 04:21:35 (mint 2) → 04:22:23 (approve) → 04:23:23 (add) → 04:27:11 (announce) = 8 min 12 s end to end, so the earliest warning is 264 s before the add and 492 s before the post. This WP's tests use the captured timestamps; the "12 min" figure in the PRD prose should be corrected by whoever owns the doc — it is prose, not a data contract, so nothing here is blocked on it.
