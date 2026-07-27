"""Executable guards for every stated FWA correctness rule (WP-18).

Waves 1-5 *honoured* the eleven correctness rules of ``docs/fwa_PRD.md`` §7, the
six suppressions of §13, and a handful of extra rules the build itself earned.
Honouring a rule is not the same as protecting it. This module exists so that
none of them can be un-honoured later, by someone who never read the
conversation in which they were established.

Every guard names the rule it enforces in its failure message. If one of these
goes red, the message alone should be enough to decide whether the code is
wrong or the rule has genuinely changed.

Two conventions, both load-bearing
----------------------------------

**Static scans run over code, not prose.** :func:`_code_only` blanks docstrings
and comments (preserving line numbers, so failures point at real lines) before
any pattern is applied. Almost every rule below is *explained at length* in a
docstring somewhere in the FWA modules -- ``weightedBackingTotal is never
TVL``, ``eth.llamarpc.com is banned``, ``sqrt(backing) is the stale comment``.
A naive grep would flag all of them. Prose must stay free to name exactly what
the code may not do; that is how the next person learns the rule.

**Guards must bite.** Every scan here was verified by mutating the shipped code
to violate its rule and confirming the guard turned red, then reverting. A
guard that can only pass is worse than no guard: it advertises a protection
that is not there.

What cannot be guarded mechanically
-----------------------------------

WP-20 reviewed the three gaps WP-18 disclosed here and closed two of them by
making the guard *closed-world*: pin the inventory, so growth is what turns the
test red. That does not make either rule fully mechanical, but it removes the
silence, which was the actual problem -- both gaps were of the form "a new X
slips past until someone remembers to add it here", and an inventory is what
stops depending on remembering.

* **Rule 6 (read every parameter live).** A scan can prove the *documented*
  values are absent as literals (crown tithe 500) and that live values are
  threaded as parameters. It cannot prove a future getter is read live rather
  than defaulted -- only that today's are. **Closed-world half (WP-20):** the
  set of ``DEFAULT_*`` protocol fallbacks in ``analytics/fwa_ev.py`` is pinned
  and no other FWA module may declare one, so a new parameter given a hardcoded
  default cannot arrive quietly. *Residue:* that the new default is genuinely
  displaced by a live read is still review.
* **Rule 8 (backing is mutable).** Staleness is a temporal property. The guards
  below prove the machinery exists (``BackingUpdated`` is decoded, positions
  are frozen, sweeps are block-pinned and reported with a block number) but not
  that a live deployment invalidates promptly. **This one WP-20 left alone** --
  proving prompt invalidation needs a live chain and a clock, which is a
  monitoring job, not a test. Nothing cheap would bite.
* **§13 "no floor-dependent figure without its coverage".** Guarded for the one
  surface that renders it (:class:`FWAHeroMetrics`, PRD §3's flagship) by
  driving the real widget. **Closed-world half (WP-20):**
  :func:`test_the_floor_dependent_surface_inventory_is_closed` pins *which*
  surfaces carry a floor-derived field at all, so a third one is red on arrival
  and must declare whether it uses the coverage badge or per-row provenance.
  *Residue:* a floor-derived quantity under an unrelated name is still invisible
  to the pattern -- ``eth_per_odds_point`` is inventoried because a human put it
  there.

And one gap WP-20 added a guard for, having found three live instances of it:

* **A fixture the product cannot emit.** Three work packages independently
  hand-wrote widget payloads carrying values the shipped code cannot produce --
  signal colours outside ``SIGNAL_COLORS``, an indicator that is not ``●``, and
  four EV kwargs under names ``FWAHeroMetrics`` does not accept (silently eaten
  by ``**_kwargs``). Every one passed green while measuring itself. See
  :func:`test_no_named_fixture_carries_a_field_the_product_cannot_emit`.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import fwa_ev, fwa_signals as sig
from maxpane_dashboard.data import fwa_client, fwa_enums, fwa_logs, fwa_market
from maxpane_dashboard.data.fwa_models import (
    FWA_DATA_KEYS,
    FWA_WIDGET_SIGNATURES,
    CollectionOdds,
    Crown,
    Position,
    PullEV,
)

_REPO = Path(__file__).resolve().parents[1]
_PKG = _REPO / "maxpane_dashboard"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fwa"


# ---------------------------------------------------------------------------
# Source access
# ---------------------------------------------------------------------------


def _blank(match: re.Match) -> str:
    """Replace a match with spaces, keeping every newline in place."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _code_only(source: str) -> str:
    """Source with docstrings and comments blanked, line numbers preserved.

    The pattern WP-5 established (``tests/analytics/test_fwa_signals.py``),
    generalised across the codebase. Blanking rather than deleting means a
    failure message can quote a real line number.
    """
    source = re.sub(r'(?s)""".*?"""', _blank, source)
    source = re.sub(r"(?s)'''.*?'''", _blank, source)
    return re.sub(r"#[^\n]*", _blank, source)


def _fwa_module_paths() -> tuple[Path, ...]:
    """Every shipped FWA Python module."""
    paths = sorted(_PKG.glob("data/fwa_*.py"))
    paths += sorted(_PKG.glob("analytics/fwa_*.py"))
    paths += sorted(_PKG.glob("widgets/fwa/*.py"))
    paths += [_PKG / "screens" / "fwa.py"]
    return tuple(p for p in paths if p.is_file())


FWA_MODULES: tuple[Path, ...] = _fwa_module_paths()

#: Modules whose entire job is presentation. Anything a user reads comes from
#: one of these (or from a signal built in ``analytics/fwa_signals.py``).
FWA_RENDER_MODULES: tuple[Path, ...] = tuple(
    p
    for p in FWA_MODULES
    if p.parent.name == "fwa" or p.name == "fwa.py" or p.name == "fwa_signals.py"
)


def _sources() -> dict[Path, str]:
    return {p: _code_only(p.read_text(encoding="utf-8")) for p in FWA_MODULES}


def _rel(path: Path) -> str:
    return str(path.relative_to(_REPO))


def _scan(pattern: str, paths=None, flags: int = 0) -> list[str]:
    """Every ``path:line: text`` hit of *pattern* in code (not prose)."""
    hits: list[str] = []
    for path in paths if paths is not None else FWA_MODULES:
        code = _code_only(path.read_text(encoding="utf-8"))
        lines = code.split("\n")
        for match in re.finditer(pattern, code, flags):
            lineno = code[: match.start()].count("\n") + 1
            hits.append(f"{_rel(path)}:{lineno}: {lines[lineno - 1].strip()}")
    return hits


