"""Fact pins for the WhitelistCurator captures, and the vendored ABI's provenance.

Every number a later curator work package hardcodes is asserted here, once,
against the committed payload it came from.  A re-capture that moves one of them
fails in this file — the file that owns the fact — instead of drifting silently
through six work packages.

Nothing here touches the network: the whole suite reads committed bytes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.curator_fixtures import CAPTURE_A, state_from_bundle, CAPTURES, capture, capture_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG = _REPO_ROOT / "maxpane_dashboard"
_VENDORED_ABI = _PKG / "abis" / "curator" / "whitelist_curator.json"


def _extract_abi_in_memory(name: str = "contract.json") -> list[dict]:
    """The extraction ``scripts/vendor_curator_abi.py`` performs, re-run here.

    Deliberately *not* an import of the script: ``scripts/`` is absent from a
    pipx install and nothing under test may depend on it.  Six lines duplicated
    is the price of the guarantee.
    """
    return capture(name)["abi"]


def test_the_two_abi_captures_agree() -> None:
    """Two agents saved the same Blockscout endpoint. Divergence means one is stale."""
    assert _extract_abi_in_memory("contract.json") == _extract_abi_in_memory(
        "wc_abi.json"
    )


def test_the_vendored_abi_matches_the_capture() -> None:
    """A hand-edit of the vendored artifact fails here.

    The committed bytes must be exactly what the extraction produces from the
    capture, formatting included, so the artifact stays a pure function of the
    provenance.
    """
    expected = json.dumps(_extract_abi_in_memory(), indent=2) + "\n"
    assert _VENDORED_ABI.read_text(encoding="utf-8") == expected


def test_the_vendored_abi_declares_every_event_the_source_declares() -> None:
    """Set equality against ``source.sol`` — this is what catches a truncated save."""
    src = capture_text("source.sol")
    declared = set(re.findall(r"^\s*event\s+(\w+)\s*\(", src, re.MULTILINE))
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    assert declared == {e["name"] for e in abi if e["type"] == "event"}
    assert declared == {
        "Launched",
        "Deposited",
        "FirstDeposit",
        "HourSaved",
        "Settled",
        "Rescued",
    }


def test_the_vendored_abi_declares_every_error_the_source_declares() -> None:
    """Ten custom errors. A missing one is a revert the client cannot name."""
    src = capture_text("source.sol")
    declared = set(re.findall(r"^\s*error\s+(\w+)\s*\(", src, re.MULTILINE))
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    assert declared == {e["name"] for e in abi if e["type"] == "error"}
    assert len(declared) == 10


def test_the_vendored_abi_holds_every_view_the_dashboard_reads() -> None:
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    names = {e["name"] for e in abi if e["type"] == "function"}
    required = {
        "contributors",
        "totalVolume",
        "totalContributors",
        "totalTxCount",
        "POINTS_PER_ETH",
        "launchTime",
        "hourlyThreshold",
        "gracePeriod",
        "hourDuration",
        "minDeposit",
        "minEscalation",
        "creditCap",
        "firstJudgedHour",
        "deployer",
        "isSettled",
        "currentHour",
        "currentHourTotal",
        "ethNeededThisHour",
        "timeLeftInHour",
        "lastActiveHour",
        "earlyMultiplierBps",
        "stats",
        "pointsOf",
        "weightOf",
        "contributedBy",
        "txCountOf",
        "requiredNext",
        "firstHourOf",
        "previewPoints",
    }
    assert required <= names, sorted(required - names)


def test_the_vendored_abi_carries_no_state_changing_call_the_dashboard_could_make() -> (
    None
):
    """Read-only by hard constraint.

    ``deposit()``, ``settle()`` and ``rescue()`` exist on chain and are in the
    ABI — that is correct, the ABI is the contract's.  What must never exist is
    a curator module that encodes one; WP7's guardrail scan owns that.  This
    test records the three names so the scan has a list to work from.
    """
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    mutating = {
        e["name"]
        for e in abi
        if e["type"] == "function"
        and e.get("stateMutability") not in ("view", "pure")
    }
    assert mutating == {"deposit", "settle", "rescue"}


def test_nothing_under_maxpane_dashboard_imports_scripts() -> None:
    """``scripts/`` is a dev tool; a pipx install ships without it."""
    offenders = []
    for path in sorted(_PKG.rglob("*.py")):
        code = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+scripts\b", code, re.MULTILINE):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, offenders


def test_the_vendored_abi_is_not_fetched_at_runtime() -> None:
    """No curator module may name a Blockscout smart-contracts URL."""
    for path in sorted(_PKG.rglob("curator*.py")):
        code = path.read_text(encoding="utf-8")
        assert "smart-contracts" not in code, path.name


# ==========================================================================
# WP0.7 — ownership, hygiene, and the fact pins
# ==========================================================================

from collections import Counter  # noqa: E402

from maxpane_dashboard.data import curator_addresses as A  # noqa: E402
from maxpane_dashboard.data.curator_models import CURATOR_KEYS  # noqa: E402
from tests.curator_fixtures import (  # noqa: E402
    CURATOR_FIXTURES,
    LIVE,
    live_bundles,
)

#: The captures committed with the research session.  Named, never counted:
#: WP1 lands more files under ``captures/live/`` at unpredictable moments, and a
#: count-based guard would turn this suite red for a *successful* capture.
REQUIRED_CAPTURES = (
    "source.sol",
    "contract.json",
    "wc_abi.json",
    "creation_tx.json",
    "tenderly_logs.json",
    "batch.json",
    "results.json",
    "ann_page_0.json",
    "hour_boundary_h1_h2.json",
    *(f"bs_page_{i}.json" for i in range(8)),
    "README.md",
)


# ---- ownership and hygiene -----------------------------------------------


def test_the_required_captures_are_committed_and_readable() -> None:
    names = {p.name for p in CAPTURES.iterdir()}
    missing = [n for n in REQUIRED_CAPTURES if n not in names]
    assert not missing, missing
    for name in REQUIRED_CAPTURES:
        if name.endswith(".json"):
            assert json.loads((CAPTURES / name).read_text("utf-8")) is not None, name


def test_the_required_set_is_named_and_not_a_count() -> None:
    """The guard above must not be re-expressed as ``len(...) == 18``.

    WP1 is adding bundles under ``captures/live/`` while other work packages
    build.  A count-based guard would go red for a *successful* capture, which
    is the worst possible failure mode: it teaches the next agent to delete the
    evidence.
    """
    assert len(REQUIRED_CAPTURES) == 18
    present = {p.name for p in CAPTURES.iterdir() if p.is_file()}
    assert set(REQUIRED_CAPTURES) <= present
    # Extra files at this level are fine and must stay fine.
    assert LIVE.name == "live"


def test_the_fixtures_root_holds_directories_only() -> None:
    """WP0 owns captures/, WP1 owns captures/live/, every other WP owns its own
    subdirectory.  A loose ``*.json`` at the root is a file with no owner, and
    it is how one WP's slice lands in another WP's glob."""
    loose = sorted(
        p.name
        for p in CURATOR_FIXTURES.iterdir()
        if p.is_file() and p.name not in ("README.md", "MANIFEST.md")
    )
    assert loose == [], f"put these in a per-work-package subdirectory: {loose}"


def test_no_capture_carries_an_api_key() -> None:
    for path in sorted(CAPTURES.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text("utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"


def test_no_live_bundle_breaks_the_reader() -> None:
    """Zero bundles is the normal pre-WP1 state and must stay green."""
    for path in live_bundles():
        assert json.loads(path.read_text("utf-8")) is not None, path.name


# ---- decoding helpers -----------------------------------------------------

#: ``lastActiveHour()`` and ``stats()`` are multi-word returns; everything else
#: in the captured round is one word.  Keyed by selector, because two of the 21
#: answered ``0x0`` and positional reasoning cannot tell those apart.
_WORDS = {name: A.VIEW_RETURN_WORDS[name] for name in A.VIEW_RETURN_WORDS}


def _decoded_batch() -> dict[str, int | tuple[int, ...]]:
    """``{selector: value}`` from ``batch.json`` + ``results.json``."""
    by_selector = {c["params"][0]["data"]: c["id"] for c in capture("batch.json")}
    results = {r["id"]: r["result"] for r in capture("results.json")}
    name_of = {getattr(A, n): n for n in A.SELECTOR_PREIMAGES}
    out: dict[str, int | tuple[int, ...]] = {}
    for selector, req_id in by_selector.items():
        raw = results[req_id][2:]
        n = _WORDS[name_of[selector]]
        words = tuple(int(raw[i * 64 : (i + 1) * 64], 16) for i in range(n))
        out[selector] = words if n > 1 else words[0]
    return out


def _logs() -> list[dict]:
    """The 377 rows of the full-history sweep.

    ``tenderly_logs.json`` is the whole JSON-RPC envelope, not a bare list --
    the plan's snippets say otherwise and they are wrong about the shape.
    """
    return capture("tenderly_logs.json")["result"]


def _deposits() -> list[dict]:
    """Every ``Deposited`` log, decoded into the nine words plus provenance."""
    out = []
    for log in _logs():
        if log["topics"][0] != A.TOPIC_DEPOSITED:
            continue
        data = log["data"][2:]
        w = [int(data[i * 64 : (i + 1) * 64], 16) for i in range(len(data) // 64)]
        out.append(
            {
                "contributor": "0x" + log["topics"][1][-40:],
                "hour": int(log["topics"][2], 16),
                "amount_wei": w[0],
                "credited_delta_wei": w[1],
                "weight_added_wei": w[2],
                "new_weight_wei": w[3],
                "tx_count": w[4],
                "hour_total_wei": w[5],
                "early_bps": w[6],
                "block_number": int(log["blockNumber"], 16),
                "tx_hash": log["transactionHash"],
                "log_index": int(log["logIndex"], 16),
            }
        )
    return out


def _first_deposit_with(*, early_bps: int, amount_wei: int) -> dict:
    matches = [
        e
        for e in _deposits()
        if e["early_bps"] == early_bps and e["amount_wei"] == amount_wei
    ]
    assert matches, f"no captured deposit at {early_bps} bps for {amount_wei} wei"
    return matches[0]


# ---- the batch round ------------------------------------------------------


def test_the_batch_round_decodes_to_the_documented_state() -> None:
    """The 21 views, at 2026-08-16 ~21:12 UTC, hour 1 of the game.

    Keyed by *selector*, never by list position: two of the 21 returned 0x0 and
    positional reasoning cannot tell them apart (WP0.4).
    """
    v = _decoded_batch()
    assert v[A.SEL_POINTS_PER_ETH] == 1000
    assert v[A.SEL_CREDIT_CAP] == 1000 * 10**18
    assert v[A.SEL_HOURLY_THRESHOLD] == 5 * 10**18
    assert v[A.SEL_GRACE_PERIOD] == 86_400
    assert v[A.SEL_HOUR_DURATION] == 3_600
    assert v[A.SEL_MIN_DEPOSIT] == 5 * 10**16  # 0.05 ETH
    assert v[A.SEL_MIN_ESCALATION] == 10**17  # 0.1 ETH
    assert v[A.SEL_FIRST_JUDGED_HOUR] == 24
    assert v[A.SEL_LAUNCH_TIME] == 1_786_910_327
    assert v[A.SEL_CURRENT_HOUR] == 1
    assert v[A.SEL_IS_SETTLED] == 0
    assert v[A.SEL_ETH_NEEDED_THIS_HOUR] == 0
    assert v[A.SEL_TIME_LEFT_IN_HOUR] == 2_796
    # 19491 bps == 1.9491x.  NOT ~1.99x -- a fixture calibrated to 1.99 would
    # miscompute every weight derived from it (plan amendment A1).
    assert v[A.SEL_EARLY_MULTIPLIER_BPS] == 19_491
    assert v[A.SEL_STATS] == (0x560119983627C22D4F, 143, 222)
    # stats() and the three public counters are different storage reads of the
    # same numbers; them agreeing is what makes the slow-tier cross-check
    # meaningful.
    assert v[A.SEL_TOTAL_VOLUME] == v[A.SEL_STATS][0]
    assert v[A.SEL_TOTAL_CONTRIBUTORS] == v[A.SEL_STATS][1]
    assert v[A.SEL_TOTAL_TX_COUNT] == v[A.SEL_STATS][2]
    # The hour-boundary hazard is INVISIBLE in this capture: the current hour
    # IS the last active hour, so both agree.  That is precisely why WP1
    # capture A exists.
    assert v[A.SEL_LAST_ACTIVE_HOUR] == (1, v[A.SEL_CURRENT_HOUR_TOTAL])


def test_the_deployer_view_returns_the_vendored_address() -> None:
    """``deployer()`` is an ``address``, so it decodes to the low 20 bytes."""
    v = _decoded_batch()
    assert f"0x{v[A.SEL_DEPLOYER]:040x}" == A.DEPLOYER.lower()


def test_the_derived_config_is_self_consistent() -> None:
    v = _decoded_batch()
    assert v[A.SEL_FIRST_JUDGED_HOUR] == v[A.SEL_GRACE_PERIOD] // v[A.SEL_HOUR_DURATION]
    # The doomsday deadlines every phase test is calibrated on.
    assert v[A.SEL_LAUNCH_TIME] + v[A.SEL_GRACE_PERIOD] == 1_786_996_727  # 08-17 19:58:47Z
    assert v[A.SEL_LAUNCH_TIME] + 25 * 3600 == 1_787_000_327  # 08-17 20:58:47Z
    assert v[A.SEL_LAUNCH_TIME] == A.LAUNCH_TIME


def test_the_hourly_threshold_is_not_recoverable_from_the_two_keys_beside_it() -> None:
    """Why ``hourly_threshold_eth`` had to become a key of its own.

    Two widgets render the number -- the hero clock's ``fed X.XX/5.00 ETH`` and
    the volume sparkline's labelled survival bar -- and the tempting shortcut is
    ``hour_fed_eth + hour_needed_eth``.  It is wrong, and this capture is the
    counter-example: ``ethNeededThisHour()`` (``source.sol`` line 547) returns 0
    for the whole grace period and again whenever a judged hour is already safe,
    so the sum reconstructs the threshold **only while an hour is short**.  Here
    734.61 ETH had been fed against a 5 ETH bar and the view answered 0.

    Without the key a widget hardcodes 5.00, which is CLAUDE.md hard constraint
    4 -- the documented value, not the live one.
    """
    v = _decoded_batch()
    fed = v[A.SEL_CURRENT_HOUR_TOTAL]
    needed = v[A.SEL_ETH_NEEDED_THIS_HOUR]
    threshold = v[A.SEL_HOURLY_THRESHOLD]
    assert needed == 0 and fed > threshold
    assert fed + needed != threshold
    # And the safe-hour arm is not a special case of grace: the same view
    # returns 0 for any judged hour already over the bar.
    assert threshold == 5 * 10**18


def test_the_first_judged_hour_is_a_read_value_not_the_literal_24() -> None:
    """Why ``first_judged_hour`` had to become a key of its own.

    ``n/a until hour 24`` (HOUR AT RISK during grace) and the closest-calls
    empty state both print it.  It happens to equal
    ``gracePeriod // hourDuration`` on this deployment, but **neither operand is
    in the flat dict either**, so with no key the widget types the 24 -- and a
    redeploy with a different grace window would render a lie.
    """
    v = _decoded_batch()
    assert v[A.SEL_FIRST_JUDGED_HOUR] == 24
    assert v[A.SEL_FIRST_JUDGED_HOUR] == v[A.SEL_GRACE_PERIOD] // v[A.SEL_HOUR_DURATION]
    assert "first_judged_hour" in CURATOR_KEYS
    assert "hourly_threshold_eth" in CURATOR_KEYS


def test_the_live_immutables_agree_with_the_vendored_pins() -> None:
    """CLAUDE.md: read values live, never hardcode a documented one.

    ``curator_addresses`` pins ``LAUNCH_TIME`` and ``CREATION_BLOCK`` so the
    archive has an origin under a full outage.  This is the test that proves the
    pin equals what the chain answered, which is the only thing that makes
    keeping it honest.
    """
    v = _decoded_batch()
    assert v[A.SEL_LAUNCH_TIME] == A.LAUNCH_TIME
    launched = [l for l in _logs() if l["topics"][0] == A.TOPIC_LAUNCHED]
    assert int(launched[0]["blockNumber"], 16) == A.CREATION_BLOCK


def test_the_launched_event_carries_the_same_config_the_views_return() -> None:
    """Two independent sources for the eight immutables: the ``once`` views and
    the ``Launched`` log emitted in the constructor.  If they ever disagree, the
    decoder is wrong -- nothing on this contract can change them."""
    v = _decoded_batch()
    launched = [l for l in _logs() if l["topics"][0] == A.TOPIC_LAUNCHED][0]
    data = launched["data"][2:]
    w = [int(data[i * 64 : (i + 1) * 64], 16) for i in range(7)]
    assert w[0] == v[A.SEL_LAUNCH_TIME]
    assert w[1] == v[A.SEL_HOURLY_THRESHOLD]
    assert w[2] == v[A.SEL_GRACE_PERIOD]
    assert w[3] == v[A.SEL_HOUR_DURATION]
    assert w[4] == v[A.SEL_MIN_DEPOSIT]
    assert w[5] == v[A.SEL_MIN_ESCALATION]
    assert w[6] == v[A.SEL_CREDIT_CAP]


# ---- the log sweep --------------------------------------------------------


def test_the_log_sweep_holds_the_history_the_folds_are_tested_against() -> None:
    """377 logs from the deploy block.

    The plan and the captures' README both say **226** ``Deposited`` rows.  The
    committed payload holds **231**.  Recounted here rather than copied, because
    a fold calibrated to 226 would drop five real deposits and nothing would say
    so.
    """
    logs = _logs()
    assert len(logs) == 377
    by_topic = Counter(l["topics"][0] for l in logs)
    assert by_topic[A.TOPIC_DEPOSITED] == 231
    assert by_topic[A.TOPIC_FIRST_DEPOSIT] == 145
    assert by_topic[A.TOPIC_LAUNCHED] == 1
    assert sum(by_topic.values()) == 377
    # 1 + 231 + 145 == 377: no other event has ever fired.
    for absent in (A.TOPIC_HOUR_SAVED, A.TOPIC_SETTLED, A.TOPIC_RESCUED):
        assert by_topic[absent] == 0


def test_first_deposit_index_is_one_based_and_contiguous() -> None:
    """H6: ``FirstDeposit.index`` is 1-based and monotonic; it maxes at exactly
    the contributor count the sweep saw."""
    idx = sorted(
        int(l["topics"][2], 16)
        for l in _logs()
        if l["topics"][0] == A.TOPIC_FIRST_DEPOSIT
    )
    assert idx == list(range(1, len(idx) + 1))
    # The sweep caught two more than the batch round's totalContributors (143):
    # the two pulls are minutes apart and the game was landing a deposit every
    # few seconds.
    assert max(idx) == 145
    assert max(idx) - _decoded_batch()[A.SEL_TOTAL_CONTRIBUTORS] == 2


def test_the_deposit_hours_are_the_two_the_game_had_lived(  ) -> None:
    """The hour comes off the event's **indexed second topic** -- no timestamp
    is needed to bucket it, which is why the boundary hazard cannot reach the
    series at all."""
    hours = Counter(e["hour"] for e in _deposits())
    assert set(hours) == {0, 1}
    assert hours[0] == 149 and hours[1] == 82


def test_the_weight_formula_cross_check_event_is_present_and_exact() -> None:
    """The one real witness for ``weightAdded = creditedDelta * earlyBps // 1e4``.

    0.05 ETH at 19 975 bps -> 0.099875 ETH of weight, to the wei.  WP3.4 asserts
    this with ``==``; here we prove the event it asserts against exists.

    ``wp0.md`` writes the expected value as ``99_875_000_000_000_00``, which is
    one digit short -- 9.9875e15, not 9.9875e16.  The chain's number is below.
    """
    ev = _first_deposit_with(early_bps=19_975, amount_wei=5 * 10**16)
    assert ev["credited_delta_wei"] == 5 * 10**16
    assert ev["weight_added_wei"] == 99_875_000_000_000_000  # 0.099875e18
    assert ev["weight_added_wei"] == 5 * 10**16 * 19_975 // 10_000
    # It is the very first deposit of the game, and the announce EOA made it.
    assert ev["contributor"] == A.ANNOUNCE.lower()
    assert ev["hour"] == 0 and ev["tx_count"] == 1


def test_every_captured_deposit_satisfies_the_weight_identity() -> None:
    """231 rows, no exceptions.  This is the differential WP3.4 re-runs."""
    deposits = _deposits()
    assert len(deposits) == 231
    for ev in deposits:
        assert ev["weight_added_wei"] == (
            ev["credited_delta_wei"] * ev["early_bps"] // 10_000
        )


def test_the_early_multiplier_decays_monotonically_through_grace() -> None:
    """``earlyBps`` falls linearly from 20 000 to 10 000 across the grace
    period.  Every captured deposit is inside grace, so no row may sit at or
    below the flat 10 000 floor -- a fixture that did would be post-grace, and
    post-grace is exactly the state nothing is captured in yet."""
    deposits = sorted(
        _deposits(), key=lambda e: (e["block_number"], e["log_index"])
    )
    bps = [e["early_bps"] for e in deposits]
    assert bps == sorted(bps, reverse=True)
    assert max(bps) <= 20_000 and min(bps) > 10_000
    assert bps[0] == 19_975


def test_the_fan_out_cluster_is_in_the_data() -> None:
    """The cluster heuristic's real positive: 9 wallets, exactly 60 ETH each,
    inside a ~32-block window (25 770 115-25 770 143)."""
    sixty = [e for e in _deposits() if e["amount_wei"] == 60 * 10**18]
    assert len(sixty) == 9
    blocks = sorted(e["block_number"] for e in sixty)
    assert blocks[0] == 25_770_115 and blocks[-1] == 25_770_143
    assert blocks[-1] - blocks[0] <= 32
    assert len({e["contributor"].lower() for e in sixty}) == 9


def test_no_capture_carries_a_credited_delta_of_zero() -> None:
    """The cap case has no real instance: the largest single send is 461.1 ETH
    against a 1000 ETH cap.  WP3.5's fixture is therefore SYNTHETIC by
    necessity, and this assertion is what keeps that documented rather than
    forgotten."""
    deposits = _deposits()
    assert all(e["credited_delta_wei"] > 0 for e in deposits)
    assert max(e["amount_wei"] for e in deposits) == 4611 * 10**17  # 461.1 ETH
    assert max(e["amount_wei"] for e in deposits) < 1000 * 10**18


def test_every_captured_log_carries_a_block_timestamp() -> None:
    """This **refutes** hazard H14 and plan amendment A4 as written.

    Both say Tenderly's ``eth_getLogs`` returns no ``blockTimestamp`` and that
    Blockscout's log items carry none either.  The committed payloads say
    otherwise: all 377 RPC rows have ``blockTimestamp`` and all 376 Blockscout
    items have ``block_timestamp``.  WP2.8's ``eth_getBlockByNumber`` batch is
    therefore a *fallback* for endpoints that omit the field, not the sole
    provenance -- and a client that ignores the field it was handed is doing a
    round trip for nothing.  The ``--:--`` rule for a missing stamp still
    stands; it is just rarer than the plan assumed.
    """
    logs = _logs()
    assert all("blockTimestamp" in l for l in logs)
    launch = [l for l in logs if l["topics"][0] == A.TOPIC_LAUNCHED][0]
    assert int(launch["blockTimestamp"], 16) == A.LAUNCH_TIME
    items = [i for p in range(8) for i in capture(f"bs_page_{p}.json")["items"]]
    assert all("block_timestamp" in i for i in items)


def test_the_blockscout_pages_reconcile_with_the_rpc_sweep() -> None:
    """376 vs 377: the one extra tenderly log landed between the two pulls.
    Pinned as an exact relationship so a re-capture that silently loses a page
    fails here."""
    bs = [i for p in range(8) for i in capture(f"bs_page_{p}.json")["items"]]
    assert len(bs) == 376
    rpc_keys = {
        (l["transactionHash"].lower(), int(l["logIndex"], 16)) for l in _logs()
    }
    bs_keys = {(i["transaction_hash"].lower(), i["index"]) for i in bs}
    assert bs_keys <= rpc_keys
    assert len(rpc_keys - bs_keys) == 1


# ---- the hour boundary ----------------------------------------------------


def _boundary_series(signature: str):
    hb = capture("hour_boundary_h1_h2.json")
    req_id = {v["signature"]: v["id"] for v in hb["views"]}[signature]
    words = {"lastActiveHour()": 2, "stats()": 3}.get(signature, 1)
    out = []
    for sample in hb["samples"]:
        raw = {r["id"]: r["result"] for r in sample["response"]}[req_id][2:]
        vals = tuple(int(raw[i * 64 : (i + 1) * 64], 16) for i in range(words))
        out.append((sample["captured_at"], vals if words > 1 else vals[0]))
    return out


def test_the_hour_boundary_capture_shows_the_illusion_in_its_real_form() -> None:
    """H2, witnessed: ``currentHourTotal()`` collapses 9987.26 -> 51.48 ETH
    across 2026-08-16 21:58:47 UTC while ``stats()`` keeps climbing.

    A sparkline fed from the state poll renders that as a 99.5% crash.  Series
    are fed from folded ``Deposited`` logs only, and this is the payload that
    makes WP5's mandated mutation go red.
    """
    totals = _boundary_series("currentHourTotal()")
    hours = dict(_boundary_series("currentHour()"))
    people = {ts: v[1] for ts, v in _boundary_series("stats()")}

    before = [v for ts, v in totals if hours[ts] == 1]
    after = [v for ts, v in totals if hours[ts] == 2]
    assert len(before) == 8 and len(after) == 8
    assert before[-1] == 9_987_263_970_125_228_654_763  # 9987.263970 ETH
    assert after[0] == 51_480_000_000_000_000_000  # 51.48 ETH
    assert after[0] / before[-1] < 0.006

    # Cumulative counters do NOT drop across the same boundary.
    ordered = [people[ts] for ts, _ in totals]
    assert ordered == sorted(ordered)
    assert ordered[0] == 494 and ordered[-1] == 541


def test_time_left_in_hour_is_never_zero_at_the_boundary() -> None:
    """H12: ``timeLeftInHour()`` returns ``hourDuration``, never 0.  A "0
    seconds left" render is unreachable and the countdown must not treat 3600 as
    a fresh hour's worth of slack when it is really the instant of rollover."""
    values = [v for _, v in _boundary_series("timeLeftInHour()")]
    assert 0 not in values
    assert max(values) == 3600
    assert values[8] == 3600  # the first post-boundary sample


