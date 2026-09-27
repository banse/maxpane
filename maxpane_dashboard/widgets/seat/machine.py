"""MACHINE: is it me, the box or the swarm -- unit/cgroup, host + retention, plane (spec §8 MACHINE).

Three groups on one ``SignalsPanelBase``: the unit's memory, cpu quota and stop
semantics (``graceful stop possible`` is what ``--force`` hangs on, spec §11);
the host's load, memory and disk, the never-pruned ``work/`` tree, the journal
horizon and its cap (surfaced, never fixed -- spec §5.1), the transcript
retention (``rollouts plain 7 d then .zst``; ``30-day window``), and the orphans
the broker found outside the unit cgroup (the 35 h stuck probe, vps §6.1); the
plane's verifier and the undocumented ``awaitingVerdict``. Degraded per group
by source (``unit``, ``workstat``, ``plane``), so a Docker inspect timeout leaves
the ``work/`` line standing. Sizes are facts, never alarms (fill8 CONSTRAINTS).
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm, parse_iso
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, as_float, fmt_int, mmdd
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.seat.config import pick_form
from maxpane_dashboard.widgets.seat_words import seat_token
from maxpane_dashboard.widgets.seat.hero import _word, _mib, _gib, _clock as _hhmm

__all__ = ["SeatMachine"]

_count = seat_token
_ROW_OVERHEAD = 4 + 1 + 2








def _mb(value: object) -> str:
    b = as_float(value)
    return DASH if b is None or b < 0 else (f"{b / 1e6:.1f} MB" if b < 10e6 else f"{b / 1e6:.0f} MB")


def _dur(seconds: object) -> str:
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    minutes, _sec = divmod(int(s), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes:02d} m"
    return f"{minutes} m"




class SeatMachine(SignalsPanelBase):
    """MACHINE -- see the module docstring."""

    TITLE = "MACHINE"
    LABEL_WIDTH = 10
    DIM_LABEL = True
    ROWS = (
        ("seat-mach-memory", "memory"), ("seat-mach-cpu", "cpu"), ("seat-mach-stop", "stop"), None,
        ("seat-mach-host", "host"), ("seat-mach-work", "work/"), ("seat-mach-journal", "journal"), ("seat-mach-transcripts", "transcripts"),
        ("seat-mach-orphans", "orphans"), None, ("seat-mach-plane", "plane"),
    )
    _ROW_SOURCE = {
        "seat-mach-memory": "unit", "seat-mach-cpu": "unit", "seat-mach-stop": "unit", "seat-mach-host": "unit",
        "seat-mach-work": "workstat", "seat-mach-journal": "unit", "seat-mach-transcripts": "unit", "seat-mach-orphans": "workstat",
        "seat-mach-plane": "plane",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._facts: dict | None = None

    def update_data(
        self,
        seat_unit_memory_current_b=None, seat_unit_memory_peak_b=None, seat_unit_memory_max_b=None, seat_unit_cpu_quota=None,
        seat_unit_tasks_current=None, seat_unit_stop_timeout_s=None, seat_unit_kill_mode=None, seat_unit_graceful_stop_possible=None,
        seat_machine_load1=None, seat_machine_mem_avail_mib=None, seat_machine_disk_free_gib=None,
        seat_machine_work_dirs=None, seat_machine_work_bytes=None, seat_machine_abnormal_lease_dirs=None, seat_machine_outbox_files=None,
        seat_machine_journal=None, seat_machine_transcript_retention=None, seat_machine_orphans=None,
        seat_plane_verifier_up=None, seat_plane_verifier_last_seen_utc=None, seat_plane_awaiting_verdict=None,
        seat_plane_connected_daemons=None, seat_daemon_fleet_online=None, seat_daemon_fleet_enrolled=None,
        seat_sources=None, seat_as_of_hhmm=None, seat_host_kind=None,
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
        room = max(self.content_region.width - self.LABEL_WIDTH - _ROW_OVERHEAD, 0)
        cut = False
        for row_id, label, forms, colour in self._rows():
            name = self._ROW_SOURCE[row_id]
            source = self._source(name)
            if source.get("ok") is False and (name != "plane" or source.get("unavailable") is True):
                reason = _word(source.get("reason")) or "unavailable"
                forms = (f"plane: unavailable ({reason})", "plane: unavailable") if name == "plane" else (f"unavailable ({name}: {reason})", "unavailable")
                colour = "yellow"
            value, was_cut = pick_form(forms, room)
            cut = cut or was_cut
            self.render_signal(f"#{row_id}", label, {"label": label, "value_str": value, "color": colour})
        as_of = f.get("seat_as_of_hhmm") if isinstance(f.get("seat_as_of_hhmm"), dict) else {}
        marker = as_of.get("unit")
        title = self.TITLE + (f" · as of {rowfit.clip(marker, 5)}" if rowfit.has_marker(marker) else "")
        self.write(".panel-title", Text(rowfit.title_with_hint(title, cut, max(self.content_region.width, 0))))

    def _rows(self):
        f = self._facts or {}
        docker = f.get("seat_host_kind") == "docker"
        mem, peak, mx = _mib(f.get("seat_unit_memory_current_b")), _mib(f.get("seat_unit_memory_peak_b")), _gib(f.get("seat_unit_memory_max_b"))
        quota = _word(f.get("seat_unit_cpu_quota")) or DASH
        tasks = _count(f.get("seat_unit_tasks_current"))
        stop_s = as_float(f.get("seat_unit_stop_timeout_s"))
        stop_word = f"{stop_s:.0f} s" if stop_s is not None else DASH
        kill = _word(f.get("seat_unit_kill_mode")) or DASH
        graceful = f.get("seat_unit_graceful_stop_possible")
        if graceful is True:
            stop_forms, stop_colour = (f"timeout {stop_word} · kill {kill} → graceful stop possible", f"{stop_word} · {kill} → graceful", "graceful ✓"), "green"
        elif graceful is False and docker:
            stop_forms, stop_colour = (f"stop-timeout {stop_word} · no init → mid-task stop is ungraceful", f"{stop_word} · no init → ungraceful", "ungraceful"), "yellow"
        elif graceful is False:
            stop_forms, stop_colour = (f"timeout {stop_word} · kill {kill} → ungraceful", f"{stop_word} → ungraceful", "ungraceful"), "yellow"
        else:
            stop_forms, stop_colour = ("unavailable",), "yellow"
        load = as_float(f.get("seat_machine_load1"))
        avail = as_float(f.get("seat_machine_mem_avail_mib"))
        disk = as_float(f.get("seat_machine_disk_free_gib"))
        load_word = f"{load:.2f}" if load is not None else DASH
        avail_word = f"{avail / 1024:.1f} G" if avail is not None else DASH
        disk_word = f"{disk:.0f} G" if disk is not None else DASH
        dirs, abnormal, outbox = _count(f.get("seat_machine_work_dirs")), _count(f.get("seat_machine_abnormal_lease_dirs")), _count(f.get("seat_machine_outbox_files"))
        work_forms = (
            f"{fmt_int(dirs) if dirs is not None else DASH} dirs · {_mb(f.get('seat_machine_work_bytes'))} · {abnormal if abnormal is not None else DASH} abnormal-lease dirs · outbox {outbox if outbox is not None else DASH}",
            f"{fmt_int(dirs) if dirs is not None else DASH} dirs · {_mb(f.get('seat_machine_work_bytes'))} · outbox {outbox if outbox is not None else DASH}",
            f"outbox {outbox if outbox is not None else DASH}",
        )
        journal = f.get("seat_machine_journal") if isinstance(f.get("seat_machine_journal"), dict) else None
        if journal is None:
            journal_forms = ("unavailable",)
        elif "driver" in journal:
            rotation = _word(journal.get("rotation")) or DASH
            journal_forms = (f"{_word(journal.get('driver')) or DASH} {_mb(journal.get('bytes'))} · {'no rotation' if rotation == 'none' else rotation} · dies with {_word(journal.get('diesWith')) or DASH}",
                             f"{_word(journal.get('driver')) or DASH} {_mb(journal.get('bytes'))} · no rotation", _mb(journal.get("bytes")))
        else:
            first = parse_iso(journal.get("firstUtc"))
            first_word = f"{mmdd(first)} {_hhmm(journal.get('firstUtc'))}" if first is not None else DASH
            cap = _word(journal.get("capNote"))
            journal_forms = (f"{first_word} → now · cap {cap}" if cap else f"{first_word} → now", f"{first_word} → now · cap {cap.split(' resolved')[0]}" if cap else f"{first_word} → now", f"since {first_word}")
        ret = f.get("seat_machine_transcript_retention") if isinstance(f.get("seat_machine_transcript_retention"), dict) else None
        if ret is None:
            tr_forms, tr_colour = ("unavailable",), "yellow"
        elif ret.get("kind") == "codex-rollouts":
            plain = _count(ret.get("plainDays"))
            plain_word = str(plain) if plain is not None else "7"
            if ret.get("zstdReadable") is False:
                tr_forms, tr_colour = (f"rollouts > {plain_word} d unreadable (compression.zstd missing)", ".zst unreadable"), "yellow"
            else:
                tr_forms, tr_colour = (f"rollouts plain {plain_word} d then .zst (readable ✓)", f"plain {plain_word} d then .zst"), "dim"
        else:
            days = _count(ret.get("deleteDays"))
            tr_forms, tr_colour = (f"transcripts {days if days is not None else 30}-day window", f"{days if days is not None else 30} d"), "dim"
        orphans = f.get("seat_machine_orphans") if isinstance(f.get("seat_machine_orphans"), list) else None
        if orphans is None:
            orphan_forms, orphan_colour = ("unavailable",), "yellow"
        elif not orphans:
            orphan_forms, orphan_colour = ("none",), "dim"
        else:
            first_orphan = next((o for o in orphans if isinstance(o, dict)), {})
            cmd = " ".join(_word(first_orphan.get("cmd")).split()[:2]) or DASH
            members = first_orphan.get("pgidMembers") if isinstance(first_orphan.get("pgidMembers"), list) else []
            roots = sum(1 for m in members if isinstance(m, dict) and m.get("uid") == 0)
            shared = f", pgid shared with {roots} root pids" if roots else ""
            orphan_forms = (f"{len(orphans)} ({cmd}, {_dur(first_orphan.get('ageS'))}, {_mb(first_orphan.get('rssB'))}{shared}) → kill-orphans",
                            f"{len(orphans)} ({cmd}, {_dur(first_orphan.get('ageS'))}) → kill-orphans", f"{len(orphans)} → kill-orphans")
            orphan_colour = "yellow"
        up = f.get("seat_plane_verifier_up")
        verifier = "verifier up" if up is True else ("verifier down" if up is False else f"verifier {DASH}")
        seen = _hhmm(f.get("seat_plane_verifier_last_seen_utc"))
        awaiting = _count(f.get("seat_plane_awaiting_verdict"))
        daemons = _count(f.get("seat_plane_connected_daemons"))
        online, enrolled = _count(f.get("seat_daemon_fleet_online")), _count(f.get("seat_daemon_fleet_enrolled"))
        beat = f" (heartbeat: {online} online, {enrolled} enrolled)" if online is not None and enrolled is not None else ""
        plane_forms = (
            f"{verifier} · last seen {seen} · awaiting verdict {awaiting if awaiting is not None else DASH} (undocumented) · {daemons if daemons is not None else DASH} daemons{beat}",
            f"{verifier} · awaiting {awaiting if awaiting is not None else DASH} · {daemons if daemons is not None else DASH} daemons",
            verifier,
        )
        return (
            ("seat-mach-memory", "memory", (f"{mem} · peak {peak} · max {mx}", f"{mem} · peak {peak}", mem), "dim"),
            ("seat-mach-cpu", "cpu", (f"quota {quota} · tasks {tasks if tasks is not None else DASH}", f"quota {quota}"), "dim"),
            ("seat-mach-stop", "stop", stop_forms, stop_colour),
            ("seat-mach-host", "host", (f"load {load_word} · mem avail {avail_word} · disk free {disk_word}", f"load {load_word} · free {disk_word}", f"load {load_word}"), "dim"),
            ("seat-mach-work", "work/", work_forms, "dim"),
            ("seat-mach-journal", "journal", journal_forms, "dim"),
            ("seat-mach-transcripts", "transcripts", tr_forms, tr_colour),
            ("seat-mach-orphans", "orphans", orphan_forms, orphan_colour),
            ("seat-mach-plane", "plane", plane_forms, "red" if up is False else "dim"),
        )
