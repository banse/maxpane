# PEPEPANE install probe — seat #7 (imd-vps)

**Status: placeholder — not yet run.** Owner decision spec §16 #17 approves one measurement run on the VPS. Until
`deploy/vps/probe_seat_host.sh` has been run there as root (after `install.sh`, spec §12.1 step 8), this file holds only
the section list the probe prints, in the order it prints them (spec §14 "Only on the VPS"). Replace everything below
the rule with the probe's stdout, keep the `## N. …` headings it emits, and re-run `tests/test_seat_deploy_files.py`
— the numbered list is bound to the script's `--list` output.

What the run records that no fixture can (spec §18 open questions 17–20): the exit status and seek behaviour of
`journalctl --after-cursor` with a vacuumed cursor on systemd 259; whether `compression.zstd` imports on the VPS's
Python 3.14.4 build; whether `imd status` and `imd doctor` complete under the transient-unit posture and their scopes'
`memory.peak`; the sysstat `HISTORY` depth; plus the slice `memory.peak` after a real `pepepane` session and the audit
and verify lines of one drained restart (owner, by hand — the probe prints the procedure under its last heading).

Regenerate on the VPS (root; add `--skip-doctor` to save the runtime turn):

~~~sh
bash /opt/imd-dash/src/deploy/vps/probe_seat_host.sh > /root/seat_install_probe.md
~~~

---

## Mac build measurements (2026-09-27)

The lean entrypoint cold physical peak was **58.8 MiB**, measured on macOS arm64 with Python 3.11.15 and Textual 8.2.8
using the libproc fallback in `scripts/pty_footprint2.py`; the budget stays 160 MiB. The historical **142 MiB** research
measurement used the full MaxPaneApp with all managers and is a different measurement. The lean import graph still
loads the Base/FrenPet module graphs through `data/__init__.py`, but constructs only SeatManager.
The in-situ healthy and worst fixture layout measured **134 columns by 50 rows**; LEDGER has a named width exception
and its full tier clears at **210 columns**. VPS physical peak, child peaks and layout certification are not yet run.

## Sections

1. connect(/run/imd-dash/broker.sock) as imd-dash succeeds (ping)
2. connect(/run/imd-dash/broker.sock) as imd-worker fails (EACCES: 0660 root:imd-dash in a 0755 root dir)
3. journalctl -u imd-worker.service as imd-dash: 14-day read count (group systemd-journal)
4. journalctl --after-cursor with a deliberately stale cursor: exit status and first entry vs the oldest
5. systemctl show imd-worker.service as imd-dash (unprivileged D-Bus read)
6. cgroup counters of imd-worker.service as imd-dash (0644)
7. python3 -c 'import compression.zstd' on /usr/bin/python3 (rollouts older than 7 days)
8. pepepane --once --offline as imd-dash (PATH via the /usr/local/bin symlink, imports, exit status)
9. broker ping (version, posture_ok, drain_armed, in_flight)
10. seat projection canary: no secret key name, no stray hex64, deviceKey == whoami
11. status through the broker as a transient unit, with the child scope's memory.peak
12. doctor through the broker (plan, apply, verify), with the child scope's memory.peak
13. plan restart while a task runs is refused; never applied by this script
14. sha256sum -c MANIFEST.sha256 on the installed broker files, units, wheel and lock (root)
15. runuser -u imd-worker -- ls /home/imd-dash must fail (root)
16. sshd -T -C user=imd-dash: allowtcpforwarding no (root)
17. systemctl show user-<uid>.slice: MemoryMax, CPUQuota, MemoryPeak (root)
18. grep HISTORY /etc/sysstat/sysstat: sar depth (root)
19. drained restart at a natural idle gap: audit lines, verify, slice memory.peak (owner, by hand)
