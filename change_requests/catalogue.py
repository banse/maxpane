"""Explicit UI targets, sourced from the dashboard's card and panel declarations."""


def areas(items):
    return [{"id": key, "label": label} for key, label in items]


def view(key, label, cards, content):
    common = [("layout", "Overall layout"), ("header", "Page header"),
              ("footer", "Footer / loading"), ("navigation", "Navigation"),
              ("loading", "Data loading")]
    return {"id": key, "label": label,
            "areas": {"card": areas(cards), "content": areas(content + common)}}


CATALOGUE = [
    view("boardroom", "BOARDROOM", [
        ("announce", "ONCHAIN FEED"), ("swarm", "BUILT BY SWARM"), ("work", "WIP"),
        ("oracles", "ORACLES"), ("pool4", "POOL4"), ("board", "FLEET"),
        ("surf-nft", "NFTS"), ("swarm-tokens", "TOKENS"),
        ("agent", "AGENT · Seat 1"), ("agent-2", "AGENT · Seat 2"),
        ("agent-3", "AGENT · Seat 3"), ("agent-4", "AGENT · Seat 4")],
        [("terminal", "Command terminal")]),
    view("surf.dashboard", "ONCHAIN FEED", [
        ("announcement", "ANNOUNCEMENT"), ("reply", "LATEST REPLY"), ("signals", "SIGNALS"),
        ("activity", "DEV ACTIVITY"), ("market", "IMD MARKET"), ("boards", "NFT BOARDS")],
        [("feed", "Onchain feed"), ("signals", "Signals"), ("activity", "Activity")]),
    view("surf.agent", "AGENT", [
        ("seat", "AGENT"), ("status", "STATUS"), ("accepted", "JOBS"), ("nodes", "SHIP"),
        ("models", "RESEARCH"), ("effort", "EFFORT"), ("runtime", "RUNTIME"), ("owner", "OWNER"),
        ("rank", "RANK"), ("collab", "COLLAB"), ("rewards", "REWARDS"), ("earnings", "EARNINGS")],
        [("records", "RECORDS table"), ("filters", "Record filters"), ("popup", "Record popup")]),
    view("surf-nft", "NFT EXPLORER", [
        ("deployed", "COLLECTIONS"), ("building", "IN THE MAKING"), ("mint_open", "MINT OPEN"),
        ("idmd_free", "IDMD FREE"), ("conditional", "CONDITIONAL"), ("chains", "CHAINS")],
        [("collections", "Collections table"), ("detail", "Collection detail"),
         ("summary", "GitHub README summary"), ("popup", "Mint / sources popup"), ("filters", "Filters")]),
    view("swarm-tokens", "SWARM TOKENS", [
        ("tokens", "TOKENS"), ("volume", "VOLUME"), ("liquidity", "LIQUIDITY"),
        ("pools", "POOLS"), ("momentum", "MOMENTUM"), ("top_volume", "TOP VOLUME")],
        [("tokens", "All tokens table"), ("activity", "Activity"), ("launches", "Newly launched"),
         ("best", "Best plays"), ("detail", "Token detail"), ("filters", "Filters")]),
    view("workflow-guide", "WORKFLOW GUIDE", [("capacity", "Step capacity"),
        ("alternatives", "Alternatives"), ("costs", "Costs")],
        [("diagram", "Workflow diagram"), ("explanation", "Explanation / limits"),
         ("topics", "Topic navigation"), ("popup", "Source details popup")]),
    view("surf.swarm", "BUILT BY SWARM", [("fleet", "FLEET"), ("output", "OUTPUT"),
        ("workflows", "WORKFLOWS"), ("launches", "LAUNCHES"), ("workflow", "LATEST WORKFLOW"),
        ("sites", "SITES")], [("launches", "Launches"), ("shipped", "Shipped recently"),
                             ("workflows", "Workflows"), ("sites", "Sites")]),
    view("surf.work", "WIP", [("jobs", "JOBS"), ("workflows", "WORKFLOWS"),
        ("seats", "SEATS"), ("build", "BUILD"), ("review", "REVIEW"), ("blocked", "BLOCKED")],
        [("tree", "Workflow / job tree"), ("details", "Selected job details")]),
    view("surf.oracles", "ORACLES", [("requests", "REQUESTS"), ("assessing", "ASSESSING"),
        ("attested", "ATTESTED"), ("disagreed", "NO QUORUM"), ("blocked", "BLOCKED"),
        ("networks", "NETWORKS")], [("requests", "Requests table"), ("details", "Request details")]),
    view("surf.board", "FLEET", [("top", "TOP SEAT"), ("recorded", "RECORDED"),
        ("rate", "ACCEPT RATE"), ("launches", "LAUNCHES"), ("workers", "WORKERS"), ("effort", "EFFORT")],
        [("leaderboard", "Leaderboard"), ("fleet", "Fleet details"), ("contributors", "Launch contributors")]),
    view("surf.pool4_user", "POOL4 MARKET", [("price", "IMD PRICE"), ("rate", "sIMD RATE"), ("staking", "STAKING"),
        ("vault", "VAULT"), ("bid", "DOWNSIDE BID"), ("queue", "DRIP QUEUE")],
        [("market", "Market / position"), ("stakers", "Stakers"), ("flow", "Recent flow")]),
    view("surf.pool4", "PROTOCOL", [("totals", "TOTALS"), ("inventory", "INVENTORY"),
        ("split", "REWARD SPLIT"), ("unsettled", "UNSETTLED"), ("delivery", "DELIVERY"), ("checks", "CHECKS")],
        [("flow", "Protocol flow"), ("split", "Reward split"), ("checks", "Checks")]),
    view("surf.launchpad", "LAUNCHPAD", [("coins", "COINS"), ("flow", "CURVE FLOW"),
        ("volume", "VOLUME"), ("fees", "CREATOR FEES"), ("queue", "BURN QUEUE"), ("burned", "BURNED")],
        [("coins", "Coins table"), ("activity", "Activity"), ("filters", "Filters")]),
]
