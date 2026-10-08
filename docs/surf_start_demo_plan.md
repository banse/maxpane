# SURFBOARD equipment rack start-screen demo

## Approved scope

The owner asked for “only create a design template with mock data that's content can be replaced with real data later,” selected “2” (Equipment Rack), and requested “2 versions: 1 with 5 card rows one with 4 card rows.” The grid retains six columns. For the five-row version, “the terminal should cover the bottom 3 rows,” with “1 card column left and right for both versions.”

Build a standalone Textual demo, not a registered dashboard. Use the existing Python/Textual environment and keep all records explicitly marked as mock data. Do not add real data clients, credentials, shell execution, network requests, or production dashboard navigation. The owner's mock-only instruction governs preview data; no live-data render is needed for this template. Superpowers are excluded by the owner.

## Layout and content contract

| Variant | Full card rows | Terminal placement | Side cards below full rows | Total slots | Empty slots |
| --- | --- | --- | --- | --- | --- |
| Five rows | Rows 1–2, six cards each | Columns 2–5, rows 3–5 | One in column 1 and one in column 6 for each lower row | 18 | 8 |
| Four rows | Row 1, six cards | Columns 2–5, rows 2–4 | One in column 1 and one in column 6 for each lower row | 12 | 2 |

The user-confirmed target is **149 columns × 45 rows**, also the default size for CLI preview exports. Cards have a minimum height of seven terminal lines. The dense five-row variant puts each compact meter in the bottom frame; the four-row variant uses the available height for taller cards.

Populate ten slots with Announce, Swarm, Agent, Board, Launchpad, Pool4, Protocol, Swarm Tokens, Portfolio, and Earnings; retain visible equipment casings in every remaining slot. Swarm Tokens, Portfolio, and Earnings are future dashboards, marked planned with an unlit lamp, an empty meter, and a coming-soon readout. Cards use dark faceplates, small corner fasteners, a dashboard name, a status lamp, an inset metric readout, and a compact meter. Empty slots use a dim casing and unlit lamp. The central terminal is recessed and darker, with IMD-inspired mock event lines and a prompt. Both variants span the bottom three rows, as requested in the follow-up. Replacement records are limited to twelve so switching to the smaller variant cannot silently hide a populated card.

Keep mock card records and terminal lines separate from layout construction so later data replacement requires no geometry edits. Use a small local data representation and ordinary Textual composition; introduce no shared framework or forced MVC layers. Terminal commands are limited to local `help`, `clear`, and `reset` actions.

## Run and interact

Run either variant from the repository root:

```bash
.venv/bin/python scripts/surf_start_demo.py --rows 5
.venv/bin/python scripts/surf_start_demo.py --rows 4
```

Use `4`/`5` to switch layouts, `Tab` to select a card, and `Enter` for its mock preview. `/` focuses the terminal; `Escape` returns to cards; `q` exits. Terminal input supports `help`, `clear`, and `reset` without executing external commands.

## Work packages

### 1. Implement and verify the standalone demo — root session

**Owned files:** `scripts/surf_start_demo.py`, `tests/screens/test_surf_start_demo.py`. This plan is owned by the planning agent; existing production files remain outside the implementation package.

**Dependency:** Approved Equipment Rack design and the layout/content contract above.

**Work:** Write focused failing tests for the two arrangements, implement the smallest demo that satisfies them, then render both variants. Export previews to a temporary directory; do not commit preview artifacts. Target fewer than 1,000 production lines, with no separate task review.

**Acceptance criteria:**

- The script runs from the repository using its existing virtual environment, accepts both row choices, and switches variants using the stated keys.
- The five-row variant shows two full rows of six cards; the four-row variant shows one. The bottom three rows retain one side card on each side of the terminal.
- At 149 columns × 45 rows, terminal bounds cover exactly the middle four columns and the final three rows in both variants; widgets do not overlap or escape the intended layout. Cards retain their seven-line minimum, with the five-row meters in the bottom frame and taller cards in the four-row variant.
- The five-row variant has 18 card slots and the four-row variant has 12. Each contains ten populated cards, with the stated count of visible empty slots.
- Composited output includes dashboard names, readable mock values, visible empty slots, and an explicit mock-data indication. Assertions inspect rendered strips and actual widget geometry rather than only source content.
- Card preview, focus navigation, and the local `help`/`clear`/`reset` commands work with the stated controls. Terminal input cannot execute shell commands or access the network. No production app registration or data flow changes are made.
- Both temporary rendered previews are visually inspected and shown before final review. Run the focused demo tests and the repository's applicable fast guards; do not run the full suite. Prove the key geometry assertions detect a deliberate layout regression and restore the original source afterward.

### 2. Independent final review — one reviewer

**Ownership:** Read-only review of the completed scoped diff; root retains all fix ownership.

**Dependency:** Package 1 is complete, previews inspected, and focused verification is green.

Check the two layouts, mock-only boundary, replaceable content, rendered-output test assertions, and CLI/key switching. Follow the repository reviewer contract and report only evidenced findings. Root handles one fix wave for Critical/Important findings, with one scoped re-review only if production code changes. Record Minor-only residuals through the repository's existing follow-up process rather than expanding this demo.
