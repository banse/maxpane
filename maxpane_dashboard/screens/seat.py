"""PEPEPANE screen geometry; completed with the dashboard in Task 8.10."""
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen


class SeatScreen(DashboardScreen):
    DEFAULT_CSS = '\n    SeatHero {\n        height: 7;\n        padding: 0 1 0 0;\n    }\n    SeatHero > SeatHeroBox {\n        width: 1fr;\n        height: 7;\n        padding: 0 1;\n        margin: 0 1;\n        border: solid $panel;\n        background: $surface;\n        content-align: center top;\n        text-align: center;\n        text-wrap: nowrap;\n        text-overflow: ellipsis;\n    }\n    SeatHero.seat-hero-green > #seat-hero-live { border: solid $success; }\n    SeatHero.seat-hero-amber > #seat-hero-live { border: solid $warning; }\n    SeatHero.seat-hero-red > #seat-hero-live { border: solid $error; }\n    \n    SeatNow > .panel-line {\n        text-wrap: nowrap;\n        text-overflow: ellipsis;\n    }\n    '
