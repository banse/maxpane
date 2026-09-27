#!/usr/bin/env bash
# deploy/vps/install.sh -- install the PEPEPANE dashboard (pepepane) and its root broker (imd-dashd) on the
# worker host. Spec §12.1 "Install sequence", steps 1-8. Every step is idempotent: it checks before it
# changes. --dry-run prints every command it would run and runs none (no root, no Linux needed).
#
# Run as root from an unpacked deploy tree -- the repo checkout, or dist/seat-deploy-<sha>.tar.gz unpacked
# under /opt/imd-dash/src (docs/seat_install.md):
#   bash deploy/vps/install.sh --dry-run --authorized-keys /root/imd-dash.pub     # preview
#   bash deploy/vps/install.sh --authorized-keys /root/imd-dash.pub               # steps 1-6 (+8 prints)
#   bash deploy/vps/install.sh --worker-dropin                                    # step 7, at an idle gap (§16 #4 approved 2026-09-26)
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: install.sh [--dry-run] [--route a|b] [--pip-wheel FILE] [--authorized-keys FILE]
                  [--seat N] [--agent N] [--worker-dropin] [--help]

Steps (spec §12.1 "Install sequence"):
  preflight             sha256sum -c --strict MANIFEST.sha256 on the staged tree BEFORE step 1: a tampered lock,
                        wheel or broker file dies here, with nothing installed
  1  venv tooling       route a (default): apt-get install python3.14-venv (3 packages)
                        route b: python3 -m venv --without-pip, then pip bootstrapped from --pip-wheel pip-*.whl
  2  user imd-dash      useradd -m -s /bin/bash -G systemd-journal imd-dash; home 0700; authorized_keys 0600
                        (no sudoers, no polkit grants: the broker is the only privileged path)
  3  venv + wheels      /opt/imd-dash/venv <- pip install --no-index --find-links /opt/imd-dash/wheels
                        --only-binary=:all: --require-hashes -r requirements.lock (closure + fork wheel, by content);
                        ln -sfn /opt/imd-dash/venv/bin/pepepane /usr/local/bin/pepepane
  4  broker files       copy imd_dashd/*.py to /opt/imd-dash/broker/imd_dashd/ (root 0755/0644), re-verify the
                        installed copies against MANIFEST.sha256 (the staged tree was checked before step 1)
  5  units              imd-dashd.socket + imd-dashd.service + imd-dashd.service.d/10-seat.conf (ExecStart with
                        --seat N: the broker's own standing read, spec §11 gate (b)); daemon-reload;
                        systemctl enable --now imd-dashd.socket
  6  fence, sshd, cfg   user-<uid>.slice.d/50-pepepane.conf; sshd_config.d/10-imd-dash.sshd.conf (sshd -t; reload ssh);
                        /home/imd-dash/.config/pepepane.toml (host/unit/broker/seat/agent -- configuration, never secrets)
  7  worker drop-in     imd-worker.service.d/20-hide-dash.conf, ONLY with --worker-dropin (spec §16 #4, approved 2026-09-26; pass it at an idle gap);
                        it takes effect at the next DRAINED restart -- this script never restarts the worker
  8  probe              prints the probe_seat_host.sh command; never runs it (imd doctor spends a runtime turn)

Options:
  --dry-run             print every command, run none
  --route a|b           install route (default a; spec §16 #2)
  --pip-wheel FILE      route b only: pip-26.2.1-py3-none-any.whl (fill7 §3 bootstrap)
  --authorized-keys FILE  public key(s) for /home/imd-dash/.ssh/authorized_keys
  --seat N              seat token id written to pepepane.toml and to the broker's 10-seat.conf (default 7)
  --agent N             PEPEPANE agent id written to pepepane.toml (default 51075; the --offline fallback)
  --worker-dropin       perform step 7
USAGE
}

# ---- paths (spec §12.1; contract §B) ------------------------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # deploy/vps
TREE="$(cd "$HERE/../.." && pwd)"                         # the deploy tree root (repo checkout or unpacked tarball)
DASH_USER=imd-dash
DASH_HOME=/home/imd-dash
PREFIX=/opt/imd-dash
VENV="$PREFIX/venv"
WHEELS="$PREFIX/wheels"
BROKER_DIR="$PREFIX/broker/imd_dashd"                     # contract §B BROKER_DIR: the package dir, copied verbatim
LOCK="$PREFIX/requirements.lock"
MANIFEST_SRC="$HERE/MANIFEST.sha256"
MANIFEST_DST="$PREFIX/MANIFEST.sha256"
UNIT_DIR=/etc/systemd/system
SSHD_DIR=/etc/ssh/sshd_config.d
SOCKET_PATH=/run/imd-dash/broker.sock
WORKER_UNIT=imd-worker.service

DRY_RUN=0
ROUTE=a
PIP_WHEEL=""
AUTH_KEYS=""
SEAT=7
AGENT=51075
WORKER_DROPIN=0

say()  { printf '%s\n' "$*"; }
warn() { printf 'install.sh: warning: %s\n' "$*" >&2; }
die()  { printf 'install.sh: %s\n' "$*" >&2; exit 1; }
step() { say; say "== step $1: $2"; }
run()  { if [ "$DRY_RUN" = 1 ]; then say "  [dry-run] $*"; else say "  + $*"; "$@"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --route) ROUTE="${2:-}"; shift ;;
    --pip-wheel) PIP_WHEEL="${2:-}"; shift ;;
    --authorized-keys) AUTH_KEYS="${2:-}"; shift ;;
    --seat) SEAT="${2:-}"; shift ;;
    --agent) AGENT="${2:-}"; shift ;;
    --worker-dropin) WORKER_DROPIN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

case "$ROUTE" in a|b) ;; *) die "--route must be a or b (spec §12.1 install route; §16 #2)" ;; esac
case "$SEAT" in ''|*[!0-9]*) die "--seat must be an integer token id" ;; esac
case "$AGENT" in ''|*[!0-9]*) die "--agent must be an integer agent id" ;; esac
if [ "$ROUTE" = b ]; then
  [ -n "$PIP_WHEEL" ] || die "--route b needs --pip-wheel pip-26.2.1-py3-none-any.whl: the VPS python has no ensurepip (fill7 §1, §3)"
fi
if [ -n "$AUTH_KEYS" ] && [ ! -f "$AUTH_KEYS" ]; then die "--authorized-keys: $AUTH_KEYS not found"; fi
if [ "$DRY_RUN" = 0 ]; then
  [ "$(id -u)" = 0 ] || die "run as root (the ssh login to imd-vps is root); use --dry-run to preview"
  [ -f /etc/os-release ] || die "this installer targets the Ubuntu VPS"
fi

# ---- preflight on the staged tree ----------------------------------------------------------------------
missing=""
for f in "$HERE/imd-dashd.socket" "$HERE/imd-dashd.service" "$HERE/20-hide-dash.conf" "$HERE/50-pepepane.conf" \
         "$HERE/10-imd-dash.sshd.conf" "$HERE/requirements.lock" "$MANIFEST_SRC" "$TREE/imd_dashd/imd_dashd.py"; do
  [ -f "$f" ] || missing="$missing $f"
done
if [ -d "$HERE/wheels" ]; then
  set -- "$HERE"/wheels/maxpane-*.whl
  [ -f "$1" ] || missing="$missing $HERE/wheels/maxpane-<version>-py3-none-any.whl"
else
  missing="$missing $HERE/wheels/"
fi
if [ -n "$missing" ]; then
  if [ "$DRY_RUN" = 1 ]; then warn "staged tree incomplete (run scripts/build_wheels.sh first):$missing"
  else die "staged tree incomplete -- run scripts/build_wheels.sh --out deploy/vps on the Mac and re-stage:$missing"; fi
fi
# The staged tree is verified by content BEFORE anything is installed (deviation 5): step 3 copies the staged wheels
# and requirements.lock and runs pip --require-hashes into the venv imd-dash runs daily, so a tampered lock+wheel
# pair must die here, not after it has been installed. MANIFEST paths are repo-relative: checked from $TREE.
if [ "$DRY_RUN" = 1 ]; then
  say "  [dry-run] (cd $TREE && sha256sum -c --strict $MANIFEST_SRC)"
else
  (cd "$TREE" && sha256sum -c --strict "$MANIFEST_SRC") || die "MANIFEST mismatch in the staged tree -- nothing installed"
fi

say "PEPEPANE install -- tree $TREE, route $ROUTE, dry-run $DRY_RUN"

# ---- 1 venv tooling ----------------------------------------------------------------------------------
step 1 "python venv tooling (route $ROUTE)"
if [ "$ROUTE" = a ]; then
  if [ "$DRY_RUN" = 1 ] || ! dpkg -s python3.14-venv >/dev/null 2>&1; then
    run apt-get install -y --no-install-recommends python3.14-venv
  else
    say "  python3.14-venv already installed"
  fi
else
  say "  route b: no apt; pip is bootstrapped from $PIP_WHEEL in step 3 (python3 -m venv --without-pip)"
fi

# ---- 2 user imd-dash -----------------------------------------------------------------------------------
step 2 "user $DASH_USER (groups: systemd-journal only; no sudoers, no polkit)"
if [ "$DRY_RUN" = 0 ] && id -u "$DASH_USER" >/dev/null 2>&1; then
  say "  user $DASH_USER exists"
else
  run useradd -m -s /bin/bash -G systemd-journal "$DASH_USER"
fi
run chmod 0700 "$DASH_HOME"
if [ -n "$AUTH_KEYS" ]; then
  run install -d -m 0700 -o "$DASH_USER" -g "$DASH_USER" "$DASH_HOME/.ssh"
  run install -m 0600 -o "$DASH_USER" -g "$DASH_USER" "$AUTH_KEYS" "$DASH_HOME/.ssh/authorized_keys"
else
  say "  no --authorized-keys given: put the public key in $DASH_HOME/.ssh/authorized_keys (0700 dir, 0600 file) before the first ssh"
fi

# ---- 3 venv + hash-pinned wheels + PATH symlink ---------------------------------------------------------
step 3 "venv $VENV, offline hash-pinned install, /usr/local/bin/pepepane"
run install -d -m 0755 "$PREFIX" "$WHEELS"
for whl in "$HERE"/wheels/*.whl; do
  [ -f "$whl" ] || { say "  (no wheels staged under $HERE/wheels)"; break; }
  run install -m 0644 "$whl" "$WHEELS/"
done
run install -m 0644 "$HERE/requirements.lock" "$LOCK"
if [ "$DRY_RUN" = 0 ] && [ -x "$VENV/bin/python" ]; then
  say "  venv exists"
elif [ "$ROUTE" = a ]; then
  run python3 -m venv "$VENV"
else
  run python3 -m venv --without-pip "$VENV"
  run "$VENV/bin/python" "$PIP_WHEEL/pip" install --no-index "$PIP_WHEEL"
fi
run "$VENV/bin/python" -m pip install --no-index --find-links "$WHEELS" --only-binary=:all: --require-hashes -r "$LOCK"
run ln -sfn "$VENV/bin/pepepane" /usr/local/bin/pepepane
say "  the venv is root-owned and 0755: $DASH_USER executes it and cannot modify its own tool"

# ---- 4 broker files, verified by content -----------------------------------------------------------------
step 4 "broker files -> $BROKER_DIR, re-verified against MANIFEST.sha256 after the copy (staged tree checked before step 1)"
run install -d -m 0755 "$PREFIX/broker" "$BROKER_DIR"
for f in "$TREE"/imd_dashd/*.py; do
  run install -m 0644 "$f" "$BROKER_DIR/"
done
run rm -rf "$BROKER_DIR/__pycache__"
run install -m 0644 "$MANIFEST_SRC" "$MANIFEST_DST"
if [ "$DRY_RUN" = 1 ]; then
  say "  [dry-run] (cd $PREFIX/broker && grep '  imd_dashd/' $MANIFEST_DST | sha256sum -c --strict)"
else
  (cd "$PREFIX/broker" && grep '  imd_dashd/' "$MANIFEST_DST" | sha256sum -c --strict) || die "installed broker files do not match MANIFEST"
fi

# ---- 5 units -------------------------------------------------------------------------------------------
step 5 "units imd-dashd.socket + imd-dashd.service + 10-seat.conf (socket-activated; the service is never enabled itself)"
run install -m 0644 "$HERE/imd-dashd.socket" "$UNIT_DIR/imd-dashd.socket"
run install -m 0644 "$HERE/imd-dashd.service" "$UNIT_DIR/imd-dashd.service"
# The root broker learns its seat only from --seat (without it the gate's plane half is always local-only and a
# drain never fires on the plane). The unit file stays the MANIFEST-pinned contract text; the seat goes in a drop-in
# that resets ExecStart (Type=simple takes one) and re-states it with --seat (deviation 10).
BROKER_DROPIN_DIR="$UNIT_DIR/imd-dashd.service.d"
render_broker_dropin() {
  cat <<DROPIN
# written by deploy/vps/install.sh -- the broker's seat for the fresh GET /seats/<id>/standing at every apply (spec §11)
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -I $BROKER_DIR/imd_dashd.py --seat $SEAT
DROPIN
}
say "  $BROKER_DROPIN_DIR/10-seat.conf:"
render_broker_dropin | sed 's/^/    > /'
run install -d -m 0755 "$BROKER_DROPIN_DIR"
if [ "$DRY_RUN" = 1 ]; then
  say "  [dry-run] install -m 0644 <the 10-seat.conf above> $BROKER_DROPIN_DIR/10-seat.conf"
else
  tmp="$(mktemp)"
  render_broker_dropin > "$tmp"
  install -m 0644 "$tmp" "$BROKER_DROPIN_DIR/10-seat.conf"
  rm -f "$tmp"
fi
run systemctl daemon-reload
run systemctl enable --now imd-dashd.socket
say "  socket: $SOCKET_PATH (0660 root:$DASH_USER in a 0755 root dir)"

# ---- 6 TUI slice fence, sshd Match block, runtime configuration ------------------------------------------
step 6 "TUI slice fence, sshd Match User $DASH_USER, $DASH_HOME/.config/pepepane.toml"
DASH_UID="$(id -u "$DASH_USER" 2>/dev/null || echo '<uid>')"
run install -d -m 0755 "$UNIT_DIR/user-$DASH_UID.slice.d"
run install -m 0644 "$HERE/50-pepepane.conf" "$UNIT_DIR/user-$DASH_UID.slice.d/50-pepepane.conf"
run systemctl daemon-reload
run install -m 0644 "$HERE/10-imd-dash.sshd.conf" "$SSHD_DIR/10-imd-dash.sshd.conf"
run sshd -t
run systemctl reload ssh

render_config() {
  cat <<CONFIG
# written by deploy/vps/install.sh -- configuration, never secrets (spec §12.1 "Runtime configuration for the TUI")
# precedence in pepepane: CLI flags > PEPEPANE_* env > this file > ~/.maxpane/config.toml [seat] token_id > defaults
[pepepane]
host = "systemd"
unit = "$WORKER_UNIT"
broker = "$SOCKET_PATH"
seat = $SEAT
agent = $AGENT
CONFIG
}
say "  $DASH_HOME/.config/pepepane.toml:"
render_config | sed 's/^/    | /'
if [ "$DRY_RUN" = 0 ]; then
  install -d -m 0700 -o "$DASH_USER" -g "$DASH_USER" "$DASH_HOME/.config"
  tmp="$(mktemp)"
  render_config > "$tmp"
  install -m 0644 -o "$DASH_USER" -g "$DASH_USER" "$tmp" "$DASH_HOME/.config/pepepane.toml"
  rm -f "$tmp"
fi

# ---- 7 worker drop-in (§16 #4, at an idle gap) -------------------------------------------------------------------
step 7 "worker drop-in 20-hide-dash.conf (owner decision spec §16 #4)"
if [ "$WORKER_DROPIN" = 1 ]; then
  run install -d -m 0755 "$UNIT_DIR/$WORKER_UNIT.d"
  run install -m 0644 "$HERE/20-hide-dash.conf" "$UNIT_DIR/$WORKER_UNIT.d/20-hide-dash.conf"
  run systemctl daemon-reload
  say "  NOT applied to the running daemon. It takes effect at the next restart of $WORKER_UNIT:"
  say "  use pepepane CONTROL [d] drain-restart (4 idle beats, fresh gate), or restart the unit by hand at an idle gap."
else
  say "  skipped: pass --worker-dropin at an idle gap (spec §16 #4, approved 2026-09-26), then one drained restart from CONTROL. The file is staged at $HERE/20-hide-dash.conf."
fi

# ---- 8 probe -------------------------------------------------------------------------------------------
step 8 "probe (owner-run, once; spec §14 'Only on the VPS')"
say "  bash $HERE/probe_seat_host.sh > /root/seat_install_probe.md     # then paste into docs/seat_install_probe.md"
say "  it applies one write verb, doctor (one runtime turn); add --skip-doctor to avoid that."
say
say "done. daily path:  ssh -t $DASH_USER@<host> pepepane      headless:  ssh $DASH_USER@<host> pepepane --once --offline"
