"""WP2.5 — ``sybilkit analyze | segments | export-clean-list``.

**Zero network.**  The offline tests drive a committed fixture through
``--dataset``; the one live-path test injects an ``httpx.MockTransport``.
``test_no_test_in_this_file_builds_a_client_without_a_transport`` is the
structural proof.

The exported JSON is what "OS the list" consumers parse, so its shape is
pinned here rather than described in a docstring: a ``schema_version``, a
provenance header taken **from the dataset** (never the wall clock — the same
archive must export byte-identically tomorrow), and every wei value as a
**decimal string**, because 786 ETH in wei is 7.86e20 and IEEE-754 doubles —
which is what `JSON.parse` gives a browser — stop being exact at 9.0e15.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from sybilkit import cli
from tests.sybilkit_fixtures import FIXTURES

LABELED = FIXTURES / "labeled_subset.json"
THIS_FILE = Path(__file__).resolve()

CONTRACT = "0x8ff23e0bd8b6f8f1cdb54b0dfc0c1f30d5ffcbd8"

#: The two live reads, supplied on the command line for the offline tests.
#: Spelled out rather than defaulted, for the same reason `CuratorPreset` has
#: no defaults for them: a run that did not read the chain must be *visibly* a
#: run that did not read the chain.
OFFLINE_RATE = ["--points-per-eth", "1000", "--min-deposit-wei", "50000000000000000"]


def _deposit_row(*, block: int, log_index: int, tag: str) -> dict:
    """One `Deposited` log row, wire-shaped, for the live-path tests."""
    from sybilkit.sources import logs

    word = lambda v: f"{v:064x}"  # noqa: E731
    return {
        "address": CONTRACT,
        "topics": [logs.DEPOSITED_TOPIC,
                   "0x" + "0" * 24 + "11" * 20,
                   hex(0)],
        "data": "0x" + "".join(word(v) for v in (10**17, 10**17, 10**17,
                                                 10**17, 1, 10**17, 10_000)),
        "blockNumber": hex(block),
        "logIndex": hex(log_index),
        "transactionHash": "0x" + (tag * 32)[:64],
    }


def run(*argv: str) -> int:
    return cli.main(list(argv))


def out_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# ===========================================================================
# analyze
# ===========================================================================


def test_analyze_prints_reasons_shaped_json(capsys) -> None:
    code = run("analyze", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    assert code == 0
    doc = out_json(capsys)
    assert doc["schema_version"] == cli.SCHEMA_VERSION
    assert doc["command"] == "analyze"
    assert doc["preset"] == "curator"
    assert doc["clusters"], "the fixture contains twelve detectable clusters"
    first = doc["clusters"][0]
    assert set(first) >= {
        "cluster_id", "members", "reasons", "confidence", "points",
        "points_share", "span_blocks", "size",
    }
    assert first["reasons"] and set(first["reasons"][0]) == {
        "family", "human_string", "strength"
    }
    assert isinstance(doc["flagged"], list)
    assert set(doc["totals"]) >= {
        "total_points", "flagged_points", "clean_points",
        "contributors", "flagged_contributors", "clusters",
    }
    assert doc["totals"]["flagged_points"] + doc["totals"]["clean_points"] == (
        doc["totals"]["total_points"]
    )


def test_the_output_carries_the_config_it_actually_ran(capsys) -> None:
    """Rulings R10/R13, visible in the artifact: whoever reads a cluster file
    six months from now can see which rate and which minimum produced it."""
    run("analyze", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    doc = out_json(capsys)
    assert doc["config"]["points_per_eth"] == 1000
    assert doc["config"]["protocol_min_amount_wei"] == "50000000000000000"
    assert doc["config"]["min_families"] == 2
    assert doc["config"]["min_size"] == 5


def test_out_writes_the_file_and_names_the_path(tmp_path, capsys) -> None:
    """A CLI cannot hand a file to the reader; it writes it and says where."""
    target = tmp_path / "clusters.json"
    code = run(
        "analyze", "--dataset", str(LABELED), "--preset", "curator",
        "--out", str(target), *OFFLINE_RATE,
    )
    assert code == 0
    assert target.is_file()
    printed = capsys.readouterr().out
    assert str(target) in printed
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["schema_version"] == cli.SCHEMA_VERSION
    assert doc["clusters"]


def test_the_provenance_header_comes_from_the_dataset_not_the_wall_clock(
    tmp_path,
) -> None:
    """Two exports of one archive are byte-identical.

    That is the whole reason the header is sourced from the data: an export
    stamped with ``datetime.now()`` diffs against itself every time anybody
    re-runs it, so the one artifact a reader wants to compare across days is
    the one artifact that cannot be compared at all.
    """
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    for target in (a, b):
        run("analyze", "--dataset", str(LABELED), "--preset", "curator",
            "--out", str(target), *OFFLINE_RATE)
    assert a.read_bytes() == b.read_bytes()

    doc = json.loads(a.read_text(encoding="utf-8"))
    assert doc["generated_at"] == "2026-08-17T19:44:40Z"  # the fixture's own sweep
    # The range the DATA covers, derived from the deposit rows themselves —
    # not `meta.latest_block` (25776962), which is the chain head at sweep
    # time and describes the sweep rather than the analysis.
    assert doc["block_range"] == {"from": 25770220, "to": 25776849}
    assert doc["source"] == str(LABELED)


def test_every_wei_value_is_a_decimal_string(capsys) -> None:
    """A JSON number is a double to most consumers, and 786 ETH in wei is
    7.86e20 — sixty-odd times past where a double stops being exact.  Points
    stay ``int`` (the widest is 36 924) so the common case reads naturally."""
    run("export-clean-list", "--dataset", str(LABELED), "--preset", "curator",
        *OFFLINE_RATE)
    doc = out_json(capsys)
    entry = doc["entries"][0]
    assert isinstance(entry["credit_wei"], str) and entry["credit_wei"].isdigit()
    assert isinstance(entry["weight_wei"], str) and entry["weight_wei"].isdigit()
    assert isinstance(entry["points"], int)
    assert int(entry["credit_wei"]) > 2**53  # really out of double range


def test_a_missing_contract_exits_non_zero_with_a_message(capsys) -> None:
    code = run("analyze", "--preset", "curator")
    assert code != 0
    err = capsys.readouterr().err
    assert "--contract" in err and "--dataset" in err


def test_an_unreadable_dataset_exits_non_zero_rather_than_analysing_nothing(
    tmp_path, capsys
) -> None:
    """An empty analysis is a conclusion, and it must never be reached by
    accident."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    code = run("analyze", "--dataset", str(broken), "--preset", "curator", *OFFLINE_RATE)
    assert code != 0
    assert "broken.json" in capsys.readouterr().err


