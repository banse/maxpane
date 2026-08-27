#!/usr/bin/env python3
"""Full-population diagnostics for sybilkit on THE LIST (settled, 19,522 wallets).

Reproduces the live maxpane run, then instruments it:
  * per-cluster evidence anatomy (which rule holds which member)
  * ablations (drop one rule family -> what survives)
  * the 60 labeled controls checked against the FULL-population run
  * ENS-named wallets inside clusters
Writes JSON to the scratchpad for downstream agents.
"""
from __future__ import annotations

import os

import collections
import json
import statistics
import sys

# Path resolution, in priority order: an explicit env override, then this
# checkout (so the audit runs from a clone of the public clustermap repo, which
# vendors sybilkit and carries the pinned snapshot), then the private workspace
# it was originally written in.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _first_path(env, *candidates):
    v = os.environ.get(env)
    if v:
        return v
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return candidates[-1] if candidates else None


SYBILKIT_SRC = _first_path(
    "SYBIL_SYBILKIT_SRC",
    os.path.join(_HERE, "..", "..", "vendor", "sybilkit", "src"),   # clustermap layout
    "/Library/Vibes/autopull/sybilkit/src",                          # original workspace
)
LABELED_SUBSET = _first_path(
    "SYBIL_LABELED_SUBSET",
    os.path.join(_HERE, "..", "..", "vendor", "sybilkit", "tests", "fixtures", "labeled_subset.json"),
    "/Library/Vibes/autopull/sybilkit/tests/fixtures/labeled_subset.json",
)
CACHE = _first_path(
    "SYBIL_CACHE",
    os.path.expanduser("~/.maxpane/curator_cache.json"),             # live maxpane cache
    os.path.join(_HERE, "..", "..", "data", "curator_snapshot.json.gz"),  # public pinned snapshot
)

sys.path.insert(0, SYBILKIT_SRC)

from sybilkit import Dataset, detect  # noqa: E402
from sybilkit.cluster import FAMILIES, _UnionFind  # noqa: E402
from sybilkit.curator import CuratorPreset, credited_totals, final_weights  # noqa: E402
from sybilkit.curve import curve_points  # noqa: E402
from sybilkit.labels import is_infra_funder  # noqa: E402
from sybilkit.signals import (  # noqa: E402
    deposit_counts,
    first_rows,
    identical_amount_windows,
    single_first_rows,
)
from sybilkit.signals.amounts import amount_edges  # noqa: E402
from sybilkit.signals.cadence import cadence_edges  # noqa: E402
from sybilkit.signals.funding import funding_edges  # noqa: E402
from sybilkit.signals.gas import gas_edges  # noqa: E402
from sybilkit.signals.sequence import sequence_edges  # noqa: E402
from sybilkit.signals.split import split_edges  # noqa: E402

def _resolve_data():
    """Evidence dir: `audit/data` in a clustermap checkout, `data/sybil` in the
    workspace this was written in. Override with env SYBIL_DATA."""
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "..", "data"), os.path.join(here, "..", "..", "data", "sybil")):
        if os.path.isdir(c):
            return c
    return os.path.join(here, "..", "..", "data", "sybil")


OUT = os.environ.get("SYBIL_DATA") or _resolve_data()
ETH = 10**18


def eth(w: int) -> str:
    whole, frac = divmod(w, ETH)
    t = f"{whole}.{frac:018d}".rstrip("0")
    return t + "0" if t.endswith(".") else t


