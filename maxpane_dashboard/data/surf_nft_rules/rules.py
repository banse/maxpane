"""Deterministic NFT mint rules from reviewed, commit-pinned source.

No network, LLM, credentials or transaction operations. ``apply_rules`` returns
a deep copy, never mutates its inputs, and only uses supplied current reads.
Rules match chain + contract + runtime code hash. A code hash pins code, not
storage or eligibility: wallet-specific balance/claim/proof checks remain due.
Mint states are evaluated at readTimestamp, never projected from cached storage
to a later wall clock. Adding a new source adapter requires manual review/tests.
"""
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ZERO = "0x" + "0" * 40
IDMD = "0x0000ec93127baa929e58e97dd0095a2bfb38ec1d"
_REVIEW_DATA = json.loads(Path(__file__).with_name("nft-reviewed.json").read_text())
RULES = {f"{r['chainId']}:{r['contract'].lower()}": r for r in _REVIEW_DATA["rules"]}
REVIEWED_BUILDS = _REVIEW_DATA.get("reviewedBuilds", [])
SUPERSEDED_BUILDS = _REVIEW_DATA.get("supersededBuilds", [])


def _matching_build(job, rules):
    digest = hashlib.sha256(str(job.get("objective", "")).encode()).hexdigest()
    return next((rule for rule in rules if rule["jobId"] == job.get("id")
                 and rule["objectiveSha256"] == digest), None)


def classify_superseded_build(job):
    """Reviewed repository ancestry proves this exact earlier build is deployed."""
    rule = _matching_build(job, SUPERSEDED_BUILDS)
    return rule["reason"] if rule else None


def reviewed_build(job, now_iso, days=7):
    """Narrow fallback for inspected NFT code with a recent completed audit.

    Matching an audit keyword alone never qualifies. The exact public request,
    pinned implementation and pinned report were reviewed together. New jobs or
    changed objectives require their own review. This does not certify readiness.
    """
    rule = _matching_build(job, REVIEWED_BUILDS)
    if not rule or rule.get("chainId") not in (1, 4663) or not 0 < days <= 365:
        return None
    launch = job.get("launch") or {}
    blocked = {"failed", "cancelled", "canceled", "abandoned", "rejected", "expired", "blocked", "parked"}
    if str(job.get("state", "")).lower() in blocked or str(launch.get("status", "")).lower() in blocked:
        return None
    explicit_chain = launch.get("chainId")
    if explicit_chain is None:
        explicit_chain = job.get("chainId")
    if explicit_chain is not None and explicit_chain != rule["chainId"]:
        return None
    now = _epoch(now_iso)
    if now is None:
        return None
    times = []
    for node in job.get("nodes") or []:
        stamp = _epoch(node.get("updatedAt"))
        if (re.fullmatch(rule["acceptedNodePattern"], str(node.get("key", "")))
                and node.get("state") in {"accepted", "completed", "done", "succeeded"}
                and stamp is not None and now - days * 86400 <= stamp <= now):
            times.append((stamp, node["updatedAt"]))
    if not times:
        return None
    result = {key: copy.deepcopy(rule[key]) for key in ("name", "description", "chainId", "evidence", "stage")}
    result["lastMeaningfulAt"] = max(times)[1]
    return result


def _key(chain):
    return f"{chain.get('chainId')}:{str(chain.get('address', '')).lower()}"


def _matched(chain):
    rule = RULES.get(_key(chain))
    return rule if (rule and chain.get("codePresent") is True
                    and str(chain.get("codeHash", "")).lower() == rule["codeHash"].lower()) else None


def classify_template(chain_evidence):
    """Return a known implementation/template exclusion reason, otherwise None."""
    rule = _matched(chain_evidence)
    return rule.get("excludedReason") if rule else None


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _epoch(value):
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError, AttributeError):
        return None


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z") if _int(value) is not None else None


