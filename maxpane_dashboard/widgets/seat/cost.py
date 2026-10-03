"""COST: tokens, turns, buckets by (model, effort, ~tier), and the quota gauge -- never a dollar (spec §8 COST, §10).

Every task spends the operator's subscription and quota; the previous writer was
~2× off (contradictions #5) and bucketing by ``(model, effort)`` is the only way a
tier change is not misread as a cost move (cost §3). The panel says which
``turns`` definition it shows (``api definition``) and its footer restates the
definitions and the depth of what was ingested.

**No currency, unconditionally** (spec §10; proof 11). No formatter here emits a
currency glyph, and :func:`_word` strips ``$`` from every third-party string on
its way in, so a hostile model id cannot smuggle one either. There is no flag.

OUTPUT TOKENS is a separate sibling panel registered in the screen refresh contract.
"""

from __future__ import annotations

import re

from rich.text import Text

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm, parse_iso
from maxpane_dashboard.analytics.seat_tiers import tier_label
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, as_float, fmt_int, mmdd, short_model
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.seat.config import pick_form
from maxpane_dashboard.widgets.seat_words import seat_token

__all__ = ["SeatCost", "tokens_word"]

_count = seat_token
_ROW_OVERHEAD = 4 + 1 + 2
_BUCKET_ROWS = ("seat-cost-bucket-1", "seat-cost-bucket-2", "seat-cost-bucket-3")


def _word(value: object) -> str:
    """Redacted, tag-stripped, and with every ``$`` removed: this panel has no currency (spec §10)."""
    return strip_tags(redact(value)).replace("$", "") if value is not None else ""


def tokens_word(value: object) -> str:
    """``812`` · ``96 k`` · ``2.1 M`` -- the spec's lower-case k/M token forms."""
    n = as_float(value)
    if n is None or n < 0:
        return DASH
    if n < 1000:
        return fmt_int(int(n))
    if n < 1_000_000:
        return f"{n / 1000:.0f} k"
    return f"{n / 1_000_000:.1f} M"


def _seconds(value: object, decimals: int = 1) -> str:
    s = as_float(value)
    return DASH if s is None or s < 0 else f"{s:.{decimals}f}"


def _bar(percent: object, cells: int = 5) -> str:
    p = as_float(percent)
    if p is None:
        return "▯" * cells
    filled = max(0, min(cells, round(p / 100 * cells)))
    return "▮" * filled + "▯" * (cells - filled)


