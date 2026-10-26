"""Primitive contract for the read-only Wallet / Swarm explorer.

``None`` populations are unread; empty lists are successful empty observations.
All timestamps are UTC Unix seconds. Amounts are decimal strings, grouped by
chain and token address; absent refund evidence is never a zero refund.

Orders: id, payer, action, name, timestamp, created_at, paid_at, payment_state,
status, outcome, in_flight, follow_up, job_id, workflow_id, launch_id,
oracle_id, schedule_id, tx_hash, payments, evidence. ``payments`` is a list
of {chain_id, asset, symbol, decimals, amount, tx_hash, observed_at} or None.
Each order is a directly attributed payer request, not a child execution.

Artifacts: id, kind (SITE/CONTRACT/TOKEN), name, chain, chain_id, address,
order_id, project, linked_id, binding_checked, usage, version, site_url,
job_id, launch_id, deployment, evidence, usage_state. Site identity is its project;
contract identity is chain/address. Tokens are a subset of contracts.
Only positively confirmed deployments enter CONTRACT/TOKEN populations.

Usage: count, actors, unit, complete, first_seen, rule, evidence, latest,
observed_at, from_block, to_block, tracking_since. None means no verified
observation; incomplete zero never means QUIET. Sites reuse linked evidence.

Sources maps names to {state, observed_at, complete, detail}. Coverage is a
list of concise statements of observed population and limitations. The reader
must reject another wallet's late result before publishing this snapshot.
"""

WALLET_KEYS = ("wallet_snapshot",)
WALLET_WIDGET_SIGNATURES = {"WalletBody": ("wallet_snapshot",)}
WALLET_SNAPSHOT_FIELDS = ("wallet", "orders", "artifacts", "schedules",
                          "payment_totals", "sources", "coverage", "as_of")


def empty_snapshot(wallet=""):
    return dict(wallet=wallet.lower(), orders=None, artifacts=None, schedules=None,
                payment_totals=None, sources={}, coverage=[], as_of=None)