def test_the_quiet_boundary_state_is_still_missing() -> None:
    """What ``hour_boundary_h1_h2.json`` does **not** contain.

    A deposit landed within 11 s of the crossing, so ``lastActiveHour()`` had
    already rolled to hour 2 in the first post-boundary sample.  The distinct
    ``lastActiveHour() < currentHour()`` shape -- a boundary with no deposit yet,
    which post-grace is also the at-risk state -- is WP1 capture **A** and has
    no real fixture.  This test is the record; delete it when the capture lands.
    """
    hours = dict(_boundary_series("currentHour()"))
    last = {ts: v[0] for ts, v in _boundary_series("lastActiveHour()")}
    assert all(last[ts] == hours[ts] for ts in hours), (
        "a quiet crossing IS in this capture now -- re-point the synthetic "
        "stale-lastActiveHour fixture at it and delete this test"
    )


# ---- the announce channel -------------------------------------------------


def test_the_announce_channel_never_posted_about_the_curator() -> None:
    """PRD §7 and §12: the launch was unannounced.

    Refined against the capture, which refutes the blunt form of this pin.  The
    announce EOA's transaction page **does** contain the curator address --
    because the channel *deposited* into it, the very first deposit of the game.
    What it never did is post: the one curator-touching item is a ``deposit``
    call to the contract, not a self-transaction carrying text.

    Surf is OUT OF SCOPE -- this is a fact pin, not a feature.
    """
    items = capture("ann_page_0.json")["items"]
    touching = [t for t in items if A.CURATOR.lower() in json.dumps(t).lower()]
    assert len(touching) == 1
    (tx,) = touching
    assert tx["method"] == "deposit"
    assert tx["to"]["hash"].lower() == A.CURATOR.lower()
    assert int(tx["value"]) == 5 * 10**16  # 0.05 ETH, the minimum
    # A post is a self-transaction; none of those mentions the curator.
    posts = [
        t
        for t in items
        if (t.get("to") or {}).get("hash", "").lower() == A.ANNOUNCE.lower()
    ]
    for post in posts:
        assert A.CURATOR.lower() not in json.dumps(post).lower()


