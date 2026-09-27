"""Where a PEPEPANE job id links: the IMD swarm's own explorer (spec §8 LEDGER, §13 identifiers).

PEPEPANE renders no chain address at all -- the device public key and the wallet are
truncated to eight characters at fold time (spec §13) -- so this package's
explorer is not a chain's. :data:`EXPLORER` is ``widgets/explorer.IMD``
(``explorer.imd.fun/jobs/<uuid>``, job pages only), the same explorer surf's
RECORD links a job on. ``tests/address_sweep/builders.py`` binds the declaration
to the sweep's ``SweepCase(name="seat", explorer=IMD, …)``.

:func:`job_link_style` is the one style a seat cell puts on a shown job id: the
OSC 8 hyperlink the terminal follows on Cmd+click and the ``@click`` action
``explorer_action.ExplorerLinkMixin`` opens it with. Both name the same page;
both are refused for anything that is not a canonical lower-case UUID, so a
hostile id renders plain and unlinked (``widgets/address._link`` is the shape,
restated here for a value that is not an address).

Pure: Rich only. No Textual, no I/O, no ``data/``.
"""

from __future__ import annotations

from rich.style import Style

from maxpane_dashboard.widgets.explorer import IMD, is_job_id, open_action, url_for

__all__ = ["EXPLORER", "JOB_COLS", "job_link_style"]

#: The PEPEPANE dashboard's explorer: job pages on ``explorer.imd.fun``, never a chain's address or tx.
EXPLORER = IMD

#: The first eight characters of a job id -- how the swarm's own pages and this
#: repo's tests name a job (``widgets/surf/swarm_seat_record.JOB_COLS`` is the
#: same measurement for the same value). The LEDGER's node column shows
#: ``nodeId8`` and links the row's full ``jobId``; the detail modal shows this head.
JOB_COLS = 8


def job_link_style(job_id: object) -> Style | None:
    """The link style for a **canonical** job id; ``None`` for anything else.

    Built action-first, the stricter check: ``open_action`` refuses a value it
    would not parse back, so no style ever carries a URL for a value the app
    would refuse to open (CLAUDE.md: degrade, never crash).
    """
    if not is_job_id(job_id):
        return None
    try:
        action = open_action(EXPLORER, "job", job_id)
        return Style(link=url_for(EXPLORER, "job", job_id), meta={"@click": action})
    except ValueError:
        return None
