# The IMD swarm: what the explorer shows and what its API serves

Research for a surf body on <https://explorer.imd.fun/>. Every number and shape below was measured on
**2026-09-16** unless a later dated capture is explicitly named, not taken from documentation: <https://www.imd.fun/docs/> says "protocol overview, agent
architecture and integration guides coming soon" and documents no endpoint at all.

## What the explorer is

A Next.js app over an agent swarm that takes a written request, breaks it into subtasks, dispatches them to
agents, reviews the result, and sometimes deploys a contract or publishes a website. Its pages are **Harness**
("What the swarm is doing right now"), **Jobs**, **Launches**, **Reviews** ("What the swarm has been scored,
onchain"), **Sites** and **Find**.

The explorer renders server-side and calls its control plane from the server, so the browser never sees the API.
The host is named in the page anyway, because agent avatars load from it:

```
https://identitymdcontrol-plane-production.up.railway.app
```

## The control plane

Keyless. No key, token, cookie or signature was sent for any read below, and every one answered 200. Its
`/health` reports `"operatorSurface": "authenticated"`, so the write surface is closed and the reads here are
the public subset.

| Route | Result | Size |
|---|---|---|
| `GET /health` | swarm counters and the identity contracts | 567 B |
| `GET /jobs` | the newest 100 jobs, newest first; `count` is the page length, not a total; no pagination; parameters ignored (2026-09-21). On 2026-09-16 it read as every job: 62 | 27.5 KB (62 jobs, 2026-09-16); 43.1 KB (100, 2026-09-21) |
| `GET /contributors` | per-device lifetime counters; aggregate by token (2026-09-22) | 32,113 B |
| `GET /workers` | live devices, capacity, pauses and runtime metadata (2026-09-22) | 97,420 B |
| `GET /seats/{tokenId}` | one seat's lifetime record (measured 2026-09-21; see [`/seats/{tokenId}`](#seatstokenid)) | 6–90 KB |
| `GET /jobs/{id}` | one job with its subtasks, verdicts and review | 2.2 KB typical, 9.2 KB worst |
| `GET /launches` | deployments with every contract address | 10.1 KB (16) |
| `GET /sites` | published IPFS sites with their ENS names | 2.3 KB (4) |
| `GET /jobs/summary` | **500**, a broken query the server admits to | — |
| everything else tried | 404 | — |

404 on: `/`, `/agents`, `/agents/1`, `/agents/by-token/1`, `/harness`, `/harness/state`, `/reviews`, `/scores`,
`/attestations`, `/receipts`, `/deliveries`, `/enrollments`, `/identity`, `/verifications`, `/feedback`, `/work`,
`/activity`, `/moves`, `/field`, `/leaderboard`, `/inference`, `/tokens`, `/operators`, `/swarm`, `/metrics`,
`/queue`, `/daemons`, `/pairs`, `/status`, `/public`, `/v1/jobs`, `/api/jobs`, `/openapi.json`, `/docs`.
The explorer's own origin serves no `/api/*` route either. (`/seats` was on this list on 2026-09-16; the bare
route is still 404, but `/seats/{tokenId}` answers — see below.)

**No filters.** `?state=executing`, `?limit=3` and `?since=…` all return the same 62 rows, so the list is
all-or-nothing. **Re-measured 2026-09-21 on `https://api.imd.fun`:** `/jobs` returns `count: 100` and exactly
100 rows — the newest 100 jobs (that capture spans `createdAt` 02:26–05:44 UTC, about 3.3 h), with no page
parameter and no older page. The 2026-09-16 reading of "every job" was true only while fewer than 100 existed;
a fold over `/jobs` is a window, never a total (`tests/fixtures/surf/swarm/seats/jobs_window_100.json`). **No caching headers**: no `cache-control`, `etag`, `age` or `last-modified`, so a conditional
request is not available either.

**No rate limiting observed.** 62 sequential detail fetches spaced 120 ms apart: 62 × 200, 188.3 KB, 24.9 s.

### `/health`

```
status version operatorSurface identity{chainId collection adapter} taskNetwork connectedDaemons
workingNow acceptedLastDay activeEnrollments pendingVerification pendingAttestation pendingDeployment
deployBreaker pendingDelivery pendingFeedback pendingFuzz pendingSites lotusTargets verifierUp
publisherUp deployerUp
```

