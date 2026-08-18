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


def _iso(text: Any) -> str | None:
    """A sweep timestamp normalised to ``YYYY-MM-DDTHH:MM:SSZ``, or ``None``.

    ``None`` rather than a guess: a bundle that carries no timestamp genuinely
    has none, and inventing one is exactly the fabricated fact this whole
    distribution refuses to produce.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    body = text.strip().replace(" ", "T")
    if body.endswith("Z"):
        return body
    if body.endswith("+00:00"):
        return body[: -len("+00:00")] + "Z"
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
    }


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

    async def _run() -> tuple[Any, dict[str, Any], dict[str, Any], int | None, int | None]:
        rate = args.points_per_eth
        if rate is None:
            rate = await sources.fetch_uint_view(args.contract, "POINTS_PER_ETH()", **kw)
        minimum = args.min_deposit_wei
        if minimum is None:
            minimum = await sources.fetch_uint_view(args.contract, "minDeposit()", **kw)
        if rate is None or minimum is None:
            return None, {}, {}, rate, minimum
        sweep = await logs.fetch_deposits(args.contract, args.from_block, **kw)
        if sweep is None:
            return None, {}, {}, rate, minimum
        fingerprints: dict[str, Any] = {}
        if "b" in args.tiers:
            hashes = sorted({d.tx_hash for d in sweep.deposits})[: args.max_txs]
            got = await txs.fetch_tx_fingerprints(hashes, **kw)
            fingerprints = got or {}
        funding: dict[str, Any] = {}
        if "c" in args.tiers and args.funding_budget:
            addresses = sorted({d.contributor for d in sweep.deposits})
            got_funding = await blockscout.fetch_funding(
                addresses, budget=args.funding_budget, **kw
            )
            funding = got_funding.funding if got_funding else {}
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
    return ds, prov, rate, minimum


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def _wei(value: int | None) -> str | None:
    return None if value is None else str(value)


def _analyze_doc(ds: Dataset, res, preset: CuratorPreset, prov: dict) -> dict:
    return {
        **prov,
        "command": "analyze",
        "preset": "curator",
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
        "preset": "curator",
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
        "preset": "curator",
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
        ds, prov, rate, minimum = _live(args, transport)
    else:
        raise CliError(
            "nothing to analyse: pass --contract to sweep a chain, or "
            "--dataset to read a committed bundle"
        )

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
