# C64 text-mode preview

From the MaxPane checkout:

```bash
.venv/bin/python scripts/c64_text_demo.py
```

The separate, offline demo shows a fixed **40-column × 25-row** character
buffer with the BASIC V2 startup banner, memory message, `READY.` and a
blinking block cursor. The startup text and logical grid follow the
[Commodore 64 User's Guide](https://www.commodore.ca/manuals/c64_users_guide/c64-users_guide-01-setup.pdf).

- **R:** restart the cursor blink.
- **Q / Escape:** exit.
- Minimum terminal: **88 columns × 34 rows**, including the key legend.
  Smaller windows show a resize notice instead of cropping the screen.

This first text-mode experiment uses the terminal's own font. Each logical
character occupies two terminal columns (glyph plus space); four cells of
light-blue border surround the 80×25 terminal-cell picture. The resulting
88×33 frame is approximately 4:3 with a typical 1:2 terminal-cell aspect.
Actual proportions depend on the terminal font and line spacing.

This is a display preview, not an original PETSCII bitmap-font renderer,
PAL raster simulation or BASIC interpreter. It neither changes MaxPane's
startup nor loads dashboard data. The earlier house demos remain separate.
