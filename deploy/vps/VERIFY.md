# Verifying the deploy tree

`MANIFEST.sha256` lists, one per line as `<sha256>  <path>` (the `sha256sum -c` format), every file the installer copies
to the host or feeds to pip: the broker package `imd_dashd/*.py` (installed verbatim under
`/opt/imd-dash/broker/imd_dashd/`), the two units, the three drop-ins, `install.sh`, `probe_seat_host.sh`,
`requirements.lock`, and the fork wheel `deploy/vps/wheels/maxpane-<version>-py3-none-any.whl`. Paths are repo-relative,
so one file checks the staged tree before anything is installed and, path-mapped, the installed copies afterwards.
`requirements.lock` carries the same fork-wheel hash as a `maxpane==<version> --hash=sha256:…` block, so a single
`pip install --no-index --find-links /opt/imd-dash/wheels --only-binary=:all: --require-hashes -r requirements.lock`
installs the 20-wheel dependency closure and the fork under one hash check.

## Regenerate (Mac, at the commit you deploy)

~~~sh
PYTHON=/Users/banse/codex/maxpane/.venv-pepepane/bin/python scripts/build_wheels.sh --out deploy/vps                   # resolve + download the closure, build the fork wheel, write lock + MANIFEST + tarball
PYTHON=/Users/banse/codex/maxpane/.venv-pepepane/bin/python scripts/build_wheels.sh --out deploy/vps --manifest-only   # only re-hash, after editing imd_dashd/ or deploy/vps/
~~~

The fork wheel's hash changes with every commit that touches `maxpane_dashboard/`; the guard
`tests/test_seat_deploy_files.py::test_manifest_hashes_match_the_committed_files` reddens whenever a listed file is
edited without a regeneration, and `::test_manifest_wheel_hash_equals_the_lock_hash` binds the lock's `maxpane` hash to
the MANIFEST's wheel line.

## Check before staging (Mac)

~~~sh
sha256sum -c --strict deploy/vps/MANIFEST.sha256           # macOS: shasum -a 256 -c deploy/vps/MANIFEST.sha256
~~~

## Check on the VPS

`install.sh` runs `sha256sum -c --strict` on the staged tree from its root at the end of its preflight, before step 1,
and installs nothing on a mismatch (step 3 feeds the staged lock and wheels to pip, so the check cannot wait for step 4);
step 4 then re-verifies the installed broker files against the copy it placed at `/opt/imd-dash/MANIFEST.sha256`.
`probe_seat_host.sh` section 14 repeats the check for the installed broker files, the units and drop-ins (paths mapped
from `deploy/vps/` to `/etc/…`) and the wheel and lock under `/opt/imd-dash`:

~~~sh
cd /opt/imd-dash/broker && grep '  imd_dashd/' /opt/imd-dash/MANIFEST.sha256 | sha256sum -c --strict
cd /opt/imd-dash && grep -E '  deploy/vps/(wheels/|requirements.lock)' MANIFEST.sha256 | sed 's#  deploy/vps/#  #' | sha256sum -c --strict
~~~

## What the checksum proves, and what it does not prove

- Proves: the bytes on the host are the bytes that were hashed on the Mac, and the venv was installed only from wheels
  whose hashes are in `requirements.lock` (pip's hash-checking mode refuses anything else, including a build from an
  sdist). Nothing more.
- Does not prove authorship. `MANIFEST.sha256` is unsigned — the same limit as the daemon's own `SHA256SUMS` (aidude
  runbook §8.2: a checksum proves transfer, not author). A tampered Mac checkout hashes cleanly; a tampered staging path
  that also rewrites the MANIFEST hashes cleanly. If the staging path is ever untrusted, sign the MANIFEST with
  `ssh-keygen -Y sign -f ~/.ssh/<key> -n file deploy/vps/MANIFEST.sha256` and verify with `ssh-keygen -Y verify` on the
  host (follow-up in `docs/seat_followups.md`).
- Does not prove the fork wheel matches the checkout unless it was built from that checkout by
  `scripts/build_wheels.sh` at the deployed commit; a wheel copied from elsewhere with the right filename fails the lock
  and the MANIFEST, which is the point.
- Does not vet the third-party wheels beyond their hashes: the closure's hashes come from PyPI through
  `uv pip compile --generate-hashes`; trusting them is trusting PyPI at resolution time, pinned by content thereafter.
- Does not cover `~/.maxpane`, `/var/log/imd-dash` or anything the running system writes — only the installed tree.
