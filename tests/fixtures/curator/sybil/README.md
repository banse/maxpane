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
| `operator_row_worst.json` | the OPERATORS panel payload — `worst_cluster` + `worst` (the row to size against, which **is** its own entry in `rows`) + all 16 rows | `cluster_economics.json` (+ the shape/fingerprint/funding files for the reason strings) |
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

## Read the envelope, not just `rows`

Each slice is an **envelope**, and the two widest payloads in the set live
*outside* its `rows` list. Size columns with
`tests/curator_sybil_fixtures.worst_case_envelope()` / `row_payloads()`, never
with `worst_case_rows()` alone.

| what | max | where it is |
|---|---|---|
| operator reason string | **53** | `rows` — an index-run operator, *not* `worst`, whose own longest phrase is only 45 |
| reasons per row / joined length | 4 / 150 | `rows` ∪ `worst` |
| segment `label` | 33 | `rows` |
| segment `detail` | **56** | `degraded_row`, outside `rows`; `rows` alone stops at 44 |
| clean-list `name` / `address` | 12 (`NAME_COLS`) / 42 | `rows` |

Both maxima above were wrong when measured on a partial view, which is the
`dev`/`ops` defect CLAUDE.md records — a cell simultaneously padded for one row
and cutting another mid-word, with both suites green. They are pinned in
`tests/data/test_curator_sybil_data.py::test_the_widest_strings_the_analysis_panels_must_fit`
and restated in the hand-off block in `data/curator_models.py`.

`worst` is **the same object** as its entry in `rows` (`worst_cluster` names
which operator). It was not, at first: the generated row for the 0.45 operator
named the same-amount window while `worst` named the consecutive-index run.
Both are real evidence about that cluster, but two lists for one operator is how
WP4 sizes against one and WP3 produces the other with both suites green.

## The synthetic ledger

The three `*_worst.json` files each carry, in a top-level `synthetic` field, the
literal

```
SYNTHETIC — calibrated from docs/curator_sybil_data/, re-point at a live analysis bundle
```

so `rg "SYNTHETIC —"` stays the whole checklist. They are *shaped* payloads: the
numbers are measured, but no live analysis sweep had ever produced a row in this
schema at the time they were written, because WP3 did not exist yet.

**WP6 close-out (2026-08-18): the three markers stay, and they are now
permanent.** WP3 exists and the live sweep does produce rows in this schema, so
the sentence this paragraph used to end with — "re-point them at a real bundle
and drop the marker" — is retired. Two reasons, and the second is the one that
matters:

1. These are **worst-case envelopes**, not snapshots. WP4 and WP5 pin column
   widths against them. A live bundle is one sample of a population that moves
   every hour, so re-pointing the width pins at one would calibrate the layout to
   whatever the list looked like that afternoon — the exact mistake CLAUDE.md
   records for the surf market panel's IMD/FP peg, where a width measured against
   a 2.75% spread was a column short the moment the peg got healthy. The 56-column
   `degraded_row` detail and the 12-character name probe exist precisely because
   no single live bundle is guaranteed to contain them.
2. The numbers already *are* live reads. `docs/curator_sybil_data/` is the
   2026-08-17 sweep of the real population, and `tests/data/test_curator_sybil_data.py`
   re-derives every value in these files straight from it. "SYNTHETIC" here means
   *shaped into the panel's schema by hand*, not *invented* — which is why
   `labeled_subset.json`, joined from the same archive without reshaping, carries
   no marker at all.

The marker literal is deliberately unchanged rather than reworded to
`SYNTHETIC — permanent`: `tests/curator_sybil_fixtures.SYNTHETIC_MARKER` and
`test_the_synthetic_slices_are_marked_and_the_measured_one_is_not` both pin the
exact string, and a doc close-out is not a reason to move a pinned literal in
three files. `rg "SYNTHETIC —"` still finds all three, which is the property the
ledger was built for.

The 33 `SYNTHETIC — re-point` markers elsewhere under `tests/` are a **different
generation** — the base curator build's, closed by that build's WP7.13 against
the live capture bundles — and are none of this build's business. `sybilkit/tests/`
carries no marker of either generation.

`labeled_subset.json` deliberately carries **no** marker. Every byte of it is
measured data — joined across five files, never invented.

Two rows in the set are the exception to "everything is derived", and both say
so in their own file's `note`:

* `segment_rows_worst.json` → `degraded_row` — a band whose `points_share_pct`
  is `null`. The data *has* that share; the row exists so WP4 can pin that a
  `None` renders as unknown and never as `0.0%`. It is also the widest string
  in the whole set (56 columns), so a sweep that skips it under-sizes the
  `detail` column by twelve.
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
