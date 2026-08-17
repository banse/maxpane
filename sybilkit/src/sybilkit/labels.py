"""CEX and infra funder labels — the funding family's exclusion list.

Why this module exists (research §7): the single strongest measured
false-positive class for funding-graph heuristics is the *shared exchange hot
wallet*.  Thousands of honest fresh wallets are first-funded by the same
dozen CEX withdrawal addresses, so "same first funder" across two wallets is
meaningless when that funder is an exchange — and a detector without this
list fabricates clusters out of Binance's Tuesday.

The 12 addresses are **re-vendored** from ChainCred,
``packages/common/src/constants/selectors.ts`` (``CEX_HOT_WALLETS``), and the
two ERC-4337 entry points ride along from the same file
(``ERC4337_ENTRYPOINTS``): a bundler's entry point "funds" every account it
deploys, which is infrastructure, not intent.  Re-vendored, not imported —
the two repos are separate distributions and must not couple releases.

Everything is lowercase; membership checks lowercase their argument, so a
checksummed spelling cannot sneak past the exclusion.
"""

from __future__ import annotations

#: The 12 known CEX hot wallets, lowercase.  Source: chaincred
#: ``packages/common/src/constants/selectors.ts`` — re-vendored 2026-08-18.
CEX_HOT_WALLETS: frozenset[str] = frozenset(
    {
        "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance 14
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Binance 15
        "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",  # Binance 16
        "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43",  # Coinbase 10
        "0x503828976d22510aad0201ac7ec88293211d23da",  # Coinbase 6
        "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",  # Coinbase 3
        "0x2910543af39aba0cd09dbb2d50200b3e800a63d2",  # Kraken 13
        "0x53d284357ec70ce289d6d64134dfac8e511c8a3d",  # Kraken 4
        "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b",  # OKX 6
        "0x98ec059dc3adfbdd63429227115656b07c44a2e1",  # OKX 8
        "0xd24400ae8bfebb18ca49be86258a3c749cf46853",  # Gemini 4
        "0x07ee55aa48bb72dcc6e9d78256648910de513eca",  # Gemini 7
    }
)

#: ERC-4337 entry points — same source file, same reason to exclude.
ERC4337_ENTRYPOINTS: frozenset[str] = frozenset(
    {
        "0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789",  # EntryPoint v0.6
        "0x0000000071727de22e5e9d8baf0edac6f37da032",  # EntryPoint v0.7
    }
)

_INFRA: frozenset[str] = CEX_HOT_WALLETS | ERC4337_ENTRYPOINTS


def is_infra_funder(addr: str | None) -> bool:
    """True when *addr* is a CEX hot wallet or 4337 entry point.

    ``None`` (a failed funder read) is "not infra" rather than an error, so
    the funding signal can filter in one expression without a second ``None``
    check.
    """
    return addr is not None and addr.lower() in _INFRA


__all__ = ["CEX_HOT_WALLETS", "ERC4337_ENTRYPOINTS", "is_infra_funder"]
