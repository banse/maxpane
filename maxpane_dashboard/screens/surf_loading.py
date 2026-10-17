"""Compatibility names for the shared dashboard lifecycle and loading footer."""
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.widgets.status_bar import StatusBar


class SurfStatusBar(StatusBar):
    pass


class SurfDashboardScreen(DashboardScreen):
    JOIN_STARTUP_PREFETCH = False