def test_an_offline_run_without_the_two_live_reads_says_so(capsys) -> None:
    """Rulings R10/R13 have teeth in the CLI too: a ``--dataset`` run cannot
    read the chain, so it must be *told* the rate and the minimum.  Guessing a
    default would be the remembered constant the whole preset forbids."""
    code = run("analyze", "--dataset", str(LABELED), "--preset", "curator")
    assert code != 0
    err = capsys.readouterr().err
    assert "--points-per-eth" in err and "--min-deposit-wei" in err


# ===========================================================================
# segments
# ===========================================================================


def test_segments_prints_the_operators_and_the_bands(capsys) -> None:
    code = run("segments", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    assert code == 0
    doc = out_json(capsys)
    assert doc["command"] == "segments"
    assert doc["operators"], "the fixture's clusters are its operators"
    op = doc["operators"][0]
    assert set(op) >= {
        "cluster_id", "size", "credit_wei", "points", "points_share",
        "subsidy_x", "confidence", "label", "reasons",
    }
    assert isinstance(op["credit_wei"], str)
    keys = {b["key"] for b in doc["bands"]}
    # `linked_groups`, not `largest_operators`: review finding #12 / D4, the
    # aggregate band was renamed off the credit line's name (plan WP5.3).
    assert "linked_groups" in keys and "early_cohort" in keys
    assert any(k.startswith("hour_") for k in keys)
    assert any(k.startswith("multiplier_") for k in keys)


def test_no_segment_string_in_the_export_carries_an_accusatory_word(capsys) -> None:
    """The library is named "sybilkit" and says so freely; what it *emits* is
    pattern language, so a consumer can render it verbatim."""
    from sybilkit.curator import FORBIDDEN_LABEL_WORDS

    run("segments", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    doc = out_json(capsys)
    strings = [b["label"] for b in doc["bands"]] + [b["detail"] for b in doc["bands"]]
    strings += [o["label"] for o in doc["operators"]]
    strings += [r for o in doc["operators"] for r in o["reasons"]]
    for text in strings:
        for word in FORBIDDEN_LABEL_WORDS:
            assert word not in text.lower(), f"{word!r} in {text!r}"


# ===========================================================================
# export-clean-list
# ===========================================================================


def test_export_clean_list_writes_the_survivors_and_their_ranks(tmp_path) -> None:
    target = tmp_path / "clean_list.json"
    code = run(
        "export-clean-list", "--dataset", str(LABELED), "--preset", "curator",
        "--out", str(target), *OFFLINE_RATE,
    )
    assert code == 0
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["command"] == "export-clean-list"
    ranks = [e["clean_rank"] for e in doc["entries"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert len(doc["entries"]) == doc["totals"]["clean_contributors"]
    assert doc["totals"]["clean_points"] == sum(e["points"] for e in doc["entries"])
    # No flagged address survives into the export.
    flagged = set(doc["removed"])
    assert flagged and not (flagged & {e["address"] for e in doc["entries"]})


def test_the_clean_list_export_names_what_it_removed_not_just_what_is_left(
    capsys,
) -> None:
    """A cleaned list that only shows survivors cannot be checked by anybody.
    The removed set travels with it, so the reader can see the claim being
    made rather than only its consequence."""
    run("export-clean-list", "--dataset", str(LABELED), "--preset", "curator",
        *OFFLINE_RATE)
    doc = out_json(capsys)
    assert len(doc["removed"]) == doc["totals"]["flagged_contributors"]
    assert doc["totals"]["contributors_total"] == (
        doc["totals"]["clean_contributors"] + doc["totals"]["flagged_contributors"]
    )


# ===========================================================================
# The live path — httpx injected, chain values read rather than remembered
# ===========================================================================


def test_the_live_path_reads_the_rate_and_the_minimum_off_the_chain(capsys) -> None:
    """Rulings R10 and R13, end to end and demonstrably.

    The transport serves ``POINTS_PER_ETH() = 777`` and
    ``minDeposit() = 70000000000000000`` — deliberately **not** the values
    anybody remembers — and both appear in the artifact's ``config``.  A CLI
    that hardcoded 1000 and 0.05 would print 1000 and 0.05 here.
    """
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")
    min_sel = sources.selector("minDeposit()")
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        results = []
        for call in calls:
            method = call["method"]
            if method == "eth_call":
                data = call["params"][0]["data"]
                asked.append(data)
                if data == rate_sel:
                    value = 777
                elif data == min_sel:
                    value = 70_000_000_000_000_000
                else:  # pragma: no cover - the CLI reads exactly two views
                    raise AssertionError(f"unexpected view {data}")
                results.append({"jsonrpc": "2.0", "id": call["id"],
                                "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                results.append({"jsonrpc": "2.0", "id": call["id"], "result": hex(120)})
            elif method == "eth_getLogs":
                results.append({"jsonrpc": "2.0", "id": call["id"], "result": []})
            else:  # pragma: no cover
                raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json=results if isinstance(body, list) else results[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100", "--preset", "curator"],
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    doc = out_json(capsys)
    assert doc["config"]["points_per_eth"] == 777
    assert doc["config"]["protocol_min_amount_wei"] == "70000000000000000"
    assert sorted(set(asked)) == sorted({rate_sel, min_sel})
    assert doc["block_range"] == {"from": 100, "to": 120}
    assert doc["clusters"] == []          # the sweep really was empty
    assert doc["totals"]["contributors"] == 0


def test_the_header_records_which_tiers_actually_ran(capsys) -> None:
    """**Review I2(a).**  The repo's no-silent-caps rule, applied to coverage.

    A capped or skipped tier changes what the detector could possibly find, so
    the artifact has to say so — otherwise two exports of the same contract
    differ for a reason no reader can see.  On a ``--dataset`` run the header
    reports what the bundle carried; the labeled subset carries all three
    tiers.
    """
    run("analyze", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    doc = out_json(capsys)
    cov = doc["coverage"]
    # A `--dataset` run asks for nothing — it reads a file — so `requested` is
    # null and only `read` is a claim about anything.
    assert cov["tiers_requested"] is None
    assert cov["tiers_read"] == "abc"
    assert cov["tx_fingerprints"]["read"] == 220
    assert cov["funding"]["read"] == 220
    assert cov["tx_fingerprints"]["source"] == "dataset"


def test_the_header_says_so_when_a_tier_is_absent(tmp_path, capsys) -> None:
    """The negative has to be representable too: a bundle with no fingerprints
    reports ``tx_fingerprints: null``, which is "this ran without tier B" and
    not "tier B found nothing"."""
    bundle = tmp_path / "logs_only.json"
    bundle.write_text(json.dumps({
        "meta": {"sweep_utc": "2026-08-17 19:44:40"},
        "deposits": [{
            "contributor": "0x" + "11" * 20, "hour": 0,
            "amount_wei": 10**17, "credited_delta_wei": 10**17,
            "weight_added_wei": 10**17, "new_weight_wei": 10**17,
            "tx_count": 1, "block": 100, "log_index": 1,
            "tx_hash": "0x" + "ab" * 32,
        }],
        "first_deposits": [{"contributor": "0x" + "11" * 20, "index": 1}],
    }), encoding="utf-8")
    code = run("analyze", "--dataset", str(bundle), "--preset", "curator", *OFFLINE_RATE)
    assert code == 0
    cov = out_json(capsys)["coverage"]
    assert cov["tiers_requested"] is None
    assert cov["tiers_read"] == "a"
    assert cov["tx_fingerprints"] is None
    assert cov["funding"] is None


def test_abc_without_a_funding_budget_exits_rather_than_silently_skipping(
    capsys,
) -> None:
    """**Review I2(b).**  ``--tiers abc`` with the budget at its 0 default used
    to run a and b, skip c, and say so nowhere — the run looked like a full
    A+B+C analysis and was not one.  A cap that silently does nothing is worse
    than no cap."""
    code = run("analyze", "--contract", CONTRACT, "--from-block", "0",
               "--preset", "curator", "--tiers", "abc")
    assert code != 0
    err = capsys.readouterr().err
    assert "--funding-budget" in err and "--tiers ab" in err


def test_the_tx_cap_cuts_chronologically_at_a_block_boundary_and_says_so() -> None:
    """**Review I2(c).**  ``sorted({...})[:n]`` is a *lexicographic* sample of
    transaction hashes — uncorrelated with anything — and it cuts mid-block,
    which splits the very groups the gas family measures uniformity over
    (``gas_edges`` needs ≥ 90 % of a component before it will speak).

    So the cap walks chain order and stops at the last block that fits whole.
    """
    from sybilkit.cli import _tx_hashes_in_chain_order
    from sybilkit.model import Deposit

    def dep(block: int, log_index: int, tag: str) -> Deposit:
        return Deposit(
            contributor="0x" + "11" * 20, hour=0, amount_wei=1,
            credited_delta_wei=1, weight_added_wei=1, new_weight_wei=1,
            tx_count=1, block_number=block, log_index=log_index,
            tx_hash="0x" + tag * 32,
        )

    # Block 10 holds three transactions, block 11 holds two.  Shuffled on the
    # way in, and the hash of the LAST one sorts first — so a lexicographic
    # slice would lead with a block-11 transaction.
    deposits = [
        dep(11, 1, "0a"), dep(10, 2, "f2"), dep(10, 1, "f1"),
        dep(11, 2, "0b"), dep(10, 3, "f3"),
    ]
    hashes, cut = _tx_hashes_in_chain_order(deposits, cap=4)
    assert hashes == ["0x" + t * 32 for t in ("f1", "f2", "f3")]
    assert cut == 11, "the cut must name the first block it did NOT cover"

    whole, cut_none = _tx_hashes_in_chain_order(deposits, cap=99)
    assert len(whole) == 5 and cut_none is None
    # A cap smaller than the first block still takes that block whole rather
    # than handing a uniformity detector a fragment of one.
    tiny, tiny_cut = _tx_hashes_in_chain_order(deposits, cap=1)
    assert tiny == ["0x" + t * 32 for t in ("f1", "f2", "f3")]
    assert tiny_cut == 11


def test_the_live_header_records_the_tx_cap_it_applied(capsys) -> None:
    """And the cut reaches the artifact, so a consumer sees the analysis was
    scored on part of the history."""
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")
    min_sel = sources.selector("minDeposit()")
    rows = [
        _deposit_row(block=100, log_index=i, tag=f"{i:02x}") for i in range(3)
    ] + [_deposit_row(block=101, log_index=9, tag="99")]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            method, cid = call["method"], call["id"]
            if method == "eth_call":
                data = call["params"][0]["data"]
                value = 1000 if data == rate_sel else 50_000_000_000_000_000
                assert data in (rate_sel, min_sel)
                out.append({"jsonrpc": "2.0", "id": cid,
                            "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": cid, "result": hex(200)})
            elif method == "eth_getLogs":
                out.append({"jsonrpc": "2.0", "id": cid, "result": rows})
            elif method == "eth_getTransactionByHash":
                h = call["params"][0]
                out.append({"jsonrpc": "2.0", "id": cid, "result": {
                    "hash": h, "nonce": "0x0", "gas": hex(91_600), "type": "0x2",
                    "maxPriorityFeePerGas": hex(10**8), "maxFeePerGas": hex(10**9),
                }})
            else:  # pragma: no cover
                raise AssertionError(method)
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100",
         "--preset", "curator", "--tiers", "ab", "--max-txs", "3"],
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    cov = out_json(capsys)["coverage"]
    assert cov["tiers_requested"] == "ab"
    assert cov["tiers_read"] == "ab"
    assert cov["tx_fingerprints"]["available"] == 4
    assert cov["tx_fingerprints"]["requested"] == 3
    assert cov["tx_fingerprints"]["read"] == 3
    assert cov["tx_fingerprints"]["unread"] == 0
    assert cov["tx_fingerprints"]["cap"] == 3
    assert cov["tx_fingerprints"]["cut_at_block"] == 101
    assert cov["funding"] is None


def test_a_tier_that_answered_with_nothing_is_not_reported_unavailable(
    capsys,
) -> None:
    """**Fix round 2, the Important — reproduced shape (a).**

    The node answers HTTP 200 with ``"result": null`` bodies: the documented
    ask-again case.  Tier B was reached, read nothing, and has two hashes to
    retry — and the header must say exactly that.  Round 1 stamped
    ``source: "unavailable"``, because ``TxSweep.__len__`` made the successful
    empty sweep falsy.
    """
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")
    rows = [_deposit_row(block=100, log_index=i, tag=f"{i:02x}") for i in range(2)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            method, cid = call["method"], call["id"]
            if method == "eth_call":
                value = 1000 if call["params"][0]["data"] == rate_sel else 5 * 10**16
                out.append({"jsonrpc": "2.0", "id": cid, "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": cid, "result": hex(200)})
            elif method == "eth_getLogs":
                out.append({"jsonrpc": "2.0", "id": cid, "result": rows})
            elif method == "eth_getTransactionByHash":
                out.append({"jsonrpc": "2.0", "id": cid, "result": None})
            else:  # pragma: no cover
                raise AssertionError(method)
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100", "--tiers", "ab"],
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    cov = out_json(capsys)["coverage"]
    fp = cov["tx_fingerprints"]
    assert fp["source"] is None, "a reachable tier was reported unavailable"
    assert fp["read"] == 0
    assert fp["unread"] == 2
    assert fp["requested"] == 2
    # Asked for b, did not get b — and the two fields say so without lying
    # about either half.
    assert cov["tiers_requested"] == "ab"
    assert cov["tiers_read"] == "a"


def test_a_tier_that_was_never_asked_a_question_is_not_an_outage(capsys) -> None:
    """**Fix round 2, the Important — reproduced shape (b).**

    An empty log sweep under the default ``--tiers ab``: there are no
    transaction hashes, so zero tier-B requests are issued.  A tier nobody
    asked anything is not unavailable — it is complete and empty.
    """
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            method, cid = call["method"], call["id"]
            if method == "eth_call":
                value = 1000 if call["params"][0]["data"] == rate_sel else 5 * 10**16
                out.append({"jsonrpc": "2.0", "id": cid, "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": cid, "result": hex(200)})
            elif method == "eth_getLogs":
                out.append({"jsonrpc": "2.0", "id": cid, "result": []})
            else:  # pragma: no cover — no fingerprint call may be issued
                raise AssertionError(f"tier B asked something: {method}")
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100"],
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    fp = out_json(capsys)["coverage"]["tx_fingerprints"]
    assert fp["requested"] == 0
    assert fp["read"] == 0
    assert fp["unread"] == 0
    assert fp["source"] is None, "a tier with nothing to ask was called unavailable"


def test_a_tier_that_really_failed_is_still_reported_unavailable(capsys) -> None:
    """The negative of the two above: ``source: "unavailable"`` has to keep
    meaning something, or fixing the false positive would just delete the
    signal."""
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")
    rows = [_deposit_row(block=100, log_index=0, tag="aa")]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if isinstance(body, list):        # the fingerprint batch: dead
            return httpx.Response(500, text="internal error")
        method, cid = body["method"], body["id"]
        if method == "eth_call":
            value = 1000 if body["params"][0]["data"] == rate_sel else 5 * 10**16
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": cid,
                                             "result": "0x" + f"{value:064x}"})
        if method == "eth_blockNumber":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": cid,
                                             "result": hex(200)})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": cid, "result": rows})

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100", "--tiers", "ab"],
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    cov = out_json(capsys)["coverage"]
    assert cov["tx_fingerprints"]["source"] == "unavailable"
    assert cov["tx_fingerprints"]["unread"] == 1
    assert cov["tiers_requested"] == "ab" and cov["tiers_read"] == "a"


def test_the_preset_name_in_the_output_is_the_one_that_was_asked_for(capsys) -> None:
    """It was hardcoded ``"curator"`` in all three builders, so a second preset
    would have shipped documents claiming to be the first one."""
    run("segments", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    doc = out_json(capsys)
    assert doc["preset"] == "curator"
    assert cli.PRESETS == ("curator",)
    # And the value is threaded, not typed: the builders read it off the header.
    import inspect

    src = inspect.getsource(cli)
    assert src.count('"preset": "curator"') == 0


def test_a_live_run_that_cannot_read_the_chain_exits_non_zero(capsys) -> None:
    """Never a remembered value dressed up as a reading: if
    ``POINTS_PER_ETH`` could not be read, the run stops."""
    httpx = pytest.importorskip("httpx")

    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "0", "--preset", "curator"],
        transport=httpx.MockTransport(dead),
    )
    assert code != 0
    assert "POINTS_PER_ETH" in capsys.readouterr().err


def test_help_works_on_the_pure_install(monkeypatch, capsys) -> None:
    """``sybilkit --help`` must survive with zero third-party packages, so the
    transport is imported lazily and only by a live fetch."""
    monkeypatch.setitem(sys.modules, "httpx", None)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "analyze" in capsys.readouterr().out


def test_an_offline_run_works_on_the_pure_install(monkeypatch, capsys) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)
    code = run("analyze", "--dataset", str(LABELED), "--preset", "curator", *OFFLINE_RATE)
    assert code == 0
    assert out_json(capsys)["clusters"]


def test_a_live_fetch_without_httpx_names_the_extra(monkeypatch, capsys) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)
    code = run("analyze", "--contract", CONTRACT, "--from-block", "0", "--preset", "curator")
    assert code != 0
    assert 'pip install "sybilkit[sources]"' in capsys.readouterr().err


# ===========================================================================
# Below the cap — the 2026-08-18 review's B1..B5 ledger
# ===========================================================================


def test_a_chain_that_answers_zero_points_per_eth_is_a_named_error_not_a_traceback(
    capsys,
) -> None:
    """**B1.**  ``hex_to_int`` answers ``None`` for a read it could not make and
    ``0`` for a chain that really said zero, so a contract answering
    ``POINTS_PER_ETH() = 0`` walks straight past the ``is None`` outage check
    and into ``CuratorPreset``, which raises ``ValueError`` — a traceback out
    of a ``main`` whose own docstring says it never raises.

    Zero is a *reading*, not an outage, and it is an unusable rate: every
    deposit scores zero points.  So the run stops and names the view that
    answered it, rather than crashing or analysing at a rate of nothing.
    """
    httpx = pytest.importorskip("httpx")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            assert call["method"] == "eth_call", "it must stop before it sweeps"
            out.append({"jsonrpc": "2.0", "id": call["id"], "result": "0x" + "0" * 64})
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100"],
        transport=httpx.MockTransport(handler),
    )
    assert code != 0
    err = capsys.readouterr().err
    assert "POINTS_PER_ETH" in err
    assert "--points-per-eth" in err, "the override is the way out; name it"


