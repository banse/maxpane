"""BOARD facts: canonical outcomes, contributor receipts and worker clocks."""
from rich.text import Text
from maxpane_dashboard.widgets.panels import HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.surf._fmt import fmt_win_rate, source_clock
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token, outcomes_clock

class SurfSwarmBoardHeroBox(HeroBoxBase):
    """Geometry is supplied by the two screen stylesheets."""

class SurfSwarmBoardHero(HeroRow):
    BOX_CLASS = SurfSwarmBoardHeroBox
    BOXES = tuple((f'surf-board-{key}',label) for key,label in (
        ('seats','RECORDED SEATS'),('live','LIVE'),('paused','PAUSED'),('capacity','CAPACITY'),
        ('rate','ACCEPT RATE'),('receipts','RECEIPTS')))

    def update_data(self, swarm_board_summary=None, swarm_board_as_of_hhmm=None,
                    swarm_workers_as_of_hhmm=None, swarm_outcomes_source=None,
                    swarm_contributors_as_of_hhmm=None, **_kwargs):
        summary=swarm_board_summary if isinstance(swarm_board_summary,dict) else {}
        for key,label in self.BOXES:
            field=key.removeprefix('surf-board-')
            if field in ('live','paused','capacity'):
                clock='as of ' + source_clock(swarm_workers_as_of_hhmm)
            elif field=='receipts':
                clock='read ' + source_clock(swarm_contributors_as_of_hhmm)
            else:
                clock=outcomes_clock(swarm_outcomes_source)
            self.render_box(f'#{key}',label,lambda field=field,clock=clock: self._body(field,summary,clock))

    @staticmethod
    def _body(field,summary,clock):
        value=seat_token(summary.get(field))
        body='unavailable' if value is None else fmt_int(value)
        if field=='live' and value is not None:
            body += ' workers'
        elif field=='capacity':
            working=seat_token(summary.get('working'))
            if working is not None and value is not None:
                body=f'{fmt_int(working)} of {fmt_int(value)}\nworking'
        elif field=='rate':
            accepted,attempts=seat_token(summary.get('accepted')),seat_token(summary.get('attempts'))
            if attempts==0 and accepted==0: body='no attempts'
            elif accepted is not None and attempts is not None and accepted <= attempts:
                failed=seat_token(summary.get('failed'))
                body=fmt_win_rate(accepted/attempts)+'\n'+(f'{fmt_int(failed)} failed' if failed is not None else 'failed unavailable')
        return Text(body+'\n'+clock)
