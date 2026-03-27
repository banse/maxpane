# MaxPane Terminal Dashboard - Project Plan

**Date:** 2026-03-27
**Mode:** Deep (architectural, multi-agent, UI design decisions pending)
**Status:** Planning complete, awaiting design mockup selection

---

## 1. Problem Statement

MaxPane needs a live monitoring interface for the RugPull Bakery game. The existing project has no frontend implementation yet. Rather than building a web dashboard (React + FastAPI as sketched in CLAUDE.md), the decision is to build a **fullscreen ASCII terminal dashboard** that displays real-time game state, analytics, and strategic signals.

**Why terminal instead of web:**
- Matches operator workflow (SSH into server, see state immediately)
- No browser dependency, works headless
- Faster to build and iterate than a full React app
- Aesthetic fit for a blockchain automation tool
- Can run alongside the bot in a tmux pane

**Who uses it:** The bot operator, watching game state to make manual strategic decisions or verify the bot's behavior.

**Success criteria:** Operator can glance at the terminal and within 5 seconds understand: who is winning, how fast, whether to boost/attack, and what just happened.

---

## 2. Context and Constraints

### Known Facts
- Python stack (must match autopet patterns)
- Three data sources: tRPC API, agent.json, on-chain RPC reads
- Seven panel types needed (leaderboard, chart, activity, season, signals, EV table, velocity)
- Must work in Terminal.app and iTerm2 on macOS
- No existing backend code -- this project is greenfield beyond CLAUDE.md scaffolding

### Constraints
- **Read-only dashboard** -- no keyboard interaction needed beyond quit (q) and maybe panel cycling
- **Poll-based updates** -- 15-30 second intervals, not websocket (tRPC API is request/response)
- **Single terminal** -- must fit all panels in one fullscreen view, responsive to terminal resize
- **No auth** -- dashboard reads public API data, no wallet keys needed
- **Python 3.11+** -- matching autopet

### Assumptions
- tRPC endpoints return JSON and are unauthenticated for read operations
- Terminal is at least 120x40 characters (standard fullscreen on a laptop)
- ETH/USD price can be fetched from a public API or hardcoded/estimated
- Cookie totals change frequently enough that 15-30s polling shows meaningful deltas

### Unknowns
- **tRPC response shapes** -- need to probe each endpoint to get exact field names and types
- **Rate limits** -- unknown if rugpullbakery.com throttles API calls
- **Historical data** -- tRPC may not provide time-series; we may need to accumulate our own
- **Season timing** -- need to confirm how season end timestamp is exposed
- **ETH price source** -- need a lightweight way to get ETH/USD without adding heavy dependencies

---

## 3. Tech Stack Decision

### Option A: Textual (recommended)

**What it is:** Full TUI framework by Textualize (Will McGuinness). Reactive widgets, CSS-like styling, built-in layout system, async-native.

**Benefits:**
- Rich widget library (DataTable, Static, Header, Footer, Sparkline, ProgressBar)
- CSS-like styling with hot-reload -- perfect for iterating on aesthetics
- Built-in responsive layout (grid, dock, vertical/horizontal)
- Async-first -- natural fit for polling loops
- Active maintenance, good docs
- Can add interactivity later (key bindings, focus, scrolling) without rewrite

**Drawbacks:**
- Heavier dependency (~5MB)
- Learning curve for CSS/DOM model
- Sparkline/chart widgets are basic; may need custom widget for cookie time-series
- Minimum terminal size requirements can be fussy

**Complexity:** Medium
**Reversibility:** Low (Textual apps have distinct structure)

### Option B: Rich Live Display

**What it is:** Rich library's Live display with Panel/Table/Layout composition. Simpler, render-loop based.

**Benefits:**
- Simpler mental model (just render a Layout every N seconds)
- Rich is already a common dependency
- Good enough for read-only dashboards
- Lighter weight

