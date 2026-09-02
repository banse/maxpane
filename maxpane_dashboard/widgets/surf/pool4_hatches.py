"""POOL4 rail: HATCHES -- discovery, the four addresses, and every lever an
owner still holds.

This is the panel that answers *who can still change this thing*. It renders
``pool4_discovery_state`` / ``pool4_discovery_detail`` (how the hook on screen
was arrived at), the four addresses the rest of the view reads from, and the
``pool4_hatches`` row list: one row per owner-held lever, each with the scope
it lives on, the lever's name, its state, and -- width permitting -- the
address behind it.

**Read-only** (CLAUDE.md hard constraint 1 -- no signer, no transactor, no
calldata construction anywhere in this repo). This panel *displays* that an
owner key exists and whether it has been renounced; it never offers to call
anything and never builds calldata.

Shared primitives live in ``_pool4.py``
---------------------------------------
The network word, the panel title and its ``‹ widen`` marker, the tag
stripper and the ``Text`` builders every line funnels through are imported
from ``widgets/surf/_pool4.py``, which all five pool4 panels share. They lived
here for one wave and were hoisted under **amendment A13**, which also ruled
the network-word policy: an **allowlist**, with anything outside
``POOL4_NETWORKS`` -- ``None`` included -- rendering the em dash. This panel's
earlier pass-through was overruled, and the objection behind it (a third
network would blank every title) is answered there by an agreement test
against ``surf_models.POOL4_NETWORKS`` rather than by a looser gate.

:func:`fit_cell` is the one helper that stayed: this module is its only
caller. It is named for what it does rather than ``window``, because a bare
noun a caller already uses for a local is how the hoist broke twice before it
landed (``body``, ``line``, ``widest`` did the same to ``body = self.query_one
(...)``).

Third-party text
----------------
``detail``, ``addr``, ``pool4_discovery_detail`` and every address key are
third-party-derived. Each is flattened, stripped of complete ``[...]``-shaped
runs, escaped with :func:`~maxpane_dashboard.widgets.markup_safety.
safe_markup`, and only then interpolated into a markup line that is parsed
into a ``rich.text.Text`` **here**, inside this module's own ``try`` --
never handed to ``Static.update()`` as a markup string. ``Static.update()``
defers ``Content.from_markup`` into the message pump, so a parse failure
there raises outside the screen's ``try/except`` and takes the app down;
parsed here, the identical failure degrades to a skipped line.
(``SurfFeed._row_text`` and ``SurfBurnkeepers._row_text`` are the worked
examples this mirrors.)

Primitives only -- this module imports nothing from ``data/`` or
``analytics/``. The closed vocabularies for ``scope`` / ``label`` / ``state``
are *not* imported from ``data/surf_models.py`` for that reason: this panel
renders whatever word it is handed and never validates it, so an added
vocabulary member needs no widget change.
"""

from __future__ import annotations


from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, long_addr
from maxpane_dashboard.widgets.surf._pool4 import (
    GLYPH_HINT,
    NETWORK_UNKNOWN,
    WIDEN_HINT,
    join_lines,
    parse_line,
    strip_tags,
    title_text,
    widest_line,
)

#: ``GLYPH_HINT`` / ``NETWORK_UNKNOWN`` / ``WIDEN_HINT`` are re-exported from
#: ``_pool4`` rather than redeclared, so ``pool4_hatches.WIDEN_HINT`` keeps
#: meaning exactly what every other pool4 module means by it.
__all__ = [
    "ADDRESS_LABELS",
    "COMPACT_WIDTH",
    "CITATION_LABEL",
    "DISCOVERY_UNKNOWN",
    "FULL_WIDTH",
    "GLYPH_HINT",
    "MAX_ROWS",
    "NETWORK_UNKNOWN",
    "SurfPool4Hatches",
    "TITLE",
    "REWARD_PATH_WORDS",
    "SOURCE_WORDS",
    "UNKNOWN_PATH_WORD",
    "UNAUDITABLE_LINE",
    "UNSOURCED_WORD",
    "UNAVAILABLE_LINE",
    "WIDEN_HINT",
    "fit_cell",
]