def _read(path):
    """The private maxpane cache, or the public pinned snapshot, as one shape.

    The snapshot (clustermap `data/curator_snapshot.json.gz`, tagged v0.1.0)
    carries the same inputs but not the derived blocks: ENS names and
    `hour_saved` ship beside it as audit data, and the live groups are simply
    recomputed — `detect()` on the snapshot reproduces the published
    263 clusters / 11,573 flagged exactly.
    """
    if path.endswith(".gz"):
        import gzip
        snap = json.load(gzip.open(path))
    else:
        snap = json.load(open(path))
    if "last_good" in snap:
        return snap
    side = lambda n: os.path.join(OUT, n)
    ens = json.load(open(side("ens_names.json"))) if os.path.exists(side("ens_names.json")) else {}
    hour_saved = json.load(open(side("hour_saved.json"))) if os.path.exists(side("hour_saved.json")) else []
    from sybilkit import Dataset, detect  # noqa: E402
    from sybilkit.curator import CuratorPreset  # noqa: E402
    cfgp = snap["analysis_config"]
    enr = snap["enrichment"]
    ds = Dataset.from_events(snap["events"], snap["first_deposits"], txs=enr["txs"], funding=enr["funding"])
    pre = CuratorPreset(points_per_eth=cfgp["points_per_eth"], min_deposit_wei=cfgp["min_deposit_wei"])
    res = detect(ds, pre.detect_config())
    groups = [{"members": [{"address": m} for m in g.members]} for g in res.clusters]
    return {
        "events": snap["events"], "first_deposits": snap["first_deposits"],
        "ens": {"names": ens}, "hour_saved": hour_saved,
        "last_good": {"clusters": {"payload": {"enrichment": enr, "groups": groups}},
                      "config": {"payload": cfgp}},
    }


def load():
    cache = _read(CACHE)
    enr = cache["last_good"]["clusters"]["payload"]["enrichment"]
    cfgp = cache["last_good"]["config"]["payload"]
    preset = CuratorPreset(points_per_eth=cfgp["points_per_eth"], min_deposit_wei=cfgp["min_deposit_wei"])
    ds = Dataset.from_events(cache["events"], cache["first_deposits"], txs=enr["txs"], funding=enr["funding"])
    ens = {a.lower(): v for a, v in cache["ens"]["names"].items()}
    live_groups = cache["last_good"]["clusters"]["payload"]["groups"]
    return cache, ds, preset, ens, live_groups


def edge_kind(e) -> str:
    """A finer label than family: which *rule* drew the edge."""
    s = e.reason.human_string
    if e.family == "amount":
        if s.startswith("identical odd"):
            return "amount:exact_odd"
        if s.startswith("identical "):
            return "amount:exact_round_wave"
        if s.startswith("near-identical"):
            return "amount:near_same_block"
        if s.startswith("≈ W/k"):
            return "amount:split"
    if e.family == "cadence":
        return "cadence:burst" if s.startswith("burst") else "cadence:drip"
    if e.family == "funding":
        return "funding:peel_chain" if "peel chain" in s else "funding:shared_hub"
    if e.family == "gas":
        return "gas:two_axes" if "one fee fingerprint" in s else "gas:limit+fee"
    return e.family


def combine(ds, cfg, tier_a_edges, *, drop_kinds=frozenset(), firsts=None):
    """Mirror of cluster.detect() with the ability to drop edge kinds.

    Returns (clusters, all_edges) where clusters is list of dicts.
    """
    if firsts is None:
        firsts = first_rows(ds)
    contributors = {d.contributor for d in ds.deposits}
    uf = _UnionFind()
    for a in contributors:
        uf.find(a)
    tier_a = [e for e in tier_a_edges if edge_kind(e) not in drop_kinds]
    for e in tier_a:
        uf.union(e.a, e.b)
    comps: dict[str, set[str]] = {}
    for a in contributors:
        comps.setdefault(uf.find(a), set()).add(a)
    groups = [g for g in comps.values() if len(g) >= 2]
    all_edges = list(tier_a)
    all_edges += [e for e in gas_edges(ds, cfg, groups=groups, firsts=firsts) if edge_kind(e) not in drop_kinds]
    all_edges += [e for e in funding_edges(ds, cfg, groups=groups) if edge_kind(e) not in drop_kinds]
    best: dict[str, dict[str, float]] = {}
    for e in all_edges:
        r = uf.find(e.a)
        fam = best.setdefault(r, {})
        fam[e.family] = max(fam.get(e.family, 0.0), e.reason.strength)
    clusters = []
    for root, members in comps.items():
        fams = best.get(root, {})
        if len(members) < cfg.min_size or len(fams) < cfg.min_families:
            continue
        comp = 1.0
        for s in fams.values():
            comp *= 1 - s
        clusters.append({"members": members, "families": sorted(fams), "confidence": 1 - comp})
    return clusters, all_edges, uf


