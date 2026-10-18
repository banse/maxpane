"""Deterministic catalog joins and projection, adapted from aidude nft-scan."""
from __future__ import annotations
import copy
import re
from datetime import datetime, timezone
from .rules import apply_rules, classify_template, reviewed_build
from .utility import enrich_utility
from .references import discover_references
from .links import normalize_site
API = "https://api.imd.fun"
CHAINS = {1: "Ethereum", 4663: "Robinhood"}
NFT_WORDS = re.compile(r"\bnfts?\b|erc[- ]?(?:721|1155)|non[- ]fungible|generative (?:art|collection)|\bcollectibles?\b", re.I)
ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
JOB_ID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)
DEAD_STATES = {"failed", "cancelled", "canceled", "abandoned", "rejected", "expired"}
TERMINAL_NODES = {"accepted", "completed", "done", "succeeded"}
NON_BUILD_TEMPLATES = {"skill:oracle-assess", "skill:research-report", "research", "skill:create-image", "skill:create-video", "skill:token-logo"}


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def target_chains(job):
    launch = job.get("launch") or {}
    if launch.get("chainId") is not None:
        return [launch["chainId"]] if launch["chainId"] in CHAINS else []
    if job.get("chainId") is not None:
        return [job["chainId"]] if job["chainId"] in CHAINS else []
    text = job.get("objective") or job.get("title") or ""
    # Deployment targets, not the chain of the payer, an identity NFT, or a quoted address.
    clauses = re.split(r"[\n.;]", text)
    targets = set()
    for clause in clauses:
        if re.search(r"sepolia|testnet|no mainnet|not (?:on )?mainnet", clause, re.I):
            continue
        if not re.search(r"deploy|launch|build|collection|chain\s*[:=]|target|network\s*[:=]", clause, re.I):
            continue
        if re.search(r"ethereum (?:mainnet|\(1\))|chain\s*(?:id)?\s*[:=]?\s*1\b", clause, re.I):
            targets.add(1)
        if re.search(r"robinhood(?: chain)?(?: mainnet)?|\b4663\b", clause, re.I):
            targets.add(4663)
    return sorted(targets)


def active_build(job, now, days=7):
    if job.get("state", "").lower() in DEAD_STATES | {"blocked", "parked"} or (job.get("launch") or {}).get("status") == "parked":
        return False, "Unsuccessful, blocked or parked job; no active continuation established"
    text = job.get("objective") or ""
    if not nft_build_intent(text):
        return False, "No NFT implementation objective"
    if not target_chains(job):
        return False, "No explicit supported mainnet target"
    implementations = [node for node in job.get("nodes") or []
                       if str(node.get("state", "")).lower() in TERMINAL_NODES
                       and not re.search(r"website|frontend|research|report", str(node.get("key", "")), re.I)
                       and (node.get("role") == "implement" or re.search(r"^(?:code$|build|implement|adapt_|write_.*(?:contract|code))", str(node.get("key", "")), re.I))]
    if not implementations:
        return False, "No accepted implementation; audit/report/idea alone is insufficient"
    current = timestamp(now)
    if current is None or not 0 < days <= 365:
        return False, "Invalid build observation window"
    cutoff = current - days * 86400
    evidence = []
    for node in job.get("nodes") or []:
        name = str(node.get("key") or node.get("type") or "")
        if not re.search(r"code|contract|implement|build|test|audit|review|deploy|verify", name, re.I):
            continue
        if str(node.get("state", "")).lower() in TERMINAL_NODES and cutoff <= (timestamp(node.get("updatedAt")) or 0) <= current:
            evidence.append(node.get("updatedAt"))
    delivery = job.get("delivery") or (job.get("result") or {}).get("delivery") or {}
    if delivery.get("repoUrl") and delivery.get("commit") and not delivery.get("failure") and cutoff <= (timestamp(delivery.get("deliveredAt")) or 0) <= current:
        evidence.append(delivery["deliveredAt"])
    if not evidence:
        return False, f"No accepted implementation activity within {days} days"
    return True, max(evidence, key=lambda v: timestamp(v) or 0)


