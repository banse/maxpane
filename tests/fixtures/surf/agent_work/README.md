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

2026-11-12 public captures (no keys; seat 420):

- `63d64980…`: live production launch; `d3229638…`: independent audit.
- `51eb88fe…`: goal; `bd06951d…`: research report. The full job responses are
  unedited and retain their served templates, launch and workflow objects.
- `seat-420-20261112.json.gz`: exact full `GET /seats/420` response, compressed.
  3,453 submission rows; 3,301 accepted submissions; 3,297 accepted distinct jobs
  out of 3,439 distinct attempted jobs. Independent paginated reads agreed.
- `seat-420-context-20261112.json.gz`: normalized membership cache from the live
  production reader and complete oracle-index coverage metadata. The job and
  chain maps retain only this seat's candidate IDs. These are frozen inputs,
  not expected results: the offline test independently projects all counters.
  The four oracle-node jobs without a request are proven absent by the complete
  index; they are not assumed to be testnet jobs. Launch-kind intent alone is
  still insufficient: 53 intent-tagged jobs yield 23 verified production jobs.
