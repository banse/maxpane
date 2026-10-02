#!/usr/bin/env bash
# deploy/vps/probe_seat_host.sh -- the spec §14 "Only on the VPS" checks, in order, as Markdown on stdout.
# Run ONCE as root after install.sh (owner decision spec §16 #17):
#   bash deploy/vps/probe_seat_host.sh > /root/seat_install_probe.md      # then paste into docs/seat_install_probe.md
#   bash deploy/vps/probe_seat_host.sh --list                             # titles only, touches nothing
# The only write verb it applies is `doctor` (one runtime turn; --skip-doctor). `plan restart` is issued and never
# applied. The §14 drained restart is the owner's, by hand, recorded under the last heading.
# Every broker reply is scrubbed of hex >= 32 before it is printed; the seat projection check prints PASS/FAIL and an
# 8-char prefix, never a key (spec §13).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(cd "$HERE/../.." && pwd)"
SOCK=/run/imd-dash/broker.sock
DASH_USER=imd-dash
DASH_HOME=/home/imd-dash
WORKER_USER=imd-worker
WORKER_UNIT=imd-worker.service
PREFIX=/opt/imd-dash
MANIFEST=/opt/imd-dash/MANIFEST.sha256
CGROUP=/sys/fs/cgroup/system.slice/imd-worker.service
STALE_CURSOR='s=00000000000000000000000000000000;i=1;b=00000000000000000000000000000000;m=1;t=1;x=1'
LIST=0
SCRUB=0
SKIP_DOCTOR=0

TITLES=(
  "connect(/run/imd-dash/broker.sock) as imd-dash succeeds (ping)"
  "connect(/run/imd-dash/broker.sock) as imd-worker fails (EACCES: 0660 root:imd-dash in a 0755 root dir)"
  "journalctl -u imd-worker.service as imd-dash: 14-day read count (group systemd-journal)"
  "journalctl --after-cursor with a deliberately stale cursor: exit status and first entry vs the oldest"
  "journalctl lifecycle --grep: newest match before limit, pcre2 and no-match exit status"
  "systemctl show imd-worker.service as imd-dash (unprivileged D-Bus read)"
  "cgroup counters of imd-worker.service as imd-dash (0644)"
  "python3 -c 'import compression.zstd' on /usr/bin/python3 (rollouts older than 7 days)"
  "pepepane --once --offline as imd-dash (PATH via the /usr/local/bin symlink, imports, exit status)"
  "broker ping (version, posture_ok, drain_armed, in_flight)"
  "seat projection canary: no secret key name, no stray hex64, deviceKey == whoami"
  "status through the broker as a transient unit, with the child scope's memory.peak"
  "doctor through the broker (plan, apply, verify), with the child scope's memory.peak"
  "plan restart while a task runs is refused; never applied by this script"
  "sha256sum -c MANIFEST.sha256 on the installed broker files, units, wheel and lock (root)"
  "runuser -u imd-worker -- ls /home/imd-dash must fail (root)"
  "sshd -T -C user=imd-dash: allowtcpforwarding no (root)"
  "systemctl show user-<uid>.slice: MemoryMax, CPUQuota, MemoryPeak (root)"
  "grep HISTORY /etc/sysstat/sysstat: sar depth (root)"
  "drained restart at a natural idle gap: audit lines, verify, slice memory.peak (owner, by hand)"
)

usage() {
  cat <<'USAGE'
usage: probe_seat_host.sh [--list] [--scrub] [--skip-doctor] [--help]
  --list         print the numbered section titles and exit (touches nothing; used by the guard test and the docs)
  --scrub        redact stdin to stdout without any host checks
  --skip-doctor  do not apply `doctor` (it spends one runtime turn and leaves a work/doctor-* transcript)
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST=1 ;;
    --scrub) SCRUB=1 ;;
    --skip-doctor) SKIP_DOCTOR=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; printf 'probe_seat_host.sh: unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done

if [ "$LIST" = 1 ]; then
  i=0
  for t in "${TITLES[@]}"; do i=$((i + 1)); printf '%d. %s\n' "$i" "$t"; done
  exit 0
fi


