# Earned wallet source capture

Source: https://explorer.imd.fun/wallet/0x84F4b7424e1B0464f9C749725C1F34bed9AA8aDA/earned?sort=job-asc
Captured 2026-10-13 at approximately 19:45 UTC. Public, keyless GET.

Original HTML SHA-256: `8ca40554282e2053a936fd483df8ee17d4b5d4def9b2fb2644815987479bf146`.

`rows.json` preserves five complete raw rows verbatim after JSON decoding: a
locked asset, claimable asset, builder asset, claimed asset and held allocation
without a token address. Original row indices: [0, 1, 24, 37, 141].

`earned.html` is a reduced structural fixture: the two original export records,
the captured provider wallet, and those exact row objects. Irrelevant UI
children were removed; record 43 and the provider child reference connect the
reduced table. The page's JSON-string flight framing is preserved.

The full capture has 229 rows, 226 identified assets, six builder allocations
and eleven claimed assets. Three held rows have no token address. Observed
claim states: locked, claimable, claimed, held. No allocation had zero units.