def main():
    cache, ds, preset, ens, live_groups = load()
    cfg = preset.detect_config()
    res = detect(ds, cfg)
    live_members = {m for g in live_groups for m in g["members"]}
    print(f"population: {len(res.analyzed)} wallets, {len(ds.deposits)} deposits, txs={len(ds.txs)} funding={len(ds.funding)}")
    print(f"reproduced: {len(res.clusters)} clusters, {len(res.flagged)} flagged (live cache: {len(live_groups)} / {len(live_members)}); identical membership: {res.flagged == live_members}")

    firsts = first_rows(ds)
    counts = deposit_counts(ds)
    singles = single_first_rows(ds, firsts=firsts)
    windows = identical_amount_windows(ds, cfg, singles=singles)
    weights = final_weights(ds)
    credits = credited_totals(ds)
    points = {a: curve_points(w, preset.points_per_eth) for a, w in weights.items()}
    total_points = sum(points.values())

    tier_a = []
    tier_a += amount_edges(ds, cfg, firsts=firsts, windows=windows)
    tier_a += split_edges(ds, cfg, windows=windows)
    tier_a += sequence_edges(ds, cfg, firsts=firsts)
    tier_a += cadence_edges(ds, cfg, firsts=firsts)
    clusters, all_edges, uf = combine(ds, cfg, tier_a, firsts=firsts)
    print(f"mirror combiner: {len(clusters)} clusters, {sum(len(c['members']) for c in clusters)} members")
    print("edge kinds:", collections.Counter(edge_kind(e) for e in all_edges).most_common())

    # ---- per-member incident edge kinds -------------------------------------
    incident: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for e in all_edges:
        k = edge_kind(e)
        incident[e.a][k] += 1
        incident[e.b][k] += 1

    # ---- funding facts ---------------------------------------------------------
    labeled = json.load(open("/Library/Vibes/autopull/sybilkit/tests/fixtures/labeled_subset.json"))
    controls = {c["address"].lower() for c in labeled["controls"]}
    members_lab = {m["address"].lower(): m["cluster"] for m in labeled["members"]}

    by_root_final = {}
    for c in res.clusters:
        for m in c.members:
            by_root_final[m] = c.cluster_id

    rows = []
    for c in res.clusters:
        mem = set(c.members)
        amts = collections.Counter(firsts[m].amount_wei for m in mem)
        dom_amt, dom_n = amts.most_common(1)[0]
        hours = [firsts[m].hour for m in mem]
        blocks = [firsts[m].block_number for m in mem]
        multi = sum(1 for m in mem if counts[m] > 1)
        ens_n = sum(1 for m in mem if m in ens)
        ens_names = [ens[m][0] if isinstance(ens[m], list) else ens[m] for m in mem if m in ens][:12]
        txs = [ds.txs.get(firsts[m].tx_hash) for m in mem]
        txs = [t for t in txs if t is not None]
        nonces = [t.nonce for t in txs if t.nonce is not None]
        fresh = sum(1 for n in nonces if n == 0)
        aged = sum(1 for n in nonces if n >= 20)
        pfs = collections.Counter(t.max_priority_fee_wei for t in txs)
        gls = collections.Counter(t.gas_limit for t in txs)
        fund = [ds.funding.get(m) for m in mem]
        resolved = [f for f in fund if f is not None and f.funder is not None]
        in_cluster = sum(1 for f in resolved if f.funder in mem)
        funders = collections.Counter(f.funder for f in resolved)
        cex = sum(1 for f in resolved if is_infra_funder(f.funder))
        top_funder, top_n = (funders.most_common(1)[0] if funders else (None, 0))
        # attachment classes
        only_near = sum(1 for m in mem if set(incident[m]) <= {"amount:near_same_block"})
        only_round = sum(1 for m in mem if set(incident[m]) <= {"amount:exact_round_wave", "amount:split"})
        only_round_or_near = sum(1 for m in mem if set(incident[m]) <= {"amount:exact_round_wave", "amount:split", "amount:near_same_block"})
        only_seq = sum(1 for m in mem if set(incident[m]) <= {"sequence"})
        no_tierA_strong = sum(
            1 for m in mem
            if not (set(incident[m]) & {"amount:exact_odd", "cadence:burst", "cadence:drip", "sequence", "funding:peel_chain"})
        )
        off_amount = sum(1 for m in mem if firsts[m].amount_wei != dom_amt)
        rows.append({
            "cluster_id": c.cluster_id,
            "size": c.size,
            "families": sorted({r.family for r in c.reasons}),
            "reasons": [r.human_string for r in c.reasons],
            "confidence": round(c.confidence, 3),
            "points": c.points,
            "points_share_pct": round(c.points_share * 100, 3),
            "credit_eth": eth(sum(credits.get(m, 0) for m in mem)),
            "dominant_amount_eth": eth(dom_amt),
            "dominant_share": round(dom_n / len(mem), 3),
            "distinct_first_amounts": len(amts),
            "off_dominant_amount": off_amount,
            "hour_min": min(hours), "hour_max": max(hours),
            "block_span": max(blocks) - min(blocks),
            "multi_deposit_members": multi,
            "ens_members": ens_n, "ens_sample": ens_names,
            "tx_cov": round(len(txs) / len(mem), 2),
            "nonce0_frac": round(fresh / len(nonces), 2) if nonces else None,
            "nonce_ge20_frac": round(aged / len(nonces), 2) if nonces else None,
            "nonce_median": statistics.median(nonces) if nonces else None,
            "distinct_priority_fees": len(pfs), "distinct_gas_limits": len(gls),
            "funding_resolved": len(resolved), "funding_cov": round(len(resolved) / len(mem), 2),
            "funder_in_cluster": in_cluster,
            "funder_in_cluster_frac": round(in_cluster / len(resolved), 2) if resolved else None,
            "distinct_funders": len(funders), "top_funder": top_funder, "top_funder_n": top_n,
            "cex_funded": cex,
            "attached_only_near": only_near,
            "attached_only_round_window": only_round,
            "attached_only_round_or_near": only_round_or_near,
            "attached_only_sequence": only_seq,
            "no_strong_rule": no_tierA_strong,
            "controls_inside": sorted(mem & controls),
            "labeled_members_inside": collections.Counter(members_lab[m] for m in mem if m in members_lab).most_common(),
        })
    rows.sort(key=lambda r: -r["size"])
    json.dump(rows, open(f"{OUT}/clusters_diag.json", "w"), indent=1, default=str)

    # ---- headline aggregates ---------------------------------------------------
    flagged = res.flagged
    print("\n=== controls (60 labeled honest wallets) in the FULL-population run ===")
    ctrl_flagged = sorted(controls & flagged)
    print(f"controls flagged: {len(ctrl_flagged)} / {len(controls & res.analyzed)} present")
    for a in ctrl_flagged:
        cid = by_root_final[a]
        print(f"  {a} -> cluster {cid} size {res.clusters[cid].size} dom {rows[[r['cluster_id'] for r in rows].index(cid)]['dominant_amount_eth']} via {dict(incident[a])} amount={eth(firsts[a].amount_wei)} deposits={counts[a]}")
    print("\n=== attachment classes over all flagged ===")
    tot = len(flagged)
    print(f"flagged total: {tot}")
    print("  only near-same-block edge:", sum(r["attached_only_near"] for r in rows))
    print("  only round-window/split edge:", sum(r["attached_only_round_window"] for r in rows))
    print("  only round-or-near (no odd/burst/drip/sequence/peel):", sum(r["attached_only_round_or_near"] for r in rows))
    print("  no strong rule at all:", sum(r["no_strong_rule"] for r in rows))
    print("  multi-deposit (laddering) members flagged:", sum(r["multi_deposit_members"] for r in rows))
    print("  ENS-named flagged:", sum(r["ens_members"] for r in rows), "of", len(ens))
    print("  ENS-named unflagged:", sum(1 for a in ens if a in res.analyzed and a not in flagged))

    # ---- ablations --------------------------------------------------------------
    print("\n=== ablations (drop one rule; mirror combiner) ===")
    base_members = {m for c in clusters for m in c["members"]}
    base_points = sum(points[m] for m in base_members)
    print(f"baseline: {len(clusters)} clusters, {len(base_members)} members, {base_points/total_points*100:.1f}% points")
    abl = {}
    for kind in ["amount:near_same_block", "amount:exact_round_wave", "amount:split", "amount:exact_odd", "sequence",
                 "cadence:burst", "cadence:drip", "gas:two_axes", "gas:limit+fee", "funding:shared_hub", "funding:peel_chain"]:
        cl, _, _ = combine(ds, cfg, tier_a, drop_kinds={kind}, firsts=firsts)
        mem = {m for c in cl for m in c["members"]}
        pts = sum(points[m] for m in mem)
        abl[kind] = {"clusters": len(cl), "members": len(mem), "points_pct": round(pts / total_points * 100, 2),
                     "members_lost": len(base_members - mem), "members_gained": len(mem - base_members),
                     "controls_flagged": len(controls & mem), "ens_flagged": sum(1 for a in ens if a in mem)}
        print(f"  -{kind:26s} clusters={len(cl):4d} members={len(mem):6d} ({len(base_members)-len(mem):+6d} lost) points={pts/total_points*100:5.1f}% controls={len(controls & mem)} ens={abl[kind]['ens_flagged']}")
    json.dump(abl, open(f"{OUT}/ablations.json", "w"), indent=1)

    # ---- windows for popular round amounts -------------------------------------
    print("\n=== round-amount wave windows (single-deposit wallets) ===")
    wrows = []
    for amount, window in windows:
        if amount % 10**16 == 0 and len(window) >= 5:
            hours = [h for h, _, _ in window]
            wrows.append((len(window), eth(amount), min(hours), max(hours)))
    wrows.sort(reverse=True)
    for n, a, h0, h1 in wrows[:40]:
        print(f"  {a:>8}Ξ ×{n:5d}  hours {h0}–{h1}")
    # ---- funding hub reasons with N ------------------------------------------------
    hub = collections.Counter()
    for e in all_edges:
        if edge_kind(e) == "funding:shared_hub":
            hub[e.reason.human_string] += 1
    print("\n=== funding hub reasons (distinct) ===", len(hub))
    small = [s for s in hub if "×2 " in s or s.endswith("×2 inside one cluster")]
    print("  hubs of exactly 2:", len(small), "| of 3:", sum(1 for s in hub if "×3 " in s))
    # which clusters got their SECOND family only from a ×2/×3 hub
    print("\n=== clusters whose 2nd family is funding via a hub of ≤3 (no peel chain) ===")
    n2 = 0
    for r in rows:
        if r["families"] == ["amount", "funding"] or r["families"] == ["cadence", "funding"] or r["families"] == ["funding", "sequence"]:
            reasons = " | ".join(r["reasons"])
            if "peel chain" not in reasons:
                n2 += 1
                print(f"  c{r['cluster_id']} size={r['size']} dom={r['dominant_amount_eth']} h{r['hour_min']}-{r['hour_max']} ens={r['ens_members']} multi={r['multi_deposit_members']} :: {reasons[:150]}")
    print("  count:", n2)

    # dump flagged ENS + controls for agents
    json.dump({
        "flagged_ens": {a: ens[a] for a in ens if a in flagged},
        "unflagged_ens": {a: ens[a] for a in ens if a in res.analyzed and a not in flagged},
        "controls_flagged": ctrl_flagged,
        "cluster_of": {a: by_root_final[a] for a in list(controls & flagged) + [a for a in ens if a in flagged]},
    }, open(f"{OUT}/flagged_ens_controls.json", "w"), indent=1)
    print(f"\nwrote {OUT}/clusters_diag.json, ablations.json, flagged_ens_controls.json")


if __name__ == "__main__":
    main()