class SeatCost(SignalsPanelBase):
    """COST -- see the module docstring."""

    TITLE = "COST"
    LABEL_WIDTH = 10
    DIM_LABEL = True
    ROWS = (
        ("seat-cost-window", "7 d"), ("seat-cost-tokens", "tokens"), ("seat-cost-bucket-1", None), ("seat-cost-bucket-2", None),
        ("seat-cost-bucket-3", None), ("seat-cost-side", "side model"), ("seat-cost-quota", "quota"), None, ("seat-cost-footer", None),
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._facts: dict | None = None

    def update_data(
        self,
        seat_cost_window_days=None, seat_cost_tasks=None, seat_cost_excluded=None, seat_cost_turns=None, seat_cost_tokens=None,
        seat_cost_buckets=None, seat_cost_side_model=None, seat_cost_series=None, seat_cost_depth=None, seat_quota=None,
        seat_host_runtime=None, seat_sources=None, seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        self._facts = {k: v for k, v in locals().items() if k.startswith("seat_")}
        self._repaint()

    def on_resize(self, _event=None) -> None:
        if self._facts is not None:
            self._repaint()

    def _source(self, name: str) -> dict:
        sources = (self._facts or {}).get("seat_sources")
        source = sources.get(name) if isinstance(sources, dict) else None
        return source if isinstance(source, dict) else {}

    def _repaint(self) -> None:
        if self._facts is None:
            return
        f = self._facts
        width = max(self.content_region.width, 0)
        room = max(width - self.LABEL_WIDTH - _ROW_OVERHEAD, 0)
        cut = False
        sessions = self._source("sessions")
        broken = sessions.get("ok") is False
        reason = _word(sessions.get("reason")) or "unavailable"
        for row_id, label, forms, colour in self._rows():
            if broken and row_id in ("seat-cost-tokens",) + _BUCKET_ROWS:
                forms = (f"tokens unavailable (sessions: {reason})", "tokens unavailable") if row_id == "seat-cost-tokens" else ("",)
                colour = "yellow"
            value, was_cut = pick_form(forms, room if label is not None else room + self.LABEL_WIDTH + 1)
            cut = cut or was_cut
            if label is None and not value:
                self.write(f"#{row_id}", "")
                continue
            self.render_signal(f"#{row_id}", label or "", {"label": label or "", "value_str": value, "color": colour}, labelled=label is not None)
        as_of = f.get("seat_as_of_hhmm") if isinstance(f.get("seat_as_of_hhmm"), dict) else {}
        marker = as_of.get("sessions")
        days = _count(f.get("seat_cost_window_days"))
        title = self.TITLE + (f" · {days} d" if days is not None else "") + (f" · as of {rowfit.clip(marker, 5)}" if rowfit.has_marker(marker) else "")
        self.write(".panel-title", Text(rowfit.title_with_hint(title, cut, width)))

    def _rows(self):
        f = self._facts or {}
        tasks = _count(f.get("seat_cost_tasks"))
        excluded = f.get("seat_cost_excluded") if isinstance(f.get("seat_cost_excluded"), dict) else {}
        ex_parts = [f"{_count(excluded.get(k))} {k}" for k in ("doctor", "manual") if _count(excluded.get(k))]
        ex_word = f" · excluded {' '.join(ex_parts)}" if ex_parts else ""
        ex_total = sum(_count(excluded.get(k)) or 0 for k in ("doctor", "manual"))
        turns = _count(f.get("seat_cost_turns"))
        tasks_word = str(tasks) if tasks is not None else DASH
        turns_word = str(turns) if turns is not None else DASH
        window_forms = (f"tasks {tasks_word}{ex_word} · turns {turns_word} (api definition)", f"tasks {tasks_word} · excl {ex_total} · turns {turns_word}", f"tasks {tasks_word}")
        tokens = f.get("seat_cost_tokens") if isinstance(f.get("seat_cost_tokens"), dict) else None
        if tokens is None:
            tokens_forms, tokens_colour = ("unavailable",), "yellow"
        else:
            tokens_forms, tokens_colour = (f"in {tokens_word(tokens.get('input'))} · out {tokens_word(tokens.get('output'))} · cached {tokens_word(tokens.get('cached'))}",
                                           f"out {tokens_word(tokens.get('output'))} · cached {tokens_word(tokens.get('cached'))}", f"out {tokens_word(tokens.get('output'))}"), "dim"
        buckets = f.get("seat_cost_buckets") if isinstance(f.get("seat_cost_buckets"), list) else []
        bucket_rows = []
        for index, row_id in enumerate(_BUCKET_ROWS):
            bucket = buckets[index] if index < len(buckets) and isinstance(buckets[index], dict) else None
            if bucket is None:
                bucket_rows.append((row_id, None, ("",), "dim"))
                continue
            head = f"{short_model(_word(bucket.get('model'))) or DASH}/{_word(bucket.get('effort')) or DASH} {tier_label(bucket.get('tierDerived') if isinstance(bucket.get('tierDerived'), str) else None)}"
            head = head.replace("$", "")
            bt = bucket.get("tokens") if isinstance(bucket.get("tokens"), dict) else {}
            n_tasks = _count(bucket.get("tasks"))
            p50 = _count(bucket.get("turnsP50"))
            wall = f"{_seconds(bucket.get('wallP50S'))}/{_seconds(bucket.get('wallP90S'))} s"
            ttft = as_float(bucket.get("ttftP50Ms"))
            ttft_word = f" · TTFT {ttft / 1000:.1f} s" if ttft is not None else ""
            ctx = tokens_word(bucket.get("turn1ContextP50"))
            hits, auth = _count(bucket.get("maxTurnsHits")), _count(bucket.get("authErrors"))
            full = (f"{head} · {n_tasks if n_tasks is not None else DASH} tasks · p50 {p50 if p50 is not None else DASH} turns · out {tokens_word(bt.get('output'))} · cached {tokens_word(bt.get('cached'))}"
                    f" · in {tokens_word(bt.get('input'))} · wall {wall}{ttft_word} · ctx {ctx} · max-turn {hits if hits is not None else DASH} · auth {auth if auth is not None else DASH}")
            mid = f"{head} · {n_tasks if n_tasks is not None else DASH} tasks · out {tokens_word(bt.get('output'))} · wall {wall} · auth {auth if auth is not None else DASH}"
            short = f"{head} · {n_tasks if n_tasks is not None else DASH} · out {tokens_word(bt.get('output'))}"
            bucket_rows.append((row_id, None, (full, mid, short), "yellow" if auth else "dim"))
        runtime = _word(f.get("seat_host_runtime"))
        side = f.get("seat_cost_side_model") if isinstance(f.get("seat_cost_side_model"), dict) else None
        if side:
            # ``_word`` strips ``$`` and redacts; the trailing 8-digit date (``claude-haiku-4-5-20251001``) is dropped
            # first because ``short_model`` only shortens a whole ``claude-<family>-<major>[-<minor>]`` id.
            raw = re.sub(r"-\d{8}$", "", _word(side.get("model")))
            model = short_model(raw) or DASH
            side_forms = (f"{model}: {tokens_word(side.get('input'))} in / {tokens_word(side.get('output'))} out (SDK, not in api usage)",
                          f"{model}: {tokens_word(side.get('input'))} in / {tokens_word(side.get('output'))} out", model)
        elif runtime == "claude":
            side_forms = ("none seen",)
        else:
            side_forms = (f"n/a ({runtime})" if runtime else "n/a",)
        quota = f.get("seat_quota") if isinstance(f.get("seat_quota"), dict) else None
        if quota is None:
            quota_forms, quota_colour = ("unavailable",), "yellow"
        elif quota.get("usedPercent") is None:
            provider = _word(quota.get("provider")) or runtime or "quota"
            quota_forms, quota_colour = (f"{provider} quota: {_word(quota.get('reason')) or 'not observable locally'}", f"{provider}: n/a"), "dim"
        else:
            pct = as_float(quota.get("usedPercent"))
            resets = parse_iso(quota.get("resetsAtUtc"))
            resets_word = f"{mmdd(resets)} {as_of_hhmm(quota.get('resetsAtUtc')) or DASH}" if resets is not None else DASH
            sampled = as_of_hhmm(quota.get("sampledAtUtc")) or DASH
            window = _word(quota.get("window")) or "window"
            provider = _word(quota.get("provider")) or runtime or "quota"
            quota_forms = (f"{provider} {window} {pct:.0f} % {_bar(pct)} · resets {resets_word} · sampled {sampled}",
                           f"{provider} {window} {pct:.0f} % {_bar(pct)}", f"{pct:.0f} % {_bar(pct)}")
            quota_colour = "yellow" if pct >= 80 else "dim"
        depth = f.get("seat_cost_depth") if isinstance(f.get("seat_cost_depth"), dict) else {}
        since = parse_iso(depth.get("sessionsFromUtc"))
        since_word = mmdd(since) if since is not None else DASH
        expired = _count(depth.get("expiredRows"))
        skipped = depth.get("skipped") if isinstance(depth.get("skipped"), dict) else {}
        oversize = _count(skipped.get("oversize"))
        footer_forms = (
            f"sessions from {since_word} · {expired if expired is not None else DASH} rows expired · {oversize if oversize is not None else DASH} oversize skipped"
            " · tokens, not currency · definitions: turns = agent messages · input = uncached · output incl. reasoning",
            f"sessions from {since_word} · {expired if expired is not None else DASH} expired · {oversize if oversize is not None else DASH} oversize · tokens, not currency",
            "tokens, not currency",
        )
        return (
            ("seat-cost-window", "7 d", window_forms, "dim"),
            ("seat-cost-tokens", "tokens", tokens_forms, tokens_colour),
            *bucket_rows,
            ("seat-cost-side", "side model", side_forms, "dim"),
            ("seat-cost-quota", "quota", quota_forms, quota_colour),
            ("seat-cost-footer", None, footer_forms, "dim"),
        )
