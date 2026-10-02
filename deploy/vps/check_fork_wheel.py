#!/usr/bin/env python3
"""Compare installed fork bytes with the staged wheel (stdlib only, run with python -I)."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import sys
import sysconfig
import zipfile


def check_fork_wheel(wheels: Path, purelib: Path) -> str:
    candidates = list(wheels.glob("maxpane-*.whl"))
    if len(candidates) != 1:
        raise ValueError("expected exactly one staged maxpane wheel")
    wheel = candidates[0]
    compared = 0
    with zipfile.ZipFile(wheel) as archive:
        records = [name for name in archive.namelist() if name.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise ValueError("expected exactly one wheel RECORD")
        for row in csv.reader(io.StringIO(archive.read(records[0]).decode("utf-8"))):
            if len(row) != 3:
                raise ValueError("invalid wheel RECORD row")
            name, expected, _size = row
            if name == records[0]:
                continue
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not expected.startswith("sha256="):
                raise ValueError("invalid path or hash in wheel RECORD")
            try:
                data = (purelib / path).read_bytes()
            except FileNotFoundError:
                raise ValueError(f"installed file missing: {name}") from None
            actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            if expected != "sha256=" + actual:
                raise ValueError(f"installed file mismatch: {name}")
            compared += 1
    if not compared:
        raise ValueError("zero installed files compared")
    prefix = hashlib.sha256(wheel.read_bytes()).hexdigest()[:10]
    return f"fork post-install check: {compared} files matched (wheel sha256 {prefix})"


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: check_fork_wheel.py WHEELS_DIRECTORY")
        print(check_fork_wheel(Path(sys.argv[1]), Path(sysconfig.get_path("purelib"))))
    except (OSError, ValueError, zipfile.BadZipFile, csv.Error) as exc:
        print(f"fork post-install check FAILED: {exc}; re-stage the archive and re-run install.sh", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