Measured: `connectedDaemons 2`, `activeEnrollments 3`, `workingNow 0`, `acceptedLastDay 13`, every `pending*` 0,
`verifierUp`/`publisherUp`/`deployerUp` all true, `deployBreaker null`. The explorer's "Agents online: 2 of 3
paired" is `connectedDaemons` over `activeEnrollments`.

### `/jobs`

Per row: `id state template objective blockedReason delivery createdAt updatedAt`. **No agent, no subtasks, no
scores** — those exist only in the detail.

Measured spread: `completed 43`, `cancelled 11`, `blocked 6`, `executing 2`; templates `shape:chain 18`,
`skill:scaffold-project 13`, `impl_tests_review 10`, `skill:research-report 6`, `single 6`, `impl_tests 4`,
`skill:build-website 2`, `skill:build-contract-project 2`, `skill:implement-and-test 1`. 14 jobs moved in the
last day, 21 in the last week. 20 of 62 carry a delivery. Objectives are user-written text, median 156 and max
159 characters in this capture, containing newlines and punctuation.

`blockedReason` reads like `node build: budget_exhausted`, `node review: attempts_exhausted`,
`node build_dapp: runtime_error`, or `cancelled by operator`.

### `/jobs/{id}`

Adds `deliver host site launch{requested kind id status chainId} delivery{repoUrl pullRequestUrl commit
deliveredAt} nodes[] reviews[]`.

A node is one subtask:

```
key role state attempt revisions dependsOn allowedPaths failureReason
dispatchNote dispatchNoteAt updatedAt verdict seat
```

`seat` is the agent that holds it — `{"tokenId": "2", "agentId": "10303"}`, the explorer's "#2". `verdict` is the
verifier's own record: `status`, `evaluation`, `rejectionCode`, a prose `detail`, `verifierVersion`,
`verifiedTreeHash`, `at`, `failedChecks`. `dispatchNote` explains a stall in the swarm's own words, e.g. *"a
review needs a contributor who did not author this work"*.

A review is the onchain score:

```json
{"status": "sent", "chainId": 11155111, "txHash": "0x83707e…", "blockNumber": 11714363,
 "sentAt": "2026-09-16T04:06:52.401Z",
 "entries": [{"nodeKey": "build_website", "agentId": "10303", "value": 100, "role": "implement"}]}
```

The explorer explains the scale: 100 when work is accepted first time, falling with each revision, 0 for a
rejection, written once when the job ends, into the agent's ERC-8004 registration.

### `/seats/{tokenId}`

Measured **2026-09-21** on `https://api.imd.fun`, keyless GET, on 8 seats (6–90 KB; #0 is the largest, 202
reviews). It is what the explorer's seat page renders ("12 of 74 attempts accepted", "72 scored" for #420).
Committed captures: `tests/fixtures/surf/swarm/seats/` (#420, #0, #1649, #516, the 404 and 400 bodies; its
`MANIFEST.json` records what is and is not known about each).

| field | meaning (as measured) |
|---|---|
| `tokenId`, `agentId`, `chainId` (1), `collection`, `adapter` | the IDMD seat and its ERC-8004 agent |
| `status` (`active`), `ownership` (`owned`), `owner` (0x…), `pairedAt`, `online` (bool) | the seat's pairing |
| `daemonVersion`, `runtimes[] {id, version}`, `devices` | what runs it |
| `attempts`, `accepted` | lifetime counters; `accepted == len(work)` on all 8 seats |
| `work[] {jobId, objective, jobState, launch, nodeKey, role, submissionHash, acceptedAt}` | every accepted submission, newest first |
| `reviews[] {jobId, nodeKey, role, value, policy, verdict, submissionHash, status, txHash, chainId, sentAt}` | every scored submission, newest first; one per job |
| `collaborators[] {tokenId, agentId, sharedJobs}` | seats it shared jobs with |

The seat-details view uses fields already present in these **2026-09-21 committed captures**;
this is a description of those captures, not a new live measurement:

- `daemonVersion: null` on seat #0 means the daemon version was not reported. The fold preserves
  it as an empty string, distinct from an absent or invalid field (`None`, unavailable).
- `collaborators[]` supplies TEAMMATES, ordered by `sharedJobs` descending and token ascending.
  `tokenId` accepts strict decimal strings or nonnegative integers; malformed entries are dropped.
  An empty list means no teammates yet; a missing or invalid list means unavailable.
- Nine rows of seat #0's `work[]` carry `launch` (`evm_project`); a null launch is a real absence
  and displays `—`. Text values use the shared widget sanitiser.