# ---------------------------------------------------------------------------
# Panel-local helper.  Everything else this panel used to define -- the network
# word, the title and its marker, the tag stripper, the ``Text`` builders and
# the width measurement -- moved to ``widgets/surf/_pool4.py`` under amendment
# A13, so all five pool4 panels share one spelling of each.  ``fit_cell``
# stayed here because this is its only caller: hoisting a one-caller helper
# buys no convergence and costs a reader one more file to open.
# ---------------------------------------------------------------------------


def fit_cell(value: object, cols: int) -> str:
    """Fit already-stripped text into *cols* terminal cells, ellipsising.

    Measured with ``rich.cells.cell_len``, never ``len()`` -- a CJK glyph is
    one character and two cells, so a ``len()``-fitted cell overflows its
    column and hands the overflow to CSS ``text-overflow: ellipsis``, which
    eats real content in silence.
    """
    text = strip_tags(value)
    if cols <= 0 or not text:
        return ""
    if cell_len(text) <= cols:
        return text
    out: list[str] = []
    used = 0
    for ch in text:
        w = cell_len(ch)
        if used + w > cols - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"

# ---------------------------------------------------------------------------
# HATCHES
# ---------------------------------------------------------------------------

TITLE = "HATCHES"
UNAVAILABLE_LINE = "hatches unavailable"

#: What the discovery line says when ``pool4_discovery_state is None``.
#: Deliberately not ``"not-discovered"``: that is a *closed vocabulary
#: member* meaning "discovery ran and found nothing", which is a different
#: statement from "discovery has not run". Rendering the same words for both
#: is the FARM/HOUR-SAVED defect CLAUDE.md records.
DISCOVERY_UNKNOWN = "not run"

#: Rows drawn before the list is cut. Nine labels across five scopes as of
#: 2026-09-02 (`distributor` and its `dripper` lever joined when pool4 went
#: live on mainnet); twelve leaves room for a scope to grow a second lever
#: of the same name without silently dropping one.
MAX_ROWS = 12

#: The label the citation line carries. ``pool4_discovery_source_tx`` is a
#: **pointer, not a credential** -- it says where to look, and the chain stays
#: the authority -- so the line names it in the flattest possible terms and
#: makes no claim about what it proves.
CITATION_LABEL = "tx"

#: The one state/citation combination worth surfacing, per
#: ``surf_models.Pool4Discovery``'s table:
#:
#:     not-discovered + None   nothing to cite yet -- expected
#:     rejected       + hash   the rejection cites the post it judged
#:     adopted        + hash   the audit trail exists -- healthy
#:     adopted        + None   AN ADOPTION NOTHING CAN AUDIT
#:
#: Only the last row gets a line. The first is the day-one path that actually
#: runs, and printing "nothing to cite" on every launch would train the reader
#: to skip the row that matters. That asymmetry **is** how this panel
#: distinguishes the two ``None`` cases: an expected absence renders no
#: citation line at all, an unauditable adoption renders this one, in warning
#: colour, where a citation would have been.
#:
#: Expressible only because state and citation are two keys. A merged string
#: could not say it -- which is the argument that got them separated.
UNAUDITABLE_LINE = "no citation to audit"

