# surf captures — real payloads, fetched 2026-08-08

Raw keyless-API responses captured during the surf research session
(Blockscout REST v2, GeckoTerminal, DexScreener, ensdata, IPFS). These are the
*source material* for the committed test fixtures — slice what a test needs
into a dedicated fixture rather than loading these wholesale.

Trimming applied: paginated lists cut to their first page or less; string
values longer than 4000 chars end with `...TRUNCATED` (initcode, base64
SVGs). `announce_eth_txs.json` message calldata is complete and decodes as
UTF-8 — except the one `register()` call, which is intentionally non-UTF-8.
`_contract.json` files keep name/abi/verified_at plus the first 20k chars of
source as `source_code_head`.