- `work[].submissionHash` is an off-chain identifier. The fold accepts exactly 64 hex characters;
  RECORD shows its first eight characters as plain text, with no blockchain explorer link.

The lifetime ACCEPT RATE is `accepted / attempts`; zero attempts has no defined rate. BY NODE instead
uses accepted work divided by reviewed work for that node, since this route does not serve attempts
per node. It includes nodes found only in `work[]`, with zero reviewed. A transaction in `sent` or
`submitted` state counts toward the node's `chain` column; queued reviews do not. The latest
`work[].acceptedAt` is the last accepted-work timestamp; the latest `reviews[].sentAt` is feedback delivery time.
Neither timestamp establishes the seat's last attempt, which the route does not serve.

`reviews[].status` takes three values:

- `sent` — `txHash` and `sentAt` set;
- `submitted` — `txHash` set, **no** `sentAt`;
- `queued` — neither, and `chainId` null.

No `blockNumber` anywhere. `reviews[].verdict` was `accepted` and `value` `1` on all 566 reviews read, so
review-accepted is not `accepted`: #420 has 72 reviews (66 sent, 5 submitted, 1 queued) and 12 accepted of 74
attempts. **Not served in these 2026-09-21 captures:** rejections, revisions, rejection codes,
failed checks, verifier detail, "working now". The 2026-09-22 capture below serves rejected/pending
counters again; that historical observation no longer describes the current corpus.

Errors:

- `404 {"error":"unknown_seat","detail":"no device has paired with that token"}` for a token never paired — a
  real negative, not a failed read.
- `400 {"error":"invalid_request","detail":"expected a decimal token id"}` for a non-decimal id.
- `/seats` with no id is `404 {"message":"Route GET:/seats not found",…}`: there is no seat list.

A competitive job's detail (`/jobs/{id}`, e.g. `oracle_assess` on `80c853bd`) lists only the winning node while
its review scores every seat that attempted it, so the job window cannot reconstruct a seat's attempts;
`/seats/{tokenId}` was the lifetime source used for that view. The later `/contributors` capture
also serves lifetime counters, with its own read time and totals (see below).

### `/launches` and `/sites`

A launch carries `launchNumber kind status chainId sourceRepoUrl sourceCommit parkedReason artifactCount
artifacts[] createdAt updatedAt`, and each artifact is `{role name address txHash blockNumber}` — real contract
addresses with the transaction that deployed them. Measured: `abandoned 10`, `live 5`, `parked 1`;
`univ4_hook 13`, `evm_project 3`.

A site carries `jobId status label cid bytes ensName txHash blockNumber attempts failure pinnedAt namedAt
supersededBy supersededAt`, e.g. `site-7018907b.site.identitymd.eth` over
`bafybeigicvgrkurqm2mmpq7ar7jxdylycscnisdatwd2irigy7mkayprla`.

## Which chain

`/health` reports `chainId 11155111` — **Sepolia** — with identity collection
`0xa0443799c320e16c80801c9c1911f3571260287f` (3,855 bytes of code) and adapter
`0x7621630cb63a73a194f45a3e6801b8c6a7ec2f92` (163 bytes, so a proxy or a shim). Review transactions are Sepolia
too. Launches are mostly Sepolia, and the abandoned ones are mainnet, so **a panel that shows an address has to
name its chain**.

Neither identity address emitted a log in the 5,000 Sepolia blocks below head 11,718,295, so the ERC-8004 score
writes land somewhere else. The registry address is recoverable from a review transaction's receipt; this
research did not chase it, and nothing in the planned view depends on it.

## What is **not** available

- **"Inference contributed: 556.3M tokens."** The explorer's own headline. No public route serves it, and it is
  not derivable from anything that is. It stays off the dashboard.
- **Per-agent identity beyond a number.** `seat` gives a token id and an ERC-8004 id; there is no public route
  for an agent's name, skills or history. (Superseded 2026-09-21 for history: `/seats/{tokenId}` serves a seat's
  lifetime work and reviews; still no name or skills.) The avatar SVG at `/agents/by-token/{n}.svg` is an image, not data.
- **Reviewer attribution.** A review says which agent was *scored*, never which agent reviewed.
- **Anything signed.** Nothing the host serves is signed or hashed. The review `txHash` is the only claim that
  can be checked against a chain.

## Consequences for a dashboard

1. **The live picture costs 567 bytes**, and the 27.5 KB list only has to be re-read when a `/health` counter
   moves. Job details are needed only for jobs that are not finished — 8 at capture time.
