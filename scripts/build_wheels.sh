#!/usr/bin/env bash
# scripts/build_wheels.sh -- build the offline, hash-pinned install set for the VPS (spec §12.1 install route a/b).
# Runs on the Mac WITH network (a build step, never a test). Outputs under --out (default deploy/vps):
#   wheels/               the shared dependency closure for cp312 and cp314 / manylinux_2_17 x86_64 + the fork (gitignored)
#   requirements.lock     `uv pip compile --generate-hashes` of pyproject [seat] + a `maxpane==<version> --hash=` block (committed)
#   MANIFEST.sha256       sha256 of imd_dashd/*.py, every deploy/vps file the installer touches, the lock and the fork wheel
# and dist/seat-deploy-<short sha>.tar.gz -- imd_dashd/ + deploy/vps/ (incl. wheels/), the tree install.sh runs from.
# --manifest-only re-hashes without resolving, downloading or building (after editing imd_dashd/ or deploy/vps/).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/deploy/vps"
SUPPORTED_PYTHONS=(3.12 3.14)        # both seats ship in every archive; bound to install.sh by an agreement test
UV_PLATFORM=x86_64-manylinux_2_17    # uv's spelling
PIP_PLATFORM=manylinux_2_17_x86_64   # pip's spelling
MANIFEST_ONLY=0
UPGRADE=0
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"

