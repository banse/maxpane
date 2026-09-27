> **Overridden by `pepepane` (2026-09-26).** This document describes the mode A/B/C design, the six-surface registration and menu key 9; it is superseded by `docs/pepepane_PRD.md` and `docs/pepepane_plan.md` and kept unedited below for its history (lineage research: `sweep-seat-prd-lineage.md`).

# SEAT — a dashboard for the IdentityMD worker running on this machine

**Status:** handover, not yet implemented. Written 2026-09-20 from a live seat
(IDMD #420 / ERC-8004 agent 50939), now at 13 accepted feedback rows on Ethereum mainnet.
**Target topology: MaxPane on the Linux host, outside the container, reading Docker's own files
(mode A).** The JSON bridge (mode B) is for building and testing on macOS, where mode A's paths do
not exist; its writer already exists. Running inside the container (mode C) is kept as a later plan.
**Triage:** Tier 2 — new dashboard, full six-surface registration.
**Game id:** `seat` · menu key `9` · title `SEAT` · one-liner
*"Your IdentityMD worker: liveness, work, reputation, cost"*.

Its sibling is `docs/surf_swarm_v2_PRD.md`, the rebuilt SURFBOARD `s` body, which covers the swarm
as a protocol. This one covers **one machine**.

---

## 1. Why this is its own dashboard and not a body in SURFBOARD

Every other MaxPane view answers a question about a public system: anyone, anywhere, gets the same
answer. **This one is only true on one machine**, and is blank everywhere else. Putting it behind a
key inside SURFBOARD would mean a body that is permanently unavailable for most readers of the
dashboard it lives in.

It is also the first view whose source is **local machine state** rather than a public endpoint. The
precedent exists — `data/frenpet_client.py` reads a local SQLite file read-only (`:570-615`) and a
loopback service at `127.0.0.1:8420` (`:85`) — but it has never carried a whole dashboard, and this
one is entirely that.

---

## 2. What an IdentityMD seat is, in the five facts this view needs

An operator holds an **IDMD NFT** (2,000 supply, mainnet `0x0000eC93…`). Pairing binds that token to
an **ERC-8004 agent id** through an adapter, after which a daemon on their machine holds an outbound
WebSocket to the control plane and is offered work.

1. **The daemon is a long-lived process in a Docker container.** It prints a heartbeat roughly every
   30 s: `alive 4h28m · idle · 9 submitted · fleet 16 online, 17 enrolled`.
2. **Work arrives as bounded tasks.** The daemon clones a repo into a workspace, runs a coding agent
   against it, and uploads one artifact. States observed: `preparing`, `working`, `checking`,
   `bundling`, `uploading`, `submitted`.
3. **Submitted is not accepted.** A submission is independently re-run by a verifier before any
   verdict exists. Only then is ERC-8004 feedback written on chain against the agent id.
4. **The daemon keeps no history.** Once a task is submitted its workspace is cleaned. The only
   record of what this machine has done is its own log, and the runtime's transcripts.
5. **Every task spends the operator's own model subscription.** Measured over the first seven tasks:
   259 turns, 183 k output tokens, **11.57 M cache-read tokens**.

Those five facts are why this dashboard exists: nothing else will tell an operator whether their
machine is earning or idling, and whether it was worth it.

---

## 3. Three source modes

**Target (A): MaxPane on the Linux host, outside the container, reading Docker's own files.**
**Dev/test (B): the JSON bridge**, because none of A's paths exist on macOS.
**Later (C): inside the container**, kept as a plan rather than the destination.

One normalised shape, one client, three readers. The panels never learn which produced the data.

### Mode A — outside the container, on the host (**the target**)

On Linux, a container's storage and its log are ordinary files on the host, and its processes appear
in the host's process table. Verified against the running seat (paths and PID are real; their
*contents on Linux* are asserted from Docker's documented layout and **must be confirmed on the VPS**,
since none of these exist on macOS):

| Source | Path | Yields |
|---|---|---|
| Seat state | `/var/lib/docker/volumes/imd-home/_data/` | `config.json` (server, wallet, `tokenId`), `work/<jobId>/` workspaces, `outbox/` |
| Runtime cost | `/var/lib/docker/volumes/imd-claude/_data/projects/*/*.jsonl` | per-task turns, tokens, model, the agent's own messages |
| **Heartbeat** | `/var/lib/docker/containers/<id>/<id>-json.log` | the `json-file` driver writes `{"log","stream","time"}` per line — **this is where `alive 4h28m · idle · 9 submitted · fleet …` lives** |
| Liveness | `/proc/<State.Pid>/` | the container's host-namespace PID (`docker inspect -f '{{.State.Pid}}'` reported **12772** here) |

