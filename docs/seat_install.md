# PEPEPANE on the VPS — installing pepepane and imd-dashd on seats #7 and #3

The owner's runbook for spec §12.1. Everything here is `deploy/vps/install.sh` and `deploy/vps/probe_seat_host.sh`
with the reasons attached; the scripts are the truth, this page is the order to run them in. Nothing below is done
by an agent: the ssh login to imd-vps is root. The three owner decisions this depends on, spec §16 #2 (install route a),
#4 (worker drop-in) and #17 (one measurement run), were approved on 2026-09-26.

## What gets installed

| path | owner:mode | from |
|---|---|---|
| `/opt/imd-dash/venv/` (textual 8.2.8 + closure + the fork wheel) | root:root 0755 | `deploy/vps/wheels/` + `requirements.lock`, `pip --require-hashes` |
| `/usr/local/bin/pepepane` → `/opt/imd-dash/venv/bin/pepepane` | root symlink | the only PATH change; a `.bashrc` line would never reach `ssh host cmd` |
| `/opt/imd-dash/broker/imd_dashd/*.py` | root:root 0755 / 0644 | `imd_dashd/` verbatim; the staged tree is checked with `sha256sum -c` before step 1, the copies again after step 4 |
| `/opt/imd-dash/MANIFEST.sha256`, `/opt/imd-dash/requirements.lock`, `/opt/imd-dash/wheels/` | root | for the probe's re-check and future re-installs |
| `/etc/systemd/system/imd-dashd.socket`, `imd-dashd.service` | root 0644 | `deploy/vps/`; the socket is enabled (`sockets.target`), the service is spawned on connect |
| `/etc/systemd/system/imd-dashd.service.d/10-seat.conf` | root 0644 | rendered by `install.sh` step 5 from `--seat`: gives the broker its seat for the gate's fresh standing read (spec §11); not in the MANIFEST (generated) |
| `/etc/systemd/system/user-<uid>.slice.d/50-pepepane.conf` | root 0644 | `MemoryMax=256M`, `CPUQuota=50%` for every process of the `imd-dash` login |
| `/etc/ssh/sshd_config.d/10-imd-dash.sshd.conf` | root 0644 | `Match User imd-dash`: no TCP/agent/X11 forwarding, TTY yes |
| `/etc/systemd/system/imd-worker.service.d/20-hide-dash.conf` | root 0644 | only with `--worker-dropin` (§16 #4); live after a drained restart |
| user `imd-dash` (groups: `systemd-journal` only), `/home/imd-dash` 0700, `.ssh/authorized_keys` 0600 | | no sudoers, no polkit |
| `/home/imd-dash/.config/pepepane.toml` | imd-dash 0644 | `host unit broker seat agent` — configuration, never a secret |
| `/var/log/imd-dash/audit.jsonl` | root 0700 dir (`LogsDirectory`) | written by the broker; read by the TUI only through `audit-tail` |

Not touched: `imd-worker.service` itself (only the optional drop-in), `/home/imd-worker`, `config.json`, journald.

## Before you start

The round-9 screen minimum is **131×40**, measured on healthy and expanded worst payloads.
Every body needs 131 columns; the measured row minima are SEAT 40, LIVE 30, CONFIG & SKILLS 22,
RECORDS 20, NODES 20 and CONTROL 29. SEAT sets the screen's height minimum. The full table tiers
clear at 126 columns for LEDGER, 108 for RECORDS and 119 for NODES, all within the screen pin.
Below a body's height minimum it scrolls and `‹ taller` lights up; narrower widths advertise
omitted content with `‹ widen`.

Gate step (c) accepts a terminal latest lifecycle line or a successful empty history read (owner D1); only a failed or unreadable lifecycle read is `gate_unknown(lifecycle)`, and stale Mac history remains unknown.

The standing child allows two 8-second attempts inside a 12-second overall child deadline. A slow first attempt can exhaust that budget; the gate then reports `local-only` and requests the typed acknowledgement. Apply admits the request within 5 seconds, permits bounded gate reads until its 15-second execution deadline, and queues systemd with a 3-second timeout. Acknowledged local-only fallback can still restart after a 12-second standing timeout; slow exhausted gates refuse with the spent-plan status. Use `pepepane --offline` when intentionally avoiding the plane.

1. Spec §16 #2 is decided: route **a**, `apt-get install python3.<minor>-venv` for the declared interpreters 3.12 and 3.14.
   Seat #7 uses `python3.14-venv`; seat #3 uses `python3.12-venv`. Route **b** needs
   no apt: `python3 -m venv --without-pip` plus `pip-26.2.1-py3-none-any.whl` passed as `--pip-wheel` (fill7 §3). The
   VPS python has no `ensurepip`, so a plain `python3 -m venv` fails until one of the two has happened.
2. Generate an ssh key for the daily account and keep the private half on the Mac: `ssh-keygen -t ed25519 -f ~/.ssh/imd-dash`.
   The public half goes to the installer as `--authorized-keys`.
3. Pick an idle gap for step 7 later (the drop-in needs a drained restart of the worker) — or skip step 7 for now.

## Build on the Mac (network here, never on the VPS)

~~~sh
cd /Users/banse/codex/maxpane && git switch pepepane
PYTHON=/Users/banse/codex/maxpane/.venv-pepepane/bin/python scripts/build_wheels.sh --out deploy/vps
# -> deploy/vps/wheels/ (22 wheels), deploy/vps/requirements.lock, deploy/vps/MANIFEST.sha256, dist/seat-deploy-<sha>.tar.gz
env -u NO_COLOR HOME=$(mktemp -d) PYTHONDONTWRITEBYTECODE=1 .venv-pepepane/bin/python -m pytest -p no:cacheprovider -q tests/test_seat_deploy_files.py
~~~

The guard must be green before staging: it proves the lock matches `pyproject`, every lock line has a hash, the
MANIFEST names every broker file and matches the tree byte for byte, and the wheel hash is the same in the lock and
the MANIFEST (`deploy/vps/VERIFY.md` says what that does and does not prove). Rebuild at the commit you deploy — the
fork wheel's hash changes with every package commit.

The archive contains both `pydantic_core` ABIs, `cp312` and `cp314`; pip selects the compatible one.
Both interpreter resolutions are seeded from the committed lock and must agree on package versions.
The build rejects an unlisted wheel hash or a missing ABI before packing. A real install requires
`/usr/bin/python3`, `python3` on PATH and any existing venv to agree on a supported major/minor version.
Route a suspends needrestart and uses a noninteractive apt invocation.
For a Mac preview, pass `--dry-run --dry-run-python-version 3.12` or `3.14`; that override is refused
on a real run. Without it, an unsupported local interpreter produces a warning and a generic tooling step.

## Seat #3 (Ubuntu 24.04)

Use the same archive on `imd-vps3` with `--seat 3 --agent 52082` and Python 3.12.3.
The owner's 2026-10-03 apt simulation for `python3.12-venv` measured **3 packages, 0 upgrades**.
Route b remains available for both interpreters but is unmeasured on Ubuntu 24.04.
The worker runs Claude Code with concurrency 3 and uid 1001; the broker resolves `imd-worker` by name.
Claude hints come from `~/.claude/CLAUDE.md`, and ExecStart supplies the initial sessions runtime.
Install without `--worker-dropin`: that step still needs the owner's Claude Code A/B under
`ProtectProc=invisible`. Run the probe after installation; section 20's drained restart from CONTROL
belongs in a later idle gap. Seat #7 keeps its approved worker drop-in and its Python 3.14 venv.

## Stage and install

~~~sh
scp dist/seat-deploy-<sha>.tar.gz ~/.ssh/imd-dash.pub imd-vps:/root/
ssh imd-vps 'mkdir -p /opt/imd-dash/src && tar -C /opt/imd-dash/src -xzf /root/seat-deploy-<sha>.tar.gz'
ssh imd-vps 'bash /opt/imd-dash/src/deploy/vps/install.sh --dry-run --authorized-keys /root/imd-dash.pub'   # read the plan
ssh imd-vps 'bash /opt/imd-dash/src/deploy/vps/install.sh --authorized-keys /root/imd-dash.pub'             # steps 1-6 (+8 prints)
~~~

`--dry-run` prints every command with a `[dry-run]` prefix and runs none; it is how you read the plan. The real run
is repeatable — each run forcibly reinstalls the fork, verifies its installed bytes, and fills missing dependencies. The steps, in the order the script prints them:

| step | what | re-run behavior | flags |
|---|---|---|---|
| 1 | venv tooling | `dpkg -s python3.<minor>-venv` first (host interpreter) | `--route a` (default) / `--route b --pip-wheel FILE` |
| 2 | user `imd-dash` in `systemd-journal` only, home 0700, `authorized_keys` 0600 | `id -u imd-dash` first | `--authorized-keys FILE` |
| 3 | `/opt/imd-dash/venv`, `pip install --no-index --find-links /opt/imd-dash/wheels --only-binary=:all: --require-hashes -r requirements.lock`, `ln -sfn … /usr/local/bin/pepepane` | forced fork reinstall with `--force-reinstall --no-deps` and its one-entry hashed lock first, then the full lock; post-install byte check; `ln -sfn` | |
| 4 | copy `imd_dashd/*.py` to `/opt/imd-dash/broker/imd_dashd/`, re-verify the copies (the staged tree's `sha256sum -c --strict MANIFEST.sha256` runs before step 1: a mismatch installs nothing) | `install` overwrites identical files | |
| 5 | the two units, the broker's `imd-dashd.service.d/10-seat.conf` (`ExecStart=` reset + `… imd_dashd.py --seat N`, so the gate reads standing for this seat), `daemon-reload`, `systemctl enable --now imd-dashd.socket` | enable is idempotent; the drop-in is rewritten identically | `--seat 7` (default) |
| 6 | slice drop-in, sshd Match block (`sshd -t` before `systemctl reload ssh`), `pepepane.toml` | overwrites identical files | `--seat 7 --agent 51075` (defaults) |
| 7 | worker drop-in `20-hide-dash.conf` + `daemon-reload` — **never a restart** | skipped without the flag | `--worker-dropin` (§16 #4, approved 2026-09-26: pass it at an idle gap) |
| 8 | prints the probe command | prints only | |

Exit codes: 0 done; 1 a precondition failed (message on stderr: not root, bad route, missing `--pip-wheel`, incomplete
staged tree, MANIFEST mismatch — the staged-tree check runs before step 1, so a mismatch installs nothing); the tree
check runs from the unpacked root, so the MANIFEST's repo-relative paths resolve.

## Verify (spec §14 "Only on the VPS", owner decision §16 #17)

~~~sh
ssh imd-vps 'bash /opt/imd-dash/src/deploy/vps/probe_seat_host.sh' > /tmp/seat_install_probe.md      # add --skip-doctor to save a runtime turn
~~~

Then paste the output into `docs/seat_install_probe.md` (replacing the placeholder body; keep the headings the probe
emits) and re-run the guard. The probe's first two sections are the negative/positive connect pair that proves
`DirectoryMode=0755` + `SocketMode=0660` + the drop-in; then the journal read, the deliberately stale `--after-cursor`,
the lifecycle grep/filter-order and no-match behavior, `compression.zstd`, `pepepane --once --offline` through the symlink, the projection canary, `status` and `doctor`
through the broker with each transient child's `memory.peak`, one `plan restart` (never applied), and the root checks
(MANIFEST, `ls /home/imd-dash` fails as `imd-worker`, `sshd -T`, the slice's `MemoryMax`, sysstat `HISTORY`). The last
section is the one drained restart you do by hand at an idle gap, recording the audit lines, the `verify` output and
the slice's `memory.peak`.

Restart, stop and start use `--no-block`: `outcome: applied` means systemd queued the job, and only `verify` confirms completion; a failed start shows no `runtimes:` within 30 seconds. After a lost reply or timeout, CONTROL shows “outcome unknown — checking verify” and retries verification through the client deadline and for at least 10 seconds after the lost reply; if verification remains unavailable, it asks you to check LOG and audit before planning afresh, saying “plan state unknown” unless a reply or verification watch proved the plan was spent. An explicit spent-plan refusal means you must press the verb to create a new plan; CONTROL never re-plans or re-applies automatically.

Stop verification can take up to 110 seconds while the unit is deactivating or after `shutting down`; without either sign of shutdown, its window remains 30 seconds.

## Daily path

~~~sh
ssh -t imd-dash@imd-vps pepepane                    # the TUI; q quits, c selects CONTROL
ssh imd-dash@imd-vps pepepane --once --offline      # the v2 status document as JSON, no TUI, no api.imd.fun -- usable at 3 a.m. over plain ssh
ssh imd-dash@imd-vps pepepane --once | head -c 600  # same, with the API tiers
~~~

The root login stays for installs only; `runuser … imd status` from root is no longer the way to look at the seat.

### Six dashboards and keys

LIVE is selected at startup. Click a hero card or use `1`–`6` to select SEAT, LIVE,
CONFIG & SKILLS, RECORDS, NODES or CONTROL. The green border marks selection; the label and
title alert report health independently. Selection focuses the body's main table or LOG.

| Where | Keys | Action |
|---|---|---|
| Every dashboard | `c`, `esc` | Select CONTROL; return to LIVE when no prompt is open |
| Outside CONTROL | `r` | Refresh |
| SEAT, LIVE, RECORDS | `enter` | Open the selected ledger row, shown JOB or selected record |
| LIVE | `h`, `n` | Toggle heartbeat lines; step through running jobs |
| CONFIG & SKILLS | `tab`, `space` / `enter` | Switch tables; plan the selected skill or systemd boot toggle |
| RECORDS | `f`, `m` | All / not completed; add 20 rows, up to 400 |
| NODES | `w` | All history / seven days |
| CONTROL | `r`, `d`, `s`, `S` | Restart, drained restart, stop, start |
| CONTROL | `b`, `o`, `D`, `x` | Boot toggle, kill orphans, doctor, cancel drain |
| Every dashboard | `q`, `t` | Quit, cycle theme |

Capacity and tier rows show their change paths but remain read-only this round. Container boot
shows the restart policy and is read-only. The old skill-id prompt and tall-LOG shortcut are gone.
While a confirmation is open, ordinary keys belong to its input and Enter submits; Escape cancels.
Clicking another card drops an unconfirmed plan. An action already applying or verifying continues,
including while the cached detail popup is open. The strip shows the verb, exact target command and warning.

JOB and detail show only sanitized API question/result text from the ledger cache, plus local metadata.
Literal brackets and line breaks survive. RECORDS shows bounded previews; full text remains available
for the newest 400 records. Older text says `text expired`. Busy replies back off from 60 to 600 seconds;
cached ledger facts stay visible. Offline mode makes no API reads and serves the cache.


## Runtime configuration

`/home/imd-dash/.config/pepepane.toml` (written by step 6):

~~~toml
[pepepane]
host = "systemd"
unit = "imd-worker.service"
broker = "/run/imd-dash/broker.sock"
seat = 7
agent = 51075
~~~

Precedence inside `pepepane`: command-line flags, then `PEPEPANE_HOST` / `PEPEPANE_UNIT` / `PEPEPANE_BROKER` /
`PEPEPANE_SEAT` / `PEPEPANE_AGENT` / `PEPEPANE_OFFLINE` / `PEPEPANE_CONFIG`, then this file, then
`~/.maxpane/config.toml` `[seat] token_id`, then defaults. `agent` is the `--offline` fallback for the agent id (the API's
`standing.enrollment.agentId` is the only other source; `imd status` prints none). Environment variables are
configuration, never secrets (MaxPane rule).

## What runs as what

- **TUI** (`pepepane`): uid `imd-dash`, in `user-<uid>.slice` with `MemoryMax=256M` / `CPUQuota=50%`. Reads the journal
  (group `systemd-journal`), `systemctl show`, cgroup files, `/proc`, `sar`, and `api.imd.fun`; writes only `~/.maxpane`
  (`seat_ledger.sqlite`, `seat_tail.json`, `config.toml`, `maxpane.log`). Never opens `config.json`, `auth.json`,
  `tools.env` or `.credentials.json`.
- **Broker** (`imd-dashd.service`, socket-activated): root, `/usr/bin/python3 -I`, stdlib only, `MemoryMax=128M`,
  `CPUQuota=50%`, `TasksMax=64`; exits after 600 s idle unless a drain is armed. `ping` answers `imd-dashd 0.1.5` as
  `version`. Audit at `/var/log/imd-dash/audit.jsonl`. The system service has no `User=` or `Group=`:
  it defaults to root. On measured systemd 259.5, explicit `User=root` with `NoNewPrivileges=yes` and seccomp
  hardening removes `CAP_SETUID`; implicit root keeps privilege dropping working with the same bounding set and
  empty ambient capabilities.
- **In-process children** (projection, `ls outbox`, work-stat, hints-stat, auth-mtime, the gate's standing read): dropped
  to `imd-worker` with `Popen(user=, group=, extra_groups=[])`, `cwd=/tmp`, and exactly this environment — `HOME=/home/imd-worker`,
  `PATH=/opt/imd-worker/bin:/opt/imd-worker/node/bin:/usr/local/bin:/usr/bin:/bin`, `NO_COLOR=1`, `LANG=C.UTF-8` — nothing else
  (spec §4.1a; `node` is not on root's PATH, and `runuser` from root needs exactly this PATH or `imd` dies with
  `env: 'node': No such file`).
- **Transient children** (`imd whoami|status|skills|tools|doctor`, `imd skills add|remove`, the session summariser):
  `systemd-run` units `imd-dash-<verb>-<seq>` as `imd-worker` with the worker unit's own posture plus
  `BindReadOnlyPaths=/opt/imd-dash/broker`, the same four environment variables, `MemoryMax=512M`, `TasksMax=64`,
  `RuntimeMaxSec` per verb (`status` 30 s, `doctor` 120 s, sessions 60 s). An OOM or hang lands in the child's cgroup,
  never the broker's. Commands use the absolute `/opt/imd-worker/bin/imd` because `systemd-run` resolves commands
  with the broker's PATH before applying the child environment. All `InaccessiblePaths` entries keep `-` prefixes:
  `ProtectHome=tmpfs` makes the dash home absent during namespace setup; without the prefix systemd exits 226.
  If the broker cannot read the worker's `IPAddressDeny` at start, these verbs answer
  `child_posture_unavailable` and the probe's `ping` shows `posture_ok: false`. `drop_ok: false` means effective
  uid/gid-drop capabilities are missing and in-process reads and gated actions refuse with `child_drop_unavailable`;
  `drop_ok: null` means the status was unreadable and the kernel still decides whether the drop succeeds.

## Footprint budget (spec §12.1)

`MemoryMax=256M` for the TUI slice is 1.8× the 142 MiB cold peak measured for the *full* MaxPane app (fill7 §4); the lean
`pepepane` entrypoint is asserted ≤ 160 MiB in CI (`scripts/pty_footprint2.py`) and its real `memory.peak` on this box is
recorded once by the probe. Broker 128M (idles ≈ 20 MiB); each transient child 512M (`imd doctor` ≈ 120 MB). Caps are
ceilings, not reservations. The VPS worker measured 116–189 MB on a 3,828 MB box whose worker cap is 3 G.
The actual lean Mac cold peak measured on 2026-09-27 was 58.8 MiB (Python 3.11.15, Textual 8.2.8, libproc fallback);
this is separate from the historical full-app 142 MiB result. The final round-9 fixture/offline run on 2026-10-04 measured 62.3 MiB with all six dashboards visited, using the same libproc physical-peak fallback. The owner measured the live VPS TUI slice peak at 114634752 bytes on 2026-10-03, under its 268435456-byte limit; see `docs/seat_install_probe.md` section 20.

## Updating the fork on the VPS

Rebuild at the new commit on the Mac (`scripts/build_wheels.sh --out deploy/vps`, guard green), stage the new tarball
under a new `/opt/imd-dash/src` name, and quit every pepepane session before re-running `install.sh`.
Before installation, check that `ping` shows `drain_armed: false` and `in_flight: null`.
Wait for any action to finish and complete or cancel an armed drain first: stopping the broker drops an armed drain.
Then run `systemctl stop imd-dashd.service` if active, leaving its socket in place, and run the installer.
Step 3 performs a forced fork reinstall, even at the same package version, then resolves the full lock and runs a
post-install check against the staged wheel's RECORD hashes by hashing installed file bytes. Require both the pip
reinstall success and the post-install check's matched-file count and short wheel identity in the output.
A live TUI retains old modules and may import new ones lazily; during reinstall the package is briefly absent.
The installer warns about matching live sessions but never kills them. Steps 4–5 copy the broker and units.
After installation, confirm `ping` reports `imd-dashd 0.1.5`, then start a fresh `pepepane`.
Re-run the probe, especially p09–p15. No worker restart is needed unless the drop-in changed.
Use `--seat 7 --agent 51075` on imd-vps (Python 3.14) and `--seat 3 --agent 52082` on imd-vps3
(Python 3.12); the archive contains both ABIs. Seat #3's worker drop-in and probe section 20 remain
separate owner-controlled work; do not add `--worker-dropin` to that install.

## Rollback / uninstall

~~~sh
systemctl disable --now imd-dashd.socket; systemctl stop imd-dashd.service
rm -f /etc/systemd/system/imd-dashd.socket /etc/systemd/system/imd-dashd.service
rm -rf /etc/systemd/system/imd-dashd.service.d
rm -f /etc/systemd/system/imd-worker.service.d/20-hide-dash.conf        # then a drained restart of the worker
rm -rf /etc/systemd/system/user-"$(id -u imd-dash)".slice.d
rm -f /etc/ssh/sshd_config.d/10-imd-dash.sshd.conf && sshd -t && systemctl reload ssh
systemctl daemon-reload
rm -f /usr/local/bin/pepepane; rm -rf /opt/imd-dash /var/log/imd-dash
# userdel -r imd-dash    # only if the account is not wanted again; the home holds the sqlite ledger
~~~

## What breaks at 3 a.m. and who notices (spec §12.1)

Broker crashes → socket activation restarts it on the next connect. TUI not running → nothing to break. journald
vacuums → the reader detects the gap from data (first entry vs the saved stamp + 60 s), falls back to `--since` and shows a
gap footer; the sqlite ledger is the durable copy. Worker stops → `Restart=always` brings it back unless it was stopped
on purpose; the hero shows `boot: disabled` while `UnitFileState=disabled` (§16 #7, decided yes 2026-09-26: the owner
already enabled the service on 2026-09-26; future disabled states remain visible and the `enable-boot` verb is available). The journal cap resolved at boot (~347 MiB, fill8 §2) is surfaced on MACHINE and re-resolves
after the next journald restart (§16 #9).
