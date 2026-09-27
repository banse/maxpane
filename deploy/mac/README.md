# PEPEPANE on the Mac — seat #420 (Docker Desktop, Claude Code) — parity install

Spec §12.2. The same `pepepane` entrypoint as the VPS, **no broker process**: `LocalDockerBroker` runs in-process and
implements the identical `BrokerProtocol` (verb enum, plan → apply → verify, single-use plan ids, one write in flight,
audit at `~/.maxpane/seat_audit.jsonl` 0600). There is no uid separation on the Mac; the mitigation is shape (enum, fixed
argv, timeouts, audit), not privilege.

## Install (into its own venv, from the pepepane checkout)

~~~sh
cd /Users/banse/codex/maxpane && git switch pepepane
uv venv .venv-seat --python 3.11                          # or 3.14; textual==8.2.8 either way (fill7 §5)
uv pip install --python .venv-seat/bin/python -e '.[seat]'
env -u NO_COLOR .venv-seat/bin/pepepane --version
~~~

Installing as a distribution (not `PYTHONPATH`) is what makes `importlib.metadata.version` resolve; without it the
status bar reads `v0+unknown` and the 134-column pin breaks (fill7 §5).

## Run

~~~sh
env -u NO_COLOR .venv-seat/bin/pepepane --host docker --container imd-worker              # the TUI
env -u NO_COLOR .venv-seat/bin/pepepane --host docker --container imd-worker --once       # the v2 document as JSON, no TUI
env -u NO_COLOR .venv-seat/bin/pepepane --host docker --container imd-worker --offline    # no api.imd.fun; every broker plan is local-only
env -u NO_COLOR .venv-seat/bin/pepepane --host fixture --fixture tests/fixtures/seat/healthy/   # dev mode: replayed log, FakeBroker, fixture API
~~~

Nothing new is mounted into the container. The aidude launchd jobs (`worker-page`, `worker-notify`) keep running —
pepepane reads none of their files (`worker_events.jsonl` is not a source, spec §5.6).

## What is different from the VPS (spec §4.2, §12.2)

- **Tail**: `docker logs -f --tail 200 --timestamps imd-worker` is the only trusted "latest" (the 2026-09-20 stale-segment
  trap); the one-shot `--since` backfill is untrusted and discarded whole when its newest stamp is older than the
  watermark. The follower exits at every container restart and re-attaches with backoff.
- **Every bare docker call** (`inspect`, `stats`, `logs`, `restart`, `stop`, `start`) runs as
  `subprocess.run([...], timeout=25)` in a thread; a `docker exec` wrapped in the container's `timeout -s TERM -k <g> <s>`
  gets a host belt of `g + s + 5` instead (doctor 135 s, skills-set 40 s, reads 30–35 s), so the in-container limit always
  fires first. A timeout opens a 5-minute breaker for that verb only (`docker inspect` timed out in 2 of 3 writer cycles
  on 09-26); an inspect timeout turns UNIT amber, never the hero — the tail owns liveness.
- **Every `docker exec` that runs `imd`, `python3` or `node`** is wrapped **inside** the container with coreutils
  `timeout -s TERM -k <grace> <secs>`, because killing the `docker exec` client does not stop the exec'd process (it
  would keep running under the worker's cap holding the runtime lock — the 35 h hung-probe class the VPS exhibited).
- **Container-reported values**: the `imd` binary lives on the `imd-npm` volume owned by uid `imd`, the same uid every
  task runs as, so `imd status|skills|whoami` and the `python3 -` projection (`imd_dashd/projection.py` piped into the
  container) are tamperable text. Every such value carries
  `trust: "container"` in the document and a `(container)` suffix on screen, and **never feeds a gate or an allowlist**
  (the gate uses the tail, the plane and `ls outbox` only).
- **`--force` is disabled** in v1: PID 1 is node without `--init` and `StopTimeout` is 10 s, so `gracefulStopPossible` is
  false, and v1's `LocalDockerBroker` refuses `--force` unconditionally. Recreating the container with
  `--stop-timeout 45 --init` (owner decision spec §16 #8, at the next idle gap) is necessary but not sufficient: switching the refusal to the
  `gracefulStopPossible` check is `docs/seat_followups.md` item 13. Idle-gated restart/stop are allowed (measured 0.6–2.0 s).
- **Verbs** map to `docker restart -t 30` / `stop -t 30` / `start`, `docker exec imd-worker timeout -s TERM -k 10 25 imd skills …`,
  `docker exec imd-worker timeout -s TERM -k 10 120 imd doctor`, `docker exec imd-worker kill -TERM -<pgid>`; boot enable is
  n/a (`--restart unless-stopped`).
- **Persistence**: `~/.maxpane/seat_ledger.sqlite` (the durable copy — the json-file log dies with `docker rm`),
  `~/.maxpane/seat_tail.json`, `~/.maxpane/seat_audit.jsonl`.

## Owner items before trusting more on this host (spec §16 #8, #18)

1. Recreate the container at an idle gap with `--stop-timeout 45 --init` (the three named volumes carry key, login and
   runtime — aidude runbook §2.1), so `--force` can ever be enabled (v1 still refuses it until follow-up item 13 lands).
2. Make the npm prefix root-owned/read-only in the next image (#18): either bake it into the image and accept `docker rm` plus
   recreate as the update step, or keep the `imd-npm` volume but run `imd update` as root at idle and chown the prefix.
   Even after it, v1 keeps every CLI-fed value `(container)` (`LocalDockerBroker.trust()` is fixed); dropping the tag is a
   later change (`docs/seat_followups.md` item 13).
