# MAXPANE — Product Requirements Document

**Version:** 0.1 (Draft)
**Date:** 2026-03-27
**Status:** Pre-MVP
**PMF Score:** 9.5/10 (Ralph Loop, 4 Iterations)

---

## 1. Problem Statement

dApp frontends in the Ethereum ecosystem are broken in three ways: they are **fragmented** (every protocol ships its own web UI, forcing users to juggle dozens of tabs), **censorable** (centralized web frontends can be taken down by domain seizures, OFAC sanctions, or hosting provider pressure — as seen with Tornado Cash, IPFS gateway censorship, and ENS frontend disputes), and **bloated** (heavy React SPAs for what is fundamentally just onchain data). Power users, DAO operators, and developers need a unified, lightweight, censorship-resistant way to interact with multiple protocols from a single interface.

## 2. Solution Overview

MAXPANE is an open-source terminal framework and the **Pane Protocol** — an open standard that lets any dApp describe its terminal-based frontend as a JSON schema. The MAXPANE client renders these schemas as ASCII panels in a fullscreen terminal dashboard. There is no central web server to censor. The interface runs locally in the user's terminal. Community members build, share, and review Panes with onchain reputation attestations.

## 3. Why Now

Four trends converge in 2026 to create a perfect window for MAXPANE:

**Frontend censorship is escalating.** Since the Tornado Cash sanctions in 2022, the surface area for frontend-level censorship has expanded. Regulators have realized they can't shut down smart contracts but they can pressure frontend providers. The demand for unstoppable interfaces is no longer theoretical — it's operational.

**L2 fragmentation is at its peak.** With Arbitrum, Base, Optimism, Blast, Scroll, zkSync, and dozens of app-specific rollups, users need an aggregated view across chains. No single dApp frontend solves this. A unified terminal does.

**TUI renaissance in developer tooling.** LazyGit, k9s, lazydocker, bottom, and dozens of other terminal UIs have proven that developers not only accept TUIs — they prefer them. The tooling ecosystem (Ratatui, Bubbletea, Textual) is mature enough to build production-grade terminal apps.

**Post-FTX "verify don't trust" mentality.** After the collapse of centralized exchanges and opaque frontends, the crypto community demands transparency. A terminal that reads directly from the chain, with no intermediary frontend server, is the ultimate expression of this principle.

---

## 4. Target Users

### Persona 1: "The DAO Operator" — Maya

Maya manages treasury operations for a mid-size DAO. She monitors Aave lending positions, Uniswap LP positions, ENS domains, and governance proposals across three L2s — daily. Currently she has 12 browser tabs open, switches between Etherscan, DeBank, Tally, and Snapshot, and still misses things. She wants one screen that shows everything, updates in real-time, and doesn't depend on any third-party frontend that could go down.

**Needs:** Multi-protocol monitoring, cross-chain aggregation, real-time alerts, keyboard-driven workflow.

### Persona 2: "The Terminal Trader" — Kai

Kai is a power trader who already lives in the terminal for everything else (tmux, vim, git). He hates switching to a browser to check token prices or execute swaps. He wants to access Uniswap, check gas prices, and monitor his portfolio without leaving his terminal. He also cares about censorship resistance — he's been burned by frontend outages during high-volatility events.

**Needs:** Fast data access, transaction execution (Phase 2), minimal latency, keyboard shortcuts, censorship resistance.

### Persona 3: "The Protocol Dev" — Sora

Sora builds smart contracts and needs to debug live contract state, watch events, decode transaction calldata, and monitor contract interactions — all while coding in her editor. She uses Foundry's `cast` for one-off queries but wants a persistent dashboard that shows her contract's live state alongside her development workflow.

**Needs:** ABI-aware contract inspection, event streaming, calldata decoding, integration with existing terminal workflow.

---

## 5. User Stories

### Phase 1 (Read-Only)

1. As a DAO operator, I want to see my multi-protocol positions across L1 and L2s in a single terminal screen, so that I don't miss critical changes.
2. As a trader, I want to view real-time token prices from Uniswap pools without opening a browser, so that I can react faster during volatility.
3. As a developer, I want to inspect live smart contract storage slots and watch events in my terminal, so that I can debug without context-switching.
4. As a user, I want to install community-built Panes for any dApp, so that I can extend my dashboard without writing code.
5. As a user, I want to arrange Panes in a customizable layout (splits, tabs, stacks), so that I can optimize my workflow.
6. As a user, I want MAXPANE to work without any centralized server, so that my access to onchain data cannot be censored.
7. As a Pane author, I want to define my Pane's interface in a simple JSON schema, so that I can add terminal support for my dApp in hours, not weeks.
8. As a user, I want a keyboard-driven interface with vim-like bindings, so that I never need to reach for the mouse.

