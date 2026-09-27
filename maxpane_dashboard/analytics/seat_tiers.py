"""Derived per-task inference tier for the PEPEPANE dashboard (spec §5.4, §10; contract §C.9) -- pure.

The tier (economy / standard / premium) is a field of the control plane's WebSocket task frame
(``budget.inference``) and is never logged or persisted (fill2 §1). The only local facts are the
``(model, effort)`` pair the runtime recorded (Codex ``turn_context``, Claude ``message.model`` +
``effort``) and the ``running <rt>[ on <model>]`` log line. So the tier is DERIVED through a
**dated** table, because the tables changed under us five times in two days (fill2 §6):

* bundle constants at ``5bfa8261``: economy claude sonnet-5/low, codex gpt-6-luna/high; premium
  codex gpt-6-astra/xhigh, claude fable-5-1/high; standard = the runtime default (no ``-m``);
* config overrides beat constants for every tier (``chooseModel``, fill2 §2) -- on #7 economy and
  standard are the same pair since 2026-09-23 19:56, so a task there renders ``economy/standard``;
* every derived tier is rendered with the ``~`` mark; runs before 2026-09-21 19:00 have no tier.

The broker's ``inference`` projection (owner decision §16 #5), when passed, replaces the dated rows
going forward. No I/O, no clock: ``at`` is always passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

TIERS = ("economy", "standard", "premium")
PREMIUM_EFFORTS = {"codex": ("xhigh", "max", "ultra"), "claude": ("high", "xhigh", "max")}  #: isPremiumModel (fill2 §2)
BUNDLE_CONSTANTS = {"5bfa8261": {
    "economy": {"claude": ("claude-sonnet-5", "low"), "codex": ("gpt-6-luna", "high")},
    "premium": {"codex": ("gpt-6-astra", "xhigh"), "claude": ("claude-fable-5-1", "high")},
}}
CURRENT_BUNDLE = "5bfa8261"
TIER_MARK = "~"
TIER_SHARED = "economy/standard"
DASH = "--"  #: mirrors widgets.fmt.DASH (fmt.py:64); analytics may not import widgets


@dataclass(frozen=True)
class TierRow:
    since_utc: str  # "2026-09-21T19:00:00Z"
    seat: int | None  # None = every seat (a bundle constant or a runtime default)
    runtime: str | None  # None = every runtime
    tier: str  # "economy" | "standard" | "premium"
    model: str
    effort: str
    note: str


#: Dated rows, oldest first (spec §10, §16 #16; fill2 §2-§6; memory notes imd-worker-285d1984-release,
#: imd-seat7-vps). Seat-specific rows (config overrides) beat seat-less rows whatever their order.
TIER_HISTORY: tuple[TierRow, ...] = (
    TierRow("2026-09-21T19:00:00Z", None, "claude", "economy", "claude-sonnet-5", "low",
            "bundle ECONOMY_MODELS.claude; oracle_assess moved to sonnet-5 at 19:00 UTC"),
    TierRow("2026-09-21T19:00:00Z", None, "codex", "economy", "gpt-5.6-terra", "low",
            "bundle ECONOMY_MODELS.codex before 61d04d62"),
    TierRow("2026-09-21T19:00:00Z", None, "claude", "standard", "claude-opus-5", "high",
            "Claude Code default before 2.1.280 (flag-less doctor runs: opus-5/high, fill2 §4)"),
    TierRow("2026-09-21T19:00:00Z", 7, "codex", "economy", "gpt-5.6-luna", "medium",
            "#7 config inference.economy.codex at setup (effective from #7's first run on 09-22)"),
    TierRow("2026-09-21T19:00:00Z", 7, "codex", "standard", "gpt-5.6-luna", "medium",
            "#7 runtime default: the /opt/imd-worker/bin/codex wrapper forces gpt-5.6-luna/medium when no -m is passed"),
    TierRow("2026-09-22T10:03:00Z", None, "codex", "premium", "gpt-6-astra", "xhigh", "79f4f4d5 PREMIUM_MODELS.codex"),
    TierRow("2026-09-22T10:03:00Z", None, "claude", "premium", "claude-fable-5-1", "high", "79f4f4d5 PREMIUM_MODELS.claude"),
    TierRow("2026-09-22T17:22:00Z", None, "claude", "standard", "claude-opus-5-5", "medium",
            "Claude Code 2.1.280 default; standard passes no --model"),
    TierRow("2026-09-22T18:26:00Z", 7, "codex", "standard", "gpt-6-luna", "medium", "#7 config inference.standard.codex"),
    TierRow("2026-09-23T19:56:00Z", 7, "codex", "economy", "gpt-6-luna", "medium", "#7 config inference.economy.codex"),
    TierRow("2026-09-23T19:58:00Z", None, "codex", "economy", "gpt-6-luna", "high",
            "61d04d62 ECONOMY_MODELS.codex terra/low -> luna/high (#7's own override still wins)"),
)


def _epoch(at: str | float | None) -> float | None:
    if at is None or isinstance(at, bool):
        return None
    if isinstance(at, (int, float)):
        return float(at)
    if isinstance(at, str) and at:
        try:
            parsed = datetime.fromisoformat(at.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None


def _applies(row: TierRow, runtime: str, seat: int | None) -> bool:
    return (row.runtime is None or row.runtime == runtime) and (row.seat is None or row.seat == seat)


def resolved_table(runtime: str, at: float | None, *, seat: int | None = None) -> dict[str, tuple[str, str]]:
    """``{tier: (model, effort)}`` in force at epoch *at* (``None`` = the newest state) for *runtime* on *seat*.

    Seat-less rows are applied in date order, then the seat's own rows on top (config beats constants).
    """
    generic: dict[str, tuple[str, str]] = {}
    specific: dict[str, tuple[str, str]] = {}
    for row in TIER_HISTORY:
        if not _applies(row, runtime, seat):
            continue
        since = _epoch(row.since_utc)
        if at is not None and since is not None and since > at:
            continue
        (specific if row.seat is not None else generic)[row.tier] = (row.model, row.effort)
    return {**generic, **specific}


def _era_start() -> float:
    return min(_epoch(row.since_utc) or 0.0 for row in TIER_HISTORY)


def _newest_row(runtime: str, seat: int | None) -> float | None:
    stamps = [_epoch(row.since_utc) for row in TIER_HISTORY if _applies(row, runtime, seat)]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


def is_premium(runtime: str | None, model: str | None, effort: str | None) -> bool:
    """``isPremiumModel``: the approved premium model and a premium effort; with no effort (a log line
    carries the model only) the model alone decides, as the daemon's own post-run check does (fill2 §1)."""
    if runtime not in PREMIUM_EFFORTS or not isinstance(model, str):
        return False
    approved = BUNDLE_CONSTANTS[CURRENT_BUNDLE]["premium"].get(runtime)
    if approved is None or model != approved[0]:
        return False
    return effort is None or effort in PREMIUM_EFFORTS[runtime]


