"""One-shot: trim the live published analysis into committed test fixtures.

Run from the repo root with the venv interpreter:

    .venv/bin/python scripts/capture_published_analysis.py

The live export is 8.3 MB over 19,522 wallets, which is not a fixture.  This keeps
every cluster that carries a distinguishing property and rewrites the trimmed
clusters' sizes so the trimmed overview and the trimmed export reconcile exactly as
the live pair does -- a fixture whose halves disagree tests the disagreement, not the code.
"""
from __future__ import annotations

import json
import pathlib
import urllib.request

BASE = "https://clustermap.vibingco.de/api/v1"
OUT = pathlib.Path("tests/fixtures/curator/published")
MEMBERS_PER_CLUSTER = 6
CLEAN_KEPT = 40


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=180) as resp:
        return json.load(resp)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    versions = get("versions")
    version_id = versions["published_version"]
    overview = get(f"overview?version={version_id}")
    export = get(
        "list/export?q=&link=all&evidence=all&preset=none&version=" + version_id
    )
    rows = export["rows"]

    by_cluster: dict[int, list[dict]] = {}
    for row in rows:
        if row["cluster_id"] is not None:
            by_cluster.setdefault(row["cluster_id"], []).append(row)

    review_ids = {
        row["cluster_id"] for row in rows if row["status"] == "review"
    }
    flagged_ids = {c["id"] for c in overview["clusters"] if c["review_flag"]}
    low_ids = {c["id"] for c in overview["clusters"] if c["band"] == "low"}
    biggest = max(overview["clusters"], key=lambda c: c["size"])["id"]
    keep_ids = (
        set(sorted(review_ids)[:4]) | set(sorted(flagged_ids)[:2])
        | set(sorted(low_ids)[:2]) | {biggest}
    )

    kept_rows: list[dict] = []
    for cid in sorted(keep_ids):
        members = by_cluster[cid]
        # Review members first so a trimmed cluster never loses the property it
        # was kept for.
        members.sort(key=lambda r: (r["status"] != "review", r["rank"]))
        kept_rows.extend(members[:MEMBERS_PER_CLUSTER])

    clean = [r for r in rows if r["status"] == "clean"]
    # Keep the rows whose 0.1.1 `link_conf` CONTRADICTS their 0.2.0 `status`:
    # they are the whole point of the trap test.
    contradicting = [r for r in clean if r["link_conf"] in ("high", "low")]
    kept_rows.extend(contradicting[:CLEAN_KEPT // 2])
    kept_rows.extend(
        [r for r in clean if r["link_conf"] == "clean"][: CLEAN_KEPT // 2]
    )

    sizes = {cid: 0 for cid in keep_ids}
    for row in kept_rows:
        if row["cluster_id"] is not None:
            sizes[row["cluster_id"]] += 1

    kept_rows.sort(key=lambda r: r["rank"])
    for rank, row in enumerate(kept_rows, start=1):
        row["rank"] = rank

    clusters = []
    for cluster in overview["clusters"]:
        if cluster["id"] not in keep_ids:
            continue
        cluster = dict(cluster)
        cluster["size"] = sizes[cluster["id"]]
        clusters.append(cluster)

    trimmed_overview = dict(overview)
    trimmed_overview["clusters"] = clusters
    trimmed_overview["totals"] = dict(overview["totals"])
    (OUT / "versions.json").write_text(json.dumps(versions, indent=1))
    (OUT / "overview_trimmed.json").write_text(
        json.dumps(trimmed_overview, indent=1)
    )
    (OUT / "export_trimmed.json").write_text(
        json.dumps({**export, "rows": kept_rows, "count": len(kept_rows)}, indent=1)
    )
    print(
        f"clusters={len(clusters)} rows={len(kept_rows)} "
        f"review={sum(1 for r in kept_rows if r['status'] == 'review')} "
        f"contradicting={sum(1 for r in kept_rows if r['status'] == 'clean' and r['link_conf'] in ('high', 'low'))}"
    )


if __name__ == "__main__":
    main()