#: How each ``pool4_discovery_source`` renders beside the verdict, and **the
#: mitigation the operator's decision was conditioned on.**
#:
#: The announce channel has not named the mainnet hook, so the operator
#: accepted ``pool4.imd.fun/docs`` as a *candidate* source. That widens the
#: trust surface and the chain fingerprint does not close it: a ``0x2840``-
#: shaped address mines in ~20,000 tries, four of the five getters are pure
#: liveness checks, and ``token()`` is the candidate's own choice. Prevention
#: was not available; **disclosure was, and this panel is where it is
#: delivered** -- so a dev-signed adoption and a docs-sourced one must never
#: look the same.
#:
#: The order is ``POOL4_DISCOVERY_SOURCES``' own, strongest first, so this
#: panel does not invent a ranking:
#:
#: * ``self-post``    -- signed by the announce wallet's key. Unforgeable.
#:                       Rendered plainly, with no warning.
#: * ``docs``         -- a page anyone with write access to it can change.
#:                       Warned.
#: * ``unattributed`` -- adopted, source not recorded. Warned, because it must
#:                       read *at least as weakly as* ``docs``.
#:
#: The words are not imported from ``surf_models`` (a widget may not import
#: ``data/``); ``test_the_source_vocabulary_agrees_with_the_contract`` asserts
#: this mapping covers ``POOL4_DISCOVERY_SOURCES`` exactly, in both directions,
#: so a fourth source reddens the suite rather than falling through to the
#: unattributed branch and quietly looking like one of these three.
SOURCE_WORDS = {
    "self-post": ("", "via self-post"),
    "docs": ("yellow", "⚠ via docs"),
    "unattributed": ("yellow", "⚠ source unattributed"),
}

#: An adoption whose source key is ``None``.
#:
#: ``None`` is where a producer bug comes to rest, and a renderer treating it
#: as "nothing to say" would draw a docs adoption identically to a signed one
#: -- undoing the disclosure by omission. It is therefore rendered **at least
#: as weakly as ``docs``**, in its own words so the producer bug stays visible
#: rather than hiding inside ``unattributed``. ``None`` must never render as
#: ``self-post``: absence is not provenance, and this is the one key where
#: mistaking it for the strong answer relaunches the problem A27 closed.
UNSOURCED_WORD = "⚠ source unrecorded"

#: The shape of the reward path, annotated onto the distributor's address row.
#:
#: **This exists because an address cannot carry it.**
#: ``pool4_distributor_addr`` is ``None`` both when there is no Distributor
#: (Sepolia's shape) and when the getter that would have named one failed --
#: and those two are three times apart on the headline percentage: 15% of
#: gross reaches stakers under ``direct``, 4.5% under ``via-distributor``. The
#: hook's getters are batched with ``allowFailure=True``, so "counters
#: answered, ``rewardsRecipient()`` did not" is a routine payload rather than
#: a corner case. A panel reading absence-of-address as absence-of-Distributor
#: would state mainnet's topology wrongly in exactly that payload.
#:
#: So the word rides on the ``dist`` row, beside the dash it disambiguates,
#: and costs no line of its own. ``None`` gets :data:`UNKNOWN_PATH_WORD`
#: rather than silence: a bare ``--`` is the ambiguity this key was added to
#: remove, and re-introducing it at the last hop would waste the key.
REWARD_PATH_WORDS = {
    "direct": "direct",
    "via-distributor": "via-distributor",
}

#: ``pool4_reward_path is None`` -- ``rewardsRecipient()`` was not read.
#: Says the path is *unread*, and annotates no leg: guessing one is the error
#: the key exists to prevent, and "unread" is not a guess.
UNKNOWN_PATH_WORD = "path unread"

#: Display forms for scope words wider than :data:`_SCOPE_COLS`.
#:
#: ``distributor`` joined the vocabulary on 2026-09-02 at eleven characters,
#: four more than the grid column. Widening the column would take this panel's
#: content need from 45 to 49, its column need from 49 to 53, and the body's
#: width pin from 106 to 107 -- and the standing rule is **shorten the value,
#: not raise the pin**. ``fit_cell`` would have rendered ``distri…``, which
#: costs the same columns' worth of meaning while looking like a defect.
#:
#: This is a *rendering* map, not a second vocabulary: the producer's word is
#: unchanged and unvalidated, and ``test_every_hatch_scope_fits_its_column``
#: asserts the real property -- every ``POOL4_HATCH_SCOPES`` member renders
#: inside the column -- so a sixth scope reddens the suite instead of being
#: silently clipped.
_SCOPE_SHORT = {"distributor": "dist"}