**This mode is strictly better than running inside**, and for a reason worth stating: the daemon's
heartbeat is stdout, so it is *not a file inside the container* — an in-container reader can never
see uptime, the submitted counter or fleet size. From the host it is a plain log file. Mode A is the
only mode that recovers everything.

**No `docker` subprocess anywhere.** The container id and PID come from configuration written once at
install time, not from shelling out per refresh. That matters because those calls hang when the
Docker daemon wedges — observed 2026-09-20, `docker ps` and `docker exec` blocked indefinitely while
the backend stayed alive.

**The real constraint is permissions, and it needs an install decision.** `/var/lib/docker` is
root-owned and typically `0710`, and the volume files are mode 0600 owned by the container's uid.
Reading them means one of: running the dashboard as root (**not recommended** for a TUI), a group or
POSIX ACL granting read on those specific paths, or a small privileged job that copies the four
sources somewhere readable — which is mode B wearing different clothes. **Pick deliberately and write
it in the install doc**; do not let it become "run it as root because that worked".

**Never read `config.json`'s device private key.** Take `wallet` and `tokenId`; nothing else there is
needed, and the 0600 mode is not decoration.

### Mode B — the JSON bridge (**development and testing**)

None of mode A's paths exist on macOS: `docker volume inspect` reports
`/var/lib/docker/volumes/imd-home/_data`, and that path is inside Docker Desktop's VM. Verified
absent on the host, along with the log path. So on a developer machine the dashboard reads a status
document instead.

**The writer already exists**: `bin/aid worker-page --json` in `/Library/Vibes/aidude` emits
`data/surf/worker-status.json` (~6 KB, `schemaVersion: 1`) from the same gathered sources as its HTML
page, on a 5-minute launchd timer. It carries every field including the heartbeat, so it is a
faithful stand-in for mode A — which is what makes it a real test harness and not a toy.

### Mode C — inside the container (**a plan for later, not the target**)

Kept because it needs no host permissions at all and is the natural shape if the worker ever runs
somewhere the host filesystem is not ours.

Measured feasible: `/proc/1/cmdline` from a sibling `docker exec` reads
`node …/imd start --runtime claude --concurrency 1`, so liveness is a fact there; the seat files and
transcripts are directly readable. The image needed `python3-venv` — it had `python3` 3.11.2 but no
pip, and `python3 -m venv` failed on missing `ensurepip`. Added in `imd-worker:6c2c43ef-forge3` and
verified a venv with pip builds.

Its costs, and why it is not the target:

- **The heartbeat is unreachable.** Uptime, the submitted counter and fleet cannot be obtained; they
  would have to render unavailable, or be replaced by weaker derived numbers clearly labelled as
  such.
- Launch requires `docker exec -it` — a plain exec has no TTY and Textual will not start.
- It puts the dashboard where task agents run with unscoped `Read`, `Grep` and `Bash(cat:*)`. It is
  read-only by charter, which fits, but it must hold no keys and write nothing outside `~/.maxpane`.
- `~/.maxpane` should live in a volume so caches survive image rebuilds.

### One normalised shape, three readers

`data/seat_client.py` exposes one method returning one structure. The reader is chosen by
configuration, never guessed:

- `MAXPANE_SEAT_STATUS` → mode B, that file.
- `MAXPANE_SEAT_DOCKER_ROOT` + container id → mode A.
- `IDENTITYMD_HOME` readable and `/proc/1` names `imd` → mode C.
- None → unavailable, naming the options.

A field a mode cannot supply arrives as unavailable-with-reason, exactly as a failed read would. The
panels are written once.

### Schema v1 — freeze this before either side starts

