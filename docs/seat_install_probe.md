# PEPEPANE install probe -- ubuntu
Build a8912d6, measured 2026-10-02; sections 1–19 are the probe’s own output.

run 2026-10-02T20:43:12Z UTC as root; deploy tree /opt/imd-dash/src; spec §14 "Only on the VPS" in order; broker replies scrubbed of hex >= 32; doctor applied

## 1. connect(/run/imd-dash/broker.sock) as imd-dash succeeds (ping)

~~~
{"ok":true,"data":{"pid":686480,"version":"imd-dashd 0.1.2","uptime_s":5.6,"drain_armed":false,"in_flight":null,"posture_ok":true,"drop_ok":true,"drain":null}}
~~~

**result:** PASS -- connect + ping as imd-dash

## 2. connect(/run/imd-dash/broker.sock) as imd-worker fails (EACCES: 0660 root:imd-dash in a 0755 root dir)

~~~
connect failed: PermissionError 13
~~~

**result:** PASS -- EACCES for imd-worker (socket 0660 root:imd-dash)

(this is the worker uid outside its unit; inside the unit the drop-in also hides /run/imd-dash entirely)

## 3. journalctl -u imd-worker.service as imd-dash: 14-day read count (group systemd-journal)

~~~
lines: 49656
~~~

**result:** PASS -- imd-dash reads the unit journal (systemd-journal group)

## 4. journalctl --after-cursor with a deliberately stale cursor: exit status and first entry vs the oldest