# ---------------------------------------------------------------------------
# Capture A — the quiet hour crossing (2026-08-17 15:58:52 UTC)
# ---------------------------------------------------------------------------


def test_capture_a_really_holds_the_state_it_was_hunted_for():
    """The pin for the bundle every boundary test now leans on.

    Hunted at every crossing from 2026-08-16 21:58 UTC and missed each time:
    during grace the game never left an hour quiet for the seconds it takes to
    read one, so `currentHourTotal` was already nonzero by the first sample.
    Post-grace it took one attempt -- which is the mechanism the whole
    dashboard is about, showing up in its own capture log.
    """
    state = state_from_bundle(CAPTURE_A)

    # The three words that make it state A rather than an ordinary crossing.
    assert state.current_hour_total_wei == 0
    assert state.last_active_hour == state.current_hour - 1
    assert state.last_active_hour_total_wei == 11_322_186_485_534_950_891_932

    # ...and the rest of the round is a live, healthy game, so nothing here is
    # an artefact of a broken read.
    assert state.settled is False
    assert state.volume_wei > 0 and state.contributors > 0
    assert state.early_bps > 10_000          # still inside the grace decay


def test_the_boundary_pair_is_the_one_a_state_poll_would_render_as_a_crash():
    """11,322 ETH in the hour that just closed, 0 in the one that just opened.

    A sparkline fed from the live view draws that as the game dying at the top
    of every hour -- and the zero would be *persisted*, so the corruption
    outlives the boundary that produced it.
    """
    state = state_from_bundle(CAPTURE_A)
    closed = state.last_active_hour_total_wei / 10**18
    opened = state.current_hour_total_wei / 10**18

    assert closed > 10_000 and opened == 0.0
    # The drop a naive reader would report, in the units they would report it.
    assert (closed - opened) / closed > 0.999