usage() {
  cat <<'USAGE'
usage: scripts/build_wheels.sh [--out DIR] [--platform x86_64-manylinux_2_17]
                               [--pip-platform manylinux_2_17_x86_64] [--manifest-only] [--upgrade] [--help]
Writes DIR/wheels/*.whl, DIR/requirements.lock, DIR/MANIFEST.sha256 and dist/seat-deploy-<sha>.tar.gz.
Reuses committed third-party versions; --upgrade permits a deliberate, reviewed version change.
Always stages Python 3.12 and 3.14; selecting a single interpreter is not supported.
Needs: uv (https://astral.sh/uv), the repo .venv (pip download), network (PyPI), git.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="${2:-}"; shift ;;
    --platform) UV_PLATFORM="${2:-}"; shift ;;
    --pip-platform) PIP_PLATFORM="${2:-}"; shift ;;
    --manifest-only) MANIFEST_ONLY=1 ;;
    --upgrade) UPGRADE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; printf 'build_wheels.sh: unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done
case "$OUT" in /*) ;; *) OUT="$REPO/$OUT" ;; esac
WHEELS="$OUT/wheels"
LOCK="$OUT/requirements.lock"
MANIFEST="$OUT/MANIFEST.sha256"

die()       { printf 'build_wheels.sh: %s\n' "$*" >&2; exit 1; }
have()      { command -v "$1" >/dev/null 2>&1; }
sha256_of() { if have sha256sum; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

[ -x "$PYTHON" ] || die "$PYTHON missing -- create the repo venv first (CLAUDE.md Build & run)"
VERSION="$("$PYTHON" -c 'import tomllib, sys; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$REPO/pyproject.toml")"
FORK_WHEEL="$WHEELS/maxpane-$VERSION-py3-none-any.whl"

if [ "$MANIFEST_ONLY" = 0 ]; then
  have uv || die "uv not found (curl -LsSf https://astral.sh/uv/install.sh | sh)"
  cd "$REPO"
  mkdir -p "$WHEELS"
  closures=()
  trap 'rm -f "${closures[@]}"' EXIT
  committed_lock="$REPO/deploy/vps/requirements.lock"
  if [ "$UPGRADE" = 0 ]; then
    [ -f "$committed_lock" ] || die "committed requirements.lock missing; use --upgrade for a deliberate new resolution"
  fi
  # 1. Seed each resolution independently; --upgrade deliberately leaves both outputs unseeded.
  for PY_VERSION in "${SUPPORTED_PYTHONS[@]}"; do
    closure="$(mktemp)"
    closures+=("$closure")
    if [ "$UPGRADE" = 0 ]; then
      awk '/^# pepepane fork wheel/ {exit} {print}' "$committed_lock" > "$closure"
    fi
    uv pip compile --quiet --generate-hashes --python-version "$PY_VERSION" --python-platform "$UV_PLATFORM" \
       --extra seat --custom-compile-command "scripts/build_wheels.sh" -o "$closure" pyproject.toml
    cmp -s <(grep -E '^[A-Za-z0-9][A-Za-z0-9._-]*==' "${closures[0]}" | sort) \
      <(grep -E '^[A-Za-z0-9][A-Za-z0-9._-]*==' "$closure" | sort) \
      || die "interpreter closures differ; Python ${SUPPORTED_PYTHONS[*]} must share one dependency version set"
  done
  # The final declared interpreter (3.14) supplies the committed lock.
  if [ "$UPGRADE" = 0 ]; then
    cmp -s <(grep -E '^[A-Za-z0-9][A-Za-z0-9._-]*==' "$closure" | sort) \
      <(awk '/^# pepepane fork wheel/ {exit} {print}' "$committed_lock" | grep -E '^[A-Za-z0-9][A-Za-z0-9._-]*==' | sort) \
      || die "third-party versions changed; review and record an explicit --upgrade"
  fi
  rm -f "$WHEELS"/*.whl
  # 2. Download every declared ABI into one directory; pure py3-none-any wheels are shared.
  index=0
  for PY_VERSION in "${SUPPORTED_PYTHONS[@]}"; do
    ABI="cp${PY_VERSION//./}"
    "$PYTHON" -m pip download --quiet --no-deps --only-binary=:all: --require-hashes --platform "$PIP_PLATFORM" \
       --python-version "$PY_VERSION" --implementation cp --abi "$ABI" -r "${closures[$index]}" -d "$WHEELS"
    index=$((index + 1))
  done
  # 3. build the fork wheel from this checkout (hatchling; reproducible for the same tree)
  uv build --quiet --wheel --out-dir "$WHEELS" "$REPO"
  [ -f "$FORK_WHEEL" ] || die "expected $FORK_WHEEL after uv build"
  # 4. the lock = closure + fork by content; installer forces the fork first, then resolves the full lock
  {
    cat "$closure"
    printf '\n# pepepane fork wheel, built by scripts/build_wheels.sh from this checkout; PyPI has a different maxpane %s\n' "$VERSION"
    printf 'maxpane==%s \\\n    --hash=sha256:%s\n' "$VERSION" "$(sha256_of "$FORK_WHEEL")"
  } > "$LOCK"
  rm -f "${closures[@]}"
  trap - EXIT
fi
[ -f "$FORK_WHEEL" ] || die "$FORK_WHEEL missing -- run without --manifest-only first"
[ -f "$LOCK" ] || die "$LOCK missing -- run without --manifest-only first"

# Mandatory archive guard, including --manifest-only: every wheel is locked and both ABIs exist.
for wheel in "$WHEELS"/*.whl; do
  digest="$(sha256_of "$wheel")"
  grep -Fq -- "--hash=sha256:$digest" "$LOCK" || die "wheel hash absent from lock: $(basename "$wheel")"
done
for PY_VERSION in "${SUPPORTED_PYTHONS[@]}"; do
  ABI="cp${PY_VERSION//./}"
  set -- "$WHEELS"/pydantic_core-*-"$ABI"-"$ABI"-*.whl
  [ -f "$1" ] || die "pydantic_core wheel missing for $ABI; rebuild the complete interpreter set"
done

# 5. MANIFEST.sha256: repo-relative paths, `sha256sum -c` format (two spaces). Never lists itself.
{
  for f in "$REPO"/imd_dashd/*.py; do
    printf '%s  %s\n' "$(sha256_of "$f")" "imd_dashd/$(basename "$f")"
  done
  for name in imd-dashd.socket imd-dashd.service 20-hide-dash.conf 50-pepepane.conf 10-imd-dash.sshd.conf \
              install.sh probe_seat_host.sh check_fork_wheel.py requirements.lock; do
    [ -f "$OUT/$name" ] || die "$OUT/$name missing -- the MANIFEST covers every file the installer touches"
    printf '%s  %s\n' "$(sha256_of "$OUT/$name")" "deploy/vps/$name"
  done
  printf '%s  %s\n' "$(sha256_of "$FORK_WHEEL")" "deploy/vps/wheels/$(basename "$FORK_WHEEL")"
} > "$MANIFEST"

# 6. the deploy tree install.sh runs from
mkdir -p "$REPO/dist"
SHA="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || printf 'nogit')"
TARBALL="$REPO/dist/seat-deploy-$SHA.tar.gz"
case "$(tar --version)" in
  *bsdtar*) tar_owner=(--uid 0 --gid 0 --uname root --gname root) ;;
  *) tar_owner=(--owner=0 --group=0 --numeric-owner) ;;
esac
tar "${tar_owner[@]}" -C "$REPO" --exclude='__pycache__' --exclude='.gitignore' -czf "$TARBALL" imd_dashd deploy/vps

n_wheels="$(ls "$WHEELS"/*.whl | wc -l | tr -d ' ')"
printf 'wheels: %s files in %s (fork wheel %s)\n' "$n_wheels" "$WHEELS" "$(basename "$FORK_WHEEL")"
printf 'lock:   %s (%s requirements)\n' "$LOCK" "$(grep -c '^[A-Za-z0-9].*==' "$LOCK")"
printf 'manifest: %s (%s lines)\n' "$MANIFEST" "$(wc -l < "$MANIFEST" | tr -d ' ')"
printf 'tarball: %s (%s bytes)\n' "$TARBALL" "$(wc -c < "$TARBALL" | tr -d ' ')"
printf 'fork wheel sha256: %s\n' "$(sha256_of "$FORK_WHEEL")"