def test_a_chain_that_answers_zero_min_deposit_stops_but_a_measured_zero_does_not(
    capsys,
) -> None:
    """**B1, the other view.**  A ``minDeposit()`` of zero disables the R13
    exemption, which is the exact failure the ``is None`` branch already
    refuses in prose: *without it the whole minimum-paying crowd is linked by
    an identicalness that identifies nobody*.  A zero that came **off the
    chain** stops the run; a zero the caller passed is that caller's own
    measurement and runs.
    """
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            method, cid = call["method"], call["id"]
            if method == "eth_call":
                value = 1000 if call["params"][0]["data"] == rate_sel else 0
                out.append({"jsonrpc": "2.0", "id": cid,
                            "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": cid, "result": hex(120)})
            elif method == "eth_getLogs":
                out.append({"jsonrpc": "2.0", "id": cid, "result": []})
            else:  # pragma: no cover
                raise AssertionError(method)
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    argv = ["analyze", "--contract", CONTRACT, "--from-block", "100"]
    code = cli.main(argv, transport=httpx.MockTransport(handler))
    assert code != 0
    err = capsys.readouterr().err
    assert "minDeposit" in err and "--min-deposit-wei" in err

    measured = cli.main(
        argv + ["--min-deposit-wei", "0"], transport=httpx.MockTransport(handler)
    )
    assert measured == 0, "a zero the caller measured is not the CLI's to refuse"
    assert out_json(capsys)["config"]["protocol_min_amount_wei"] == "0"


