# `tests/fixtures/curator/sybil/` — the linked-wallet analysis fixtures

Committed by **WP0** of the curator sybil / fan-out build
(`docs/curator_sybil_PRD.md`, `docs/curator_sybil_implementation_plan.md`).
Read through `tests/curator_sybil_fixtures.py` — never by a hand-rolled path.
**Read-only.** Nothing regenerates these; a test that rewrote one would turn the
provenance into whatever made the suite green that afternoon.

All of it is derived from `docs/curator_sybil_data/`, the 2026-08-17 19:44:40 UTC
research sweep (latest block 25 776 962, 22 319 deposits, 15 576 contributors,
not yet settled). Nothing here touches the network.

| file | what it is | derived from |
|---|---|---|
| `labeled_subset.json` | the benchmark subset: 16 audited operators × 10 sampled members + 60 controls, each with deposits, join index, tx fingerprint and funder | `suspects.json` + `tx_fingerprints.json` + `funding.json` + `deposits.json.gz` + `first_deposits.json.gz` + `same_amount_clusters.json` + `index_runs.json` |
| `operator_row_worst.json` | the OPERATORS panel payload — `worst` (the row to size against) + all 16 rows | `cluster_economics.json` (+ the shape/fingerprint/funding files for the reason strings) |
| `segment_rows_worst.json` | the SEGMENTS panel payload — 12 derived bands + one explicit unavailable row | `whales_segments.json`, `population.json`, `deposits.json.gz` |
| `clean_list_rows_worst.json` | the CLEANED LIST payload — top 20 survivors + totals + a name-width probe | `deposits.json.gz`, `cluster_economics.json` |

## Why "worst case" and not a toy row

WP4 and WP5 pin their widths against these rows **before WP3's adapter exists**.
A toy row would calibrate the layout to a state the data is never in — the
IMD/FP-peg lesson in CLAUDE.md, where a width measured against a 2.75% spread
was one column short the moment the peg got healthy. The widest real operator is
**1 995 wallets holding 6.81% of all points at a 44.6× sqrt subsidy**, its
reason list deliberately over-provisioned to four pattern-language phrases
(implementation plan §6 risk 6), and that is what the columns have to fit.

## The synthetic ledger

The three `*_worst.json` files each carry, in a top-level `synthetic` field, the
literal

```
SYNTHETIC — calibrated from docs/curator_sybil_data/, re-point at a live analysis bundle
```

so `rg "SYNTHETIC —"` stays the whole checklist. They are *shaped* payloads: the
numbers are measured, but no live analysis sweep has ever produced a row in this
schema, because WP3 has not been written. When it has, re-point them at a real
bundle and drop the marker.

`labeled_subset.json` deliberately carries **no** marker. Every byte of it is
measured data — joined across five files, never invented.

Two rows in the set are the exception to "everything is derived", and both say
so in their own file's `note`:

* `segment_rows_worst.json` → `degraded_row` — a band whose `points_share_pct`
  is `null`. The data *has* that share; the row exists so WP4 can pin that a
  `None` renders as unknown and never as `0.0%`.
* `clean_list_rows_worst.json` → the last row of `rows`, a synthetic
  `0xff…ff` address carrying `surfsurf.eth` (exactly `NAME_COLS` = 12
  characters). Every real address in the file has `name: null`, because no
  reverse ENS has been resolved for any of them and attributing one would be a
  fabricated fact. The probe exists so the name cell can be measured at its
  widest without inventing an identity.

## What is pinned where

`tests/data/test_curator_sybil_data.py` re-derives every number in these files
straight from `docs/curator_sybil_data/` — including recomputing the whole
population's points wei-exactly (`isqrt(weight) * 1000 // 10**9`) and matching
`population.json` to the digit. So the fixtures are provable without the
one-shot script that wrote them, and that script is deliberately not committed.

## The mirror

`labeled_subset.json` is **byte-identical** to
`sybilkit/tests/fixtures/labeled_subset.json`. PRD §8 requires both
distributions to gate on the same evidence; a test asserts the two copies agree,
so they cannot drift into two convenient subsets.
