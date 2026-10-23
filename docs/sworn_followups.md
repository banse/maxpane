# Sworn follow-ups

2026-10-23. Main Explorer plus large detail popup implemented from proposals 1/3.

- Native Kitty/Ghostty output needs an actual terminal visual check: image
  replacement, popup close, dashboard navigation and font/viewport resizing.
  Protocol commands, ownership, placeholders and the same-SVG character fallback
  have automated coverage. Headless screenshots do not certify native pixels.
- Older SURF registration test
  `test_a_full_outage_renders_explicit_states_not_zeros` expects a generated
  outage banner removed under the owner's display override. Reproduced at
  unchanged commit `611686e9` in an isolated archive and HOME on Python 3.11.
  Update its expectation when that existing SURF behavior is next touched.
- The SWARM TOKENS stylesheet agreement guard also fails at unchanged commit
  `bc51d933`, reproduced in an isolated archive and HOME on Python 3.11. Its
  extraction runs through the following SWORN CSS block because its old
  `PORTFOLIO` end marker is absent. Repair the guard's section boundary when
  that test is next touched; the wallet-popup/layout change does not edit
  either stylesheet or SWARM TOKENS screen.

Collection-wide family scans, an owned-token index, ENS search and a gallery
remain outside this first dashboard. Unvisited rows have unknown family counts;
community detail explicitly says how many metadata entries are shown when the
Renderer caps its list. Neither count is fabricated.