def nft_build_intent(text):
    """Require collection work, not an NFT used as a token claim dependency."""
    if not NFT_WORDS.search(text):
        return False
    if re.search(r"records? (?:are )?not nfts?|no nft (?:is |will be )?(?:created|minted)", text, re.I):
        return False
    if re.search(r"nft (?:contract|collection)(?: address)? (?:will be supplied|is (?:being )?developed separately)", text, re.I):
        return False
    patterns = (
        r"(?:build|create|launch|deploy|implement).{0,160}(?:erc[- ]?721|erc[- ]?1155|nft collection|nft mint|nft game|generative (?:art|collection))",
        r"(?:erc[- ]?721|erc[- ]?1155).{0,80}(?:collection|contract|nfts?|membership)",
        r"(?:nft|generative|art) collection.{0,100}(?:supply|mint|pieces|deploy)",
        r"(?:nft name|tokenuri|soulbound|nft rarity|nft maximum|nft distribution)",
    )
    return any(re.search(pattern, text, re.I | re.S) for pattern in patterns)


def verified_nft(launch, chain):
    return launch.get("chainId") in CHAINS and launch.get("chainId") == chain.get("chainId") and chain.get("standard") in {"ERC-721", "ERC-1155", "ERC-721 + ERC-1155"} and chain.get("codePresent") is True and chain.get("receiptSuccess") is True and chain.get("deploymentConfirmed") is True and chain.get("receiptAddressMatches") is not False


def reported_terms(text):
    """Evidence excerpts remain reported claims; never infer live availability."""
    text = text or ""
    excerpts = []
    for line in re.split(r"\n|(?<=[.!?])\s+", text):
        if re.search(r"mint|claim|sale|epoch|royalt|supply|cap\b", line, re.I):
            cleaned = re.sub(r"\s+", " ", line).strip(" -*#")
            if cleaned:
                excerpts.append(cleaned[:700])
    benefit = {"status": "unknown", "conditions": "No verified IDMD-holder mint entitlement found.", "evidence": []}
    for line in excerpts:
        if re.search(r"\bIDMD\b|identity\s*md(?:\s+nft)?|identitymd", line, re.I) and re.search(r"free|zero[- ]price|0 (?:eth|imd)|no (?:mint )?cost", line, re.I) and re.search(r"mint|claim", line, re.I):
            if re.search(r"erc[- ]?20|airdrop|token (?:allocation|supply)|reward snapshot", line, re.I) and not re.search(r"nft|erc[- ]?721", line, re.I):
                continue
            benefit = {"status": "conditional", "conditions": "Reported in job/manifest; current eligibility not independently established: " + line, "evidence": [line]}
            break
    price = re.search(r"public\s+mint(?:\s+price)?\s*(?:is|of|:|=|costs)?\s*(\d+(?:\.\d+)?)\s*(ETH|IMD|USDC)\b", text, re.I)
    return {"idmdBenefit": benefit, "mint": {"state": "Unverified", "start": None, "end": None, "publicPrice": price.group(1) if price else None, "currency": price.group(2).upper() if price else None, "limits": None, "conditions": "Reported terms; check linked contract before minting.", "reportedTerms": excerpts[:12]}}


def deployment_candidates(raw):
    found = {}
    for summary in raw.get("launches", []):
        launch = raw.get("launchDetails", {}).get(summary["id"], summary)
        chain = launch.get("chainId")
        if chain not in CHAINS:
            continue
        for artifact in launch.get("artifacts") or []:
            address = str(artifact.get("address", "")).lower()
            if not ADDRESS.fullmatch(address):
                continue
            key = f"{chain}:{address}"
            if key not in found:
                found[key] = {"chainId": chain, "address": address, "artifact": artifact, "launch": launch, "launchIds": [], "jobIds": []}
            found[key]["launchIds"].append(launch["id"])
            found[key]["jobIds"].extend(j["id"] for j in launch.get("jobs") or [])
    return found


