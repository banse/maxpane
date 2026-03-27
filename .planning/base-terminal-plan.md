# Base Terminal Plan for MaxPane

## Problem Statement

MaxPane is a multi-game TUI (Textual) that currently supports two games: RugPull Bakery and FrenPet, switchable with Tab. We need to add a third screen -- Base Terminal -- a real-time trading dashboard for Base chain tokens. The data pipeline needs to be ported from an existing Node.js codebase (baseboard) to Python, using the same APIs and enrichment logic but adapted to MaxPane's `httpx`-based async patterns.

### Who is affected

- Existing Bakery and FrenPet screens must continue working unchanged.
- Base Terminal is entirely new: 5 internal views (Trending, Launches, Token, Fees, Overview) switchable with 1-5 keys, following the FrenPet `ContentSwitcher` pattern.

### Success criteria

1. Tab cycles through Bakery, FrenPet, and Base Terminal without data loss or timer conflicts.
2. `--game base` launches directly into the Base Terminal screen.
3. Phase 1 (Trending Scanner) is independently testable: top 20 trending tokens with price, volume, mcap, sparklines, and top movers.
4. Each subsequent phase (Launches, Token Detail, Fees, Overview) is independently deliverable.
5. Data refreshes on configurable poll intervals without blocking the UI.
6. API keys are loaded from the baseboard `.env` or environment variables, not hardcoded.

---

## Context and Constraints

### Known facts

- Textual version supports `Screen`, `ContentSwitcher`, registered themes, `run_worker`, and `set_interval`.
- The FrenPet screen already demonstrates the multi-view `ContentSwitcher` pattern with number-key switching -- this is the template for Base Terminal's 5-view layout.
- Screen lifecycle is handled via `on_screen_resume()` / `on_screen_suspend()` for starting/stopping poll timers. Bakery and FrenPet both follow this pattern.
- Data managers follow a consistent pattern: own an HTTP client, a cache, and expose `fetch_and_compute()` returning a flat dict for widget consumption. See `DataManager` and `FrenPetManager`.
- HTTP clients use `httpx.AsyncClient` with exponential-backoff retries. See `GameDataClient._get_with_retry()`.
- The app currently supports two games via `action_switch_game()` which toggles between "bakery" and "frenpet". This needs to become a 3-way cycle.
- The baseboard Node.js services are all successfully running and provide working reference implementations of every API call, parsing logic, and data enrichment pipeline.

### API endpoints (from baseboard, confirmed working)

| Service | Method | URL | Auth | Notes |
|---------|--------|-----|------|-------|
| Bankr Trending | POST | `https://api.bankr.bot/agent/prompt` | `x-api-key` header | Async job: submit prompt, poll for result. 2s poll, 60 max polls. |
| Bankr Job Poll | GET | `https://api.bankr.bot/agent/job/{jobId}` | `x-api-key` header | Returns status: pending/completed/failed. |
| DexScreener | GET | `https://api.dexscreener.com/latest/dex/tokens/{addresses}` | None | Batch up to 30 comma-separated addresses. Returns pairs array. |
| GeckoTerminal | GET | `https://api.geckoterminal.com/api/v2/networks/base/trending_pools` | None | JSONAPI format with `data` and `included` arrays. |
| Clanker Tokens | GET | `https://www.clanker.world/api/tokens?sort=desc&page=N` | None | Paginated, newest first. `&champagne=true` for graduated. |
| Base RPC | POST | `https://mainnet.base.org` or Alchemy | API key in URL | JSON-RPC for `eth_getLogs`, `eth_blockNumber`, `eth_call`. |

### API keys (from `/Library/Vibes/baseboard/.env`)

```
BANKR_API_KEY=***REDACTED_BANKR_KEY***
ALCHEMY_API_KEY=***REDACTED_ALCHEMY_KEY***
BASE_RPC_URL=https://mainnet.base.org
```

### Contract addresses (from baseboard `config.js`)

```
CLANKER_LAUNCH_CONTRACT=0x9ae5f51d81FF510bF961218F833F79D57bfBAb07
CLANKER_CLAIMING_CONTRACT=0xaF6E8f06c2c72c38D076Edc1ab2B5C2eA2bc365C  (LpLocker)
CLANKER_FEE_LOCKER=0xF3622742b1E446D92e45E22923Ef11C2fcD55D68
WETH_ADDRESS=0x4200000000000000000000000000000000000006
CLANKER_DEPLOYER=0xe85a59c628f7d27878aceb4bf3b35733630083a9
```

### Constraints