def _amount(value, decimals=None):
    if _int(value) is None or _int(decimals) is None or decimals > 255:
        return None
    # Integer formatting avoids Decimal's default precision rounding large wei.
    whole, frac = divmod(value, 10**decimals)
    tail = str(frac).zfill(decimals).rstrip("0")
    return str(whole) + ("." + tail if tail else "")


def _payment_decimals(chain, rule):
    """Currency conversion follows exact reviewed token relationships + live metadata."""
    if rule.get("adapter") in {"goblin", "loom"}:
        return 18  # Native ETH units, not an ERC-20 default.
    from .utility import enrich_utility
    record = enrich_utility({"chainId": chain.get("chainId"), "contractAddress": chain.get("address")}, chain)
    decimals = set()
    for token in record.get("tokens", []):
        if "payment" not in token.get("roles", []):
            continue
        address = token.get("address")
        metadata = (chain.get("tokenMetadata") or {}).get(f"{chain.get('chainId')}:{address}", {})
        value = metadata.get("decimals")
        if (metadata.get("chainId") == chain.get("chainId") and metadata.get("address") == address
                and metadata.get("codePresent") is True and metadata.get("readBlock") == chain.get("readBlock")
                and _int(value) is not None and value <= 255):
            decimals.add(value)
    return next(iter(decimals)) if len(decimals) == 1 else None


def _capacity(count, cap):
    if _int(count) is None or _int(cap) is None:
        return "unknown"
    return "sold-out" if count >= cap else "open"


def _gate(state, value, closed="not-started", inverted=False):
    if state == "sold-out":
        return state
    if not isinstance(value, bool):
        return "unknown"
    if value == inverted:
        return closed
    return state


def _window(state, stamp, start=None, end=None):
    if state == "sold-out":
        return state
    if stamp is None:
        return "unknown"
    if start is not None and stamp < start:
        return "not-started"
    if end is not None and stamp >= end:
        return "ended"
    return state


def _overall(*states):
    for state in ("open", "conditional", "unknown"):
        if state in states:
            return state
    return "ended" if "ended" in states else states[0]


def _benefit(status, conditions, route_state, exclusive=True):
    if route_state in {"sold-out", "ended", "not-started", "paused", "unconfigured"}:
        status = "no"
        conditions = "Currently unavailable (" + route_state + "). " + conditions
    elif route_state == "unknown" and status != "no":
        status = "unknown"
    return {"status": status, "conditions": conditions, "exclusive": exclusive, "evidence": []}


def _route(name, state, conditions, price=None, currency=None, start=None, end=None):
    return {"name": name, "state": state, "conditions": conditions,
            "price": price, "currency": currency, "start": _iso(start), "end": _iso(end)}


