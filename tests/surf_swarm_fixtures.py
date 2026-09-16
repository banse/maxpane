"""The committed swarm captures, exactly as the keyless API served them."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SWARM_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surf" / "swarm"


def swarm_capture(name: str) -> Any:
    with open(SWARM_FIXTURES / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)
