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
    assert "largest_operators" in keys and "early_cohort" in keys
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
