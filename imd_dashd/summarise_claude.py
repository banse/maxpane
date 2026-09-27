"""Claude Code transcript summariser for the PEPEPANE dashboard (spec §5.4, §10; contract §C.8).

Self-contained on purpose: on the Mac the broker pipes this file into the worker container
(``docker exec -i imd-worker timeout -s TERM -k 5 20 python3 -``, container python 3.11.2),
so it imports only the standard library, nothing from ``imd_dashd`` or
``maxpane_dashboard``, and is Python 3.11 syntax. It emits metadata only -- model, effort,
turns, token classes, timings, side-model usage, API-error statuses -- never a prompt, a
tool result or assistant text; the one free-text field it passes on,
``apiErrors[].message``, is redacted by the caller. ``cost-state.totalCostUSD`` and every
``costUSD`` are never read (spec §10 no-currency rule).

API-equal definitions (spec §10; reconciled 40/40, fill3 §2):

* turns = the count of ``type:"user"`` lines (== tool_use blocks + 1 == SDK ``num_turns``);
* tokens summed over DISTINCT ``message.id`` -- Claude Code writes one line per content block
  with identical usage, so per-line summing over-counts 1.5-1.9x (the aidude writer's bug);
  input = ``input_tokens``, output = ``output_tokens``, cached = ``cache_read_input_tokens +
  cache_creation_input_tokens``, cacheWrite = 0 (creation is already inside cached);
* side model = ``cost-state.modelUsage`` keys starting ``claude-haiku-4-5``: SDK side calls,
  absent from the API usage -- reported separately, never added;
* turn-1 context = the first assistant ``cache_creation + cache_read + input_tokens``.

Slug exclusions are EXACT matches, never prefixes (spec §5.4): a prefix match on
``-home-imd`` would also swallow ``-home-imd--identitymd-work``, the slug a research task
uses on the Mac.

Hostile size (spec §5.4): files over 64 MiB are skipped unopened, lines over 1 MiB are
skipped unparsed and counted, each file has a 5 s wall clock and each call a budget.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timezone

MAX_FILE_BYTES = 64 * 1024 * 1024  #: skip larger files unopened (spec §5.4)
MAX_LINE_BYTES = 1024 * 1024  #: skip longer lines unparsed (spec §5.4)
PER_FILE_WALL_S = 5.0  #: per-file wall clock (spec §5.4)
DEFAULT_BUDGET_S = 15.0  #: per-call budget inside the in-container `timeout ... 20` (spec §4.2)
CLAUDE_CLEANUP_DAYS = 30  #: cleanupPeriodDays default: older transcripts are swept (fill8 §4)
CLAUDE_EXCLUDED_SLUGS = frozenset({"-home-imd", "-tmp", "-tmp-probe-ws", "-tmp-probe-ws2", "-tmp-probe-ws3"})  #: EXACT
CLAUDE_DOCTOR_SLUG_PREFIX = "-home-imd--identitymd-work-doctor-"  #: `imd doctor` smoke runs (fill6 §3)
CLAUDE_RESEARCH_SLUG = "-home-imd--identitymd-work"  #: cwd = work root; exact; NOT excluded (mutation proof 35)
CLAUDE_TASK_SLUG_PREFIX = "-home-imd--identitymd-work-"  #: + <jobId 36>-<nodeId 36>
SIDE_MODEL_PREFIX = "claude-haiku-4-5"  #: SDK side calls in cost-state.modelUsage (fill3 §2)
SYNTHETIC_MODEL = "<synthetic>"  #: client-side error messages, not a model
STR_CAP = 200
MESSAGE_CAP = 500
MAX_API_ERRORS = 20  #: a task can append lines; the list stays bounded
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SYNTHETIC_STATUS_RE = re.compile(r"API Error: (\d{3})")

SESSION_KEYS = (
    "path", "runtime", "cwd", "slug", "kind", "jobId", "nodeId", "startedUtc", "endedUtc", "mtime", "bytes",
    "model", "effort", "turns", "turnsDefinition", "tokens", "sideModel", "ttftMs", "wallMs", "turn1Context",
    "maxTurnsReached", "maxTurns", "apiErrors", "lastAgentMessageEmpty", "tokenCountInfoMissing",
    "taskCompleteErrorPresent", "quota", "skippedOversize", "error",
)


def classify_slug(slug: str) -> str:
    """``task | research | doctor | manual | unknown`` for a ``~/.claude/projects/<slug>`` dir name.

    Exclusions are exact (``CLAUDE_EXCLUDED_SLUGS``); the research slug is exact and counts;
    doctor is the ``-home-imd--identitymd-work-doctor-*`` pattern (spec §5.4, §10).
    """
    if not isinstance(slug, str) or not slug:
        return "unknown"
    if slug in CLAUDE_EXCLUDED_SLUGS:
        return "manual"
    if slug == CLAUDE_RESEARCH_SLUG:
        return "research"
    if slug.startswith(CLAUDE_DOCTOR_SLUG_PREFIX) and len(slug) > len(CLAUDE_DOCTOR_SLUG_PREFIX):
        return "doctor"
    if parse_task_slug(slug) is not None:
        return "task"
    return "unknown"


def parse_task_slug(slug: str) -> tuple[str, str] | None:
    """``-home-imd--identitymd-work-<jobId>-<nodeId>`` -> ``(jobId, nodeId)``.

    Both ids are 36-char UUIDs that themselves contain ``-``, so the split is by length.
    """
    if not isinstance(slug, str) or not slug.startswith(CLAUDE_TASK_SLUG_PREFIX):
        return None
    rest = slug[len(CLAUDE_TASK_SLUG_PREFIX):]
    if len(rest) != 73 or rest[36] != "-":
        return None
    job, node = rest[:36], rest[37:]
    if UUID_RE.fullmatch(job) and UUID_RE.fullmatch(node):
        return (job, node)
    return None