def apply_rules(record, chain_evidence, now_iso):
    """Return a copy enriched with mint/idmdBenefit/stats/ruleReview fields.

    Unknown rules erase unverified availability/price conclusions, preserving
    ``mint.reportedTerms`` verbatim for the separate reported-claims UI.
    ``yes`` means a free route for the class exists at the pinned block, not that
    a particular wallet is eligible. All free routes still incur network gas.
    """
    result = copy.deepcopy(record)
    chain = chain_evidence
    reads = chain.get("reads") or {}
    previous = result.get("mint") or {}
    mint = {"state": "unknown", "start": None, "end": None, "publicPrice": None,
            "currency": None, "limits": None, "conditions": "Mint rules have not been reviewed for this deployed code.",
            "reportedTerms": previous.get("reportedTerms", []), "gasIncluded": False,
            "asOf": chain.get("readTimestamp"), "readBlock": chain.get("readBlock"), "routes": []}
    benefit = {"status": "unknown", "conditions": "No reviewed IDMD-holder entitlement for this deployed code.", "evidence": []}
    result.update(mint=mint, idmdBenefit=benefit)
    if chain.get("proofOnly") is True:
        mint["conditions"] = "Mint-route reads for this deployment are pending; wallet eligibility is not checked."
        result["ruleReview"] = {"status": "pending", "checkedAt": chain.get("checkedAt")}
        return result
    rule = _matched(chain)
    if not rule:
        result["ruleReview"] = {"status": "code-mismatch" if _key(chain) in RULES else "unreviewed", "checkedAt": now_iso}
        return result
    sources = [{"label": "Reviewed source", "url": rule.get("sourceUrl") or rule["sourceRepoUrl"] + "/tree/" + rule["sourceCommit"]}]
    result["ruleReview"] = {"status": "matched", "codeHash": rule["codeHash"], "sources": sources,
                            "reviewedAt": rule["reviewedAt"], "checkedAt": now_iso,
                            "scope": "Source rules plus current getter reads; not wallet-specific simulation or a security audit."}
    if rule.get("excludedReason"):
        result["excludedReason"] = rule["excludedReason"]
        return result
    adapter = rule["adapter"]
    amount = lambda value: _amount(value, _payment_decimals(chain, rule))
    stamp = _epoch(chain.get("readTimestamp"))
    stats = {**result.get("stats", {}), **chain.get("stats", {})}
    cap = rule.get("maxSupply")
    if cap is not None:
        stats["maxSupply"] = cap
    count = reads.get("totalMinted", reads.get("totalSupply"))
    state = _capacity(count, cap)
    conditions, limits, price, currency = "", "", None, None
    routes = []
    benefit = _benefit("no", "No IDMD-holder free mint route in the reviewed source.", state)
    if _int(reads.get("totalMinted")) is not None:
        stats["totalMinted"] = reads["totalMinted"]
    if _int(reads.get("totalSupply")) is not None:
        stats["totalSupply"] = reads["totalSupply"]

    if adapter == "imdenza":
        state = _capacity(reads.get("totalMinted"), cap)
        price, currency = amount(69_000_000_000_000_000), "IMD"
        limits = "One NFT per call; free IDMD route once per wallet AND per IDMD token. Public mint has no wallet cap."
        conditions = "Approve a supported same-chain IMD token for public mint. Separate free routes require the configured IMD balance threshold or a Fidenza NFT; their once-per-wallet flags can stack."
        configured = reads.get("identityMdCollection")
        free_state = state if isinstance(configured, str) and configured.lower() == IDMD else "unknown" if configured is None else "unconfigured"
        benefit = _benefit("yes", "Current canonical IDMD owner; unused IDMD token and unused wallet claim flag; no delegation.", free_state)
        if configured is not None and str(configured).lower() != IDMD:
            benefit["conditions"] += " identityMdCollection is not configured to the canonical IDMD collection."
        routes.append(_route("IDMD claim", free_state, benefit["conditions"], "0", "IMD"))
    elif adapter == "goblin":
        count = reads.get("liveSupply")
        state = _gate(_capacity(count, cap), reads.get("soldOut"), "sold-out", inverted=True)
        price, currency = amount(reads.get("PRICE")), "ETH"
        limits = "20 lifetime mints per wallet; sellout is permanent even if tokens burn later."
        conditions = "Exact ETH payment. Free game spins are not free NFTs. Refund availability is a separate contract rule."
        stats["totalSupply"] = count
        if _int(reads.get("nextTokenId")) is not None:
            stats["totalMinted"] = max(0, reads["nextTokenId"] - 1)
        stats["refundsOpen"] = reads.get("refundsOpen")
    elif adapter == "vimd2":
        end = _int(reads.get("ENTRY_END"))
        state = _window(_capacity(reads.get("entryCount"), cap), stamp, end=end) if end is not None else "unknown"
        price, currency = amount(reads.get("ENTRY_PRICE")), "VIMD"
        limits = "One entry NFT per IDMD seat; owners and current delegates qualify."
        conditions = "Entry burns the configured VIMD amount and needs valid portrait/package links. Voting has its own token burn."
        mint["end"] = _iso(end)
        stats.update(totalMinted=reads.get("entryCount"), totalSupply=reads.get("entryCount"), totalVotes=reads.get("totalVotes"), votingEnds=_iso(reads.get("VOTE_END")))
    elif adapter == "veterans":
        state = _gate(_capacity(reads.get("totalMinted"), cap), reads.get("isConfigured"), "unconfigured")
        price, currency = amount(reads.get("mintPrice", reads.get("MINT_PRICE"))), "IMD"
        limits = "No explicit wallet cap; 10 proof-of-work epochs."
        conditions = "Configured IMD balance/allowance plus qualifying proof of work; current difficulty must be satisfied."
        for field in ("currentEpoch", "difficulty", "mintsRemainingInEpoch", "remainingSupply"):
            stats[field] = reads.get(field)
    elif adapter == "pulse":
        state = _capacity(reads.get("totalMinted"), cap)
        price, currency = "0", None
        limits = "One soulbound, nontransferable Drone per wallet."
        conditions = "No PULSE balance or staking required for the mint; later gameplay has separate requirements."
        benefit = _benefit("yes", "Free for everyone, including IDMD holders; one per wallet.", state, False)
    elif adapter == "swarmlers":
        state = _gate(_capacity(reads.get("totalMinted"), cap), reads.get("publicMintOpen"))
        price, currency = amount(reads.get("MINT_PRICE")), "IMD"
        limits = "Free claim once per wallet AND per IDMD token; 25 creator mints count toward supply."
        conditions = "Public mint requires IMD approval/payment. Free route additionally needs an owner-appointed reporter's verified activity record."
        benefit = _benefit("conditional", "Current IDMD owner with reporter-attested verified worker activity within 7 days, bound to this wallet; both wallet and IDMD token must be unused.", state)
        routes.append(_route("Active-worker IDMD claim", state, benefit["conditions"], "0", "IMD"))
    elif adapter == "keel":
        state = _gate(_capacity(reads.get("totalMinted"), cap), reads.get("mintOpen"))
        for field in ("keelToken", "passSigner"):
            value = reads.get(field)
            if value is None:
                state = "unknown"
            elif str(value).lower() == ZERO:
                state = "unconfigured"
        price, currency = "0", None
        limits = "Once per wallet for life, including after redemption or burn."
        conditions = "Valid authorized EIP-712 MintPass, unexpired deadline and the signed positive KEEL holding minimum; signer service availability has not been tested."
        benefit = _benefit("conditional", "No IDMD-specific privilege. A valid signer pass and sufficient KEEL holdings are required for everyone.", state, False)
    elif adapter == "genesis":
        paid_state = _capacity(reads.get("totalBurnMints"), 2000)
        end = _int(reads.get("VOTE_END"))
        free_state = _capacity(reads.get("totalVoteMints"), 2000)
        free_state = _window(free_state, stamp, end=end) if end is not None else "unknown"
        seats = reads.get("SEATS")
        if seats is None:
            free_state = "unknown"
        elif str(seats).lower() != IDMD:
            free_state = "unconfigured"
        state = _overall(paid_state, free_state)
        price, currency = amount(reads.get("BURN_AMOUNT")), "VIMD"
        limits = "2,000 free vote NFTs plus 2,000 paid collector NFTs; one free vote per seat, not per wallet."
        conditions = "Public collector mint burns the configured VIMD amount; free vote mint ends separately. Finalist must be 0–2."
        benefit = _benefit("yes", "Current canonical IDMD owner, unused seat ID 0–1999, and valid finalist; delegates cannot use this free route.", free_state)
        routes += [_route("IDMD vote mint", free_state, benefit["conditions"], "0", "VIMD", end=end), _route("Collector mint", paid_state, conditions, price, currency)]
        stats.update(freeMints=reads.get("totalVoteMints"), paidMints=reads.get("totalBurnMints"), totalVotes=reads.get("totalVotes"))
    elif adapter == "ogpass":
        reserved_counts = [reads.get(k) for k in ("publicSupply", "founderOutstanding", "reservedFounderSlots")]
        public_count = sum(reserved_counts) if all(_int(v) is not None for v in reserved_counts) else None
        state = _gate(_capacity(public_count, cap), reads.get("buysPaused"), "paused", inverted=True)
        end = _int(reads.get("claimDeadline"))
        free_state = _capacity(reads.get("founderClaimed"), reads.get("founderCount"))
        free_state = _window(free_state, stamp, end=end) if end is not None else "unknown"
        price, currency = amount(reads.get("currentBuyPrice")), "OG"
        limits = "One soulbound pass held at a time; 1,000 outstanding supply cap, not lifetime mints."
        conditions = "Public curve buy needs OG approval and user-set maximum price/deadline. Reserved founder slots may reduce available public inventory."
        benefit = _benefit("conditional", "Founder Merkle allowlist proof and unused founder claim; current IDMD ownership alone does not qualify. Wallet must hold no pass.", free_state, False)
        routes += [_route("Public mint", state, conditions, price, currency), _route("Founder snapshot claim", free_state, benefit["conditions"], "0", "OG", end=end)]
        state = _overall(state, free_state)
        stats.update(founderClaimed=reads.get("founderClaimed"), founderCount=reads.get("founderCount"), publicSupply=reads.get("publicSupply"))
    elif adapter == "bmc":
        count = _int(reads.get("totalMinted"))
        state = _capacity(count, cap)
        if rule["launchNumber"] == 1481:
            state = _gate(state, reads.get("mintingOpen"))
        if rule["launchNumber"] == 1394 and count is not None and count >= 40:
            state = _gate(state, reads.get("saleClosed"), "ended", inverted=True)
        price = amount(reads.get("currentPrice"))
        if price is None and count is not None:
            price = amount((1_000_000 if count < 40 else 350_000) * 10**18)
        currency = "BMC"
        limits = "First 40 Genesis mints; 460 Mystery mints; no wallet cap."
        conditions = "Burn the configured tier-specific BMC amount; balance and allowance required."
        if rule["launchNumber"] == 1425:
            conditions += " Mystery mint additionally requires the external VRF request to succeed; this dependency has not been simulated."
        if rule["launchNumber"] != 1481:
            conditions += " Older deployment; a newer contract does not disable this one."
        stats.update(revealedCount=reads.get("revealedCount"), pendingReveals=reads.get("pendingReveals"))
    elif adapter == "pepeolithic":
        start, length = _int(reads.get("startTime")), _int(reads.get("caveLength"))
        end = start + 7 * length if start is not None and length is not None else None
        public_state = _window(state, stamp, start, end) if end is not None else "unknown"
        free_state, inventory = "unknown", "unknown"
        if _int(reads.get("nextFree")) is not None:
            next_free = reads["nextFree"]
            # _takeFree skips sale pieces. nextFree is a token cursor, not a count.
            while next_free < 736 and _pepe_sale_piece(next_free):
                next_free += 1
            inventory = "sold-out" if next_free >= 736 else "open"
            free_state = inventory
            free_state = _window(free_state, stamp, start) if start is not None else "unknown"
            free_state = _gate(free_state, reads.get("unclaimedReleased"), "ended", inverted=True)
        leftover_state = _gate(inventory, reads.get("unclaimedReleased"))
        state = _overall(public_state, free_state, leftover_state)
        price, currency = None, "ZTO"
        limits = "737 total: 2 constructor mints, 400 auction pieces, 335 snapshot claims. One free claim per wallet."
        conditions = "Dynamic round auction price; each cave closes after 24 hours. Individual round availability/pricing needs parameterized reads."
        benefit = _benefit("conditional", "Valid seatRoot snapshot Merkle proof and unused wallet claim; current IDMD ownership alone does not qualify.", free_state, False)
        mint["start"], mint["end"] = _iso(start), _iso(end)
        routes += [_route("Round auctions", public_state, conditions, None, "ZTO", start, end), _route("Snapshot free claim", free_state, benefit["conditions"], "0", "ZTO", start)]
        routes.append(_route("Released leftovers", leftover_state, "After releaseUnclaimed, remaining free inventory becomes paid floor-price inventory.", amount(reads.get("floorPrice")), "ZTO"))
        if leftover_state == "open" and public_state == "ended":
            price = amount(reads.get("floorPrice"))
        if start is not None and length is not None:
            conditions += " Free claims end only when releaseUnclaimed is called (earliest " + _iso(start + 8 * length) + "), or inventory runs out."
            stats["earliestFreeRelease"] = _iso(start + 8 * length)
        stats["nextFreeTokenCursor"] = reads.get("nextFree")
    elif adapter == "sinopia":
        state = "auction / delivery"
        price, currency = amount(reads.get("RESERVE")), "IMD"
        limits = "Uncapped; one NFT per successfully delivered and revealed auction round."
        conditions = "The configured IMD reserve applies. First bid starts a 3-hour auction, late bids extend it. Settlement commissions the swarm; successful delivery and hash-checked reveal mint to the winner. No guaranteed mint date."
        stats["auctionRounds"] = reads.get("latestRoundId")
        stats["maxSupply"] = None
    else:
        return _apply_special(result, rule, chain, now_iso, sources)

    if not routes:
        routes.append(_route("Mint", state, conditions, price, currency))
    elif adapter not in {"genesis", "pepeolithic", "ogpass"}:
        routes.insert(0, _route("Public mint", state, conditions, price, currency))
    if stamp is None:
        if state == "open":
            state = "unknown"
        if benefit["status"] in {"yes", "conditional"}:
            benefit["status"] = "unknown"
        for route in routes:
            if route["state"] == "open":
                route["state"] = "unknown"
    mint.update(state=state, publicPrice=price, currency=currency, limits=limits,
                conditions=conditions + " Network gas is additional; wallet eligibility was not simulated.", routes=routes)
    benefit["evidence"] = sources
    result.update(idmdBenefit=benefit, stats=stats)
    return result