exit status: 0
first entries returned (__REALTIME_TIMESTAMP, MESSAGE head):
~~~
1790078400363692 Started imd-worker.service - IMD worker (Codex, seat #7).
1790078400629371 2026-09-22T12:00:00.628Z runtimes: codex codex-cli 0.155.1 (using codex, as aske
1790078400643060 2026-09-22T12:00:00.642Z execution profiles: none, foundry
~~~
oldest entry in the unit journal, for comparison:
~~~
1790078400363692 Started imd-worker.service - IMD worker (Codex, seat #7).
~~~
~~~
fallback --since "2026-10-02 20:33:14 UTC": exit 0, 1 JSON record(s)
~~~

**result:** recorded -- spec §5.1: a vacuumed cursor may exit 0 and seek to the oldest entry; the reader detects the gap from data (first entry vs lastTsUtc + 60 s), not from this exit status; the fallback re-attach's --since 'YYYY-MM-DD HH:MM:SS UTC' form must exit 0 here

## 5. journalctl lifecycle --grep: newest match before limit, pcre2 and no-match exit status

~~~
unfiltered history exit status: 0
lifecycle exit status: 0
lifecycle stdout: {"MESSAGE": "2026-10-02T20:17:05.522Z submission stored (27298bc85f91) \u2014 awaiting verdict", "__REALTIME_TIMESTAMP": "1790972225523079"}
lifecycle stderr: 
newest entry heartbeat: True
grep/pcre2: PASS
filter-before-limit: PASS
no-match exit status: 1
no-match stdout: 
no-match stderr: 
no-match acceptance: PASS
~~~

**result:** recorded -- filtered history must select the latest lifecycle even after a newer heartbeat; JSON no-match must report exit 1, empty stdout and empty stderr; no action was applied

## 6. systemctl show imd-worker.service as imd-dash (unprivileged D-Bus read)

~~~
ActiveState=active
SubState=running
UnitFileState=enabled
ActiveEnterTimestamp=Fri 2026-10-02 17:57:41 UTC
Restart=always
RestartUSec=30s
TimeoutStopUSec=30s
MainPID=679726
NRestarts=0
ExecMainStartTimestamp=Fri 2026-10-02 17:57:41 UTC
TasksCurrent=11
CPUQuotaPerSecUSec=2s
MemoryMax=3758096384
TasksMax=512
IPAddressDeny=100.64.0.0/10 [public-ip]/32 169.254.0.0/16 10.0.0.0/8 fc00::/7 [public-ip]/32 172.16.0.0/12 fe80::/10 192.168.0.0/16
KillMode=control-group
~~~

**result:** recorded -- gracefulStopPossible = KillMode control-group and TimeoutStopUSec >= 30 s; IPAddressDeny is what the broker copies onto its transient children (§4.1b)

## 7. cgroup counters of imd-worker.service as imd-dash (0644)

~~~
memory.current: 66969600
memory.peak: 177516544
memory.max: 3758096384
cpu.max: 200000 100000
~~~

**result:** recorded

## 8. python3 -c 'import compression.zstd' on /usr/bin/python3 (rollouts older than 7 days)

~~~
exit status: 0
compression.zstd ok 3.14.4
~~~

**result:** PASS -- .jsonl.zst rollouts will be readable

## 9. pepepane --once --offline as imd-dash (PATH via the /usr/local/bin symlink, imports, exit status)

~~~
exit status: 0, stdout bytes: 147348, stderr bytes: 0
~~~
~~~
schemaVersion 2 producer pepepane 0.1.0
host {'kind': 'systemd', 'unit': 'imd-worker.service', 'container': None, 'runtime': 'codex', 'hostname': 'ubuntu'}
startedAtUtc 2026-10-02T20:43:21Z completedAtUtc 2026-10-02T20:43:21Z
sources ok: {'tail': True, 'unit': True, 'broker': True, 'seat': True, 'status': True, 'skills': True, 'sessions': True, 'workstat': True, 'hints': True, 'auth': True}
dollar signs in the document: 0
hex64 values anywhere: 0 (must be 0: keys are truncated at fold time)
~~~
stderr head:
~~~
~~~

**result:** PASS -- the lean entrypoint imports and runs as imd-dash through /usr/local/bin/pepepane

## 10. broker ping (version, posture_ok, drain_armed, in_flight)

~~~
{"ok":true,"data":{"pid":686480,"version":"imd-dashd 0.1.2","uptime_s":14.8,"drain_armed":false,"in_flight":null,"posture_ok":true,"drop_ok":true,"drain":null}}
~~~

**result:** recorded -- version is the broker's VERSION; posture_ok false means IPAddressDeny could not be read and every runtime verb answers child_posture_unavailable

## 11. seat projection canary: no secret key name, no stray hex64, deviceKey == whoami

~~~
allowlist keys present: ['configMtimeUtc', 'deviceKey', 'inference', 'maxConcurrency', 'server', 'skillsOptOut', 'tokenId', 'tools', 'wallet']
keys matching the secret-name regex: 0 []
hex64 values: 1 stray (not deviceKey): []
deviceKey == whoami: True prefix 0df32ad4
PASS
~~~

**result:** see PASS/FAIL above (spec §13 projection canary: key names, sk-/eyJ, whoami match, no other hex64, exactly 8 source keys)

## 12. status through the broker as a transient unit, with the child scope's memory.peak

~~~
{"ok":true,"data":{"lines":["  config    /home/imd-worker/.identitymd/config.json","  server    https://api.imd.fun","  device    <hex64>","  token     7","  capacity  1 concurrent task(s)","  \u2717 claude  claude is not on PATH","  \u2192 codex   codex-cli 0.159.3","  tasks run on: codex","  offers: code, fuzz, research","  server    active: eligible \u2014 this machine can receive work"],"rc":0,"unit":"imd-dash-status-12"}}
~~~

systemd accounting for imd-dash-status-12 (journal, last 20 min):
~~~
~~~
no accounting line: below systemd's logging thresholds
~~~
sessions ok: True rc: 0 count: 995
~~~

**result:** recorded -- proves the transient-unit posture (ProtectHome=tmpfs, TemporaryFileSystem=/opt:ro, copied IPAddressDeny) lets imd status run; the peak sizes MemoryMax=512M

## 13. doctor through the broker (plan, apply, verify), with the child scope's memory.peak

plan:
~~~
{"ok":true,"plan":{"plan_id":"cbff13d68a7bc09e","verb":"doctor","argv":["/opt/imd-worker/bin/imd","doctor"],"expires_at":"2026-10-02T20:44:23Z","single_use":true,"preconditions":{"last_doctor_utc":null,"runtime_max_s":120},"warning":"spends one runtime turn and quota; leaves a work/doctor-* transcript; excluded from cost by cwd","inverse":null,"verify":{"verified_when":["exit 0"],"within_s":120,"connected_when":null,"reported_separately":true},"restart_required_after":false,"audit_seq":28}}
~~~
apply:
~~~
{"ok":true,"result":{"outcome":"started","exit_code":null,"cursor_before":null,"audit_seq":29,"preconditions":{"last_doctor_utc":null,"runtime_max_s":120},"unit":"imd-dash-doctor-14"}}
~~~
verify after 2 polls (5 s each):
~~~
{"ok":true,"data":{"verified":false,"connected":null,"verify_lines":["imd doctor \u00b7 daemon 0.1.0+2a548252","  config    /home/imd-worker/.identitymd/config.json","  server    https://api.imd.fun","  device    <hex64>","  token     7","  capacity  1 concurrent task(s)","  \u2717 claude  claude is not on PATH","  \u2192 codex   codex-cli 0.159.3","  tasks run on: codex","  offers: code, fuzz, research","  running a one-line prompt on codex, which takes a few seconds\u2026","  \u2713 git         git version 2.53.0","  \u2713 forge       1.8.3 \u00b7 the release the verifier runs","  \u2713 tool browse ready \u00b7 /opt/imd-worker/bin/browser-mcp","  \u2713 codex run   answered in 4.9s","  \u2713 work root   /home/imd-worker/.identitymd/work \u00b7 101.7 GB free","  \u2717 memory      3.7 GB","                fix: contract work needs about 4.0 GB; below that forge is killed during the daemon's own checks. Add memory or offer no contract work","  \u2713 config      /home/imd-worker/.identitymd/config.json \u00b7 owner only","  \u2713 plane       api.imd.fun \u00b7 build 0.1.0+69e7008b \u00b7 548 online, 571 enrolled","  \u2713 release     0.1.0+2a548252, the latest","  \u2713 socket      challenge from api.imd.fun in 189ms","  \u2713 github      github.com in 169ms","  the network says","  \u2713 enrollment  active \u00b7 token 7 \u00b7 agent 51075","  \u2713 presence    connected \u00b7 heartbeat 31s ago \u00b7 daemon 0.1.0+2a548252 \u00b7 runs on codex","  \u2713 standing    no failed runs in the last day","  \u2713 queue       nothing waiting \u00b7 548 online \u2014 the network is quiet, not this machine","  1 thing to fix: memory"],"cursor_after":null,"elapsed_s":10.2,"audit_seq":null,"reason":"exit 1","rc":1,"stderr_head":[]}}
~~~

systemd accounting for imd-dash-doctor-14 (journal, last 20 min):
~~~
imd-dash-doctor-14.service: Failed with result 'exit-code'.
imd-dash-doctor-14.service: Consumed 1.187s CPU time over 5.149s wall clock time, 139M memory peak.
~~~

**result:** recorded -- RuntimeMaxSec=120 (90 s smoke + ~30 s network checks); output above is redacted by the broker; the runtime turn is excluded from COST by its work/doctor-* cwd

## 14. plan restart while a task runs is refused; never applied by this script

gate preview:
~~~
{"ok":true,"data":{"safe":true,"reason":null,"idle_beats":6,"idle_beats_required":4,"newest_heartbeat_age_s":18.4,"plane":{"mode":"plane+local","running":0,"as_of":"2026-10-02T20:43:34.451Z","standing_age_s":0.0},"last_lifecycle_line":"2026-10-02T20:17:05.522Z submission stored (27298bc85f91) \u2014 awaiting verdict","lifecycle_open":false,"outbox_files":0,"unit_active":true,"graceful_stop_possible":true,"unknown":null}}
~~~
plan restart (never applied here; the plan id expires in 60 s):
~~~
{"ok":true,"plan":{"plan_id":"92ba9b9e771808f2","verb":"restart","argv":["systemctl","restart","--no-block","imd-worker.service"],"expires_at":"2026-10-02T20:44:34Z","single_use":true,"preconditions":{"idle_beats":6,"idle_beats_required":4,"newest_heartbeat_age_s":18.7,"plane":{"mode":"plane+local","running":0,"as_of":"2026-10-02T20:43:34.715Z","standing_age_s":0.0},"last_lifecycle_line":"2026-10-02T20:17:05.522Z submission stored (27298bc85f91) \u2014 awaiting verdict","lifecycle_open":false,"outbox_files":0,"unit_active":true,"graceful_stop_possible":true},"warning":"a task assigned in the ~1\u20135 s between the gate's fresh reads and systemctl may be reported as a failed run; 3 consecutive failed runs pause the seat 15 min (never measured: 16/16 historical restarts were idle)","inverse":{"verb":"stop","args":{}},"verify":{"verified_when":["shutting down","runtimes:"],"within_s":30,"connected_when":"admitted (session","reported_separately":true},"restart_required_after":false,"audit_seq":31}}
~~~
~~~
preconditions.plane.mode: plane+local
~~~

**result:** recorded -- gate_unknown(lifecycle) means only a failed lifecycle read; expected ok:false error gate_blocked while a task runs, ok:true with preconditions when idle; at idle preconditions.plane.mode must read plane+local (local-only means offline mode or unavailable/stale plane evidence; check standing-read diagnostics and /etc/systemd/system/imd-dashd.service.d/10-seat.conf); either way nothing was applied

## 15. sha256sum -c MANIFEST.sha256 on the installed broker files, units, wheel and lock (root)

broker files under /opt/imd-dash/broker:
~~~
imd_dashd/__init__.py: OK
imd_dashd/audit.py: OK
imd_dashd/child_unit.py: OK
imd_dashd/drain.py: OK
imd_dashd/gate.py: OK
imd_dashd/imd_dashd.py: OK
imd_dashd/probe_hygiene.py: OK
imd_dashd/process_snapshot.py: OK
imd_dashd/projection.py: OK
imd_dashd/redact.py: OK
imd_dashd/summarise_claude.py: OK
imd_dashd/summarise_codex.py: OK
imd_dashd/verbs.py: OK
~~~
units and drop-ins (installed paths mapped from deploy/vps/):
~~~
/etc/systemd/system/imd-dashd.socket: OK
/etc/systemd/system/imd-dashd.service: OK
/etc/systemd/system/imd-worker.service.d/20-hide-dash.conf: OK
/etc/systemd/system/user-1001.slice.d/50-pepepane.conf: OK
/etc/ssh/sshd_config.d/10-imd-dash.sshd.conf: OK
~~~
fork wheel and lock under /opt/imd-dash:
~~~
requirements.lock: OK
wheels/maxpane-0.9.3-py3-none-any.whl: OK
~~~
~~~
fork post-install check: 367 files matched (wheel sha256 9306351ab3)
~~~

**result:** every line above must read OK (20-hide-dash.conf reads FAILED open or read until step 7 has been run)

## 16. runuser -u imd-worker -- ls /home/imd-dash must fail (root)

~~~
exit status: 2
ls: cannot open directory '/home/imd-dash': Permission denied
~~~

**result:** PASS -- /home/imd-dash (0700) is closed to imd-worker

## 17. sshd -T -C user=imd-dash: allowtcpforwarding no (root)

~~~
x11forwarding no
permittty yes
allowtcpforwarding no
allowagentforwarding no
~~~

**result:** PASS -- the Match User block applies

## 18. systemctl show user-<uid>.slice: MemoryMax, CPUQuota, MemoryPeak (root)

~~~
MemoryCurrent=[not set]
MemoryPeak=[not set]
CPUQuotaPerSecUSec=500ms
MemoryMax=268435456
~~~

**result:** recorded -- MemoryMax must read 268435456 (256M); MemoryPeak is meaningful only while or after an imd-dash login ran pepepane (the §14 slice peak)

## 19. grep HISTORY /etc/sysstat/sysstat: sar depth (root)

~~~
HISTORY=7
sa01
sa02
sa24
sa25
sa26
sa27
sa28
sa29
sa30
sar01
sar23
sar24
sar25
sar26
sar27
sar28
sar29
sar30
~~~

**result:** recorded -- the depth MACHINE's sar sparkline can reach (spec §5.5)

## 20. drained restart at a natural idle gap: audit lines, verify, slice memory.peak (owner, by hand)

### audit lines 33-37 (plan, drain_armed, drain_fire, apply, verify)
~~~
{"ts":"2026-10-02T23:36:37Z","seq":33,"peer_uid":1001,"verb":"drain-restart","phase":"plan","plan_id":"8d36fa27ecfd0e14","args":{"offline":false},"preconditions":{"idle_beats":6,"idle_beats_required":4,"newest_heartbeat_age_s":16.6,"plane":{"mode":"plane+local","running":0,"as_of":"2026-10-02T23:36:37.704Z","standing_age_s":0.0},"last_lifecycle_line":"2026-10-02T21:06:48.165Z submission stored (09065c9d7326) \u2014 awaiting verdict","lifecycle_open":false,"outbox_files":0,"unit_active":true,"graceful_stop_possible":true},"outcome":"planned","verified":null,"connected":null,"cursor_before":null,"cursor_after":null}
{"ts":"2026-10-02T23:37:03Z","seq":34,"peer_uid":1001,"verb":"drain-restart","phase":"drain_armed","plan_id":"8d36fa27ecfd0e14","args":null,"preconditions":{"idle_beats":6,"idle_beats_required":4,"newest_heartbeat_age_s":16.6,"plane":{"mode":"plane+local","running":0,"as_of":"2026-10-02T23:36:37.704Z","standing_age_s":0.0},"last_lifecycle_line":"2026-10-02T21:06:48.165Z submission stored (09065c9d7326) \u2014 awaiting verdict","lifecycle_open":false,"outbox_files":0,"unit_active":true,"graceful_stop_possible":true},"outcome":"armed","verified":null,"connected":null,"cursor_before":null,"cursor_after":null}
{"ts":"2026-10-02T23:38:37Z","seq":35,"peer_uid":null,"verb":"drain-restart","phase":"drain_fire","plan_id":"aac620669e980090","args":null,"preconditions":{"idle_beats":6,"idle_beats_required":4,"newest_heartbeat_age_s":16.4,"plane":{"mode":"plane+local","running":0,"as_of":"2026-10-02T23:38:37.729Z","standing_age_s":0.0},"last_lifecycle_line":"2026-10-02T21:06:48.165Z submission stored (09065c9d7326) \u2014 awaiting verdict","lifecycle_open":false,"outbox_files":0,"unit_active":true,"graceful_stop_possible":true},"outcome":"firing","verified":null,"connected":null,"cursor_before":null,"cursor_after":null}
{"ts":"2026-10-02T23:38:37Z","seq":36,"peer_uid":0,"verb":"drain-restart","phase":"apply","plan_id":"aac620669e980090","args":null,"preconditions":{"idle_beats":6,"idle_beats_required":4,"newest_heartbeat_age_s":16.4,"plane":{"mode":"plane+local","running":0,"as_of":"2026-10-02T23:38:37.729Z","standing_age_s":0.0},"last_lifecycle_line":"2026-10-02T21:06:48.165Z submission stored (09065c9d7326) \u2014 awaiting verdict","lifecycle_open":false,"outbox_files":0,"unit_active":true,"graceful_stop_possible":true},"outcome":"applied","verified":null,"connected":null,"cursor_before":"s=<hex>;i=1d190;b=<hex>;m=d36755cae6;t=65ce4071489b2;x=30ea4c720162de5f","cursor_after":null}
{"ts":"2026-10-02T23:39:07Z","seq":37,"peer_uid":null,"verb":"drain-restart","phase":"verify","plan_id":"aac620669e980090","args":null,"preconditions":null,"outcome":"verified","verified":true,"connected":true,"cursor_before":"s=<hex>;i=1d190;b=<hex>;m=d36755cae6;t=65ce4071489b2;x=30ea4c720162de5f","cursor_after":"s=<hex>;i=1d1a7;b=<hex>;m=d3685cd34a;t=65ce4081b9217;x=e9053c31b2b67f53"}
~~~

### worker journal around the fire (shutting down -> runtimes: -> admitted)
~~~
2026-10-02T23:38:37.774Z shutting down
imd-worker.service: Deactivated successfully.
Stopped imd-worker.service - IMD worker (Codex, seat #7).
imd-worker.service: Consumed 31.865s CPU time over 5h 40min 56.336s wall clock time, 169.2M memory peak.
Started imd-worker.service - IMD worker (Codex, seat #7).
2026-10-02T23:38:38.027Z runtimes: codex codex-cli 0.159.3 (using codex, as asked)
2026-10-02T23:38:38.313Z execution profiles: none, foundry
2026-10-02T23:38:38.313Z tools advertised: browser
2026-10-02T23:38:38.470Z connected to api.imd.fun
2026-10-02T23:38:38.570Z admitted (session ed8a5e9e)
2026-10-02T23:38:38.587Z release 0.1.0+2a548252, the latest
2026-10-02T23:39:08.523Z alive 0m · idle · 0 submitted · fleet 546 online, 570 enrolled
~~~

### TUI slice during a live pepepane session, measured 2026-10-03 (spec §14 slice peak)
~~~
MemoryPeak=114634752
MemoryMax=268435456
~~~

## Mac build measurements (2026-09-27)

The lean entrypoint cold physical peak was **58.8 MiB**, measured on macOS arm64 with Python 3.11.15 and Textual 8.2.8
using the libproc fallback in `scripts/pty_footprint2.py`; the budget stays 160 MiB. The historical **142 MiB** research
measurement used the full MaxPaneApp with all managers and is a different measurement. The lean import graph still
loads the Base/FrenPet module graphs through `data/__init__.py`, but constructs only SeatManager.
The in-situ healthy and worst fixture layout measured **134 columns by 50 rows**; LEDGER has a named width exception
and its full tier clears at **210 columns**. The VPS slice peak is now recorded as 114634752 bytes and the doctor child peak as 139M. The status child peak has no accounting line and remains unmeasured; the VPS layout sweep remains unrun.
