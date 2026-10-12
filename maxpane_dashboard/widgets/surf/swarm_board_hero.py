"""Leaderboard rack cards over independently observed projected facts."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid

from ._swarm_seat import seat_token
from .news_hero import HeroRecord, _count, _number
from .pool4_hero import Pool4HeroCard, _amount, _face


def leaderboard_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("top", "TOP SEAT", "SEAT", "RANK --"),
        ("recorded", "RECORDED", "SEATS", "RECORDS"),
        ("rate", "ACCEPT RATE", "%", "ACCEPTED"),
        ("outcomes", "OUTCOMES", "RECORDS", "RECORDS"),
        ("workers", "WORKERS", "NOW", "CURRENT"),
        ("effort", "EFFORT", "RECEIPTS", "CONTRIBUTORS"),
    ):
        source = payload.get(key)
        source = source if isinstance(source, dict) else {}
        state = source.get("state")
        state = state if state in ("ok", "partial", "stale", "unavailable") else "unavailable"
        section = source if state != "unavailable" else {}
        fields = dict(key=key, title=title, heading=heading, footer=footer, state=state,
                      read_ts=_number(source.get("read_ts")), accent=state == "ok")
        if key == "top":
            token = seat_token(section.get("token_id"))
            accepted = _amount(seat_token(section.get("accepted")))
            rank = _count(seat_token(section.get("rank")))
            if section.get("empty") is True:
                fields.update(preview="no recorded seats", footer="NO RECORDS", accent=False)
            else:
                # The canonical identifier never passes through a compact or
                # floating-point formatter; a long ID uses the normal text face.
                fields["digits"] = str(token) if token is not None and _number(token) is not None else "--"
                fields["subtitle"] = f"{accepted} accepted"
                fields["footer"] = f"RANK {rank}"
                fields["accent"] &= fields["digits"] != "--" and accepted != "--" and rank != "--"
        elif key == "recorded":
            seats = seat_token(section.get("seats"))
            fields["digits"] = str(seats) if seats is not None and seats < 10000 else _amount(seats)
            attempts = _amount(seat_token(section.get("attempts")))
            fields["subtitle"] = f"{attempts} attempts"
            fields["accent"] &= fields["digits"] != "--" and attempts != "--"
        elif key == "rate":
            accepted, attempts = (seat_token(section.get(field)) for field in ("accepted", "attempts"))
            if accepted == 0 and attempts == 0:
                fields.update(preview="no attempts", accent=False)
            else:
                percent = _number(section.get("percent"))
                if (percent is None or percent > 100 or accepted is None or attempts is None
                        or attempts == 0 or accepted > attempts):
                    percent = None
                fields["digits"] = _face(percent, 1)
                fields["accent"] &= percent is not None
            fields["subtitle"] = f"{_amount(accepted)} / {_amount(attempts)}"
        else:
            columns = {"outcomes": ("rejected", "failed", "pending"),
                       "workers": ("live", "working", "capacity"),
                       "effort": ("receipts", "turns", "hours")}[key]
            stats = []
            for column in columns:
                value = section.get(column)
                value = _number(value) if column == "hours" else seat_token(value)
                stats.append((column, _count(value) if key == "workers" else _amount(value)))
            fields["stats"] = tuple(stats)
            fields["accent"] &= all(value != "--" for _, value in stats)
        records.append(HeroRecord(**fields))
    return tuple(records)


class SurfSwarmBoardHero(Grid):
    DEFAULT_CSS = """
    SurfSwarmBoardHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in leaderboard_records(None):
            yield Pool4HeroCard(record)

    def update_data(self, *, surf_leaderboard_hero=None, **kwargs):
        for record in leaderboard_records(surf_leaderboard_hero):
            self.query_one(f"#hero-{record.key}", Pool4HeroCard).set_record(record)
