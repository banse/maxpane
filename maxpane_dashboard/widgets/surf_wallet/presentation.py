"""Literal, source-bound wallet facts and the shared rack visual vocabulary."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from rich.text import Text

from maxpane_dashboard.analytics.surf_wallet import usage_source, usage_signal, usage_text
from maxpane_dashboard.widgets.address import address_prose, address_text, hash_text, job_text
from maxpane_dashboard.widgets.explorer import IMD, is_tx_hash
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.sparkline_common import build_sparkline
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord
from maxpane_dashboard.widgets.surf_nft.detail import source_text
from maxpane_dashboard.widgets.surfboard.rack import meter_text
from . import EXPLORER


def number(value):
    return "--" if value is None else flatten(value)


def literal(value, style="", *, chain_id=None):
    return address_prose(flatten(value) if value is not None else "--", explorer=EXPLORER(chain_id), style=style)


def clock(value, full=False, time_only=False):
    try:
        return datetime.fromtimestamp(value, timezone.utc).strftime("%H:%M" if time_only else "%m-%d %H:%M UTC" if full else "%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return "--"


def name_text(artifact, width=None):
    name = flatten(artifact.get("name")) or "Unnamed artifact"
    if artifact.get("address"):
        return address_text(artifact["address"], label=name, width=max(1, width-2) if width else None,
                            explorer=EXPLORER(artifact.get("chain_id")))
    return literal(clip(name, width) if width else name, chain_id=artifact.get("chain_id"))


def meter(value, total, width=12, color="bright_green"):
    if value is None or total is None:
        return Text("--".ljust(width), style="dim")
    filled = min(width, max(0, round(width*value/total))) if total else 0
    prefix = len("AUX ")
    bar = meter_text({"key": "wallet", "numerator": filled, "denominator": width}, width=width+prefix).plain[prefix:]
    return Text.assemble((bar[:filled], color), (bar[filled:], "dim"))


def hero_records(metrics, view):
    counts, orders = metrics["counts"], metrics["orders"]
    actions = Counter(row.get("action") for row in orders) if orders is not None else None
    count = lambda label: number(counts.get(label))
    action = lambda label: number(actions[label] if actions is not None else None)
    totals = metrics["payment_totals"]
    group = totals[0] if totals and len(totals) == 1 else None
    paid = number(group.get("paid")) if group else "--"
    partial_paid = bool(group and paid != "--" and not group.get("paid_complete"))
    paid_bound = (">=" if partial_paid else "") + paid
    symbol = flatten(group.get("symbol")) if group else "ASSETS" if totals is not None else "PAID"
    paid_footer = f"paid {paid_bound} {symbol}" if group else f"{len(totals)} payment assets" if totals is not None else "paid --"
    specs = {
        "requests": ("REQUESTS", "ORDERS", paid_footer, count("REQUESTS"), "observed / 30D"),
        "jobs": ("JOBS", "REQUESTS", f"all: {count('IN FLIGHT')} in flight", count("JOBS"), f"{action('job.open')} new / {action('job.continue')} cont"),
        "workflows": ("WORKFLOWS", "REQUESTS", f"{count('SITES')} sites / {number(metrics['linked_sites'])} linked", count("WORKFLOWS"), f"{number(metrics['outcomes']['shipped'])} shipped"),
        "launches": ("LAUNCHES", "REQUESTS", f"{count('CONTRACTS')} ctr / {count('TOKENS')} tokens", count("LAUNCHES"), f"{number(metrics['outcomes']['deployed'])} deployed"),
        "oracles": ("ORACLES", "REQUESTS", f"all: {count('ATTENTION')} follow-ups", count("ORACLES"), f"{number(metrics['outcomes']['attested'])} attested"),
        "schedules": ("SCHEDULES", "REQUESTS", f"{action('schedule.create')} new / {action('schedule.topup')} topups", count("SCHEDULES"), "not run count"),
        "sites": ("SITES", "PROJECTS", "ALL KNOWN", count("SITES"), f"{number(metrics['linked_sites'])} linked"),
        "contracts": ("CONTRACTS", "DEPLOYED", f"{number(metrics['rules'])} usage rules", count("CONTRACTS"), f"incl. {count('TOKENS')} tokens"),
        "tokens": ("TOKENS", "DEPLOYED", "ALL KNOWN", count("TOKENS"), "in contracts"),
        "paid": ("PAID", symbol, f"{number(metrics['settled'])} settled", paid if group else str(len(totals)) if totals is not None else "--",
                 "at least" if partial_paid else f"refund {number(group.get('refunded'))}" if group else "payment groups" if totals is not None else ""),
        "attention": ("ATTENTION", "REQUESTS", "follow-ups / 30D", count("ATTENTION"), f"{count('IN FLIGHT')} in flight"),
    }
    keys = ("requests", "jobs", "workflows", "launches", "oracles", "schedules") if view == "overview" else ("requests", "sites", "contracts", "tokens", "paid", "attention")
    return [HeroRecord(f"wallet-{view}-{key}", title, heading, footer, digits=digits,
                       subtitle=subtitle, read_ts=metrics["as_of"])
            for key in keys for title, heading, footer, digits, subtitle in (specs[key],)]


def insights(metrics):
    counts, daily = metrics["counts"], metrics["daily"]
    total = counts.get("REQUESTS")
    activity = Text(f"{number(total)} observed requests\n", style="bold")
    known = [value for value in daily or [] if value is not None]
    if known:
        glyphs = iter(build_sparkline(known, width=len(known), pad=False))
        activity.append("".join(next(glyphs) if value is not None else "·" for value in daily), style="bright_green")
    else:
        activity.append("--", style="dim")
    activity.append(f"\n30 daily bins · UTC\nPeak {max(known) if known else '--'}/day · latest {number(daily[-1]) if daily else '--'}\n")
    activity.append("Each bar = 24 hours\n· = unobserved history", style="dim")
    states = Text()
    for label in ("Completed", "In flight", "Attention", "Not admitted", "Unknown"):
        value = (metrics["states"] or {}).get(label)
        states.append(f"{label:13}")
        states.append(meter(value, total, color="yellow" if label == "Attention" else "bright_green"))
        states.append(f" {number(value)}\n")
    states.append("Mutually exclusive / 30D", style="dim")
    onchain = Text()
    contracts = counts.get("CONTRACTS")
    for label in ("Active", "Quiet", "Unknown"):
        value = (metrics["signals"] or {}).get(label)
        onchain.append(f"{label:9}")
        onchain.append(meter(value, contracts, color="dim" if label == "Unknown" else "bright_green"))
        onchain.append(f" {number(value)}\n")
    onchain.append(f"{number(contracts)} contracts incl. {number(counts.get('TOKENS'))} tokens\n", style="dim")
    for label, value, denominator in (("rules", metrics["rules"], contracts), ("complete", metrics["complete"], metrics["rules"])):
        onchain.append(f"{number(value)}/{number(denominator)} {label:8} ")
        onchain.append(meter(value, denominator))
        if label == "rules":
            onchain.append("\n")
    return {"activity": activity, "states": states, "onchain": onchain, "payments": payments(metrics)}


def payments(metrics):
    out = Text()
    groups = metrics["payment_totals"]
    if groups:
        for index, group in enumerate(groups):
            if index:
                out.append("\n")
            chain = {1: "ETH", 8453: "BASE", 4663: "RH"}.get(group.get("chain_id"), "Unknown chain")
            out.append(f"{chain} · ")
            asset, symbol = group.get("asset"), flatten(group.get("symbol")) or "asset"
            out.append(address_text(asset, label=symbol, width=15, explorer=EXPLORER(group.get("chain_id"))) if asset else literal(symbol))
            for label, key in (("Paid", "paid"), ("Refunded", "refunded")):
                value = number(group.get(key))
                if value != "--" and not group.get("paid_complete" if key == "paid" else "refund_complete"):
                    value = ">=" + value
                out.append(f"\n{label:10} {value}")
            try:
                net = str(Decimal(group["paid"])-Decimal(group["refunded"])) if group.get("paid_complete") and group.get("refund_complete") else "--"
            except (InvalidOperation, TypeError, KeyError):
                net = "--"
            out.append(f"\nNet paid   {net}\n", style="bold")
    else:
        out.append("No observed payments\n" if groups == [] else "Paid       --\nRefunded   --\nNet paid   --\n")
    out.append(meter(metrics["settled"], metrics["counts"].get("REQUESTS"), width=28))
    out.append(f"\n{number(metrics['settled'])} settled / {number(metrics['unsettled'])} unsettled")
    return out


def artifact_detail(artifact, by_id, snapshot):
    links, out, path = [], Text(), Text()
    if artifact is None:
        return Text("Select a created artifact"), Text("--"), links
    explorer = EXPLORER(artifact.get("chain_id"))
    source = usage_source(artifact, by_id)
    usage = (source or {}).get("usage")
    signal = usage_signal(artifact, by_id)

    def line(label, value=None):
        if label:
            out.append(label+"  ", style="dim")
        out.append(value if isinstance(value, Text) else literal(value, chain_id=artifact.get("chain_id")))
        out.append("\n")

    def link(label, url):
        return source_text(label, url, links, explorer=explorer, action="screen.open_wallet_source")

    def evidence(items):
        for item in items if isinstance(items, list) else [items] if items else []:
            if isinstance(item, dict):
                line("↗", link(item.get("label") or "Evidence", item.get("url")))
                if item.get("tx_hash"):
                    line("Tx", hash_text(item["tx_hash"], width=48, explorer=explorer))
                for label, key in (("Block", "block_number"), ("Proof", "linkage"), ("", "detail")):
                    if item.get(key) is not None:
                        line(label, item[key])
            else:
                line("", link("Rule source" if str(item).startswith("https://") else item, item))

    line("", name_text(artifact))
    line("", f"{artifact.get('kind')} / {artifact.get('chain') or '--'} · {signal}")
    out.append("\n")
    for label, key in (("Order", "order_id"), ("Project", "project"), ("Version", "version")):
        line(label, artifact.get(key))
    if artifact.get("job_id"):
        line("Job", job_text(artifact["job_id"], width=36, explorer=IMD))
    if artifact.get("address"):
        line("Address", address_text(artifact["address"], explorer=explorer))
    if artifact.get("kind") == "SITE":
        line("Site", link(artifact.get("site_url") or "--", artifact.get("site_url")))
        line("Linked", name_text(source) if source else "--")
    out.append("\nONCHAIN USE / 24H\n", style="bold")
    line("", usage_text(artifact, by_id))
    if usage:
        line("Rule", usage.get("rule"))
        line("Window", "complete" if usage.get("complete") else "partial / lower bound only")
        line("Observed", clock(usage.get("observed_at"), full=True))
        line("Blocks", f"{number(usage.get('from_block'))}..{number(usage.get('to_block'))}")
        latest = usage.get("latest")
        line("Latest", hash_text(latest, width=45, explorer=EXPLORER((source or artifact).get("chain_id")))
             if is_tx_hash(latest) else clock(latest, full=True))
        if usage.get("through_timestamp") is not None:
            line("Through", clock(usage["through_timestamp"], full=True))
        if usage.get("first_seen"):
            line("Tracking", clock(usage.get("tracking_since"), full=True))
            line("", "First observed; not first-ever use.")
    else:
        line("", "No onchain link observed." if signal == "NO ONCHAIN LINK" else "No verified usage observation.")
        line("", "Unknown is not zero activity.")
    if artifact.get("kind") == "SITE" and source:
        line("", "Linked contract evidence; frontend origin not proven.")
    out.append("\nEVIDENCE\n", style="bold")
    evidence(artifact.get("evidence"))
    evidence(artifact.get("deployment"))
    if usage:
        evidence(usage.get("evidence"))
    out.append("\nCOVERAGE\n", style="bold")
    for detail in snapshot.get("coverage") or ["--"]:
        line("", detail)
    path.append(name_text(artifact, width=41))
    path.append(f" / {flatten(artifact.get('kind'))}\n")
    path.append("├─ order " + clip(flatten(artifact.get("order_id")) or "--", 30)+"\n", style="dim")
    path.append("└─ ")
    path.append(name_text(source, width=38) if source else Text("no linked contract" if artifact.get("binding_checked") else "link not verified"))
    path.append("\n   └─ " + clip(flatten(usage_text(artifact, by_id)).split(" / ")[0], 35)+"\n")
    path.append(signal+"\n", style="bright_green" if "ACTIVE" in signal else "dim")
    path.append("frontend origin not proven" if artifact.get("kind") == "SITE" and source else "Enter: rule, coverage and evidence", style="dim")
    return out, path, links