def live_site(site):
    return bool(isinstance(site, dict) and site.get("url") and site.get("status") in {"named", "live", "published", "pinned"} and not site.get("supersededBy") and not site.get("takenDownAt") and not site.get("takenDownReason"))


def job_references(details):
    """Prepare explicit UUID/commit links for one projection of unchanged facts."""
    commits = {}
    for job_id, job in details.items():
        commit = (job.get("delivery") or {}).get("commit")
        if isinstance(commit, str) and re.fullmatch(r"[0-9a-fA-F]{40}", commit):
            commits.setdefault(commit, set()).add(job_id)
    references = {}
    for job_id, job in details.items():
        referenced = {v for v in JOB_ID.findall(job.get("objective") or "") if v in details}
        for version in (job.get("project") or {}).get("versions", []):
            referenced.update(commits.get(version.get("baseCommit"), set()))
        references[job_id] = referenced
    return references


def related_records(raw, seed_jobs, address=None, launch_ids=(), *, references=None):
    """Explicit workflow/project/publication joins; name similarity is never a join."""
    details = raw.get("jobDetails", {})
    ids, sites, repos = set(seed_jobs), {}, {}
    references = job_references(details) if references is None else references
    # A site job that explicitly names the deployed contract is a direct reference.
    if address:
        for job in details.values():
            if job.get("site") and address.lower() in str(job.get("objective", "")).lower():
                ids.add(job["id"])
    changed = True
    while changed:
        previous = len(ids)
        for job_id, referenced in references.items():
            if job_id in ids or referenced & ids:
                ids.update(referenced)
                ids.add(job_id)
        for workflow in raw.get("workflows", []):
            linked = {v for v in (workflow.get("contractsJobId"), workflow.get("frontendJobId")) if v}
            if linked & ids:
                ids.update(linked)
        for job_id in list(ids):
            job = details.get(job_id, {})
            ids.update(v["jobId"] for v in (job.get("project") or {}).get("versions", []) if v.get("jobId"))
        for publication in raw.get("publications", []):
            linked = {v["jobId"] for v in publication.get("versions", []) if v.get("jobId")}
            if publication.get("id", "").startswith("job:"):
                linked.add(publication["id"][4:])
            linked_launches = {c["id"] for c in publication.get("contracts", []) if c.get("id")}
            if ids & linked or linked_launches & set(launch_ids):
                ids.update(linked)
                for site in publication.get("sites", []):
                    if live_site(site):
                        sites[site.get("id") or site["url"]] = site
                for version in publication.get("versions", []):
                    if live_site(version.get("site")):
                        site = version["site"]
                        sites[site.get("id") or site["url"]] = site
                    if version.get("repoUrl"):
                        repos[version["repoUrl"]] = {"url": version["repoUrl"], "commit": version.get("commit")}
        changed = len(ids) != previous
    jobs = []
    for job_id in sorted(ids):
        job = details.get(job_id, {})
        title = re.sub(r"\s+", " ", job.get("objective") or job_id)[:140]
        jobs.append({"id": job_id, "title": title, "url": f"https://explorer.imd.fun/jobs/{job_id}", "status": job.get("state")})
        if live_site(job.get("site")):
            site = job["site"]
            sites[site.get("id") or site["url"]] = site
    for site in (raw.get("sites") or {}).get("sites", []):
        if site.get("jobId") in ids and live_site(site):
            sites[site.get("id") or site["url"]] = site
    return jobs, sorted(sites.values(), key=lambda v: v.get("updatedAt") or "", reverse=True), list(repos.values())


