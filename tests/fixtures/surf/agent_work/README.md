# Agent work launch membership

The three JSON files are unedited public, keyless `GET /jobs/{id}` responses
captured on 2026-10-13 from the IMD control-plane endpoint pool (`api.imd.fun`
and `identitymdcontrol-plane-production.up.railway.app`).

- `f708c332-034f-47b3-b204-318734811863`: completed work with a live launch.
- `6a7439e9-e9aa-469b-bdb5-633bd6c7f423`: blocked work requesting a launch,
  but with no launch ID or status.
- `22624be0-d2da-400e-91c4-51dac0a9a7f5`: completed work with an explicit
  negative launch object.

These establish that a seat work row's launch *kind* is not evidence that
the work was launched. Tests also use synthetic invalid/changed fields to
exercise cache validation and state transitions without network access.
