# AGENT card labels and premium usage

2026-10-13. Tier 2: EFFORT gains primitive data-contract fields. The user has
specified the four visual changes; no new dashboard or interaction is needed.
Expected production diff is below 1,000 lines, so there are no package reviews
and exactly one final review. Preserve the existing twelve-card rack.

## Required behavior

| Card | Change |
| --- | --- |
| STATUS | Render the static `0F` separator with a foreground equal to the effective outer card background. Apply this to tall digits and compact/unknown fallback. Keep the inset background, active-slot/capacity digits, and meter unchanged. |
| SEAT | Change the inner title from `IDMD` to `Identity.md`. |
| RANK | A zero or unknown movement has no outer footer text. Positive and negative movements retain their arrows, counts, and colors. |
| EFFORT | Replace `CONTRIBUTORS` with `x% premium`, calculated from actual recorded use of Astra, Opus, or Fable. Preserve hours, token totals, and neutral border. |

## Evidence and metric semantics

The existing contributor endpoint exposes per-device counters, hours, and
tokens, but no model usage breakdown. The selected seat's lifetime `work[]`
contains submission identities, without actual model names. Its advertised
`runtimes[].premiumModel` is configuration and cannot establish past usage.
Actual models already reach `swarm_seat_work_rows` through exact submission
answer-cache enrichment. `submission_answer` obtains them from `usage.model`;
both `read` and `no_reply` states can contain valid model evidence.

Answer hydration is bounded by the displayed record window and existing cache
limits. Consequently, current data can establish the share among work entries
whose actual model is known, with explicit coverage; it cannot establish an
exact lifetime share when some submissions remain unread. The user explicitly
chose the known-model share with coverage on hover. The EFFORT tooltip therefore
states the sampling basis and counts; the visible percentage does not claim a
complete lifetime model breakdown.

The denominator uses all enriched rows available for the selected seat, before
table filtering or viewport slicing. One source `work[]` entry is one work
attempt, matching RECORD and the existing attempt counters. Different work
entries for the same job remain distinct; never deduplicate by job ID. Do not
invent a new receipt/attempt reconciliation or count advertised models.

Premium classification is case-insensitive and matches the family names
`astra`, `opus`, or `fable` as model-name tokens, including provider prefixes
and version suffixes. Arbitrary substrings such as `notopus` are not premium.
Known other model families count in the denominator, while missing or invalid
model evidence does not. Do not add endpoints, polling fan-out, or eager
hydration of the complete work history for this metric.

## Frozen contract

Append these fields to `SURF_AGENT_HERO_FIELDS['effort']`:

| Field | Type | Meaning |
| --- | --- | --- |
| `premium_percent` | `float \| None` | `100 * premium_jobs / model_jobs`, or `None` when the denominator is zero/unavailable. |
| `premium_jobs` | `int \| None` | Known-model work entries using a premium family. |
| `model_jobs` | `int \| None` | Work entries with a nonblank string model and answer state `read` or `no_reply`. |
| `work_jobs` | `int \| None` | All selected-seat work rows in the served list. |

Selected detail must be available (`ok`, `partial`, or retained `stale`) and
the rows must be a list. Otherwise all four values are `None`. A served empty
list produces counts `0, 0, 0`, with percentage `None`. A nonempty list with no
known models produces `0, 0, N`, with percentage `None`. Missing data never
becomes `0%`. These facts are independent of contributor availability; preserve
the existing contributor clocks and state for hours/tokens. Historical model
usage is tied to validated exact submissions; no new read clock is necessary.

Use the existing percentage formatting style for the visible footer and
`--% premium` when there is no known-model denominator. The tooltip states
premium attempts, known-model attempts, and total recorded attempts, making
incomplete coverage clear without presenting the subset as a lifetime total.

## Work packages and ownership

1. **Planner** owns this document only. Freeze the contract and evidence before
   implementation. No code changes or subagents.
2. **Controller** owns `data/surf_models.py`, `data/surf_agent_hero.py`, the
   matching data/contract fixtures and tests, and any required manager or
   composing screen adjustments. Add failing tests for the frozen semantics,
   then implement the smallest pure projection. No new network path.
3. **UI implementer or controller** owns `widgets/surf/agent_rack_hero.py` and
   its widget tests. Add composited assertions for all four changes, including
   fallback separator color and coverage tooltip. Starts after the contract is
   frozen and may proceed beside package 2 only with disjoint file ownership.
4. **Controller** integrates, shows the real keyless native render at 149×45,
   checks layout boundaries if geometry changes, updates the followups record,
   runs scoped final checks, and coordinates the single final review and local
   commit. No push is requested.

All implementers share the tree and preserve others' changes. Report findings
outside owned files rather than editing them. No agent spawns another agent.

## Verification and delivery

- Pure projection: mixed Astra/Opus/Fable and other families; case/provider/
  version variants; false substring matches; same job with distinct attempts;
  `read` and `no_reply`; missing/invalid models; empty/missing rows; pending,
  unavailable, retained detail; contributor/source isolation; no input mutation.
- UI: exact `Identity.md`; rank zero and unknown leave a blank footer; positive
  and negative movements remain; tall and compact `0F` foreground equals the
  outer background; premium percentage/unknown footer and truthful coverage.
- Native live render at 149×45 precedes layout hardening, completion documents,
  and reviewer dispatch. Preserve current 132×29 AGENT pin unless native
  measurement proves a change. Use the project's layout measurement path.
- While editing, run changed cases only. Before commit, run touched and
  composing test files once, fast guards, and doc pins using the project venv.
  Tests stay offline. No full suite or unrelated registration checks.
- Use `scripts/mutate.py` to prove the model-classification/denominator tests
  catch the corresponding defects; restore byte-for-byte. No checkout/reset.
- One final whole-change review, one fix wave, and one scoped re-review only
  when a review fix changes production code. File Minor findings. Record the
  result and actual test evidence in the final commit/report.