- Must use `httpx` (not `aiohttp`, not `requests`) to stay consistent with existing MaxPane HTTP stack.
- No wallet private keys or transaction signing -- read-only dashboard.
- The Bankr API is async (submit job, poll for result). The Python client must handle this polling loop within a single `fetch_and_compute()` call, with a timeout.
- DexScreener is unauthenticated but rate-limited. Must respect the 30-address batch limit and use a 2-minute cache TTL (matching baseboard's `CACHE_TTL = 120000`).
- GeckoTerminal uses JSONAPI format with relationships/included. Parser must handle the `data`/`included` join pattern.
- Fee monitoring requires on-chain log queries. Phase 4 can use simple RPC polling (`eth_getLogs`) rather than WebSocket, since Textual is poll-based anyway.
- For ABI decoding (fee events, deployer events), use `eth_abi` or `web3.py`. Prefer `eth_abi` to avoid the heavy `web3` dependency if possible.

### Assumptions

1. Bankr API returns trending tokens in a numbered-list text format that must be regex-parsed. The baseboard `parseTokensFromResponse()` logic is the reference implementation.
2. DexScreener returns multiple pairs per token; we keep the first (highest liquidity) pair per base token address.
3. GeckoTerminal trending pools change roughly every 2 minutes; a 2-minute poll interval is appropriate.
4. Clanker API pagination works reliably up to 10 pages for the new-token service.
5. Fee events on Clanker contracts are frequent enough to see activity within a 15-second poll window.

### Unknowns

1. **Bankr API reliability.** The job-based async pattern means trending data can be 1-2 minutes stale. If the Bankr API is down, we need graceful degradation (show GeckoTerminal trending as fallback).
2. **DexScreener rate limits.** The baseboard makes frequent batch calls. Need to confirm Python client won't hit stricter limits than the Node.js version.
3. **ABI decoding dependency.** Options: `eth_abi` (lightweight), `web3.py` (heavy but battle-tested), or manual topic/data parsing. Needs a decision.
4. **Alchemy API.** The baseboard uses Alchemy for WebSocket subscriptions and gap-fill pricing. For the TUI, we may not need Alchemy at all for Phase 1-3. Phase 4 (Fees) benefits from it but can fall back to direct RPC.
5. **Token detail candle data.** DexScreener has OHLCV endpoints but they are not used in baseboard. Need to verify the endpoint exists and the format.

---

## Architecture Decisions

### AD-1: Screen pattern -- ContentSwitcher with 5 views

**Decision:** Follow the FrenPet pattern exactly. `BaseTerminalScreen` is a `Screen` subclass with a `ContentSwitcher` containing 5 `Vertical` containers (ids: `trending`, `launches`, `token`, `fees`, `overview`). Number keys 1-5 switch views. A view-selector static widget at the top shows which view is active.

**Why:** Proven pattern. FrenPet already demonstrates this works with 3 views, data flowing to all views on each refresh, and number-key switching. Extending to 5 views is trivial.

### AD-2: Data pipeline -- single BaseManager with multiple sub-clients

**Decision:** Create a `BaseManager` (analogous to `DataManager` / `FrenPetManager`) that orchestrates multiple specialized API clients:
- `BankrClient` -- trending token queries
- `DexScreenerClient` -- market data enrichment
- `GeckoTerminalClient` -- trending pools
- `ClankerClient` -- token launches, graduated tokens
- `BaseRpcClient` -- on-chain log queries (Phase 4)

All clients share a single `httpx.AsyncClient` instance for connection pooling.

**Why:** Clean separation of concerns. Each client maps 1:1 to a baseboard service, making the port straightforward. The manager's `fetch_and_compute()` orchestrates them with `asyncio.gather()` for parallel fetching, same as the existing `GameDataClient.fetch_all()`.

**Alternative considered:** Single monolithic client. Rejected because the 5 API sources have very different auth, parsing, and caching requirements.

### AD-3: Token cache -- in-memory with time-series

**Decision:** Create `BaseCache` with:
- `token_cache: dict[str, TokenData]` -- latest snapshot per token address
- `price_history: dict[str, deque[tuple[float, float]]]` -- (timestamp, price) for sparklines
- `market_cache: dict[str, tuple[MarketData, float]]` -- DexScreener data with TTL timestamp
- Cache TTL of 120 seconds for market data (matching baseboard)
- Max 2000 tokens in cache, pruning stale tokens without market data after 10 minutes (matching baseboard's newTokenService logic)

**Why:** Mirrors the baseboard caching strategy. The existing `DataCache` pattern (deque-based time-series) already works for sparklines in Bakery.

### AD-4: ABI decoding for on-chain events (Phase 4)

**Decision:** Use `eth_abi` for decoding event logs. It is lightweight (~100KB) and handles `eth_getLogs` response decoding. Avoid pulling in `web3.py` (which adds ~50MB of dependencies) just for log parsing.

**Alternative:** Manual hex parsing of topics and data fields. Feasible for the 2-3 event types we need, but brittle and harder to maintain. `eth_abi` is the right balance.

**Note:** If `eth_abi` proves insufficient, we can upgrade to `web3.py` later. This is reversible.

### AD-5: Three-way game switching

**Decision:** Refactor `action_switch_game()` in `MaxPaneApp` from a binary toggle to a cycle through a list: `["bakery", "frenpet", "base"]`. Each game is lazily installed on first switch (existing pattern). Add `BaseManager` initialization alongside the existing managers.

**Why:** Minimal change to the existing app structure. The lazy-install pattern already works for FrenPet.

### AD-6: Environment variable loading

**Decision:** Load API keys from environment variables with fallback to reading `/Library/Vibes/baseboard/.env` if the vars are not set. Use `python-dotenv` (already likely in use or easily added) to load the baseboard `.env` file as a secondary source.

**Why:** Avoids duplicating secrets. The baseboard `.env` already has all needed keys. In production/CI, environment variables take precedence.

---

## File Structure

```
dashboard/
  screens/
    base_terminal.py           # BaseTerminalScreen (5-view ContentSwitcher)
  data/
    base_client.py             # BankrClient, DexScreenerClient, GeckoTerminalClient,
                               #   ClankerClient, BaseRpcClient
    base_models.py             # Pydantic models: Token, MarketData, TrendingPool,
                               #   ClankerToken, FeeClaim, etc.
    base_cache.py              # BaseCache: token cache, price time-series, market TTL
    base_manager.py            # BaseManager: orchestrates all clients + cache + analytics
  analytics/
    base_tokens.py             # Top movers, volume analysis, launch rate, graduation rate
    base_signals.py            # Momentum signals, volume spikes, new launch alerts
  widgets/
    base/
      __init__.py              # Re-exports all widgets
      trending_table.py        # Top 20 trending tokens table (DataTable or Static)
      price_sparklines.py      # Multi-token sparkline panel (braille chars)
      top_movers.py            # Biggest gainers/losers panel
      volume_bars.py           # Volume comparison horizontal bars
      launch_feed.py           # Live launch event feed (scrolling list)
      launch_stats.py          # Launch rate, graduation rate metrics
      token_detail.py          # Single token deep dive (selected from other views)
      trade_feed.py            # Recent swaps for a selected token
      fee_claims.py            # Fee claim event feed
      fee_leaderboard.py       # Top fee-earning tokens table
      live_feed.py             # Combined activity feed (all event types)
      overview_charts.py       # Multi-chart Bloomberg-style summary
```

---

## Work Packages

### Phase 1: Trending Scanner (first testable milestone)

#### WP-B1: Base API Clients + Models

**Scope:** Port the three Phase 1 data sources from baseboard Node.js to Python.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/data/base_models.py`
- `/Library/Vibes/autopull/dashboard/data/base_client.py`

**Pydantic models to define:**

```python
class MarketData(BaseModel):
    price_usd: float = 0.0
    volume_24h: float = 0.0
    market_cap: float = 0.0
    liquidity: float = 0.0
    fdv: float = 0.0
    price_change_5m: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    txns_24h_buys: int = 0
    txns_24h_sells: int = 0
    pair_address: str = ""
    pair_created_at: str | None = None
    dex_screener_url: str = ""

class Token(BaseModel):
    name: str
    symbol: str
    contract_address: str
    description: str | None = None
    img_url: str = ""
    market: MarketData | None = None
    source: str = ""  # "bankr", "gecko", "clanker", "deployer"
    rank: int | None = None
    created_at: str | None = None

class ClankerToken(Token):
    """Extended token model for Clanker launches."""
    requestor: str = ""
    deployer: str = ""
    champagne: bool = False  # graduated

class FeeClaim(BaseModel):
    for_token: str | None = None
    for_token_name: str | None = None
    for_token_symbol: str | None = None
    fee_owner: str | None = None
    eth_amount: float = 0.0
    timestamp: str = ""
    tx_hash: str = ""
    source: str = ""  # "LpLocker" or "FeeLocker"
    first_claim: bool = False
```

**Clients to implement:**

1. **BankrClient** (port of `bankrService.js`)
   - `submit_prompt(prompt: str) -> str` (returns job_id)
   - `wait_for_job(job_id: str, poll_interval=2.0, max_polls=60) -> dict`
   - `fetch_trending() -> list[Token]` (combines submit + wait + parse)
   - `_parse_tokens_from_response(text: str) -> list[Token]` (regex parser, port of `parseTokensFromResponse`)
   - Auth: `x-api-key` header from `BANKR_API_KEY` env var
   - Refresh interval: 5 minutes (matching baseboard `REFRESH_INTERVAL = 300000`)

2. **DexScreenerClient** (port of `dexscreenerService.js`)
   - `fetch_market_data(addresses: list[str]) -> dict[str, MarketData]`
   - `enrich_tokens(tokens: list[Token]) -> list[Token]`
   - Batch size: 30 addresses per request
   - Cache: 120-second TTL per address (matching baseboard `CACHE_TTL = 120000`)

3. **GeckoTerminalClient** (port of `geckoTerminalService.js`)
   - `fetch_trending() -> list[Token]`
   - Parser must handle JSONAPI `data` + `included` relationship join
   - Refresh interval: 2 minutes

**Porting notes:**

- Bankr response parsing: The baseboard regex-parses numbered-list output from an LLM. This is inherently fragile. The Python port should use the same regex patterns but add fallback handling for format variations.
- DexScreener: The `pairs` array may be at `data.pairs` or the response may be a direct array. Handle both (baseboard does this: `Array.isArray(data) ? data : (data.pairs || [])`).
- GeckoTerminal: The JSONAPI `included` array contains token metadata keyed by `{type}/{id}`. Build a lookup map, then join with pool `relationships.base_token.data.id`.

**Implementation detail for Bankr async job pattern:**

```python
async def fetch_trending(self) -> list[Token]:
    job_id = await self._submit_prompt(TRENDING_PROMPT)
    result = await self._wait_for_job(job_id)
    if result.get("status") == "completed" and result.get("response"):
        tokens = self._parse_tokens_from_response(result["response"])
        if len(tokens) >= 3:
            return tokens
    return []  # graceful degradation
```

**Testing approach:** Unit test the parsers with captured API responses. Integration test with live API calls gated behind env var presence.

**Dependencies:** `httpx` (existing), `pydantic` (existing).

**Estimated complexity:** Medium. Three distinct API integrations, each with different auth and response formats.

---

#### WP-B2: Base Analytics

**Scope:** Compute derived metrics from raw token data for widget display.

**File to create:**
- `/Library/Vibes/autopull/dashboard/analytics/base_tokens.py`

**Functions to implement:**

```python
def calculate_top_movers(
    tokens: list[Token],
    count: int = 5,
) -> tuple[list[Token], list[Token]]:
    """Return (top_gainers, top_losers) sorted by 24h price change."""

def calculate_volume_leaders(
    tokens: list[Token],
    count: int = 10,
) -> list[Token]:
    """Return tokens sorted by 24h volume descending."""

def calculate_market_summary(
    tokens: list[Token],
) -> dict:
    """Aggregate metrics: total volume, avg price change, bullish/bearish ratio."""

def merge_trending_sources(
    bankr_tokens: list[Token],
    gecko_tokens: list[Token],
) -> list[Token]:
    """Deduplicate by contract_address, prefer Bankr ranking, fill gaps from Gecko."""
```

**Testing approach:** Unit tests with synthetic token data.

**Estimated complexity:** Low. Pure functions operating on model objects.

---

#### WP-B3: Base Cache + Manager

**Scope:** Wire up the data pipeline: cache layer for price time-series, manager for orchestration.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/data/base_cache.py`
- `/Library/Vibes/autopull/dashboard/data/base_manager.py`

**BaseCache responsibilities:**
- Store latest token snapshots keyed by address
- Accumulate price time-series for sparklines (deque with max 120 samples, same as Bakery)
- TTL-based market data cache for DexScreener results (120s)
- Pruning: remove tokens without market data after 10 minutes (match baseboard)

**BaseManager.fetch_and_compute() flow:**

```
1. Parallel fetch:
   - bankr_client.fetch_trending()           # 5-min cached, may take 1-2 min on cold start
   - gecko_client.fetch_trending()            # 2-min cached
2. Merge trending sources (deduplicate by address)
3. Enrich with DexScreener market data:
   - dexscreener_client.enrich_tokens(merged_tokens)
4. Update cache (token snapshots + price time-series)
5. Compute analytics:
   - top_movers = calculate_top_movers(enriched_tokens)
   - volume_leaders = calculate_volume_leaders(enriched_tokens)
   - market_summary = calculate_market_summary(enriched_tokens)
6. Return flat dict for widget consumption
```

**Staggered refresh strategy:**
- Bankr trending: every 5 minutes (slow, LLM-based)
- GeckoTerminal trending: every 2 minutes
- DexScreener enrichment: every 30 seconds (re-enrich existing tokens with fresh prices)
- The manager's `fetch_and_compute()` is called every 30 seconds by the screen timer, but only triggers each sub-fetch when its individual interval has elapsed.

**Return dict shape (Phase 1):**

```python
{
    # Trending table
    "trending_tokens": list[Token],       # merged + enriched, ranked
    # Top movers
    "top_gainers": list[Token],
    "top_losers": list[Token],
    # Volume
    "volume_leaders": list[Token],
    # Sparklines
    "price_histories": dict[str, list[tuple[float, float]]],  # addr -> [(ts, price)]
    # Market summary
    "market_summary": dict,
    # Status
    "last_updated_seconds_ago": float,
    "error_count": int,
    "poll_interval": int,
    # Source stats
    "bankr_count": int,
    "gecko_count": int,
    "enriched_count": int,
}
```

**Dependencies:** WP-B1 (clients), WP-B2 (analytics).

**Estimated complexity:** Medium. Main challenge is the staggered refresh timing and graceful degradation when individual sources fail.

---

#### WP-B4: App Integration

**Scope:** Wire BaseTerminalScreen into the MaxPane app shell.

**Files to modify:**
- `/Library/Vibes/autopull/dashboard/app.py`
- `/Library/Vibes/autopull/dashboard/__main__.py`

**Changes to `app.py`:**

1. Import `BaseManager` and `BaseTerminalScreen`.
2. Add `self._base_manager = BaseManager(poll_interval=poll_interval)` in `__init__`.
3. Add `"base"` to the initial game handling in `on_mount()` and `_on_splash_dismissed()`.
4. Refactor `action_switch_game()` from binary toggle to 3-way cycle:

```python
_GAME_ORDER = ["bakery", "frenpet", "base"]

def action_switch_game(self) -> None:
    idx = self._GAME_ORDER.index(self._current_game)
    self._current_game = self._GAME_ORDER[(idx + 1) % len(self._GAME_ORDER)]
    # lazy install pattern (existing)
    if not self.is_screen_installed(self._current_game):
        screen = self._create_screen(self._current_game)
        self.install_screen(screen, name=self._current_game)
    self.switch_screen(self._current_game)
```

5. Add `await self._base_manager.close()` in `action_quit()`.

**Changes to `__main__.py`:**

1. Add `"base"` to `--game` choices.
2. Pass through to `MaxPaneApp`.

**Testing approach:** Manual: `python -m dashboard --game base` should show the Base Terminal screen. Tab should cycle through all three games.

**Dependencies:** WP-B3 (manager), WP-B5 (screen -- can stub initially).

**Estimated complexity:** Low. Small, well-defined changes to existing files.

---

#### WP-B5: Trending View Widgets + Screen

**Scope:** Build the BaseTerminalScreen and all Phase 1 widgets.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/screens/base_terminal.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/__init__.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/trending_table.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/price_sparklines.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/top_movers.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/volume_bars.py`

**BaseTerminalScreen layout (Phase 1, views 2-5 show "Coming soon" placeholders):**

```python
class BaseTerminalScreen(Screen):
    BINDINGS = [
        Binding("1", "show_trending", "Trending", show=False),
        Binding("2", "show_launches", "Launches", show=False),
        Binding("3", "show_token", "Token", show=False),
        Binding("4", "show_fees", "Fees", show=False),
        Binding("5", "show_overview", "Overview", show=False),
        Binding("r", "refresh", "Refresh", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Base Terminal", id="bt-title")
        yield Static(
            "[bold reverse] 1 Trending [/]  [dim][2] Launches  [3] Token  [4] Fees  [5] Overview[/]",
            id="bt-view-selector",
        )
        with ContentSwitcher(initial="trending"):
            with Vertical(id="trending"):
                yield TrendingTable()
                with Horizontal(id="bt-mid-row"):
                    yield TopMovers()
                    yield PriceSparklines()
                yield VolumeBarChart()
            with Vertical(id="launches"):
                yield Static("[dim]Phase 2 -- coming soon[/]")
            with Vertical(id="token"):
                yield Static("[dim]Phase 3 -- coming soon[/]")
            with Vertical(id="fees"):
                yield Static("[dim]Phase 4 -- coming soon[/]")
            with Vertical(id="overview"):
                yield Static("[dim]Phase 5 -- coming soon[/]")
        yield StatusBar()
```

**Widget specifications:**

1. **TrendingTable** -- renders top 20 tokens as a formatted table
   - Columns: Rank, Name, Symbol, Price, 24h Change (colored), Volume, MCap
   - Uses Rich markup for color-coding price changes (green positive, red negative)
   - Data method: `update_data(tokens: list[Token])`

2. **PriceSparklines** -- shows sparkline charts for top tokens
   - Uses braille characters (same pattern as existing CookieChart if any)
   - Shows 5-10 tokens, each with a mini sparkline and current price
   - Data method: `update_data(histories: dict[str, list[tuple[float, float]]])`

3. **TopMovers** -- shows biggest gainers and losers
   - Split panel: left side gainers (green), right side losers (red)
   - Shows top 5 each with name, symbol, percentage change
   - Data method: `update_data(gainers: list[Token], losers: list[Token])`

4. **VolumeBarChart** -- horizontal bar chart of volume leaders
   - Shows top 10 tokens by 24h volume
   - Uses block characters for bars, scaled to terminal width
   - Data method: `update_data(tokens: list[Token])`

**Screen lifecycle:** Follows BakeryScreen/FrenPetScreen pattern exactly:
- `on_screen_resume()`: immediate refresh + start timer
- `on_screen_suspend()`: stop timer
- `_do_refresh()`: call manager's `fetch_and_compute()`, distribute to widgets

**Dependencies:** WP-B1, WP-B2, WP-B3, WP-B4.

**Estimated complexity:** Medium-high. Most widgets are straightforward Rich-markup rendering, but the sparkline widget requires careful terminal character math.

---

### Phase 2: Launch Radar

#### WP-B6: Clanker Client Extension

**Scope:** Add Clanker API client to the base data pipeline.

**Files to modify:**
- `/Library/Vibes/autopull/dashboard/data/base_client.py` -- add `ClankerClient`
- `/Library/Vibes/autopull/dashboard/data/base_models.py` -- add `ClankerToken` if not already defined
- `/Library/Vibes/autopull/dashboard/data/base_manager.py` -- add launch data to `fetch_and_compute()`

**ClankerClient methods (port of `clankerService.js`):**

```python
class ClankerClient:
    async def fetch_tokens(self, page=1, sort="desc") -> list[ClankerToken]
    async def fetch_graduated(self) -> list[ClankerToken]
    async def poll_recent(self, max_pages=10) -> list[ClankerToken]
```

**Key porting details:**
- The baseboard fetches up to 100 pages for 24h tokens. For the TUI, cap at 10 pages (matching `MAX_CLANKER_PAGES` in newTokenService).
- Graduated tokens: filter with `?champagne=true` query param.
- Deduplication by contract address (lowercase), same as baseboard.
- DexScreener enrichment for new launches: batch enrich addresses not yet in cache.

**Manager additions:**
- Add `clanker_tokens` and `graduated_tokens` to the fetch_and_compute return dict.
- Add launch rate calculation: tokens per hour over the last N hours.

**Analytics additions to `base_tokens.py`:**

```python
def calculate_launch_rate(tokens: list[ClankerToken], hours: int = 1) -> float:
    """Tokens launched per hour over the given window."""

def calculate_graduation_rate(all_tokens: list[ClankerToken], graduated: list[ClankerToken]) -> float:
    """Percentage of tokens that reached champagne threshold."""
```

**Estimated complexity:** Medium. Straightforward API port, but the pagination and dedup logic needs care.

---

#### WP-B7: Launch View Widgets

**Scope:** Build the Launches view widgets and wire into BaseTerminalScreen.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/widgets/base/launch_feed.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/launch_stats.py`

**Files to modify:**
- `/Library/Vibes/autopull/dashboard/screens/base_terminal.py` -- replace Phase 2 placeholder

**Widget specifications:**

1. **LaunchFeed** -- scrolling list of recent launches
   - Each row: age (e.g., "2m ago"), name, symbol, initial liquidity, current price, 5m change, buy/sell counts
   - Color-coded: green for positive 5m change, red for negative
   - Newest at top, max 50 displayed
   - Data method: `update_data(tokens: list[ClankerToken])`

2. **LaunchStats** -- aggregate launch metrics
   - Launch rate (tokens/hour)
   - Graduation rate (% reaching champagne)
   - Total launches in last 24h
   - Average initial liquidity
   - Data method: `update_data(rate: float, grad_rate: float, count_24h: int, avg_liq: float)`

**Layout:**

```
[LaunchStats (compact, 3 lines)]
[LaunchFeed (fills remaining space)]
```

**Estimated complexity:** Low-medium. Mostly rendering logic.

---

### Phase 3: Token Detail

#### WP-B8: Token Detail Data

**Scope:** Add DexScreener candle/trade data and deep token info.

**Files to modify:**
- `/Library/Vibes/autopull/dashboard/data/base_client.py` -- add candle and trade endpoints to DexScreenerClient
- `/Library/Vibes/autopull/dashboard/data/base_models.py` -- add `Candle`, `Trade` models

**New DexScreenerClient methods:**

```python
async def fetch_candles(self, pair_address: str, timeframe: str = "15m") -> list[Candle]
async def fetch_trades(self, pair_address: str, limit: int = 50) -> list[Trade]
```

**DexScreener endpoints (to verify):**
- Candles: `GET https://api.dexscreener.com/latest/dex/pairs/base/{pairAddress}` (may include OHLCV)
- Trades: May need to use on-chain swap events or a third-party API

**Risk:** DexScreener's candle/trade API availability is an unknown. Fallback: use price history from our own cache to draw a simpler line chart.

**Manager addition:** When a token is "selected" (from trending or launches view), fetch its detailed data on demand rather than on every poll cycle. Add a `fetch_token_detail(address: str)` method.

**Estimated complexity:** Medium. The DexScreener candle API needs investigation.

---

#### WP-B9: Token Detail Widgets

**Scope:** Build the Token detail view.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/widgets/base/token_detail.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/trade_feed.py`

**Widget specifications:**

1. **TokenDetail** -- comprehensive single-token panel
   - Name, symbol, contract address (truncated)
   - Price (large), 24h change
   - MCap, FDV, Liquidity, 24h Volume
   - ASCII price chart (line or candle depending on data availability)
   - Pool info: pair address, DEX, fee tier
   - Data method: `update_data(token: Token, candles: list[Candle] | None)`

2. **TradeFeed** -- recent trades for the selected token
   - Type (buy/sell, color-coded), amount, price, time
   - Data method: `update_data(trades: list[Trade])`

**Token selection mechanism:**
- From Trending view: press Enter on a row to select token, auto-switch to view 3.
- From Launches view: same pattern.
- Custom Textual message: `class TokenSelected(Message)` with `address` field.
- Screen handles the message: stores selected address, fetches detail, updates widgets.

**Estimated complexity:** Medium-high. The ASCII chart rendering is the hardest part.

---

### Phase 4: Fee Monitor

#### WP-B10: Fee Monitoring Client

**Scope:** Port the baseboard `feeService.js` to Python using RPC polling.

**Files to modify:**
- `/Library/Vibes/autopull/dashboard/data/base_client.py` -- add `BaseRpcClient`
- `/Library/Vibes/autopull/dashboard/data/base_models.py` -- `FeeClaim` model (if not already defined)

**BaseRpcClient methods:**

```python
class BaseRpcClient:
    async def get_block_number(self) -> int
    async def get_logs(self, address: str, topics: list, from_block: int, to_block: int) -> list[dict]
    async def poll_fee_events(self, from_block: int, to_block: int) -> list[FeeClaim]
```

**Event topics to monitor (from baseboard):**
- `ClaimedRewards` on LpLocker (`0xaF6E8...`): topic `0x21d15f71...`
- `ClaimTokens` on FeeLocker (`0xF3622...`): topic `0xf98eaa9c...`

**ABI decoding:**
- Use `eth_abi.decode()` to parse event data from log entries
- Need the ABI fragments for these two events only (not full contract ABIs)
- Event ABIs can be hardcoded as Python constants (much simpler than importing JSON ABI files)

**Polling strategy:**
- Track `last_block` state
- Every 15 seconds, query `eth_blockNumber`, then `eth_getLogs` for the range `[last_block+1, current_block]`
- Parse and deduplicate by tx hash
- Maintain a rolling log of max 500 entries (matching baseboard)

**Fallback:** If Alchemy is available, use it for the RPC. Otherwise, use `https://mainnet.base.org` directly.

**Estimated complexity:** Medium-high. On-chain event parsing requires careful hex/ABI handling.

---

#### WP-B11: Fee View Widgets + Live Feed

**Scope:** Build the Fees view and combined live feed.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/widgets/base/fee_claims.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/fee_leaderboard.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/live_feed.py`

**Widget specifications:**

1. **FeeClaimFeed** -- scrolling list of fee claim events
   - Each row: time, token name/symbol, ETH amount, source (LpLocker/FeeLocker), tx hash (truncated)
   - Highlight claims > 1 ETH with alert styling
   - Data method: `update_data(claims: list[FeeClaim])`

2. **FeeLeaderboard** -- tokens ranked by total fees claimed
   - Columns: Rank, Token, Total ETH Claimed, Claim Count, Last Claim
   - Data method: `update_data(leaderboard: list[dict])`

3. **LiveFeed** -- combined activity feed (all event types)
   - Interleaves: launches, fee claims, large swaps
   - Unified timestamp ordering (newest first)
   - Color-coded by event type
   - Data method: `update_data(events: list[dict])`

**Estimated complexity:** Medium. The leaderboard aggregation logic is the main complexity.

---

### Phase 5: Multi-Chart Overview

#### WP-B12: Overview Widgets

**Scope:** Build the Bloomberg-style multi-chart overview screen.

**Files to create:**
- `/Library/Vibes/autopull/dashboard/widgets/base/overview_charts.py`

**Layout concept:**

```
+------------------+------------------+
| Top 10 Sparklines| Volume Bars      |
| (price mini-charts)| (24h volume)  |
+------------------+------------------+
| Launch Rate      | Fee Claims       |
| (tokens/hour     | (ETH/hour        |
|  over 24h)       |  over 24h)       |
+------------------+------------------+
| Market Summary   | Gas Trend        |
| (bullish/bearish | (base fee over   |
|  ratio, avg chg) |  time)           |
+------------------+------------------+
```

**Note:** Gas trend requires an additional RPC call (`eth_gasPrice` or `eth_feeHistory`). This is simple to add to `BaseRpcClient`.

**Dependencies:** All previous phases (reuses sparkline, volume, launch, and fee data).

**Estimated complexity:** Medium. Layout density is the challenge -- fitting 6 panels on one terminal screen requires careful sizing.

---

## Dependency Graph

```
Phase 1:
  WP-B1 (clients + models)
    |
    +---> WP-B2 (analytics)  ---+
    |                           |
    +---> WP-B3 (cache + mgr) -+---> WP-B4 (app integration) --+
                                |                                |
                                +---> WP-B5 (widgets + screen) -+---> Phase 1 Complete

Phase 2:
  WP-B6 (clanker client) ---> WP-B7 (launch widgets)

Phase 3:
  WP-B8 (token detail data) ---> WP-B9 (token detail widgets)

Phase 4:
  WP-B10 (fee RPC client) ---> WP-B11 (fee widgets + live feed)

Phase 5:
  WP-B12 (overview) -- depends on all above
```

**Cross-phase dependencies:**
- WP-B6 extends WP-B1's client file (additive, no conflict)
- WP-B8 extends WP-B1's DexScreenerClient (additive)
- WP-B10 adds BaseRpcClient to WP-B1's client file (additive)
- All Phase 2-4 widgets are added to the screen's ContentSwitcher, replacing placeholders

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bankr API downtime or slow responses | Medium | Medium | GeckoTerminal trending as fallback. Cache last-good Bankr result. Show staleness indicator. |
| Bankr response format changes (LLM output) | Medium | High | Robust regex parsing with multiple fallback patterns. Log unparseable responses for debugging. |
| DexScreener rate limiting | Low | Medium | Respect 30-address batch limit. Use 120s cache TTL. Stagger re-enrichment across cycles. |
| `eth_abi` insufficient for event decoding | Low | Low | Upgrade to `web3.py` if needed. Manual hex parsing as last resort. |
| Terminal too narrow for dense layouts | Medium | Low | Responsive design: hide columns or switch to compact mode when terminal width < threshold. |
| Phase 4 RPC polling misses events in block gaps | Low | Medium | On startup, scan back 100 blocks to catch recent history (matching baseboard). |

---

## Validation Plan

### Phase 1 validation

1. **Smoke test:** `python -m dashboard --game base` shows Base Terminal with trending tokens.
2. **Data accuracy:** Compare TUI output against DexScreener web UI for price/volume/mcap of top tokens.
3. **Tab switching:** Cycle Bakery -> FrenPet -> Base Terminal -> Bakery. Verify no data loss, timers restart correctly.
4. **Graceful degradation:** Kill network, verify the dashboard shows stale data with error indicator, not a crash.
5. **Performance:** Refresh cycle completes in < 5 seconds. No UI freezing during data fetch.

### Per-phase validation

- Phase 2: Verify launch feed shows new tokens appearing in real-time (within 30s of Clanker API update).
- Phase 3: Select a token from trending, verify detail view shows correct data matching DexScreener.
- Phase 4: Verify fee claims appear within 30 seconds of on-chain event (compare with baseboard's live feed).
- Phase 5: All 6 overview panels render with real data, no "N/A" values when all sources are healthy.

---

## Implementation Sequence (recommended)

1. **WP-B1** -- Start here. All other work depends on working API clients.
2. **WP-B2 + WP-B3** -- Can be done in parallel once WP-B1 is testable.
3. **WP-B4** -- Small change, do alongside WP-B5.
4. **WP-B5** -- Build screen and widgets, wire everything up. Phase 1 done.
5. **WP-B6 -> WP-B7** -- Phase 2 is self-contained after Phase 1.
6. **WP-B8 -> WP-B9** -- Phase 3 can overlap with Phase 2.
7. **WP-B10 -> WP-B11** -- Phase 4 is independent of Phases 2-3.
8. **WP-B12** -- Phase 5 last, after all data sources are flowing.

**Estimated total effort:** 5-7 working sessions, with Phase 1 deliverable after sessions 1-3.

---

## Open Questions

1. **Should Base Terminal poll interval differ from Bakery/FrenPet?** DexScreener data changes faster than game state. A 15-second poll for DexScreener enrichment with 5-minute Bankr refresh seems right, but this is tunable.
2. **Should we add `python-dotenv` as a dependency?** Currently the project may or may not use it. Alternative: manual `.env` parsing or require env vars to be set externally.
3. **Do we need the Alchemy SDK (`alchemy-sdk` Python package)?** The baseboard uses it for WebSocket subscriptions and `transfers.getAllTransfers()`. For Phase 4 we can likely avoid it by using raw `eth_getLogs` RPC calls, which are simpler.
4. **Token selection UX for Phase 3.** Should Enter on a trending row jump to the Token view? Or should there be a separate "select" action? FrenPet uses left/right arrows for pet navigation -- a similar pattern could work for token selection.
5. **Should Phase 5 (Overview) be the default view?** Bloomberg terminals show the overview first. But trending data is more immediately useful for a trading scanner. Recommend: Trending as default, Overview as the "power user" view.