def _string_literals(path: Path) -> list[str]:
    """Every string constant in a module, f-string fragments included.

    Parsed rather than grepped so an f-string's literal segments are visible
    and a docstring is not: ``ast.get_docstring`` targets are skipped, which
    keeps the "prose may name what code may not do" rule intact.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                out.append(node.value)
    return out


def _row_keys() -> dict[str, tuple[str, ...]]:
    """``FWA_ROW_KEYS`` — the vocabulary of the ``list[dict]`` payloads."""
    from maxpane_dashboard.data.fwa_models import FWA_ROW_KEYS

    return {k: tuple(v) for k, v in FWA_ROW_KEYS.items()}


def _fwa_test_files() -> tuple[Path, ...]:
    """Every FWA test module except this one.

    This file is excluded on purpose: it *names* the constructs it forbids, and
    a scan that included itself could only ever be satisfied by obfuscation.
    """
    here = Path(__file__).resolve()
    return tuple(
        p
        for p in sorted(here.parent.rglob("*.py"))
        if "fwa" in p.name and p.resolve() != here
    )


def _render_strings() -> list[tuple[str, str]]:
    """``(module, literal)`` for every string a render module can emit."""
    out: list[tuple[str, str]] = []
    for path in FWA_RENDER_MODULES:
        for text in _string_literals(path):
            out.append((_rel(path), text))
    return out


# ---------------------------------------------------------------------------
# Pinned on-chain facts, straight from the vendored fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pinned() -> dict:
    """``pinned_aggregates.json`` -> ``{block: expected_decoded}``."""
    import json

    raw = json.loads((_FIXTURES / "pinned_aggregates.json").read_text(encoding="utf-8"))
    return {int(k): v["expected_decoded"] for k, v in raw["blocks"].items()}


@pytest.fixture(scope="module")
def hole_trap() -> dict:
    import json

    raw = json.loads((_FIXTURES / "aggregate3_slots.json").read_text(encoding="utf-8"))
    return raw["free_list_hole_trap"]


@pytest.fixture(scope="module")
def listing_fixture() -> dict:
    import json

    return json.loads((_FIXTURES / "listings_56508.json").read_text(encoding="utf-8"))


# ===========================================================================
# PRD §7 — the eleven correctness rules
# ===========================================================================


def test_rule_1_weight_is_inverse_to_backing():
    """PRD §7 rule 1: ``weight = 1e36 / backing``, never proportional.

    Two guards, because the constant alone is not the rule. A proportional
    implementation could keep ``INVERSE_WEIGHT_NUMERATOR`` and still be wrong,
    so monotonicity is asserted directly: more ETH must mean *less* weight.
    """
    assert fwa_ev.INVERSE_WEIGHT_NUMERATOR == 10**36, (
        "PRD §7 rule 1: INVERSE_WEIGHT_NUMERATOR must stay 1e36"
    )

    tenth, one, ten = 10**17, 10**18, 10**19
    weights = [fwa_ev.inverse_weight(b) for b in (tenth, one, ten)]
    assert weights[0] > weights[1] > weights[2], (
        "PRD §7 rule 1: weight is INVERSE to backing — a bigger position must be "
        f"drawn LESS often, got weights {weights} for backings [0.1, 1, 10] ETH"
    )
    assert fwa_ev.inverse_weight(one) == 10**18
    # The largest live position: 221 ETH -> 4524886877828054 (findings §6).
    assert fwa_ev.inverse_weight(221_000_000_000_000_000_000) == 4_524_886_877_828_054

    # Floor division, exactly as the contract does it — not float, not rounded.
    assert fwa_ev.inverse_weight(3 * 10**18) == 10**36 // (3 * 10**18)


def test_rule_2_acquisition_fee_is_two_floor_divisions(pinned):
    """PRD §7 rule 2: two sequential floor divisions, bit-exact at both blocks.

    The collapsed one-step form agrees at 25612655 and disagrees by one wei at
    25612701, which is exactly why a single pinned sample cannot catch the
    collapse. Both blocks are asserted, and the disagreement is asserted too so
    this test fails loudly if the fixtures ever stop discriminating.
    """
    assert set(pinned) == {25_612_655, 25_612_701}, "both pinned blocks required"

    disagreements = 0
    for block, agg in pinned.items():
        wbt, tw = agg["weightedBackingTotal"], agg["totalWeight"]
        got = fwa_ev.acquisition_fee_wei(wbt, tw, fwa_ev.DEFAULT_SURCHARGE_BPS)
        assert got == agg["acquisitionFee"], (
            f"PRD §7 rule 2: acquisitionFee must reproduce BIT-EXACTLY at pinned "
            f"block {block}: got {got}, chain says {agg['acquisitionFee']} "
            f"(off by {got - agg['acquisitionFee']} wei)"
        )
        collapsed = wbt * (fwa_ev.BPS + fwa_ev.DEFAULT_SURCHARGE_BPS) // (tw * fwa_ev.BPS)
        disagreements += collapsed != got

    assert disagreements == 1, (
        "PRD §7 rule 2: the pinned blocks must include one where the collapsed "
        "single-division form disagrees, otherwise this guard cannot detect a "
        "collapse. Expected exactly 1 disagreement, saw "
        f"{disagreements}"
    )

    # And the intermediate EV is itself a floor division, kept separate.
    ev = fwa_ev.expected_value_wei(7, 2)
    assert ev == 3, "PRD §7 rule 2: expected_value_wei must floor, not round"


def test_rule_3_settlement_discount_bps_is_the_purchaser_payout():
    """PRD §7 rule 3: 8500 is the purchaser *payout* (85%), not a 15% discount."""
    one_eth = 10**18
    payout = fwa_ev.sellback_payout_wei(one_eth, 8_500)
    assert payout == 850_000_000_000_000_000, (
        "PRD §7 rule 3: 8500 bps is the purchaser PAYOUT — 1 ETH of backing must "
        f"pay back 0.85 ETH, got {payout / 10**18} ETH. Returning 0.15 means the "
        "naming trap was inverted."
    )
    assert fwa_ev.DEFAULT_PURCHASER_PAYOUT_BPS == 8_500

    # …and it is never *called* a discount where a user can read it.
    offenders = [
        (mod, text)
        for mod, text in _render_strings()
        if re.search(r"discount", text, re.IGNORECASE)
    ]
    assert not offenders, (
        "PRD §7 rule 3: 8500 is a payout rate. No user-facing string may call it "
        f"a discount: {offenders}"
    )


def test_rule_4_weighted_backing_total_is_never_tvl_and_never_reaches_a_widget():
    """PRD §7 rule 4: ``weightedBackingTotal`` is neither wei nor ETH nor TVL.

    It is ``Σ(weight × backing) ≈ count × 1e36``, so its leading digits look
    like a count of ETH. The structural defence is that it never crosses the
    flat-dict boundary at all — a widget cannot mislabel a value it never
    receives.
    """
    assert "weighted_backing_total" not in FWA_DATA_KEYS, (
        "PRD §7 rule 4: weighted_backing_total must stay OUT of FWA_DATA_KEYS — "
        "it is not wei, not ETH, and not TVL. Value held is core_balance_eth."
    )
    for widget, kwargs in FWA_WIDGET_SIGNATURES.items():
        assert "weighted_backing_total" not in kwargs, (
            f"PRD §7 rule 4: {widget} must not accept weighted_backing_total"
        )

    # No render module even names it — the only legitimate consumers are the
    # sweep invariant check and the snapshot model.
    hits = _scan(r"weighted_backing_total|weightedBackingTotal", FWA_RENDER_MODULES)
    assert not hits, (
        "PRD §7 rule 4: weightedBackingTotal must not reach a render module: " f"{hits}"
    )

    # Nowhere in FWA code is it put next to an ETH/TVL label.
    offenders = [
        (mod, text)
        for mod, text in _render_strings()
        if re.search(r"\bTVL\b", text, re.IGNORECASE)
    ]
    assert not offenders, (
        f"PRD §7 rule 4: no FWA render string may say TVL: {offenders}"
    )

    # The one value-held source is the core balance, and it is in the contract.
    assert "core_balance_eth" in FWA_DATA_KEYS


def test_rule_5_fees_split_equally_and_no_sqrt_weighting_creeps_in():
    """PRD §7 rule 5: ``feeShare == 1`` per position — an EQUAL split.

    ``feeShareTotal() == activeListingCount() == 5928`` live. The FWA source
    carries a stale struct comment claiming ``sqrt(backing)``, and the rewards
    ABI really does expose ``sqrtBackingTotal()`` / ``sqrtBacking`` — so the
    materials to "fix" the code into being wrong are sitting right there in
    ``abis/fwa/``. This guard exists to stop that fix.
    """
    # Equal split: every position gets the same credit regardless of backing.
    assert fwa_ev.per_position_credit(1_000, 4) == 250
    assert fwa_ev.per_position_credit(1_001, 4) == 250, (
        "PRD §7 rule 5: per-position credit floors; credited must stay <= collected"
    )
    assert fwa_ev.per_position_credit(1_000, 0) == 0

    # No sqrt weighting anywhere it could influence a number. The client may
    # *read* ``sqrtBackingTotal()`` as an observation (it sits in the hot view
    # table); the moment it enters the maths or reaches a widget, rule 5 is
    # broken.
    analytics = tuple(_PKG.glob("analytics/fwa_*.py"))
    hits = _scan(r"sqrt", analytics + FWA_RENDER_MODULES, re.IGNORECASE)
    assert not hits, (
        "PRD §7 rule 5: fees split EQUALLY (feeShare == 1 per position, verified "
        "live feeShareTotal() == activeListingCount() == 5928). The sqrt(backing) "
        "comment in the source struct is STALE and abis/fwa/ really does expose "
        f"sqrtBackingTotal() — do not wire it into the maths: {hits}"
    )
    assert not [k for k in FWA_DATA_KEYS if "sqrt" in k.lower()], (
        "PRD §7 rule 5: no sqrt-derived value may cross the flat-dict boundary"
    )
    hits = _scan(r"sqrt\w*\s*(?:\*|/|//|\+|-)|(?:\*|/|//|\+|-)\s*sqrt", FWA_MODULES)
    assert not hits, (
        f"PRD §7 rule 5: a sqrt value entered an arithmetic expression: {hits}"
    )

    # The invariant check treats a feeShareTotal divergence as a mismatch.
    report = fwa_client.check_sweep_invariants(
        [],
        expected_count=0,
        total_weight_onchain=0,
        weighted_backing_total_onchain=0,
        acquisition_fee_onchain=0,
        fee_share_total_onchain=7,
    )
    assert not report["invariants_ok"], (
        "PRD §7 rule 5: feeShareTotal() != activeListingCount() must fail the "
        "sweep invariant — an unequal split is a defect, not a state"
    )
    assert any("feeShareTotal" in m for m in report["mismatches"])


def test_rule_6_no_documented_parameter_is_hardcoded_as_truth():
    """PRD §7 rule 6: every protocol parameter is read live.

    The documented crown tithe is 5% (500 bps); live it is 1% (100 bps,
    ``ConfigSet key=15``, block 25592190). A ``500`` literal anywhere in the
    FWA code is therefore either that stale doc value or something that will be
    mistaken for it.

    Mechanically incomplete by nature: this pins the divergences known today. A
    *new* getter given a hardcoded default would pass until it is added here.
    """
    # ``500`` is fine as a batch size or an HTTP status; it is not fine
    # anywhere near a bps/tithe/share/crown identifier.
    param_line = r"^.*(?:bps|BPS|tithe|Tithe|crown|Crown|share|Share|fee|Fee).*$"
    for path in FWA_MODULES:
        code = _code_only(path.read_text(encoding="utf-8"))
        for match in re.finditer(param_line, code, re.MULTILINE):
            line = match.group(0)
            if re.search(r"(?<![\d_.])500(?![\d_])", line):
                lineno = code[: match.start()].count("\n") + 1
                pytest.fail(
                    "PRD §7 rule 6: the crown tithe is documented at 500 bps and "
                    "live at 100 (ConfigSet key=15, block 25592190). A 500 next "
                    "to a parameter name is either the stale doc value or will be "
                    f"mistaken for it — read it live. {_rel(path)}:{lineno}: "
                    f"{line.strip()}"
                )

    # No module-level ``*_BPS`` constant may be frozen at a numeric doc value.
    # ``DEFAULT_*_BPS`` names are exempt by construction: the ``DEFAULT_``
    # prefix is the promise that they are fallbacks, and the signature
    # assertions below prove the live value can displace them.
    hits = [
        h
        for h in _scan(
            r"^(?!_?DEFAULT_)[A-Z_]*BPS[A-Z_]*\s*[:=]\s*\d",
            FWA_MODULES,
            re.MULTILINE,
        )
    ]
    assert not hits, (
        "PRD §7 rule 6: a protocol parameter frozen as a module constant will "
        f"drift the way the crown tithe did (docs 500, live 100): {hits}"
    )

    # Defaults exist only as fallbacks, and every one is overridable.
    for func in (fwa_ev.acquisition_fee_wei, fwa_ev.surcharge_wei, fwa_ev.pull_ev_band):
        params = inspect.signature(func).parameters
        assert "surcharge_bps" in params, (
            f"PRD §7 rule 6: {func.__name__} must take surcharge_bps as a "
            "parameter so the live value can be threaded through"
        )
        assert params["surcharge_bps"].default is not inspect.Parameter.empty

    for func in (fwa_ev.sellback_payout_wei, fwa_ev.jackpot_ratio, fwa_ev.pull_ev_band):
        names = set(inspect.signature(func).parameters)
        assert names & {"payout_bps", "purchaser_payout_bps"}, (
            f"PRD §7 rule 6: {func.__name__} must accept the live payout bps"
        )

    # The model default is a neutral zero, not the documented 500.
    crown = Crown(listing_id=0)
    assert crown.share_bps == 0, (
        "PRD §7 rule 6: Crown.share_bps must default to 0 (unknown), never to the "
        "documented 500 or the currently-live 100"
    )
    assert crown.threshold_bps == 0
    assert crown.vacant is True

    # -- closed-world half (WP-20) -------------------------------------------
    # The open end of this rule was that a *new* parameter given a hardcoded
    # default slips past a scan that only knows today's parameters. It cannot
    # slip past an inventory: the set of protocol-parameter fallbacks is pinned
    # here, so adding one turns this red and forces the same conversation the
    # crown tithe forced (documented 500, live 100). This does not prove a new
    # getter is read live — nothing static can — but it removes the silence.
    declared = {
        name
        for name in dir(fwa_ev)
        if name.startswith("DEFAULT_") and isinstance(getattr(fwa_ev, name), int)
    }
    assert declared == {
        "DEFAULT_SURCHARGE_BPS",
        "DEFAULT_PURCHASER_PAYOUT_BPS",
        "DEFAULT_TOP_THRESHOLD_BPS",
    }, (
        "PRD §7 rule 6: the set of protocol-parameter FALLBACKS in "
        f"analytics/fwa_ev.py changed to {sorted(declared)}. Every one of these "
        "is a documented value standing in for a live read, and the crown tithe "
        "is the proof that documented and live diverge. A new entry needs: a "
        "live read that displaces it, a keyword parameter so a caller can thread "
        "that read through, and an assertion above. Removing one is fine — "
        "update this set."
    )
    # …and no *other* FWA module may grow one, which is how a default escapes
    # review: it is easy to argue about a constant in the maths module and easy
    # to miss one that appeared in a client or a widget.
    hits = _scan(
        r"^DEFAULT_[A-Z_]*(?:BPS|SHARE|TITHE|FEE|THRESHOLD|GAP)\b\s*[:=]",
        tuple(p for p in FWA_MODULES if p.name != "fwa_ev.py"),
        re.MULTILINE,
    )
    assert not hits, (
        "PRD §7 rule 6: protocol-parameter fallbacks belong in "
        f"analytics/fwa_ev.py where they are inventoried, not here: {hits}"
    )


def test_rule_7_allowlist_is_derived_from_collection_whitelist_set_logs():
    """PRD §7 rule 7: the registry comes from ``CollectionWhitelistSet`` on core.

    51 collections live, not the 16 in the docs, and the event is emitted by
    FWA **core** — FWAWhitelist only carries the write side. A checked-in
    address list of any size is a failure; the guard fires well below 16.
    """
    assert "CollectionWhitelistSet" in fwa_logs.LOG_EVENTS
    assert fwa_logs.FWA_CORE_ADDRESS.lower() == fwa_client.FWA_CORE.lower(), (
        "PRD §7 rule 7: CollectionWhitelistSet is read from FWA core, so the log "
        "module's address must be core's"
    )

    # collection_registry is a pure fold over logs — no seed, no baked-in list.
    assert fwa_logs.collection_registry([]) == {}, (
        "PRD §7 rule 7: with no logs the registry must be EMPTY. A non-empty "
        "result means an allowlist was hardcoded instead of derived."
    )
    derived = fwa_logs.collection_registry(
        [
            {"collection": "0x" + "aa" * 20, "allowed": True, "block_number": 1, "ts": 1},
            {"collection": "0x" + "bb" * 20, "allowed": True, "block_number": 2, "ts": 2},
            {"collection": "0x" + "aa" * 20, "allowed": False, "block_number": 3, "ts": 3},
        ]
    )
    assert len(derived) == 2
    assert derived["0x" + "aa" * 20]["allowed"] is False, (
        "PRD §7 rule 7: a de-listing must show as allowed=False, not vanish"
    )

    # No module carries a bare block of collection addresses. The seven FWA
    # protocol contracts plus Multicall3 and the token are legitimately pinned;
    # a *collection* list starts at 16 (the docs' stale count) and is 51 live,
    # so the ceiling sits well clear of both.
    for path in FWA_MODULES:
        code = _code_only(path.read_text(encoding="utf-8"))
        addresses = set(re.findall(r'"(0x[0-9a-fA-F]{40})"', code))
        assert len(addresses) <= 10, (
            f"PRD §7 rule 7: {_rel(path)} carries {len(addresses)} hardcoded "
            "addresses. The protocol contracts are pinned; a COLLECTION list is "
            "not — it must be derived from CollectionWhitelistSet logs (51 live, "
            f"not the docs' 16): {sorted(addresses)}"
        )
        # …and never as one sequence literal, which is what an allowlist is.
        for block in re.findall(r"[\[\(\{](?:[^\[\]\(\)\{\}]|\n)*[\]\)\}]", code):
            found = re.findall(r'"0x[0-9a-fA-F]{40}"', block)
            assert len(found) < 6, (
                f"PRD §7 rule 7: {_rel(path)} contains a {len(found)}-address "
                "sequence literal — that shape is an allowlist, and the "
                "allowlist is derived from logs"
            )


def test_rule_8_backing_is_mutable_so_cached_positions_go_stale():
    """PRD §7 rule 8: ``updateBacking`` mutates backing; caches go stale.

    Guarded structurally: the invalidation event is decoded, positions are
    immutable so a stale row cannot be silently patched in place, and every
    sweep carries the block it belongs to. Actual staleness is temporal and
    stays a review item.
    """
    assert "BackingUpdated" in fwa_logs.LOG_EVENTS, (
        "PRD §7 rule 8: BackingUpdated is what invalidates a cached sweep — it "
        "must stay in LOG_EVENTS"
    )
    assert "BackingUpdated" in fwa_logs.DECODERS

    pos = Position(listing_id=1, slot=1, collection="0x" + "11" * 20, token_id=1,
                   backing_wei=10**18, weight=10**18, depositor="0x" + "22" * 20)
    with pytest.raises(Exception):
        pos.backing_wei = 2 * 10**18  # type: ignore[misc]

    # A sweep result is only meaningful with the block it was taken at.
    from maxpane_dashboard.data.fwa_models import FWASnapshot

    assert "block_number" in FWASnapshot.model_fields
    assert "odds_as_of_block" in FWA_DATA_KEYS, (
        "PRD §7 rule 8: the odds board must publish the block its rows belong to"
    )
    assert "odds_stale" in FWA_DATA_KEYS


def test_rule_9_quotes_carry_an_explicit_gas_price_and_a_bounded_gas():
    """PRD §7 rule 9: quote with explicit ``gasPrice`` + bounded ``gas``.

    ``FWAVRFService.requestFee()`` reads ``tx.gasprice``. Without one the VRF
    leg reads 0, which is what made two research agents conclude the fee was
    waived. The bound and the price are both non-optional on this path.
    """
    params = inspect.signature(fwa_client.FWAClient.quote_acquisition_price).parameters
    assert params["gas_price_wei"].default is inspect.Parameter.empty, (
        "PRD §7 rule 9: gas_price_wei must be a REQUIRED argument of "
        "quote_acquisition_price — a default would let a caller quote at 0 and "
        "read the VRF fee as waived"
    )

    quote_src = _code_only(inspect.getsource(fwa_client.FWAClient.quote_acquisition_price))
    assert "gas=_QUOTE_GAS_BOUND" in quote_src.replace(" ", "").replace("\n", "") or (
        "gas=" in quote_src and "_QUOTE_GAS_BOUND" in quote_src
    ), "PRD §7 rule 9: the quote must send a bounded gas"
    assert "gas_price_wei=gas_price_wei" in quote_src.replace(" ", ""), (
        "PRD §7 rule 9: the quote must send an explicit gasPrice"
    )
    assert int(fwa_client._QUOTE_GAS_BOUND, 16) > 0

    # A negative price is a programming error; zero is allowed but must warn.
    import asyncio

    client = fwa_client.FWAClient.__new__(fwa_client.FWAClient)
    with pytest.raises(ValueError):
        asyncio.run(fwa_client.FWAClient.quote_acquisition_price(client, -1))

    # _eth_call only emits the keys it was given — no silent default.
    call_src = _code_only(inspect.getsource(fwa_client.FWAClient._eth_call))
    assert '"gasPrice"' in call_src and '"gas"' in call_src


def test_rule_10_dynamic_tuple_decode_is_pinned_to_raw_hex(listing_fixture):
    """PRD §7 rule 10: struct-array getters need raw-hex fixture assertions.

    The Talismans gotcha: a dynamic tuple decoded with a static-tuple layout
    produces plausible garbage. The only defence is decoding real return data
    and comparing every field against the values read off chain.
    """
    raw = listing_fixture["raw_return_data"]
    expected = listing_fixture["expected_decoded"]
    assert raw.startswith("0x") and len(raw) > 2, (
        "PRD §7 rule 10: the fixture must carry real raw return data — an "
        "expected-values block alone proves nothing about the decoder"
    )

    decoded = fwa_client.decode_listing(raw, 56_508)
    assert decoded is not None, (
        "PRD §7 rule 10: listings(id) raw return data must decode — a None here "
        "means the tuple layout drifted"
    )

    # Every field, by hand, against the values read off chain at block 25612655.
    assert decoded.collection.lower() == expected["collection"].lower()
    assert decoded.depositor.lower() == expected["depositor"].lower()
    assert decoded.token_id == expected["tokenId"]
    assert decoded.weight == expected["weight"]
    assert decoded.backing_wei == expected["value"]
    assert decoded.fee_share == expected["feeShare"]
    assert decoded.fee_debt == expected["feeDebt"]
    assert decoded.slot == expected["slot"]
    assert decoded.allocated_at == expected["allocatedAt"]
    assert decoded.status == expected["status"]
    assert decoded.allocatee is None, (
        "PRD §7 rule 10: the zero address must normalise to None — no widget may "
        "render 0x0000… as a purchaser"
    )

    # The struct's own invariants, from the same block.
    assert fwa_ev.inverse_weight(decoded.backing_wei) == decoded.weight, (
        "PRD §7 rule 10 + rule 1: the decoded weight must equal 1e36 // backing"
    )
    assert decoded.fee_share == 1, "PRD §7 rule 5: feeShare is 1 on every position"

    # A truncated tuple must degrade, not invent fields.
    assert fwa_client.decode_listing("0x", 1) is None
    assert fwa_client.decode_listing(raw[:60], 1) is None
    assert fwa_client.decode_listing("0x" + "00" * 32 * 11, 1) is None, (
        "PRD §7 rule 10: an all-zero struct is a dead slot, not a zero-backed "
        "position — 1e36 // 0 would explode and drag every aggregate"
    )


def test_rule_11_a_partial_sweep_is_a_defect_not_a_degraded_state(hole_trap):
    """PRD §7 rule 11: free-list slot holes — fail loudly, never render.

    The naive ``slot = 1..activeListingCount()`` scan at block 25612701 finds
    3,604 of 3,867 positions and lands a ``weightedBackingTotal`` short by
    almost exactly ``263e36``. The resulting acquisitionFee is wrong in the
    third significant figure and looks entirely plausible. This is the most
    dangerous failure mode the dashboard has, so the guard asserts both
    directions: the plausible-but-wrong sweep must fail, and the correct one
    must pass.
    """
    naive = hole_trap["naive_scan_slots_1_to_activeListingCount"]
    count = hole_trap["activeListingCount"]

    class _P:
        __slots__ = ("backing_wei", "weight")

        def __init__(self, backing_wei: int) -> None:
            self.backing_wei = backing_wei
            self.weight = fwa_ev.inverse_weight(backing_wei)

    # Recreate the shortfall without needing 3,867 real rows: hand the checker
    # a set whose recomputed aggregates are the naive scan's, against the
    # chain's correct ones.
    report = fwa_client.check_sweep_invariants(
        [],
        expected_count=count,
        total_weight_onchain=1,
        weighted_backing_total_onchain=naive["weightedBackingTotal_correct"],
        acquisition_fee_onchain=naive["acquisitionFee_correct"],
    )
    assert report["invariants_ok"] is False, (
        "PRD §7 rule 11: a sweep that misses free-list slots must report "
        "invariants_ok=False. A partial sweep is a DEFECT, not a degraded state."
    )
    assert any("count" in m for m in report["mismatches"])
    assert any("weightedBackingTotal" in m for m in report["mismatches"]), (
        "PRD §7 rule 11: the weightedBackingTotal shortfall must be named in the "
        f"mismatch list so the failure is self-explaining: {report['mismatches']}"
    )

    # The shortfall really is ids_missed x 1e36 — that is what makes it plausible.
    assert naive["weightedBackingTotal_shortfall_over_1e36"] == pytest.approx(
        naive["ids_missed"], abs=1.0
    )

    # A complete sweep passes.
    positions = [_P(10**18), _P(2 * 10**18)]
    backings = [p.backing_wei for p in positions]
    ok = fwa_client.check_sweep_invariants(
        positions,
        expected_count=2,
        total_weight_onchain=fwa_ev.total_weight(backings),
        weighted_backing_total_onchain=fwa_ev.weighted_backing_total(backings),
        acquisition_fee_onchain=fwa_ev.acquisition_fee_wei(
            fwa_ev.weighted_backing_total(backings), fwa_ev.total_weight(backings)
        ),
        fee_share_total_onchain=2,
    )
    assert ok["invariants_ok"] is True, ok["mismatches"]

    # And the sweep is block-pinned: the report and the snapshot carry a block,
    # and the multicall threads one through rather than defaulting to latest.
    sweep_src = _code_only(inspect.getsource(fwa_client.FWAClient._sweep_positions_inner))
    assert "block" in sweep_src, "PRD §7 rule 11: the sweep must pin a block"
    assert 'block="latest"' not in sweep_src.replace(" ", ""), (
        "PRD §7 rule 11: the sweep must never fall back to 'latest' — results "
        "merged across blocks are silently wrong"
    )


# ===========================================================================
# PRD §13 — the six suppressions
# ===========================================================================


def test_suppression_1_vrf_fee_is_never_asserted_to_be_zero_or_computed():
    """PRD §13: the VRF fee being 0 is an unset-gasPrice artifact, not a fact.

    The dashboard renders the leg the contract returned, or nothing. It never
    computes one from ``serviceGasEstimate × gasPrice × margin``, and it never
    prints a "free"/"waived"/"no VRF fee" claim.
    """
    offenders = [
        (mod, text)
        for mod, text in _render_strings()
        if re.search(r"\b(free pull|waived|no vrf fee|vrf fee: ?0\b)", text, re.IGNORECASE)
    ]
    assert not offenders, (
        "PRD §13: the VRF fee is NOT known to be zero — a zero reading is an "
        f"unset-gasPrice artifact. No string may present it as a fact: {offenders}"
    )

    hits = _scan(r"serviceGasEstimate|service_gas_estimate", FWA_MODULES)
    assert not hits, (
        "PRD §13: the VRF leg is taken from quoteAcquisitionPrice as returned, "
        f"never recomputed from a gas estimate: {hits}"
    )

    assert "vrf_fee_eth" in FWA_DATA_KEYS
    # quote_total is the returned tuple member, never a local sum.
    assert "quote_total_eth" in FWA_DATA_KEYS


def test_suppression_2_token_share_linearity_is_a_label_not_a_fact():
    """PRD §13: ``tokenShareBps(uint256)`` linearity is unconfirmed.

    The hot/cold ramp may be rendered as a *label*; the live value is read.
    Nothing may state the ramp is linear, and the ramp endpoints must stay
    overridable rather than being treated as measured truth.
    """
    offenders = [
        (mod, text)
        for mod, text in _render_strings()
        if re.search(r"linear|interpolat", text, re.IGNORECASE)
    ]
    assert not offenders, (
        "PRD §13: tokenShareBps linearity is UNCONFIRMED — it may not be stated "
        f"as a fact anywhere a user reads: {offenders}"
    )

    params = inspect.signature(fwa_ev.surcharge_ramp_share).parameters
    assert {"hot_gap", "cold_gap"} <= set(params), (
        "PRD §13: the ramp endpoints must be parameters (fallback labels), not "
        f"baked-in truth — signature is {tuple(params)}"
    )
    for name in ("hot_gap", "cold_gap"):
        assert params[name].default is not inspect.Parameter.empty
    assert "token_share_bps" in fwa_client.HOT_EXTRA_KEYS, (
        "PRD §13: tokenShareBps must be READ live, not modelled"
    )


def test_suppression_3_enum_names_are_recovered_not_guessed():
    """PRD §13: the ``ListingStatus`` / ``AcquisitionStatus`` enums were unread.

    They have since been recovered from verified source, so the suppression
    resolves into a different obligation: an *unrecognised* value must render
    as the raw number, never be coerced into a neighbouring name that happens
    to look plausible.
    """
    assert fwa_enums.listing_status_label(1) == "Active"
    assert fwa_enums.LISTING_STATUS_ACTIVE == 1

    for label_fn, table in (
        (fwa_enums.listing_status_label, fwa_enums.LISTING_STATUS),
        (fwa_enums.acquisition_status_label, fwa_enums.ACQUISITION_STATUS),
    ):
        unknown = max(table) + 1
        got = label_fn(unknown)
        assert got == f"status {unknown}", (
            "PRD §13: an enum value outside the recovered table means the "
            "contract was redeployed. The honest label is the raw number, never "
            f"a plausible guess — got {got!r}"
        )
        assert got not in table.values()

    # No hedging language leaks into the labels themselves.
    for table in (fwa_enums.LISTING_STATUS, fwa_enums.ACQUISITION_STATUS):
        for name in table.values():
            assert not re.search(r"guess|probably|unknown\?|\?$", name, re.IGNORECASE)


def test_suppression_4_no_fwaclaim_progress_reaches_the_ui():
    """PRD §13: FWAClaim holds 3.6M of a stated 200M — provenance unresolved.

    Until it is known whether those are genuine claims or an owner ``rescue``,
    no progress figure may be displayed.
    """
    offenders = [
        (mod, text)
        for mod, text in _render_strings()
        if re.search(r"claim progress|claimed|of 200,000,000|200,000,000", text, re.IGNORECASE)
    ]
    assert not offenders, (
        "PRD §13: FWAClaim progress is UNRESOLVED (genuine claims vs owner "
        f"rescue) and must not be displayed: {offenders}"
    )

    hits = _scan(r"200_000_000|200,000,000|3_600_000\b", FWA_MODULES)
    assert not hits, f"PRD §13: no FWAClaim supply literal in FWA code: {hits}"

    assert not [k for k in FWA_DATA_KEYS if "claim" in k.lower()], (
        "PRD §13: no claim-progress key may exist in the flat-dict contract"
    )


def test_suppression_5_no_500m_in_the_pool_claim():
    """PRD §13: whether 500M FWA sits "in the pool" is unverified.

    PoolManager is a singleton; placement was never confirmed. The claim must
    appear nowhere — neither as prose nor as a literal that could become one.
    """
    offenders = [
        (mod, text)
        for mod, text in _render_strings()
        if re.search(r"500\s*M\b|500,000,000|500 ?million", text, re.IGNORECASE)
    ]
    assert not offenders, (
        "PRD §13: 'about 500M FWA sits in the pool' is UNVERIFIED (PoolManager is "
        f"a singleton). It may not be claimed anywhere: {offenders}"
    )
    hits = _scan(r"500_000_000|500e6|5e8", FWA_MODULES)
    assert not hits, f"PRD §13: no 500M supply-placement literal: {hits}"


async def test_suppression_6_no_floor_dependent_figure_renders_without_coverage():
    """PRD §13 + §3: a floor-derived number always carries its coverage.

    Keyless floors cover ~22 of 38 collections and the two largest weight
    buckets are unpriced, so the EV band without its coverage badge is
    precision theatre. Driven through the real widget rather than grepped:
    the badge has to survive the hero card's four-line vertical budget, and a
    ``padding: 1 2`` regression would silently drop exactly that line.
    """
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    from maxpane_dashboard.widgets.fwa.fwa_hero_metrics import FWAHeroMetrics

    class _Harness(App):
        def compose(self) -> ComposeResult:
            yield FWAHeroMetrics()

    payloads = [
        {},
        dict.fromkeys(FWA_WIDGET_SIGNATURES["FWAHeroMetrics"]),
        {
            "pull_ev_best_eth": 0.0182,
            "pull_ev_lower_eth": -0.0431,
            "ev_available": True,
            "ev_collections_priced": 22,
            "ev_collections_total": 38,
            "ev_weight_priced_pct": 61.3,
            "ev_rebate_eth": 0.0009,
        },
        {
            "pull_ev_best_eth": 0.5,
            "pull_ev_lower_eth": 0.5,
            "ev_available": True,
            "ev_collections_priced": 38,
            "ev_collections_total": 38,
            "ev_weight_priced_pct": 100.0,
        },
    ]

    app = _Harness()
    # Wide enough that the badge is not ellipsised, short enough that the hero
    # card's vertical budget is the thing under test.
    async with app.run_test(size=(140, 12)):
        hero = app.query_one(FWAHeroMetrics)
        for payload in payloads:
            hero.update_data(**payload)
            await app.workers.wait_for_complete()
            box = hero.query_one("#fwa-hero-ev", Static)
            visual = box.visual
            text = getattr(visual, "plain", str(visual))

            strips = app.screen._compositor.render_strips()
            on_screen = "\n".join(
                "".join(seg.text for seg in strip) for strip in strips
            )

            assert re.search(r"[\d-]+\s*/\s*[\d-]+", text), (
                "PRD §3/§13: the PULL EV card must always carry its coverage "
                "badge (priced/total — dashes when unknown, but never absent). "
                f"Rendered: {text!r}"
            )
            assert "of weight priced" in text
            if payload.get("ev_available"):
                assert re.search(r"\d+\s*/\s*\d+", text), (
                    "PRD §3/§13: when an EV number is rendered its coverage must "
                    f"be a real count, not dashes. Rendered: {text!r}"
                )
            assert "of weight priced" in on_screen, (
                "PRD §3/§13: the coverage badge is present in the widget but not "
                "ON SCREEN — the hero card lost a line to padding. An EV number "
                "without its coverage is the one thing PRD §3 forbids outright."
            )


def test_the_floor_dependent_surface_inventory_is_closed():
    """§13's coverage rule, made closed-world (WP-20).

    The assertion above drives ``FWAHeroMetrics``, the one surface PRD §3 names.
    Its stated gap was that *a new widget rendering a floor-derived number would
    need its own assertion* — i.e. the guard was silent about growth, which is
    the only direction the risk comes from.

    So the inventory is pinned instead. Today exactly two surfaces carry a
    floor-derived figure, and each carries its own provenance next to it:

    * ``FWAHeroMetrics`` — the EV band, with the ``priced/total · weight%``
      coverage badge (driven for real above).
    * ``collection_odds`` rows — ``floor_eth`` and ``eth_per_odds_point``, with
      per-row ``floor_source`` and ``floor_note``. Row-level provenance is the
      row-level equivalent of the badge: every floor on screen says where it
      came from, and an unpriced one says so rather than reading 0.

    A third surface makes this red and has to declare which of the two shapes it
    is using. What this still cannot do is recognise a floor-derived quantity
    given an unrelated name — ``eth_per_odds_point`` is in the list because
    someone put it there, not because a scan inferred it. That residue is real
    and stays review.
    """
    floor_words = re.compile(r"floor|odds_point", re.IGNORECASE)

    carriers = {
        widget: sorted(k for k in kwargs if floor_words.search(k))
        for widget, kwargs in FWA_WIDGET_SIGNATURES.items()
    }
    carriers.update(
        {
            f"{row_group} rows": sorted(k for k in keys if floor_words.search(k))
            for row_group, keys in _row_keys().items()
        }
    )
    populated = {name: fields for name, fields in carriers.items() if fields}

    assert populated == {
        "collection_odds rows": [
            "eth_per_odds_point",
            "floor_eth",
            "floor_note",
            "floor_source",
        ],
    }, (
        "PRD §13: the set of surfaces carrying a floor-derived figure changed to "
        f"{populated}. Every floor number a user reads must arrive with its own "
        "provenance — the EV band with its coverage badge (asserted by driving "
        "the widget in test_suppression_6_*), an odds row with floor_source and "
        "floor_note. A new entry here needs one of those two, plus an assertion "
        "that it reaches pixels."
    )

    # The EV band is the other carrier; it is named through pull_ev_*/ev_* and
    # is inventoried separately so the two shapes stay distinguishable.
    hero = set(FWA_WIDGET_SIGNATURES["FWAHeroMetrics"])
    assert {"ev_collections_priced", "ev_collections_total", "ev_weight_priced_pct"} <= hero, (
        "PRD §3: the coverage badge's three inputs must stay in the hero "
        f"signature: {sorted(hero)}"
    )
    ev_carriers = {
        widget
        for widget, kwargs in FWA_WIDGET_SIGNATURES.items()
        if any(k.startswith(("pull_ev_", "ev_")) for k in kwargs)
    }
    assert ev_carriers == {"FWAHeroMetrics"}, (
        "PRD §3: the EV band is rendered by FWAHeroMetrics alone, because that "
        "is the widget whose coverage badge is asserted to reach the screen. "
        f"Now also: {sorted(ev_carriers - {'FWAHeroMetrics'})}"
    )

    # And the odds row's provenance really is populated, not merely declared.
    assert CollectionOdds.model_fields["floor_source"].default == "missing"
    assert CollectionOdds.model_fields["floor_eth"].default is None


# ===========================================================================
# Guards earned during the build — these are the ones that actually bit
# ===========================================================================


def test_no_hardcoded_harmonic_arithmetic_gap_anywhere():
    """The hm/am gap is a LIVE ratio, not a constant.

    Measured 3.885x during research and <=3.49x two days later. WP-5 already
    forbids the literals inside ``analytics/fwa_ev.py``; the principle extends
    to every FWA module, because a gap constant anywhere is a number that will
    be wrong within days of being written.
    """
    # The two measured values are forbidden outright — they mean nothing else.
    hits = _scan(r"(?<![\d_.])(3\.885|3\.49)(?![\d])", FWA_MODULES)
    assert not hits, (
        "The harmonic/arithmetic gap is a LIVE ratio (3.885x measured, <=3.49x "
        "two days later). No measured gap value may be pinned in FWA code — "
        f"compute it from the current backings: {hits}"
    )
    # A round number near the gap is only suspicious next to a gap identifier;
    # 4.0 is a perfectly good backoff second elsewhere.
    gap_line = r"^.*(?:gap|harmonic|arithmetic|\bhm\b|\bam\b|hm_am).*$"
    for path in FWA_MODULES:
        code = _code_only(path.read_text(encoding="utf-8"))
        for match in re.finditer(gap_line, code, re.MULTILINE | re.IGNORECASE):
            line = match.group(0)
            if re.search(r"(?<![\d_.])[2-9]\.\d+(?![\d])", line):
                lineno = code[: match.start()].count("\n") + 1
                pytest.fail(
                    "The harmonic/arithmetic gap is a LIVE ratio, never a "
                    f"constant. {_rel(path)}:{lineno}: {line.strip()}"
                )
    for name in ("hm_am_gap", "gap_x", "GAP", "HM_AM", "DEFAULT_GAP"):
        hits = _scan(rf"^{name}\s*[:=]", FWA_MODULES, re.MULTILINE)
        assert not hits, f"no module-level gap constant: {hits}"

    # It is computed, and it moves with its input.
    tight = fwa_ev.hm_am_gap([10**18, 10**18, 10**18])
    wide = fwa_ev.hm_am_gap([10**16, 10**18, 100 * 10**18])
    assert tight == pytest.approx(1.0, abs=1e-9)
    assert wide > 5.0, (
        "hm_am_gap must track the actual backing distribution, not a constant"
    )


def test_a_missing_floor_is_omitted_never_zeroed():
    """A ``0.0`` floor is worse than a missing one — and it inflates upward.

    Zeroing an unpriced collection *raises* ``lower_eth`` (the pessimistic leg
    becomes an assertion of worthlessness rather than of ignorance) and lifts
    ``collections_priced``, so the coverage badge overstates confidence at the
    same moment the band collapses. Both errors point the same way: toward a
    confident lie.
    """
    assert CollectionOdds.model_fields["floor_eth"].default is None, (
        "an unpriced collection's floor must default to None, never 0.0"
    )
    assert CollectionOdds.model_fields["floor_source"].default == "missing"
    assert fwa_market.FloorQuote(address="0x1").floor_eth is None
    assert fwa_market.FloorQuote(address="0x1").priced is False
    assert fwa_market._opt_float(None) is None
    assert fwa_market._opt_float("") is None

    # floors_for_ev omits unpriced collections rather than emitting 0.0.
    quotes = {
        "0xaa": fwa_market.FloorQuote(address="0xaa", floor_eth=0.5, status="ok"),
        "0xbb": fwa_market.FloorQuote(address="0xbb", floor_eth=None, status="missing"),
        "0xcc": fwa_market.FloorQuote(address="0xcc", floor_eth=None, status="suppressed"),
    }
    floors = fwa_market.floors_for_ev(quotes)
    assert set(floors) == {"0xaa"}, (
        "floors_for_ev must OMIT unpriced collections. Present-with-0.0 asserts "
        f"the collection is worthless: {floors}"
    )
    assert 0.0 not in floors.values()

    # And the omission is what keeps the band honest. Backing is deliberately
    # tiny so the sell-back leg cannot mask a zeroed floor.
    positions = [(10**16, "0xaa"), (10**16, "0xbb")]
    omitted = fwa_ev.pull_ev_band(positions, {"0xaa": 5.0}, acquisition_fee_wei=0)
    zeroed = fwa_ev.pull_ev_band(
        positions, {"0xaa": 5.0, "0xbb": 0.0}, acquisition_fee_wei=0
    )
    assert zeroed["collections_priced"] > omitted["collections_priced"], (
        "a 0.0 floor inflates collections_priced — the coverage badge would "
        "overstate how much of the pool is actually priced"
    )
    assert zeroed["lower_eth"] > omitted["lower_eth"], (
        "a 0.0 floor RAISES the pessimistic bound: max(0.85*backing, 0.0) beats "
        "the zeroed-out contribution an unknown floor is supposed to give. The "
        "band collapses toward a confident lie from the unexpected direction."
    )
    assert omitted["lower_eth"] <= omitted["best_eth"]
    assert zeroed["weight_priced_pct"] > omitted["weight_priced_pct"]


def test_a_failed_read_is_none_never_zero():
    """``externalBuysEnabled()``, ``TTT_AMOUNT()``, ``lastBuybackBlock()`` all
    legitimately read zero.

    Collapsing a failed RPC onto ``0`` makes a dead node indistinguishable from
    a disabled feature — and the disabled feature is the interesting state.
    """
    views = tuple(
        v
        for v in fwa_client.HOT_VIEWS
        if v.key in {"external_buys_enabled", "ttt_amount", "last_buyback_block"}
    )
    assert len(views) == 3, "all three zero-valued views must stay in the hot batch"

    values, failed = fwa_client.decode_view_results(views, [(False, "0x")] * 3)
    for key in ("external_buys_enabled", "ttt_amount", "last_buyback_block"):
        assert values[key] is None, (
            f"a failed read of {key} must be None, never 0/False — those are "
            "legitimate live values and conflating them hides a dead RPC"
        )
        assert key in failed

    # A short result list is a failure too, not a zero.
    values, failed = fwa_client.decode_view_results(views, [])
    assert all(values[v.key] is None for v in views)
    assert len(failed) == 3

    # A genuine zero survives as a genuine zero.
    zero_word = "0x" + "00" * 32
    values, failed = fwa_client.decode_view_results(views, [(True, zero_word)] * 3)
    assert values["external_buys_enabled"] is False
    assert values["ttt_amount"] == 0
    assert values["last_buyback_block"] == 0
    assert failed == []

    # …and the signal layer keeps the distinction.
    assert sig.buy_gate_signal(None).value_str != sig.buy_gate_signal(False).value_str, (
        "an unreadable buy gate and a closed buy gate are different states"
    )


def test_pull_ev_has_no_point_field_and_cannot_grow_one():
    """PRD §3: the flagship metric is a band, enforced by the type.

    ``extra="forbid"`` is what makes it impossible to bolt a confident single
    number on at a call site. Both halves are asserted, because the absent
    field alone would be a convention and the config alone would be pointless.
    """
    fields = set(PullEV.model_fields)
    forbidden = {"point_eth", "value_eth", "ev_eth", "ev", "point", "value", "mid_eth"}
    assert not fields & forbidden, (
        "PRD §3: PullEV must have no point field — floors are missing for 16 of "
        f"38 collections. Found: {sorted(fields & forbidden)}"
    )
    assert {"lower_eth", "best_eth"} <= fields
    assert PullEV.model_config.get("extra") == "forbid", (
        'PRD §3: PullEV.model_config must keep extra="forbid" so a point value '
        "cannot be added at a call site"
    )
    assert PullEV.model_config.get("frozen") is True

    ev = PullEV(
        lower_eth=-0.04,
        best_eth=0.02,
        fee_eth=0.13,
        rebate_eth=0.0,
        collections_priced=22,
        collections_total=38,
        weight_priced_pct=61.3,
    )
    with pytest.raises(Exception):
        PullEV(**{**ev.model_dump(), "point_eth": 0.0})
    with pytest.raises(Exception):
        ev.lower_eth = 0.0  # type: ignore[misc]

    # The band is the contract at the flat-dict boundary too.
    assert "pull_ev_lower_eth" in FWA_DATA_KEYS and "pull_ev_best_eth" in FWA_DATA_KEYS
    assert not [k for k in FWA_DATA_KEYS if k in {"pull_ev_eth", "pull_ev_point_eth"}]
    # …and the analytics function returns both bounds, never one.
    band = fwa_ev.pull_ev_band([(10**18, "0xaa")], {}, acquisition_fee_wei=0)
    assert {"lower_eth", "best_eth"} <= set(band)
    assert not {"ev", "point", "value"} & set(band)


def test_no_wall_clock_dependence_in_the_analytics_or_test_layers():
    """No result may move because the emissions stop (2026-08-04T19:01:23Z) passed.

    WP-5 guards ``analytics/fwa_signals.py`` and its own suite. Generalised
    here: the whole analytics layer takes an injected clock, and no FWA test
    file anywhere reads a calendar. A suite that only passes before the stop is
    a defect, and the stop is days away.
    """
    needles = [
        f"{mod}.{call}("
        for mod, call in (
            ("time", "time"),
            ("datetime", "now"),
            ("datetime", "today"),
            ("datetime", "utcnow"),
            ("date", "today"),
        )
    ]

    analytics = tuple(_PKG.glob("analytics/fwa_*.py"))
    assert analytics
    for path in analytics:
        code = _code_only(path.read_text(encoding="utf-8"))
        for needle in needles:
            assert needle not in code, (
                f"{_rel(path)} reads the wall clock. The analytics layer must "
                "take an injected clock so the emissions stop cannot move a "
                f"result: {needle}"
            )

    test_files = _fwa_test_files()
    assert len(test_files) >= 10, "expected the FWA suite to be discovered"
    calendar_needles = [n for n in needles if not n.startswith("time.")]
    for path in test_files:
        code = _code_only(path.read_text(encoding="utf-8"))
        for needle in calendar_needles:
            assert needle not in code, (
                f"{_rel(path)} reads the calendar. No FWA test may assert "
                "differently before and after 2026-08-04T19:01:23Z: " + needle
            )

    # The emissions signal itself is a pure function of its injected clock, and
    # it refuses to invent one.
    stop = 1_785_870_083
    args = (stop + 86_400, 1_784_574_083, 15 * 24 * 3_600)
    assert sig.emissions_signal(*args) == sig.emissions_signal(*args)
    assert "ended" in sig.emissions_signal(*args).value_str
    assert "live" in sig.emissions_signal(stop - 86_400, 1_784_574_083, 15 * 24 * 3_600).value_str
    assert sig.emissions_signal().value_str == "emissions status unavailable", (
        "with no clock injected the signal must say so, never guess from now()"
    )


async def test_widget_renders_do_not_move_with_the_wall_clock(monkeypatch):
    """The same payload must render identically on either side of the stop.

    The static scan above cannot reach the widgets, which legitimately use
    ``time.time()`` as an *as-of* fallback. This drives the real render twice
    under two clocks a year apart and compares the pixels.
    """
    import time as time_module

    from textual.app import App, ComposeResult

    from maxpane_dashboard.widgets.fwa import (
        FWAActivityFeed,
        FWAChaseBoard,
        FWAHeroMetrics,
        FWAOddsBoard,
        FWASettlementTable,
        FWASignals,
        FWASparkline,
    )

    widget_types = {
        "FWAHeroMetrics": FWAHeroMetrics,
        "FWAOddsBoard": FWAOddsBoard,
        "FWASparkline": FWASparkline,
        "FWASignals": FWASignals,
        "FWAActivityFeed": FWAActivityFeed,
        "FWAChaseBoard": FWAChaseBoard,
        "FWASettlementTable": FWASettlementTable,
    }

    async def _render_at(now: float) -> dict[str, str]:
        monkeypatch.setattr(time_module, "time", lambda: now)
        out: dict[str, str] = {}
        for name, cls in widget_types.items():
            class _Harness(App):
                def compose(self) -> ComposeResult:
                    yield cls()

            app = _Harness()
            async with app.run_test():
                widget = app.query_one(cls)
                widget.update_data(
                    **dict.fromkeys(FWA_WIDGET_SIGNATURES[name])
                )
                await app.workers.wait_for_complete()
                strips = app.screen._compositor.render_strips()
                out[name] = "\n".join(
                    "".join(seg.text for seg in strip) for strip in strips
                )
        return out

    stop = 1_785_870_083  # 2026-08-04T19:01:23Z
    before = await _render_at(stop - 30 * 86_400)
    after = await _render_at(stop + 365 * 86_400)

    for name in widget_types:
        assert before[name] == after[name], (
            f"{name} renders differently before and after the emissions stop. No "
            "FWA surface may depend on the wall clock — the post-emissions state "
            "is the primary case, not the exception."
        )


def test_no_network_in_any_fwa_test():
    """Structural: every FWA test drives a transport, never a socket.

    Asserted by construction rather than by running offline — an HTTP client
    constructed without an explicit ``transport=`` in a test is a live socket
    waiting for a CI runner with connectivity.
    """
    test_files = _fwa_test_files()
    # Needles are assembled at runtime so this scan does not trip over its own
    # source text — the same reason WP-5 assembles its clock needles.
    banned = [
        f"{mod}.{call}"
        for mod, call in (
            ("requests", "get"),
            ("requests", "post"),
            ("urllib", "request"),
            ("socket", "socket"),
        )
    ]
    for path in test_files:
        code = _code_only(path.read_text(encoding="utf-8"))

        for needle in banned:
            assert needle not in code, f"{_rel(path)} may reach the network: {needle}"

        for match in re.finditer(r"httpx\.(?:Async)?Client\(", code):
            tail = code[match.end() : match.end() + 400]
            depth, closing = 1, len(tail)
            for i, ch in enumerate(tail):
                depth += (ch == "(") - (ch == ")")
                if depth == 0:
                    closing = i
                    break
            args = tail[:closing]
            lineno = code[: match.start()].count("\n") + 1
            assert "transport=" in args, (
                f"{_rel(path)}:{lineno} builds an httpx client with no explicit "
                "transport — every FWA test must be hermetic"
            )

    # The clients themselves accept an injected transport, which is what makes
    # the above possible at all.
    assert "http_client" in inspect.signature(fwa_client.FWAClient.__init__).parameters
    assert "http_client" in inspect.signature(fwa_logs.FWALogClient.__init__).parameters


def test_no_etherscan_no_keyed_endpoint_and_no_import_of_scripts():
    """Shipped code is keyless and standalone.

    Etherscan, Reservoir, OpenSea and the keyed RPCs were all used during
    *research*; none may survive into the package. ``scripts/`` is a
    development tool — vendoring ABIs is a build step, not a runtime import,
    and the package must work from a pipx install where ``scripts/`` is absent.
    """
    hits = _scan(r"etherscan|js-copytextarea2|data-csource", FWA_MODULES, re.IGNORECASE)
    assert not hits, (
        f"no Etherscan reference may survive in shipped FWA code: {hits}"
    )

    banned_hosts = (
        "api.etherscan.io",
        "eth.llamarpc.com",
        "rpc.ankr.com",
        "api.reservoir.tools",
        "api-mainnet.magiceden.dev",
        "sourcify.dev",
        "eth-mainnet.g.alchemy.com",
        "mainnet.infura.io",
    )
    for path in FWA_MODULES:
        code = _code_only(path.read_text(encoding="utf-8"))
        # A declared denylist is the one legitimate place these names appear.
        denylist = re.search(r"(?s)_BANNED_RPC_HOSTS\s*=\s*frozenset\(.*?\n\)", code)
        scannable = code.replace(denylist.group(0), "") if denylist else code
        for host in banned_hosts:
            assert host not in scannable, (
                f"{_rel(path)} references the keyed/dead host {host}. Every "
                "MaxPane dashboard must run keyless."
            )

    for pattern in (r"\bapi_key\b", r"\bapikey\b", r"X-API-KEY", r"\bAuthorization\b"):
        hits = _scan(pattern, FWA_MODULES, re.IGNORECASE)
        assert not hits, f"no API key or auth header in FWA code: {hits}"

    # The denylist is real, not decorative.
    assert banned_hosts[1] in fwa_client._BANNED_RPC_HOSTS
    assert "api.reservoir.tools" in fwa_client._BANNED_RPC_HOSTS

    # Nothing in the whole package imports the dev scripts.
    offenders = []
    for path in sorted(_PKG.rglob("*.py")):
        code = _code_only(path.read_text(encoding="utf-8"))
        if re.search(r"^\s*(from|import)\s+scripts\b", code, re.MULTILINE):
            offenders.append(_rel(path))
    assert not offenders, (
        "maxpane_dashboard/ must never import scripts/ — the package ships "
        f"without it: {offenders}"
    )


def test_fwa_code_is_read_only_no_signing_no_sending():
    """The dashboard reads chain state. It never holds a key or builds a tx.

    Named explicitly rather than left implicit: every other MaxPane dashboard
    is read-only too, and the day one of them is not, that must be a deliberate
    decision someone made against a red test.
    """
    signing_imports = r"^\s*(from|import)\s+(eth_account|web3\.auto|.*keystore)\b"
    hits = _scan(signing_imports, FWA_MODULES, re.MULTILINE)
    assert not hits, f"FWA code must not import a signing library: {hits}"

    for pattern in (
        r"\bLocalAccount\b",
        r"\bprivate_key\b",
        r"\bPRIVATE_KEY\b",
        r"\bmnemonic\b",
        r"eth_sendRawTransaction",
        r"eth_sendTransaction",
        r"\bpersonal_[a-z]",
        r"\beth_sign\b",
        r"\bsign_transaction\b",
        r"\bbuild_transaction\b",
        r"\bgetpass\b",
    ):
        hits = _scan(pattern, FWA_MODULES)
        assert not hits, (
            "FWA is a read-only dashboard: no signing, no sending, no key "
            f"prompts, no transaction construction. Found {pattern}: {hits}"
        )

    # Positively: every JSON-RPC method actually dispatched is a read method.
    # Matched at the call site rather than by name, so a data key that merely
    # starts with ``eth_`` (``eth_backed``) is not mistaken for one.
    read_only = {
        "eth_call",
        "eth_blockNumber",
        "eth_getBalance",
        "eth_gasPrice",
        "eth_getLogs",
        "eth_getBlockByNumber",
        "eth_chainId",
        "eth_getCode",
        "eth_getTransactionReceipt",
    }
    dispatched: set[str] = set()
    for path in FWA_MODULES:
        code = _code_only(path.read_text(encoding="utf-8"))
        for method in re.findall(
            r'(?:_rpc\(\s*|"method"\s*:\s*)"([a-z]+_[A-Za-z]+)"', code
        ):
            dispatched.add(method)
            assert method in read_only, (
                f"{_rel(path)} dispatches the non-read RPC method {method}. FWA "
                "is read-only: no signing, no sending, no transaction "
                "construction."
            )
    assert "eth_call" in dispatched, (
        "no RPC dispatch site was found at all — this guard would pass "
        "vacuously; the match pattern has drifted from the client"
    )


def test_the_unconsumed_sqrt_backing_read_is_free_and_stays_out_of_the_maths():
    """WP-20's ruling on ``sqrtBackingTotal()``: keep it, and pin why.

    It was carried forward as a *dead read* -- in ``HOT_VIEWS``, consumed by
    nothing, therefore "a live RPC cost for nothing" every 15 s tick. Measured,
    the cost is not there: ``HOT_VIEWS`` is dispatched through Multicall3
    ``aggregate3`` in chunks of :data:`MULTICALL_MAX_CALLS`, and the whole table
    fits in **one** chunk with an order of magnitude to spare. Dropping one view
    removes ~100 bytes of calldata from a request that still happens. It is not
    a round trip, so the premise for removing it was wrong.

    What it *is* worth is what rule 5's guard already says: the FWA source
    carries a stale struct comment claiming fees are split by ``sqrt(backing)``,
    and ``abis/fwa/`` really does expose ``sqrtBackingTotal()``. The materials to
    "fix" the code into being wrong are sitting right there. Reading the value as
    a plain observation, while the guard forbids it entering the maths, keeps the
    trap concrete rather than abstract.

    This test is the ruling's expiry condition. If ``HOT_VIEWS`` ever grows past
    a chunk boundary such that this view genuinely costs a second round trip, the
    arithmetic below goes red and the decision is reopened with real evidence
    instead of an assumption.
    """
    import math

    keys = [v.key for v in fwa_client.HOT_VIEWS]
    assert "sqrt_backing_total" in keys
    assert "sqrt_backing_total" in fwa_client.FWA_HOT_KEYS

    total = len(fwa_client.HOT_VIEWS)
    limit = fwa_client.MULTICALL_MAX_CALLS
    with_it = math.ceil(total / limit)
    without_it = math.ceil((total - 1) / limit)
    assert with_it == without_it, (
        f"sqrtBackingTotal() now costs a whole extra multicall round trip "
        f"({with_it} chunks vs {without_it} without it, {total} views at "
        f"{limit} per chunk). WP-20 kept this unconsumed read on the measured "
        "grounds that it was free. It is no longer free — either drop it from "
        "HOT_VIEWS or raise MULTICALL_MAX_CALLS."
    )
    assert total < limit, (
        f"HOT_VIEWS ({total}) is at the chunk limit ({limit}); the next view "
        "added is a second round trip for every tick"
    )

    # The other half of the bargain: observed, never used. Rule 5's scan covers
    # analytics and the render modules; this pins the flat-dict boundary too, so
    # the value cannot reach a widget by being added to the payload.
    from maxpane_dashboard.data.fwa_models import FWA_ROW_KEYS

    assert not [k for k in FWA_DATA_KEYS if "sqrt" in k.lower()]
    for group, row in FWA_ROW_KEYS.items():
        assert not [k for k in row if "sqrt" in k.lower()], group
    for widget, kwargs in FWA_WIDGET_SIGNATURES.items():
        assert not [k for k in kwargs if "sqrt" in k.lower()], widget


def test_no_named_fixture_carries_a_field_the_product_cannot_emit():
    """A fixture the product cannot produce measures itself, not the product.

    Added by WP-20 after three separate instances of the same defect shipped
    through three different work packages:

    * ``tests/screens/test_fwa_screen.py`` built five signal rows by hand with
      ``"color": "cyan" | "green" | "red"`` and ``"indicator": "▲"``. The
      analytics vocabulary is ``$success | $warning | $error | dim`` and the
      indicator is always ``●`` -- WP-19 moved the colours to theme variables
      precisely because the CSS name ``green`` is ``#008000``, which fails AA
      against every possible background. So the screen test was rendering a
      palette the product had been changed to never emit.
    * ``tests/widgets/test_fwa_widgets_b.py`` carried the same thing, plus an
      ``"■"`` indicator.
    * ``tests/widgets/test_fwa_accessibility.py``'s ``_HERO`` passed
      ``pull_ev_available`` / ``priced_collections`` / ``total_collections`` /
      ``priced_weight_pct``. ``FWAHeroMetrics.update_data`` accepts none of
      those -- the real names are ``ev_available`` / ``ev_collections_*`` /
      ``ev_weight_priced_pct`` -- so all four were swallowed by ``**_kwargs``
      and the accessibility audit measured the coverage badge as
      ``--/-- · --%``. The audit's *conclusions* survived the correction, but
      it had been aimed slightly beside the target.

    The ``**_kwargs`` on every widget is deliberate (it lets ``FWA_DATA_KEYS``
    grow without breaking a widget mid-wave), which is exactly why a misspelled
    kwarg is silent and needs a guard rather than a type.

    **Scope: module-level *named* fixtures only.** A dict literal passed inline
    to a formatter is usually an adversarial input -- ``_fmt_pool_temp({...
    "color": "#f59e0b"})`` deliberately feeds an unrenderable colour to prove
    the textual fallback fires -- and those must stay free. A fixture with a
    name is a claim about what the product emits.
    """
    from maxpane_dashboard.analytics.fwa_signals import INDICATOR, SIGNAL_COLORS

    known_kwargs = set(FWA_DATA_KEYS)
    for kwargs in FWA_WIDGET_SIGNATURES.values():
        known_kwargs |= set(kwargs)

    def _const_dict(node: ast.Dict) -> dict:
        return {
            k.value: v.value
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant)
            and isinstance(k.value, str)
            and isinstance(v, ast.Constant)
        }

    def _check_signal(where: str, node: ast.Dict) -> None:
        const = _const_dict(node)
        if "value_str" not in const or "color" not in const:
            return
        assert const["color"] in SIGNAL_COLORS, (
            f"{where} declares color={const['color']!r}. "
            f"analytics/fwa_signals.py can only emit {sorted(SIGNAL_COLORS)} — "
            "a fixture outside that vocabulary tests the fixture, not the panel"
        )
        assert const.get("indicator", INDICATOR) == INDICATOR, (
            f"{where} declares indicator={const['indicator']!r}; every FWASignal "
            f"carries {INDICATOR!r}"
        )

    checked_signals = 0
    checked_payloads = 0
    for path in _fwa_test_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for stmt in tree.body:  # module level only — see the docstring
            if not isinstance(stmt, ast.Assign):
                continue
            name = (
                stmt.targets[0].id
                if isinstance(stmt.targets[0], ast.Name)
                else "<fixture>"
            )
            candidates = []
            if isinstance(stmt.value, ast.Dict):
                candidates.append(stmt.value)
            elif isinstance(stmt.value, (ast.List, ast.Tuple)):
                candidates += [e for e in stmt.value.elts if isinstance(e, ast.Dict)]

            for node in candidates:
                where = f"{_rel(path)}:{node.lineno} ({name})"
                _check_signal(where, node)
                checked_signals += 1
                # Nested signal rows, e.g. a payload's five ``*_signal`` values.
                for value in node.values:
                    if isinstance(value, ast.Dict):
                        _check_signal(f"{_rel(path)}:{value.lineno} ({name})", value)

                keys = {
                    k.value
                    for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                # A dict that is mostly widget kwargs is a widget payload; a
                # stray key in one is a silently-swallowed misspelling.
                if len(keys & known_kwargs) >= 3:
                    checked_payloads += 1
                    unknown = sorted(keys - known_kwargs)
                    assert not unknown, (
                        f"{where} passes {unknown} — not in FWA_DATA_KEYS and not "
                        "a kwarg of any widget in FWA_WIDGET_SIGNATURES. Every "
                        "widget ends its signature with **_kwargs, so this is "
                        "accepted silently and rendered as missing data. The "
                        "assertions around it are then measuring nothing."
                    )

    assert checked_payloads >= 3 and checked_signals >= 3, (
        "this guard found no fixtures to check — the discovery walk has drifted "
        f"(payloads={checked_payloads}, dicts={checked_signals})"
    )


def test_every_prd_rule_has_a_guard_in_this_module():
    """Traceability: no rule may lose its guard without this test noticing.

    A rule whose guard is deleted is worse off than a rule that never had one,
    because the traceability table still claims coverage.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    for n in range(1, 12):
        assert re.search(rf"^def test_rule_{n}_", source, re.MULTILINE), (
            f"PRD §7 rule {n} has no guard in this module"
        )
    for n in range(1, 7):
        assert re.search(rf"^(async )?def test_suppression_{n}_", source, re.MULTILINE), (
            f"PRD §13 suppression {n} has no guard in this module"
        )
    for name in (
        "test_no_hardcoded_harmonic_arithmetic_gap_anywhere",
        "test_a_missing_floor_is_omitted_never_zeroed",
        "test_a_failed_read_is_none_never_zero",
        "test_pull_ev_has_no_point_field_and_cannot_grow_one",
        "test_no_wall_clock_dependence_in_the_analytics_or_test_layers",
        "test_widget_renders_do_not_move_with_the_wall_clock",
        "test_no_network_in_any_fwa_test",
        "test_no_etherscan_no_keyed_endpoint_and_no_import_of_scripts",
        "test_fwa_code_is_read_only_no_signing_no_sending",
        "test_no_named_fixture_carries_a_field_the_product_cannot_emit",
        "test_the_floor_dependent_surface_inventory_is_closed",
        "test_the_unconsumed_sqrt_backing_read_is_free_and_stays_out_of_the_maths",
    ):
        assert re.search(rf"^(async )?def {name}\(", source, re.MULTILINE), (
            f"the build-earned guard {name} was removed"
        )

    # And the scan set itself must not quietly shrink.
    assert len(FWA_MODULES) >= 17, (
        f"only {len(FWA_MODULES)} FWA modules found — the static scans below "
        "would silently stop covering the missing ones"
    )
    assert any(p.name == "fwa.py" and p.parent.name == "screens" for p in FWA_MODULES)
    assert sum(1 for p in FWA_MODULES if p.parent.name == "fwa") >= 8