def test_an_unexpected_value_error_exits_non_zero_with_a_message(capsys) -> None:
    """**B1, the handler half.**  ``--points-per-eth 0`` is not None, so it
    clears every guard in ``_run`` and raises out of ``CuratorPreset``.  The
    library validates its own inputs properly; what was missing was a CLI that
    turns that validation into a message and an exit status instead of a
    stack trace.
    """
    code = run("analyze", "--dataset", str(LABELED),
               "--points-per-eth", "0", "--min-deposit-wei", "0")
    assert code == 3
    assert "points_per_eth" in capsys.readouterr().err


def test_a_non_utc_offset_is_converted_rather_than_suffixed_with_z(
    tmp_path, capsys
) -> None:
    """**B2.**  ``_iso`` handled ``Z`` and ``+00:00`` and then appended a ``Z``
    to whatever was left, so a sweep stamped ``2026-08-17T21:44:40+02:00``
    reached the provenance header as ``2026-08-17T21:44:40+02:00Z`` — not a
    timestamp in any format, and two hours wrong to anything lenient enough to
    parse it.  An offset is converted; only a *naive* stamp gets a bare ``Z``.
    """
    assert cli._iso("2026-08-17T21:44:40+02:00") == "2026-08-17T19:44:40Z"
    assert cli._iso("2026-08-17T11:44:40-08:00") == "2026-08-17T19:44:40Z"
    # The three shapes that were already right stay byte-identical: this is a
    # provenance field whose whole job is exporting the same archive to the
    # same bytes tomorrow.
    assert cli._iso("2026-08-17 19:44:40") == "2026-08-17T19:44:40Z"
    assert cli._iso("2026-08-17T19:44:40+00:00") == "2026-08-17T19:44:40Z"
    assert cli._iso("2026-08-17T19:44:40Z") == "2026-08-17T19:44:40Z"
    assert cli._iso("") is None and cli._iso(None) is None
    # And a stamp we cannot read keeps its own offset rather than being handed
    # a `Z` it never earned.
    assert not cli._iso("whenever+02:00").endswith("Z")

    bundle = tmp_path / "berlin.json"
    bundle.write_text(json.dumps({
        "meta": {"sweep_utc": "2026-08-17T21:44:40+02:00"},
        "deposits": [{
            "contributor": "0x" + "11" * 20, "hour": 0,
            "amount_wei": 10**17, "credited_delta_wei": 10**17,
            "weight_added_wei": 10**17, "new_weight_wei": 10**17,
            "tx_count": 1, "block": 100, "log_index": 1,
            "tx_hash": "0x" + "ab" * 32,
        }],
        "first_deposits": [{"contributor": "0x" + "11" * 20, "index": 1}],
    }), encoding="utf-8")
    assert run("analyze", "--dataset", str(bundle), *OFFLINE_RATE) == 0
    assert out_json(capsys)["generated_at"] == "2026-08-17T19:44:40Z"


