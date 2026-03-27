"""Dashboard templates — copy and adapt for new game dashboards.

Based on the Bakery dashboard layout which has the best alignment.

Templates:
    screen_template.py          — Screen with polling, compose layout, refresh wiring
    hero_metrics_template.py    — 3 hero metric cards (equal width, bordered, centered)
    leaderboard_template.py     — DataTable with sortable columns
    sparkline_template.py       — Sparkline chart using block characters
    activity_feed_template.py   — RichLog with newest-first, auto-scroll-to-top
    signals_template.py         — Key-value signal rows with fixed-width columns
    two_column_table_template.py — Side-by-side ranked lists (boost/attack style)
    status_bar_template.py      — Bottom status bar with keybindings and metadata

Usage:
    1. Copy the templates you need into your game's widget directory
    2. Rename classes and IDs
    3. Adapt update_data() signatures for your data model
    4. Add CSS rules to minimal.tcss following the same patterns
    5. Wire into your screen's compose() and _do_refresh()
"""
