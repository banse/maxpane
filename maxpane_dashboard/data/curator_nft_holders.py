"""Keyless current-state NFT holder scans for curator list filters."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

import httpx

from maxpane_dashboard.data.curator_list_filters import (
    FilterDataUnavailable,
    NftCollectionRef,
)
from maxpane_dashboard.data.evm_abi import (
    decode_aggregate3_result,
    decode_string,
    encode_aggregate3,
)
from maxpane_dashboard.data.rpc_common import (
    ENDPOINT_DEAD_CODES,
    OwnedHttpClient,
    jsonrpc_payload,
    pace,
)

logger = logging.getLogger(__name__)

MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"
BALANCE_OF = "0x70a08231"
NAME = "0x06fdde03"
MAX_BALANCES_PER_CALL = 500
DEFAULT_MIN_INTERVAL = 0.12
RPC_POOLS: Mapping[str, tuple[str, ...]] = {
    "ethereum": (
        "https://ethereum-rpc.publicnode.com",
        "https://eth.drpc.org",
    ),
    "base": (
        "https://base-rpc.publicnode.com",
        "https://mainnet.base.org",
        "https://base.llamarpc.com",
    ),
}


class NftHolderPending(FilterDataUnavailable):
    pass


class NftHolderUnavailable(FilterDataUnavailable):
    pass


@dataclass(frozen=True, slots=True)
class NftHolderScan:
    collection: NftCollectionRef
    holders: frozenset[str]
    checked: int
    failed: int
    block_number: int | None

    @property
    def complete(self) -> bool:
        return self.failed == 0


def _normalise_wallets(wallets: Iterable[object]) -> tuple[str, ...]:
    valid = {
        wallet.casefold()
        for wallet in wallets
        if isinstance(wallet, str)
        and len(wallet) == 42
        and wallet.startswith(("0x", "0X"))
        and all(char in "0123456789abcdefABCDEF" for char in wallet[2:])
    }
    return tuple(sorted(valid))


def wallet_universe_fingerprint(wallets: Iterable[object]) -> str:
    body = "\n".join(_normalise_wallets(wallets)).encode("ascii")
    return hashlib.sha256(body).hexdigest()


def _address_word(address: str) -> str:
    return address[2:].casefold().rjust(64, "0")


def _balance_call(address: str) -> str:
    return BALANCE_OF + _address_word(address)


def _uint_result(value: str) -> int | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    try:
        raw = bytes.fromhex(value[2:])
    except ValueError:
        return None
    if len(raw) != 32:
        return None
    return int.from_bytes(raw, "big")


def _code_result_is_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("0x")
        and all(char in "0123456789abcdefABCDEF" for char in value[2:])
    )


def _block_number_result(value: object) -> int | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


def _aggregate3_result_is_valid(value: object, count: int) -> bool:
    return (
        isinstance(value, str)
        and len(decode_aggregate3_result(value)) == count
    )


class NftHolderClient(OwnedHttpClient):
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        rpc_pools: Mapping[str, Sequence[str]] = RPC_POOLS,
        min_interval: float = DEFAULT_MIN_INTERVAL,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": "MaxPane/curator-nft-holders"},
        )
        self._owns_client = http_client is None
        self._rpc_pools = {
            chain: tuple(urls) for chain, urls in rpc_pools.items()
        }
        self._min_interval = float(min_interval)
        self._last_rpc_at = 0.0
        self._request_id = 0

    async def _rpc(
        self,
        chain: str,
        method: str,
        params: list,
        result_is_valid: Callable[[object], bool],
    ):
        urls = self._rpc_pools.get(chain, ())
        if not urls:
            raise NftHolderUnavailable(f"no keyless {chain} RPC")
        last_error: Exception | None = None
        for url in urls:
            self._last_rpc_at = await pace(
                self._last_rpc_at, self._min_interval
            )
            self._request_id += 1
            request_id = self._request_id
            try:
                response = await self._client.post(
                    url,
                    json=jsonrpc_payload(request_id, method, params),
                )
                if response.status_code in ENDPOINT_DEAD_CODES:
                    raise RuntimeError(
                        f"{url}: HTTP {response.status_code}"
                    )
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise RuntimeError(f"{url}: non-object RPC response")
                if body.get("id") != request_id:
                    raise RuntimeError(f"{url}: mismatched RPC id")
                if body.get("error") is not None:
                    raise RuntimeError(f"{url}: {body['error']}")
                if "result" not in body:
                    raise RuntimeError(f"{url}: missing RPC result")
                result = body["result"]
                if not result_is_valid(result):
                    raise RuntimeError(f"{url}: invalid {method} result")
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "NFT holder RPC %s %s failed: %s",
                    chain,
                    method,
                    exc,
                )
        raise NftHolderUnavailable(
            f"{chain} NFT holder RPC unavailable"
        ) from last_error

    async def collection_name(
        self, collection: NftCollectionRef
    ) -> str | None:
        raw_block = await self._rpc(
            collection.chain,
            "eth_blockNumber",
            [],
            lambda value: _block_number_result(value) is not None,
        )
        code = await self._rpc(
            collection.chain,
            "eth_getCode",
            [collection.address, raw_block],
            _code_result_is_valid,
        )
        if not isinstance(code, str) or code in ("0x", "0x0"):
            raise NftHolderUnavailable(f"{collection.label}: no contract code")
        calldata = encode_aggregate3([(collection.address, NAME, True)])
        raw = await self._rpc(
            collection.chain,
            "eth_call",
            [{"to": MULTICALL3, "data": calldata}, raw_block],
            lambda value: _aggregate3_result_is_valid(value, 1),
        )
        [(success, value)] = decode_aggregate3_result(raw)
        return decode_string(value) if success else None

    async def scan(
        self,
        collection: NftCollectionRef,
        wallets: Iterable[object],
    ) -> NftHolderScan:
        addresses = _normalise_wallets(wallets)
        raw_block = await self._rpc(
            collection.chain,
            "eth_blockNumber",
            [],
            lambda value: _block_number_result(value) is not None,
        )
        block_number = _block_number_result(raw_block)
        code = await self._rpc(
            collection.chain,
            "eth_getCode",
            [collection.address, raw_block],
            _code_result_is_valid,
        )
        if not isinstance(code, str) or code in ("0x", "0x0"):
            raise NftHolderUnavailable(
                f"{collection.label}: no contract code"
            )

        holders: set[str] = set()
        checked = 0
        failed = 0
        for start in range(0, len(addresses), MAX_BALANCES_PER_CALL):
            chunk = addresses[
                start : start + MAX_BALANCES_PER_CALL
            ]
            calldata = encode_aggregate3(
                [
                    (collection.address, _balance_call(address), True)
                    for address in chunk
                ]
            )
            raw = await self._rpc(
                collection.chain,
                "eth_call",
                [{"to": MULTICALL3, "data": calldata}, raw_block],
                lambda value: _aggregate3_result_is_valid(
                    value, len(chunk)
                ),
            )
            decoded = (
                decode_aggregate3_result(raw)
                if isinstance(raw, str)
                else []
            )
            if len(decoded) != len(chunk):
                decoded = list(decoded[: len(chunk)])
                decoded.extend(
                    [(False, "0x")] * (len(chunk) - len(decoded))
                )
            for address, (success, value) in zip(chunk, decoded):
                balance = _uint_result(value) if success else None
                if balance is None:
                    failed += 1
                    continue
                checked += 1
                if balance > 0:
                    holders.add(address)
        return NftHolderScan(
            collection=collection,
            holders=frozenset(holders),
            checked=checked,
            failed=failed,
            block_number=block_number,
        )


__all__ = [
    "MAX_BALANCES_PER_CALL",
    "NftHolderClient",
    "NftHolderPending",
    "NftHolderScan",
    "NftHolderUnavailable",
    "RPC_POOLS",
    "wallet_universe_fingerprint",
]
