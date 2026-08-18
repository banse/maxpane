"""THE LIST's preset — the curve, the segments, the cleaned list.

``sybilkit`` is a general tool; this module is the one place that knows what
*this* game is.  It is still pure, still wei-native, still stdlib-only, and it
still imports nothing from maxpane: a preset is a bag of **measurements** plus
three folds over a :class:`~sybilkit.model.Dataset` and a
:class:`~sybilkit.report.DetectResult`.

The rule that shapes the whole module
    **Every chain constant is an input.**  ``POINTS_PER_ETH`` and
    ``minDeposit`` are read off the chain by whoever builds the preset (the CLI
    does it with an ``eth_call``, the maxpane adapter with its own client) and
    handed to :class:`CuratorPreset`, which has **no default for either**.
    CLAUDE.md hard constraint 4 is not a style rule here: one protocol in this
    repo documents a 5 % fee that is 1 % on chain, and a "4.0×" ratio quoted in
    research measured 3.885×, then 3.49×, then 2.956× on three consecutive
    days.  A preset that remembered ``1000`` would be right until the day it
    silently was not, and every point in the analysis would move with it.

    Ruling R13 makes the minimum the same kind of input for a sharper reason:
    with ``protocol_min_amount_wei`` unset, the crowd that all paid the
    protocol floor is byte-identical by construction and welds into one
    enormous group — WP1 measured **1 468 of 1 468** minimum-payers flagged
    with the knob off against **272** with it on.  Everyone sends the minimum,
    so the minimum identifies nobody.

The curve is not re-implemented here
    :func:`curve_points` is :func:`sybilkit.curve.curve_points`, re-exported
    (ruling R1).  There is deliberately exactly one implementation and one
    mutation-tested suite for it; a second copy is always the one nobody
    mutates, and the two drift in the last digits where nobody looks.

Pattern language, in the labels
    A preset's ``label`` strings are what a consumer renders.  The library may
    say "sybil" in its own name and docstrings — it is a general sybil-analysis
    toolkit and lives outside every scanned surface — but the *segment labels*
    are written in the dashboard's own vocabulary ("largest operators", "early
    cohort") so that an adapter never has to translate an accusation into a
    description.  :data:`FORBIDDEN_LABEL_WORDS` names what may not appear and
    ``tests/test_curator.py`` scans every produced string for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cluster import DetectConfig
from .curve import curve_points  # re-export, ruling R1 — never a second copy
from .model import Dataset
from .report import Cluster, DetectResult

#: Words a rendered ``label`` or ``detail`` may never contain.  The chain
#: cannot prove intent — one person spreading a deposit and nine people copying
#: a trade produce identical logs — so the preset describes shapes and lets the
#: reader draw the conclusion.  Mirrors the three forbidden-word tests the
#: curator dashboard already enforces on its own surfaces.
FORBIDDEN_LABEL_WORDS: tuple[str, ...] = (
    "sybil",
    "cheat",
    "fraud",
    "attack",
    "abuse",
    "farmer",
    "wash",
)

#: Multiplier bands, in basis points, **descending** — each band is
#: ``[edge, previous_edge)``.  The early-bird multiplier decays 2.0× → 1.0×
#: across the grace period, so these four bands split the population into
#: "arrived at nearly double" through "arrived at par".  A default, not a
#: measurement: the *edges* are a presentation choice and the preset takes
#: them as a field so a caller with a different decay can say so.
DEFAULT_MULTIPLIER_BAND_BPS: tuple[int, ...] = (17_500, 15_000, 12_500, 10_000)

_ETH = 10**18


def _eth_str(wei: int) -> str:
    """A wei amount as a short ETH string.  Presentation only — nothing
    computes with it; trailing zeros trimmed, one decimal always kept."""
    whole, frac = divmod(wei, _ETH)
    text = f"{whole}.{frac:018d}".rstrip("0")
    return text + "0" if text.endswith(".") else text


# ---------------------------------------------------------------------------
# The preset
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CuratorPreset:
    """THE LIST's constants, as the caller measured them.

    ``points_per_eth``
        The chain's own ``POINTS_PER_ETH``.  **No default.**  It is 1000 on
        this deployment and that is a measurement, not a constant.

    ``min_deposit_wei``
        The chain's own ``minDeposit``.  **No default**, ruling R13: it becomes
        ``DetectConfig.protocol_min_amount_wei``, and without it the whole
        minimum-paying crowd is flagged wholesale on an identicalness that
        identifies nobody.

    The remaining fields are *analysis* choices rather than chain readings, so
    they carry documented defaults: the four ``DetectConfig`` gate knobs, the
    size of the "early cohort" (the research's index-1000 slice), how many
    trailing grace hours count as the late cohort, the combined-credit line
    above which an operator is one of the "largest", and the multiplier band
    edges.  Every one of them is still a field, so a caller who measured
    something different is never arguing with a literal.
    """

    points_per_eth: int
    min_deposit_wei: int
    min_size: int = 5
    min_families: int = 2
    near_amount_tol: float = 0.10
    confidence_threshold: float = 0.5
    early_cohort_size: int = 1_000
    late_cohort_hours: int = 2
    largest_operator_credit_wei: int = 800 * _ETH
    multiplier_band_bps: tuple[int, ...] = field(
        default=DEFAULT_MULTIPLIER_BAND_BPS
    )

    def __post_init__(self) -> None:
        # A programming error raises; it never produces a plausible analysis.
        if not isinstance(self.points_per_eth, int) or self.points_per_eth <= 0:
            raise ValueError(
                f"points_per_eth must be a positive int read from the chain, "
                f"got {self.points_per_eth!r}"
            )
        if not isinstance(self.min_deposit_wei, int) or self.min_deposit_wei < 0:
            raise ValueError(
                f"min_deposit_wei must be a non-negative wei int read from the "
                f"chain, got {self.min_deposit_wei!r}"
            )
        if self.early_cohort_size < 1:
            raise ValueError("early_cohort_size must be >= 1")
        if self.late_cohort_hours < 1:
            raise ValueError("late_cohort_hours must be >= 1")

    def detect_config(self) -> DetectConfig:
        """The gate configuration, with both live reads threaded in.

        This is the **only** path the rate has (ruling R10 removed the dataset
        attribute and its fallback), and the only path the minimum has
        (R13).  A caller that drives ``detect`` with anything else is driving
        it without the chain's own numbers.
        """
        return DetectConfig(
            min_size=self.min_size,
            min_families=self.min_families,
            near_amount_tol=self.near_amount_tol,
            confidence_threshold=self.confidence_threshold,
            points_per_eth=self.points_per_eth,
            protocol_min_amount_wei=self.min_deposit_wei,
        )

    def points(self, weight_wei: int) -> int:
        """Curve points for *weight_wei* at **this preset's** measured rate."""
        return curve_points(weight_wei, self.points_per_eth)


__all__ = [
    "CuratorPreset",
    "DEFAULT_MULTIPLIER_BAND_BPS",
    "FORBIDDEN_LABEL_WORDS",
    "curve_points",
]