_SCOPE_COLS = 7      # widest rendered scope: "dripper", "dist" (see _SCOPE_SHORT)
_LABEL_COLS = 9      # widest POOL4_HATCH_LABELS members: "rebalance", "burn sink"
_STATE_COLS = 9      # widest POOL4_HATCH_STATES member: "renounced"
_ADDR_COLS = 17      # `_fmt.long_addr`: 0x + 8 hex + … + 6 hex
_DISCOVERY_LABEL_COLS = 9
_ADDR_LABEL_COLS = 5
_GAP = 1

#: The four addresses the whole view reads from, in the order a reader needs
#: them: the hook is the trust decision, the token is what it prices, and the
#: vault/dripper are reached *off* the hook rather than scraped.
ADDRESS_LABELS = (
    ("hook", "pool4_hook_addr"),
    ("token", "pool4_token_addr"),
    ("vault", "pool4_vault_addr"),
    # The Reward Distributor, mainnet-only and a **new trust surface**: its
    # owner holds `emergencyWithdraw` (drain it) and `setDripper` (re-point the
    # entire rewards path). It sits between the hook and the dripper -- mainnet
    # is `rewardsRecipient() -> Distributor -> dripper() -> Dripper -> vault()`
    # where Sepolia was one hop shorter -- so it is listed in path order.
    ("dist", "pool4_distributor_addr"),
    ("drip", "pool4_dripper_addr"),
)

#: Widest full-tier line: one hatch row carrying all four cells.
#: ``7 + 1 + 9 + 1 + 9 + 1 + 17``. Pinned against composited output by
#: ``test_the_hatches_full_width_pin_is_the_widest_full_tier_line``, which
#: compares with ``==`` and therefore reddens whether the pin is set too low
#: or too high.
FULL_WIDTH = (
    _SCOPE_COLS + _GAP + _LABEL_COLS + _GAP + _STATE_COLS + _GAP + _ADDR_COLS
)                                                                        # 45

#: Widest word in :data:`REWARD_PATH_WORDS` (``via-distributor``);
#: :data:`UNKNOWN_PATH_WORD` is shorter.
_PATH_COLS = 15

#: The distributor's address row carrying its reward-path annotation.
#: ``5 + 1 + 17 + 1 + 15``.
_DIST_ROW_WIDTH = (
    _ADDR_LABEL_COLS + _GAP + _ADDR_COLS + _GAP + _PATH_COLS
)                                                                        # 39

#: One tier below full: the per-row address/detail column goes. It is the
#: cheapest cell to lose *on this panel specifically* -- the five principal
#: addresses already have their own block above, so what is shed is the
#: supplementary owner/sink address, never the hook a reader is trusting.
#: The scope, the lever's name and its state all stay.
#:
#: **The address block is not a tier**, so since 2026-09-02 the widest compact
#: line is the distributor's row rather than the lever grid's 27. That is a
#: measurement, not a regression: the reward-path word is what tells "Sepolia
#: has no Distributor" apart from "the getter that would have named one
#: failed", three times apart on the headline percentage, so shedding it to
#: keep a rounder number would trade the panel's whole reason for a column.
COMPACT_WIDTH = max(
    _SCOPE_COLS + _GAP + _LABEL_COLS + _GAP + _STATE_COLS,               # 27
    _DIST_ROW_WIDTH,                                                     # 39
)


def _pad(value: str, cols: int) -> str:
    """Left-align into *cols* cells, measured with ``cell_len``."""
    fitted = fit_cell(value, cols)
    return fitted + " " * max(cols - cell_len(fitted), 0)