def _pepe_sale_piece(token_id):
    if token_id in (0, 736):
        return False
    cave = (token_id - 1) // 105 + 1
    round_no = ((token_id - 1) % 105) // 5 + 1
    slot = (token_id - 1) % 5 + 1
    count = 5 if cave == 7 and round_no == 21 else 1 if cave < 3 else cave - 1 if cave < 5 else 4
    return slot > 5 - count


def _dependency(chain, rule, name):
    """Accept dependency storage only from the same block/chain/address binding."""
    supplied = (chain.get("dependencyReads") or {}).get(name) or {}
    expected = (rule.get("dependencies") or {}).get(name) or {}
    if (expected and supplied.get("chainId") == chain.get("chainId") == expected.get("chainId")
            and str(supplied.get("address", "")).lower() == expected.get("address", "").lower()
            and supplied.get("readBlock") == chain.get("readBlock") and supplied.get("readBlock") is not None
            and supplied.get("codePresent") is True and supplied.get("codeReviewed") is True):
        return supplied.get("reads") or {}
    return {}


def _apply_special(result, rule, chain, now_iso, sources):
    reads, mint = chain.get("reads") or {}, result["mint"]
    stats = {**result.get("stats", {}), **chain.get("stats", {})}
    adapter, stamp = rule["adapter"], _epoch(chain.get("readTimestamp"))
    amount = lambda value: _amount(value, _payment_decimals(chain, rule))
    state, price, currency, limits, conditions = "unknown", None, None, "", ""
    benefit = _benefit("no", "No IDMD-holder free mint privilege in the reviewed source.", state)
    routes = []
    if adapter == "loom":
        state = _gate(_capacity(reads.get("totalSupply"), reads.get("maxSupply")), reads.get("paused"), "paused", inverted=True)
        base, fee = _int(reads.get("mintPrice")), _int(reads.get("PLATFORM_FEE"))
        if base is not None and fee is not None:
            price = amount(base + fee)
        currency = "ETH"
        limits = f"Maximum {reads.get('maxPerWallet', 'unknown')} lifetime public mints per wallet; owner reserve is separate."
        conditions = "Each public mint pays mintPrice PLUS mandatory PLATFORM_FEE, even when mintPrice is zero. No IDMD discount."
        stats.update(totalSupply=reads.get("totalSupply"), maxSupply=reads.get("maxSupply"), royaltyBps=reads.get("royaltyBps"))
    elif adapter == "farm":
        dep = _dependency(chain, rule, "StarterClaim")
        launch = _int(dep.get("launchTime"))
        start, end = (launch + 2 * 86400, launch + 16 * 86400) if launch is not None else (None, None)
        state = _window("open", stamp, start, end) if start is not None else "unknown"
        if dep.get("root") in (None, "0x" + "0" * 64):
            state = "unknown" if dep.get("root") is None else "unconfigured"
        price, currency = "0 (snapshot starter)", None
        limits = "Three soulbound starter items per eligible snapshot ID. No global collection cap. Paid packs and game rewards are separate routes."
        conditions = "Frozen IDMD ownership snapshot proof binds token ID and wallet. Claim, entropy capture and resolve are separate transactions; resolve also needs inventory capacity."
        benefit = _benefit("conditional", "Snapshot Merkle proof required; current IDMD ownership alone does not qualify. Three items after claim/entropy/resolve, with no mint fee.", state, False)
        mint["start"], mint["end"] = _iso(start), _iso(end)
        routes.append(_route("IDMD snapshot starter", state, benefit["conditions"], "0", None, start, end))
        free_end = _int(dep.get("freeClaimEnds"))
        other_state = _capacity(dep.get("freeClaimed"), 500)
        other_state = _window(other_state, stamp, end=free_end) if free_end is not None else "unknown"
        if dep.get("freeRoot") in (None, "0x" + "0" * 64):
            other_state = "unknown" if dep.get("freeRoot") is None else "unconfigured"
        routes.append(_route("500-wallet allowlist pack", other_state, "Separate wallet/index Merkle proof; one per wallet and index; then resolve three items.", "0", None, end=free_end))
        if _int(reads.get("nextId")) is not None:
            stats["totalMinted"] = max(0, reads["nextId"] - 1)
        stats.update(maxSupply=None, snapshotBlock=dep.get("snapshotBlock"), freePacksClaimed=dep.get("freeClaimed"))
        aggregate = chain.get("specialStats") or {}
        if aggregate.get("complete") is True and aggregate.get("readBlock") == chain.get("readBlock"):
            for field in ("liveItems", "burnedItems", "beneficialHolders", "custodyHolders"):
                stats[field] = aggregate.get(field)
    elif adapter == "courier":
        currency = "MOON"
        conditions = "Item prices must be positive MOON. Purchases need an enabled configured item, exact token approval, and item-specific supply/wallet capacity."
        limits = "Per-item owner-configured limits; no global supply cap or fixed schedule."
        scan = chain.get("eventScan") or {}
        if (scan.get("complete") is True and scan.get("fromBlock") == 87504238 and scan.get("toBlock") == chain.get("readBlock")
                and scan.get("event") == "ItemConfigured(uint256,uint256,uint256,uint256,bool,string)"
                and scan.get("error") is None and isinstance(scan.get("items"), list)):
            if scan.get("events") == [] and scan["items"] == []:
                state = "unconfigured"
                conditions += " Complete deployment-to-snapshot ItemConfigured event scan found no configured items."
                stats.update(totalMinted=0, totalSupply=0)
            for item in scan["items"]:
                item_state = _capacity(item.get("minted"), item.get("maxSupply"))
                if item.get("maxSupply") == 0 and _int(item.get("minted")) is not None:
                    item_state = "open"  # Zero is explicitly unlimited in MoonShop.
                if item.get("exists") != 1:
                    item_state = "unconfigured"
                elif item.get("enabled") != 1:
                    item_state = "paused"
                routes.append(_route("Item " + str(item.get("id")), item_state,
                                     "Per-wallet limit: " + str(item.get("perWalletLimit")),
                                     amount(item.get("price")), "MOON"))
            if routes:
                state = _overall(*(route["state"] for route in routes))
                stats["configuredItemTypes"] = len(routes)
        stats["maxSupply"] = None
    elif adapter == "hive":
        dep = _dependency(chain, rule, "HiveWars")
        start = _int(dep.get("startTime"))
        settled = _int(dep.get("lastSettledEpoch"))
        first_end = start + 30 * 86400 if start is not None else None
        if settled is not None:
            state = "not-started" if settled < 30 else "conditional"
        price = "0"
        limits = "One soulbound badge per eligible wallet per finalized season; no global cap."
        conditions = "No IDMD privilege. Winning-colony membership and the configured active NECTAR minimum for 7 completed season epochs; season must be finalized with a nonneutral winner."
        benefit = _benefit("conditional", conditions, state, False)
        mint["start"] = _iso(first_end)
        stats.update(maxSupply=None, currentEpoch=dep.get("currentEpoch"), currentSeason=dep.get("currentSeason"), lastSettledEpoch=settled, firstSeasonEnd=_iso(first_end))
    elif adapter == "union":
        state, price = "open", "0"
        limits = "One nontransferable card per wallet. Local 2000 is the name, not a supply cap."
        conditions = "Requires positive STRIKE wallet balance OR staked STRIKE; prior mint disqualifies. IDMD ownership changes gold metadata only."
        benefit = _benefit("conditional", conditions, state, False)
        stats["maxSupply"] = None
    elif adapter == "seasons":
        dep = _dependency(chain, rule, "Canvas")
        season, start = _int(dep.get("currentSeason")), _int(dep.get("seasonStart"))
        duration = _int(dep.get("DURATION"))
        earliest = start + duration if start is not None and duration is not None and season else None
        currency = "IMD"
        limits = "One artwork NFT per completed seven-day canvas season; no global supply cap."
        conditions = "Permissionless endSeason mints to auction escrow, not to its caller. The 24-hour English auction transfers the existing NFT at finalization; first bid is one atomic IMD unit, later raises round up by at least 5%. Late bids add ten minutes."
        conditions += " With no bid the top painter receives the NFT; a wholly blank season remains in escrow. No IDMD entitlement."
        if season is not None:
            stats.update(totalSupply=max(0, season - 1), totalMinted=max(0, season - 1))
            state = "not-started" if season == 0 else "awaiting-season-end"
        stats.update(maxSupply=None, currentSeason=season, nextSeasonEndEarliest=_iso(earliest))
        mint["start"] = _iso(earliest)
        auction = reads.get("latestAuction")
        if season is not None and season > 1:
            state = "unknown"
            if isinstance(auction, dict) and auction.get("id") == season - 1:
                end, occupied = _int(auction.get("end")), _int(auction.get("occupied"))
                finalized = auction.get("finalized")
                if finalized is True:
                    state = "awaiting-season-end"
                elif finalized is False and end is not None and stamp is not None:
                    if stamp >= end:
                        state = "awaiting-finalization"
                    elif occupied == 0:
                        state = "blank-season"
                    elif occupied is not None:
                        state = "auction-open"
                        price = amount(reads.get("minimumBid"))
                stats["latestAuction"] = copy.deepcopy(auction)
                routes.append(_route("Latest season auction", state, conditions, price, currency, end=end))
        routes.append(_route("Next season mint to escrow", "awaiting-season-end" if earliest else "unknown",
                             "Earliest eligible time; a caller must end the season, and the previous auction rollover must be resolved.", None, None, earliest))
    else:
        return result
    if stamp is None:
        state = "unknown"
        if benefit["status"] in {"yes", "conditional"}:
            benefit["status"] = "unknown"
    if not routes:
        routes.append(_route("Mint", state, conditions, price, currency))
    mint.update(state=state, publicPrice=price, currency=currency, limits=limits,
                conditions=conditions + " Network gas is additional; wallet eligibility was not simulated.", routes=routes)
    benefit["evidence"] = sources
    result.update(idmdBenefit=benefit, stats=stats)
    return result