def pinned_source(client, candidate):
    launch = candidate["launch"]
    repo, commit = launch.get("sourceRepoUrl", ""), launch.get("sourceCommit", "")
    if not re.fullmatch(r"https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        return {}
    name = candidate["artifact"].get("name", "")
    attested = next((c for c in (launch.get("attestation") or {}).get("contracts", []) if c.get("name") == name), {})
    path = attested.get("path") or f"src/{name}.sol"
    if not re.fullmatch(r"[A-Za-z0-9_./-]+\.sol", path) or ".." in path.split("/"):
        return {}
    base = "https://raw.githubusercontent.com/" + repo.removeprefix("https://github.com/") + "/" + commit + "/"
    try:
        text = client.get(base + path)
    except RuntimeError:
        return {}
    return {"text": text if isinstance(text, str) else "", "url": repo + "/blob/" + commit + "/" + path, "rawBase": base, "name": name}


def pinned_abi(client, source):
    if not source.get("rawBase") or not re.fullmatch(r"[A-Za-z0-9_]+", source.get("name", "")):
        return None
    name = source["name"]
    for path in (f"docs/abi/{name}.json", f"abi/{name}.json", f"artifacts/{name}.json", f"out/{name}.sol/{name}.json"):
        try:
            data = client.get(source["rawBase"] + path)
            abi = data if isinstance(data, list) else data.get("abi") if isinstance(data, dict) else None
            if isinstance(abi, list):
                return abi
        except RuntimeError:
            continue
    return None


def source_getter_abi(text):
    """Conservative read-only getter hints, not a Solidity compiler or full ABI."""
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text or "", flags=re.S)
    scalar = r"(?:u?int(?:8|16|32|64|128|256)?|address|bool|string|bytes(?:[1-9]|[12][0-9]|3[0-2]))"
    found = {}
    for kind, name in re.findall(r"\b(" + scalar + r")\s+public\s+(?:(?:constant|immutable|override)\s+)*([A-Za-z_]\w*)\s*(?:[;=])", text):
        found[name] = kind
    for name, kind in re.findall(r"\bfunction\s+([A-Za-z_]\w*)\s*\(\s*\)\s+(?:external|public)\s+(?:view|pure)\s+(?:override\s+)?returns\s*\(\s*(" + scalar + r")(?:\s+memory)?(?:\s+[A-Za-z_]\w*)?\s*\)", text):
        found[name] = kind
    return [{"type": "function", "name": name, "stateMutability": "view", "inputs": [], "outputs": [{"type": kind}]} for name, kind in found.items()]