def _grid(cells: list[tuple[str, int, str]]) -> str:
    """Join ``(raw text, width, style)`` cells with :data:`_GAP`.

    The **last** cell is never padded, so a line carries no trailing spaces
    and a width measurement over composited output means what it says. Each
    cell is padded *raw* and escaped afterwards -- padding an escaped string
    misaligns it, since ``\\[`` is two characters and one cell.
    """
    out: list[str] = []
    for index, (raw, cols, style) in enumerate(cells):
        last = index == len(cells) - 1
        text = fit_cell(raw, cols) if last else _pad(raw, cols)
        if not text:
            text = " " * cols if not last else ""
        escaped = safe_markup(text)
        out.append(f"[{style}]{escaped}[/]" if style else escaped)
    return (" " * _GAP).join(out).rstrip()


def _hatch_cells(row: object) -> tuple[str, str, str, str, bool] | None:
    """Decompose one hatch row; ``None`` drops it."""
    if not isinstance(row, dict):
        return None
    try:
        scope = strip_tags(row.get("scope"))
        scope = _SCOPE_SHORT.get(scope, scope)
        label = strip_tags(row.get("label"))
        state = strip_tags(row.get("state")) or "unknown"
        addr = row.get("addr")
        known = bool(row.get("addr_known"))
        if addr:
            tail = long_addr(addr)
        else:
            tail = strip_tags(row.get("detail"))
        return scope, label, state, tail, known
    except Exception:
        return None


def _hatch_row_markup(row: object, tier: str) -> str | None:
    """Format one hatch row at *tier*; ``None`` drops it.

    A single malformed row must never take down the panel, so every failure
    here is a dropped row rather than an exception.
    """
    cells = _hatch_cells(row)
    if cells is None:
        return None
    try:
        scope, label, state, tail, known = cells
        # `unknown` is dimmed and nothing else is coloured: the meaning of
        # `live` swings between reassuring and alarming depending on which
        # lever it is attached to (a live burn sink is fine, a live owner key
        # is the whole point of the panel), so a green/red verdict here would
        # be the widget editorialising over a fact it cannot judge.
        state_style = "dim" if state == "unknown" else ""
        grid: list[tuple[str, int, str]] = [
            (scope, _SCOPE_COLS, "dim"),
            (label, _LABEL_COLS, ""),
            (state, _STATE_COLS, state_style),
        ]
        if tier == "full":
            grid.append((tail, _ADDR_COLS, "cyan" if known and tail else "dim"))
        return _grid(grid)
    except Exception:
        return None


def _reward_path_markup(path: object) -> str:
    """The path word for the ``dist`` row -- see :data:`REWARD_PATH_WORDS`."""
    word = strip_tags(path)
    text = REWARD_PATH_WORDS.get(word)
    if text is None:
        return f"[dim]{safe_markup(UNKNOWN_PATH_WORD)}[/]"
    return f"[dim]{safe_markup(text)}[/]"


def _address_markup(label: str, value: object, note: str = "") -> str:
    """One line of the address block. ``--`` when the address is unread --
    never a blank, which reads as "there is no such contract".

    *note* rides on the same row rather than taking one of its own; the
    distributor's row uses it for the reward path, which is the word that
    tells a bare ``--`` there ("no Distributor" from Sepolia) apart from the
    same ``--`` produced by an unread getter.
    """
    shown = long_addr(value) if value else DASH
    line = (
        f"[dim]{safe_markup(_pad(label, _ADDR_LABEL_COLS))}[/] "
        f"{safe_markup(_pad(shown, _ADDR_COLS))}" if note else
        f"[dim]{safe_markup(_pad(label, _ADDR_LABEL_COLS))}[/] "
        f"{safe_markup(fit_cell(shown, _ADDR_COLS))}"
    )
    return f"{line} {note}" if note else line