2. **Scores and throughput need the full sweep**, 188 KB, so they belong on a slow tier.
3. **One host, unsigned, third-party.** Treat every field as third-party text: escape before markup, fit on
   cell width, and never present its word as verified.


## BOARD captures — 2026-09-22

Source: the owner's seven frozen captures in `tests/fixtures/surf/swarm/v3/`, probed by Claude
at **≈01:55–02:05Z** on `https://api.imd.fun`. `MANIFEST.json` binds each file to its route,
status, date, selection reason, byte length and SHA-256. These are capture observations; no new
network requests were made while implementing the BOARD contract.

### `/contributors`

The envelope serves `receipts: 8226`, `tokensPerCompletedJob: 371004`, and **101 device rows
representing 99 distinct seats**. Seats #1089 and #1129 each have two devices. BOARD's SEATS
counts distinct token IDs, while the leaderboard's `dev` counts contributor devices per seat.

Each row serves `deviceKey`, `wallet`, decimal-string `tokenId`; integer `attempts`, `accepted`,
`rejected`, `pending`, `turns`; and decimal-string `wallClockMs`, `inputTokens`, `outputTokens`,
`cachedInputTokens`. Across the captured rows, attempts equal accepted + rejected + pending.
Totals are 8,226 attempts, 6,555 accepted, 242 rejected and 1,429 pending. Every counter is
aggregated by seat before display; rank is accepted descending, accept rate descending, token
ascending. Rate is undefined at zero attempts. Hours are aggregated wall-clock milliseconds / 3,600,000.

Token counts differ substantially by runtime accounting. `tokensPerCompletedJob` could not be
reproduced from these rows and is displayed **as served**, labelled `(served)`. No token-based
ranking or inferred cost is produced. Wallets are not part of the BOARD row contract.

### `/workers`

The envelope serves `count: 91` and 91 workers, all distinct seats in this capture. Each row has
`deviceKey`, `seat {tokenId, agentId}`, `working`, `maxConcurrency`, `paused`, `daemonVersion`,
`runtimes [{id, version}]`, `profiles`, `tools`, `skills`, `platform {os, arch, nodeVersion}`,
`connectedHere`, `connectedAt`, and `lastHeartbeatAt`.

Eleven seats have `paused {until, consecutiveFailures}`, each at three failures. Working sums to
zero and capacity to 151. Runtime buckets are codex 53, claude 37 and both 1; OS buckets linux 75,
darwin 12 and win32 4. Profiles are none+foundry 68 and none 23. Concurrency counts are 1×50,
2×30, 3×3 and 4×8. Daemon versions are served facts, without a latest/outdated judgement:

| Version | Devices |
|---|---:|
| `0.1.0+5e34612c` | 67 |
| `0.1.0+1308af71` | 18 |
| `0.1.0+285d1984` | 3 |
| `0.1.0+358bb77c` | 2 |
| `0.1.0+e9ca5510` | 1 |

The fifth daemon version is present in the frozen capture although omitted from the handover's
four-version summary. BOARD LIVE uses the valid **served** `count`, not the row length or
`/health.connectedDaemons`. The same-minute health capture reports 92; that independent count
stays on SWARM.

### Independent sources and normalization

The selected #420 capture serves `/seats` attempts 204, accepted 190, rejected 2, pending 12.
The contributor rows instead give attempts 207, accepted 189, rejected 2, pending 16. AGENT's
existing attempt/accepted line remains `/seats`-only; its separately labelled contributors group
uses `/contributors` only. This is a source difference, not a reconciliation opportunity.

The public contract is frozen in `data/surf_models.py`: `swarm_board_summary`,
`swarm_board_rows`, `swarm_fleet`, `swarm_seat_live`, `swarm_seat_contrib`, and the independent
`swarm_board_as_of_hhmm` / `swarm_workers_as_of_hhmm` markers. Each last-good slot retains its
own last-good-version clock. A changed valid normalized payload updates only its source slot
and marker; an unchanged successful read advances tier scheduling without rewriting that version.
Mixed-source panels receive both markers. A failed endpoint preserves its old slot and marker,
stores a changed successful counterpart, and schedules the tier with the 120-second backoff.
Selecting another seat derives that token's live/contributor state from these cached slots without another board request.

Contributor admission requires valid token/device identity and the six displayed counters:
`attempts`, `accepted`, `rejected`, `pending`, `turns`, `wallClockMs`. The undisplayed
`inputTokens`, `outputTokens`, `cachedInputTokens` are optional and become `None` if malformed.
Numeric parsing accepts nonnegative integers or ASCII-digit decimal strings only; booleans,
floats, negatives, signs, whitespace and garbage are invalid. The strict token parser is reused.
A missing top-level list makes the source unread; a valid empty list is a real empty read.