def brief_description(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^Workflow contract stage context.*?Original request\s*[:：]\s*", "", text, flags=re.I)
    return text[:340] + ("…" if len(text) > 340 else "")


def build_title(text):
    match = re.search(r"\bProject:\s*([^\n.;]+)", text, re.I)
    if match:
        return re.split(r",\s*(?:an?|the)\s", match.group(1), maxsplit=1)[0][:110]
    match = re.search(r"Build the contracts for ([^,\n]+)", text, re.I)
    if match:
        return match.group(1)[:110]
    return re.split(r"\n|[.!?]\s", text, maxsplit=1)[0].strip(" #")[:110]


def superseded_projects(details):
    from .rules import classify_superseded_build
    result = {}
    for job in details.values():
        reason = classify_superseded_build(job)
        if reason:
            result[(job.get("project") or {}).get("id") or job["id"]] = reason
    return result


def project_catalog(raw, candidates, checked, *, now_iso, active_days=7):
    collections, excluded, deployed_jobs = [], [], set()
    details = raw.get("jobDetails", {})
    references = job_references(details)
    for key, candidate in candidates.items():
        chain, launch = checked.get(key, {}), candidate["launch"]
        if (not verified_nft(launch, chain) or chain.get("chainId") != candidate.get("chainId")
                or str(chain.get("address", "")).lower() != candidate.get("address")):
            excluded.append({"id": key, "launchIds": candidate["launchIds"], "reason": "Not a verified NFT deployment", "detectionStatus": chain.get("detectionStatus"), "warnings": chain.get("warnings", [])})
            continue
        template = classify_template(chain) or (chain.get("templateReason") if chain.get("isTemplate") else None)
        if template:
            excluded.append({"id": key, "launchIds": candidate["launchIds"], "reason": template})
            continue
        jobs, sites, repos = related_records(raw, set(candidate["jobIds"]), candidate["address"],
                                           candidate["launchIds"], references=references)
        deployed_jobs.update(j["id"] for j in jobs)
        notes = ((launch.get("attestation") or {}).get("manifest") or {}).get("notes") or ""
        objectives = "\n".join(details.get(j["id"], {}).get("objective", "") for j in jobs)
        terms = reported_terms(notes + "\n" + objectives)
        source = chain.get("pinnedSource") or {}
        evidence = [{"label": "IMD deployment record", "url": API + "/launches/" + launch["id"], "detail": "Successful receipt and NFT bytecode independently checked; deployment address attributed by IMD."}]
        if source.get("url"):
            evidence.append({"label": "Pinned collection source", "url": source["url"], "detail": "Source published at the launch commit."})
        if chain.get("sourceUrl"):
            evidence.append({"label": "Explorer source", "url": chain["sourceUrl"], "detail": chain.get("abiSource")})
        if launch.get("sourceRepoUrl"):
            repos.insert(0, {"url": launch["sourceRepoUrl"], "commit": launch.get("sourceCommit")})
        deployment = {**chain.get("deployment", {}), "txHash": candidate["artifact"].get("txHash"), "verifiedAt": chain.get("checkedAt"), "receiptSuccess": chain.get("receiptSuccess"), "codePresent": chain.get("codePresent")}
        if chain.get("factoryCreationVerified"):
            evidence[0]["detail"] = "NFT runtime and successful receipt checked; reviewed factory/constructor relationship independently verified."
            deployment["factoryAddress"] = chain.get("factoryAddress")
            if chain.get("implementationAddress"):
                deployment["implementationAddress"] = chain["implementationAddress"]
            if chain.get("constructorProof"):
                deployment["constructorProof"] = copy.deepcopy(chain["constructorProof"])
        record = {"id": key, "name": chain.get("name") or candidate["artifact"].get("name") or "Unnamed collection", "symbol": chain.get("symbol"),
                  "description": brief_description(notes or objectives), "category": "launched", "chainId": candidate["chainId"], "chainName": CHAINS[candidate["chainId"]],
                  "contractAddress": candidate["address"], "standard": chain["standard"], "deployment": deployment, "jobs": jobs, "sites": sites,
                  "repositories": repos, "launchIds": candidate["launchIds"], "launchNumber": launch.get("launchNumber"),
                  **terms, "stats": chain.get("stats") or {}, "chainReads": chain.get("reads") or {}, "readBlock": chain.get("readBlock"),
                  "activity": {"stage": "Deployed; mint availability requires separate checks", "lastMeaningfulAt": launch.get("updatedAt")},
                  "evidence": evidence, "unknowns": list(chain.get("warnings") or []), "codeHash": chain.get("codeHash")}
        if not sites:
            record["unknowns"].append("No current published website linked through the public jobs/publications was found.")
        collections.append(apply_rules(record, chain, now_iso))
    # Separate active-build pass. Deduplicate by explicit project ID (not project name).
    grouped = {}
    superseded_groups = superseded_projects(details)
    for job in details.values():
        if job["id"] in deployed_jobs:
            continue
        head = details.get((job.get("project") or {}).get("running") or (job.get("project") or {}).get("head"), {})
        if head.get("state", "").lower() in DEAD_STATES | {"blocked", "parked"}:
            excluded.append({"id": job["id"], "reason": "Latest project continuation is unsuccessful or blocked", "category": "build"})
            continue
        superseded = superseded_groups.get((job.get("project") or {}).get("id") or job["id"])
        if superseded:
            excluded.append({"id": job["id"], "reason": superseded, "category": "build"})
            continue
        launch = job.get("launch") or {}
        artifacts = [c for c in candidates.values() if launch.get("id") in c["launchIds"]]
        if launch.get("status") == "live" and artifacts and not any(checked.get(f"{c['chainId']}:{c['address']}", {}).get("isTemplate") for c in artifacts):
            # A completed ERC-20/accessory deployment is not proof of NFT work.
            excluded.append({"id": job["id"], "reason": "Completed launch contains no NFT collection or reviewed NFT factory template", "category": "build"})
            continue
        qualifies, evidence = active_build(job, raw.get("finishedAt") or now_iso, active_days)
        review = reviewed_build(job, raw.get("finishedAt") or now_iso, active_days)
        if review:
            qualifies, evidence = True, review["lastMeaningfulAt"]
        if not qualifies:
            if NFT_WORDS.search(job.get("objective") or ""):
                excluded.append({"id": job["id"], "reason": evidence, "category": "build"})
            continue
        project = (job.get("project") or {}).get("id") or job["id"]
        if project not in grouped or (timestamp(evidence) or 0) > (timestamp(grouped[project][1]) or 0):
            grouped[project] = (job, evidence, review)
    for project, (job, stamp, review) in grouped.items():
        jobs, sites, repos = related_records(raw, {job["id"]}, references=references)
        if any(j["id"] in deployed_jobs for j in jobs):
            continue
        for chain_id in ([review["chainId"]] if review else target_chains(job)):
            text = job.get("objective") or ""
            title = review["name"] if review else build_title(text)
            collections.append({"id": f"build:{chain_id}:{project}", "name": title or "NFT build", "symbol": None,
                                "description": review["description"] if review else brief_description(text), "category": "in_the_making", "chainId": chain_id, "chainName": CHAINS[chain_id],
                                "contractAddress": None, "standard": "Not deployed", "deployment": {}, "jobs": jobs, "sites": sites, "repositories": repos,
                                **reported_terms(text), "stats": {}, "activity": {"stage": review["stage"] if review else "Recent accepted implementation", "lastMeaningfulAt": stamp, "evidence": "Reviewed pinned code and accepted audit" if review else "Accepted implementation node in public job history"},
                                "evidence": (review["evidence"] if review else []) + [{"label": "Active build record", "url": API + "/jobs/" + job["id"], "detail": f"Meaningful progress within {active_days} days"}],
                                "unknowns": ["No verified NFT deployment found. Planned mint terms may change."]})
    collections = [enrich_utility(record, checked.get(record["id"]), jobs=details) for record in collections]
    for record in collections:
        record["sites"] = [normalize_site(site) for site in record.get("sites", [])]
        chain = checked.get(record["id"], {})
        for token in record.get("tokens", []):
            key = str(token.get("chainId")) + ":" + str(token.get("address", "")).lower()
            token["onchain"] = copy.deepcopy(chain.get("tokenMetadata", {}).get(key, {}))
    coverage = copy.deepcopy(raw.get("coverage", {}))
    coverage["complete"] = bool(coverage.get("complete")) and all(key in checked and checked[key].get("inspectionComplete") for key in candidates)
    scans = [value[family] for value in checked.values()
             for family in ("factoryDiscovery", "childDiscovery", "eventScan")
             if isinstance(value.get(family), dict) and "complete" in value[family]]
    if any(scan["complete"] is not True for scan in scans):
        coverage["complete"] = False
    coverage["factoryScans"] = scans
    coverage["contractsChecked"] = len(checked)
    coverage["references"] = discover_references(raw, observed_at=raw.get("finishedAt"))["coverage"]
    return {"generatedAt": now_iso, "scanAt": raw.get("finishedAt"), "coverage": coverage,
            "collections": sorted(collections, key=lambda r: (r["category"] != "launched", -(timestamp(r.get("deployment", {}).get("timestamp")) or 0), r["name"].lower(), r["id"])), "excluded": excluded}
