# PEPEPANE status document — schema v2, and the mapping from the aidude writer's v1

**Producer:** `pepepane --once` prints one document per run (`data/seat_models.py` owns the shape; `pepepane 0.1.0` is
the `producer` string). **Version:** `schemaVersion: 2`. **Consumers:** The Lineup, the aidude mode-B writer if it adopts
v2 (spec §17 "aidude writer fixes"; `docs/seat_followups.md`), any external alerting. v2 is a **new contract**, not an
extension of v1 (spec §7): a consumer that reads v1 keys from a v2 document gets `null`, never a wrong number, and a
v2 consumer refuses v1 outright.

## Rules every consumer relies on

- **Refusal first** (`data/seat_models.validate_status_document()`, run by `--once` on its own output): not a JSON
  object → `not_an_object`; larger than 2 MiB on disk → `too_large`; `schemaVersion` not `2` → `wrong_schema`; any key
  matching `privateKey|devicePrivateKey|mnemonic|secret|tools\.env|auth\.json` (case-insensitive), any value matching an
  OpenAI-style `sk-…` or a JWT `eyJ…`, or **any** 64-hex value anywhere → `with_secret` (and the producer audits
  `canary`). No 64-hex value survives in a valid document because the device public key is truncated to 8 characters at
  fold time (spec §13). A missing field inside v2 is `null`, never a crash.
- **A failed read is `null`, never `0`** — and the truth about availability is `sources`, per field. Every block below
  names the source tag its fields come from (`L` daemon log/tail · `H` home-dir facts via the broker · `C` `imd` CLI text
  via the broker · `U` unit/cgroup/docker · `S` session summariser · `A` `api.imd.fun` · `D` derived · `K` configured).
  Each `sources.<name>` is `{ok, asOfUtc, ageS, reason, trust}`; `trust` is `"host"` on the VPS and `"container"` for
  every Mac value produced by `docker exec … imd …` or the `python3 -` projection (`imd_dashd/projection.py` piped into
  the container; WP6 deviation 4) (spec §4.2) — a container-reported value is shown, never
  used for a gate.