A bad token is dropped. A valid contributor token with an inadmissible row is remembered in
`malformed_tokens`. Its selected contribution is unavailable, and all its BOARD rows are
suppressed, including otherwise valid siblings. SEATS counts the union of admitted and malformed
tokens. Aggregate attempts/accepted/rejected/pending and all ranks become unavailable when
accounting is incomplete; other complete seats retain their own counters. AGENT renders
`rank unavailable` without a denominator in that case, preserving room for its source clock;
`ranked_of` still carries the known seat count in data. Receipts and
tokens-per-completed-job remain independently served values.

Every valid-token worker stays present. Bad device, numeric or metadata fields become unknown.
Internal `pause_known` distinguishes served null pause from missing/malformed pause; a valid
pause retains its paired until/failures. Working and capacity sums are unavailable if any member
is unknown. Positive known work proves working; otherwise a valid pause proves paused. Idle
requires every device to have known zero work and known-null pause; other cases are unknown.
For multiple pauses choose the earliest until, breaking ties by device key, retaining its paired
failure count. Unknown concurrency produces no fleet bucket. Optional metadata remains `None`,
distinct from served empty lists; empty fleet metadata mixes read `none reported`.

A good workers read without a seat yields offline; unread or inadmissible yields unavailable.
A good contributors read without a seat yields `listed: False`; unread or malformed yields
`None`. Cache slots require sorted unique nonnegative integer `malformed_tokens` lists, and
worker rows require boolean `pause_known`. Old normalized slots lacking this bookkeeping are
rejected because discarded identities cannot be reconstructed; ordinary refresh repopulates them.

Worker metadata belongs in **`swarm_seat_live`**, keeping `/seats` summary fields source-pure:
`skills` is the distinct skill count, `profiles` a sorted distinct list, and `platform` the sorted
distinct `os arch` values joined with commas. No missing field is presented as zero metadata.
Fleet mixes count devices, sort count descending then value, and preserve runtime/daemon text as
served; third-party text is sanitized in the widget. Paused fleet entries aggregate per seat and
sort by until then token.

### Detail dispatch and failure notes

`job_5a4dfb13_dispatch_note` is executing and carries a node `dispatchNote` with `dispatchNoteAt`.
`job_0ed3e9f8_blocked` contains a failed, unassigned node with `failureReason: budget_exhausted`.
`job_33016bad_two_node_verdict` preserves a two-node example with seat attribution and verdicts.
IN FLIGHT remains limited to executing jobs. Its row gains `note` and `note_kind`: dispatchNote
wins over failureReason; absent notes remain `None`. `dispatchNoteAt` and `allowedPaths` are not
displayed. The existing widget signature already receives `swarm_inflight_rows`, so extending
that row contract carries the note without adding an unused top-level widget parameter.

### Display and selection

BOARD is the seventh body on `b`: six source-labelled hero boxes, the complete scrollable seat
leaderboard, and fleet metadata. Enter or a single mouse click validates the row's immutable token, saves it through
`config.save_seat`, and follows the shared AGENT selection path without waiting on the network.
A first click on a noncurrent row selects immediately; each activation saves once. Header and
empty-space clicks do not select. The selection marker follows the current AGENT seat. Fleet values remain whole when shown;
`+N` counts omitted entries. Wallets are absent from BOARD.

AGENT's STATUS uses workers independently of `/seats`, with its worker clock in the title.
The accepted timestamp still requires a good seats state; its source clock is in ACCEPTED.
SEAT's contributor group remains available independently of the seats response. It keeps
all counters, turns, hours, rank and its own clock on two lines at narrow widths, joining one
only when the whole group fits. Worker metadata and its clock are no longer painted in SEAT.
Pairing time shares identity; queued feedback shares sent/submitted. The old seats online flag
is removed; STATUS is the liveness source. An absent seat and an unread source retain distinct
messages. Acceptance labels replace the old win wording;
the historical `win_rate` and `last_won_ts` contract names retain their acceptance meaning.

IN FLIGHT's last column sanitizes and clips the note, lighting `‹ widen` when content is cut.
A literal ellipsis in a fitting source note does not itself indicate clipping. Long free-text
notes remain a named layout exception; measured pins and exceptions live beside the constants
in `screens/surf.py`. No blocked jobs are added to this table.

