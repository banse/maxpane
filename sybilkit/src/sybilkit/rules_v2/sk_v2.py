#!/usr/bin/env python3
"""sybilkit v2 prototype harness — re-implements the tier-A signals with knobs so
candidate rule changes can be measured on the real settled population.

Baseline (Rules()) must reproduce the shipped result (263 clusters / 11,573 flagged).
Nothing here touches the sybilkit repo; gas/funding edges are reused from the library
(funding's infra list is patched per run).
"""
from __future__ import annotations

import os

import collections
import json
import statistics
import sys
from dataclasses import dataclass, field, replace

sys.path.insert(0, "/Library/Vibes/autopull/sybilkit/src")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sybilkit.cluster import Edge, _UnionFind  # noqa: E402
from sybilkit.curve import curve_points  # noqa: E402
from sybilkit.labels import CEX_HOT_WALLETS, ERC4337_ENTRYPOINTS  # noqa: E402
from sybilkit.report import Reason  # noqa: E402
from sybilkit.signals import deposit_counts, first_rows, near, single_first_rows, tol_bps_of  # noqa: E402
from sybilkit.signals import funding as _funding_mod  # noqa: E402
from sybilkit.signals.funding import funding_edges  # noqa: E402
from sybilkit.signals.gas import gas_edges  # noqa: E402

from sk_diag import edge_kind, load  # noqa: E402

def _resolve_data():
    """Evidence dir: `audit/data` in a clustermap checkout, `data/sybil` in the
    workspace this was written in. Override with env SYBIL_DATA."""
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "..", "data"), os.path.join(here, "..", "..", "data", "sybil")):
        if os.path.isdir(c):
            return c
    return os.path.join(here, "..", "..", "data", "sybil")


SCRATCH = os.environ.get("SYBIL_DATA") or _resolve_data()
ROUND_WEI = 10**16
ETH = 10**18

STRONG_KINDS = {"amount:exact_odd", "cadence:burst", "cadence:drip", "sequence", "funding:peel_chain"}


def decimals(amount_wei: int) -> int:
    """Significant decimal places of the ETH amount (0.45 -> 2, 2.067 -> 3, jitter -> 15+)."""
    if amount_wei == 0:
        return 0
    d = 18
    while d > 0 and amount_wei % 10 == 0:
        amount_wei //= 10
        d -= 1
    return d


@dataclass(frozen=True)
class Rules:
    # amount family
    round_window_mode: str = "hour"        # 'hour' (shipped) | 'block'
    round_window_blocks: int = 32          # used when mode == 'block'
    odd_mode: str = "global"               # 'global' (shipped) | 'jitter_only' | 'jitter_or_windowed'
    jitter_min_decimals: int = 6
    near_mode: str = "all"                 # 'all' (shipped) | 'jitter_only' | 'off'
    split_on: bool = True
    min_exempt_everywhere: bool = False    # protocol minimum exempt from sequence/cadence/near too
    min_band_factor: float = 0.0           # >0: amounts <= factor*min exempt from identity rules (odd/round/near/split), sequence and drip (burst kept)
    amount_universe: str = "single_first"  # 'single_first' (shipped) | 'largest' (each wallet's largest deposit, ladders included)
    tight_peel_builder: bool = False       # peel chain as a tier-A builder: funded nonce<=1, funder is a contributor whose deposit precedes by <= peel_max_blocks, amounts within peel_amount_tol
    peel_max_blocks: int = 30
    peel_amount_tol: float = 0.25
    peel_max_nonce: int = 1                # funded wallet's nonce at deposit must be <= this (warmed farm wallets carry 5-10)
    tight_peel_two_families: bool = False
    ladder_family: bool = False            # identical >=3-step deposit ladders across >=5 wallets whose first deposits fall within ladder_window_blocks
    ladder_window_blocks: int = 300
    jitter_band_family: bool = False       # >= jitter_band_min unique >=6-decimal amounts within a 2% band in ONE hour -> amount + cadence (engine) edges
    jitter_band_min: int = 20
    jitter_band_pct: float = 0.02
    residual_family: bool = False          # identical >=6-digit sub-0.01 residual shared by >=3 wallets -> global amount edge (max-send-minus-gas scripts)
    fresh_hub_family: bool = False         # one small (non-infra, fan-out<50) funder -> >=3 nonce-0 wallets depositing within 600 blocks: funding + cadence edges (builder)
    cex_fanout_share: float = 0.9          # share of the funder's nonce-0 group that must sit on one fee value
    cex_fanout_pop_max: float = 1.0        # ... and how common that fee value may be population-wide (1.0 = unchecked)
    cex_fanout_family: bool = False        # one exchange-scale funder -> >=10 nonce-0 wallets sharing ONE priority-fee value (>=90% of the group): funding + gas edges (builder)  # a tight peel edge also books its timing as a cadence edge (funded+deposited within 30 blocks of the funder's deposit)
    # sequence / cadence
    sequence_on: bool = True
    sequence_min_zone_exempt: bool = False   # skip runs whose amounts are all <= 1.2x protocol minimum
    sequence_min_run_round: int = 5          # min run length when the run's amounts are not jitter-class
    cadence_on: bool = True
    # corroboration
    hub_min: int = 2                       # shipped: 2
    infra_extra: frozenset = field(default_factory=frozenset)
    exchange_hub_mode: str = "exclude"     # 'exclude' | 'weak' (infra_extra hubs count only when the component is >=90% nonce-0 AND one gas axis collapses)
    gas_on: bool = True
    gas_one_axis_min_txs: int = 0          # >0: add a weaker gas reason when ONE axis collapses across >= this many distinct txs
    # gate
    min_size: int = 5
    min_families: int = 2
    member_gate: str = "cluster"           # 'cluster' (shipped) | 'local2' | 'local2_strong'
    aged_weak_periphery: int = 0           # nonce>=N + funder outside the population + only amount/cadence -> periphery
    core_only: bool = False                # components from STRONG edges only; weak edges never merge