- **Two stamps**: `startedAtUtc` and `completedAtUtc`; every panel's "as of" is its own source's `asOfUtc`, never the
  fold time (v1's single start-only stamp produced false ambers, fill4 §6).
- **Three outcome axes are never summed** (spec §2): control-plane attempts (`standing.attempts` etc., `tasks.rows[].outcome`),
  chain feedback rows (not in v2 at all — SURFBOARD and The Lineup render them), and standing/doctor failed runs
  (`standing.recentFailures`, `tasks.rows[].failureReason` as enum words only). `pending` is never "running".
- **Identifiers**: `seat.deviceKeyPublic` and `seat.wallet` are 8 characters; job/node ids are full (they are join keys);
  submission hashes are `hash12`. Free-text failure summaries from the API are never persisted or emitted.
- No currency anywhere in v1: no `$` figure in any panel, document field or code path — `cost-state.totalCostUSD` and `imd doctor`'s list-price line are never read or shown (spec §10). v2 has no currency field; `cost` is tokens.

## v2 top-level blocks

| block | source tags | what it holds (spec §7 has every field) |
|---|---|---|
| `schemaVersion`, `producer` | K | `2`, `pepepane 0.1.0` |
| `startedAtUtc`, `completedAtUtc` | D | the fold's own two stamps |
| `pollInterval` | K | the TUI poll cadence in seconds (default 5; `--poll-interval`); the fold carries it as `poll_interval`, the status bar's `Ns poll` (WP1 deviation 8) |
| `host` | U | `kind` (`systemd`/`docker`/`fixture`), `unit`, `container`, `runtime` (`codex`/`claude`), `hostname` |
| `sources` | — | one entry per source: `tail` `unit` `broker` `seat` `status` `skills` `sessions` `workstat` `hints` `auth` `standing` `seatWork` `reasons` `plane`; the API four keep last-good values behind `ok:false` until `unavailable`, and are absent under `--offline` |
| `seat` | C/H/L/A/K | `tokenId`, `agentId` (A `enrollment.agentId` → K `PEPEPANE_AGENT` → null), `deviceKeyPublic` (8 chars), `wallet` (8 chars), `server`, `eligibility`, `capacity` (int), `offers`, `daemonVersion`, `runtime{id,version}`, `releaseAvailable`, `buildMismatch`, `skills{offered,on,optOut,needsNetwork,rows}`, `tools`, `inference` (projection, owner #5), `premiumAdvertised`, `hints{path,bytes,sha8,mtimeUtc}`, `configChangedSinceStart` |
| `daemon` | L | newest heartbeat: `state`, `uptime`, `work`, `running` (int), `submittedSinceStart`, `lastHeartbeatUtc`, `heartbeatAgeS`, `idleBeats`, `fleetOnline`/`fleetEnrolled` (null when the clause is absent), `pausedHint`, `invocationId`, `lastAdmittedUtc`, `disconnects24h`, `reconnects24h`, `consecutiveDisconnectedBeats` |
| `auth` | D over L+S+H | the runtime-auth-degraded composite (spec §10): `degraded`, `reasons`, `sinceUtc`, `credentialFileMtimeUtc` (stat only) |
| `unit` | U | `activeState`, `subState`, `mainPid`, `sinceUtc`, `restarts`, `bootEnabled`, `restartPolicy`, `killMode`, `stopTimeoutS`, `gracefulStopPossible`, `memoryCurrentB`, `memoryPeakB`, `memoryMaxB`, `cpuQuota`, `tasksCurrent` (docker: the same names from `docker inspect`/`stats`) |
| `current` | L (+A) | the task in flight or `null`: `nodeId8`, `jobId`, `role`, `kind`, `phase`, `startedUtc`, `elapsedS`, `maxTurns`, `model`, `tierDerived`, `lastMessage` (≤160, control-stripped, redacted), `lastMessageUtc`, `planeSince`, `objective`, `nodeKey` |
| `queue` | A | `/seats/<id>/standing.queue` only: `ready`, `eligible`, `fleetOnline`, `blocked[]`, `asOfUtc` — never from `?queue=0` (which returns `null`) |
| `tasks` | L/H/S/A | `window{fromUtc,toUtc,source,rows,gapNote,ledgerSinceUtc}` and `rows[]` keyed `seat/node8/acceptedUtc` with local lifecycle facts, session facts and the API verdict joined by `hash12` (spec §7 lists every field) |
| `today` | D | per-UTC-day counts, `p50S`, `longestS`, verdict counts, `verdictLagP50S`, `divergence{localStored, planeRowsSubmittedToday, ok}` |
| `cost` | S/D | 7-day window with API-equal definitions (spec §10): `tasks`, `excluded{doctor,manual}`, `turns`, `tokens{input,output,cached,cacheWrite}`, `buckets[]` per `(model, effort, ~tier)`, `sideModel`, `series` (14 d from sqlite `days`), `depth` — tokens, never currency |
| `quota` | S | Codex: `usedPercent`, `resetsAtUtc`, `sampledAtUtc`, `planType`; Claude: `usedPercent: null`, `reason: "not observable locally"` |
| `standing` | A | lifetime counters from `/seats/<id>` (`attempts accepted rejected failed pending`, `countersInconsistent` when they violate `attempts == accepted+rejected+failed+pending`) plus the live `/seats/<id>/standing` facts (`working`, `running[]`, `consecutiveFailures`, `pausedUntil`, `breaker`, `recentFailures[]` without `summary`, `presenceConnected`, `heartbeatAgeMs`) |
| `plane` | A | `/health` + `/services`: `version`, `verifierUp`, `verifierLastSeenUtc`, `awaitingVerdict` (undocumented), `connectedDaemons` |
| `machine` | U/H/L | `load1`, `memAvailMiB`, `diskFreeGiB`, `workDirs`, `workBytes`, `abnormalLeaseDirs`, `outboxFiles`, `journal{firstUtc,lastUtc,capNote}` or the docker log facts, `transcriptRetention`, `orphans[]` |
| `control` | broker | `brokerReachable`, `gate{…}` (plan-time preview; apply re-reads everything), `drain`, `inFlight`, `restartRequired`, `lastAudit[]` |

## Mapping: aidude writer v1 (`tools/surf/_worker_page.py`, `schemaVersion: 1`) → v2

The v1 emitter has 13 top-level keys (`container cost current daemon fleet generatedAtUtc host reputation
schemaVersion seat sources standing tasks`) and 9 `sources` (fill4 §3). Every one is listed; "dropped" means v2 has no
field for it on purpose, with the reason.

| v1 | v2 | note |
|---|---|---|
| `schemaVersion` = 1 | `schemaVersion` = 2, plus `producer` | a v2 consumer refuses 1 as `wrong_schema`; the writer refused ≠ 1 the same way (plan R-A) |
| `generatedAtUtc` (stamped before any gather) | `startedAtUtc` + `completedAtUtc` | v1's single stamp aged by the gather time (~40–50 s, fill4 §6) and produced false ambers |
| `seat.tokenId` | `seat.tokenId` | int |
| `seat.agentId` | `seat.agentId` | v2 source order: `standing.enrollment.agentId` (A) → `PEPEPANE_AGENT` (K) → null; `imd status` prints none |
| `seat.deviceKey` (64 hex) | `seat.deviceKeyPublic` (8 chars) | spec §13 identifiers; a 64-hex value anywhere refuses the document |
| `seat.eligibility` | `seat.eligibility` | third-party text, redacted + sanitised |
| `seat.capacity` (string `"1 concurrent task(s)"`) | `seat.capacity` (int) | parsed |
| `seat.offers` | `seat.offers` | list |
| `seat.server` | `seat.server` | |
| — | `seat.wallet`, `seat.daemonVersion`, `seat.runtime`, `seat.releaseAvailable`, `seat.skills`, `seat.tools`, `seat.inference`, `seat.premiumAdvertised`, `seat.hints`, `seat.configChangedSinceStart` | new |
| `daemon.state` / `uptime` / `work` | same names | |
| `daemon.working` (bool) | `daemon.running` (int) | the heartbeat says `N task(s) running` |
| `daemon.submitted` | `daemon.submittedSinceStart` | resets at every `runtimes:` restart boundary (contradictions #7) |
| `daemon.lastHeartbeatUtc` | `daemon.lastHeartbeatUtc` | |
| `daemon.heartbeatAgeSeconds` | `daemon.heartbeatAgeS` | |
| `daemon.buildMismatch` | `seat.buildMismatch` | moved beside `daemonVersion`/`releaseAvailable` |
| — | `daemon.idleBeats`, `fleetOnline`, `fleetEnrolled`, `pausedHint`, `invocationId`, `lastAdmittedUtc`, `disconnects24h`, `reconnects24h`, `consecutiveDisconnectedBeats` | new; fleet figures come from the heartbeat clause first (v1 took them from `/health`) |
| `host.kind` / `host.runtime` | `host.kind` / `host.runtime` | |
| `host.ssh` | dropped | the TUI runs on the host; nothing is read over ssh |
| `host.unit` / `host.container` | `host.unit` / `host.container` | plus `host.hostname` |
| `host.bootEnabled` | `unit.bootEnabled` | |
| `container.running` / `container.status` | `unit.activeState` / `unit.subState` (docker: `running`/`status`) | the block is `unit` on both hosts |
| `container.image` | dropped | the image tag does not describe the running build (collectors CONSTRAINTS); `seat.daemonVersion` comes from the log |
| `container.restartPolicy` / `container.restarts` | `unit.restartPolicy` / `unit.restarts` | |
| `container.memoryUsed` (docker `stats` text) | `unit.memoryCurrentB` (bytes, int) | plus `memoryPeakB`, `memoryMaxB` |
| `container.memoryPercent` / `container.cpuPercent` | dropped | derive from `memoryCurrentB`/`memoryMaxB`; load is `machine.load1`; v1 read them from `docker stats`, which fails independently of `inspect` (fill4 §5) — hence per-field sources |
| `container.pids` | `unit.tasksCurrent` | |
| — | `unit.mainPid`, `sinceUtc`, `killMode`, `stopTimeoutS`, `gracefulStopPossible`, `cpuQuota` | new; `gracefulStopPossible` decides whether `--force` may exist (spec §5.5) |
| `fleet.online` / `fleet.enrolled` | `daemon.fleetOnline` / `daemon.fleetEnrolled` (heartbeat), `plane.connectedDaemons` (`/health`) | never summed across routes |
| `fleet.workingNow` / `acceptedLastDay` / `queued` / `deployBreaker` | dropped | fleet-wide figures; The Lineup renders them (three "working" figures disagree at any instant, changelog 2026-09-26) |
| `fleet.controlPlaneVersion` | `plane.version` | plus `plane.verifierUp`, `verifierLastSeenUtc`, `awaitingVerdict`, `connectedDaemons` |
| `current.taskId` | `current.nodeId8` (+ `nodeId`, `jobId`) | v1's id was the log's node8 too |
| `current.kind` / `phase` / `startedUtc` / `maxTurns` | `current.kind` (+ `role`) / `phase` / `startedUtc` (+ `elapsedS`) / `maxTurns` | |
| `current.artifact` | dropped | the allowed-paths clause is not carried; the LEDGER detail modal shows phases |
| `current.message` | `current.lastMessage` (+ `lastMessageUtc`) | ≤160 chars, control-stripped (redactor step 0), redacted, sanitised |
| — | `current.model`, `tierDerived`, `planeSince`, `objective`, `nodeKey` | new |
| `tasks` (list of rows) | `tasks.window` + `tasks.rows[]` | the window says which log, from when, and whether a gap or a discarded backfill occurred |
| `tasks[].id` | `tasks.rows[].nodeId8` (+ `nodeId`, `jobId`, `key`) | key = `seat/node8/acceptedUtc` because node8 repeats within and across seats (fill6) |
| `tasks[].kind` | `tasks.rows[].kind` (+ `role`) | |
| `tasks[].startedUtc` | `tasks.rows[].acceptedUtc` | plus `submittedUtc`, `storedUtc` |
| `tasks[].seconds` | `tasks.rows[].durationS` | |
| `tasks[].phase` | dropped from rows | phases seen live in the detail modal; the row carries `repair`, `resent`, `cancelled`, `leaseClosed`, `preAgentFailure`, `agentRan` instead |
| `tasks[].submissionId` | `tasks.rows[].hash12` | the 12-hex prefix of `work[].submissionHash`; the API verdict joins on it |
| `tasks[].answer` (free text) | dropped | model output is never persisted or emitted (spec §13; safety §5.4) |
| — | `tasks.rows[].runtime`, `model`, `effort`, `tierDerived`, `turns`, `turnsDefinition`, `tokens`, `sideModelTokens`, `ttftMs`, `wallMs`, `turn1Context`, `maxTurnsReached`, `apiErrors`, `sessionFiles`, `outcome`, `outcomeAsOfUtc`, `acceptedAtApi`, `verdictLagS`, `failureReason`, `failureClass`, `nodeKey`, `objective`, `source` | new |
| `reputation` (`accepted`, `rejected`, `tags`, `scannedFromBlock`, `scannedToBlock`, `rows[]{block,outcome,tag1,tag2,client,tx}`) | dropped | chain rows are the third outcome axis and out of scope (spec §17); uncapped in v1 (~296 B/row, fill4 §2); SURFBOARD/The Lineup render them |
| `cost.runs` | `cost.tasks` (+ `cost.excluded{doctor,manual}`) | v1 counted every transcript on the machine incl. doctor/probe sessions (fill3 §5) |
| `cost.turns` | `cost.turns` | API-equal definition: Claude `type:"user"` lines, Codex `AgentMessage` items (v1 was ~2× over) |
| `cost.inputTokens` / `outputTokens` | `cost.tokens.input` / `cost.tokens.output` | Claude summed over distinct `message.id`, not per line |
| `cost.cacheRead` / `cost.cacheWrite` | `cost.tokens.cached` / `cost.tokens.cacheWrite` | Claude `cached = cache_read + cache_creation` (= API); Codex `cacheWrite` is always 0 |
| `cost.model` (first run's) | `cost.buckets[].model` (+ `effort`, `tierDerived`) | bucketed by `(model, effort)` because tiers changed under us |
| — | `cost.windowDays`, `cost.buckets[].{tasks,turnsP50,wallP50S,wallP90S,ttftP50Ms,turn1ContextP50,maxTurnsHits,authErrors}`, `cost.sideModel`, `cost.series`, `cost.depth`, `quota` | new |
| `standing.ok` | `sources.standing.ok` / `sources.seatWork.ok` | availability lives in `sources` |
| `standing.attempts` / `accepted` / `rejected` / `pending` | `standing.attempts` / `accepted` / `rejected` / `pending` (+ `failed`, `countersInconsistent`) | v1 read `/contributors` (per **device**, folds `failed` into `pending`); v2 reads `/seats/<id>` top-level counters (417/417 seats satisfy the identity) |
| `standing.turns` / `rejectRate` / `fleetRejectRate` / `fleetAttempts` / `rankByAttempts` / `contributors` | dropped | cross-route arithmetic and fleet ranking belong to the AGENT view / The Lineup (spec §6 rule 1) |
| — | `standing.working`, `running[]`, `consecutiveFailures`, `pausedUntil`, `breaker`, `recentFailures[]`, `presenceConnected`, `heartbeatAgeMs`, `asOfUtc` | new, from `/seats/<id>/standing` (the seats form, which omits `summary`) |
| `sources` (9 blocks, `{ok, reason}`) | `sources` (14 names, `{ok, asOfUtc, ageS, reason, trust}`) | see the row below for each v1 name |
| `sources.heartbeat` | `sources.tail` | the log follower (journald / `docker logs`) |
| `sources.status` | `sources.status` (+ `sources.seat`, `sources.skills`) | `imd status` / the projection / `imd skills`, each its own source |
| `sources.container` + `sources.stats` | `sources.unit` | mapped **per field** (`inspect` and `stats` fail independently, fill4 §5) |
| `sources.tasks` | `sources.tail` (+ the ledger's `tasks.window`) | rows come from the tail; the ledger is durable |
| `sources.chain` | dropped | no chain source in v2 |
| `sources.health` | `sources.plane` | `/health` + `/services` |
| `sources.transcripts` | `sources.sessions` | the summariser (VPS: transient unit; Mac: in-container `timeout`) |
| `sources.standing` | `sources.standing` + `sources.seatWork` (+ `sources.reasons`) | one per route |
| — | `sources.broker`, `sources.workstat`, `sources.hints`, `sources.auth` | new |
| — | `auth`, `queue`, `today`, `machine`, `control` | new blocks with no v1 counterpart |

## What the aidude writer would adopt to emit v2

Listed in `docs/seat_followups.md` ("aidude writer fixes", spec §17): dedup Claude usage by `message.id`; Codex turns =
`AgentMessage` items; exclude doctor/probe sessions by cwd/slug; drop `reputation` or cap its rows; per-field `sources`
with `asOfUtc`; `completedAtUtc`; a local systemd mode; `schemaVersion: 2` with `producer`. Until then v1 stays what it
is and PEPEPANE does not consume it (spec §7 last paragraph).