def test_a_negative_funding_budget_is_rejected_at_the_command_line(capsys) -> None:
    """**B3, the CLI half.**  ``fetch_funding`` now clamps a negative budget to
    zero — it used to slice ``wanted[:-5]``, which looks up *all but* the last
    five addresses, the exact opposite of a cap.  The clamp keeps the library
    safe for every caller; it also turns a typo into a pass that quietly reads
    nothing.  At the command line the typo is nameable, so it is named.
    """
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["analyze", "--dataset", str(LABELED), *OFFLINE_RATE,
                  "--funding-budget", "-5"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--funding-budget" in err and "-5" in err

    # The values that mean something still parse, zero included: zero is
    # "tier C off", which `--tiers abc` already refuses separately.
    parser = cli.build_parser()
    assert parser.parse_args(["analyze", "--funding-budget", "0"]).funding_budget == 0
    assert parser.parse_args(["analyze", "--funding-budget", "40"]).funding_budget == 40


def test_a_zero_tx_cap_fetches_nothing_and_says_where_it_stopped(capsys) -> None:
    """**B4.**  The block-boundary rule is ``if out and len(out) + len(group) >
    cap``, and the ``out and`` was there so a cap smaller than the first block
    still takes that block **whole** rather than handing a uniformity detector
    a fragment.  With ``cap=0`` the same clause let the first block through: a
    cap of nothing fetched a whole block, and the coverage header then reported
    a cap of 0 next to a non-zero ``read``.

    Zero means zero.  It still names the block it stopped at, because that is
    the cursor a later pass resumes from.
    """
    from sybilkit.cli import _tx_hashes_in_chain_order
    from sybilkit.model import Deposit

    def dep(block: int, log_index: int, tag: str) -> Deposit:
        return Deposit(
            contributor="0x" + "11" * 20, hour=0, amount_wei=1,
            credited_delta_wei=1, weight_added_wei=1, new_weight_wei=1,
            tx_count=1, block_number=block, log_index=log_index,
            tx_hash="0x" + tag * 32,
        )

    deposits = [dep(10, 1, "f1"), dep(10, 2, "f2"), dep(11, 1, "0a")]
    assert _tx_hashes_in_chain_order(deposits, cap=0) == ([], 10)
    # A negative cap is the same statement, never an inverted one.
    assert _tx_hashes_in_chain_order(deposits, cap=-3) == ([], 10)
    # Nothing to cut, so nowhere to resume from: `None`, not block zero.
    assert _tx_hashes_in_chain_order([], cap=0) == ([], None)

    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")
    rows = [_deposit_row(block=100, log_index=i, tag=f"{i:02x}") for i in range(2)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            method, cid = call["method"], call["id"]
            if method == "eth_call":
                value = 1000 if call["params"][0]["data"] == rate_sel else 5 * 10**16
                out.append({"jsonrpc": "2.0", "id": cid,
                            "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": cid, "result": hex(200)})
            elif method == "eth_getLogs":
                out.append({"jsonrpc": "2.0", "id": cid, "result": rows})
            else:  # pragma: no cover — a cap of zero fetches no fingerprint
                raise AssertionError(f"--max-txs 0 asked for a fingerprint: {method}")
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "100",
         "--tiers", "ab", "--max-txs", "0"],
        transport=httpx.MockTransport(handler),
    )
    assert code == 0
    fp = out_json(capsys)["coverage"]["tx_fingerprints"]
    assert fp["cap"] == 0
    assert fp["requested"] == 0 and fp["read"] == 0 and fp["unread"] == 0
    assert fp["available"] == 2, "the history is still measured; it was not read"
    assert fp["cut_at_block"] == 100, "the cap stopped before block 100"