# ---- helpers -------------------------------------------------------------------------------------------
SECTION_N=0
section()    { SECTION_N=$((SECTION_N + 1)); printf '\n## %d. %s\n\n' "$SECTION_N" "$1"; }
code_block() { printf '~~~\n'; scrub; printf '~~~\n'; }
result()     { printf '\n**result:** %s\n' "$1"; }
scrub() {
  /usr/bin/python3 -I -c '
# BEGIN PROBE_REDACTOR
import sys
sys.path.insert(0, "/opt/imd-dash/broker")
from imd_dashd.redact import redact
from imd_dashd.probe_hygiene import redact_public_ips
for line in sys.stdin:
    sys.stdout.write(redact_public_ips(redact(line)).replace(chr(36), ""))
# END PROBE_REDACTOR
' | sed -E 's/[0-9a-fA-F]{32,}/<hex>/g'
}
if [ "$SCRUB" = 1 ]; then scrub; exit 0; fi

[ "$(id -u)" = 0 ] || { printf 'probe_seat_host.sh: run as root (it switches to imd-dash and imd-worker with runuser)\n' >&2; exit 1; }

as_dash()    { runuser -u "$DASH_USER" -- env HOME="$DASH_HOME" PATH=/usr/local/bin:/usr/bin:/bin "$@"; }
as_worker()  { runuser -u "$WORKER_USER" -- env HOME=/home/imd-worker PATH=/usr/local/bin:/usr/bin:/bin "$@"; }
json_get()   { /usr/bin/python3 -c 'import json,sys
try:
    d = json.loads(sys.stdin.read() or "{}")
except Exception:
    d = {}
for k in sys.argv[1:]:
    d = d.get(k) if isinstance(d, dict) else None
print("" if d is None else d)' "$@"; }

# broker_call USER '<one JSON line>' -> the broker's one-line reply, or "connect failed: <Exception> <errno>"
broker_call() {
  local user="$1" req="$2"
  runuser -u "$user" -- env HOME="/home/$user" /usr/bin/python3 - "$SOCK" "$req" <<'PY'
import socket, sys
sys.path.insert(0, "/opt/imd-dash/broker")
from imd_dashd.child_unit import RUNTIME_MAX_S, SUBPROCESS_BELT_S
path, req = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(max(RUNTIME_MAX_S.values()) + SUBPROCESS_BELT_S + 5)
try:
    s.connect(path)
except OSError as exc:
    print("connect failed:", type(exc).__name__, exc.errno)
    sys.exit(2)
s.sendall(req.encode() + b"\n")
buf = b""
while not buf.endswith(b"\n"):
    chunk = s.recv(65536)
    if not chunk:
        break
    buf += chunk
sys.stdout.write(buf.decode(errors="replace") or "(no reply)\n")
PY
}

# Accounting for the exact unit named in the broker's raw reply, before output scrubbing.
peak_of_unit() {
  if [ -z "$1" ]; then printf '\nno transient unit in broker reply; accounting unavailable\n'; return; fi
  printf '\nsystemd accounting for %s (journal, last 20 min):\n' "$1"
  journalctl --since "-20 min" -u "${1%.service}.service" -o cat 2>&1 | grep -i -E 'consumed|memory peak|failed|timed out' | tail -n 5 | scrub | code_block
}

# ---- the probes, one function per title ----------------------------------------------------------------
p01() {
  local out; out="$(broker_call "$DASH_USER" '{"v":1,"verb":"ping","args":{}}')"
  printf '%s\n' "$out" | scrub | code_block
  case "$out" in *'"ok": true'*|*'"ok":true'*) result "PASS -- connect + ping as $DASH_USER" ;; *) result "FAIL -- expected an ok:true ping reply" ;; esac
}
p02() {
  local out; out="$(broker_call "$WORKER_USER" '{"v":1,"verb":"ping","args":{}}')"
  printf '%s\n' "$out" | scrub | code_block
  case "$out" in "connect failed: PermissionError 13"*) result "PASS -- EACCES for $WORKER_USER (socket 0660 root:$DASH_USER)" ;;
                 *) result "FAIL -- the worker uid must not reach the broker socket" ;; esac
  printf '\n(this is the worker uid outside its unit; inside the unit the drop-in also hides /run/imd-dash entirely)\n'
}
p03() {
  local n; n="$(as_dash journalctl -u "$WORKER_UNIT" --since -14d -o json 2>/dev/null | wc -l | tr -d ' ')"
  printf 'lines: %s\n' "$n" | code_block
  if [ "${n:-0}" -gt 0 ] 2>/dev/null; then result "PASS -- $DASH_USER reads the unit journal (systemd-journal group)"; else result "FAIL -- 0 lines: is $DASH_USER in group systemd-journal?"; fi
}
journal_heads() {
  /usr/bin/python3 -c '
# BEGIN CURSOR_PROBE
import json, sys
sys.path.insert(0, "/opt/imd-dash/broker")
from imd_dashd.redact import redact

def decode_message(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(type(byte) is int and 0 <= byte < 256 for byte in value):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            pass
    return None

for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        print("<non-JSON line omitted>")
        continue
    if not isinstance(record, dict):
        print("<non-object JSON omitted>")
        continue
    decoded = decode_message(record.get("MESSAGE"))
    head = redact(decoded)[:80] if decoded is not None else "<unreadable MESSAGE omitted>"
    print(record.get("__REALTIME_TIMESTAMP"), head)
# END CURSOR_PROBE
'
}

p04() {
  local rc=0 out
  out="$(as_dash journalctl -u "$WORKER_UNIT" -o json -n 3 --after-cursor="$STALE_CURSOR" 2>&1)" || rc=$?
  printf 'exit status: %d\n' "$rc"
  printf 'first entries returned (__REALTIME_TIMESTAMP, MESSAGE head):\n'
  printf '%s\n' "$out" | journal_heads 2>&1 | scrub | code_block
  printf 'oldest entry in the unit journal, for comparison:\n'
  as_dash journalctl -u "$WORKER_UNIT" -o json 2>/dev/null | head -n 1 | journal_heads 2>&1 | scrub | code_block
  local since_arg rc2=0 out2
  since_arg="$(date -u -d '-10 min' '+%Y-%m-%d %H:%M:%S') UTC"   # the form seat_tail.journal_since_arg() emits
  out2="$(as_dash journalctl -u "$WORKER_UNIT" -o json -n 1 --since "$since_arg" 2>&1)" || rc2=$?
  printf 'fallback --since "%s": exit %d, %s JSON record(s)\n' "$since_arg" "$rc2" "$(printf '%s\n' "$out2" | grep -c '^{' || true)" | code_block
  result "recorded -- spec §5.1: a vacuumed cursor may exit 0 and seek to the oldest entry; the reader detects the gap from data (first entry vs lastTsUtc + 60 s), not from this exit status; the fallback re-attach's --since 'YYYY-MM-DD HH:MM:SS UTC' form must exit 0 here"
}
p05() {
  /usr/bin/python3 -I - <<'PYPROBE' | code_block
# BEGIN LIFECYCLE_PROBE
import json
import subprocess
import sys
sys.path.insert(0, "/opt/imd-dash/broker")
from imd_dashd.imd_dashd import lifecycle_journal_argv, lifecycle_read_outcome
from imd_dashd.gate import newest_lifecycle, HEARTBEAT_RE
from imd_dashd.redact import redact

def decode_message(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(type(byte) is int and 0 <= byte < 256 for byte in value):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            pass
    return None

def read(argv, label, *, show_output=True):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=12)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(label + " unreadable:", type(exc).__name__)
        return None
    print(label + " exit status:", done.returncode)
    if show_output:
        safe_lines = []
        for line in done.stdout.split("\n"):
            line = line.rstrip("\r")
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                safe_lines.append("<non-JSON line omitted>")
            else:
                if isinstance(record, dict):
                    display = {key: record[key] for key in ("MESSAGE", "__REALTIME_TIMESTAMP") if key in record}
                    if "MESSAGE" in display:
                        decoded = decode_message(display["MESSAGE"])
                        display["MESSAGE"] = redact(decoded) if decoded is not None else "<unreadable MESSAGE omitted>"
                    safe_lines.append(json.dumps(display))
        print(label + " stdout:", "\n".join(safe_lines))
        print(label + " stderr:", done.stderr)
    return done

def messages(done):
    rows = []
    if done is not None:
        for line in done.stdout.split("\n"):
            line = line.rstrip("\r")
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            message = decode_message(record.get("MESSAGE"))
            if message is not None:
                rows.append(message)
    return rows

argv = lifecycle_journal_argv()
# Bounded independent unfiltered history. Insufficient retained history is inconclusive.
baseline = read(argv[:argv.index("--grep")] + ["--lines", "10000"], "unfiltered history", show_output=False)
filtered = read(argv, "lifecycle")
rows = messages(baseline)
expected, _open = newest_lifecycle(rows)
actual = messages(filtered)
print("newest entry heartbeat:", bool(rows and HEARTBEAT_RE.match(rows[-1])))
print("grep/pcre2:", "PASS" if filtered is not None and lifecycle_read_outcome(filtered.returncode, filtered.stdout, filtered.stderr)[1] else "FAIL")
if baseline is None or baseline.returncode or expected is None:
    print("filter-before-limit: inconclusive (no lifecycle in bounded baseline)")
elif not rows or not HEARTBEAT_RE.match(rows[-1]) or rows[-1][:24] <= expected[:24]:
    print("filter-before-limit: inconclusive (newest entry is not a heartbeat)")
else:
    print("filter-before-limit:", "PASS" if actual == [expected] else "FAIL")
no_match = read(lifecycle_journal_argv(pattern="(?!)"), "no-match")
print("no-match acceptance:", "PASS" if no_match is not None and lifecycle_read_outcome(no_match.returncode, no_match.stdout, no_match.stderr) == ([], True) else "FAIL")
# END LIFECYCLE_PROBE
PYPROBE
  result "recorded -- filtered history must select the latest lifecycle even after a newer heartbeat; JSON no-match must report exit 1, empty stdout and empty stderr; no action was applied"
}
p06() {
  as_dash systemctl show "$WORKER_UNIT" --timestamp=utc -p ActiveState,SubState,MainPID,NRestarts,ActiveEnterTimestamp,ExecMainStartTimestamp,UnitFileState,Restart,RestartUSec,MemoryMax,CPUQuotaPerSecUSec,TasksMax,TasksCurrent,KillMode,TimeoutStopUSec,IPAddressDeny 2>&1 | code_block
  result "recorded -- gracefulStopPossible = KillMode control-group and TimeoutStopUSec >= 30 s; IPAddressDeny is what the broker copies onto its transient children (§4.1b)"
}
p07() {
  local f
  for f in memory.current memory.peak memory.max cpu.max; do printf '%s: %s\n' "$f" "$(as_dash cat "$CGROUP/$f" 2>&1)"; done | code_block
  result "recorded"
}
p08() {
  local rc=0 out
  out="$(as_dash /usr/bin/python3 -c 'import compression.zstd, sys; print("compression.zstd ok", sys.version.split()[0])' 2>&1)" || rc=$?
  printf 'exit status: %d\n%s\n' "$rc" "$out" | code_block
  if [ "$rc" = 0 ]; then result "PASS -- .jsonl.zst rollouts will be readable"; else result "recorded -- ImportError: COST will read 'rollouts > 7 d unreadable (compression.zstd missing)' (§5.4); plain .jsonl unaffected"; fi
}
p09() {
  local out rc=0
  out="$(mktemp)"
  as_dash pepepane --once --offline > "$out" 2> "$out.err" || rc=$?
  printf 'exit status: %d, stdout bytes: %s, stderr bytes: %s\n' "$rc" "$(wc -c < "$out" | tr -d ' ')" "$(wc -c < "$out.err" | tr -d ' ')" | code_block
  /usr/bin/python3 - "$out" <<'PY' | scrub | code_block
import json, re, sys
raw = open(sys.argv[1], "rb").read()
try:
    doc = json.loads(raw)
except Exception as exc:
    print("stdout is not one JSON document:", type(exc).__name__); raise SystemExit
print("schemaVersion", doc.get("schemaVersion"), "producer", doc.get("producer"))
print("host", doc.get("host"))
print("startedAtUtc", doc.get("startedAtUtc"), "completedAtUtc", doc.get("completedAtUtc"))
print("sources ok:", {k: (v or {}).get("ok") for k, v in (doc.get("sources") or {}).items()})
print("dollar signs in the document:", raw.count(b"\x24"))
print("hex64 values anywhere:", len(re.findall(rb"\b[0-9a-f]{64}\b", raw)), "(must be 0: keys are truncated at fold time)")
PY
  printf 'stderr head:\n'; scrub < "$out.err" | head -c 600 | code_block
  rm -f "$out" "$out.err"
  if [ "$rc" = 0 ]; then result "PASS -- the lean entrypoint imports and runs as $DASH_USER through /usr/local/bin/pepepane"; else result "FAIL -- exit $rc; see stderr above"; fi
}
p10() {
  broker_call "$DASH_USER" '{"v":1,"verb":"ping","args":{}}' | scrub | code_block
  result "recorded -- version is the broker's VERSION; posture_ok false means IPAddressDeny could not be read and every runtime verb answers child_posture_unavailable"
}
p11() {
  local seat who
  seat="$(broker_call "$DASH_USER" '{"v":1,"verb":"seat","args":{}}')"
  who="$(broker_call "$DASH_USER" '{"v":1,"verb":"whoami","args":{}}')"
  /usr/bin/python3 - "$seat" "$who" <<'PY' | code_block
import json, re, sys
try:
    seat = json.loads(sys.argv[1]); who = json.loads(sys.argv[2])
except Exception as exc:
    print("reply is not JSON:", type(exc).__name__); print("FAIL"); raise SystemExit
if not seat.get("ok"):
    print("seat refused:", seat.get("error"), seat.get("detail")); print("FAIL (refused -- a refusal is the canary working, but the projection is unavailable)"); raise SystemExit
data = seat.get("data") or {}
key = (who.get("data") or {}).get("deviceKey")
names = re.compile(r"privateKey|devicePrivateKey|mnemonic|secret", re.I)
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + "." + k, k, v
            yield from walk(v, path + "." + k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, path + "[" + str(i) + "]")
bad_names = [p for p, k, v in walk(data) if names.search(k)]
hex64 = [(p, v) for p, k, v in walk(data) if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)]
stray = [p for p, v in hex64 if not p.endswith(".deviceKey")]
print("allowlist keys present:", sorted(data))
print("keys matching the secret-name regex:", len(bad_names), bad_names)
print("hex64 values:", len(hex64), "stray (not deviceKey):", stray)
print("deviceKey == whoami:", bool(key) and data.get("deviceKey") == key, "prefix", (data.get("deviceKey") or "")[:8])
print("PASS" if not bad_names and not stray and key and data.get("deviceKey") == key else "FAIL")
PY
  result "see PASS/FAIL above (spec §13 projection canary: key names, sk-/eyJ, whoami match, no other hex64, exactly 8 source keys)"
}
p12() {
  local resp unit since req
  resp="$(broker_call "$DASH_USER" '{"v":1,"verb":"status","args":{}}')"
  unit="$(printf '%s' "$resp" | json_get data unit)"
  printf '%s\n' "$resp" | scrub | head -c 3000 | code_block
  peak_of_unit "$unit"
  since=$(( $(date -u +%s) - 3 * 86400 ))
  req="$(printf '{"v":1,"verb":"sessions","args":{"runtime":"codex","since":%s}}' "$since")"
  broker_call "$DASH_USER" "$req" | /usr/bin/python3 -c '
import json, sys
try:
    reply = json.load(sys.stdin)
    data = reply.get("data") or {}
    detail = reply.get("detail") or {}
    sessions = data.get("sessions")
    print("sessions ok:", reply.get("ok"), "rc:", 0 if reply.get("ok") else detail.get("rc"),
          "count:", len(sessions) if isinstance(sessions, list) else None)
    if not reply.get("ok"):
        print("sessions error:", reply.get("error"), detail)
except (ValueError, TypeError, AttributeError):
    print("sessions ok: False rc: unknown count: unknown (unreadable reply)")
' | scrub | code_block
  result "recorded -- proves the transient-unit posture (ProtectHome=tmpfs, TemporaryFileSystem=/opt:ro, copied IPAddressDeny) lets imd status run; the peak sizes MemoryMax=512M"
}
p13() {
  if [ "$SKIP_DOCTOR" = 1 ]; then printf 'skipped (--skip-doctor): doctor spends one runtime turn and leaves a work/doctor-* transcript\n'; result "skipped"; return; fi
  local plan pid confirm req resp i unit
  plan="$(broker_call "$DASH_USER" '{"v":1,"verb":"doctor","args":{}}')"
  printf 'plan:\n'; printf '%s\n' "$plan" | scrub | code_block
  pid="$(printf '%s' "$plan" | json_get plan plan_id)"
  if [ -z "$pid" ]; then result "not applied -- no plan_id (busy, doctor_too_soon or child_posture_unavailable above)"; return; fi
  confirm="$(printf '%s' "$pid" | cut -c1-4)"
  req="$(printf '{"v":1,"verb":"apply","args":{"plan_id":"%s","confirm":"%s"}}' "$pid" "$confirm")"
  resp="$(broker_call "$DASH_USER" "$req")"
  unit="$(printf '%s' "$resp" | json_get result unit)"
  printf 'apply:\n'; printf '%s\n' "$resp" | scrub | code_block
  i=0
  while [ "$i" -lt 30 ]; do
    sleep 5; i=$((i + 1))
    req="$(printf '{"v":1,"verb":"verify","args":{"plan_id":"%s"}}' "$pid")"
    resp="$(broker_call "$DASH_USER" "$req")"
    case "$resp" in *'"verified": null'*|*'"verified":null'*) continue ;; esac
    break
  done
  printf 'verify after %d polls (5 s each):\n' "$i"; printf '%s\n' "$resp" | scrub | head -c 4000 | code_block
  peak_of_unit "$unit"
  result "recorded -- RuntimeMaxSec=120 (90 s smoke + ~30 s network checks); output above is redacted by the broker; the runtime turn is excluded from COST by its work/doctor-* cwd"
}
p14() {
  local plan mode
  printf 'gate preview:\n'
  broker_call "$DASH_USER" '{"v":1,"verb":"gate","args":{"offline":false}}' | scrub | code_block
  printf 'plan restart (never applied here; the plan id expires in 60 s):\n'
  plan="$(broker_call "$DASH_USER" '{"v":1,"verb":"restart","args":{"offline":false}}')"
  printf '%s\n' "$plan" | scrub | code_block
  mode="$(printf '%s' "$plan" | json_get plan preconditions plane mode)"
  printf 'preconditions.plane.mode: %s\n' "${mode:-<no plan: see the reply above>}" | code_block
  result "recorded -- gate_unknown(lifecycle) means only a failed lifecycle read; expected ok:false error gate_blocked while a task runs, ok:true with preconditions when idle; at idle preconditions.plane.mode must read plane+local (local-only means offline mode or unavailable/stale plane evidence; check standing-read diagnostics and /etc/systemd/system/imd-dashd.service.d/10-seat.conf); either way nothing was applied"
}
p15() {
  [ -f "$MANIFEST" ] || { printf 'missing %s\n' "$MANIFEST" | code_block; result "FAIL"; return; }
  local uid; uid="$(id -u "$DASH_USER")"
  printf 'broker files under %s/broker:\n' "$PREFIX"
  (cd "$PREFIX/broker" && grep '  imd_dashd/' "$MANIFEST" | sha256sum -c --strict 2>&1) | code_block
  printf 'units and drop-ins (installed paths mapped from deploy/vps/):\n'
  {
    grep -E '  deploy/vps/imd-dashd\.(socket|service)$' "$MANIFEST" | sed 's#  deploy/vps/#  /etc/systemd/system/#'
    grep -E '  deploy/vps/20-hide-dash\.conf$' "$MANIFEST" | sed 's#  deploy/vps/#  /etc/systemd/system/imd-worker.service.d/#'
    grep -E '  deploy/vps/50-pepepane\.conf$' "$MANIFEST" | sed "s#  deploy/vps/#  /etc/systemd/system/user-$uid.slice.d/#"
    grep -E '  deploy/vps/10-imd-dash\.sshd\.conf$' "$MANIFEST" | sed 's#  deploy/vps/#  /etc/ssh/sshd_config.d/#'
  } | sha256sum -c 2>&1 | code_block
  printf 'fork wheel and lock under %s:\n' "$PREFIX"
  (cd "$PREFIX" && grep -E '  deploy/vps/(wheels/maxpane-.*\.whl|requirements\.lock)$' "$MANIFEST" | sed 's#  deploy/vps/#  #' | sha256sum -c --strict 2>&1) | code_block
  local fork_check fork_rc=0
  fork_check="$("$PREFIX/venv/bin/python" -I "$HERE/check_fork_wheel.py" "$PREFIX/wheels" 2>&1)" || fork_rc=$?
  printf '%s\n' "$fork_check" | scrub | code_block
  if [ "$fork_rc" != 0 ]; then result "FAIL -- installed fork bytes differ; re-run install.sh from the staged archive"; return; fi
  result "every line above must read OK (20-hide-dash.conf reads FAILED open or read until step 7 has been run)"
}
p16() {
  local rc=0 out
  out="$(as_worker ls "$DASH_HOME" 2>&1)" || rc=$?
  printf 'exit status: %d\n%s\n' "$rc" "$out" | code_block
  if [ "$rc" != 0 ]; then result "PASS -- $DASH_HOME (0700) is closed to $WORKER_USER"; else result "FAIL -- the worker uid listed the dash home"; fi
}
p17() {
  local v; v="$(sshd -T -C user="$DASH_USER" 2>&1 | grep -i -E '^(allowtcpforwarding|x11forwarding|allowagentforwarding|permittty) ')"
  printf '%s\n' "$v" | code_block
  case "$v" in *"allowtcpforwarding no"*) result "PASS -- the Match User block applies" ;; *) result "FAIL -- sshd -T does not show allowtcpforwarding no for $DASH_USER" ;; esac
}
p18() {
  local uid; uid="$(id -u "$DASH_USER")"
  systemctl show "user-$uid.slice" -p MemoryMax -p CPUQuotaPerSecUSec -p MemoryCurrent -p MemoryPeak 2>&1 | code_block
  result "recorded -- MemoryMax must read 268435456 (256M); MemoryPeak is meaningful only while or after an imd-dash login ran pepepane (the §14 slice peak)"
}
p19() {
  { grep -E '^HISTORY' /etc/sysstat/sysstat 2>&1 || printf 'HISTORY not set (sysstat default 7 days)\n'; ls /var/log/sysstat 2>&1 | head -n 40; } | code_block
  result "recorded -- the depth MACHINE's sar sparkline can reach (spec §5.5)"
}
p20() {
  cat <<TEXT | code_block
owner, by hand, at a natural idle gap (spec §14; §11 idle gate G):
  a) ssh -t $DASH_USER@<host> pepepane      -> press c (CONTROL), then r (restart) or d (drain-restart); type the plan id's first 4 chars
  b) watch GATE / LIVE: 'verified' (shutting down -> runtimes: within 30 s) and 'connected' (admitted) are reported separately
  c) record here:
       tail -n 6 /var/log/imd-dash/audit.jsonl | bash $HERE/probe_seat_host.sh --scrub  # plan, apply (preconditions), verify lines with cursors
       journalctl -u $WORKER_UNIT --since '-5 min' -o cat | tail -n 12 | bash $HERE/probe_seat_host.sh --scrub  # shutting down / runtimes: / admitted
       systemctl show user-$(id -u "$DASH_USER").slice -p MemoryPeak    # the slice's peak after the session
TEXT
  result "pending -- paste the three outputs above into docs/seat_install_probe.md under this heading"
}

# ---- run -----------------------------------------------------------------------------------------------
printf '# PEPEPANE install probe -- %s\n\n' "$(hostname)"
printf 'run %s UTC as root; deploy tree %s; spec §14 "Only on the VPS" in order; broker replies scrubbed of hex >= 32; doctor %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TREE" "$([ "$SKIP_DOCTOR" = 1 ] && printf 'skipped' || printf 'applied')"
set +e   # every probe records its own outcome; a negative check is a pass
i=0
for t in "${TITLES[@]}"; do
  i=$((i + 1))
  section "$t"
  "p$(printf '%02d' "$i")"
done
printf '\n---\nend of probe\n'
