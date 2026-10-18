# WORKFLOWS documentation atlas: source research

Date: 2026-10-18. Source: the owner's `aidude/docs/swarm-workflows.html`,
read from `/Library/Vibes/aidude/docs/swarm-workflows.html` during design.
This path is a research input, never an installed application's dependency.

The source describes IMD workflows as measured for Sworn on **2026-10-18**,
plane **745c1db4**, worker **0.1.2**. Its footer cites
`docs/imd-api-changelog.md`, job records `c3792acf` and `53f5fb2b`, oracle
requests `cb72b826`, `4ee4290d`, `03ccc51e`, `fa460b4b`, worker `dist/cli.js`,
and `Identity-md/worker#6`. These references are attribution, not independently
verified sources. No live API was queried for this atlas.

## Ten documented topics

| ID | Source section | Required content and branches |
| --- | --- | --- |
| `purchase` | 01 Buying any action by x402 | Free check, quote, two signatures, submit, settlement, admission. Quote 600 s; Permit2 deadline 300 s; settlement 3 confirmations. Example 07:48:46 to 07:51:33. Blocked work does not recover the documented 0.5 IMD charge. |
| `single_skill` | 02 A single-skill job | Dispatch eligible seat, work, verification, accepted/failed verdict, delivery. Failure re-dispatches; maximum three attempts then blocked. `job.open` and templates are documentation terms. Objective 1–8,000 chars, references ≤8, paths ≤16, repo ≤100/200 MB as written; the source does not define the two repo-size categories. |
| `shapes` | 03 The three step shapes | All three shapes: chain; parallel components followed by `integrate-project`; DAG with explicit dependencies. Workers merge accepted bundles at joins. One to six authored steps; each step text ≤3,000 chars; rendered objective plus step ≤8,000; complete request ≤16 KiB. |
| `contracts` | 04 Contracts-only launch | Imported-code audit, adaptation, tests, manifest, four audit disciplines, judge, attested factory deployment, live repository. Blocking finding leaves contracts undeployed. One to eight contracts; atomic transaction; no token. Example #2147 paid 07:48, live 08:26, body 6,071 chars. |
| `site` | 05 Site continuation, and where it broke today | Build, content check, docs, plane design critic, hosting. Historical failure: check produced no bundle; docs restarted from base; merge conflicted on README.md and DESIGN.md; `clone_failed` three times, blocked, nothing hosted. Documented remedy: direct build→docs dependency or build writes README. Example job 53f5fb2b; plan B 7,672/8,000 chars and 16,243/16,384 bytes. |
| `company` | 06 Company workflow | Contracts, deployment, frontend consuming deployment.json, IPFS/ENS publishing, validation up to one day. No pause for the payer's own post-deploy checks. Existing parentJobId refused; completed/blocked work can be continued. Combined request/context/draft ≤8,000 despite request field ≤16,000; one website step last and one adversarial review. |
| `oracle` | 07 Oracle round trip | Request transaction, admission, panel, computation/attestation, writer callback, Registry validation, stored or Missed(reason). Historical reason 5 below quorum, reason 8 rule false; third attempt stored. Consumer sets panel/quorum: illustrated 5/3, Registry panel evidence 11/7. Typed bool/uint256/address[]; Sworn Registry ≤64 addresses, 2,112 bytes. |
| `intake` | 08 Onchain Intake states | received→paid→admitted→completing→completed; refusal from received, failure from admitted in the drawn edges. Literal errors unknown_action, wrong_asset, short_payment, body_*. Intake v2 request and result/status endpoints are explanations only. Three confirmations before admission, no x402/request token. |
| `schedules` | 09 A schedule's runs | Creation and prepaid runs, cadence slot, opened/spent or skipped while previous run is in flight or failed/unspent. Three consecutive failures pause; exhausted/topup; after outage one late run plus missedSlots. No queued slots; cadence PT11M through P1D. |
| `growth` | 10 How a project grows | Launch→site continuation→fix→feature→further continuation. Same payer/label/history; parentJobId is latest job; ipfs:true retains label. Blocked job is continued, not resumed. Fresh job.open creates a new project. Start-tree merge cleanliness remains an explicit open question in the historical source. |

Global header figures are historical: 8,000 chars per rendered step, 3,000 per
step text, 1–6 steps, 16 KiB request body, 8,000 combined company input, and
0.5 IMD per paid action. Do not turn them into current prices, runtime quotas,
live counters, guaranteed timings, or a schedule's total prepaid cost.

## Source ambiguities retained as provenance

- Section 01 calls Intake “09”; the actual Intake section is 08. Atlas navigation
  uses the real section ID; verbatim excerpts retain the original text.
- Section 03's explicit dependency caption describes build→docs, while its
  dashed SVG edge ends at the tests rectangle. Explain the caption's intended
  dependency and disclose the source discrepancy in topic detail.
- Section 08's accessible summary says refused/failed branch after received;
  its actual edges put refused after received and failed after admitted. Follow
  the drawn edges and retain this discrepancy in detail.
- The company sample reports 70 completed and 29 blocked among 100. Do not
  invent the remaining row's state or call these current/global statistics.
- Contracts-only annotations say “your 3 steps,” while node styling and labels
  are not a reliable authored-step count. Distinguish diagram nodes from job
  steps; quote the source's counts rather than derive them from boxes.

## Existing MaxPane behavior verified in code

`widgets/surf/swarm_workflows.py` is a retained execution-history table, not
this atlas. Its current cap is 1,000, and selecting a row opens
`WorkflowDetailScreen`. Old 12-row and throughput-fold plans are historical.
`w` opens WORK IN PROGRESS; `b` is leaderboard; `x` on SWARM opens the latest
production launch snapshot. These meanings remain.

`SurfboardScreen` has a centered IMD BOARDROOM title, six rack columns, arrow/
Enter card navigation and a shared footer. `g` is absent from its bindings and
the application's q/t/tab/m bindings. It must remain ordinary text inside the
boardroom command and seat inputs. No new top-level game is needed.

`DashboardScreen` currently schedules non-ReaderHandle managers unconditionally;
a small default-on polling capability is required for this static screen.
`RecordDetailScreen` already provides a cached snapshot, scrolling sections,
clickable X and Space/Escape close. Its subclass can render source excerpts.
Latest footer conventions retain centered loading and app context, without
shortcut/poll/freshness clutter. Static content requires no network reader.