**Drawbacks:**
- No built-in responsive layout -- manual column math
- No widget lifecycle -- everything re-renders from scratch
- Sparklines exist but charts are very limited
- Adding interactivity later requires rewrite to Textual anyway
- Flicker on full re-render without careful differential updates

**Complexity:** Low initially, grows fast
**Reversibility:** Medium (simpler to migrate away from)

### Option C: Blessed/Curses (not recommended)

Low-level, poor Python ecosystem, no advantage over Textual.

### Decision: **Textual** (Option A)

Textual is the right choice because:
1. The dashboard has 7+ panels that need responsive layout -- Textual's grid handles this natively
2. We want the option to add keyboard navigation later (cycle panels, drill into bakery)
3. CSS-like theming makes it trivial to switch between the 4 aesthetic styles
4. Async polling loop integrates naturally with Textual's event system
5. The sparkline/chart requirement is non-trivial and Textual has the best foundation

---

## 4. Design Phase -- Mockup Strategy

Before any code, create 4 ASCII mockup files that the user views in-terminal to pick an aesthetic.

Each mockup is a plain `.txt` file at `/Library/Vibes/maxpane/.planning/mockups/` showing what the dashboard would look like at ~120x45 characters.

### Mockup 1: Bloomberg Terminal (`mockup-bloomberg.txt`)
- Black background implied (dark terminal)
- Green and amber text (indicated by comments/labels)
- Dense data tables, no wasted space
- Monospace financial ticker aesthetic
- Numbers right-aligned, compact headers
- Thin box-drawing borders (single-line)

### Mockup 2: htop System Monitor (`mockup-htop.txt`)
- Colored bars and meters
- CPU-bar style for cookie production rates
- Dense multi-column layout
- Header with system-style info (season, uptime, poll count)
- Activity feed as scrolling log at bottom

### Mockup 3: Retro Game (`mockup-retro-game.txt`)
- Double-line box-drawing characters
- Game-themed headers ("BAKERY WARS", cookie emoji equivalents in ASCII)
- Playful column names
- Banner-style season countdown
- More decorative, less data-dense

