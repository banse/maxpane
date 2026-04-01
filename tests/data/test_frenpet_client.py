"""Tests for FrenPet models and client.

Covers model construction, score conversion, population stat computation,
and mocked HTTP responses for all client methods.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from maxpane_dashboard.data.frenpet_models import (
    FrenPet,
    FrenPetPopulation,
    FrenPetSnapshot,
    normalize_score,
)
from maxpane_dashboard.data.frenpet_client import FrenPetClient


# ---------------------------------------------------------------------------
# Fixtures: sample API data
# ---------------------------------------------------------------------------

def _make_pet_api_dict(
    pet_id: int = 1,
    score: int | str = 5000,
    *,
    status: int = 0,
    last_attacked: int = 0,
    shield_expires: int = 0,
    time_until_starving: int = 0,
    owner: str = "0xabc",
    name: str = "TestPet",
) -> dict:
    """Build a raw Ponder-style camelCase pet dict."""
    return {
        "id": pet_id,
        "score": score,
        "attackPoints": 10,
        "defensePoints": 5,
        "level": 3,
        "status": status,
        "lastAttacked": last_attacked,
        "lastAttackUsed": 0,
        "shieldExpires": shield_expires,
        "timeUntilStarving": time_until_starving,
        "stakingPerksUntil": 0,
        "wheelLastSpin": 0,
        "petWins": 2,
        "winQty": 10,
        "lossQty": 3,
        "shrooms": 100,
        "name": name,
        "owner": owner,
    }


@pytest.fixture
def sample_pet_data() -> dict:
    return _make_pet_api_dict()


@pytest.fixture
def now() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# Score conversion tests
# ---------------------------------------------------------------------------

class TestScoreConversion:
    def test_small_score_passes_through(self):
        assert normalize_score(5000) == 5000

    def test_raw_score_divided(self):
        """Scores above 1e15 are raw 12-decimal values."""
        raw = 5_000_000_000_000_000_000  # 5e18 -> 5_000_000
        assert normalize_score(raw) == 5_000_000

    def test_string_score_converted(self):
        assert normalize_score("12345") == 12345

    def test_string_raw_score_divided(self):
        raw_str = "5000000000000000000"  # 5e18
        assert normalize_score(raw_str) == 5_000_000

    def test_zero_score(self):
        assert normalize_score(0) == 0

    def test_boundary_score(self):
        """Score exactly at 1e15 threshold passes through."""
        assert normalize_score(1_000_000_000_000_000) == 1_000_000_000_000_000

    def test_just_above_threshold(self):
        """Score just above 1e15 is divided."""
        raw = 1_000_000_000_000_001
        assert normalize_score(raw) == 1000


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------

class TestFrenPetModel:
    def test_from_api_basic(self, sample_pet_data: dict):
        pet = FrenPet.from_api(sample_pet_data)
        assert pet.id == 1
        assert pet.score == 5000
        assert pet.attack_points == 10
        assert pet.defense_points == 5
        assert pet.level == 3
        assert pet.name == "TestPet"
        assert pet.owner == "0xabc"

    def test_from_api_raw_score(self):
        data = _make_pet_api_dict(score=2_000_000_000_000_000_000)
        pet = FrenPet.from_api(data)
        assert pet.score == 2_000_000

    def test_from_api_string_fields(self):
        """Ponder sometimes returns numeric fields as strings."""
        data = _make_pet_api_dict(score="9999", pet_id=42)
        data["id"] = "42"
        pet = FrenPet.from_api(data)
        assert pet.id == 42
        assert pet.score == 9999

    def test_frozen(self, sample_pet_data: dict):
        pet = FrenPet.from_api(sample_pet_data)
        with pytest.raises(Exception):
            pet.score = 999  # type: ignore[misc]

    def test_missing_optional_fields_default(self):
        """Fields missing from the API dict use safe defaults."""
        minimal = {"id": 1, "name": "Min", "owner": "0x0"}
        pet = FrenPet.from_api(minimal)
        assert pet.score == 0
        assert pet.attack_points == 0
        assert pet.shrooms == 0


# ---------------------------------------------------------------------------
# Population stat tests
# ---------------------------------------------------------------------------

class TestFrenPetPopulation:
    def test_all_active(self, now: int):
        future = now + 86400
        pets = [
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=i, status=0, time_until_starving=future
            ))
            for i in range(5)
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        assert pop.total == 5
        assert pop.active == 5
        assert pop.hibernated == 0

    def test_hibernated_by_status(self, now: int):
        future = now + 86400
        pets = [
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=1, status=2, time_until_starving=future
            )),
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=2, status=0, time_until_starving=future
            )),
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        assert pop.active == 1
        assert pop.hibernated == 1

    def test_hibernated_by_starving(self, now: int):
        """A pet with status=0 but past time_until_starving is hibernated."""
        past = now - 3600
        pets = [
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=1, status=0, time_until_starving=past
            )),
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        assert pop.active == 0
        assert pop.hibernated == 1

    def test_shielded_count(self, now: int):
        future = now + 86400
        pets = [
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=1, shield_expires=future, time_until_starving=future
            )),
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=2, shield_expires=now - 1, time_until_starving=future
            )),
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        assert pop.shielded == 1

    def test_in_cooldown_count(self, now: int):
        future = now + 86400
        recently_attacked = now - 1800  # 30 min ago
        long_ago = now - 7200  # 2 hours ago
        pets = [
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=1, last_attacked=recently_attacked, time_until_starving=future
            )),
            FrenPet.from_api(_make_pet_api_dict(
                pet_id=2, last_attacked=long_ago, time_until_starving=future
            )),
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        assert pop.in_cooldown == 1

    def test_empty_population(self, now: int):
        pop = FrenPetPopulation.from_pets([], now=now)
        assert pop.total == 0
        assert pop.active == 0
        assert pop.hibernated == 0
        assert pop.shielded == 0
        assert pop.in_cooldown == 0

    def test_pets_stored_as_tuple(self, now: int):
        future = now + 86400
        pets = [
            FrenPet.from_api(_make_pet_api_dict(pet_id=1, time_until_starving=future)),
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        assert isinstance(pop.pets, tuple)
        assert len(pop.pets) == 1


class TestFrenPetSnapshot:
    def test_frozen(self, now: int):
        future = now + 86400
        pets = [
            FrenPet.from_api(_make_pet_api_dict(pet_id=1, time_until_starving=future)),
        ]
        pop = FrenPetPopulation.from_pets(pets, now=now)
        snap = FrenPetSnapshot(
            population=pop,
            managed_pets=(),
            top_pets=tuple(pets),
            fetched_at=float(now),
        )
        assert snap.fetched_at == float(now)
        with pytest.raises(Exception):
            snap.fetched_at = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Client HTTP tests (mocked)
# ---------------------------------------------------------------------------

def _mock_graphql_response(data: dict) -> httpx.Response:
    """Build a fake httpx.Response wrapping GraphQL data."""
    import json
    return httpx.Response(
        status_code=200,
        json={"data": data},
        request=httpx.Request("POST", "https://api.pet.game"),
    )


def _mock_rpc_response(result: str) -> httpx.Response:
    """Build a fake httpx.Response wrapping an eth_call result."""
    return httpx.Response(
        status_code=200,
        json={"jsonrpc": "2.0", "id": 1, "result": result},
        request=httpx.Request("POST", "https://mainnet.base.org"),
    )


class TestFrenPetClientGetAllPets:
    @pytest.mark.asyncio
    async def test_returns_parsed_pets(self):
        pet_data = [
            _make_pet_api_dict(pet_id=1, score=5000, name="Alpha"),
            _make_pet_api_dict(pet_id=2, score=3000, name="Beta"),
        ]
        mock_resp = _mock_graphql_response({"pets": {"items": pet_data}})

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            pets = await client.get_all_pets(limit=100)

        assert len(pets) == 2
        assert pets[0].name == "Alpha"
        assert pets[1].name == "Beta"

    @pytest.mark.asyncio
    async def test_empty_response(self):
        mock_resp = _mock_graphql_response({"pets": {"items": []}})

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            pets = await client.get_all_pets()

        assert pets == []


class TestFrenPetClientGetPet:
    @pytest.mark.asyncio
    async def test_found(self):
        pet_data = _make_pet_api_dict(pet_id=42, name="Solo")
        mock_resp = _mock_graphql_response({"pet": pet_data})

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            pet = await client.get_pet(42)

        assert pet is not None
        assert pet.id == 42
        assert pet.name == "Solo"

    @pytest.mark.asyncio
    async def test_not_found(self):
        mock_resp = _mock_graphql_response({"pet": None})

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            pet = await client.get_pet(99999)

        assert pet is None


class TestFrenPetClientGetPetsByOwner:
    @pytest.mark.asyncio
    async def test_returns_owner_pets(self):
        pet_data = [
            _make_pet_api_dict(pet_id=1, owner="0xabc"),
            _make_pet_api_dict(pet_id=2, owner="0xabc"),
        ]
        mock_resp = _mock_graphql_response({"pets": {"items": pet_data}})

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            pets = await client.get_pets_by_owner("0xABC")

        assert len(pets) == 2
        assert all(p.owner == "0xabc" for p in pets)


class TestFrenPetClientGetTrainingData:
    @pytest.mark.asyncio
    async def test_parses_uint256_values(self):
        # 3 uint256 values: 10, 20, 30
        result_hex = (
            "0x"
            + "000000000000000000000000000000000000000000000000000000000000000a"
            + "0000000000000000000000000000000000000000000000000000000000000014"
            + "000000000000000000000000000000000000000000000000000000000000001e"
        )
        mock_resp = _mock_rpc_response(result_hex)

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            values = await client.get_training_data(pet_id=1)

        assert values == [10, 20, 30]

    @pytest.mark.asyncio
    async def test_empty_result(self):
        mock_resp = _mock_rpc_response("0x")

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(return_value=mock_resp)

            values = await client.get_training_data(pet_id=1)

        assert values == []


class TestFrenPetClientFetchSnapshot:
    @pytest.mark.asyncio
    async def test_spectator_mode(self):
        """Without a wallet address, managed_pets should be empty."""
        now = int(time.time())
        future = now + 86400
        pets = [
            FrenPet(id=1, score=9000, attack_points=10, defense_points=10,
                    level=1, status=0, last_attacked=0, last_attack_used=0,
                    shield_expires=0, time_until_starving=future,
                    staking_perks_until=0, wheel_last_spin=0, pet_wins=0,
                    win_qty=0, loss_qty=0, shrooms=0, name="Pet #1", owner=""),
            FrenPet(id=2, score=7000, attack_points=8, defense_points=8,
                    level=1, status=0, last_attacked=0, last_attack_used=0,
                    shield_expires=0, time_until_starving=future,
                    staking_perks_until=0, wheel_last_spin=0, pet_wins=0,
                    win_qty=0, loss_qty=0, shrooms=0, name="Pet #2", owner=""),
        ]

        async with FrenPetClient() as client:
            # Mock: indexer returns pets, autopet API returns empty
            client.get_all_pets_from_indexer = lambda: pets
            client.get_autopet_pets = AsyncMock(return_value=[])

            snapshot = await client.fetch_snapshot()

        assert len(snapshot.managed_pets) == 0
        assert snapshot.population.total == 2
        assert len(snapshot.top_pets) == 2

    @pytest.mark.asyncio
    async def test_with_wallet(self):
        """With a wallet address, managed_pets should be populated."""
        now = int(time.time())
        future = now + 86400
        all_pets = [
            FrenPet(id=i, score=1000*i, attack_points=10, defense_points=10,
                    level=1, status=0, last_attacked=0, last_attack_used=0,
                    shield_expires=0, time_until_starving=future,
                    staking_perks_until=0, wheel_last_spin=0, pet_wins=0,
                    win_qty=0, loss_qty=0, shrooms=0, name=f"Pet #{i}", owner="")
            for i in range(1, 4)
        ]
        managed = [all_pets[0]]

        async with FrenPetClient() as client:
            client.get_all_pets_from_indexer = lambda: all_pets
            client.get_autopet_pets = AsyncMock(return_value=managed)

            snapshot = await client.fetch_snapshot(wallet_address="0xUser")

        assert len(snapshot.managed_pets) == 1
        assert snapshot.population.total == 3


class TestFrenPetClientRetry:
    @pytest.mark.asyncio
    async def test_retries_on_server_error(self):
        """Client retries on 500 and eventually succeeds."""
        error_resp = httpx.Response(
            status_code=500,
            text="Internal Server Error",
            request=httpx.Request("POST", "https://api.pet.game"),
        )
        success_resp = _mock_graphql_response({"pet": _make_pet_api_dict(pet_id=1)})

        call_count = 0

        async def mock_post(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return error_resp
            return success_resp

        async with FrenPetClient() as client:
            client._client = AsyncMock(spec=httpx.AsyncClient)
            client._client.post = AsyncMock(side_effect=mock_post)

            pet = await client.get_pet(1)

        assert pet is not None
        assert call_count == 3
