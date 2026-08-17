#!/usr/bin/env python3
"""One-shot tooling that vendors the WhitelistCurator ABI for the curator dashboard.

    ############################################################################
    #  NOTHING IMPORTS THIS SCRIPT.                                            #
    #                                                                          #
    #  It lives in scripts/ and is run by hand.  The shipped dashboard reads    #
    #  maxpane_dashboard/abis/curator/whitelist_curator.json off disk and never #
    #  performs ABI acquisition itself (CLAUDE.md: "vendored ABI JSON per       #
    #  protocol -- never fetched at runtime").  If you ever find                #
    #  `import vendor_curator_abi` under maxpane_dashboard/, that is a bug --   #
    #  delete the import, not this warning.                                     #
    ############################################################################

Why this exists
---------------
``WhitelistCurator`` (``0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91``, Ethereum
mainnet) is verified on Blockscout.  During the 2026-08-16 research session two
agents independently saved the same ``/api/v2/smart-contracts/<addr>`` response,
as ``tests/fixtures/curator/captures/contract.json`` and ``.../wc_abi.json``.
Both carry an ``abi`` key and the two arrays are byte-for-byte equal, so either
is a valid source; this script reads ``contract.json`` (the fuller save, which
also carries the verified ``source_code``) and writes the array out.

There is **no network path in this file at all**.  The acquisition already
happened; the capture is the provenance, and re-running this script is a pure
function of committed bytes.  That is what makes
``test_the_vendored_abi_matches_the_capture`` able to re-run the extraction in
memory and diff it against the committed artifact.

Usage
-----
    .venv/bin/python scripts/vendor_curator_abi.py            # write the ABI
    .venv/bin/python scripts/vendor_curator_abi.py --check    # verify only

Generated artifact
------------------
    maxpane_dashboard/abis/curator/whitelist_curator.json   50 entries
        6 events, 10 errors, 32 functions, 1 constructor, 1 receive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: Repository root, resolved from this file so the script runs from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: The committed Blockscout smart-contracts response the ABI is extracted from.
CAPTURE = REPO_ROOT / "tests" / "fixtures" / "curator" / "captures" / "contract.json"

#: The second save of the same endpoint.  Read only to prove the two agree.
CAPTURE_TWIN = REPO_ROOT / "tests" / "fixtures" / "curator" / "captures" / "wc_abi.json"

#: Where the vendored array lands.  One subdirectory per protocol, like abis/fwa/.
OUTPUT = (
    REPO_ROOT / "maxpane_dashboard" / "abis" / "curator" / "whitelist_curator.json"
)


def extract_abi(capture_path: Path = CAPTURE) -> list[dict[str, Any]]:
    """The ABI array out of a Blockscout smart-contracts response.

    Pure: reads one committed file, opens no socket.  The tests call this and
    compare the result against the committed artifact, so a hand-edit of the
    JSON fails instead of shipping.
    """
    with open(capture_path, encoding="utf-8") as fh:
        body = json.load(fh)
    abi = body["abi"]
    if not isinstance(abi, list) or not abi:
        raise SystemExit(f"{capture_path.name}: no usable 'abi' array")
    return abi


def render(abi: list[dict[str, Any]]) -> str:
    """The exact bytes the artifact holds: indent=2 plus a trailing newline."""
    return json.dumps(abi, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed artifact matches the capture; write nothing",
    )
    parser.add_argument("--capture", type=Path, default=CAPTURE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    abi = extract_abi(args.capture)
    twin = extract_abi(CAPTURE_TWIN)
    if abi != twin:
        raise SystemExit(
            "contract.json and wc_abi.json disagree -- two saves of one endpoint "
            "diverging means one is stale.  Resolve before vendoring."
        )

    text = render(abi)
    if args.check:
        if not args.output.exists():
            print(f"MISSING {args.output}", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != text:
            print(f"STALE {args.output}", file=sys.stderr)
            return 1
        print(f"OK {args.output} ({len(abi)} entries)")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {args.output} ({len(abi)} entries)")
    return 0


if __name__ == "__main__":  # pragma: no cover - one-shot tooling
    raise SystemExit(main())
