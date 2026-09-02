"""THE SPLIT: where a pool4 fee actually went, measured against what is claimed.

A label/value panel on ``widgets/surf/launchpad.SurfCurveFlow``'s shape -- one
``Vertical`` holding one ``Static``, ``text-wrap: nowrap; text-overflow:
ellipsis`` -- carrying the three measured shares, the four cumulative
counters, ``lastClaimBlock`` and the two unsettled legs.

**Every percentage on this panel is rendered from the payload's measured keys
and from nothing else.**  ``pool4_measured_inference_pct`` /
``_burn_pct`` / ``_stakers_pct`` are computed by ``data/surf_pool4.py`` from
the live counters; this module holds no share of its own to fall back on, and
``test_no_researched_split_is_quoted_in_the_module_source`` greps this file
for the three figures the research documented and fails if any of them
appears.  That is not pedantry: CLAUDE.md's fourth hard constraint records a
protocol documenting a 5% fee that is 1% on chain, and a ratio quoted at "4.0x"
that measured three different values on three consecutive days.  A number
typed into a widget is a number that cannot drift with the chain.

The drift line
--------------

``pool4_split_drift_bps`` is the measured staker share minus the *claimed*
``rewardShareBps()``, in basis points, and it is the one number on this panel
that says whether the recovered interface and the chain agree.  Three states,
three sentences:

* ``0.0`` -- **the healthy value, and it renders as a number.**  It is a
  representable zero, never a dash: "measured matches claimed" is an answer,
  and printing ``--`` over it would turn a passing cross-check into a missing
  read.
* non-zero -- the panel says so **in its own words**, styled, and the line is
  moved to the top of the body, immediately under the title, ahead of the
  measured shares themselves.  A disagreement between what the hook claims and
  what the chain did is the most important thing this panel can tell a reader,
  so it is also the first.
* ``None`` -- one side or the other is unread.  Not zero, not a drift.

The reward leg is subdivided on mainnet, and was not on Sepolia
--------------------------------------------------------------

``rewardShareBps()`` is the share of retired IMD that leaves the burn path.
On Sepolia it went straight to the Dripper, so that share **was** the staker
share and one number honestly carried both meanings.  On mainnet a Reward
Distributor sits in front of the Dripper and splits it three ways -- staking,
nodes and bonding -- so the same number now overstates the staker share by
more than three times: 15% where 4.5% is true, and it would render as an
entirely plausible figure.

The producer fixed the number (``pool4_measured_stakers_pct`` is the staking
leg alone once a Distributor is in the path, and the whole reward leg when
there is none, so it is correct on both deployments).  **This module had the
same bug in its labels**, and both are fixed here:

* ``claimed stakers 1,500/10,000 bps`` was wrong on mainnet -- that is the
  claimed *reward share*, and the claimed staker share is 450 bps of it.  It
  now reads ``claimed reward``.
* the drift line said ``measured stakers below claimed``.  ``split_drift_bps``
  compares ``totalRewarded`` against ``rewardShareBps``, i.e. the **whole**
  reward leg on both chains, so it now says ``reward share``.

Both were true on Sepolia and neither was true on mainnet, which is the exact
shape of the defect this whole change exists to remove: a label that was
accurate against one deployment and became a confident lie against the next.

**The three legs are rendered as a subdivision, never as peers.**  They are
indented under the ``claimed reward`` line that names their parent, and they
sit contiguous with it.  On mainnet the three measured percentages
deliberately no longer sum to 100: bonding and nodes are the remainder, and
the leg block is where they are.

**Which shape it is, is said on the ``measured stakers`` line** --
``(staking leg)`` or ``(reward leg)`` -- rather than on the parent, and that
placement is the fix rather than a layout preference.  That is the number
whose meaning changes between deployments, and the one that overstated the
staker share by 3x; the word that disambiguates it belongs against it.  A
reader tells the two apart by reading one word, without counting lines or
summing percentages.  The two words share no substring, for the same reason
the counter vocabulary does not: they are the entire difference between a
number that means 15% and one that means 4.5%.

**The topology is a claim about the chain, and it is read as a WORD.**
``pool4_reward_path`` is ``direct`` or ``via-distributor``, and ``None`` when
``rewardsRecipient()`` was not read.  Four states, and the annotation keys off
the word rather than off any address:

* ``via-distributor``, legs reported -> the split is shown, stakers is the
  ``(staking leg)``;
* ``via-distributor``, no legs       -> a Distributor **is** in the path and
  its split could not be read.  Said outright
  (:data:`DISTRIBUTOR_UNREAD`), never rendered as a two-way deployment;
* ``direct``                         -> there is no Distributor and the reward
  leg genuinely is the staker leg: ``(reward leg)``;
* ``None``                           -> **annotate nothing.**  Not a guess in
  either direction.

**An address cannot carry this, and asking for one was my mistake.**  I filed
for ``pool4_distributor_addr`` on the argument that a stated fact beats an
inference, and WP0 accepted the diagnosis and rejected the remedy: that
address is ``None`` both when there is no Distributor *and* when the getter
that would have named one failed.  Those two are three times apart on the
headline percentage, and the hook's getters are batched with
``allowFailure=True`` -- one reverted view degrades one field, not the round
-- so "the counters answered, ``rewardsRecipient()`` did not" is an ordinary
payload rather than a corner case.  A panel reading absence-of-address as
absence-of-Distributor would have labelled mainnet's 15% as the staker share
in exactly that payload: **the 3x bug, arriving through the door opened to
prevent it.**  The healthy reading has to be a word, because ``None`` is what
an omission produces.  Same family as :data:`POOL4_COUNTER_STATES`.

The address is still accepted and still rendered nowhere here; it is HATCHES'
to show.  It is deliberately **not** used as a fallback signal: a fallback
that is wrong in a routine payload is not a safety net, it is the defect with
a longer fuse.

**Bonding's share is DERIVED and says so on the same line.**  There is no
``bondingBps()`` getter -- it is ``denominator - staking - nodes`` -- so the
word ``derived`` sits beside the number, on ``cap_floor``'s *observed*
precedent, and the value goes ``None`` whenever either input does.  It is
never rendered as though the chain stated it.

``held`` is the chain's own word (``heldBonding()``/``heldNft()``): IMD sitting
in the Distributor awaiting ``distribute()``.  **Zero is a real value** meaning
distributed up to date, so it renders ``0.00``.  There is deliberately no
staking equivalent -- that leg is forwarded rather than held -- so the stakers
line carries no ``held`` clause at all rather than a zero that would be
indistinguishable from a real one.

The counter reconciliation (R1 control (c), finding W1)
------------------------------------------------------

``pool4_counter_state`` is the verdict on whether the hook's cumulative
counters equal the sum of its own logs, and it belongs **here** because this
is the panel those counters are rendered on: a verdict whose evidence is on
another screen is not evidence a reader can check.  It matters because the
hook is *unverified source* -- its interface was recovered from bytecode
selectors and three of its event signatures are still unresolved -- so a
wrong operand order in a decoder otherwise surfaces as a confident wrong
number with nothing anywhere to say so.

**Five states, and only two of them are verdicts.**

* ``mismatch`` -- an identity does not hold.  Hoisted to the top of the body,
  **above even a non-zero split drift**: the drift is computed *from* these
  counters, so if the counters themselves are wrong the drift is a
  measurement of nothing, and the deeper fault is reported first.
* ``reconciled`` -- the only good news this key gives.  It sits quietly with
  the counters it is about, because a passing control is not news.
* ``window-limited`` / ``unchecked`` / ``None`` -- **"we did not establish
  this", which is a third thing.**  These are the states this panel is most
  likely to get wrong, because the tempting renderings are the two wrong
  ones: silence reads as health, and a warning colour reads as alarm.  They
  therefore share the phrase *not established*, share the muted style of an
  ordinary line, and share no word with either verdict.

That last property is enforced rather than hoped for.  The producer spells
its vocabulary ``reconciled``/``mismatch`` and not ``agree``/``disagree``
precisely because ``agree`` is a substring of ``disagree``, and a widget
testing ``"agree" in state`` would paint a mismatch as healthy; this module
renders **its own** words, so it carries **its own** copy of that guard --
``test_no_rendered_counter_word_is_a_substring_of_another``.

**A mismatch's detail is wrapped, not clipped.**  It is the "by how much",
and a claim whose evidence is shed at a narrow width is not a claim a reader
can act on -- but making it a hard line would light ``‹ widen`` permanently,
since a wei-exact difference is long by nature and the marker would stop
meaning anything.  So it is word-wrapped to the panel's own width
(:func:`_wrap`) and every word of it is visible at every width.  Only a
single unbreakable token wider than the panel is left over-long, and *that*
lights the marker, which is the one case where nothing else can be done.

Width behaviour
---------------

**Every group fits itself, and no group is shed.**  A pair that does not fit
reflows onto two lines; one that fits stays on one.  The decision is made
*per group* (:func:`_fit_group`) and measured against the panel's real width,
never against a constant -- these are cumulative counters on a token whose
supply is nine figures, so nothing here has a bound to size against.

It used to be one global full/narrow tier whose threshold was set by the
**widest** group on the panel.  At the rail's 48 columns the ``unsettled``
pair needs 52, so it forced ``burned · rewarded`` (46) and ``fees ·
retained`` (40) onto two lines each as well: three rows spent because one
group did not fit.  Those rows are not free -- this panel sits in the column
that binds the POOL4 body's **height** pin, so a row here is a row of
terminal the whole body demands.  Per-group fitting returned two of them,
which is what let the mainnet Distributor's three legs land without moving
that pin.

:data:`SHORT_HINT` is therefore reserved for the one case reflowing cannot
answer: a single part wider than the whole panel, where the ``Static``'s CSS
ellipsis is about to cut a number.  A cut number is a wrong number, not a
missing one, and this panel refuses to let that happen quietly.

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``.  The title, its network word, the widen vocabulary, the
markup parsing and the line measurement all come from
``widgets/surf/_pool4.py``, the body's single definition of each (amendment
A13); nothing here is a local copy of any of them.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from rich.cells import cell_len

from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, as_float, fmt_imd
from maxpane_dashboard.widgets.surf._pool4 import (
    join_lines,
    parse_line,
    strip_tags,
    title_text,
    widest_line,
)

__all__ = [
    "COUNTER_ALERT",
    "COUNTER_NEVER",
    "COUNTER_NOT_ESTABLISHED",
    "COUNTER_NO_DETAIL",
    "COUNTER_UNKNOWN",
    "COUNTER_WORDS",
    "DRIFT_ALERT",
    "DRIFT_MATCH",
    "DRIFT_UNREAD",
    "SurfPool4Split",
    "TITLE",
]

#: Panel title.  The network word is appended by
#: :func:`~widgets.surf._pool4.title_text` and a hint after that, both
#: appended and never substituted, so ``"THE SPLIT" in text`` holds at every
#: width and in every state.
TITLE = "THE SPLIT"

#: The word that leads a non-zero drift line.  Upper case, and a word that
#: appears nowhere else on the panel, so a test (and a reader) can find the
#: alarm state without matching on a whole sentence.
DRIFT_ALERT = "DRIFT"

#: What a zero drift says.  ``0.0`` is the healthy answer and this sentence is
#: the panel agreeing with the chain, not the panel having nothing to report.
DRIFT_MATCH = "measured matches claimed"

#: What an unreadable drift says.  Shares no substring with
#: :data:`DRIFT_MATCH` or with :data:`DRIFT_ALERT`: an indeterminate read must
#: never be mistaken for either confident answer (``SurfBurnPipeline.
#: _ready_word``'s rule).
DRIFT_UNREAD = "claimed or measured unread"


#: The phrase the three *neither* states share, and the reason they share it:
#: ``window-limited``, ``unchecked`` and a ``None`` that has never run are all
#: "we did not establish this", which is a third thing beside pass and fail.
#: A reader who learns the phrase once learns all three.
COUNTER_NOT_ESTABLISHED = "not established"

#: This panel's rendered word per producer state.  ``POOL4_COUNTER_STATES``
#: restated -- a widget may not import ``data/`` -- and
#: ``test_the_counter_vocabulary_agrees_with_the_producers`` compares the two
#: in both directions, so a renamed state reddens rather than falling through
#: to the unrecognised branch on a reader's screen.
COUNTER_WORDS = {
    "reconciled": "reconciled",
    "mismatch": "MISMATCH",
    "window-limited": f"{COUNTER_NOT_ESTABLISHED} (window)",
    "unchecked": f"{COUNTER_NOT_ESTABLISHED} (unread)",
}

#: ``pool4_counter_state is None``: the check has never run. Not a failure,
#: not a pass -- and said in the same phrase as its two siblings.
COUNTER_NEVER = f"{COUNTER_NOT_ESTABLISHED} (never run)"

#: A state word this panel does not know. It must not read as health and must
#: not read as alarm, so it lands in the same third category -- while
#: ``test_the_counter_vocabulary_agrees_with_the_producers`` makes sure a
#: *renamed* state is caught in CI rather than here, on screen.
COUNTER_UNKNOWN = f"{COUNTER_NOT_ESTABLISHED} (unrecognised)"

#: The banner a mismatch leads with. Its own constant because it is a
#: **rendered interface string** a test greps composited output for, and
#: because it is the one phrase on this panel that must not be paraphrased.
COUNTER_ALERT = "COUNTER MISMATCH"

#: What each non-mismatch state says after its word, when the producer sent no
#: detail of its own. The producer's detail wins where there is one: it is
#: specific and these are general.
COUNTER_NOTES = {
    # 26 columns exactly, because ``counters reconciled`` is 19 and the rail
    # gives this panel 48: at 27 the note wraps and a *passing* control costs
    # two rows on the column that binds the body's height pin. The longer
    # phrasing it replaced ("counters match the sum of the hook's own logs, to
    # the wei") said no more than this one does.
    "reconciled": "identities hold to the wei",
    "window-limited": "log sums cover a trailing window, not full history",
    "unchecked": "not computed on this sweep",
    None: "the check has not run yet",
}

#: A mismatch with no detail. The absence is **stated**, never left as a bare
#: banner: "something disagrees" with the "by how much" silently missing looks
#: identical to a panel that simply did not render it.
COUNTER_NO_DETAIL = "detail unavailable"


def _wrap(text: str, width: int) -> list[str]:
    """Word-wrap ``text`` to ``width`` **terminal cells**.

    The ``Static`` is ``text-wrap: nowrap`` because every other line here is a
    label/value pair that must not reflow; the mismatch detail is the one
    piece of prose on the panel, and it is also the one piece that may not be
    lost, so it is wrapped here instead of by CSS.

    Measured on :func:`rich.cells.cell_len`, never ``len()``.  A piece comes
    back wider than ``width`` only when a single token is unbreakable and
    over-long; the caller marks that piece **hard** so the widen marker lights
    for it, which is the one case wrapping cannot answer.  ``width <= 0`` is
    "not laid out yet" and returns the text whole; ``on_resize`` re-lays it.
    """
    if width <= 0:
        return [text]
    out: list[str] = []
    line = ""
    for word in text.split():
        if cell_len(word) > width:
            if line:
                out.append(line)
                line = ""
            out.append(word)          # over-long and unbreakable: flagged, not cut
            continue
        candidate = f"{line} {word}" if line else word
        if cell_len(candidate) <= width:
            line = candidate
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    return out or [""]


def _fit_group(parts: list[str], width: int) -> list[str]:
    """Pack ``parts`` onto as few lines as fit, joined by the panel's ``·``.

    **Per group, not per panel.** This replaced a global full/narrow tier
    whose threshold was set by the *widest* group on the panel: at the rail's
    48 columns the ``unsettled`` pair needs 52, so it forced every other pair
    onto two lines each -- three rows spent because one group did not fit.
    Deciding per group spends a row only where a row is actually needed.

    A part is never split, so a line comes back over-long only when a single
    part exceeds ``width``; the caller marks that line **hard** and the widen
    marker lights for it. Measured on :func:`rich.cells.cell_len`.

    ``width <= 0`` is "not laid out yet" and packs everything onto one line;
    :meth:`SurfPool4Split.on_resize` re-lays it out once there is a size.
    """
    if width <= 0:
        return [" · ".join(parts)]
    lines: list[str] = []
    line = ""
    for part in parts:
        candidate = f"{line} · {part}" if line else part
        if line and cell_len(candidate) > width:
            lines.append(line)
            line = part
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _fit_block(head: str, note: str, width: int, style: str,
               indent: str = "") -> list[tuple]:
    """One counter line if it fits, otherwise the word and its note wrapped.

    The combined ``word · note`` form is preferred because a routine state is
    not worth two lines of a panel this dense.  When it does not fit, the note
    reflows underneath rather than being cut -- the *word* is the verdict and
    must never be the thing an ellipsis eats, which is exactly what a single
    soft line would allow at a narrow width.

    A piece is marked ``hard`` only when it is still too wide after wrapping,
    i.e. an unbreakable token or a head longer than the whole panel.  An
    ordinary counter report therefore costs no widen marker, and the marker
    keeps meaning "something here cannot be shown".
    """
    combined = f"{head} · {note}" if note else head
    if not width or cell_len(combined) <= width:
        pieces = [combined]
    else:
        # The continuation carries the head's own indent. Without it a wrapped
        # distributor leg starts at the panel's left margin and stops reading
        # as part of the leg above it -- which turns a subdivision back into
        # the row of peers this whole rendering exists to avoid.
        pieces = [head] + [
            indent + piece for piece in _wrap(note, max(width - cell_len(indent), 1))
        ]
    return [
        (style, piece, bool(width) and cell_len(piece) > width)
        for piece in pieces
    ]


def _counter_lines(state, detail, width: int) -> tuple[list[tuple], bool]:
    """``(lines, alarming)`` for the counter reconciliation.

    ``alarming`` hoists the block to the top of the body.  Only ``mismatch``
    sets it: the other four states report that the control did or did not
    establish something, and a report is not an alarm.

    The state is normalised before lookup because a **persisted** payload is
    third-party input on this repo's own precedent, and an unrecognised word
    lands in the third category rather than being echoed into a verdict.
    """
    key = state.strip().lower() if isinstance(state, str) else None
    if key is not None and key not in COUNTER_WORDS:
        return _fit_block(f"counters {COUNTER_UNKNOWN}", "", width, "dim"), False

    note = strip_tags(detail) or COUNTER_NOTES.get(key, "")

    if key == "mismatch":
        # The banner keeps a line of its own at every width: it is the whole
        # point of the state, and combining it with the evidence would let a
        # long detail push it into a reflow.
        lines = [("bold yellow", f"⚠ {COUNTER_ALERT}", False)]
        lines += [
            ("yellow", piece, bool(width) and cell_len(piece) > width)
            for piece in _wrap(note or COUNTER_NO_DETAIL, width)
        ]
        return lines, True

    word = COUNTER_WORDS[key] if key is not None else COUNTER_NEVER
    return _fit_block(f"counters {word}", note, width, "dim"), False


#: What ``measured stakers`` means when a Distributor subdivides the reward
#: leg: the staking part of it, and nothing else.
LEG_WORD_STAKING = "staking leg"

#: ...and when there is none: the whole reward leg, which on such a deployment
#: genuinely **is** the staker leg.
#:
#: The pair reads as a contrast -- ``(reward leg)`` against ``(staking leg)``
#: -- and neither is a substring of the other, the same guard the counter
#: vocabulary carries and for the same reason: these two words are the entire
#: difference between a number that means 15% and one that means 4.5%.
#: ``"whole reward leg"`` was the first spelling and it was six columns too
#: wide for the band this panel is rendered in, which would have lit the widen
#: marker on a line that had lost nothing.
#:
#: **This annotation sits on the stakers line rather than on the claimed line
#: below it, and that is the fix rather than a layout preference.** It is that
#: number whose meaning changes between the two deployments -- the one that
#: overstated the staker share by more than three times -- so the word that
#: disambiguates it belongs against it. It also costs no row: the rail gives
#: this panel 48 columns and the alternative did not fit on one, which on the
#: column that binds the body's height pin is a row nobody agreed to spend.
LEG_WORD_WHOLE = "reward leg"

#: What indents a leg under the ``claimed reward`` line that names its parent.
#: One column, because the rail gives this panel 48 and the longest leg spends
#: 47 of them; the indent is what makes the block read as a subdivision rather
#: than as three more peers, so it is the last column that may be reclaimed.
LEG_INDENT = " "

#: Said when ``pool4_distributor_addr`` names a Distributor but no leg reports
#: a value: it **is** in the path and its split could not be read. Distinct
#: from both the two-way rendering and a healthy three-way one, because it is
#: a third fact -- and the one a reader would otherwise mistake for "this
#: deployment has no Distributor", which is the wrong protocol.
DISTRIBUTOR_UNREAD = "distributor present, split unread"

#: ``POOL4_REWARD_PATHS`` restated -- a widget may not import ``data/`` -- and
#: ``test_the_reward_path_vocabulary_agrees_with_the_producers`` compares the
#: two in both directions, so a renamed path reddens rather than silently
#: annotating nothing on every payload.
PATH_DIRECT = "direct"
PATH_VIA_DISTRIBUTOR = "via-distributor"
REWARD_PATHS = (PATH_DIRECT, PATH_VIA_DISTRIBUTOR)

#: Beside bonding's share, on ``cap_floor``'s *observed* precedent. Bonding has
#: no getter: it is ``denominator - staking - nodes``, and a number with no
#: getter behind it must never be rendered as though the chain stated it.
DERIVED = "derived"

#: The legs, in render order, as ``(label, bps key, earned key, held key)``.
#: ``held`` is ``None`` for stakers **by contract**: that leg is forwarded
#: rather than held, so there is no ``held_staking`` to read and the line
#: carries no clause -- inventing one for symmetry would print a zero
#: indistinguishable from a real "distributed up to date".
#: Bonding is rendered last because it is the derived remainder.
DISTRIBUTOR_LEGS = (
    ("stakers", "distributor_staking_bps", "distributor_staking_earned", None),
    ("nodes", "distributor_nodes_bps", "distributor_nodes_earned",
     "distributor_held_nodes"),
    ("bonding", "distributor_bonding_bps", "distributor_bonding_earned",
     "distributor_held_bonding"),
)


def _leg_share(bps, denominator) -> str:
    """One leg's share of the reward leg, as a percentage of the denominator.

    A percentage rather than the raw bps because the rail gives this panel 48
    columns: ``bonding 40.00% derived · earned 4.20 · held 4.20`` fits and
    ``bonding 4,000 bps derived · …`` does not, and a line that does not fit
    costs a row in the column that binds the body's height pin.

    ``--`` when either side is unread -- a failed read, correctly a dash, and
    never a zero share.
    """
    share = as_float(bps)
    total = as_float(denominator)
    if share is None or not total:
        return DASH
    return f"{share / total * 100:.2f}%"


def _distributor_lines(payload: dict, width: int) -> tuple[list[tuple], bool]:
    """``(lines, any leg reported)`` for the three-way reward-leg subdivision.

    The lines are indented and sit directly under the ``claimed reward`` line
    that names their parent, which is what makes them read as a *subdivision
    of that share* rather than as three more peers beside the measured
    percentages.

    Returns no lines at all when no leg reports anything: there is nothing to
    subdivide, and three dashes would suggest a Distributor whose values could
    not be read -- a different claim from the one the payload supports.

    The boolean is what the ``measured stakers`` annotation keys off, and the
    inference behind it is exact rather than a guess: ``reward_leg_split``
    returns ``None`` whenever a Distributor is in the path but its bps are
    unread, so **a stakers percentage that exists while no leg reports means
    there is no Distributor** and that percentage is the whole reward leg.
    """
    denominator = payload.get("bps_denominator")
    rows: list[tuple] = []
    present = False
    for label, bps_key, earned_key, held_key in DISTRIBUTOR_LEGS:
        bps = payload.get(bps_key)
        earned = payload.get(earned_key)
        held = payload.get(held_key) if held_key else None
        if bps is None and earned is None and held is None:
            continue
        present = True
        head = f"{LEG_INDENT}{label} {_leg_share(bps, denominator)}"
        if label == "bonding":
            head = f"{head} {DERIVED}"
        clauses = [f"earned {fmt_imd(earned)}"]
        if held_key is not None:
            # ``0.00`` here means distributed up to date -- a fact, not a gap.
            clauses.append(f"held {fmt_imd(held)}")
        # Two spaces between the clauses rather than the panel's ``·``: the
        # bonding line is the longest of the three (it carries ``derived``) and
        # at the rail's 48 the separator was the one column that pushed it onto
        # a second row. Two rows for one leg would be three rows for the block,
        # on the column that binds the body's height pin.
        rows += _fit_block(head, "  ".join(clauses), width, "dim", LEG_INDENT)
    return (rows, True) if present else ([], False)


def _pct(value) -> str:
    """A measured share, two decimals.  ``--`` only when it was not read."""
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:.2f}%"


def _exact(value) -> str:
    """A cumulative counter, exact and comma-grouped -- never compacted.

    These four are the numbers the chain can settle: the sums of
    ``FeeCollected`` and ``ClaimsSettled`` must equal them to the wei, and a
    compacted ``111.1K`` cannot be compared against anything.  The same
    distinction ``SurfBurnPipeline._fmt_total`` draws for its own headline
    cumulative figure, for the same reason.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.0f}"