def tier_for(runtime: str | None, model: str | None, effort: str | None, at: str | float | None, *,
             seat: int | None = None, inference: dict | None = None) -> str | None:
    """The derived tier of one run, without the ``~`` mark (``tier_label`` adds it).

    ``inference`` (the broker projection) beats ``TIER_HISTORY`` for runs at/after the newest
    applicable row; a pair two tiers share -> ``"economy/standard"``; a bare model (``running codex``)
    -> ``"standard"``; before the tier era (2026-09-21 19:00Z) with no projection -> ``None``;
    ``effort=None`` matches on the model alone.
    """
    if runtime not in ("codex", "claude"):
        return None
    epoch = _epoch(at)
    if epoch is not None and epoch < _era_start() and inference is None:
        return None
    if model is None:
        return "standard"
    table = resolved_table(runtime, epoch, seat=seat)
    newest = _newest_row(runtime, seat)
    if isinstance(inference, dict) and (epoch is None or newest is None or epoch >= newest):
        for tier in TIERS:
            block = inference.get(tier)
            choice = block.get(runtime) if isinstance(block, dict) else None
            if isinstance(choice, dict) and isinstance(choice.get("model"), str):
                table[tier] = (choice["model"], choice.get("effort") if isinstance(choice.get("effort"), str) else "")
    matches = [tier for tier in TIERS if tier in table and table[tier][0] == model
               and (effort is None or table[tier][1] == effort)]
    if not matches:
        # isPremiumModel also accepts the approved model at max/ultra (codex) or xhigh/max (claude) -- once premium exists
        return "premium" if "premium" in table and is_premium(runtime, model, effort) else None
    return "/".join(matches)


def tier_label(tier: str | None) -> str:
    """``~economy/standard`` -- every derived tier carries the mark; ``--`` when unknown."""
    return f"{TIER_MARK}{tier}" if isinstance(tier, str) and tier else DASH


__all__ = [
    "TIERS", "PREMIUM_EFFORTS", "BUNDLE_CONSTANTS", "CURRENT_BUNDLE", "TIER_MARK", "TIER_SHARED", "DASH",
    "TierRow", "TIER_HISTORY", "resolved_table", "is_premium", "tier_for", "tier_label",
]