## 2026-09-22 — polish: submission answers and advertised models

Reference: `/Library/Vibes/aidude/docs/imd-api-changelog.md` §§2–4, including its afternoon
route-discovery entry (read only). That shared file now includes the routes which the polish
handover described as missing from it. Fresh WP0 captures are in `tests/fixtures/surf/swarm/v4/`;
`MANIFEST.json` records each actual UTC timestamp, full URL, HTTP status, bytes and SHA-256.
The seven requests all returned 200. Counts below describe those files, not fixed API promises.

- `/jobs/{uuid}/submissions` serves every submitted attempt for that known job, with exact
  `hash`, seat, node/role, Markdown `summary`, `usage`, outcome/oracle verdict, findings and
  artifacts. The three captures contain 40/30/2 submissions; each includes seat #420.
- `/jobs/{uuid}/result`, `/artifacts/{hash}` and `/bundles/{hash}` were observed by the reference's
  author. They provide the winning bundle, raw artifacts and git bundle respectively. WP0 did
  not refetch these three routes, and this dashboard does not consume them.
- Submission `usage.model` is the model that **ran** the attempt. Worker
  `runtimes[].premiumModel{model,effort}` is **advertised**, asserted by a daemon rather than
  probed. They must not be substituted for each other. The fresh worker capture has 107 rows:
  43 advertise gpt-6-astra/xhigh, 34 claude-fable-5-1/high, and 30 no model.
- `/skills` now carries `inference` and lifetime `record` attempts/accepted/rejected/pending/
  wallClockMs. Missing fields remain unknown; the model-tier names are served text.
- `/health.status` is available as a health word. `operatorSurface`, `taskNetwork` and
  `lotusTargets` remain outside the display contract because their meaning is not established.
- `/workflows` joins two-stage launches. It is filed as F51; per-job co-working via submissions
  is F52, and rejected attempts outside known jobs are F53. No workflow or global rejected-job
  discovery was added.

RECORD selects only the submission whose hash exactly matches the seat's work row. It displays
the first sentence of the cleaned reply, with model and duration from that same read. Markdown
link targets are discarded and remaining absolute local paths reduced to basenames. Newline
sentence boundaries are preserved until selection; flattening comes afterward. Rendering still
sanitizes third-party text. The raw submission payload is never persisted in the answer cache.

Five answer states stay distinct: read, not read, unavailable, not served, no reply. Unknown
model/duration on a successful matching read are em dashes. Failed, unfetched and absent rows
show their explicit state in the answer cell and em dashes for model/duration; stale metadata
is suppressed. A successful empty reply may still carry its matched usage fields.

The answer reader permits four unique jobs after each successful selected-seat read, covering
the first 40 RECORD rows. Unread rows precede due retries; multiple hashes from one job share
one GET. Retryable results become due after `SWARM_ANSWER_DUE_S`. The validated cache keeps
at most 400 extracted points for 48 hours, with `read_ts` and `terminal` bookkeeping.
Corrected by polish §7: a 404 is explicitly preserved by the client and displayed as
`not served`, like a successfully absent hash. These real negatives and successful terminal
reads remain frozen while retained. Transport/parse failures stay unavailable and retry even
on terminal jobs; legacy unavailable/frozen entries become retryable. Malformed points are
dropped independently. A safe stored string is checked for length, link targets, absolute
paths and controls, rather than re-running sentence extraction. Extraction is bounded to
4,096 input characters, uses linear link scanning and reaches a bounded stripping fixed point.
`file://` and home paths are reduced without exposing bare user segments; HTTP(S) URLs remain.

A four-job MockTransport replay used the three committed submission captures and one copied
oracle payload assigned a synthetic UUID: 270,288 compact raw bytes became 1,087 cache bytes
for four extracted points. Replay CPU/transport time was 0.00553 seconds with pacing injected,
not slept. Required pacing adds a 0.48-second submissions floor (0.60 seconds including the
seat GET). These are replay measurements, not a measured four-job live latency; the three
actual WP0 submission GETs took 0.380, 0.215 and 0.167 seconds individually.

CAPABILITY displays inference and accepted/attempts on its optional wider tier (166 terminal
columns in the measured layout). The original seven columns remain whole at 141; no SWARM
body pin was raised. The enriched first 40 RECORD rows in the v4 seat capture include the
boilerplate and informative jobs at indices 0 and 1; the build job at 125 is not part of that
window. Their longest cleaned answer is 80 cells and clears from 204 terminal columns.