def _eth(value) -> str:
    """Retained ETH.  Four decimals: the observed balances are third-decimal
    quantities, and a zero here is a *fact* -- the owner has withdrawn
    everything ever collected -- so it renders as a number, not a dash.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:,.4f}"


def _block(value) -> str:
    """``lastClaimBlock``, comma-grouped."""
    v = as_float(value)
    if v is None:
        return DASH
    return f"{int(v):,}"


def _bps(value) -> str:
    """A raw basis-point integer, comma-grouped; ``--`` when unread."""
    v = as_float(value)
    if v is None:
        return DASH
    return f"{int(v):,}"


def _drift_line(drift_bps) -> tuple[str, str, bool]:
    """``(style, text, alarming)`` for the drift line.

    ``alarming`` is what moves the line to the top of the body.  Note the
    ``v == 0`` test rather than a falsiness test: ``as_float`` already turned
    an unreadable value into ``None`` and returned it above, so by this point
    a zero is a **measurement**, and the two must not share a branch.

    Every form here puts the *number* first and the sentence after it, which
    is what lets this line be classified soft in :func:`_body_lines` -- the
    ``Static``'s ellipsis eats from the right, so a cut takes words off the
    explanation and never a digit off the value.
    """
    v = as_float(drift_bps)
    if v is None:
        return "dim", f"drift {EMDASH} bps · {DRIFT_UNREAD}", False
    if v == 0:
        return "dim", f"drift 0.00 bps · {DRIFT_MATCH}", False
    # ``split_drift_bps`` compares ``totalRewarded`` against
    # ``rewardShareBps``: both are the WHOLE reward leg, on both deployments.
    # This line said "measured stakers" until mainnet subdivided that leg,
    # at which point the wording named a quantity a third the size of the one
    # being compared.
    direction = "above" if v > 0 else "below"
    return (
        "bold yellow",
        f"⚠ {DRIFT_ALERT} {v:+,.2f} bps · reward share {direction} claimed",
        True,
    )


def _body_lines(payload: dict, width: int) -> list[tuple[str, str, bool]]:
    """The panel body as ``(style, plain text, hard)`` triples.

    Kept as triples rather than as finished markup so the caller can *measure*
    what it is about to render (``cell_len`` on the plain half) and escape it
    once, in one place, on the way out.

    ``hard`` is whether an ellipsis on this line would cut a **value**.  Only
    the hard lines choose the tier and light the marker: the drift sentence
    leads with its own number and trails an explanation, so clipping it costs
    words, which is the same licence ``pool4_flow``'s legend has.  Measuring
    the sentence instead would reflow -- and then mark -- a panel whose every
    value fits comfortably, which is a marker pointing at nothing.

    **Nothing is ever shed here.**  A group that does not fit is *reflowed*
    onto more lines by :func:`_fit_group`, per group rather than per panel, so
    no value is dropped and nothing is advertised as dropped.  The widen
    marker is left for the one case reflowing cannot answer: a single part
    wider than the panel.
    """
    drift_style, drift_text, alarming = _drift_line(payload.get("drift_bps"))
    counter, counter_alarming = _counter_lines(
        payload.get("counter_state"), payload.get("counter_detail"), width,
    )

    # The hoisted block, and the order inside it is an argument, not a
    # preference: a counter mismatch says the *counters* disagree with the
    # hook's own logs, and the split drift is computed **from** those counters
    # -- so if the first is true the second is a measurement of nothing. The
    # deeper fault is reported first. One blank line closes the block however
    # many lines went into it.
    hoisted: list[tuple[str, str, bool]] = []
    if counter_alarming:
        hoisted += counter
    if alarming:
        hoisted.append((drift_style, drift_text, False))

    lines: list[tuple[str, str, bool]] = [("", "", False)]
    if hoisted:
        lines += hoisted
        lines.append(("", "", False))

    legs, subdivided = _distributor_lines(payload, width)
    # The stated word, never an inference and never an address. ``None`` here
    # is "unknown", and it annotates nothing: guessing in either direction is
    # a 3x error on the headline percentage.
    path = payload.get("reward_path")
    stakers = f"stakers {_pct(payload.get('stakers_pct'))}"
    if path == PATH_VIA_DISTRIBUTOR:
        stakers = f"{stakers} ({LEG_WORD_STAKING})"
    elif path == PATH_DIRECT and payload.get("stakers_pct") is not None:
        # ``direct``, and a number to describe: the reward leg genuinely IS
        # the staker leg. Annotated only when there is a number -- a word over
        # a dash would describe a read that did not happen.
        stakers = f"{stakers} ({LEG_WORD_WHOLE})"
    measured = [
        f"inference {_pct(payload.get('inference_pct'))}",
        f"burn {_pct(payload.get('burn_pct'))}",
        stakers,
    ]
    # Each part carries its own ``measured`` prefix, so a line that packs two
    # of them and a line that carries one read the same way. Dropping the
    # prefix from the continuation would save four columns and cost a reader
    # the word that says what the number is a measurement *of*.
    lines += [
        ("", text, True)
        for text in _fit_group([f"measured {part}" for part in measured], width)
    ]

    # The parent of the leg block. ``claimed reward``, not ``claimed stakers``:
    # ``rewardShareBps()`` is the whole reward leg, and calling it the staker
    # share was true only while the two were the same number. ``{bps}/{den}``
    # rather than ``{bps} of {den}`` keeps it on ONE row at the rail's 48, and
    # a second row here would be a row on the column that binds the body's
    # height pin.
    lines.append((
        "dim",
        f"claimed reward {_bps(payload.get('reward_share_bps'))}"
        f"/{_bps(payload.get('bps_denominator'))} bps",
        True,
    ))
    lines += legs
    if path == PATH_VIA_DISTRIBUTOR and not subdivided:
        # It is in the path and we could not read its split. Saying nothing
        # would render a mainnet deployment as though it were a Sepolia one,
        # which is the whole protocol misdescribed by omission.
        lines += _fit_block(f"{LEG_INDENT}{DISTRIBUTOR_UNREAD}", "", width,
                            "dim", LEG_INDENT)
    if not alarming:
        lines.append((drift_style, drift_text, False))

    pairs = [
        (f"burned {_exact(payload.get('total_burned'))} IMD",
         f"rewarded {_exact(payload.get('total_rewarded'))} IMD"),
        (f"fees {_exact(payload.get('total_fee_token'))} IMD",
         f"retained {_eth(payload.get('retained_eth'))} ETH"),
        # ``0.00`` here means "settled up to date" -- a fact about the hook,
        # not a missing read.  ``fmt_imd`` is the formatter that renders a
        # sub-1 accrual as ``0.05`` instead of the house compact helper's
        # ``0``, which is the false zero this dashboard exists to avoid.
        (f"unsettled burn {fmt_imd(payload.get('unsettled_burn'))} IMD",
         f"unsettled stakers {fmt_imd(payload.get('unsettled_stakers'))} IMD"),
    ]
    for pair in pairs:
        # One line where the pair fits, two where it does not -- decided for
        # this pair alone. ``burned · rewarded`` (46) and ``fees · retained``
        # (40) fit the rail's 48 and ``unsettled`` (52) does not, so the first
        # two now cost one row each where the global tier charged two.
        lines += [("dim", text, True) for text in _fit_group(list(pair), width)]

    if not counter_alarming:
        # It is a verdict on the four counters directly above it, so it is
        # rendered directly below them -- close enough to read as their
        # footnote rather than as a fact about something else on the panel.
        lines += counter

    lines.append((
        "dim",
        f"last claim block {_block(payload.get('last_claim_block'))}",
        True,
    ))

    # Stripped, not merely escaped: an escaped ``[/x]`` still paints the
    # literal ``[/x]`` once Rich unescapes it for display, and a persisted
    # cache file is third-party input too.
    as_of = strip_tags(payload.get("as_of"))
    if as_of:
        lines.append(("dim", f"as of {as_of}", True))
    return lines


class SurfPool4Split(Vertical):
    """The measured fee split, and whether it matches what the hook claims."""

    DEFAULT_CSS = """
    SurfPool4Split {
        height: auto;
    }
    SurfPool4Split > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw values, not formatted lines, so a resize re-lays them out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(TITLE, id="surf-p4split-body")

    def update_data(
        self,
        pool4_network=None,
        pool4_measured_inference_pct=None,
        pool4_measured_burn_pct=None,
        pool4_measured_stakers_pct=None,
        pool4_reward_share_bps=None,
        pool4_bps_denominator=None,
        pool4_split_drift_bps=None,
        pool4_total_burned=None,
        pool4_total_rewarded=None,
        pool4_total_fee_token=None,
        pool4_retained_eth=None,
        pool4_last_claim_block=None,
        pool4_unsettled_burn=None,
        pool4_unsettled_stakers=None,
        pool4_counter_state=None,
        pool4_counter_detail=None,
        pool4_distributor_addr=None,
        pool4_reward_path=None,
        pool4_distributor_staking_bps=None,
        pool4_distributor_nodes_bps=None,
        pool4_distributor_bonding_bps=None,
        pool4_distributor_staking_earned=None,
        pool4_distributor_nodes_earned=None,
        pool4_distributor_bonding_earned=None,
        pool4_distributor_held_nodes=None,
        pool4_distributor_held_bonding=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel.  Signature frozen by
        ``docs/surf_pool4_contract.md`` §0.4 -- every key spelled with its full
        ``pool4_`` prefix (no short ``as_of_hhmm`` alias, deliberately), and
        ``**_kwargs`` mandatory because the screen splats the whole payload.
        """
        self._payload = {
            "network": pool4_network,
            "inference_pct": pool4_measured_inference_pct,
            "burn_pct": pool4_measured_burn_pct,
            "stakers_pct": pool4_measured_stakers_pct,
            "reward_share_bps": pool4_reward_share_bps,
            "bps_denominator": pool4_bps_denominator,
            "drift_bps": pool4_split_drift_bps,
            "total_burned": pool4_total_burned,
            "total_rewarded": pool4_total_rewarded,
            "total_fee_token": pool4_total_fee_token,
            "retained_eth": pool4_retained_eth,
            "last_claim_block": pool4_last_claim_block,
            "unsettled_burn": pool4_unsettled_burn,
            "unsettled_stakers": pool4_unsettled_stakers,
            "counter_state": pool4_counter_state,
            "counter_detail": pool4_counter_detail,
            # ``nodes`` where the chain says ``nft``: the payload key mirrors
            # the project's documentation and the model field mirrors the
            # chain, which is WP0's stated discipline and is pinned in both
            # directions. Not a slip, and not to be "corrected" here.
            # Accepted and rendered nowhere: HATCHES shows the address. It is
            # deliberately not a fallback topology signal -- see the module
            # docstring on why an address cannot carry this fact.
            "distributor_addr": pool4_distributor_addr,
            "reward_path": pool4_reward_path,
            "distributor_staking_bps": pool4_distributor_staking_bps,
            "distributor_nodes_bps": pool4_distributor_nodes_bps,
            "distributor_bonding_bps": pool4_distributor_bonding_bps,
            "distributor_staking_earned": pool4_distributor_staking_earned,
            "distributor_nodes_earned": pool4_distributor_nodes_earned,
            "distributor_bonding_earned": pool4_distributor_bonding_earned,
            "distributor_held_nodes": pool4_distributor_held_nodes,
            "distributor_held_bonding": pool4_distributor_held_bonding,
            "as_of": pool4_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the lines out: the layout depends on the width.

        Without this, a panel first rendered at zero width keeps the optimistic
        wide layout for the life of the screen and lets the CSS ellipsis cut
        its counters instead of reflowing them.
        """
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _parse(self, width: int) -> list[tuple, ...]:
        """``_body_lines`` parsed to ``(Text, hard)`` pairs.

        Parsed **per line** through :func:`~widgets.surf._pool4.parse_line`,
        which is the whole reason to parse before measuring: one unparseable
        line is dropped and the rest of the panel still paints, where one
        joined markup string fails whole.  It also parses *here*, inside a
        ``try`` -- handing ``Static.update`` a markup string defers
        ``Content.from_markup`` into the message pump, where the failure
        raises outside the screen's own ``try/except`` and takes the app down
        (CLAUDE.md, ``SurfFeed._row_text``).
        """
        out = []
        for style, text, hard in _body_lines(self._payload, width):
            escaped = safe_markup(text)
            parsed = parse_line(f"[{style}]{escaped}[/]" if style else escaped)
            if parsed is not None:
                out.append((parsed, hard))
        return out

    def _render_view(self) -> None:
        width = max(self.content_size.width - 2, 0)

        def widest(rows) -> int:
            """Widest line that could lose a **value** to the ellipsis.

            Measured on the parsed ``Text`` through
            :func:`~widgets.surf._pool4.widest_line`, i.e. on
            ``rich.cells.cell_len`` -- a CJK glyph is one character and two
            cells, and a tier chosen on ``len()`` hands the overflow to the
            CSS ellipsis to eat in silence.
            """
            return widest_line([text for text, hard in rows if hard])

        # One pass. There is no second, narrower layout to fall back to any
        # more: every group fits itself (:func:`_fit_group`), so the only line
        # that can still be over-wide is one carrying a single part wider than
        # the panel -- which no relayout can help and the marker below names.
        rows = self._parse(width)

        # A single part is wider than the whole panel, so the ``Static``'s
        # CSS ellipsis is about to cut a value.  ``title_text`` places the
        # widest marker
        # that fits -- ``‹ widen``, then the bare ``‹`` -- and places none at
        # all when neither does, rather than pushing the network word off the
        # title to make room for a marker CSS would eat anyway.
        head = title_text(TITLE, self._payload.get("network"),
                          bool(width) and widest(rows) > width, width)
        parsed_head = parse_line(f"[bold]{safe_markup(head)}[/]")

        body = join_lines(
            ([parsed_head] if parsed_head is not None else [])
            + [text for text, _hard in rows]
        )
        try:
            self.query_one("#surf-p4split-body", Static).update(body)
        except Exception:  # not composed yet
            pass
