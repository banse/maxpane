import datetime

from maxpane_dashboard.data import surf_swarm as S
from tests.surf_swarm_fixtures import swarm_capture

JOBS = swarm_capture("jobs")["jobs"]
EXECUTING = swarm_capture("job_executing")
BLOCKED = swarm_capture("job_blocked")
DONE = swarm_capture("job_completed")


def _ts(iso: str) -> float:
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


NOW = _ts("2026-09-16T18:00:00Z")


def test_health_facts_reads_the_counters_and_never_invents_a_zero():
    facts = S.health_facts(swarm_capture("health"))
    assert facts["agents_online"] == swarm_capture("health")["connectedDaemons"]
    assert facts["agents_enrolled"] == swarm_capture("health")["activeEnrollments"]
    assert facts["services_up"] == {"verifier": True, "publisher": True, "deployer": True}
    blank = S.health_facts(None)
    assert blank["agents_online"] is None and blank["accepted_today"] is None
    assert blank["services_up"] is None


def test_queue_rows_count_every_state_and_sort_by_size():
    rows = S.queue_rows(JOBS)
    assert sum(r["count"] for r in rows) == len(JOBS)
    assert rows == sorted(rows, key=lambda r: (-r["count"], r["state"]))
    assert S.queue_rows(None) == []


def test_blocked_rows_carry_the_reason_and_nothing_terminal():
    rows = S.blocked_rows(JOBS)
    assert rows, "the capture has blocked jobs"
    assert all(r["reason"] for r in rows)
    assert all(r["job_id"] and r["template"] for r in rows)
    assert all(j["state"] == "blocked"
               for j in JOBS if j["id"] in {r["job_id"] for r in rows})


def test_unfinished_ids_are_exactly_the_non_terminal_jobs():
    ids = S.unfinished_ids(JOBS)
    assert set(ids) == {j["id"] for j in JOBS if j["state"] not in S.TERMINAL_STATES}
    assert S.TERMINAL_STATES == frozenset({"completed", "cancelled"})


def test_field_rows_name_the_seat_and_keep_the_dispatch_note():
    rows = S.field_rows([EXECUTING], now=NOW)
    assert rows, "the executing capture has nodes"
    held = [r for r in rows if r["agent_token"] is not None]
    assert held, "no node in the capture names a seat"
    assert all(r["job_id"] == EXECUTING["id"] for r in rows)
    assert all(r["age_s"] >= 0 for r in rows)
    noted = [r for r in rows if r["dispatch_note"]]
    assert noted and "review" in noted[0]["dispatch_note"]


def test_field_rows_of_a_blocked_job_keep_the_failed_node():
    rows = S.field_rows([BLOCKED], now=NOW)
    assert any(r["node_state"] == "failed" for r in rows)


def test_score_rows_fold_one_row_per_agent():
    rows = S.score_rows([DONE])
    assert len(rows) == 1
    row = rows[0]
    entry = DONE["reviews"][0]["entries"][0]
    assert row["agent_id"] == entry["agentId"]
    assert row["jobs_scored"] == 1
    assert row["mean_score"] == float(entry["value"])
    assert row["last_tx_hash"] == DONE["reviews"][0]["txHash"]
    assert row["last_chain_id"] == DONE["reviews"][0]["chainId"]


def test_shipped_rows_mix_deliveries_launches_and_sites_newest_first():
    rows = S.shipped_rows(JOBS, [DONE], swarm_capture("launches")["launches"],
                          swarm_capture("sites")["sites"])
    kinds = {r["kind"] for r in rows}
    assert {"launch", "site"} <= kinds
    stamps = [r["at_ts"] for r in rows if r["at_ts"] is not None]
    assert stamps == sorted(stamps, reverse=True)
    launch = next(r for r in rows if r["kind"] == "launch")
    assert launch["address"] and launch["address"].startswith("0x")
    assert launch["chain_id"] is not None
    site = next(r for r in rows if r["kind"] == "site")
    assert site["ens_name"] and site["cid"]


def test_throughput_is_derived_and_says_its_window():
    out = S.throughput(JOBS, [DONE], now=NOW, window_days=7)
    assert out["window_days"] == 7
    assert out["accepted_per_day"] >= 0
    assert out["median_delivery_s"] is None or out["median_delivery_s"] > 0
    assert 0.0 <= out["revision_rate"] <= 1.0
    empty = S.throughput(None, None, now=NOW)
    assert empty["accepted_per_day"] is None and empty["revision_rate"] is None


def test_network_of_is_an_allowlist():
    assert S.network_of(11155111) == "SEPOLIA"
    assert S.network_of(1) == "MAINNET"
    assert S.network_of(999) is None
    assert S.network_of(None) is None
