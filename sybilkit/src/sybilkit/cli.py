"""``sybilkit analyze | segments | export-clean-list`` — keyless, JSON out.

This is the "OS the list" tool: it sweeps a contract's deposit history with no
key of any kind, runs the same detector the library exposes, and writes JSON
somebody else can parse.  Three rules shape the output format and each one is a
mistake that would otherwise be discovered by a consumer rather than by us.

**Wei are decimal strings.**  A JSON number is an IEEE-754 double to almost
every consumer — ``JSON.parse`` certainly — and doubles stop being exact at
9.0e15.  786 ETH is 7.86e20 wei.  Points stay ``int`` (the widest observed is
36 924) so the common case still reads naturally.

**The provenance header comes from the dataset, never the wall clock.**
``generated_at`` is the sweep's own timestamp and ``block_range`` is the range
the data covers, so exporting the same archive twice produces byte-identical
files.  An export stamped ``datetime.now()`` diffs against itself every time
anybody re-runs it, which destroys the one artifact a reader wants to compare
across days.

**The chain's numbers are read, not remembered.**  ``POINTS_PER_ETH`` and
``minDeposit`` come off the contract with an ``eth_call`` on the live path and
must be given explicitly on the ``--dataset`` path (rulings R10 and R13); there
is no default for either, anywhere, and a run that could not read them stops
rather than substituting a plausible number.

``httpx`` is imported lazily, through ``sybilkit.sources``, so ``--help`` and
every ``--dataset`` run work on the pure ``pip install sybilkit``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from .bench import dataset_from_labeled
from .cluster import detect
from .curator import CuratorPreset, clean_list, segments
from .model import Dataset

#: Bumped when a **consumer-visible** shape changes.  It is in every document
#: this CLI writes so that a parser can refuse a file it does not understand
#: instead of quietly reading a renamed field as absent.
SCHEMA_VERSION = 1

PRESETS = ("curator",)


# ---------------------------------------------------------------------------
# Dataset loading — two shapes, both offline
# ---------------------------------------------------------------------------


class CliError(Exception):
    """Something the user can fix; printed to stderr, never a traceback."""


def _load_bundle(path: Path) -> tuple[Dataset, dict]:
    """A committed JSON bundle as ``(Dataset, meta)``.

    Two shapes are accepted because two shapes exist in the wild and neither is
    worth converting by hand: the **labeled-subset** shape
    (``{"members": [...], "controls": [...]}``), which is what the benchmark
    fixture is, and a plain **event bundle**
    (``{"deposits": [...], "first_deposits": [...], "txs": [...],
    "funding": [...]}``), which is what a sweep dumps.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CliError(f"could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CliError(f"{path}: expected a JSON object at the top level")
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    if "members" in raw or "controls" in raw:
        return dataset_from_labeled(raw), meta
    if "deposits" not in raw:
        raise CliError(
            f"{path}: no 'deposits' and no 'members' — this is neither an event "
            "bundle nor a labeled subset"
        )
    return (
        Dataset.from_events(
            raw.get("deposits") or (),
            raw.get("first_deposits") or (),
            txs=raw.get("txs"),
            funding=raw.get("funding"),
        ),
        meta,
    )


#: A trailing ``[+-]HH:MM`` / ``[+-]HHMM`` UTC offset.  Anchored, and four
#: digits wide on purpose: ``2026-08-17`` must not read as an offset of
#: ``-17``, because the conversion below would then run a date-only stamp
#: through the *local* zone.
_UTC_OFFSET = re.compile(r"[+-]\d{2}:?\d{2}$")


def _iso(text: Any) -> str | None:
    """A sweep timestamp normalised to ``YYYY-MM-DDTHH:MM:SSZ``, or ``None``.

    ``None`` rather than a guess: a bundle that carries no timestamp genuinely
    has none, and inventing one is exactly the fabricated fact this whole
    distribution refuses to produce.

    An offset that is not UTC is **converted**, never suffixed.  Handling
    ``Z`` and ``+00:00`` and then appending a ``Z`` to whatever was left turned
    a sweep stamped ``2026-08-17T21:44:40+02:00`` into
    ``2026-08-17T21:44:40+02:00Z`` — not a timestamp in any format, and two
    hours wrong to any reader lenient enough to parse it.  Only a *naive*
    stamp gets a bare ``Z``.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    body = text.strip().replace(" ", "T")
    if body.endswith("Z"):
        return body
    if body.endswith("+00:00"):
        # Already UTC: rewritten rather than re-parsed, so this path stays
        # byte-preserving (fractional seconds and all) for the spelling the
        # sweeps actually emit.
        return body[: -len("+00:00")] + "Z"
    if _UTC_OFFSET.search(body):
        import datetime  # noqa: PLC0415 — only this formatting needs it

        try:
            moment = datetime.datetime.fromisoformat(body)
        except ValueError:
            # Whatever this is, it is not a stamp we can read.  Hand it back
            # untouched: a `Z` it never earned is a fabricated fact, and it
            # still carries its own offset, so nothing is lost.
            return body
        if moment.tzinfo is None:
            return body  # the offset was a coincidence; never guess a zone
        return moment.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return body + "Z"


def _provenance(ds: Dataset, meta: dict, source: str) -> dict:
    """The header every document carries.  Everything in it is measured."""
    generated_at = _iso(meta.get("sweep_utc") or meta.get("generated_at"))
    if generated_at is None:
        stamps = [d.ts for d in ds.deposits if d.ts is not None]
        if stamps:
            import datetime  # noqa: PLC0415 — only this formatting needs it

            generated_at = (
                datetime.datetime.fromtimestamp(max(stamps), datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
    blocks = [d.block_number for d in ds.deposits]
    block_range = (
        {"from": min(blocks), "to": max(blocks)} if blocks else {"from": None, "to": None}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "block_range": block_range,
        "source": source,
        # The repo's no-silent-caps rule: a capped or skipped tier changes what
        # the detector could possibly find, so the artifact has to say so — a
        # consumer comparing two exports must be able to see that one of them
        # never ran the funding pass.
        #
        # TWO FIELDS, because one word cannot carry both facts and a single
        # `tiers` meant "asked for" on the live path and "carries" on the
        # `--dataset` path under a comment claiming it meant "read".
        #
        #   tiers_requested — what this invocation asked for.  `None` on a
        #                     `--dataset` run, which asks for nothing (it reads
        #                     a file, and `--tiers` is ignored there).
        #   tiers_read      — what the DATASET THE DETECTOR SAW actually holds.
        #                     Derived the same way on both paths, from the
        #                     built `Dataset`, so the two are comparable.
        #
        # `tiers_requested != tiers_read` is therefore a real and readable
        # signal: a tier was asked for and did not arrive.
        "coverage": {
            "tiers_requested": None,
            "tiers_read": tiers_read(ds),
            "tx_fingerprints": (
                {"read": len(ds.txs), "source": "dataset"} if ds.txs else None
            ),
            "funding": (
                {"read": len(ds.funding), "source": "dataset"} if ds.funding else None
            ),
        },
    }


def tiers_read(ds: Dataset) -> str:
    """Which evidence tiers the dataset the detector saw actually carries.

    ``"a"`` logs, ``"b"`` transaction fingerprints, ``"c"`` funding — derived
    from the dataset itself rather than from anybody's intent, so it means the
    same thing on a live sweep and on a committed bundle.
    """
    return "".join(
        tier
        for tier, present in (
            ("a", bool(ds.deposits)),
            ("b", bool(ds.txs)),
            ("c", bool(ds.funding)),
        )
        if present
    )


# ---------------------------------------------------------------------------
# The live path
# ---------------------------------------------------------------------------


def _live(args, transport: Any) -> tuple[Dataset, dict, int, int]:
    """Sweep the chain: read the two constants, then the logs, then the tiers.

    Returns ``(dataset, provenance, points_per_eth, min_deposit_wei)``.  The
    two constants come first and a failure to read either **stops the run** —
    an analysis scored at a rate nobody measured is worse than no analysis,
    because it looks exactly like one that was.
    """
    import asyncio  # noqa: PLC0415 — the pure install never reaches this line

    from . import sources
    from .sources import blockscout, logs, txs

    try:
        sources.require_httpx()
    except sources.MissingDependency as exc:
        raise CliError(str(exc)) from exc

    config = sources.SourceConfig()
    kw: dict[str, Any] = {"config": config, "transport": transport}
    coverage: dict[str, Any] = {"tiers_requested": args.tiers}

    async def _run() -> tuple[Any, dict[str, Any], dict[str, Any], int | None, int | None]:
        rate = args.points_per_eth
        if rate is None:
            rate = await sources.fetch_uint_view(args.contract, "POINTS_PER_ETH()", **kw)
            # A READ ZERO IS NOT AN OUTAGE, AND `is None` CANNOT SEE IT.
            # `hex_to_int` answers `None` for a read that failed and `0` for a
            # chain that really said zero, which is the whole point of that
            # rule — but zero is also an unusable rate: every deposit scores
            # zero points, and `CuratorPreset` (rightly) refuses it with a
            # `ValueError` that used to leave `main` as a traceback.  Name the
            # view that answered it instead.  Only the *live* read is checked:
            # `--points-per-eth` is the caller's own measurement and never
            # reaches here.
            if rate == 0:
                raise CliError(
                    f"{args.contract} answered POINTS_PER_ETH() = 0.  That is a "
                    "reading rather than an outage, and it is an unusable rate: "
                    "every deposit would score zero points.  Check the address "
                    "(a contract without that view can answer zero words), or "
                    "pass --points-per-eth with a value you read yourself."
                )
        minimum = args.min_deposit_wei
        if minimum is None:
            minimum = await sources.fetch_uint_view(args.contract, "minDeposit()", **kw)
            # Same shape, and the same reasoning the `is None` branch below
            # already spells out: with no protocol minimum the R13 exemption
            # applies to nobody, so the whole minimum-paying crowd is linked by
            # an identicalness that identifies nobody.  A zero the caller
            # measured is the caller's business — `--min-deposit-wei 0` skips
            # this read entirely — but a zero we read off the chain stops.
            if minimum == 0:
                raise CliError(
                    f"{args.contract} answered minDeposit() = 0, so the R13 "
                    "exemption would apply to nobody and the whole "
                    "minimum-paying crowd would be linked by an identicalness "
                    "that identifies nobody.  Check the address, or pass "
                    "--min-deposit-wei 0 if that zero is what you measured."
                )
        if rate is None or minimum is None:
            return None, {}, {}, rate, minimum
        sweep = await logs.fetch_deposits(args.contract, args.from_block, **kw)
        if sweep is None:
            return None, {}, {}, rate, minimum

        # `is not None`, never truthiness.  A sweep that ran and resolved
        # nothing is a healthy sweep — the node answering `"result": null` is
        # the documented ask-again case — and a falsy-empty check would stamp
        # it "unavailable", which is the opposite of what happened.
        fingerprints: dict[str, Any] = {}
        if "b" in args.tiers:
            hashes, cut_at = _tx_hashes_in_chain_order(sweep.deposits, args.max_txs)
            got = await txs.fetch_tx_fingerprints(hashes, **kw)
            reached = got is not None
            fingerprints = got.fingerprints if reached else {}
            coverage["tx_fingerprints"] = {
                "requested": len(hashes),
                "read": len(fingerprints),
                "unread": (len(got.pending) if reached else len(hashes)),
                "available": len({d.tx_hash for d in sweep.deposits}),
                "cap": args.max_txs,
                "cut_at_block": cut_at,
                "source": None if reached else "unavailable",
            }
        else:
            coverage["tx_fingerprints"] = None

        funding: dict[str, Any] = {}
        if "c" in args.tiers:
            addresses = _contributors_in_chain_order(sweep.deposits)
            got_funding = await blockscout.fetch_funding(
                addresses, budget=args.funding_budget, **kw
            )
            reached_funding = got_funding is not None
            funding = got_funding.funding if reached_funding else {}
            coverage["funding"] = {
                "requested": len(addresses),
                "read": len(funding),
                "budget": args.funding_budget,
                "pending": (
                    len(got_funding.pending) if reached_funding else len(addresses)
                ),
                "page_bounded": (
                    len(got_funding.page_bounded) if reached_funding else 0
                ),
                "source": None if reached_funding else "unavailable",
            }
        else:
            coverage["funding"] = None
        return sweep, fingerprints, funding, rate, minimum

    sweep, fingerprints, funding, rate, minimum = asyncio.run(_run())
    if rate is None:
        raise CliError(
            "could not read POINTS_PER_ETH() from the chain — refusing to score "
            "an analysis at a rate nobody measured.  Pass --points-per-eth to "
            "override with a value you read yourself."
        )
    if minimum is None:
        raise CliError(
            "could not read minDeposit() from the chain — without it the whole "
            "minimum-paying crowd is linked by an identicalness that identifies "
            "nobody.  Pass --min-deposit-wei to override."
        )
    if sweep is None:
        raise CliError(
            f"the log sweep of {args.contract} from block {args.from_block} failed; "
            "reporting unavailable rather than a partial history"
        )
    ds = sweep.dataset(txs=fingerprints or None, funding=funding or None)
    prov = _provenance(ds, {}, f"{args.contract}@{args.from_block}")
    prov["block_range"] = {"from": sweep.from_block, "to": sweep.to_block}
    # The live detail replaces the dataset-derived per-tier rows, but
    # `tiers_read` stays the one `_provenance` computed: it is derived from the
    # dataset the detector actually saw, identically on both paths, which is
    # what makes `tiers_requested != tiers_read` mean something.
    coverage["tiers_read"] = prov["coverage"]["tiers_read"]
    prov["coverage"] = coverage
    return ds, prov, rate, minimum


def _tx_hashes_in_chain_order(
    deposits, cap: int
) -> tuple[list[str], int | None]:
    """Distinct deposit tx hashes in **chain order**, cut at a block boundary.

    Two things wrong with the obvious ``sorted({...})[:cap]`` and both of them
    matter to the detector rather than to the fetch:

    * a *lexicographic* slice of transaction hashes is an arbitrary sample of
      the population — it is uncorrelated with anything, so a capped run
      fingerprints a scatter of wallets across every operator instead of a
      contiguous slice of history;
    * cutting mid-block splits a **group**.  The gas family's whole claim is
      "this component collapses to one fingerprint", and it requires ≥ 90 %
      coverage of a component before it will speak; a cap that fingerprints 14
      of a 20-transaction block hands it a coverage hole shaped exactly like
      evidence.

    So: walk chain order, and stop at the last block that fits **whole**.
    Returns ``(hashes, cut_at_block)`` — ``cut_at_block`` is ``None`` when
    nothing was cut, and otherwise the first block NOT covered, which the
    document header records and a later pass can resume from.
    """
    ordered = sorted(deposits, key=lambda d: (d.block_number, d.log_index))
    by_block: dict[int, list[str]] = {}
    for dep in ordered:
        hashes = by_block.setdefault(dep.block_number, [])
        if dep.tx_hash not in hashes:
            hashes.append(dep.tx_hash)

    out: list[str] = []
    for block in sorted(by_block):
        group = by_block[block]
        if out and len(out) + len(group) > cap:
            return out, block
        out.extend(group)
        if len(out) >= cap:
            nxt = [b for b in sorted(by_block) if b > block]
            return out, (nxt[0] if nxt else None)
    return out, None


def _contributors_in_chain_order(deposits) -> list[str]:
    """Distinct contributors in the order they first appear on chain.

    Chain order rather than sorted, for the same reason as the hashes: a
    budgeted funding pass should walk the history, not the alphabet.
    """
    seen: dict[str, None] = {}
    for dep in sorted(deposits, key=lambda d: (d.block_number, d.log_index)):
        seen.setdefault(dep.contributor, None)
    return list(seen)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def _wei(value: int | None) -> str | None:
    return None if value is None else str(value)


def _analyze_doc(ds: Dataset, res, preset: CuratorPreset, prov: dict) -> dict:
    return {
        **prov,
        "command": "analyze",
        "preset": prov.get("preset", "curator"),
        "config": {
            "min_size": preset.min_size,
            "min_families": preset.min_families,
            "near_amount_tol": preset.near_amount_tol,
            "confidence_threshold": preset.confidence_threshold,
            "points_per_eth": preset.points_per_eth,
            "protocol_min_amount_wei": _wei(preset.min_deposit_wei),
        },
        "totals": {
            "total_points": res.total_points,
            "flagged_points": res.flagged_points,
            "clean_points": res.clean_points,
            "contributors": len(res.analyzed),
            "flagged_contributors": len(res.flagged),
            "clusters": len(res.clusters),
        },
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "members": list(c.members),
                "reasons": [
                    {
                        "family": r.family,
                        "human_string": r.human_string,
                        "strength": r.strength,
                    }
                    for r in c.reasons
                ],
                "confidence": c.confidence,
                "points": c.points,
                "points_share": c.points_share,
                "span_blocks": c.span_blocks,
            }
            for c in res.clusters
        ],
        "flagged": sorted(res.flagged),
    }


def _segments_doc(ds: Dataset, res, preset: CuratorPreset, prov: dict) -> dict:
    segs = segments(ds, res, preset)
    return {
        **prov,
        "command": "segments",
        "preset": prov.get("preset", "curator"),
        "total_points": segs.total_points,
        "total_contributors": segs.total_contributors,
        "largest_operator_credit_wei": _wei(segs.largest_operator_credit_wei),
        "operators": [
            {
                "cluster_id": op.cluster_id,
                "size": op.size,
                "credit_wei": _wei(op.credit_wei),
                "weight_wei": _wei(op.weight_wei),
                "points": op.points,
                "points_share": op.points_share,
                "subsidy_x": op.subsidy_x,
                "confidence": op.confidence,
                "label": op.label,
                "reasons": list(op.reasons),
            }
            for op in segs.operators
        ],
        "bands": [
            {
                "key": b.key,
                "kind": b.kind,
                "label": b.label,
                "contributors": b.contributors,
                "points": b.points,
                "points_share": b.points_share,
                "detail": b.detail,
            }
            for b in segs.bands
        ],
    }


def _clean_list_doc(ds: Dataset, res, preset: CuratorPreset, prov: dict) -> dict:
    clean = clean_list(ds, res, preset)
    return {
        **prov,
        "command": "export-clean-list",
        "preset": prov.get("preset", "curator"),
        "totals": {
            "total_points": clean.total_points,
            "flagged_points": clean.flagged_points,
            "clean_points": clean.clean_points,
            "contributors_total": clean.contributors_total,
            "flagged_contributors": clean.flagged_contributors,
            "clean_contributors": clean.clean_contributors,
        },
        "entries": [
            {
                "clean_rank": e.clean_rank,
                "address": e.address,
                "points": e.points,
                "credit_wei": _wei(e.credit_wei),
                "weight_wei": _wei(e.weight_wei),
            }
            for e in clean.entries
        ],
        # The removed set travels WITH the survivors: a cleaned list that shows
        # only who is left cannot be checked by anybody.
        "removed": sorted(res.flagged),
    }


BUILDERS = {
    "analyze": _analyze_doc,
    "segments": _segments_doc,
    "export-clean-list": _clean_list_doc,
}


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sybilkit",
        description=(
            "Keyless, read-only EVM sybil / fan-out cluster analysis.  Nothing "
            "here signs, sends, or constructs calldata for a state change, and "
            "no source needs an API key of any kind."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("analyze", "detect linked-wallet clusters and write reasons-shaped JSON"),
        ("segments", "operator, cohort, hour and multiplier bands"),
        ("export-clean-list", "the ranked list with flagged groups removed"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--contract", help="the contract to sweep (live path)")
        p.add_argument("--from-block", type=int, default=0,
                       help="first block of the sweep (live path)")
        p.add_argument("--dataset", help="a committed JSON bundle; sweeps nothing")
        p.add_argument("--preset", choices=PRESETS, default="curator")
        p.add_argument("--out", help="write here instead of stdout, and say where")
        p.add_argument("--points-per-eth", type=int, default=None,
                       help="the chain's POINTS_PER_ETH; read live when omitted")
        p.add_argument("--min-deposit-wei", type=int, default=None,
                       help="the chain's minDeposit in wei; read live when omitted")
        p.add_argument("--tiers", default="ab", choices=("a", "ab", "abc"),
                       help="evidence tiers to fetch: a=logs, b=+gas, c=+funding")
        p.add_argument("--max-txs", type=int, default=5_000,
                       help="cap on tier-B fingerprint lookups")
        p.add_argument("--funding-budget", type=int, default=0,
                       help="cap on tier-C funding lookups (slow; 0 disables)")
        p.add_argument("--min-size", type=int, default=5)
        p.add_argument("--min-families", type=int, default=2)
        p.add_argument("--near-amount-tol", type=float, default=0.10)
    return parser


def main(argv: Sequence[str] | None = None, *, transport: Any = None) -> int:
    """Run one subcommand.  Returns a process exit status; never raises.

    *transport* is keyword-only and exists so the suite can drive the live path
    without a socket.  It is not a user-facing flag: a caller who wants a
    different endpoint edits :class:`sybilkit.sources.SourceConfig`.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args, parser, transport)
    except CliError as exc:
        print(f"sybilkit: {exc}", file=sys.stderr)
        return 2
    except (ValueError, KeyError, ArithmeticError) as exc:
        # The three exception types a *user-supplied* input reaches the library
        # with: an out-of-range option (`--points-per-eth 0` →
        # `CuratorPreset.__post_init__`), a hand-written bundle missing a field
        # (`dataset_from_labeled` reads `entry["first_index"]` directly), and
        # anything the arithmetic reaches on a degenerate dataset.  The library
        # validates its own inputs properly; what was missing was a CLI that
        # turned that validation into a message and a status instead of a
        # stack trace.  Deliberately narrow: a `TypeError` or an
        # `AttributeError` is *our* bug and still propagates with its traceback
        # intact, because that is the report we want.  Exit 3, distinct from
        # the 2 a `CliError` returns, so a script can tell "you asked for
        # something impossible" from "your input is malformed".
        print(f"sybilkit: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


def _run(args, parser: argparse.ArgumentParser, transport: Any) -> int:
    if args.dataset:
        if args.points_per_eth is None or args.min_deposit_wei is None:
            raise CliError(
                "a --dataset run cannot read the chain, so it must be told the "
                "chain's numbers: pass --points-per-eth and --min-deposit-wei "
                "(read them yourself; there is deliberately no default)"
            )
        ds, meta = _load_bundle(Path(args.dataset))
        prov = _provenance(ds, meta, args.dataset)
        rate, minimum = args.points_per_eth, args.min_deposit_wei
    elif args.contract:
        # A cap that silently does nothing is worse than no cap: `--tiers abc`
        # with the funding budget at its 0 default used to run tiers a and b
        # and report tier c in neither the output nor an error, so the run
        # looked like a full A+B+C analysis and was not one.
        if "c" in args.tiers and not args.funding_budget:
            raise CliError(
                "--tiers abc asks for the funding pass but --funding-budget is 0, "
                "which would skip it silently.  Pass --funding-budget N (it is "
                "the slow tier: ~1-2 keyless Blockscout calls per address at "
                "~3 req/s, resumable across runs), or drop to --tiers ab."
            )
        ds, prov, rate, minimum = _live(args, transport)
    else:
        raise CliError(
            "nothing to analyse: pass --contract to sweep a chain, or "
            "--dataset to read a committed bundle"
        )
    prov["preset"] = args.preset

    preset = CuratorPreset(
        points_per_eth=rate,
        min_deposit_wei=minimum,
        min_size=args.min_size,
        min_families=args.min_families,
        near_amount_tol=args.near_amount_tol,
    )
    res = detect(ds, preset.detect_config())
    doc = BUILDERS[args.command](ds, res, preset, prov)
    text = json.dumps(doc, indent=2, sort_keys=False, ensure_ascii=False)
    if args.out:
        target = Path(args.out)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            raise CliError(f"could not write {target}: {exc}") from exc
        rows = next(
            (len(doc[k]) for k in ("clusters", "entries", "bands") if k in doc), 0
        )
        print(f"wrote {rows} rows to {target}")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "CliError", "build_parser", "main"]
