"""Pure shared presentation of independent executor observations."""
from datetime import datetime, timezone

from ._fmt import fmt_imd
from ..rowfit import cell_len, pad


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _amount(source):
    amount, decimals = source.get("amount_wei"), source.get("decimals")
    if (type(amount) is not int or not 0 <= amount < 2**256
            or type(decimals) is not int or not 0 <= decimals <= 255):
        return "—"
    value = amount / 10**decimals
    shown = "<0.01" if 0 < value < .01 else fmt_imd(value)
    if len(shown) > 10:
        shown = f"{value:.2e}"
    return f"{shown} IMD"


def pipeline_lines(payload, *, label_cols=13, width=None):
    """A receipt is an observation, not a lifetime or POOL4-only total."""
    payload = _mapping(payload)
    lines = ["executor-wide"]
    for key, label in (("queue", "queued"), ("bridge", "last bridge"),
                       ("base_burn", "Base burned")):
        stage = _mapping(payload.get(key))
        if key == "queue":
            value = _amount(stage)
        else:
            event = _mapping(stage.get("event"))
            value = _amount(event) if event else (
                "none in window" if stage.get("complete") is True else "—")
            if event and stage.get("complete") is not True:
                value += " *"
                if key == "bridge":
                    label = "bridge seen"
        lines.append(f"{pad(label, label_cols)}{value}")
    if width is not None:
        groups = []
        for pair in (lines[:2], lines[2:]):
            joined = " · ".join(pair)
            groups.extend([joined] if cell_len(joined) <= width else pair)
        return groups
    return lines


def _stamp(value):
    if type(value) not in (int, float):
        return "—"
    try:
        return datetime.fromtimestamp(value, timezone.utc).strftime("%m-%d %H:%M UTC")
    except (ValueError, OverflowError, OSError):
        return "—"


def pipeline_tooltip(payload):
    payload = _mapping(payload)
    lines = ["Hook settled is allocation to the sink, not a confirmed Base burn.",
             "Flow rate measures recent hook burn allocations.",
             "Supply and its percentage use the Ethereum wrapper supply.",
             "Executor inventory and events can include multiple sources.",
             "Bridge and verified receiver burn cover separate recent windows.",
             "Only complete coverage establishes the latest verified event in that window.",
             "They are not paired, POOL4-only or lifetime totals.",
             "Base burned requires a successful Base receipt with BurnExecuted and",
             "the receiver token's matching transfer to zero."]
    for key, label in (("queue", "Queue"), ("bridge", "Bridge"), ("base_burn", "Base burn")):
        stage = _mapping(payload.get(key))
        lines.append(f"{label} observed {_stamp(stage.get('read_ts'))}")
        if key != "queue":
            lo, hi = stage.get("from_block"), stage.get("to_block")
            if type(lo) is int and type(hi) is int:
                coverage = "complete" if stage.get("complete") is True else "incomplete *"
                lines.append(f"  recent window {lo}–{hi}; {coverage}")
            event = _mapping(stage.get("event"))
            if event:
                lines.append(f"  event {_stamp(event.get('timestamp'))}")
    return "\n".join(lines)