def test_a_from_block_past_the_head_is_a_named_error_not_an_inverted_range(
    capsys,
) -> None:
    """**B5.**  ``fetch_deposits`` answers a from-block past the head with an
    empty ``DepositSweep(from_block, head, …)`` — correct for a library whose
    caller may be polling a range that has not been mined yet.  The CLI then
    stamped it straight into the provenance header, so the artifact stated
    ``block_range: {"from": 500, "to": 120}`` — a range running backwards,
    presented as a measurement, and an analysis of nothing reported as an
    analysis.  Exit 0, no warning.

    A from-block past the head is a typo the user can fix, so it is named:
    both numbers, before anything is swept.
    """
    httpx = pytest.importorskip("httpx")
    from sybilkit import sources

    rate_sel = sources.selector("POINTS_PER_ETH()")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls = body if isinstance(body, list) else [body]
        out = []
        for call in calls:
            method, cid = call["method"], call["id"]
            if method == "eth_call":
                value = 1000 if call["params"][0]["data"] == rate_sel else 5 * 10**16
                out.append({"jsonrpc": "2.0", "id": cid,
                            "result": "0x" + f"{value:064x}"})
            elif method == "eth_blockNumber":
                out.append({"jsonrpc": "2.0", "id": cid, "result": hex(120)})
            else:  # pragma: no cover — there is nothing to sweep
                raise AssertionError(f"swept past the head: {method}")
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    code = cli.main(
        ["analyze", "--contract", CONTRACT, "--from-block", "500"],
        transport=httpx.MockTransport(handler),
    )
    assert code != 0
    err = capsys.readouterr().err
    assert "500" in err and "120" in err, "name both numbers; one of them is a typo"


