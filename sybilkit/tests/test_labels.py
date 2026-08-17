"""WP1.7 — CEX and infra labels: the funding signal's exclusion list.

The recurring false-positive class (research §7): thousands of honest fresh
wallets are first-funded by the same dozen exchange hot wallets, so a shared
funder that is a CEX must never count as funding evidence.  The 12 addresses
are re-vendored from ChainCred's ``packages/common/src/constants/selectors.ts``
(the two repos are separate; an import would couple their releases).

The end-to-end half of this task — a cluster whose only funding link is a
shared CEX hot wallet is *not formed* — lands with the combiner in
``test_signals_funding.py`` / ``test_cluster.py``, where ``detect`` exists to
assert it against.
"""

from __future__ import annotations

from sybilkit.labels import CEX_HOT_WALLETS, ERC4337_ENTRYPOINTS, is_infra_funder


def test_the_twelve_cex_hot_wallets_are_a_frozenset() -> None:
    assert isinstance(CEX_HOT_WALLETS, frozenset)
    assert len(CEX_HOT_WALLETS) == 12


def test_every_label_is_a_lowercase_address() -> None:
    for addr in CEX_HOT_WALLETS | ERC4337_ENTRYPOINTS:
        assert addr == addr.lower()
        assert addr.startswith("0x") and len(addr) == 42
        int(addr, 16)  # hex-decodes


def test_the_known_binance_and_kraken_wallets_are_present() -> None:
    """Two spot checks against the vendored source, one per exchange family,
    so a re-vendor that drops a row fails loudly."""
    assert "0x28c6c06298d514db089934071355e5743bf21d60" in CEX_HOT_WALLETS  # Binance 14
    assert "0x2910543af39aba0cd09dbb2d50200b3e800a63d2" in CEX_HOT_WALLETS  # Kraken 13


def test_is_infra_funder_covers_cex_and_entrypoints_case_insensitively() -> None:
    cex = next(iter(CEX_HOT_WALLETS))
    entry = next(iter(ERC4337_ENTRYPOINTS))
    assert is_infra_funder(cex)
    assert is_infra_funder(cex.upper().replace("0X", "0x"))
    assert is_infra_funder(entry)
    assert not is_infra_funder("0x" + "11" * 20)


def test_a_none_funder_is_not_infra() -> None:
    """``funder is None`` is a failed read; the hook must say "not infra"
    rather than raise, so a caller can filter without a second None check."""
    assert not is_infra_funder(None)
