"""Async HTTP client for FrenPet data from Ponder GraphQL, Base RPC, and local AutoPet.

Read-only -- this client never submits transactions.  It fetches pet
data from the Ponder indexer at ``https://api.pet.game``, reads
on-chain state via ``eth_call`` against the Diamond proxy on Base,
and optionally reads the local AutoPet indexer DB for full population data.

Uses httpx.AsyncClient with exponential-backoff retries, matching the
pattern established by the Bakery ``GameDataClient``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx

from maxpane_dashboard.data.frenpet_models import (
    FrenPet,
    FrenPetPopulation,
    FrenPetSnapshot,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# GraphQL field list (shared across queries)
# ---------------------------------------------------------------------------

_PET_FIELDS = """
    id score attackPoints defensePoints level status
    lastAttacked lastAttackUsed timeUntilStarving
    shieldExpires shrooms petWins winQty lossQty name owner
    stakingPerksUntil wheelLastSpin
""".strip()

# Attack event topic for FrenPet Diamond
_ATTACK_EVENT_TOPIC = (
    "0xccf2d58600a20c60b9006a46e39af9f1d1e42fa0a105bf3fbb35a49e"
    "5a08e83b"
)


class FrenPetClient:
    """Fetches FrenPet data from Ponder GraphQL and Base RPC.

    Parameters
    ----------
    graphql_url:
        Ponder GraphQL endpoint.
    rpc_url:
        Base mainnet JSON-RPC endpoint.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  If not provided
        one is created internally and closed on ``close()``.
    """

    GRAPHQL_URL = "https://api.pet.game"
    RPC_URL = "https://mainnet.base.org"
    DIAMOND = "0x0e22b5f3e11944578b37ed04f5312dfc246f443c"
    AUTOPET_API = "http://127.0.0.1:8420"
    INDEXER_DB = os.environ.get("MAXPANE_INDEXER_DB", "")

    def __init__(
        self,
        graphql_url: str = GRAPHQL_URL,
        rpc_url: str = RPC_URL,
        autopet_url: str = AUTOPET_API,
        indexer_db: str = INDEXER_DB,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._graphql_url = graphql_url
        self._rpc_url = rpc_url
        self._autopet_url = autopet_url
        self._indexer_db = indexer_db
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> FrenPetClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal: retry helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(self, url: str, json_body: dict[str, Any]) -> httpx.Response:
        """POST with exponential-backoff retries on transient failures."""
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.post(url, json=json_body)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.StreamError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "POST %s failed (attempt %d/%d): %s -- retrying in %.1fs",
                        url,
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "POST %s failed after %d attempts: %s",
                        url,
                        _MAX_RETRIES,
                        exc,
                    )
        raise last_exc  # type: ignore[misc]

    async def _get_with_retry(self, url: str) -> httpx.Response:
        """GET with exponential-backoff retries on transient failures."""
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(url)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.StreamError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Internal: GraphQL
    # ------------------------------------------------------------------

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query against the Ponder indexer.

        Returns the ``data`` portion of the response.  Raises
        ``RuntimeError`` if the response contains GraphQL errors.
        """
        body: dict[str, Any] = {"query": query}
        if variables is not None:
            body["variables"] = variables

        resp = await self._post_with_retry(self._graphql_url, body)
        payload = resp.json()

        if payload.get("errors"):
            logger.error("GraphQL errors: %s", payload["errors"])
            raise RuntimeError(f"GraphQL errors: {payload['errors']}")

        return payload.get("data", {})

    # ------------------------------------------------------------------
    # Internal: RPC
    # ------------------------------------------------------------------

    async def _eth_call(self, to: str, data: str) -> str:
        """Execute a read-only ``eth_call`` via JSON-RPC.

        Returns the hex-encoded result string (with ``0x`` prefix).
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"],
        }
        resp = await self._post_with_retry(self._rpc_url, payload)
        result = resp.json()
        if "error" in result:
            raise RuntimeError(f"RPC error: {result['error']}")
        return result.get("result", "0x")

    # ------------------------------------------------------------------
    # Public API: pet queries
    # ------------------------------------------------------------------

    async def get_all_pets(self, limit: int = 500, min_score: int = 0) -> list[FrenPet]:
        """Fetch pets from Ponder GraphQL, ordered by score descending.

        Parameters
        ----------
        limit:
            Maximum number of pets to return per page.
        min_score:
            Minimum display-scale score filter.  Passed to Ponder as
            a raw ``score_gt`` string (``"0"`` by default).
        """
        score_filter = str(min_score)
        query = """
        query($limit: Int!, $score_filter: BigInt!) {
            pets(
                limit: $limit,
                orderBy: "score",
                orderDirection: "desc",
                where: { score_gt: $score_filter }
            ) {
                items {
                    """ + _PET_FIELDS + """
                }
            }
        }
        """
        variables = {"limit": limit, "score_filter": score_filter}
        data = await self._graphql(query, variables)
        items = data.get("pets", {}).get("items", [])
        return [FrenPet.from_api(item) for item in items]

    async def get_pet(self, pet_id: int) -> FrenPet | None:
        """Fetch a single pet by ID from Ponder.

        Returns ``None`` if the pet does not exist.
        """
        query = """
        query($pet_id: Int!) {
            pet(id: $pet_id) {
                """ + _PET_FIELDS + """
            }
        }
        """
        variables = {"pet_id": pet_id}
        data = await self._graphql(query, variables)
        pet_data = data.get("pet")
        if not pet_data:
            return None
        return FrenPet.from_api(pet_data)

    async def get_pets_by_owner(self, owner_address: str) -> list[FrenPet]:
        """Fetch all pets owned by a wallet address.

        Parameters
        ----------
        owner_address:
            Ethereum address (hex string, case-insensitive).
        """
        addr = owner_address
        query = """
        query($owner: String!) {
            pets(
                limit: 100,
                orderBy: "score",
                orderDirection: "desc",
                where: { owner: $owner }
            ) {
                items {
                    """ + _PET_FIELDS + """
                }
            }
        }
        """
        variables = {"owner": addr}
        data = await self._graphql(query, variables)
        items = data.get("pets", {}).get("items", [])
        return [FrenPet.from_api(item) for item in items]

    # ------------------------------------------------------------------
    # Public API: attack events
    # ------------------------------------------------------------------

    async def get_recent_attacks(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent Attack events.

        Attempts to query Ponder first via a GraphQL ``attacks`` table.
        If the indexer does not expose an attacks entity, falls back to
        reading raw RPC logs filtered by the Attack event topic.

        Returns a list of dicts with keys:
        ``attacker_id``, ``defender_id``, ``attacker_won``, ``timestamp``.
        """
        # --- Try Ponder first ---
        try:
            return await self._get_attacks_ponder(limit)
        except Exception as exc:
            logger.info(
                "Ponder attacks query failed (%s), falling back to RPC logs", exc
            )

        # --- Fallback: RPC getLogs ---
        return await self._get_attacks_rpc(limit)

    async def _get_attacks_ponder(self, limit: int) -> list[dict[str, Any]]:
        """Query the Ponder ``attacks`` entity."""
        query = """
        query($limit: Int!) {
            attacks(
                limit: $limit,
                orderBy: "createdAt",
                orderDirection: "desc"
            ) {
                items {
                    attackerId targetId winnerId loserId won createdAt
                    attackPoints defensePoints
                }
            }
        }
        """
        variables = {"limit": limit}
        data = await self._graphql(query, variables)
        items = data.get("attacks", {}).get("items", [])
        results = []
        for item in items:
            attacker_id = int(item["attackerId"])
            attacker_won = attacker_id == int(item.get("winnerId", 0))
            # 'won' is the raw on-chain score transferred (not a boolean).
            # Always in raw 12-decimal format, divide by 1e12 for display.
            won_score_raw = int(item.get("won", 0))
            won_score = won_score_raw // 1_000_000_000_000
            points_delta = won_score if attacker_won else -won_score
            results.append({
                "attacker_id": attacker_id,
                "defender_id": int(item["targetId"]),
                "attacker_won": attacker_won,
                "timestamp": int(item["createdAt"]),
                "points_delta": points_delta,
            })
        return results

    async def _get_attacks_rpc(self, limit: int) -> list[dict[str, Any]]:
        """Read Attack event logs from Base RPC as a fallback.

        Scans the last 2000 blocks for Attack events on the Diamond
        contract and returns up to ``limit`` results.
        """
        # Get current block number
        block_resp = await self._post_with_retry(
            self._rpc_url,
            {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
        )
        current_block = int(block_resp.json()["result"], 16)
        from_block = hex(max(0, current_block - 2000))

        # Fetch logs
        log_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getLogs",
            "params": [
                {
                    "address": self.DIAMOND,
                    "topics": [_ATTACK_EVENT_TOPIC],
                    "fromBlock": from_block,
                    "toBlock": "latest",
                }
            ],
        }
        resp = await self._post_with_retry(self._rpc_url, log_payload)
        logs = resp.json().get("result", [])

        attacks: list[dict[str, Any]] = []
        for log in logs[-limit:]:
            # Attack(uint256 attacker, uint256 defender, bool won)
            # Topics: [event_sig, attacker_id, defender_id]
            # Data: bool won encoded as uint256
            topics = log.get("topics", [])
            data_hex = log.get("data", "0x")
            if len(topics) >= 3:
                attacker_id = int(topics[1], 16)
                defender_id = int(topics[2], 16)
                attacker_won = int(data_hex, 16) != 0 if data_hex != "0x" else False
                # Estimate timestamp from block number (not exact, but acceptable)
                block_num = int(log.get("blockNumber", "0x0"), 16)
                attacks.append(
                    {
                        "attacker_id": attacker_id,
                        "defender_id": defender_id,
                        "attacker_won": attacker_won,
                        "timestamp": block_num,  # block number as proxy
                    }
                )

        return attacks

    # ------------------------------------------------------------------
    # Public API: on-chain reads
    # ------------------------------------------------------------------

    async def get_training_data(self, pet_id: int) -> list[int]:
        """Read ``getTrainingData(petId)`` via ``eth_call`` on the Diamond.

        The function selector is ``0xe1cb2317``.  Returns a list of 12
        ``uint256`` values decoded from the ABI-encoded response.
        """
        data_hex = hex(pet_id)[2:].zfill(64)
        hex_result = await self._eth_call(
            self.DIAMOND,
            f"0xe1cb2317{data_hex}",
        )
        # Strip 0x prefix and split into 64-char (32-byte) chunks
        raw = hex_result[2:]
        values: list[int] = []
        for i in range(0, len(raw), 64):
            chunk = raw[i : i + 64]
            if chunk:
                values.append(int(chunk, 16))
        return values

    # ------------------------------------------------------------------
    # Public API: wallet reward reads (Diamond contract)
    # ------------------------------------------------------------------

    async def get_pending_eth(self, pet_id: int) -> int:
        """Call pendingEth(uint256) -> uint256 (wei)."""
        selector = "0xccc73973"  # keccak256("pendingEth(uint256)")[:4]
        data = selector + hex(pet_id)[2:].zfill(64)
        result = await self._eth_call(self.DIAMOND, data)
        return int(result, 16)

    async def get_eth_owed(self, pet_id: int) -> int:
        """Call ethOwed(uint256) -> uint256 (wei)."""
        selector = "0xb835613c"  # keccak256("ethOwed(uint256)")[:4]
        data = selector + hex(pet_id)[2:].zfill(64)
        result = await self._eth_call(self.DIAMOND, data)
        return int(result, 16)

    async def get_fp_owed(self, pet_id: int) -> int:
        """Call fpOwed(uint256) -> uint256 (wei)."""
        selector = "0x5142a32d"  # keccak256("fpOwed(uint256)")[:4]
        data = selector + hex(pet_id)[2:].zfill(64)
        result = await self._eth_call(self.DIAMOND, data)
        return int(result, 16)

    async def get_fp_per_second(self, pet_id: int) -> int:
        """Call calculateFpPerSecond(uint256) -> uint256."""
        selector = "0xa4af7db8"  # keccak256("calculateFpPerSecond(uint256)")[:4]
        data = selector + hex(pet_id)[2:].zfill(64)
        result = await self._eth_call(self.DIAMOND, data)
        return int(result, 16)

    async def get_user_shares(self, address: str) -> int:
        """Call userShares(address) -> uint256."""
        selector = "0xde69b3aa"  # keccak256("userShares(address)")[:4]
        addr_padded = address.lower().replace("0x", "").zfill(64)
        data = selector + addr_padded
        result = await self._eth_call(self.DIAMOND, data)
        return int(result, 16)

    async def get_total_shares(self) -> int:
        """Call totalShares() -> uint256."""
        selector = "0x3a98ef39"  # keccak256("totalShares()")[:4]
        result = await self._eth_call(self.DIAMOND, selector)
        return int(result, 16)

    async def get_total_fp_in_pool(self) -> int:
        """Call totalFpInPool() -> uint256."""
        selector = "0x6845b28e"  # keccak256("totalFpInPool()")[:4]
        result = await self._eth_call(self.DIAMOND, selector)
        return int(result, 16)

    # ------------------------------------------------------------------
    # Public API: FP reward pool
    # ------------------------------------------------------------------

    FP_TOKEN = "0xff0c532fdb8cd566ae169c1cb157ff2bdc83e105"

    async def get_fp_reward_pool(self) -> float:
        """Read FP balance of the Diamond contract (reward pool).

        FP Token: 0xff0c532fdb8cd566ae169c1cb157ff2bdc83e105
        Diamond:  0x0e22b5f3e11944578b37ed04f5312dfc246f443c
        Uses balanceOf(address) selector 0x70a08231.
        Returns balance in FP (divided by 1e18).
        """
        try:
            # balanceOf(address) — pad Diamond address to 32 bytes
            padded_address = self.DIAMOND[2:].lower().zfill(64)
            calldata = f"0x70a08231{padded_address}"
            hex_result = await self._eth_call(self.FP_TOKEN, calldata)
            raw = hex_result[2:] if hex_result.startswith("0x") else hex_result
            if not raw:
                return 0.0
            return int(raw, 16) / 1e18
        except Exception as exc:
            logger.warning("Failed to read FP reward pool: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # AutoPet indexer DB (local SQLite — full population)
    # ------------------------------------------------------------------

    def get_all_pets_from_indexer(self) -> list[FrenPet]:
        """Read ALL pets from the local autopet indexer SQLite DB.

        This is synchronous but fast (~5ms for ~4000 pets). Returns the
        full population, not limited to top 500 like Ponder.
        Falls back to empty list if the DB doesn't exist.
        """
        db_path = Path(self._indexer_db)
        if not db_path.exists():
            logger.debug("Indexer DB not found at %s", db_path)
            return []

        now = time.time()
        pets: list[FrenPet] = []
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, score, atk, defense, last_attacked, "
                "last_attack_used, shield_expires, status, updated_at "
                "FROM indexed_pets ORDER BY score DESC"
            )
            for row in cursor:
                pets.append(FrenPet(
                    id=row["id"],
                    score=row["score"],
                    attack_points=row["atk"],
                    defense_points=row["defense"],
                    level=0,
                    status=row["status"],
                    last_attacked=row["last_attacked"],
                    last_attack_used=row["last_attack_used"],
                    shield_expires=row["shield_expires"],
                    time_until_starving=0,  # not in indexer DB
                    staking_perks_until=0,
                    wheel_last_spin=0,
                    pet_wins=0,
                    win_qty=0,
                    loss_qty=0,
                    shrooms=0,
                    name=f"Pet #{row['id']}",
                    owner="",
                ))
            conn.close()
            logger.info("Indexer DB: loaded %d pets", len(pets))
        except Exception as exc:
            logger.warning("Failed to read indexer DB: %s", exc)

        return pets

    # ------------------------------------------------------------------
    # AutoPet local API (http://127.0.0.1:8420)
    # ------------------------------------------------------------------

    async def get_autopet_pets(self) -> list[FrenPet]:
        """Fetch managed pets from the local autopet API server."""
        try:
            resp = await self._get_with_retry(
                f"{self._autopet_url}/api/pets"
            )
            data = resp.json()
            now = time.time()
            pets: list[FrenPet] = []
            for p in data:
                pets.append(FrenPet(
                    id=p["pet_id"],
                    score=int(p.get("points", 0) / 1e12) if p.get("points", 0) > 1e15 else int(p.get("points", 0)),
                    attack_points=p.get("atk", 0),
                    defense_points=p.get("defense", 0),
                    level=0,
                    status=0,
                    last_attacked=0,
                    last_attack_used=0,
                    shield_expires=0,
                    time_until_starving=int(now + p.get("tod_remaining_hours", 0) * 3600),
                    staking_perks_until=0,
                    wheel_last_spin=0,
                    pet_wins=p.get("wins", 0),
                    win_qty=p.get("wins", 0),
                    loss_qty=p.get("losses", 0),
                    shrooms=0,
                    name=f"Pet #{p['pet_id']}",
                    owner="",
                ))
            logger.info("AutoPet API: fetched %d managed pets", len(pets))
            return pets
        except Exception as exc:
            logger.debug("AutoPet API unavailable: %s", exc)
            return []

    async def get_autopet_battles(self) -> list[dict]:
        """Fetch recent battle history from the local autopet API."""
        try:
            resp = await self._get_with_retry(
                f"{self._autopet_url}/api/battle/stats/all"
            )
            data = resp.json()
            battles = data.get("recent", data) if isinstance(data, dict) else data
            return battles[:50] if isinstance(battles, list) else []
        except Exception as exc:
            logger.debug("AutoPet battles unavailable: %s", exc)
            return []

    async def get_autopet_actions(self) -> list[dict]:
        """Fetch pending actions from the local autopet API."""
        try:
            resp = await self._get_with_retry(
                f"{self._autopet_url}/api/actions/pending"
            )
            return resp.json() if isinstance(resp.json(), list) else []
        except Exception as exc:
            logger.debug("AutoPet actions unavailable: %s", exc)
            return []

    async def get_autopet_sniper(self) -> dict:
        """Fetch sniper queue from the local autopet API."""
        try:
            resp = await self._get_with_retry(
                f"{self._autopet_url}/api/sniper/queue"
            )
            return resp.json()
        except Exception as exc:
            logger.debug("AutoPet sniper unavailable: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Unified snapshot
    # ------------------------------------------------------------------

    async def fetch_snapshot(
        self,
        wallet_address: str | None = None,
        remote_only: bool = False,
    ) -> FrenPetSnapshot:
        """Fetch everything needed for a dashboard refresh.

        Runs queries concurrently where possible.  Individual failures
        are logged and replaced with safe defaults so the dashboard
        always receives a usable snapshot.

        Parameters
        ----------
        wallet_address:
            If provided, the snapshot includes the user's managed pets.
            When ``None`` (spectator mode), ``managed_pets`` is empty.
        remote_only:
            When ``True``, skip local sources (indexer DB, AutoPet API)
            and fetch everything from remote endpoints only.
        """
        now = time.time()

        if not remote_only:
            # Try indexer DB first for full population (sync, ~5ms)
            all_pets = self.get_all_pets_from_indexer()
        else:
            all_pets = []

        # Fall back to Ponder if indexer DB unavailable or skipped
        if not all_pets:
            try:
                all_pets = await self.get_all_pets(limit=500)
            except Exception as exc:
                logger.error("Failed to fetch all_pets from Ponder: %s", exc)
                all_pets = []

        # Fetch managed pets from autopet local API (has live stats)
        # Fall back to Ponder owner query
        managed_pets: list[FrenPet] = []
        if not remote_only:
            try:
                managed_pets = await self.get_autopet_pets()
            except Exception:
                pass
        if not managed_pets and wallet_address:
            try:
                managed_pets = await self.get_pets_by_owner(wallet_address)
            except Exception as exc:
                logger.error("Failed to fetch owner pets: %s", exc)

        # Compute population stats
        population = FrenPetPopulation.from_pets(all_pets, now=now)

        # Top 10 by score (already sorted desc from the query)
        top_pets = all_pets[:10]

        # FP reward pool (graceful — returns 0.0 on failure)
        fp_reward_pool = 0.0
        try:
            fp_reward_pool = await self.get_fp_reward_pool()
        except Exception as exc:
            logger.warning("Failed to fetch FP reward pool: %s", exc)

        return FrenPetSnapshot(
            population=population,
            managed_pets=tuple(managed_pets),
            top_pets=tuple(top_pets),
            fp_reward_pool=fp_reward_pool,
            fetched_at=now,
        )
