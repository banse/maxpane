# Surfboard text-color alignment

Owner scope (2026-10-10): match the new SWARM TOKENS and PORTFOLIO tables and
IMD terminal text to the existing MaxPane tables, using the supplied Matrix
screenshots. Change only text colors. Preserve content, boldness, layout,
backgrounds, borders, links, interaction and data handling.

Tier 2: three views, one root-owned package under 100 production lines.
No package review; one final review. The three widget modules own the change;
no shared stylesheet, screen geometry or data contract changes are needed.

Implementation plan:

1. Compare composited foregrounds with BASE TRADING's native table in a failing test.
2. Let ordinary table cells inherit the native foreground; keep semantic colors.
   Scope header and marker colors so they do not leak into adjoining cells.
3. Use the native foreground and existing green/red status colors in the IMD
   terminal, with neutral secondary text and its existing backgrounds/borders.
4. Compare before/after text, regions, backgrounds, boldness and link metadata;
   show fresh keyless live renders at 149×45 before final review.
5. Run touched/composing tests, address checks, fast guards and doc pins; review
   the scoped diff and commit.

Verification so far: all eight new compositor cases failed on the original
colors and pass after the change. Before/after captures of all three complete
views have identical text, regions and non-foreground styles, including links.
Fresh live Matrix captures were inspected and shown to the owner. Existing
source coverage remains explicitly partial where providers lack data.