def amount_class(amount_wei: int, rules: Rules, exempt: int | None) -> str:
    if exempt is not None and amount_wei == exempt:
        return "min"
    if amount_wei % ROUND_WEI == 0:
        return "round"
    if decimals(amount_wei) >= rules.jitter_min_decimals:
        return "jitter"
    return "human_odd"


def windows_for(rows, rules: Rules, global_reach: bool):
    """rows: sorted list of (hour, block, addr). Returns list of windows (lists)."""
    if global_reach:
        return [rows] if len(rows) >= 2 else []
    out, cur = [], [rows[0]]
    for r in rows[1:]:
        if rules.round_window_mode == "hour":
            gap_ok = r[0] - cur[-1][0] <= 1
        else:
            gap_ok = r[1] - cur[-1][1] <= rules.round_window_blocks
        if gap_ok:
            cur.append(r)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [r]
    if len(cur) >= 2:
        out.append(cur)
    return out


def tier_a_edges(ds, cfg, rules: Rules):
    firsts = first_rows(ds)
    counts = deposit_counts(ds)
    if rules.amount_universe == "largest":
        singles = {}
        for d in ds.deposits:
            cur = singles.get(d.contributor)
            if cur is None or d.amount_wei > cur.amount_wei:
                singles[d.contributor] = d
    else:
        singles = {a: d for a, d in firsts.items() if counts[a] == 1}
    exempt = cfg.protocol_min_amount_wei
    band = int(exempt * rules.min_band_factor) if (exempt is not None and rules.min_band_factor > 0) else None
    if band is not None:
        singles = {a: d for a, d in singles.items() if d.amount_wei > band}
    tol = tol_bps_of(cfg.near_amount_tol)
    edges: list[Edge] = []

    # ---- amount: identical (odd global / round windowed) + split ------------
    by_amount: dict[int, list] = collections.defaultdict(list)
    for a, d in singles.items():
        by_amount[d.amount_wei].append((d.hour, d.block_number, a))
    for amount, rows in sorted(by_amount.items()):
        if len(rows) < 2:
            continue
        cls = amount_class(amount, rules, exempt)
        if cls == "min":
            continue
        rows.sort()
        if cls == "round":
            wins, strength, tag = windows_for(rows, rules, False), 0.75, "identical %sΞ send ×%d in one wave"
        elif cls == "jitter":
            wins, strength, tag = windows_for(rows, rules, True), 0.9, "identical odd %sΞ send ×%d"
        else:  # human_odd
            if rules.odd_mode == "global":
                wins, strength, tag = windows_for(rows, rules, True), 0.9, "identical odd %sΞ send ×%d"
            elif rules.odd_mode == "jitter_only":
                wins, strength, tag = windows_for(rows, rules, False), 0.75, "identical %sΞ send ×%d in one wave"
            else:  # jitter_or_windowed: same as round windowing but odd strength
                wins, strength, tag = windows_for(rows, rules, False), 0.9, "identical odd %sΞ send ×%d"
        for w in wins:
            reason = Reason("amount", tag % (eth(amount), len(w)), strength)
            for (_, _, a), (_, _, b) in zip(w, w[1:]):
                edges.append(Edge(a, b, "amount", strength, reason))
            if rules.split_on and len(w) >= cfg.min_size and amount * len(w) >= 50 * ETH:
                r2 = Reason("amount", f"≈ W/k equal split: {eth(amount*len(w))}Ξ across ×{len(w)} of {eth(amount)}Ξ", 0.8)
                for (_, _, a), (_, _, b) in zip(w, w[1:]):
                    edges.append(Edge(a, b, "amount", 0.8, r2))

    # ---- amount: near-identical, same block ---------------------------------
    if rules.near_mode != "off":
        by_block: dict[int, list] = collections.defaultdict(list)
        for a, d in singles.items():
            if exempt is not None and d.amount_wei == exempt:
                continue
            if rules.near_mode == "jitter_only" and amount_class(d.amount_wei, rules, exempt) != "jitter":
                continue
            by_block[d.block_number].append((d.amount_wei, a))
        for block, rows in by_block.items():
            if len(rows) < 2:
                continue
            rows.sort()
            for (aa, a), (bb, b) in zip(rows, rows[1:]):
                if aa != bb and near(aa, bb, tol):
                    edges.append(Edge(a, b, "amount", 0.7, Reason("amount", f"near-identical {eth(aa)}Ξ–{eth(bb)}Ξ in one block", 0.7)))

    # ---- sequence -------------------------------------------------------------
    if rules.sequence_on:
        by_index = sorted((i, a) for a, i in ds.first_index.items() if a in firsts)
        run: list = []

        def flush(run):
            if len(run) < cfg.min_size:
                return
            if rules.min_exempt_everywhere and exempt is not None and all(firsts[a].amount_wei == exempt for _, a in run):
                return
            if rules.sequence_min_zone_exempt and exempt is not None and all(firsts[a].amount_wei <= exempt * 12 // 10 for _, a in run):
                return
            if band is not None and all(firsts[a].amount_wei <= band for _, a in run):
                return
            if not all(amount_class(firsts[a].amount_wei, rules, exempt) == "jitter" for _, a in run) and len(run) < rules.sequence_min_run_round:
                return
            blocks = [firsts[a].block_number for _, a in run]
            reason = Reason("sequence", f"consecutive join indices {run[0][0]:,}–{run[-1][0]:,} · {max(blocks)-min(blocks)}-block span", 0.9)
            for (_, a), (_, b) in zip(run, run[1:]):
                edges.append(Edge(a, b, "sequence", 0.9, reason))

        for index, addr in by_index:
            if run:
                pi, pa = run[-1]
                pd, dd = firsts[pa], firsts[addr]
                if index == pi + 1 and abs(dd.block_number - pd.block_number) <= 2 and near(dd.amount_wei, pd.amount_wei, tol):
                    run.append((index, addr))
                    continue
                flush(run)
            run = [(index, addr)]
        flush(run)

    # ---- cadence: burst + drip ---------------------------------------------------
    if rules.cadence_on:
        pab: dict[int, dict[int, list]] = collections.defaultdict(lambda: collections.defaultdict(list))
        burst_universe = {a: d for a, d in firsts.items() if counts[a] == 1} if band is not None else singles
        for a, d in burst_universe.items():
            if rules.min_exempt_everywhere and exempt is not None and d.amount_wei == exempt:
                continue
            pab[d.amount_wei][d.block_number].append(a)
        for amount, blocks in pab.items():
            q = {b: ad for b, ad in blocks.items() if len(ad) >= cfg.min_size}
            if len(q) < 2:
                continue
            for b, ad in q.items():
                reason = Reason("cadence", f"burst ×{len(ad)} of {eth(amount)}Ξ in one block, repeated over {len(q)} blocks", 0.85)
                ad.sort()
                for x, y in zip(ad, ad[1:]):
                    edges.append(Edge(x, y, "cadence", 0.85, reason))
        by_amt: dict[int, list] = collections.defaultdict(list)
        for a, d in singles.items():
            if rules.min_exempt_everywhere and exempt is not None and d.amount_wei == exempt:
                continue
            by_amt[d.amount_wei].append((d.block_number, a))
        for amount, rows in by_amt.items():
            if len(rows) < 8:
                continue
            rows.sort()
            run = [rows[0]]

            def flush_drip(run, amount=amount):
                if len(run) < 8:
                    return
                gaps = [b2 - b1 for (b1, _), (b2, _) in zip(run, run[1:])]
                if max(gaps) - min(gaps) > 4:
                    return
                reason = Reason("cadence", f"metronomic drip ×{len(run)} of {eth(amount)}Ξ every ~{sorted(gaps)[len(gaps)//2]} blocks", 0.8)
                for (_, a), (_, b) in zip(run, run[1:]):
                    edges.append(Edge(a, b, "cadence", 0.8, reason))

            for row in rows[1:]:
                gap = row[0] - run[-1][0]
                if 1 <= gap <= 8:
                    run.append(row)
                else:
                    flush_drip(run)
                    run = [row]
            flush_drip(run)
    # ---- jitter band: engine drip of unique >=6-decimal amounts inside a narrow band per hour ---
    if rules.jitter_band_family:
        by_hour: dict[int, list] = collections.defaultdict(list)
        for a, d in singles.items():
            if amount_class(d.amount_wei, rules, exempt) == "jitter":
                by_hour[d.hour].append((d.amount_wei, a))
        for h, rows in by_hour.items():
            if len(rows) < rules.jitter_band_min:
                continue
            rows.sort()
            i = 0
            while i < len(rows):
                j = i
                while j + 1 < len(rows) and rows[j + 1][0] <= rows[i][0] * (1 + rules.jitter_band_pct):
                    j += 1
                if j - i + 1 >= rules.jitter_band_min:
                    grp = rows[i:j + 1]
                    r1 = Reason("amount", f"jitter band: ×{len(grp)} unique ≥6-decimal amounts within {rules.jitter_band_pct:.0%} ({eth(grp[0][0])}–{eth(grp[-1][0])}Ξ) in hour {h}", 0.85)
                    r2 = Reason("cadence", f"engine pocket: ×{len(grp)} jittered sends inside one hour (humans: 0.5% of ENS wallets use such amounts)", 0.8)
                    for (_, a), (_, b) in zip(grp, grp[1:]):
                        edges.append(Edge(a, b, "amount", 0.85, r1)); edges.append(Edge(a, b, "cadence", 0.8, r2))
                    i = j + 1
                else:
                    i += 1
    # ---- residual fingerprint: identical >=6-digit sub-cent residual (max-send-minus-gas scripts) ---
    if rules.residual_family:
        by_res: dict[int, list] = collections.defaultdict(list)
        for a, d in singles.items():
            res = d.amount_wei % 10**16
            if res and decimals(res) >= 6 and res % 10**10:  # non-trivial residual with real digits
                by_res[res].append((d.block_number, a))
        for res, rows in by_res.items():
            if len(rows) < 3:
                continue
            rows.sort()
            reason = Reason("amount", f"identical sub-cent residual …{res:016d}wei ×{len(rows)} (max-send-minus-gas script)", 0.9)
            for (_, a), (_, b) in zip(rows, rows[1:]):
                edges.append(Edge(a, b, "amount", 0.9, reason))

    # ---- ladder fingerprint: identical multi-step deposit tuples ----------------------
    if rules.ladder_family:
        lad: dict[str, list] = collections.defaultdict(list)
        for d in ds.deposits:
            lad[d.contributor].append((d.block_number, d.amount_wei))
        by_tuple: dict[tuple, list] = collections.defaultdict(list)
        for a, rows in lad.items():
            if len(rows) >= 3:
                rows.sort()
                by_tuple[tuple(x for _, x in rows)].append((rows[0][0], a))
        for tup, rows in by_tuple.items():
            if len(rows) < cfg.min_size:
                continue
            rows.sort()
            win = [rows[0]]
            def flush_l(win, tup=tup):
                if len(win) < cfg.min_size:
                    return
                reason = Reason("amount", f"identical {len(tup)}-step ladder {eth(tup[0])}→{eth(tup[-1])}Ξ ×{len(win)} within {rules.ladder_window_blocks} blocks", 0.85)
                for (_, a), (_, b) in zip(win, win[1:]):
                    edges.append(Edge(a, b, "amount", 0.85, reason))
            for r in rows[1:]:
                if r[0] - win[-1][0] <= rules.ladder_window_blocks:
                    win.append(r)
                else:
                    flush_l(win); win = [r]
            flush_l(win)

    # ---- fresh hub: a small funder fanning out fresh wallets that all deposit within 2 hours ------
    if (rules.fresh_hub_family or rules.cex_fanout_family) and ds.funding:
        by_f: dict[str, list] = collections.defaultdict(list)
        fanout = collections.Counter(f.funder for f in ds.funding.values() if f.funder)
        for a, f in ds.funding.items():
            if f.funder and f.funder != a and a in firsts:
                t = ds.txs.get(firsts[a].tx_hash)
                if t is not None and t.nonce == 0:
                    by_f[f.funder].append((firsts[a].block_number, a, t.max_priority_fee_wei))
        base_infra_set = frozenset(CEX_HOT_WALLETS | ERC4337_ENTRYPOINTS)
        pop_fees = collections.Counter(
            ds.txs[firsts[a].tx_hash].max_priority_fee_wei
            for a in firsts if firsts[a].tx_hash in ds.txs
        )
        pop_total = sum(pop_fees.values()) or 1
        pop_fee_share = {f: c / pop_total for f, c in pop_fees.items()}
        for funder, rows in by_f.items():
            is_exch = funder in rules.infra_extra or funder in base_infra_set
            if rules.fresh_hub_family and not is_exch and fanout[funder] < 50 and len(rows) >= 3:
                rows.sort()
                win = [rows[0]]
                def flush_h(win, funder=funder):
                    if len(win) < 3:
                        return
                    r1 = Reason("funding", f"fresh hub: {funder[:10]}… funded ×{len(win)} brand-new wallets that all deposited within 2 hours", 0.85)
                    r2 = Reason("cadence", f"fresh-hub cadence: ×{len(win)} nonce-0 deposits within 600 blocks of one small funder", 0.75)
                    for (_, a, _), (_, b, _) in zip(win, win[1:]):
                        edges.append(Edge(a, b, "funding", 0.85, r1)); edges.append(Edge(a, b, "cadence", 0.75, r2))
                for r in rows[1:]:
                    if r[0] - win[-1][0] <= 600:
                        win.append(r)
                    else:
                        flush_h(win); win = [r]
                flush_h(win)
            if rules.cex_fanout_family and is_exch and len(rows) >= 10:
                fees = collections.Counter(fee for _, _, fee in rows if fee is not None)
                if fees:
                    fee, k = fees.most_common(1)[0]
                    # The share test is measured against the funder's whole
                    # nonce-0 group, so it moves when coverage moves: at 64 %
                    # coverage the Bitget loop sat at 97 % of its group and
                    # fired; with every contributor resolved the same 244
                    # wallets are 78.7 % of a group that grew to 310, and the
                    # rule went silent on a farm it had caught.  What actually
                    # carries the evidence is that many fresh withdrawals share
                    # one fee value the rest of the population rarely uses — an
                    # absolute count plus a rarity check, which is what the
                    # reason string below already claimed.
                    pop_share = pop_fee_share.get(fee, 1.0)
                    if k >= 10 and k >= rules.cex_fanout_share * len(rows) and pop_share <= rules.cex_fanout_pop_max:
                        grp = sorted((b, a) for b, a, f in rows if f == fee)
                        r1 = Reason("funding", f"exchange fan-out: {funder[:10]}… first-funded ×{k} nonce-0 wallets", 0.75)
                        r2 = Reason("gas", f"one priority fee ({fee} wei) on ×{k} of {len(rows)} fresh withdrawals (population share of that value {pop_share:.1%})", 0.7)
                        for (_, a), (_, b) in zip(grp, grp[1:]):
                            edges.append(Edge(a, b, "funding", 0.75, r1)); edges.append(Edge(a, b, "gas", 0.7, r2))

    # ---- tight peel chain as a tier-A builder --------------------------------------
    if rules.tight_peel_builder and ds.funding:
        dep_blocks: dict[str, list] = collections.defaultdict(list)
        for d in ds.deposits:
            dep_blocks[d.contributor].append((d.block_number, d.amount_wei))
        for a in dep_blocks:
            dep_blocks[a].sort()
        tolp = round(rules.peel_amount_tol * 10_000)
        for a, f in ds.funding.items():
            if f.funder is None or f.funder == a or a not in firsts or f.funder not in dep_blocks:
                continue
            t = ds.txs.get(firsts[a].tx_hash)
            if t is None or t.nonce is None or t.nonce > rules.peel_max_nonce:
                continue
            bw, aw = firsts[a].block_number, firsts[a].amount_wei
            prev = [(b, amt) for b, amt in dep_blocks[f.funder] if b <= bw]
            if not prev:
                continue
            fb, famt = prev[-1]
            if bw - fb <= rules.peel_max_blocks and near(aw, famt, tolp):
                edges.append(Edge(a, f.funder, "funding", 0.95, Reason("funding", "first funder is a member of the same cluster (peel chain) · tight: fresh wallet, funded within 30 blocks, like amount", 0.95)))
                if rules.tight_peel_two_families:
                    edges.append(Edge(a, f.funder, "cadence", 0.8, Reason("cadence", f"peel cadence: deposit lands ≤{rules.peel_max_blocks} blocks after the funder's own deposit", 0.8)))
    return edges, firsts, counts


def eth(w: int) -> str:
    whole, frac = divmod(w, ETH)
    t = f"{whole}.{frac:018d}".rstrip("0")
    return t + "0" if t.endswith(".") else t


def run(ds, cfg, rules: Rules, *, firsts_cache=None):
    edges, firsts, counts = tier_a_edges(ds, cfg, rules)
    contributors = {d.contributor for d in ds.deposits}
    uf = _UnionFind()
    for a in contributors:
        uf.find(a)
    merge_edges = [e for e in edges if not rules.core_only or edge_kind(e) in STRONG_KINDS]
    for e in merge_edges:
        uf.union(e.a, e.b)
    comps: dict[str, set] = {}
    for a in contributors:
        comps.setdefault(uf.find(a), set()).add(a)
    groups = [g for g in comps.values() if len(g) >= 2]

    # corroboration inside components
    base_infra = frozenset(CEX_HOT_WALLETS | ERC4337_ENTRYPOINTS)
    infra = frozenset(base_infra | rules.infra_extra)
    orig = _funding_mod.is_infra_funder
    _funding_mod.is_infra_funder = lambda a: a is not None and a.lower() in infra
    try:
        fedges = funding_edges(ds, cfg, groups=groups)
    finally:
        _funding_mod.is_infra_funder = orig
    # machine-fingerprint facts per component (for the weak-exchange-hub and one-axis gas rules)
    comp_fp = {}
    for g in groups:
        txs = {}
        for m in g:
            d = firsts.get(m)
            t = ds.txs.get(d.tx_hash) if d else None
            if t is not None:
                txs.setdefault(d.tx_hash, t)
        fp = list(txs.values())
        nonces = [t.nonce for t in fp if t.nonce is not None]
        fresh = (sum(1 for n in nonces if n == 0) / len(nonces)) if nonces else 0.0
        collapsed = []
        for ax in ("max_priority_fee_wei", "max_fee_wei", "gas_limit"):
            vals = [getattr(t, ax) for t in fp]
            if vals and all(v is not None for v in vals) and len(set(vals)) == 1:
                collapsed.append(ax)
        comp_fp[id(g)] = (len(fp), fresh, collapsed)
    if rules.exchange_hub_mode == "fresh_only" and rules.infra_extra:
        _funding_mod.is_infra_funder = lambda a: a is not None and a.lower() in base_infra
        try:
            fedges_all = funding_edges(ds, cfg, groups=groups)
        finally:
            _funding_mod.is_infra_funder = orig
        by_funder = {a: (f.funder or "").lower() for a, f in ds.funding.items()}
        def fresh(m):
            d = firsts.get(m); t = ds.txs.get(d.tx_hash) if d else None
            return t is not None and t.nonce == 0
        kept = list(fedges)
        seen = {(e.a, e.b, e.reason.human_string) for e in fedges}
        for e in fedges_all:
            key = (e.a, e.b, e.reason.human_string)
            if key in seen:
                continue
            fa, fb = by_funder.get(e.a), by_funder.get(e.b)
            if "shared first funder" in e.reason.human_string and fa in rules.infra_extra and fa == fb and fresh(e.a) and fresh(e.b):
                kept.append(Edge(e.a, e.b, "funding", 0.75, Reason("funding", e.reason.human_string + " · exchange withdrawals to fresh wallets", 0.75)))
        fedges = kept
    if rules.exchange_hub_mode == "weak" and rules.infra_extra:
        # re-run funding with ONLY the base infra excluded, then keep exchange-hub edges only for machine-looking components
        _funding_mod.is_infra_funder = lambda a: a is not None and a.lower() in base_infra
        try:
            fedges_all = funding_edges(ds, cfg, groups=groups)
        finally:
            _funding_mod.is_infra_funder = orig
        comp_of = {}
        for g in groups:
            for m in g:
                comp_of[m] = id(g)
        by_funder = {a: (f.funder or "").lower() for a, f in ds.funding.items()}
        kept = list(fedges)
        seen = {(e.a, e.b, e.reason.human_string) for e in fedges}
        for e in fedges_all:
            key = (e.a, e.b, e.reason.human_string)
            if key in seen:
                continue
            # an exchange-hub edge: both endpoints funded by an infra_extra funder
            fa, fb = by_funder.get(e.a), by_funder.get(e.b)
            if "shared first funder" in e.reason.human_string and fa in rules.infra_extra and fa == fb:
                n, fresh, collapsed = comp_fp.get(comp_of.get(e.a), (0, 0.0, []))
                if n >= 10 and fresh >= 0.9 and collapsed:
                    kept.append(Edge(e.a, e.b, "funding", 0.6, Reason("funding", e.reason.human_string + " · exchange withdrawals, all fresh, one fee value", 0.6)))
        fedges = kept
    if rules.hub_min > 2:
        kept = []
        for e in fedges:
            s = e.reason.human_string
            if "shared first funder" in s:
                n = int(s.split("×")[1].split()[0])
                if n < rules.hub_min:
                    continue
            kept.append(e)
        fedges = kept
    gedges = gas_edges(ds, cfg, groups=groups, firsts=firsts) if rules.gas_on else []
    if rules.gas_on and rules.gas_one_axis_min_txs > 0:
        for g in groups:
            n, fresh, collapsed = comp_fp.get(id(g), (0, 0.0, []))
            if n >= rules.gas_one_axis_min_txs and len(collapsed) == 1 and n >= 0.9 * len(g):
                reason = Reason("gas", f"one {collapsed[0].replace('_wei','').replace('_',' ')} value across ×{n} (controls spread over dozens)", 0.6)
                ms = sorted(g)
                for a, b in zip(ms, ms[1:]):
                    gedges.append(Edge(a, b, "gas", 0.6, reason))
    all_edges = edges + gedges + fedges

    # per-component families, per-member incident families
    fam_by_root: dict[str, dict[str, float]] = collections.defaultdict(dict)
    local: dict[str, dict[str, set]] = collections.defaultdict(lambda: collections.defaultdict(set))  # member -> family -> kinds
    for e in all_edges:
        r = uf.find(e.a)
        if uf.find(e.b) != r:
            continue  # a weak edge across components (core_only mode) never counts
        fam_by_root[r][e.family] = max(fam_by_root[r].get(e.family, 0.0), e.reason.strength)
        k = edge_kind(e)
        local[e.a][e.family].add(k)
        local[e.b][e.family].add(k)

    clusters = []
    for root, members in comps.items():
        fams = fam_by_root.get(root, {})
        if len(members) < rules.min_size or len(fams) < rules.min_families:
            continue
        if rules.member_gate == "cluster":
            core = set(members)
        else:
            core = set()
            for m in members:
                lf = local[m]
                nfam = len(lf)
                has_strong = any(k in STRONG_KINDS for ks in lf.values() for k in ks)
                # A wallet that had a life before this game, whose money came
                # from outside the population, and which is held ONLY by the two
                # coincidence-prone families, is the exact profile of every
                # residual false positive measured against the verified-honest
                # controls: an aged person sending a common round amount during
                # a busy wave. Amount+cadence agree trivially there — they are
                # two views of the same coincidence, not two witnesses.
                weak_only = bool(rules.aged_weak_periphery) and set(lf) <= {"amount", "cadence"}
                if weak_only:
                    t = ds.txs.get(firsts[m].tx_hash) if m in firsts else None
                    f = ds.funding.get(m)
                    aged = t is not None and t.nonce >= rules.aged_weak_periphery
                    external = f is not None and f.funder is not None and f.funder not in firsts
                    if aged and external:
                        continue  # periphery: shown, never removed
                if rules.member_gate == "local2" and nfam >= 2:
                    core.add(m)
                elif rules.member_gate == "local2_strong" and nfam >= 2 and has_strong:
                    core.add(m)
            if len(core) < rules.min_size:
                continue
        clusters.append({"members": members, "core": core, "periphery": members - core, "families": sorted(fams)})
    return clusters, all_edges, firsts, counts


def metrics(clusters, ds, preset, ens, extra):
    """Headline metrics for a variant."""
    weights = {}
    for d in sorted(ds.deposits, key=lambda d: (d.block_number, d.log_index)):
        weights[d.contributor] = d.new_weight_wei
    points = {a: curve_points(w, preset.points_per_eth) for a, w in weights.items()}
    total = sum(points.values())
    flagged = {m for c in clusters for m in c["core"]}
    periph = {m for c in clusters for m in c["periphery"]} - flagged
    lab = extra["labeled_members"]
    ops = collections.defaultdict(set)
    for a, name in lab.items():
        ops[name].add(a)
    whole = 0
    recall_n = 0
    for name, mem in ops.items():
        best = max((len(mem & set(c["core"])) for c in clusters), default=0)
        whole += best == len(mem)
        recall_n += len(mem & flagged)
    farm_windows = extra["farm_windows"]  # dict name -> set of addresses
    fw = {name: (len(s & flagged), len(s)) for name, s in farm_windows.items()}
    return {
        "clusters": len(clusters),
        "flagged": len(flagged),
        "periphery": len(periph),
        "points_pct": round(sum(points[m] for m in flagged) / total * 100, 2),
        "labeled_recall": f"{recall_n}/{len(lab)}",
        "operators_whole": f"{whole}/{len(ops)}",
        "farm_windows": fw,
        "ens_flagged": sum(1 for a in ens if a in flagged),
        "controls_flagged": len(extra["controls"] & flagged),
        "rescuers_flagged": len(extra["rescuers"] & flagged),
        "idmd_flagged": len(extra["idmd"] & flagged),
        "ladderers_flagged": sum(1 for m in flagged if extra["counts"].get(m, 1) > 1),
        "size_hist": sorted(collections.Counter(len(c["core"]) for c in clusters).items())[-8:],
    }


def build_extra(ds, cache):
    from sk_diag import LABELED_SUBSET
    lab = json.load(open(LABELED_SUBSET))
    labeled_members = {m["address"].lower(): m["cluster"] for m in lab["members"]}
    controls = {c["address"].lower() for c in lab["controls"]}
    rescuers = {r["wallet"].lower() for r in cache["hour_saved"]}
    firsts = first_rows(ds)
    counts = deposit_counts(ds)
    # undisputed farm windows as recall proxies (single-deposit, exact amount, hour range)
    from decimal import Decimal
    def win(amount_eth, h0, h1):
        w = int(Decimal(str(amount_eth)) * ETH)
        return {a for a, d in firsts.items() if counts[a] == 1 and d.amount_wei == w and h0 <= d.hour <= h1}
    farm_windows = {
        "0.45@h3-4": win(0.45, 3, 4), "14.0@h3-15": win(14.0, 3, 15), "10.0@h5": win(10.0, 5, 5),
        "1.2@h1-2": win(1.2, 1, 2), "2.067": win(2.067, 0, 66), "0.45@h34-37": win(0.45, 34, 37),
    }
    # the five audited 100-jitter batches: consecutive index ranges from the audit names
    ring = set()
    for d in ds.deposits:
        if 90 * ETH <= d.amount_wei <= 110 * ETH and 16 <= d.hour <= 19:
            ring.add(d.contributor)
    farm_windows["ring99(any dep 90-110Ξ h16-19)"] = ring
    lad = collections.defaultdict(list)
    for d in ds.deposits:
        lad[d.contributor].append((d.block_number, d.amount_wei))
    l10 = {a for a, rows in lad.items() if len(rows) == 5 and sorted(x for _, x in rows)[0] in (int(9.9 * ETH), 10 * ETH) and sorted(x for _, x in rows)[-1] in (int(10.3 * ETH), int(10.4 * ETH))}
    l045 = {a for a, rows in lad.items() if len(rows) == 5 and tuple(sorted(x for _, x in rows)) == tuple(int(Decimal(str(v)) * ETH) for v in (0.05, 0.15, 0.25, 0.35, 0.45)) and 35 <= firsts[a].hour <= 37}
    farm_windows["ladder10.x(5-step h37-45)"] = l10
    bitget = {a for a, f in ds.funding.items() if f.funder == "0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23" and a in firsts and 17 <= firsts[a].hour <= 31 and int(1.1 * ETH) <= firsts[a].amount_wei <= int(1.8 * ETH)}
    farm_windows["bitget-ladder(1.19-1.69 h17-31)"] = bitget
    recyc = {a for a, f in ds.funding.items() if f.funder in ("0x3230466e58bb1019f5695ff55248ece1e753eb79", "0x2fc92dde494064724fd371e55172877f86d842e9", "0x2e0db3f849b19b8d23993c4434ed02bf930d94f2")}
    farm_windows["0.05 recyclers(3 small hubs)"] = recyc
    jit110 = {a for a, d in firsts.items() if counts[a] == 1 and int(1.10 * ETH) <= d.amount_wei <= int(1.14 * ETH) and decimals(d.amount_wei) >= 6 and 36 <= d.hour <= 55}
    jit100 = {a for a, d in firsts.items() if counts[a] == 1 and int(1.00 * ETH) <= d.amount_wei <= int(1.05 * ETH) and decimals(d.amount_wei) >= 6 and 56 <= d.hour <= 64}
    farm_windows["jitter1.10-1.14(h36-55)"] = jit110
    farm_windows["jitter1.00-1.05(h56-64)"] = jit100
    farm_windows["ladder0.05→0.45(h35-37)"] = l045
    idx = {a: i for a, i in ds.first_index.items()}
    for start in (12058, 13326, 13795, 13897, 14001):
        farm_windows[f"idxrun_{start}"] = {a for a, i in idx.items() if start <= i < start + 100}
    try:
        idmd = {a.lower() for a in json.load(open(f"{SCRATCH}/idmd_holders.json"))}
    except Exception:
        idmd = set()
    return {"labeled_members": labeled_members, "controls": controls, "rescuers": rescuers, "counts": counts, "farm_windows": farm_windows, "idmd": idmd}


CAND = dict(round_window_mode="block", round_window_blocks=32, min_band_factor=1.25, odd_mode="jitter_only", near_mode="jitter_only",
            hub_min=2, exchange_hub_mode="fresh_only", member_gate="local2", tight_peel_builder=True, amount_universe="largest")
CAND2 = {**CAND, "tight_peel_two_families": True}
VARIANTS = {
    "v2 candidate": Rules(**CAND),
    "v2b (peel books cadence)": Rules(**CAND2),
    "v2c (v2b + ladder family)": Rules(**{**CAND2, "ladder_family": True}),
    "v2d (v2c, peel nonce≤20)": Rules(**{**CAND2, "ladder_family": True, "peel_max_nonce": 20}),
    "v2d + local2_strong": Rules(**{**CAND2, "ladder_family": True, "peel_max_nonce": 20, "member_gate": "local2_strong"}),
    "v2e (v2d + jitter band + residual)": Rules(**{**CAND2, "ladder_family": True, "peel_max_nonce": 20, "jitter_band_family": True, "residual_family": True}),
    "v2f (v2e + fresh hub + cex fan-out)": Rules(**{**CAND2, "ladder_family": True, "peel_max_nonce": 20, "jitter_band_family": True, "residual_family": True, "fresh_hub_family": True, "cex_fanout_family": True}),
    # v2f's fan-out test re-measured so it does not move with coverage: an
    # absolute count of fresh withdrawals on one fee value, and that value must
    # be uncommon population-wide.
    "v2h (v2g + aged-weak periphery)": Rules(**{**CAND2, "ladder_family": True, "peel_max_nonce": 20, "jitter_band_family": True, "residual_family": True, "fresh_hub_family": True, "cex_fanout_family": True, "cex_fanout_share": 0.5, "cex_fanout_pop_max": 0.25, "aged_weak_periphery": 50}),
    "v2g (v2f, coverage-stable fan-out)": Rules(**{**CAND2, "ladder_family": True, "peel_max_nonce": 20, "jitter_band_family": True, "residual_family": True, "fresh_hub_family": True, "cex_fanout_family": True, "cex_fanout_share": 0.5, "cex_fanout_pop_max": 0.25}),
    "v2b − largest": Rules(**{**CAND2, "amount_universe": "single_first"}),
    "v2b + local2_strong": Rules(**{**CAND2, "member_gate": "local2_strong"}),
    "v2 − tight_peel": Rules(**{**CAND, "tight_peel_builder": False}),
    "v2 − largest": Rules(**{**CAND, "amount_universe": "single_first"}),
    "v2 − fresh_only(cex→exclude)": Rules(**{**CAND, "exchange_hub_mode": "exclude"}),
    "v2 − band(1.25→0, seq min-zone)": Rules(**{**CAND, "min_band_factor": 0.0, "min_exempt_everywhere": True, "sequence_min_zone_exempt": True}),
    "v2 − local2 (cluster gate)": Rules(**{**CAND, "member_gate": "cluster"}),
    "v2 + local2_strong": Rules(**{**CAND, "member_gate": "local2_strong"}),
    "baseline(shipped)": Rules(),
    "A round windows ≤32 blocks": Rules(round_window_mode="block", round_window_blocks=32),
    "A' round windows ≤300 blocks(~1h)": Rules(round_window_mode="block", round_window_blocks=300),
    "B min exempt everywhere": Rules(min_exempt_everywhere=True),
    "C odd: jitter_only (≤5 decimals = round)": Rules(odd_mode="jitter_only"),
    "D near: jitter_only": Rules(near_mode="jitter_only"),
    "E hub_min 5": Rules(hub_min=5),
    "F member gate local2": Rules(member_gate="local2"),
    "G member gate local2_strong": Rules(member_gate="local2_strong"),
    "H core_only (weak edges never merge)": Rules(core_only=True),
    "ABCDE combined": Rules(round_window_mode="block", round_window_blocks=32, min_exempt_everywhere=True, odd_mode="jitter_only", near_mode="jitter_only", hub_min=5),
    "ABCDE + local2": Rules(round_window_mode="block", round_window_blocks=32, min_exempt_everywhere=True, odd_mode="jitter_only", near_mode="jitter_only", hub_min=5, member_gate="local2"),
    "ABCDE2 + local2_strong": Rules(round_window_mode="block", round_window_blocks=32, min_exempt_everywhere=True, odd_mode="jitter_only", near_mode="jitter_only", hub_min=5, member_gate="local2_strong", sequence_min_zone_exempt=True, sequence_min_run_round=8),
    "ABCDE2 + local2": Rules(round_window_mode="block", round_window_blocks=32, min_exempt_everywhere=True, odd_mode="jitter_only", near_mode="jitter_only", hub_min=5, member_gate="local2", sequence_min_zone_exempt=True, sequence_min_run_round=8),
    "ABCDE2 + local2 + weak-exchange-hub + gas1axis20": Rules(round_window_mode="block", round_window_blocks=32, min_exempt_everywhere=True, odd_mode="jitter_only", near_mode="jitter_only", hub_min=5, member_gate="local2", sequence_min_zone_exempt=True, sequence_min_run_round=8, exchange_hub_mode="weak", gas_one_axis_min_txs=20),
    "ABCDE + local2_strong": Rules(round_window_mode="block", round_window_blocks=32, min_exempt_everywhere=True, odd_mode="jitter_only", near_mode="jitter_only", hub_min=5, member_gate="local2_strong"),
}


def dump_diff(name, rules, ds, cfg, preset, ens, extra, cache):
    """Released-vs-baseline wallets with attributes, plus per-cluster shrink table."""
    base_cl, base_edges, firsts, counts = run(ds, cfg, Rules())
    var_cl, var_edges, _, _ = run(ds, cfg, rules)
    base_flagged = {m for c in base_cl for m in c["core"]}
    var_flagged = {m for c in var_cl for m in c["core"]}
    var_periph = {m for c in var_cl for m in c["periphery"]}
    released = base_flagged - var_flagged
    newly = var_flagged - base_flagged
    inc = collections.defaultdict(collections.Counter)
    for e in base_edges:
        k = edge_kind(e); inc[e.a][k] += 1; inc[e.b][k] += 1
    live = cache["last_good"]["clusters"]["payload"]["groups"]
    cid_of = {m: i for i, g in enumerate(live) for m in g["members"]}
    rows = []
    for a in sorted(released):
        d = firsts[a]
        rows.append({"address": a, "baseline_cluster": cid_of.get(a), "amount_eth": eth(d.amount_wei), "hour": d.hour,
                     "deposits": counts[a], "ens": (ens.get(a) or [None])[0], "incident_kinds": dict(inc[a]),
                     "now": "periphery" if a in var_periph else "clean"})
    shrink = collections.Counter(r["baseline_cluster"] for r in rows)
    table = []
    for cid, n in shrink.most_common():
        g = live[cid]
        table.append({"cluster_id": cid, "size": g["size"], "released": n, "families": g["families"], "reason0": g["reasons"][0][:70]})
    newly_rows = []
    for a in sorted(newly):
        lad = sorted((d.block_number, d.amount_wei) for d in ds.deposits if d.contributor == a)
        t = ds.txs.get(firsts[a].tx_hash)
        f = ds.funding.get(a)
        newly_rows.append({"address": a, "ens": (ens.get(a) or [None])[0], "nonce": t.nonce if t else None, "deposits": [eth(x) for _, x in lad],
                           "hour": firsts[a].hour, "funder": (f.funder if f else None), "funder_is_contributor": bool(f and f.funder in firsts),
                           "rescuer": a in extra["rescuers"], "idmd": a in extra["idmd"]})
    nl = [r for r in newly_rows if len(r["deposits"]) > 1]
    print(f"  newly flagged: {len(newly_rows)} (ladderers {len(nl)}, ENS {sum(1 for r in newly_rows if r['ens'])}, nonce>=20 {sum(1 for r in newly_rows if (r['nonce'] or 0) >= 20)}, funder-is-contributor {sum(1 for r in newly_rows if r['funder_is_contributor'])})")
    for r in newly_rows[:40]:
        print(f"    {r['address'][:12]} ens={r['ens']} nonce={r['nonce']} h{r['hour']} deps={r['deposits'][:6]} funder∈pop={r['funder_is_contributor']} resc={r['rescuer']} idmd={r['idmd']}")
    json.dump({"variant": name, "released": rows, "newly_flagged": newly_rows, "shrink_table": table},
              open(f"{SCRATCH}/v2_diff.json", "w"), indent=1)
    print(f"\n=== diff {name}: released={len(released)} newly_flagged={len(newly)} periphery={len(var_periph)} ===")
    for t in table[:25]:
        print(f"  c{t['cluster_id']:<4d} size={t['size']:5d} released={t['released']:5d} fam={','.join(t['families'])} :: {t['reason0']}")
    amt = collections.Counter(r["amount_eth"] for r in rows)
    print("  released by amount:", amt.most_common(15))
    hrs = collections.Counter(r["hour"] for r in rows)
    print("  released by hour:", sorted(hrs.items()))


def main(argv):
    cache, ds, preset, ens, live_groups = load()
    if "--enrich-extra" in argv:
        from sybilkit import Dataset
        enr = cache["last_good"]["clusters"]["payload"]["enrichment"]
        txs = dict(enr["txs"]); funding = dict(enr["funding"])
        n0 = (len(txs), len(funding))
        for path in argv[argv.index("--enrich-extra") + 1].split(";"):
            ex = json.load(open(path))
            for h, t in ex.get("txs", {}).items():
                txs.setdefault(h, t)
            for a, f in ex.get("funding", {}).items():
                # A `funder=None` row is a *measurement* (both histories walked
                # to the end, nothing incoming), not a gap — keep it, so
                # coverage accounting is honest.  It draws no edges either way.
                funding.setdefault(a, f)
        ds = Dataset.from_events(cache["events"], cache["first_deposits"], txs=txs, funding=funding)
        nofund = sum(1 for f in ds.funding.values() if not f.funder)
        print(f"enrichment extended: txs {n0[0]}→{len(ds.txs)} funding {n0[1]}→{len(ds.funding)} (funder=None {nofund})")
    cfg = preset.detect_config()
    extra = build_extra(ds, cache)
    infra_extra = frozenset()
    if "--infra" in argv:
        p = argv[argv.index("--infra") + 1]
        infra_extra = frozenset(a.lower() for a in json.load(open(p)))
        print(f"infra_extra: {len(infra_extra)} funders")
    out = {}
    names = argv[argv.index("--only") + 1].split(";") if "--only" in argv else list(VARIANTS)
    for name in names:
        rules = replace(VARIANTS[name], infra_extra=infra_extra) if infra_extra else VARIANTS[name]
        clusters, all_edges, firsts, counts = run(ds, cfg, rules)
        m = metrics(clusters, ds, preset, ens, extra)
        out[name] = m
        fw = " ".join(f"{k}={a}/{b}" for k, (a, b) in m["farm_windows"].items())
        print(f"{name:42s} clusters={m['clusters']:4d} flagged={m['flagged']:6d} periph={m['periphery']:5d} pts={m['points_pct']:5.1f}% lab={m['labeled_recall']} whole={m['operators_whole']} ens={m['ens_flagged']:4d} ctrl={m['controls_flagged']:2d} resc={m['rescuers_flagged']:2d} idmd={m['idmd_flagged']:2d} ladder={m['ladderers_flagged']:3d}")
        print(f"      farm windows: {fw}")
    json.dump(out, open(f"{SCRATCH}/v2_variants.json", "w"), indent=1, default=str)
    if "--diff" in argv:
        name = argv[argv.index("--diff") + 1]
        rules = replace(VARIANTS[name], infra_extra=infra_extra) if infra_extra else VARIANTS[name]
        dump_diff(name, rules, ds, cfg, preset, ens, extra, cache)


if __name__ == "__main__":
    main(sys.argv)