### Mockup 4: Minimal Dashboard (`mockup-minimal.txt`)
- Big numbers for key metrics (prize pool, #1 cookies, gap)
- Lots of whitespace
- Clean single-purpose panels
- Sparkline charts prominent
- Modern dashboard feel (think Datadog/Grafana terminal edition)

**Deliverable:** 4 text files. User opens each in terminal, picks one. That choice drives the Textual CSS theme.

---

## 5. Architecture

```
maxpane/
  dashboard/
    __init__.py
    __main__.py              # Entry point: python -m dashboard
    app.py                   # Textual App subclass, layout, keybindings
    config.py                # Dashboard-specific config (poll interval, etc.)
    data/
      __init__.py
      client.py              # tRPC + agent.json HTTP client (aiohttp/httpx)
      models.py              # Pydantic models for API responses
      cache.py               # In-memory cache with TTL, time-series accumulator
      price.py               # ETH/USD price fetch
    analytics/
      __init__.py
      production.py          # Cookies/hr calculation, velocity, trending
      ev.py                  # Boost/attack EV tables
      signals.py             # Late-join EV, prize/member, "should join?"
      leaderboard.py         # Gap analysis, rank changes
    widgets/
      __init__.py
      leaderboard.py         # Top bakeries table
      cookie_chart.py        # Time-series sparkline/plot
      activity_feed.py       # Color-coded event stream
      season_info.py         # Countdown, prize pool, season ID
      signals_panel.py       # Strategic signals
      ev_table.py            # Boost/attack EV matrix
      velocity.py            # Production rate with trend arrows
    themes/
      __init__.py
      bloomberg.tcss         # Textual CSS for Bloomberg style
      htop.tcss              # Textual CSS for htop style
      retro.tcss             # Textual CSS for retro game style
      minimal.tcss           # Textual CSS for minimal style
```

### Key Design Decisions

**Separation of data and display:** The data layer fetches and caches. The analytics layer computes derived values. Widgets only render. This means:
- Data layer is testable without any TUI
- Analytics engine is testable with fixture data
- Widgets can be developed with mock data before API is wired up

**Time-series accumulation:** The tRPC API likely returns point-in-time snapshots, not history. The cache layer will accumulate cookie totals over time in a rolling deque (e.g., last 60 data points at 30s intervals = 30 minutes of history). This drives the cookie chart.

**Poll loop as Textual Worker:** Textual has a `Worker` concept for background tasks. The poll loop runs as a worker, updates a shared data store, and posts a custom message to trigger widget refreshes. No threading needed -- it is all async.

---

## 6. Work Packages

### WP1: API Probing and Data Models
**Goal:** Hit every tRPC endpoint and agent.json, capture response shapes, create Pydantic models.
**Agent type:** Code agent with HTTP access
**Effort:** Small (2-3 hours)
**Dependencies:** None
**Deliverables:**
- `dashboard/data/models.py` with typed Pydantic models
- `docs/api-responses.json` with raw sample responses for reference
- Notes on any rate limiting or auth requirements discovered

**Steps:**
1. Fetch `https://www.rugpullbakery.com/agent.json`, document structure
2. Call each tRPC endpoint with appropriate input params, capture responses
3. Define Pydantic models matching response shapes
4. Note any fields that are unclear or undocumented

### WP2: Data Client
**Goal:** Async HTTP client that fetches all game data with caching and error handling.
**Agent type:** Backend code agent
**Effort:** Small-medium (3-4 hours)
**Dependencies:** WP1 (models)
**Deliverables:**
- `dashboard/data/client.py` -- async client class
- `dashboard/data/cache.py` -- TTL cache + time-series accumulator
- `dashboard/data/price.py` -- ETH/USD price fetch
- Unit tests with mocked responses

**Steps:**
1. Implement `GameDataClient` with methods matching each API endpoint
2. Use `httpx.AsyncClient` for async HTTP
3. Implement `DataCache` with configurable TTL and deque-based time-series storage
4. Implement `PriceClient` for ETH/USD (CoinGecko simple price API or similar)
5. Add retry logic (3 retries, exponential backoff) for transient failures
6. Write tests with `respx` or `httpx` mock transport

### WP3: Analytics Engine
**Goal:** Pure-function calculations that turn raw game data into dashboard insights.
**Agent type:** Backend code agent (math-heavy)
**Effort:** Medium (4-5 hours)
**Dependencies:** WP1 (models, for type signatures)
**Deliverables:**
- `dashboard/analytics/production.py` -- cookies/hr, velocity, trend detection
- `dashboard/analytics/ev.py` -- boost/attack EV calculations
- `dashboard/analytics/signals.py` -- late-join EV, prize/member ratio, join recommendation
- `dashboard/analytics/leaderboard.py` -- gap to #1, rank change detection
- Unit tests with fixture data

**Steps:**
1. Production rate: `(cookies_now - cookies_prev) / time_delta`, smoothed over 3+ samples
2. Boost EV: `success_rate * production_rate * (multiplier - 1) * remaining_duration - cookie_cost`
3. Attack EV: `success_rate * target_production_rate * penalty_factor * duration - cookie_cost`
4. Late-join EV: `(prize_pool / expected_final_members) - buy_in_cost - expected_gas`
5. Prize/member for each top bakery: `prize_pool * rank_share / member_count`
6. Trend arrows: compare last 3 velocity samples, classify as rising/flat/falling
7. Write comprehensive tests -- these calculations drive strategic decisions

### WP4: Design Mockups
**Goal:** 4 text files showing different aesthetic options for user to choose from.
**Agent type:** Creative/design agent
**Effort:** Small (2-3 hours)
**Dependencies:** None (can run in parallel with WP1-3)
**Deliverables:**
- `/Library/Vibes/maxpane/.planning/mockups/mockup-bloomberg.txt`
- `/Library/Vibes/maxpane/.planning/mockups/mockup-htop.txt`
- `/Library/Vibes/maxpane/.planning/mockups/mockup-retro-game.txt`
- `/Library/Vibes/maxpane/.planning/mockups/mockup-minimal.txt`

**Steps:**
1. Establish a common data scenario (same fake numbers across all 4)
2. Lay out each mockup at 120x45 character grid
3. Use box-drawing characters, ASCII art, alignment appropriate to each style
4. Include color annotations as comments (e.g., `[green]`, `[amber]`)
5. Ensure all 7 panel types appear in each mockup
6. Include a legend showing what colors mean

### WP5: Textual App Shell and Layout
**Goal:** Working Textual app with responsive panel layout, no real data yet.
**Agent type:** TUI/frontend code agent
**Effort:** Medium (4-5 hours)
**Dependencies:** WP4 (user must pick a style first), or build with placeholder theme
**Deliverables:**
- `dashboard/app.py` -- main App class with layout
- `dashboard/__main__.py` -- entry point
- `dashboard/themes/*.tcss` -- at least the chosen style
- Placeholder widgets showing static mock data
- Responsive behavior verified at 120x40, 160x50, 200x60

**Steps:**
1. Create Textual App subclass with `compose()` defining the 7-panel layout
2. Use Textual's grid/dock layout for responsive sizing
3. Create placeholder widget classes (Static text with mock data)
4. Write the chosen TCSS theme file
5. Add key bindings: `q` to quit, `r` to force refresh
6. Test resize behavior at multiple terminal sizes
7. Verify rendering in both Terminal.app and iTerm2

### WP6: Individual Widgets
**Goal:** Each of the 7 panels as a real Textual widget, consuming data models.
**Agent type:** TUI/frontend code agent
**Effort:** Large (6-8 hours, can parallelize per widget)
**Dependencies:** WP5 (app shell), WP1 (models)
**Deliverables:**
- `dashboard/widgets/leaderboard.py` -- DataTable with bakery rankings
- `dashboard/widgets/cookie_chart.py` -- Sparkline or custom plot widget
- `dashboard/widgets/activity_feed.py` -- scrolling log with color coding
- `dashboard/widgets/season_info.py` -- countdown timer, prize pool display
- `dashboard/widgets/signals_panel.py` -- strategic signal indicators
- `dashboard/widgets/ev_table.py` -- boost/attack EV matrix
- `dashboard/widgets/velocity.py` -- production rates with trend arrows

**Per-widget steps:**
1. Define widget class extending appropriate Textual widget
2. Accept data model as input, render formatted output
3. Implement `update(data)` method for live refresh
4. Add color coding per theme rules
5. Handle edge cases (no data yet, API error, season not active)
6. Test with mock data at various terminal widths

**Widget-specific notes:**

| Widget | Base Class | Key Challenge |
|--------|-----------|---------------|
| Leaderboard | DataTable | Column sizing responsive to width |
| Cookie Chart | Custom (Sparkline) | Accumulating time-series, scaling Y axis |
| Activity Feed | RichLog or Custom | Auto-scroll, max buffer size, color per event type |
| Season Info | Static | Live countdown (tick every second, not just on poll) |
| Signals | Static | Color thresholds (green/amber/red) |
| EV Table | DataTable | Number formatting, highlight best EV |
| Velocity | Static | Trend arrow unicode chars, rate formatting |

### WP7: Live Update Loop and Integration
**Goal:** Wire everything together -- poll loop fetches data, analytics process it, widgets render it.
**Agent type:** Backend integration agent
**Effort:** Medium (4-5 hours)
**Dependencies:** WP2, WP3, WP5, WP6
**Deliverables:**
- Poll loop as Textual Worker
- Data flow: client -> cache -> analytics -> widgets
- Error handling (API down, partial data, network timeout)
- Graceful degradation (show stale data with staleness indicator)
- Configurable poll interval

**Steps:**
1. Create `DataManager` class that orchestrates fetch -> cache -> analytics
2. Implement as Textual `Worker` running in background
3. On each poll: fetch all endpoints, update cache, recalculate analytics, post refresh message
4. App handles refresh message by calling `update()` on each widget
5. Add staleness indicator (show last-updated timestamp, turn amber if >60s stale)
6. Add error counter and display (bottom bar: "API errors: 0 | Last update: 3s ago")
7. Handle graceful startup (show "Loading..." until first successful poll)

### WP8: CLI Entry Point and Packaging
**Goal:** Clean way to launch the dashboard.
**Agent type:** Code agent (minor)
**Effort:** Small (1-2 hours)
**Dependencies:** WP7
**Deliverables:**
- `dashboard/__main__.py` -- `python -m dashboard`
- CLI args: `--poll-interval`, `--theme`, `--no-color`
- Update `pyproject.toml` with dashboard dependencies

**Steps:**
1. Add `argparse` or `click` CLI parser
2. Wire args to config
3. Add `textual`, `httpx`, `pydantic` to project dependencies
4. Optionally add `[tool.project.scripts]` entry for `maxpane-dashboard` command
5. Test launch and clean exit

---

## 7. Dependency Graph and Phasing

```
Phase 0 (parallel, no deps):
  WP1: API Probing          WP4: Design Mockups
       |                         |
Phase 1 (parallel after WP1):   |
  WP2: Data Client               |
  WP3: Analytics Engine           |
       |                         |
Phase 2 (after WP4 + user picks style):
  WP5: App Shell + Layout
       |
Phase 3 (after WP2, WP3, WP5):
  WP6: Individual Widgets (parallelizable per widget)
       |
Phase 4 (after WP6):
  WP7: Live Update Loop + Integration
       |
Phase 5 (after WP7):
  WP8: CLI Entry Point + Packaging
```

**Critical path:** WP1 -> WP2 -> WP6 -> WP7 -> WP8
**Parallel track:** WP4 (mockups) and WP3 (analytics) can proceed independently
**Blocking decision:** User must choose a mockup style before WP5 starts (or WP5 starts with a default and themes are swapped later)

---

## 8. Agent Assignment Recommendations

| Work Package | Recommended Agent Type | Why |
|---|---|---|
| WP1: API Probing | Code agent with HTTP/fetch tools | Needs to make live HTTP calls, parse JSON |
| WP2: Data Client | Backend Python agent | Async HTTP, caching patterns, error handling |
| WP3: Analytics Engine | Backend Python agent (math focus) | Pure functions, heavy on game mechanics math |
| WP4: Design Mockups | Creative/ASCII art agent | Aesthetic judgment, box-drawing, layout sense |
| WP5: App Shell | TUI specialist agent | Textual framework expertise, CSS layout |
| WP6: Widgets | TUI specialist agent (same as WP5) | Widget composition, Textual API |
| WP7: Integration | Full-stack agent | Wiring async systems, error handling, state management |
| WP8: CLI/Packaging | General code agent | Simple, any agent can handle |

**Optimal parallelism:** 3 agents working simultaneously:
- Agent A: WP1 -> WP2 -> WP7 -> WP8 (data pipeline)
- Agent B: WP3 (analytics, independent)
- Agent C: WP4 -> WP5 -> WP6 (UI pipeline, blocked on user design choice between WP4 and WP5)

---

## 9. Risks and Unknowns

### High Risk
- **tRPC response shapes are unknown until probed.** If the API returns unexpected structures or requires authentication, WP1 is blocked. Mitigation: probe early, fail fast.
- **Time-series data does not exist in the API.** We must accumulate our own, meaning the chart is empty on first launch and takes 30+ minutes to populate. Mitigation: persist accumulated data to a local JSON file so restarts do not lose history.

### Medium Risk
- **Textual sparkline/chart limitations.** If the built-in Sparkline widget cannot handle the cookie chart needs (multiple series, labels, scaling), a custom widget will be needed, adding 2-3 hours. Mitigation: evaluate Sparkline capability early in WP5.
- **Terminal.app rendering quirks.** Terminal.app has weaker Unicode and color support than iTerm2. Some box-drawing or color combinations may render poorly. Mitigation: test both terminals throughout, not just at the end.
- **Poll rate vs. API tolerance.** 7 panels polling at 15-30s means 4-6 HTTP calls every cycle. If the API rate-limits, we need to batch or stagger. Mitigation: use a single coordinated fetch cycle (not per-widget polling).

### Low Risk
- **ETH price source.** CoinGecko free API may rate-limit. Mitigation: cache price for 5 minutes, fallback to a configurable static price.
- **Season not active.** If between seasons, most data will be empty. Mitigation: show "No active season" state gracefully.

---

## 10. Validation Plan

### Per Work Package
| WP | Validation |
|----|-----------|
| WP1 | All endpoints return parseable data; models match responses |
| WP2 | Client fetches all data with mocked and live endpoints; cache TTL works; retries work |
| WP3 | Unit tests pass with known fixture data; EV calculations match manual spreadsheet |
| WP4 | User views all 4 mockups in terminal and picks one |
| WP5 | App launches, shows placeholder data, resizes correctly, quits cleanly |
| WP6 | Each widget renders correctly with mock data; handles empty/error states |
| WP7 | Dashboard runs for 10+ minutes without crash; data updates visibly; stale indicator works |
| WP8 | `python -m dashboard` launches correctly; CLI args work; clean exit with q or Ctrl+C |

### End-to-End Acceptance
1. Launch dashboard in Terminal.app at default size
2. See all 7 panels populated with live game data within 30 seconds
3. Watch data update automatically for 5 minutes
4. Resize terminal -- layout adapts without crashing
5. Kill network -- dashboard shows stale indicator, does not crash
6. Restore network -- dashboard recovers and resumes updating
7. Press `q` -- clean exit, no orphan processes

---

## 11. Recommended Approach

**Build the data layer and mockups in parallel, let the user pick a style, then build the UI on top of the data layer using Textual.**

### Why This Approach
- Separating data from display means the expensive work (API client, analytics) is reusable regardless of UI choice
- Mockups first avoids building a UI the user does not like
- Textual gives us the best balance of capability and development speed for a 7-panel responsive dashboard
- Work packages are sized for independent agents with clean interfaces between them

### Implementation Steps (ordered)
1. Probe all APIs, create Pydantic models (WP1)
2. Create 4 mockup files (WP4) -- **in parallel with step 1**
3. Calculate analytics with fixture data (WP3) -- **in parallel with steps 1-2**
4. **User picks a style** (blocking gate)
5. Build data client and cache (WP2)
6. Build Textual app shell with chosen theme (WP5)
7. Build individual widgets (WP6)
8. Wire live update loop (WP7)
9. Package CLI entry point (WP8)

### Open Questions for User
1. **Interactivity level:** Is the dashboard purely read-only, or do you want keyboard navigation (e.g., press 1-7 to focus a panel, arrow keys to scroll leaderboard)?
2. **Persistence:** Should cookie history survive dashboard restarts (write to local file)?
3. **Multiple bakery tracking:** Should the dashboard focus on one specific bakery (yours) or show the entire top-N competitive landscape?
4. **Sound/notifications:** Any interest in terminal bell on specific events (e.g., attack on your bakery)?
5. **Theme hot-switching:** Should you be able to press a key to cycle themes at runtime, or is one theme baked in at launch?