def test_a_malformed_labeled_bundle_is_a_message_not_a_key_error_traceback(
    tmp_path, capsys
) -> None:
    """The ``KeyError`` half of the same handler: ``dataset_from_labeled``
    reads ``entry["first_index"]`` directly, so a hand-written labeled bundle
    missing one field is a traceback rather than "your file is missing this"."""
    bundle = tmp_path / "labeled_missing_index.json"
    bundle.write_text(
        json.dumps({"members": [{"address": "0x" + "11" * 20}]}), encoding="utf-8"
    )
    code = run("analyze", "--dataset", str(bundle), *OFFLINE_RATE)
    assert code == 3
    assert "first_index" in capsys.readouterr().err


# ===========================================================================
# Structural
# ===========================================================================


def test_no_test_in_this_file_builds_a_client_without_a_transport() -> None:
    tree = ast.parse(THIS_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name in ("AsyncClient", "Client"):
            assert any(kw.arg == "transport" for kw in node.keywords), ast.dump(node)


def test_the_cli_imports_no_transport_at_module_scope() -> None:
    """The entry point is what a pure install runs first."""
    import sybilkit.cli as cli_mod

    tree = ast.parse(Path(cli_mod.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module.split(".")[0]]
        assert "httpx" not in names


def test_the_declared_entry_point_resolves_to_this_main() -> None:
    """An agreement test between the packaging and the code.

    ``pyproject.toml`` names ``sybilkit = "sybilkit.cli:main"``.  A rename here
    would leave a wheel whose console script imports something that no longer
    exists — and nothing in a normal test run would notice, because a test run
    calls ``cli.main`` directly and never goes through the entry point.
    """
    import tomllib

    root = THIS_FILE.parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    target = data["project"]["scripts"]["sybilkit"]
    assert target == "sybilkit.cli:main"

    module_path, _, attr = target.partition(":")
    import importlib

    resolved = getattr(importlib.import_module(module_path), attr)
    assert resolved is cli.main
    assert callable(resolved)


def test_the_sources_extra_declares_the_only_third_party_package() -> None:
    """``dependencies`` stays empty and ``[sources]`` carries exactly httpx.

    Pinned because the whole "the core imports with zero third-party packages"
    promise is one careless ``dependencies = [...]`` away from being false, and
    a wheel that quietly grew a dependency looks identical until somebody
    installs it somewhere small.
    """
    import tomllib

    root = THIS_FILE.parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []
    extras = data["project"]["optional-dependencies"]
    assert list(extras) == ["sources"]
    assert [d.split(">=")[0] for d in extras["sources"]] == ["httpx"]