### Phase 2 (Interactive)

9. As a trader, I want to sign and submit transactions from within MAXPANE, so that I can execute swaps without leaving the terminal.
10. As a DAO member, I want to vote on governance proposals from my terminal, so that participation is frictionless.
11. As a user, I want MAXPANE to integrate with my hardware wallet for transaction signing, so that my keys stay secure.

### Phase 3 (Multiplayer)

12. As a DAO, we want shared terminal sessions where all members see the same dashboard in real-time, so that governance discussions have a shared visual context.

---

## 6. The Pane Protocol

The core innovation of MAXPANE is the Pane Protocol — a standardized JSON schema that any dApp can implement to describe its terminal interface.

### Schema Overview

```json
{
  "pane": {
    "name": "Uniswap Pool Watcher",
    "version": "1.0.0",
    "author": "0x1234...abcd",
    "chains": ["ethereum", "arbitrum", "base"],
    "description": "Live Uniswap V3 pool prices and volume"
  },
  "data": {
    "sources": [
      {
        "id": "pool_price",
        "type": "contract_read",
        "chain": "ethereum",
        "address": "0x...",
        "abi": "function slot0() view returns (uint160, int24, ...)",
        "method": "slot0",
        "refresh": "12s"
      }
    ]
  },
  "layout": {
    "type": "vertical",
    "children": [
      {
        "type": "header",
        "content": "ETH/USDC · Uniswap V3"
      },
      {
        "type": "table",
        "columns": ["Pair", "Price", "24h Volume", "TVL"],
        "rows": "{{data.pool_price | format}}"
      },
      {
        "type": "chart",
        "style": "sparkline",
        "data": "{{data.pool_price.history}}"
      }
    ]
  },
  "keybindings": {
    "r": "refresh",
    "c": "copy_price",
    "/": "search_pools"
  }
}
```

### Design Principles

**Declarative, not imperative.** Pane authors describe what to show, not how to render it. The MAXPANE client handles rendering, theming, and layout. This keeps Panes portable and safe — a malicious Pane cannot execute arbitrary code.

**Data-driven.** All data sources are explicitly declared — contract reads, event subscriptions, API calls. The client fetches data and binds it to the layout template. No hidden network requests.

**Versioned.** The protocol schema is versioned. Panes declare which version they target. The client maintains backward compatibility.

---

## 7. Feature Prioritization (MoSCoW)

### Must Have (MVP)

- Pane Protocol JSON schema specification (v0.1)
- Terminal renderer (Ratatui-based) with split/tab layouts
- 4 starter Panes: Uniswap (prices), Aave (lending rates), ENS (name lookup), ERC-20 (token balances)
- Multi-chain support: Ethereum L1, Arbitrum, Base, Optimism
- Keyboard-driven navigation (vim-like bindings)
- Local configuration file (~/.maxpane/config.toml)
- Matrix-style boot sequence (optional, toggleable)
- Pane install from local file or Git URL

### Should Have (Post-MVP)

- Community Pane registry (Git-based or IPFS-pinned index)
- Onchain reputation attestations for Pane authors (EAS)
- Custom color themes (C64, Amber, Phosphor Green, custom)
- Event subscription and real-time streaming
- Pane search and discovery CLI (`maxpane search uniswap`)
- Cross-chain wallet balance aggregation

### Could Have (Phase 2+)

- Transaction signing (WalletConnect v2 integration)
- Hardware wallet support (Ledger, Trezor via USB)
- Governance voting from terminal
- Pane-to-Pane data piping (Unix philosophy)
- Multiplayer shared sessions (Phase 3)

### Won't Have (Out of Scope)

- Web-based UI (defeats the purpose)
- Centralized backend or API server
- Proprietary Pane format
- Token or coin launch

---

## 8. Competitive Analysis

| Product | What It Does | vs. MAXPANE |
|---------|-------------|-------------|
| **Etherscan** | Block explorer, web-based | Read-only, per-chain, centralized frontend, no customization |
| **DeBank/Zapper** | Portfolio tracker, web-based | Aggregated but centralized, no terminal, no extensibility |
| **Foundry (cast)** | CLI tool for contract interaction | Single commands, no persistent dashboard, no community plugins |
| **Dune Analytics** | SQL-based onchain analytics | Powerful but web-based, query-focused, not real-time monitoring |
| **Frame.sh** | Desktop wallet with dApp browser | Closest in spirit but GUI-based, no terminal, no protocol standard |
| **Terminal-based explorers** | Various small projects | Fragmented, single-purpose, no standard, no ecosystem |

**MAXPANE's unique position:** The only project that combines a standardized open protocol (Pane Protocol) with a terminal-native renderer, community extensibility, and censorship resistance by design. No web server. No centralized frontend. No single point of failure.