def _source_markup(state: str, source: object) -> str:
    """The provenance clause that rides beside the verdict word.

    Rendered only on an adoption: ``not-discovered`` and ``rejected`` have
    nothing adopted to attribute, and printing a provenance note on the
    day-one path every launch is how a reader learns to skip the clause that
    matters. Same asymmetry the citation uses one line below.
    """
    if state != "adopted":
        return ""
    word = strip_tags(source)
    style, text = SOURCE_WORDS.get(word, ("yellow", UNSOURCED_WORD))
    body = f"[{style}]{safe_markup(text)}[/]" if style else safe_markup(text)
    return f" [dim]·[/] {body}"


def _discovery_markup(
    state: object, detail: object, source_tx: object, source: object, room: int
) -> list[str]:
    """The discovery block: the verdict, its sentence, and the post it rests on.

    Three renderings, and the split between them is the whole point of
    ``pool4_discovery_source_tx`` existing as its own key:

    * **the verdict word**, on the label line;
    * **the detail** -- WP3's sentence -- as a single elastic summary line
      fitted to *room*, ellipsised when it does not fit. It is a summary by
      design and the ``…`` says so; the untruncated value stays in the cache
      slot for an auditor. After amendment A27 every clause in it describes a
      **forgeable** gate (a ``0x2840``-shaped address mines in ~20,000 tries,
      four of five getters are liveness checks, ``token()`` is the candidate's
      own choice), so losing its tail to width costs a reader nothing they
      could have relied on;
    * **the citation**, on its own line, fitted to the same room but *never*
      competing with the sentence for it.

    That last bullet is finding S18's actual fix. While the citation was welded
    to the tail of the sentence upstream, any fitting pass dropped it first --
    and after A27 it is the only unforgeable evidence there is. Two keys, two
    lines, and the load-bearing one cannot be crowded out by the decorative one.

    The hash is truncated **prefix-first** (``fit_cell``: head plus ``…``),
    because the prefix is what an explorer searches on. At the pinned body
    width that is 34 hex digits -- unambiguous for any transaction that will
    ever exist -- against the 8 digits the old address-window form gave it.

    *room* is the panel's real text budget less this block's indent, never a
    tier constant: a constant gave the detail one rendering from a 106-column
    terminal to a 260-column one, with 115 spare columns going unused beside
    an ellipsis.
    """
    word = strip_tags(state) or DISCOVERY_UNKNOWN
    style = "dim" if word in (DISCOVERY_UNKNOWN, "not-discovered") else ""
    label = safe_markup(_pad("discovery", _DISCOVERY_LABEL_COLS))
    head = f"[dim]{label}[/] "
    head += f"[{style}]{safe_markup(word)}[/]" if style else safe_markup(word)
    head += _source_markup(word, source)
    lines = [head]
    indent = " " * (_DISCOVERY_LABEL_COLS + _GAP)

    text = strip_tags(detail)
    if text:
        lines.append(f"[dim]{indent}{safe_markup(fit_cell(text, room))}[/]")

    citation = strip_tags(source_tx)
    if citation:
        shown = fit_cell(citation, max(room - len(CITATION_LABEL) - 1, 0))
        lines.append(
            f"[dim]{indent}{CITATION_LABEL} [/]{safe_markup(shown)}"
        )
    elif word == "adopted":
        # The row the two-key split exists to make sayable. Warning colour,
        # in the position a citation would have occupied, so it reads as an
        # absence rather than as one more dim note.
        lines.append(
            f"[yellow]{indent}⚠ {safe_markup(fit_cell(UNAUDITABLE_LINE, room))}[/]"
        )
    return lines