```jsonc
{
  "schemaVersion": 1,
  "generatedAtUtc": "2026-09-20T20:08:00Z",   // staleness comes from THIS, never file mtime
  "seat":   { "tokenId": 420, "agentId": 50939, "owner": "0x…",
              "deviceKey": "72b617d4…", "eligibility": "eligible — this machine can receive work",
              "capacity": 1, "offers": ["code","fuzz","research"] },
  "daemon": { "state": "alive",               // alive | disconnected | unknown
              "uptime": "4h28m", "work": "idle", "working": false,
              "submitted": 9, "lastHeartbeatUtc": "…", "buildMismatch": true },
  "container": { "running": true, "image": "imd-worker:6c2c43ef-forge2",
                 "restartPolicy": "unless-stopped", "restarts": 0,
                 "memoryUsed": "46.4MiB", "memoryLimit": "3.5GiB",
                 "cpuPercent": "0.00%", "pids": 11 },
  "fleet":  { "online": 16, "enrolled": 17, "workingNow": 5,
              "acceptedLastDay": 57, "queued": 1 },
  "current": { "taskId": "bbc66c11", "kind": "implement", "phase": "working",
               "startedUtc": "…", "elapsedSeconds": 892,
               "artifact": "artifacts/answer.json", "maxTurns": 60,
               "message": "Now the full scan on the first archive-capable endpoint." },
  "tasks":  [ { "id": "2da52d17", "kind": "implement", "startedUtc": "…", "seconds": 138,
                "phase": "submitted", "submissionId": "194e31c25742",
                "answer": "630 — 63.0 °F at KNYC, Central Park" } ],
  "reputation": { "accepted": 4, "rejected": 0, "tags": ["verification:structural"],
                  "scannedFromBlock": 26013352, "scannedToBlock": 26020322,
                  "rows": [ { "block": 26020304, "outcome": "accepted",
                              "tag1": "verification:structural", "tx": "0x…",
                              "jobId": "f4e7cc3d-…" } ] },
  "cost":   { "runs": 7, "turns": 259, "inputTokens": 518, "outputTokens": 183169,
              "cacheWrite": 777267, "cacheRead": 11570248, "model": "claude-opus-5" },
  "sources": { "heartbeat": {"ok": true},
               "chain": {"ok": false, "reason": "no keyless RPC answered"} }
}
```

**`sources` is load-bearing, not decoration.** Each block can fail independently — the chain read in
particular fails often, because it depends on keyless RPCs. MaxPane's rule is that a dead source
shows an explicit unavailable behind an `as of HH:MM` marker, never a stale number as live and never
a *false* degradation. `sources` is how the writer distinguishes "zero" from "could not look", and a
block whose source is `ok: false` **must render unavailable even when stale values are present**.

---

## 4. Panels

Six surfaces: one hero plus five panels, matching the SURFBOARD body budget as a starting point.
Sweep the pin; do not assume it fits.

**HERO — is my seat alive.** `state`, `uptime`, idle-or-working, `eligibility`, and
`IDMD #<tokenId> · agent <agentId>`.

Three visual states, and getting them right *is* the panel: green when alive; **red** when
`state != "alive"` or the container is not running; **amber with the age shown** when
`generatedAtUtc` is older than ~10 minutes. A monitor that looks calm over a dead daemon is worse
than no monitor — and staleness here means the writer stopped, which the reader cannot otherwise
detect.

**1 · CURRENT WORK.** `current.taskId`, `phase`, elapsed, `artifact`, `maxTurns`, and the agent's own
last `message`. When `current` is null, name the last task from `tasks[0]` and when it went out.
*Earns its slot:* it is the only place the machine's present activity is legible, and the agent's own
sentence is the most informative line the daemon produces.

**2 · TASK LEDGER.** `tasks[]`: start, id, duration, phase, submission id, and what it answered.
*Earns its slot:* **the daemon keeps no task history** — this is the only record that exists.
Label the window: it is reconstructed from a log that rotates, so it is recent history, not all time.

**3 · REPUTATION.** `accepted` / `rejected`, the tag set, and **the block range actually scanned**,
so a count is checkable rather than merely asserted. Show `rows` newest-first with explorer links.
*Earns its slot:* it is the seat's permanent public record. Keep "submitted" and "accepted" visually
distinct — conflating them would flatter the machine.

**4 · COST.** `runs`, `turns`, output and cache tokens, and the model. *Earns its slot:* every task
spends the operator's own subscription, and nothing else tells them so. **Show tokens, not
currency** — no price is recorded anywhere, so a figure in dollars would be an estimate dressed as a
reading.

**5 · MACHINE.** `container` plus `fleet`: image, restart policy, restarts, memory against limit,
CPU, pids; and online/enrolled/working/queued. *Earns its slot:* it answers "is it me or is it the
swarm" in one place — an idle seat beside an empty queue is not a fault, and a restart count that
climbs is.

---

## 5. Data contract

`data/seat_models.py`, frozen first: key list plus `WIDGET_SIGNATURES`. Prefix every key `seat_*`.

`data/seat_manager.py::fetch_and_compute()` returns one flat dict, per
`data/talismans_manager.py:124-283`: per-source `try` with `self._error_count += 1`, **`None` not
`0`** for "could not look", and injection seams `client=`, `cache=`, `cache_path=`.

There is exactly **one** source, so there is no parallel-fetch story — but there are several
independently-failing *blocks* within it, and they get the same treatment as separate sources would.

`analytics/seat_signals.py` is pure: staleness classification, duration rollups, accepted-rate,
token aggregates. Inject the clock (`now=`/`now_ts`) — staleness is the whole point of this view and
it cannot be tested against a real clock.