---

## 9. Success Metrics (KPIs)

### North Star Metric

**Weekly Active Pane Sessions** — number of unique users who open MAXPANE and interact with at least one Pane per week.

### Supporting Metrics

| Metric | Target (6 months) | Why It Matters |
|--------|-------------------|----------------|
| GitHub stars | 2,000+ | Community interest signal |
| Published community Panes | 20+ | Ecosystem health |
| Pane Protocol adopters (dApps) | 5+ protocols | Standard adoption |
| Contributors | 30+ | Open-source sustainability |
| Grant funding secured | 2+ grants | Financial sustainability |
| Discord/Telegram members | 500+ | Community size |
| Weekly active users | 200+ | Actual usage |
| Boot-to-first-data latency | <3 seconds | UX quality |

---

## 10. Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Pane Protocol too complex for dApp teams** | High | Ship with dead-simple starter template + CLI generator (`maxpane init`). First Panes should be buildable in <1 hour. |
| **RPC rate limits / costs** | Medium | Default to public RPCs, support user-provided keys (Alchemy, Infura). Implement aggressive caching and smart polling. |
| **Security of community Panes** | High | Pane Protocol is declarative (no arbitrary code execution). Panes can only read from declared sources. Onchain reputation + community review. |
| **Low adoption / chicken-and-egg** | Medium | Ship 4 high-quality starter Panes that are immediately useful. Don't wait for community — lead with value. |
| **TUI fatigue / niche audience** | Medium | The demoscene branding makes it feel like a movement, not just a tool. Viral bootscreen drives awareness beyond the terminal-native audience. |
| **L2 RPC fragmentation** | Low | Abstract chain configuration. Support custom RPC endpoints. Target the 4 biggest L2s first. |

---

## 11. 90-Day Roadmap

### Weeks 1-2: Foundation

- Pane Protocol JSON schema specification (v0.1) — formalize and document
- Rust project scaffold with Ratatui
- Basic terminal renderer: single Pane, full screen
- RPC abstraction layer (ethers-rs / alloy) for L1 + L2s
- Config file parser (~/.maxpane/config.toml)

### Weeks 3-5: Core Framework

- Layout engine: splits (horizontal/vertical), tabs, stacking
- Keyboard navigation system (vim-like: hjkl, /, :commands)
- Pane loading from local JSON files
- Data fetching engine: contract reads, polling, caching
- ABI decoding for contract return values

### Weeks 6-8: Starter Panes

- Uniswap Pane: pool prices, top pairs, sparkline charts
- Aave Pane: lending rates, supply/borrow positions
- ENS Pane: name lookup, registration status, expiry
- ERC-20 Pane: wallet token balances across chains

### Weeks 9-10: Polish & Branding

- Matrix boot sequence (animated, toggleable)
- Color themes: Phosphor Green, Amber, C64, custom
- Pane install CLI: `maxpane install <git-url>`
- Error handling, loading states, empty states
- Performance optimization (target <3s boot-to-data)

### Weeks 11-12: Launch Preparation

- GitHub repository setup, README, CONTRIBUTING.md
- Demo video / GIF for README and Twitter
- Documentation site (mdBook or similar)
- Submit to Ethereum Foundation / Optimism RPGF grants
- Soft launch on Crypto Twitter + Ethereum developer communities

---

## 12. Technical Constraints

- **No web server.** MAXPANE runs entirely locally. All data comes from RPC endpoints.
- **No arbitrary code in Panes.** The Pane Protocol is declarative. This is a security boundary that must never be compromised.
- **Rust only for core.** Performance matters in terminal rendering. Ratatui is the de-facto standard.
- **JSON Schema for Panes.** Not YAML, not TOML, not a custom DSL. JSON is universal, tooling exists, and it's parseable everywhere.
- **Support at minimum: Ethereum L1, Arbitrum, Base, Optimism.** Additional chains can be added via config.

---

## 13. Open Questions

1. **Pane discovery mechanism:** Git-based registry (like Homebrew taps) vs. IPFS-pinned index vs. onchain registry? Each has trade-offs in decentralization, discoverability, and complexity.
2. **Transaction signing architecture (Phase 2):** WalletConnect v2 vs. direct keystore integration vs. external signer? Security implications are significant.
3. **Multiplayer protocol (Phase 3):** P2P (libp2p) vs. relay-based? How to handle latency for real-time shared views?
4. **Pane sandboxing:** Is declarative-only sufficient, or do we need a WASM sandbox for advanced Panes that need computation?
5. **Governance:** How does the Pane Protocol itself evolve? EIP-style process? Benevolent dictator? DAO?

---

*Generated by IdeaRalph · PMF Score: 9.5/10 · "My terminal tastes like the blockchain!"*
