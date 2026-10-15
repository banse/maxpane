"""Session-local delivery of the existing production launch detector's events."""
from __future__ import annotations

from math import isfinite
from time import time
from uuid import UUID

from textual.message import Message

from maxpane_dashboard.analytics.surf_launch_checks import is_production
from maxpane_dashboard.widgets.explorer import is_address
from maxpane_dashboard.widgets.markup_safety import flatten, safe_markup
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.surf._swarm_chain import chain_word


class SurfLaunchesUpdated(Message):
    def __init__(self, screen, data: dict) -> None:
        super().__init__()
        self.screen = screen
        self.data = data


class LaunchNotifications:
    def __init__(self, *, clock=time) -> None:
        self._clock = clock
        self._started_at = clock()
        self._baseline_at: float | None = None
        self._launches: set[str] = set()
        self._tokens: set[tuple[int, str]] = set()

    def consume(self, data: dict) -> list[dict]:
        events = data.get("swarm_launch_fired")
        if data.get("sig_swarm_state") not in ("ok", "watch", "fired") or not isinstance(events, list):
            return []
        now = self._clock()
        read_ts = data.get("swarm_launch_read_ts")
        if (type(read_ts) not in (int, float) or not isfinite(read_ts)
                or not self._started_at <= read_ts <= now):
            return []
        initial = self._baseline_at is None
        if initial:
            self._baseline_at = now
        candidates = []
        for event in events:
            if not isinstance(event, dict):
                continue
            key, ts = event.get("launch_id"), event.get("ts")
            try:
                if not isinstance(key, str) or str(UUID(key)) != key:
                    continue
            except ValueError:
                continue
            if (type(ts) not in (int, float) or not isfinite(ts) or not 0 <= ts <= now
                    or type(event.get("number")) is not int or event["number"] < 0
                    or not is_production({"chainId": event.get("chain_id")})):
                continue
            address = event.get("token_address")
            token = (event["chain_id"], address.lower()) if is_address(address) else None
            candidates.append((event, key, ts, token))
        # Newest-first snapshots may put an alias before the enriched known UUID.
        self._tokens.update(token for _, key, _, token in candidates
                            if key in self._launches and token is not None)
        new = []
        for event, key, ts, token in candidates:
            seen = key in self._launches or (token is not None and token in self._tokens)
            self._launches.add(key)
            # Enrichment must teach aliases even when the UUID was already seen.
            if token is not None:
                self._tokens.add(token)
            if not initial and not seen and ts > self._baseline_at:
                new.append(event)
        return new


def launch_toast_message(event: dict) -> str:
    ticker = safe_markup(clip(flatten(event.get("ticker")), 24))
    label = f"${ticker}" if ticker else "Unknown token"
    return f"{label} · {chain_word(event['chain_id'])}\nLaunch #{event['number']}"
