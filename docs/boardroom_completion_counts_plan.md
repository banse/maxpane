# Boardroom completion counts and reload retention

Approved scope: the owner's 2026-11-11 request. Tier 2 because the normalized
overview contract gains two fields. One package, implemented by the root
session; expected under 200 production lines, one final review, no task reviews.

## Result and source contract

- SHIPPED has inner heading LAUNCHES and displays `/swarm.counts.launchesLive`.
  Its inner footer counts successfully completed workflows (`completed` plus
  `superseded`) from the existing full certified workflow catalogue. Replacing
  a completed release does not erase its completion. The 24H meter stays intact.
- WIP retains its executing-job digits and open-workflow outer footer. Its inner
  footer is `x working`, counting distinct busy seats in the complete `/swarm`
  seat map. It does not count node types, work items, or daemon devices.
- Add nullable nonnegative integer `launches_live` and `working_seats` to
  `SURFBOARD_OVERVIEW_FIELDS`. Missing or malformed optional facts stay unknown;
  other valid overview facts survive. Migrate old hash-validated cached
  overviews with those fields unknown and preserve original source clocks.
- `SurfCardReader` retains completed and open workflow counts together only
  after a complete, recognized-lifecycle catalogue read, with their source time.
- Cards keep valid digits, numeric captions and footers through incomplete,
  failed or loading observations. Actual zero replaces prior data. Identity
  changes still clear the affected seat's display memory. Unknown first-load
  digits remain blank; display memory never modifies source facts.

## Ownership and sequence

Root owns the whole package. Freeze/decode `data/surf_models.py` and
`data/surfboard.py`, then publish completion facts in `data/surf_card_reader.py`,
then update `widgets/surfboard/rack.py`. Use existing network reads and
`CardValues`; no endpoint, shared-widget or manager orchestration changes.

Write regression checks in the corresponding data/rack tests first. Use the
committed overview/workflow fixtures and a catalogue-owner stub. Check actual
composited values, independent zero updates, unknown reloads, source immutability
and identity reset. Mutations cover wrong sources, partial catalogue acceptance,
superseded omission and retention bypass. Existing unrelated reader harness
failures are identified against unchanged HEAD and filed, not folded into scope.

Show a public-data render at 149×45 before layout certification, docs evidence
or review. Check the rack boundary and long captions; retain the measured pin
unless evidence moves it. Run touched and composing test files once, fast guards
and documentation pins. One final review with at most two fix rounds per the
architectural tier; commit exact paths, no push or full suite.

## Source evidence

Official `https://imd.fun/docs/llms.txt`, read 2026-11-11: workflow completion
requires site validation; a completed release later replaced becomes superseded.
The public `/swarm` capture had 938 live launches, 20 working daemons and 21 busy
seats. These are dated observations, never implementation constants. The full
seat map is the existing research roster source; busy flags report assignments,
not proof of a running model process.

## Verification

The public-data 149×45 render showed 939 launches, 163 completed workflows,
4 executing jobs and 15 busy seats. Shown before layout certification; captured
at `/tmp/boardroom-counts-live.{json,svg,png}`. The measured 143×37 pin is unchanged:
eleven boundary samples cover 110–160 columns and 25–55 rows, including the
one-column scrollbar cost on short terminals. Screen-refresh tests also pass
at 143×37 and 149×45.

Six mutations were killed and restored: wrong launch source, all seats counted
as busy, partial catalogue accepted, superseded completions omitted, digits
cleared during reload, and real zero ignored. Initial focused checks: 45 passed;
refresh checks: 7 passed. Touched and composing files: 647 passed and 85 failed;
77 failures also reproduce on unchanged `66cc5126` in an isolated archive.
The remaining eight were obsolete expectations for changed behavior; after
updating them, all 33 selected correction/decoder/refresh checks pass. No new
production failure remains identified. Fast guards: 130 passed and one existing
TOKENS/SWORN stylesheet-slice failure. Documentation pins: 12 passed. The full
suite was not run. Residual groups are recorded in `surfboard_followups.md`.

Final review: Approved, no findings. Five independently selected checks passed;
the reviewer also killed a cache-hash bypass mutation and restored the tree
byte for byte. IMDb recorded `none`: the change applies existing protocol facts
and introduces no new protocol lesson.
