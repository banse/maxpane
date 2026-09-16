# The IMD swarm: what the explorer shows and what its API serves

Research for a surf body on <https://explorer.imd.fun/>. Every number and shape below was measured on
**2026-09-16**, not taken from documentation: <https://www.imd.fun/docs/> says "protocol overview, agent
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
| `GET /jobs` | every job, newest first | 27.5 KB (62 jobs) |
| `GET /jobs/{id}` | one job with its subtasks, verdicts and review | 2.2 KB typical, 9.2 KB worst |
| `GET /launches` | deployments with every contract address | 10.1 KB (16) |
| `GET /sites` | published IPFS sites with their ENS names | 2.3 KB (4) |
| `GET /jobs/summary` | **500**, a broken query the server admits to | — |
| everything else tried | 404 | — |

404 on: `/`, `/agents`, `/agents/1`, `/agents/by-token/1`, `/harness`, `/harness/state`, `/reviews`, `/scores`,
`/attestations`, `/receipts`, `/deliveries`, `/enrollments`, `/identity`, `/verifications`, `/feedback`, `/work`,
`/activity`, `/moves`, `/field`, `/leaderboard`, `/inference`, `/tokens`, `/operators`, `/swarm`, `/metrics`,
`/queue`, `/seats`, `/daemons`, `/pairs`, `/status`, `/public`, `/v1/jobs`, `/api/jobs`, `/openapi.json`, `/docs`.
The explorer's own origin serves no `/api/*` route either.

**No filters.** `?state=executing`, `?limit=3` and `?since=…` all return the same 62 rows, so the list is
all-or-nothing. **No caching headers**: no `cache-control`, `etag`, `age` or `last-modified`, so a conditional
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
  for an agent's name, skills or history. The avatar SVG at `/agents/by-token/{n}.svg` is an image, not data.
- **Reviewer attribution.** A review says which agent was *scored*, never which agent reviewed.
- **Anything signed.** Nothing the host serves is signed or hashed. The review `txHash` is the only claim that
  can be checked against a chain.

## Consequences for a dashboard

1. **The live picture costs 567 bytes**, and the 27.5 KB list only has to be re-read when a `/health` counter
   moves. Job details are needed only for jobs that are not finished — 8 at capture time.
2. **Scores and throughput need the full sweep**, 188 KB, so they belong on a slow tier.
3. **One host, unsigned, third-party.** Treat every field as third-party text: escape before markup, fit on
   cell width, and never present its word as verified.