class SurfPool4Hatches(Vertical):
    """Discovery, the four addresses, and every owner-held lever.

    Read-only (CLAUDE.md hard constraint 1): see the module docstring.
    """

    DEFAULT_CSS = """
    SurfPool4Hatches {
        height: auto;
    }
    SurfPool4Hatches > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    #: ``> Static``'s own ``padding: 0 1`` eats one column on each side of the
    #: *child*'s content box, so the budget a fit decision compares against is
    #: ``self.size.width`` minus these two columns, never ``self.size.width``
    #: itself. ``SurfBurnkeepers._TITLE_PADDING_COLS`` records the identical
    #: mistake being made and fixed on the panel directly above this one in
    #: the launchpad rail: comparing against the unpadded container width
    #: accepts a tier two columns too wide for the padded box and hands the
    #: overflow to CSS to clip in silence.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw payload, not formatted lines, so a resize re-lays it out.
        self._payload: dict = {}
        self._widen = False

    def compose(self) -> ComposeResult:
        yield Static(TITLE, id="surf-pool4-hatches-body")

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        pool4_hatches=None,
        pool4_network=None,
        pool4_discovery_state=None,
        pool4_discovery_detail=None,
        pool4_discovery_source_tx=None,
        pool4_discovery_source=None,
        pool4_hook_addr=None,
        pool4_token_addr=None,
        pool4_vault_addr=None,
        pool4_distributor_addr=None,
        pool4_reward_path=None,
        pool4_dripper_addr=None,
        pool4_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel.

        Every keyword is spelled with its full ``pool4_`` contract prefix,
        deliberately (contract §0.1): the launchpad panels take ``as_of_hhmm``
        short via ``_PREFIXED_KWARG_ALIASES``, and a second body whose panels
        also took the short name would make one kwarg name stand for two
        different contract keys, at which point the alias stops proving
        anything. ``**_kwargs`` is mandatory -- the screen splats the whole
        payload and a future key must not raise.
        """
        self._payload = {
            "rows": pool4_hatches,
            "network": pool4_network,
            "discovery_state": pool4_discovery_state,
            "discovery_detail": pool4_discovery_detail,
            # Kept beside the verdict, never merged into it: the detail is a
            # sentence, this is a pointer to a credential, and a reader must
            # be able to tell them apart (surf_models.Pool4Discovery).
            "discovery_source_tx": pool4_discovery_source_tx,
            "discovery_source": pool4_discovery_source,
            "reward_path": pool4_reward_path,
            "addrs": {
                "pool4_hook_addr": pool4_hook_addr,
                "pool4_token_addr": pool4_token_addr,
                "pool4_vault_addr": pool4_vault_addr,
                "pool4_distributor_addr": pool4_distributor_addr,
                "pool4_dripper_addr": pool4_dripper_addr,
            },
            "as_of": pool4_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        """Real rendered columns inside the child ``Static``'s padded box."""
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``HATCHES · SEPOLIA``, with the widen marker appended when the
        panel had to shed a column -- see ``_pool4.title_text``.
        """
        return title_text(
            TITLE, self._payload.get("network"), self._widen, self._text_budget()
        )

    def _is_blank(self) -> bool:
        """True when nothing at all has been read -- the whole-panel
        unavailable state, as opposed to a field-by-field one.
        """
        payload = self._payload
        if payload.get("rows") is not None:
            return False
        if payload.get("discovery_state") is not None:
            return False
        return not any(payload.get("addrs", {}).values())

    def _content_lines(self, tier: str, room: int) -> list[Text]:
        payload = self._payload
        markup: list[str] = []
        markup.extend(
            _discovery_markup(
                payload.get("discovery_state"),
                payload.get("discovery_detail"),
                payload.get("discovery_source_tx"),
                payload.get("discovery_source"),
                room,
            )
        )
        # No blank separator here, and none before the lever list below.
        #
        # WP8 needed two rows back off this panel to keep the body's height
        # pin at 44 rather than 46, and 44 matters: it is already the tallest
        # requirement in the repo and W7 records that nobody has ever measured
        # whether a real laptop clears it, so 46 spends more of a margin
        # nobody has confirmed exists.
        #
        # **The two rows came out of whitespace, not out of the lever list.**
        # The producer emits exactly twelve levers and every one is a distinct
        # trust surface -- the vault's owner/paused/rescue, the dripper's
        # owner/rewards, the distributor's owner/rewards, the hook's
        # owner/market/rebalance/burn sink, and bonding's deployed. Capping the
        # list at ten would have dropped the last two, which are the two that
        # changed most recently: the burn sink moved from `0x…dEaD` to the
        # BurnExecutor on mainnet, and bonding went live taking 40% of the
        # reward share. Hiding a trust surface to save a row inverts what this
        # panel is for.
        #
        # A separator earns its row between two blocks that look alike. These
        # do not: the address block is `label 0x…` and the lever list is a
        # four-column grid, and the blank line after the title still gives the
        # panel its heading room (`SurfBurnPipeline`'s note on the same idiom).
        addrs = payload.get("addrs", {})
        for label, key in ADDRESS_LABELS:
            note = (
                _reward_path_markup(payload.get("reward_path"))
                if key == "pool4_distributor_addr" else ""
            )
            markup.append(_address_markup(label, addrs.get(key), note))

        rows_payload = payload.get("rows")
        if rows_payload is None:
            markup.append(f"[yellow]⚠ {UNAVAILABLE_LINE}[/]")
        else:
            try:
                rows = list(rows_payload)[:MAX_ROWS]
            except TypeError:
                rows = []
            rendered = [
                line
                for line in (_hatch_row_markup(row, tier) for row in rows)
                if line is not None
            ]
            if rendered:
                markup.extend(rendered)
            else:
                # No lever list at all is a content state, not a "no room"
                # one -- say so plainly rather than leave a blank block.
                markup.append("[dim]no levers reported[/]")

        as_of = payload.get("as_of")
        if as_of:
            markup.append(f"[dim]as of {safe_markup(strip_tags(as_of))}[/]")

        return [t for t in (parse_line(m) for m in markup) if t is not None]

    def _render_view(self) -> None:
        try:
            body = self.query_one("#surf-pool4-hatches-body", Static)
        except Exception:  # not composed yet
            return

        if not self._payload:
            self._widen = False
            body.update(Text(self._title_text(), style="dim"))
            return

        if self._is_blank():
            self._widen = False
            lines = [
                Text(self._title_text(), style="dim"),
                Text(""),
                Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"),
            ]
            body.update(join_lines(lines))
            return

        # Measure the tier that was actually built, rather than comparing the
        # budget against a constant: a data-dependent line (a long discovery
        # detail, an unusually wide state word) can exceed FULL_WIDTH, and a
        # marker keyed off `budget < FULL_WIDTH` would stay dark while that
        # line was being clipped by CSS in silence. Measured this way the
        # marker means what it says at every width and for every payload.
        budget = self._text_budget()
        indent = _DISCOVERY_LABEL_COLS + _GAP
        # ``budget == 0`` means "not laid out yet"; the full tier's own width
        # keeps the pre-layout frame sensible and ``on_resize`` re-renders with
        # the real number the moment there is one.
        room = max(budget - indent, 1) if budget else FULL_WIDTH - indent
        # The discovery block is fitted to the panel, so it never drives the
        # tier and never lights the marker: the detail is a one-line summary
        # whose truncation announces itself in its own `…`, and the citation --
        # the only part a reader can check anything against -- has its own line
        # and is never crowded out by it. `‹ widen` stays what it is on this
        # panel: a whole column of the hatch grid was shed.
        content = self._content_lines("full", room)
        if budget and widest_line(content) > budget:
            self._widen = True
            content = self._content_lines("compact", room)
        else:
            self._widen = False

        # No blank row under the title. It was there on ``SurfBurnPipeline``'s
        # precedent -- "the rail's panels sat flush against their own headings
        # and read as one block of text" -- and that argument holds for a panel
        # whose body is prose. This one's body is a label/value grid in a dim-
        # labelled column, which already separates itself from a dim title, so
        # the row was buying less here than it costs: the pool4 body's height
        # pin is the tallest requirement in the repo and W7 records that nobody
        # has ever measured whether a real laptop clears it.
        lines = [Text(self._title_text(), style="dim"), *content]
        body.update(join_lines(lines))
