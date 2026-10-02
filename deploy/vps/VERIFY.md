# Verifying the deploy tree

`MANIFEST.sha256` lists, one per line as `<sha256>  <path>` (the `sha256sum -c` format), every file the installer copies
to the host or feeds to pip: the broker package `imd_dashd/*.py` (installed verbatim under
`/opt/imd-dash/broker/imd_dashd/`), the two units, the three drop-ins, `install.sh`, `probe_seat_host.sh`,
`check_fork_wheel.py`, `requirements.lock`, and the fork wheel `deploy/vps/wheels/maxpane-<version>-py3-none-any.whl`. Paths are repo-relative,
so one file checks the staged tree before anything is installed and, path-mapped, the installed copies afterwards.
`requirements.lock` carries the same fork-wheel hash as a `maxpane==<version> --hash=sha256:…` block.
The installer first forces a hash-checked fork-only reinstall with `--require-hashes --force-reinstall --no-deps`, then runs the
unchanged full-lock install to resolve its dependency closure. A plain full-lock reinstall skips an already-satisfied
fork and does not hash-check it. The one-entry file is cut from the final `# pepepane fork wheel` block and must
contain exactly one maxpane pin and one SHA-256 hash.

The shared stdlib `check_fork_wheel.py`, run by the venv's `python -I`, reads the staged wheel RECORD with csv/zipfile
and hashes every corresponding installed file under purelib. Missing or mismatching bytes and zero comparisons fail.
It prints a file count and ten-character wheel SHA prefix; it never trusts the installed RECORD's copied hashes.
Pip-generated files absent from the wheel RECORD are naturally ignored.

## Regenerate (Mac, at the commit you deploy)

~~~sh
PYTHON=/path/to/checkout/.venv-pepepane/bin/python scripts/build_wheels.sh --out deploy/vps                   # reproduce locked versions, download, build and hash
PYTHON=/path/to/checkout/.venv-pepepane/bin/python scripts/build_wheels.sh --out deploy/vps --manifest-only   # only re-hash, after editing imd_dashd/ or deploy/vps/
~~~

Normal builds seed the resolver from the checkout's committed `deploy/vps/requirements.lock`, excluding the fork-wheel
block, even when another output directory is selected. The resolver runs from the checkout root to keep annotations
relative; any third-party version drift stops the build before downloading or replacing existing wheels. Use
`scripts/build_wheels.sh --out deploy/vps --upgrade` only for a deliberate upgrade, then review the lock diff and record
the changed versions in `docs/decisions.md` before shipping. Archive owner headers use neutral root identifiers.

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
`probe_seat_host.sh` p15 repeats the check for the installed broker files, the units and drop-ins (paths mapped
from `deploy/vps/` to `/etc/…`) and the wheel and lock under `/opt/imd-dash`; it also runs the same installed-byte check:

~~~sh
cd /opt/imd-dash/broker && grep '  imd_dashd/' /opt/imd-dash/MANIFEST.sha256 | sha256sum -c --strict
cd /opt/imd-dash && grep -E '  deploy/vps/(wheels/|requirements.lock)' MANIFEST.sha256 | sed 's#  deploy/vps/#  #' | sha256sum -c --strict
~~~

## What the checksum proves, and what it does not prove

- Proves: the bytes on the host are the bytes that were hashed on the Mac, and the venv was installed only from wheels
  whose hashes are in `requirements.lock` for newly installed distributions (pip refuses unhashed downloads and sdists).
  The fork is always reinstalled and its actual installed bytes are checked. Existing satisfied third-party packages are
  not re-hashed by pip or by the fork check.
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
