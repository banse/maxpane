"""Pure summary builders shared by the SWARM hero and site filtering."""
from collections import Counter
from rich.cells import cell_len
from rich.text import Text
from maxpane_dashboard.widgets.fmt import DASH, fmt_int
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import UNAVAILABLE

SERVICE_NAMES = ("verifier", "publisher", "deployer")


def is_current_site(row: object) -> bool:
    return (isinstance(row, dict) and bool(row.get("ens_name"))
            and not row.get("superseded_by") and row.get("status") != "superseded")


def launch_counts(summary):
    if not isinstance(summary, dict):
        return None
    source = summary.get("by_status")
    counted = [entry for entry in (source if isinstance(source, list) else ())
               if isinstance(entry, dict) and fmt_int(entry.get("count")) != DASH]
    counts = [(strip_tags(entry.get("status")) or DASH, int(entry["count"])) for entry in counted]
    return sum(count for _, count in counts), counts


def row_counts(rows, *, sites=False):
    if not isinstance(rows, list):
        return None
    shown = [row for row in rows if isinstance(row, dict) and (not sites or is_current_site(row))]
    counts = Counter(word for row in shown if (word := strip_tags(row.get("status"))))
    return len(shown), list(counts.items())


def summary_body(summary, width):
    if summary is None:
        return Text.from_markup(UNAVAILABLE)
    total, counts = summary
    parts = []
    for word, count in sorted(counts, key=lambda item: (-item[1], item[0])):
        pair = f"{fmt_int(count)} {word}"
        if cell_len(" · ".join([*parts, pair])) <= width:
            parts.append(pair)
    body = Text(fmt_int(total), style="bold white")
    body.append("\n")
    body.append(" · ".join(parts), style="dim")
    return body
