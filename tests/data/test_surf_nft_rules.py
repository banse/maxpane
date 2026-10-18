"""Behavioral regression checks for reviewed, fail-closed mint rules."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import maxpane_dashboard.data.surf_nft_rules.rules as rules
from maxpane_dashboard.data.surf_nft_rules.rules import apply_rules, classify_template, RULES


class MintRulesTest(unittest.TestCase):
    def evidence(self, launch, reads, **extra):
        rule = next(x for x in RULES.values() if x.get("launchNumber") == launch)
        return {"chainId": rule["chainId"], "address": rule["contract"],
                "codePresent": True, "codeHash": rule["codeHash"],
                "reads": reads, "stats": {}, "readBlock": 123,
                "readTimestamp": "2026-10-16T20:34:47Z", **extra}

    def apply(self, launch, reads, **extra):
        chain = self.evidence(launch, reads, **extra)
        getter = {1671: "VIMD", 1076: "coin", 1556: "token"}.get(launch)
        if getter:
            address = "0x"+"ab"*20
            chain["reads"][getter] = address
            chain["tokenMetadata"] = {str(chain["chainId"])+":"+address: {"chainId":chain["chainId"],"address":address,"codePresent":True,"readBlock":123,"decimals":18}}
        return apply_rules({}, chain, "2026-10-16T20:35:00Z")

    def test_changed_bytecode_rejects_claimed_free_and_open(self):
        chain = self.evidence(1416, {"totalMinted": 2}, codeHash="0x" + "99" * 32)
        record = {"idmdBenefit": {"status": "yes"}, "mint": {"state": "open", "publicPrice": "0", "reportedTerms": ["free"]}}
        original = copy.deepcopy(record)
        result = apply_rules(record, chain, "2026-10-16T20:35:00Z")
        self.assertEqual(result["idmdBenefit"]["status"], "unknown")
        self.assertEqual(result["mint"]["state"], "unknown")
        self.assertIsNone(result["mint"]["publicPrice"])
        self.assertEqual(result["mint"]["reportedTerms"], ["free"])
        self.assertEqual(record, original)

    def test_imdenza_canonical_idmd_configuration(self):
        reads = {"totalMinted": 1, "identityMdCollection": "0x" + "0" * 40}
        self.assertEqual(self.apply(2000, reads)["idmdBenefit"]["status"], "no")
        reads["identityMdCollection"] = "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d"
        result = self.apply(2000, reads)
        self.assertEqual(result["idmdBenefit"]["status"], "yes")
        self.assertIn("unused", result["idmdBenefit"]["conditions"])
        self.assertEqual(result["stats"]["totalMinted"], 1)

    def test_free_anyone_is_not_exclusive_idmd(self):
        result = self.apply(1416, {"totalMinted": 0})
        self.assertEqual(result["idmdBenefit"]["status"], "yes")
        self.assertFalse(result["idmdBenefit"]["exclusive"])
        self.assertEqual(result["mint"]["publicPrice"], "0")
        self.assertFalse(result["mint"]["gasIncluded"])

    def test_idmd_entry_burn_is_paid(self):
        result = self.apply(1671, {"entryCount": 1, "ENTRY_END": 1792288847, "ENTRY_PRICE": 25_000 * 10**18})
        self.assertEqual(result["idmdBenefit"]["status"], "no")

        self.assertEqual(result["mint"]["publicPrice"], "25000")
        self.assertEqual(result["mint"]["currency"], "VIMD")
        self.assertEqual(result["mint"]["state"], "open")

    def test_ended_window_uses_pinned_block_time(self):
        reads = {"entryCount": 1, "ENTRY_END": 1792288847}
        result = self.apply(1671, reads, readTimestamp="2026-10-18T02:00:47Z")
        self.assertEqual(result["mint"]["state"], "ended")
        # A later wall clock does not rewrite historical reads as live state.
        chain = self.evidence(1671, reads)
        result = apply_rules({}, chain, "2027-01-01T00:00:00Z")
        self.assertEqual(result["mint"]["state"], "open")
        self.assertEqual(result["mint"]["asOf"], chain["readTimestamp"])

    def test_supply_exhaustion_prevents_free(self):
        result = self.apply(1416, {"totalMinted": 4096})
        self.assertEqual(result["mint"]["state"], "sold-out")
        self.assertEqual(result["idmdBenefit"]["status"], "no")

    def test_missing_live_getter_does_not_reuse_review_snapshot(self):
        self.assertEqual(self.apply(1416, {})["mint"]["state"], "unknown")
        self.assertEqual(self.apply(1756, {"totalMinted": 10})["mint"]["state"], "unknown")
        self.assertEqual(self.apply(1565, {"totalMinted": 29})["mint"]["state"], "unknown")

    def test_snapshot_proof_is_not_universal_idmd_benefit(self):
        result = self.apply(1343, {"totalSupply": 4, "buysPaused": False,
                                 "claimDeadline": 1794344615, "founderClaimed": 2, "founderCount": 49})
        self.assertEqual(result["idmdBenefit"]["status"], "conditional")
        self.assertFalse(result["idmdBenefit"]["exclusive"])
        self.assertIn("Merkle", result["idmdBenefit"]["conditions"])

    def test_worker_activity_requirement_preserved(self):
        result = self.apply(1565, {"totalMinted": 29, "publicMintOpen": True})
        self.assertEqual(result["idmdBenefit"]["status"], "conditional")
        self.assertIn("7 days", result["idmdBenefit"]["conditions"])
        self.assertIn("reporter", result["idmdBenefit"]["conditions"])

    def test_bmc_deployments_have_different_opening_gates(self):
        self.assertEqual(self.apply(1394, {"totalMinted": 0})["mint"]["state"], "open")
        self.assertEqual(self.apply(1425, {"totalMinted": 0})["mint"]["state"], "open")
        self.assertEqual(self.apply(1481, {"totalMinted": 0, "mintingOpen": False})["mint"]["state"], "not-started")

    def test_unreviewed_contract_is_unknown(self):
        result = apply_rules({}, {"chainId": 1, "address": "0x" + "12" * 20,
                                  "codePresent": True, "codeHash": "0x" + "34" * 32,
                                  "reads": {"mintPrice": 0, "paused": False}}, "2026-10-16T00:00:00Z")
        self.assertEqual(result["idmdBenefit"]["status"], "unknown")
        self.assertEqual(result["mint"]["state"], "unknown")

    def test_known_template_excluded_only_with_exact_code(self):
        chain = self.evidence(1631, {})
        self.assertIn("implementation", classify_template(chain))
        chain["codeHash"] = "0x" + "ab" * 32
        self.assertIsNone(classify_template(chain))

    def test_platform_fee_is_included_even_when_base_price_zero(self):
        rule = next(r for r in RULES.values() if r.get("adapter") == "loom")
        chain = {"chainId": 1, "address": rule["contract"], "codeHash": rule["codeHash"], "codePresent": True,
                 "readTimestamp": "2026-10-16T20:34:47Z", "reads": {"mintPrice": 0,
                 "PLATFORM_FEE": 500_000_000_000_000, "totalSupply": 5, "maxSupply": 10000,
                 "paused": False, "maxPerWallet": 5}}
        result = apply_rules({}, chain, chain["readTimestamp"])
        self.assertEqual(result["mint"]["publicPrice"], "0.0005")
        self.assertEqual(result["idmdBenefit"]["status"], "no")

    def test_missing_snapshot_time_never_claims_free_available(self):
        result = self.apply(1416, {"totalMinted": 1}, readTimestamp=None)
        self.assertEqual(result["mint"]["state"], "unknown")
        self.assertEqual(result["idmdBenefit"]["status"], "unknown")

    def test_founder_reservation_blocks_public_even_below_total_supply_cap(self):
        result = self.apply(1343, {"totalSupply": 951, "buysPaused": False,
                                 "publicSupply": 951, "founderOutstanding": 0, "reservedFounderSlots": 49,
                                 "claimDeadline": 1794344615, "founderClaimed": 0, "founderCount": 49})
        routes = {r["name"]: r for r in result["mint"]["routes"]}
        self.assertEqual(routes["Public mint"]["state"], "sold-out")
        self.assertEqual(routes["Founder snapshot claim"]["state"], "open")
        self.assertEqual(result["mint"]["state"], "open")

    def test_pepeolithic_released_leftovers_are_paid_not_free(self):
        result = self.apply(1076, {"totalSupply": 300, "startTime": 1791810000,
                                 "caveLength": 86400, "nextFree": 137,
                                 "unclaimedReleased": True, "floorPrice": 10000 * 10**18},
                            readTimestamp="2026-10-21T00:00:00Z")
        self.assertEqual(result["mint"]["state"], "open")
        self.assertEqual(result["idmdBenefit"]["status"], "no")
        self.assertEqual(result["mint"]["publicPrice"], "10000")

    def test_farm_snapshot_window_requires_fresh_bound_dependency(self):
        chain = self.evidence(1722, {"nextId": 115})
        rule = RULES[f"{chain['chainId']}:{chain['address']}"]
        dependency = {**rule["dependencies"]["StarterClaim"], "readBlock": 123, "codePresent": True, "codeReviewed": True,
                      "reads": {"launchTime": 1791967009, "root": "0x" + "12" * 32,
                                "freeRoot": "0x" + "34" * 32, "freeClaimEnds": 1794559009,
                                "freeClaimed": 1}}
        chain["dependencyReads"] = {"StarterClaim": dependency}
        result = apply_rules({}, chain, "2026-10-16T21:00:00Z")
        self.assertEqual(result["idmdBenefit"]["status"], "conditional")
        self.assertEqual(result["mint"]["start"], "2026-10-16T08:36:49Z")
        self.assertEqual(result["mint"]["end"], "2026-10-30T08:36:49Z")
        self.assertEqual(result["stats"]["totalMinted"], 114)
        dependency["readBlock"] = 122
        result = apply_rules({}, chain, "2026-10-16T21:00:00Z")
        self.assertEqual(result["idmdBenefit"]["status"], "unknown")

    def test_courier_requires_complete_event_scan_for_unconfigured(self):
        scan = {"complete": False, "fromBlock": 87504238, "toBlock": 123,
                "event": "ItemConfigured(uint256,uint256,uint256,uint256,bool,string)",
                "events": [], "items": []}
        self.assertEqual(self.apply(1556, {}, eventScan=scan)["mint"]["state"], "unknown")
        scan["complete"] = True
        self.assertEqual(self.apply(1556, {}, eventScan=scan)["mint"]["state"], "unconfigured")
        scan["events"] = [{"id": 1}]
        scan["items"] = [{"id": 1, "price": 3 * 10**18, "maxSupply": 10,
                           "minted": 2, "enabled": 1, "exists": 1, "perWalletLimit": 1}]
        result = self.apply(1556, {}, eventScan=scan)
        self.assertEqual(result["mint"]["state"], "open")
        self.assertEqual(result["mint"]["routes"][0]["price"], "3")
        self.assertEqual(result["idmdBenefit"]["status"], "no")
        scan["items"][0]["maxSupply"] = 0  # MoonShop explicitly treats zero as uncapped.
        self.assertEqual(self.apply(1556, {}, eventScan=scan)["mint"]["state"], "open")


    def test_seasons_auction_is_paid_and_mint_to_escrow_is_distinct(self):
        chain = self.evidence(1033, {"latestAuction": {"id": 1, "end": 1792288847,
                              "finalized": False, "occupied": 5, "highBid": 0}, "minimumBid": 1})
        rule = RULES[f"{chain['chainId']}:{chain['address']}"]
        chain["dependencyReads"] = {"Canvas": {**rule["dependencies"]["Canvas"], "readBlock": 123, "codePresent": True, "codeReviewed": True,
            "reads": {"currentSeason": 2, "seasonStart": 1792100000, "DURATION": 604800}}}
        token = "0x"+"ab"*20
        chain["reads"]["canvas"] = rule["dependencies"]["Canvas"]["address"]
        chain["dependencyReads"]["Canvas"]["reads"]["imd"] = token
        chain["tokenMetadata"] = {"4663:"+token: {"chainId":4663,"address":token,"codePresent":True,"readBlock":123,"decimals":18}}
        result = apply_rules({}, chain, "2026-10-16T21:00:00Z")
        self.assertEqual(result["mint"]["state"], "auction-open")
        self.assertEqual(result["mint"]["publicPrice"], "0.000000000000000001")
        self.assertEqual(result["idmdBenefit"]["status"], "no")
        self.assertEqual(result["stats"]["totalSupply"], 1)
        chain["reads"]["latestAuction"]["end"] = 1
        result = apply_rules({}, chain, "2026-10-16T21:00:00Z")
        self.assertEqual(result["mint"]["state"], "awaiting-finalization")
        self.assertIsNone(result["mint"]["publicPrice"])


class ReviewedBuildTest(unittest.TestCase):
    def setUp(self):
        self.job = {"id": "fixture", "objective": "Existing reviewed mainnet NFT code", "state": "completed",
                    "launch": {"chainId": None}, "nodes": [{"key": "audit_judge", "state": "accepted", "updatedAt": "2026-10-16T12:00:00Z"}]}
        self.rule = {"jobId": "fixture", "objectiveSha256": hashlib.sha256(self.job["objective"].encode()).hexdigest(),
                     "chainId": 4663, "name": "Example", "description": "Source checked", "stage": "Audited implementation",
                     "acceptedNodePattern": "^audit_judge$", "evidence": [{"url": "https://example.org/source"}], "reason": "Already deployed"}

    def test_recent_reviewed_implementation_qualifies(self):
        with patch.object(rules, "REVIEWED_BUILDS", [self.rule]):
            result = rules.reviewed_build(self.job, "2026-10-16T20:00:00Z")
        self.assertEqual(result["chainId"], 4663)
        self.assertEqual(result["lastMeaningfulAt"], "2026-10-16T12:00:00Z")

    def test_changed_objective_stale_review_or_dead_job_never_qualifies(self):
        with patch.object(rules, "REVIEWED_BUILDS", [self.rule]):
            self.assertIsNone(rules.reviewed_build(self.job, "2026-11-01T00:00:00Z"))
            for state in ("blocked", "failed", "parked", "cancelled"):
                self.assertIsNone(rules.reviewed_build({**self.job, "state": state}, "2026-10-16T20:00:00Z"))
            self.assertIsNone(rules.reviewed_build({**self.job, "objective": "changed"}, "2026-10-16T20:00:00Z"))
            self.assertIsNone(rules.reviewed_build({**self.job, "launch": {"chainId": 11155111}}, "2026-10-16T20:00:00Z"))
            self.assertIsNone(rules.reviewed_build({**self.job, "chainId": 11155111}, "2026-10-16T20:00:00Z"))

    def test_full_blackout_build_is_superseded_but_listing_summary_is_not(self):
        # Complete public job objective, not the truncated /jobs listing preview.
        job = {"id": "5ce56cbc-1158-455f-9c37-453120687a3a", "objective": "BLACKOUT v3: rework the contracts from job 80dc62dc (repo identity-md-launches/launch-1269-reports-v1-job-b9e37680-814c-4f17-b4bc-6) to the v3 design below. Build + tests + Robinhood fork + re-run sim. NO DEPLOY. Where v3 differs from the current code, v3 wins. Keep: no owner, no upgrades, bounded Params (max 10% step per 24h), pull payments, CEI, reentrancy guards, constructor-param addresses, team address 0x6d51cBE774aeAe4dd40bCA2560E9bc2695A0d007.\n\n1. EPOCHS (autonomous)\n- Epoch = 6h. A new epoch starts only when anyone calls advanceEpoch(); no mining accrues between epoch end and the call. Caller gets a bounty (default 0.001 ETH, Params 0.0005-0.003) from the heartbeat balance.\n- Swarm submits plans for the next 2 epochs: event type, severity within bounds, swarm random number, letter. Event randomness = hash(swarm number, block hash after the shift). No plan = contract picks the event from a fixed fallback table. Swarm never picks a player or district.\n- Claims available every epoch. Regulator script (dry run) + rule table: keep reward pool runway >= 14 days by tuning emission, tariff, pack pace and event mix within bounds.\n\n2. NO BURNS. Remove BurnVault. Every token spend (token packs, repair, electricity, overclock, merge, inventory expansion, token lobby) goes 100% to the reward pool. Withdrawal tax goes 100% to active farms next epoch.\n\n3. ETH SPLITS (fixed): packs 85% reward-pool buy / 13% team / 2% heartbeat. ETH lobby and progressive sell surcharge: same 85/13/2. Heartbeat balance capped at 1 ETH, excess to reward-pool buy. Generator removed.\n\n4. SWAP FEE. Preferred (if IMD launch allows a custom hook): 2% project fee = 1% team + 1% reward-pool buy, plus 0.25% network, plus the progressive sell surcharge (total cap 15%). Fallback (standard IMD hook): 1% split 0.5% team / 0.5% reward-pool buy, no surcharge. Build both paths, document which applies.\n\n5. PACKS. No quantity limits at all (remove wallet, global, token-pack daily limits). VRGDA price: start 0.010 ETH, floor 0.006, ceiling 0.03, target ~20 packs/hour, +1% per pack above pace at launch, ~2%/hour decay below pace (all Params). Token pack = current ETH price converted by 30-min TWAP with 10% discount. 3 items per pack, future block hash N+2, expiry fallback 3 Common GPUs.\nRarity: Common 70, Rare 22, Epic 6.7, Legendary 1, Mythic 0.3 (Mythic only for account level 10+, else that 0.3 goes to Common). Hash 10/28/80/250/800.\n\n6. ITEMS: 12 soulbound types (no transfers except into/out of own farm). Compute (100% of rarity hash): GPU 16%, ASIC 15%, FPGA 12%. Others mine at 60%: Power Supply 9, Battery 7, Solar Panel 7 (power); Fan 9, Liquid Cooling 6 (cooling); Router 6 (network); Motherboard 5, Server Rack 4, Surge Protector 4 (infra).\nRoom = 6 slots, any items, no duplicate type. Combos per room (hash bonuses add, cap +40%, values in Params):\nCompute Duo GPU+ASIC +10%; Triple Core GPU+ASIC+FPGA +20% (replaces Duo); Full Stack all 5 tags +15%; Airflow Fan+Server Rack +5% and fire halved; Cold Power PSU+Liquid Cooling electricity -15% and fire immune; Off-grid Solar+Battery electricity -20% and outage loses 50% not 100%; Clean Power Surge Protector+PSU surge immune; Locked Rack Router+Server Rack cable theft immune; rarity set 3+ same rarity +5/10/20/30% (R/E/L/M, highest only).\n\n7. INVENTORY, ROOMS, LEVELS\n- Inventory 15 slots; full inventory blocks opening packs. Exits: scrap item for ~1h of its yield (from pool), merge 3 identical into next rarity (up to Legendary), expand +5 slots for rising token price (to pool).\n- Items only in rooms. Room 1 at start, room 2 when farm is 3 days old, room 3 at level 7, room 4 at level 10. Remove room keys.\n- Account XP from active epochs, packs bought, tokens spent in game. Targets: level 3 ~1 day, level 5 ~48h, level 10 ~1 week. Equip gates: Epic level 3, Legendary level 5, Mythic level 10.\n\n8. MINING: emission from pool only (start 3.5%/day, sim picks bounds), per epoch by hashrate. Remove the 2% whale soft cap. Internal balance per player; in-game spend no tax +5% bonus; withdraw tax max(5%, 20% - 15%*age/7d). Durability 100, -0.5 per epoch, yield x durability, repair with tokens anytime. Overclock +10%/level up to 5. Electricity tariff start 15% of yield, bounds 10-30%.\n\n9. EVENTS (one per epoch or Calm; per-20-epoch caps: each negative <= 4, positives >= 4; same district outage cooldown 2 days):\nOutage: 30% of district farms get 0 this epoch. Power surge: 10% of district farms, random item -50 durability, 2% chance destroyed (never Legendary/Mythic). Server fire: rooms without cooling yield 0 this epoch, items -30 durability. Cable theft: 20% of district farms lose Router effects for 2 epochs or until token repair. Tax audit: top 10% farms by hash give 10% of this epoch's mining to the pool. Green wave: district +10% mining. Cheap tariff: city electricity -50% this epoch.\nAutomatic supply drop: if epoch pack sales >= 2x target pace, 5% random active farms get a free Common or Rare item (minted).\nLobby: ETH or token for own district lowers negative odds (min weight 0.40, 3-day half-life) and raises Green wave odds. Herald letter for every event and Params change.\n\n10. WEEKLY SEASON (permissionless finalize): best district by spend (packs+lobby+repairs) -> every active farm there gets a free Rare-guaranteed pack; lottery: 3 random active farms (tickets = active epochs) get an Epic+ item; best farm (in-game spend / yield) gets 1% of weekly emission.\n\n11. KEEP: referrals 5% of invitee mining on top, one level, set once, no self. Identity MD holders: only 1 free starter pack per tokenId, snapshot at token launch block, window hour 48 to day 16, Rare 92 / Epic 8, 50% mining until a paid pack. Remove all other holder perks.\n\n12. SIM (35 days, 6h steps, steady/hype/weak; ~900 NFT holders sell 35/50/65% of the swarm 10% in 14 days). Tune to: week-1 joiner payback <= 10 days in steady; game alive >= 3 weeks in steady and hype; event losses <= 10% of average farm weekly yield. Report payback by join week, stall day, team and heartbeat ETH, both swap-fee paths.\n\n13. TESTS: unit, fuzz, invariants (token conservation, no burns, splits, caps, level gates, inventory limit, soulbound, epoch cannot advance early, bounty paid once, fallback events, VRGDA bounds), Robinhood fork smoke, gas per action incl. advanceEpoch with many farms (must stay bounded).\n\n14. Ask a second contributor with fresh context to review; fix high and medium.\n\nDeliver: updated repo, report.md (what changed vs 80dc62dc, Params table with bounds, sim results, review findings, open questions), regulator.md."}
        self.assertIn("deployed FarmItems", rules.classify_superseded_build(job) or "")
        listing = job["objective"].split(" Build + tests", 1)[0] + "…"
        self.assertIsNone(rules.classify_superseded_build({**job, "objective": listing}))

    def test_supersession_is_bound_to_exact_job_and_objective(self):
        with patch.object(rules, "SUPERSEDED_BUILDS", [self.rule]):
            self.assertEqual(rules.classify_superseded_build(self.job), "Already deployed")
            self.assertIsNone(rules.classify_superseded_build({**self.job, "id": "other"}))
            self.assertIsNone(rules.classify_superseded_build({**self.job, "objective": "changed"}))


if __name__ == "__main__":
    unittest.main()


def test_erc20_amount_requires_observed_decimals_not_assumed_eighteen():
    chain = MintRulesTest().evidence(1671, {'entryCount': 1, 'ENTRY_END': 1792288847, 'ENTRY_PRICE': 25_000_000, 'VIMD': '0x'+'ab'*20})
    raw = apply_rules({}, chain, '2026-10-16T20:35:00Z')
    assert raw['mint']['publicPrice'] is None
    chain['tokenMetadata'] = {'1:0x'+'ab'*20: {'chainId':1, 'address':'0x'+'ab'*20, 'codePresent':True, 'readBlock':123, 'decimals':6}}
    assert apply_rules({}, chain, '2026-10-16T20:35:00Z')['mint']['publicPrice'] == '25'
    chain['tokenMetadata']['1:0x'+'ab'*20]['readBlock'] = 122
    assert apply_rules({}, chain, '2026-10-16T20:35:00Z')['mint']['publicPrice'] is None


def test_rule_dependencies_without_reviewed_code_cannot_certify_mint_gate():
    chain = MintRulesTest().evidence(1422, {}, dependencyReads={'HiveWars': {'chainId':1, 'address':'0xa7b90c8ec172fdbb03f885ab9d21a4e26d8db590', 'readBlock':123, 'reads':{'lastSettledEpoch':30}, 'codePresent':True, 'codeReviewed':False}})
    assert apply_rules({}, chain, '2026-10-16T20:35:00Z')['mint']['state'] == 'unknown'

import pytest
PARITY_PATH = Path(__file__).resolve().parents[1] / 'fixtures/surf/nft/rules/reviewed_cases.json'
PARITY_CASES = json.loads(PARITY_PATH.read_text())['cases']


@pytest.mark.parametrize('case', PARITY_CASES, ids=lambda case:case['adapter']+':'+case['identity'])
def test_every_reviewed_adapter_saved_snapshot(case):
    result = apply_rules({}, case['evidence'], '2026-10-17T00:00:00Z')
    assert result['mint']['state'] == case['expectedState']
    assert result['mint']['asOf'] == case['evidence'].get('readTimestamp')
    broken = copy.deepcopy(case['evidence'])
    broken['codeHash'] = '0x'+'fe'*32
    assert apply_rules({}, broken, '2026-10-17T00:00:00Z')['mint']['state'] == 'unknown'
    broken = copy.deepcopy(case['evidence'])
    broken['chainId'] = 31337
    assert apply_rules({}, broken, '2026-10-17T00:00:00Z')['idmdBenefit']['status'] == 'unknown'


def test_parity_fixture_covers_every_packaged_review():
    assert {case['identity'] for case in PARITY_CASES} == set(RULES)


def test_sparse_catalog_excludes_unchecked_and_wrong_chain_evidence():
    from maxpane_dashboard.data.surf_nft_rules.catalog import project_catalog
    address='0x'+'11'*20
    key='1:'+address
    candidate={'chainId':1,'address':address,'launch':{'id':'launch','chainId':1},'artifact':{},'jobIds':[],'launchIds':['launch']}
    raw={'coverage':{'complete':True},'jobDetails':{},'launches':[]}
    result=project_catalog(raw,{key:candidate},{},now_iso='2026-10-17T00:00:00Z')
    assert result['collections']==[] and result['coverage']['complete'] is False
    wrong={'chainId':4663,'address':address,'standard':'ERC-721','codePresent':True,'receiptSuccess':True,'deploymentConfirmed':True}
    assert project_catalog(raw,{key:candidate},{key:wrong},now_iso='2026-10-17T00:00:00Z')['collections']==[]


def test_future_accepted_build_activity_does_not_count_as_current():
    from maxpane_dashboard.data.surf_nft_rules.catalog import active_build
    job={'state':'completed','chainId':1,'objective':'Build an ERC721 NFT collection',
         'nodes':[{'key':'build','role':'implement','state':'accepted','updatedAt':'2027-01-01T00:00:00Z'}]}
    assert active_build(job,'2026-10-17T00:00:00Z')[0] is False


def test_factory_partial_coverage_cannot_become_complete_catalog():
    from maxpane_dashboard.data.surf_nft_rules.catalog import project_catalog
    address='0x'+'11'*20
    key='1:'+address
    candidate={'chainId':1,'address':address,'launch':{'id':'launch','chainId':1},'artifact':{},'jobIds':[],'launchIds':['launch']}
    evidence={'chainId':1,'address':address,'inspectionComplete':True,'detectionStatus':'unsupported',
              'factoryDiscovery':{'complete':False,'count':300,'nextCursor':256}}
    result=project_catalog({'coverage':{'complete':True},'jobDetails':{}},{key:candidate},{key:evidence},now_iso='2026-10-17T00:00:00Z')
    assert result['coverage']['complete'] is False


def test_confirmed_factory_source_details_keep_implementation_address():
    from maxpane_dashboard.data.surf_nft_rules.catalog import project_catalog
    address='0x'+'11'*20
    key='1:'+address
    candidate={'chainId':1,'address':address,'launch':{'id':'launch','chainId':1},'artifact':{},'jobIds':[],'launchIds':['launch']}
    evidence={'chainId':1,'address':address,'standard':'ERC-721','codePresent':True,'receiptSuccess':True,
              'deploymentConfirmed':True,'factoryCreationVerified':True,
              'factoryAddress':'0x'+'22'*20,'implementationAddress':'0x'+'33'*20}
    rows=project_catalog({'coverage':{},'jobDetails':{}},{key:candidate},{key:evidence},now_iso='2026-10-17T00:00:00Z')['collections']
    assert rows[0]['deployment']['factoryAddress']=='0x'+'22'*20
    assert rows[0]['deployment']['implementationAddress']=='0x'+'33'*20


def test_related_records_preserves_explicit_transitive_and_directed_joins():
    from maxpane_dashboard.data.surf_nft_rules.catalog import related_records

    a, b, c, d, missing, reverse, workflow, published = [
        f'00000000-0000-4000-8000-{i:012d}' for i in range(8)]
    commit = 'ab' * 20
    raw = {'jobDetails': {
        a: {'id': a, 'objective': f'Shared project {c}', 'delivery': {'commit': commit}},
        b: {'id': b, 'objective': f'Continue {c}'},
        c: {'id': c, 'objective': f'Continue {a}'},
        d: {'id': d, 'project': {'versions': [{'baseCommit': commit, 'jobId': missing}]}},
        reverse: {'id': reverse, 'objective': 'Shared project',
                  'project': {'versions': [{'jobId': a}]}},
    }, 'workflows': [{'contractsJobId': b, 'frontendJobId': workflow}],
        'publications': [{'id': 'job:' + workflow, 'versions': [{'jobId': published}]}]}
    original = copy.deepcopy(raw)
    jobs, sites, repos = related_records(raw, {a})
    assert [job['id'] for job in jobs] == sorted([a, b, c, d, missing, workflow, published])
    assert next(job for job in jobs if job['id'] == missing)['title'] == missing
    assert sites == repos == []
    assert raw == original
    assert {job['id'] for job in related_records(raw, {reverse})[0]} == set(raw['jobDetails']) | {
        missing, workflow, published}


def test_related_records_keeps_source_overwrite_and_repository_order():
    from maxpane_dashboard.data.surf_nft_rules.catalog import related_records

    job = '00000000-0000-4000-8000-000000000001'
    def site(name, identity='site'):
        return {'id': identity, 'url': f'https://{name}.example', 'status': 'published'}
    raw = {'jobDetails': {job: {'id': job, 'site': site('job')}}, 'publications': [
        {'contracts': [{'id': 'launch'}], 'versions': [
            {'jobId': job, 'repoUrl': 'https://github.com/test/first', 'commit': 'old'},
            {'repoUrl': 'https://github.com/test/second', 'commit': 'second'}],
         'sites': [site('first'), site('extra', 'other')]},
        {'id': 'job:' + job, 'versions': [
            {'repoUrl': 'https://github.com/test/first', 'commit': 'new'}],
         'sites': [site('second')]},
    ], 'sites': {'sites': [dict(site('final'), jobId=job)]}}
    jobs, sites, repos = related_records(raw, set(), launch_ids=['launch'])
    assert [entry['id'] for entry in jobs] == [job]
    assert [entry['url'] for entry in sites] == ['https://final.example', 'https://extra.example']
    assert repos == [{'url': 'https://github.com/test/first', 'commit': 'new'},
                     {'url': 'https://github.com/test/second', 'commit': 'second'}]


def test_catalog_parses_each_job_once_without_promoting_reported_mint_claims(monkeypatch):
    from unittest.mock import Mock
    import maxpane_dashboard.data.surf_nft_rules.catalog as catalog

    job = '00000000-0000-4000-8000-000000000001'
    claim = 'IDMD holders can claim a free NFT mint. Public mint price: 0 ETH.'
    raw = {'jobDetails': {job: {'id': job, 'objective': claim}}}
    candidates, checked = {}, {}
    for char in '12':
        address = '0x' + char * 40
        key = '1:' + address
        candidates[key] = {'chainId': 1, 'address': address, 'launch': {'id': char, 'chainId': 1},
                           'artifact': {}, 'jobIds': [job], 'launchIds': [char]}
        checked[key] = {'chainId': 1, 'address': address, 'standard': 'ERC-721',
                        'codePresent': True, 'receiptSuccess': True, 'deploymentConfirmed': True}
    pattern = Mock(wraps=catalog.JOB_ID)
    monkeypatch.setattr(catalog, 'JOB_ID', pattern)
    rows = catalog.project_catalog(raw, candidates, checked, now_iso='2026-10-17T00:00:00Z')['collections']
    assert len(rows) == 2
    for row in rows:
        assert [entry['id'] for entry in row['jobs']] == [job]
        assert row['mint']['state'] == 'unknown'
        assert row['mint']['publicPrice'] is None
        assert row['idmdBenefit']['status'] == 'unknown'
        assert 'Public mint price: 0 ETH.' in row['mint']['reportedTerms']
    assert pattern.findall.call_count == len(raw['jobDetails'])