**No cache tier is needed.** The source is a local file that a writer refreshes every ~5 minutes;
re-reading it is free and caching it would only add a second staleness axis. Keep
`~/.maxpane/seat_cache.json` for any persisted *series* (token spend over time, accepted count over
time) that the file itself does not carry.

---

## 6. Registration — the six surfaces plus the copies

Order matters: `app.py` → `__main__.py` → `GAMES`. Growing `GAMES` first turns the registration
tests red.

1. `app.py` — `_GAME_CYCLE` (`:216`), the manager in `MaxPaneApp.__init__` (`:84-137`), the
   `_prefetch_manager` map (`:159-182`), and an `elif game_id == "seat"` branch in `_launch_game`.
2. `__main__.py:256` — `--game` choices.
3. `screens/game_select.py:11-36` — `("9", "seat", "SEAT", "…")`. Keys must stay contiguous
   `1..N`; today `1..8` are taken and several hidden entries sit between them as comments.
4. `README.md` table and `.claude/rules/dashboard-registry.md` table.
5. **Four copies of `MANAGER_ATTRS`** — `tests/test_app_startup.py`, `test_surf_registration.py`,
   `test_game_select_quit.py`, `test_curator_registration.py`. Miss one and a headless test
   overwrites the developer's real `~/.maxpane/*.json`.
   `test_curator_registration.py::test_every_copy_of_manager_attrs_names_every_manager_the_app_builds`
   catches it.
6. `ALL_GAMES` in `tests/test_app_startup.py`.

`app.py`, `__main__.py`, `screens/game_select.py` and `themes/minimal.tcss` are the owner-gated
shared files: one owner, edited late.

---

## 7. What this must honour

- **Read-only, and more so than usual.** This dashboard reads a file describing a machine that
  executes remote code. It never writes to it, never calls `docker`, never touches the container.
- **Keyless.** The status file is local; nothing here needs a key. If the chain block inside it is
  absent, that is the writer's problem to report and this view's problem to display honestly.
- **No test touches the network** — and here, no test touches a real status file either. Commit
  fixtures: a healthy file, a stale one, one with `sources.chain.ok = false`, one that is malformed,
  and the absent case.
- **Never render a stale value as live.** The single most important behaviour in this dashboard.
- **Third-party strings are hostile.** `current.message`, `tasks[].answer` and `tags` all originate
  from a remote control plane and a model's output. Route every one through
  `widgets/markup_safety.safe_markup`.
- **Addresses get the copy icon and explorer link**, one `EXPLORER` declaration for the package
  (`widgets/seat/_chain.py`, `ETHEREUM`).
- **Layout pin.** New body, new sweep, `#:` block beside the constant. Read
  `.claude/skills/terminal-layout/SKILL.md` first.

---

## 8. The mode-B writer already exists

Built 2026-09-20 in `/Library/Vibes/aidude`: `bin/aid worker-page --json` writes
`data/surf/worker-status.json` (~6 KB) against the schema in §3, from the same gathered sources as
its HTML page, on the same 5-minute launchd timer. Verified: every field populated, `sources` all
`ok`, and an assertion that the device private key is absent.

**Treat the schema as the contract between two repos.** It is versioned (`schemaVersion: 1`); when
the writer is absent or older, degrade rather than guess.

Modes A and C are this repo's to write. **Build mode B first** — it is testable from a fixture
today, on the machine the work will actually be done on — then mode A against the same normalised
shape, on the VPS where its paths exist. Mode C only if the host filesystem ever stops being ours.

---

## 9. What I do not know

- **Whether a machine ever runs two seats.** One IDMD authorises one active device, so one file per
  machine holds today. If that changes, the path needs a seat id.
- **Mode A's file contents are asserted, not measured.** The paths and the container PID were read
  from the live daemon, but none of them exist on macOS, so the shape of
  `<id>-json.log` and the readability of the volume directories must be confirmed on the VPS before
  the reader is written. Budget for the log being rotated by Docker (`max-size`/`max-file`), which
  would make it a window rather than the full history — the same trap that made `docker logs
  --tail 400` return a stale segment on 2026-09-20.
- **The permission decision for mode A** — root, ACL, or a privileged copier — is unmade, and it
  changes the install doc more than the code.
- **How much task history the mode-B writer can offer.** It reconstructs from a container log that rotates;
  a small `--tail` was measured to return the current segment while a large one silently returned a
  *previous* segment three hours stale. So `tasks[]` is a recent window of unspecified depth, and the
  panel should say so rather than implying completeness.
- **Whether `buildMismatch` matters.** The daemon warns when the control plane runs a newer commit
  than the published worker release. It has been true continuously without any observed effect.
  Surface it; do not dramatise it.
