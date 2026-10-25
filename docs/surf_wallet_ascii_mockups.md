# WALLET / SWARM — drei ASCII-Entwürfe für den Boardroom

Stand: 2026-10-25. **Nur ASCII-Design, keine Implementierung.** MY CONTRACTS
bleibt zurückgestellt. Nutzerkorrektur: ausschließlich die Nutzung einer Wallet
mit dem Swarm, ohne Trading und ohne Details ihrer Agents. Die AGENT-Ansicht
liefert nur die visuelle Vorlage. Einstiegsvorschlag ist eine WALLET-Karte im
Boardroom; weder Navigation noch neue Tasten sind bereits implementiert.

Alle Namen, Zahlen, Zeiten und Zustände sind **DEMO**. Adressen und IDs sind
Platzhalter. Die [Datengrundlagen](surf_wallet_game_mechanics.md) beschreiben
Quellen und Grenzen. Jeder ASCII-Entwurf passt rechnerisch in 149×45; dies ist
kein gemessener Textual-Layout-Pin und keine ausführbare Vorschau.

## Gemeinsame Gestaltung und Umfang

- Sechs gleich breite Rack Cards pro Reihe, dunkles Inset, neutrale Rahmen und
  große grüne Ziffern. A nutzt zwei Reihen wie die bestehende AGENT-Ansicht.
- Inhalt: eigene Jobs, Fortsetzungen, Workflows, Launches, Oracle-Anfragen,
  Schedules, Top-ups, Zahlungen, Rückerstattungen und zugehörige Ergebnisse.
  Seats, Worker, Agent-Leistung, Aufwand, Rankings und Agent-Rewards entfallen.
- Kartenwerte zentriert, Tabellen linksbündig. Amber nur für fachlichen
  Handlungsbedarf; Text und Auswahlmarker ergänzen Farbe. Kontrastprüfung und
  echte Tastaturtests gehören zur späteren Textual-Vorschau.
- Zeitraum steuert die gefundenen Requests und Zahlungen; ihre aktuell bekannten
  Zustände werden dazu angezeigt. Typ-/Statusfilter verändern nur RECORD und
  dessen sichtbare Trefferzahl, nicht stillschweigend die Hero-Zähler.
- Bereits geladene Daten erscheinen sofort. Die Übersicht lädt selbständig,
  ohne Detailbesuch. Große ungelesene Werte bleiben leer; gemeinsamer Ladefooter
  statt Card-Loader. Wallet-Wechsel isolieren Cache und verspätete Antworten.
- Alle Bedienhinweise sind Vorschläge. Enter öffnet den betreffenden Auftrag
  oder Beleg; Escape führt zurück zum Boardroom. Keine Agent-Navigation.
- Coverage benennt begrenzte Historie. Technische Quellenfehler bleiben intern;
  die Ansicht behauptet keine vollständige Lifetime-Historie.

## Gemeinsamer DEMO-Datensatz

Zeitraum: 2026-09-25 12:00 bis 2026-10-25 12:00 UTC (`30D`).

| Karte | DEMO | Bedeutung |
|---|---:|---|
| REQUESTS | 84 | Eindeutige beobachtete Orders einschließlich Zahlungsversuchen |
| JOBS | 42 | 32 neue Jobs + 10 Fortsetzungen |
| WORKFLOWS | 12 | Workflow-Requests; 10 verknüpfte Workflows geliefert |
| LAUNCHES | 8 | Launch-Requests; 6 verknüpfte Deployments bestätigt |
| ORACLES | 16 | Oracle-Requests; 14 verknüpfte Antworten attestiert |
| SCHEDULES | 6 | 2 Create- + 4 Topup-Requests; keine Anzahl ausgeführter Runs |
| IN FLIGHT | 5 | Requests mit laufender Arbeit: 2 Jobs, 1 Workflow, 1 Launch, 1 Oracle; blockierte separat |
| ATTENTION | 4 | 2 blockierte Arbeiten, 1 fehlgeschlagene Lieferung, 1 pausierte Schedule; eindeutige offene Follow-ups |
| PAYMENTS | 78 | Bestätigte Zahlungen; weitere 6 Versuche unbestätigt |
| PAID | 62.5 IMD | Belegte Bruttozahlungen im Fenster |
| REFUNDS | 1.0 IMD | Belegte Rückzahlungen zu Requests, separat von PAID |
| LAST ACTION | 11:42 UTC | Jüngste beobachtete direkte Wallet-Aktion am 10-25: job.continue |

42 + 12 + 8 + 16 + 6 = 84. Untergeordnete Jobs, Zahlungen und Ergebnisse
vermehren diese Request-Zahl nicht. HTTP- und Intake-Belege desselben Auftrags
werden verknüpft. Zahlungen stammen aus fiktiven Receipts, nicht aus einem
angenommenen Einheitstarif. Andere Assets, Chains und Gas bleiben getrennt.
Es gibt keine Earnings-, Profit- oder Agent-Performance-Kennzahl.

Von zwei erstellten eigenen Schedules ist eine aktiv und eine pausiert. Einer
der vier Topups finanziert einen fremden Schedule; das verleiht kein Eigentum.
Refunds und automatisch ausgeführte Schedule-Runs sind verknüpfte Vorgänge,
keine neuen direkten Wallet-Requests. Eine fehlgeschlagene Zahlung ist sichtbar,
begründet jedoch keinen ausgeführten Job. Historische Zahlungsfehler erscheinen
im Verlauf; ATTENTION zählt nur noch offene Follow-ups.

## A — Wallet Rack: Aufträge und Nutzung auf einen Blick

Zwölf Hero Cards über RECORD. Reihe eins zeigt die beauftragten Leistungen,
Reihe zwei laufende Aufträge, offene Punkte, Zahlungen und letzte Nutzung.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | 30D: 09-25 12:00 to 10-25 12:00

+- REQUESTS ----------+ +- JOBS --------------+ +- WORKFLOWS ---------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- SCHEDULES ---------+
|    OBSERVED / 30D   | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |            _        | |            _        | |          _          | |            _        | |          _          |
|       |_| |_|       | |       |_|  _|       | |         |  _|       | |         |_|         | |         | |_        | |         |_          |
|       |_|   |       | |         | |_        | |         | |_        | |         |_|         | |         | |_|       | |         |_|         |
|                     | |                     | |                     | |                     | |                     | |                     |
|   paid + attempts   | |32 open / 10 continue| |      10 shipped     | |      6 deployed     | |     14 attested     | | 2 creates / 4 topups|
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

+- IN FLIGHT ---------+ +- ATTENTION ---------+ +- PAYMENTS ----------+ +- PAID --------------+ +- REFUNDS -----------+ +- LAST ACTION -------+
|   LINKED REQUESTS   | |      FOLLOW-UPS     | |   CONFIRMED / 30D   | |    IMD / SETTLED    | |    IMD / RECEIVED   | |     UTC / 10-25     |
|                     | |                     | |                     | |                     | |                     | |                     |
|          _          | |                     | |        _   _        | |     _   _     _     | |             _       | |                 _   |
|         |_          | |         |_|         | |         | |_|       | |    |_   _|   |_     | |        |   | |      | |    |   | . |_|  _|  |
|          _|         | |           |         | |         | |_|       | |    |_| |_  .  _|    | |        | . |_|      | |    |   | .   | |_   |
|                     | |                     | |                     | |                     | |                     | |                     |
|   excludes blocked  | | 2 blocked / 2 other | | 6 attempts unsettled| |    gross payments   | |  linked to requests | |     job.continue    |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

RECORD [ALL]  Type [ALL]  Status [ALL]  Chain [ALL]  Search [___________________]  Cards: observed 30D
Coverage: paid latest 100 | Intake history partial | payments and refunds: observed receipts | [details]

WHEN         ACTION             OBJECT           PAYMENT            RESULT / EVIDENCE
------------ ------------------ ---------------- ------------------ ---------------------------------------------------------------
>10-25 11:42 job.continue       Atlas v2         settled            working / <job>
 10-25 10:18 oracle.request     Check release    settled            attested / <oracle>
 10-25 09:45 launch.open        Harbor           settled            deployed / <launch>
 10-24 19:10 workflow.open      Atlas site       settled            blocked: hosting / <workflow>
 10-24 18:30 schedule.topup     Daily check      settled            3 runs added / owned by <other-wallet>
 10-24 17:20 refund             Prior request    +1.0 IMD received  linked payment / <tx>
 10-24 16:30 job.open           New request      failed             no work admitted / <order>
 10-24 15:10 schedule.create    Daily report     settled            active / <schedule>
Newest 8 records shown | related results and refunds do not add extra requests

SELECTED: Atlas v2 | paid 0.5 IMD | work running | request <order> -> project <project> -> job <job>
Enter details | / search | f filters | i wallet | x open evidence | r refresh | Esc boardroom
```

**Vorteil:** Vertrautes AGENT-Layout mit ausschließlich walletbezogenen Zahlen.
**Nachteil:** Ausführliche Auftragsdetails brauchen eine eigene Detailansicht.

## B — Aufträge und Zahlungen: Auswahl mit dauerhaftem Detailbereich

Sechs Hero Cards, darunter Auftragsliste, Zahlungsbelege und Schedule-Übersicht.
Die rechte Spalte zeigt den ausgewählten Auftrag und dessen Ergebnis.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | 30D: 09-25 12:00 to 10-25 12:00

+- REQUESTS ----------+ +- IN FLIGHT ---------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- PAID --------------+ +- REFUNDS -----------+
|    OBSERVED / 30D   | |   LINKED REQUESTS   | |       REQUESTS      | |       REQUESTS      | |    IMD / SETTLED    | |    IMD / RECEIVED   |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |          _          | |          _          | |            _        | |     _   _     _     | |             _       |
|       |_| |_|       | |         |_          | |         |_|         | |         | |_        | |    |_   _|   |_     | |        |   | |      |
|       |_|   |       | |          _|         | |         |_|         | |         | |_|       | |    |_| |_  .  _|    | |        | . |_|      |
|                     | |                     | |                     | |                     | |                     | |                     |
|   paid + attempts   | |   excludes blocked  | |      6 deployed     | |     14 attested     | |    gross payments   | |  linked to requests |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Window [30D]  Type [ALL]  Status [ALL]  Chain [ALL]  Search [______________________]
Coverage: paid latest 100 | Intake history partial | payments and refunds: observed receipts | [details]

MY REQUESTS / 84 observed                                                                SELECTED / Atlas v2
JOBS 42 | WORKFLOWS 12 | LAUNCHES 8 | ORACLES 16 | SCHEDULE ACTIONS 6                    -----------------------------------------------------
OBJECT            ACTION             PAYMENT        RESULT                               Action       job.continue
> Atlas v2        job.continue       settled        working                              Paid         0.5 IMD confirmed
  Check release   oracle.request     settled        attested                             Request      <order> [open]
  Harbor          launch.open        settled        deployed                             Project      <project> [open]
  Atlas site      workflow.open      settled        blocked                              Job          <job> [open]
  Daily check     schedule.topup     settled        3 runs added                         Continued    previous version
  New request     job.open           failed         not admitted
                                                                                         RESULT
PAYMENTS / 78 confirmed | 6 attempts unsettled                                           Work running
WHEN         REQUEST          OUTFLOW       REFUND       EVIDENCE                        Artifacts appear when delivered.
10-25 11:42  Atlas v2         0.5 IMD       --           <tx> [open]
10-24 17:20  Prior request    --            1.0 IMD      <tx> [open]                     COSTS / 30D
10-24 16:30  New request      --            --           payment failed                  Gross paid   62.5 IMD
                                                                                         Refunded      1.0 IMD
SCHEDULES / 2 created | 4 topups                                                         Other assets and gas remain separate.
Daily report: active | 1 other own schedule paused
Daily check: funded by this wallet, owned by <other-wallet>                              ATTENTION / 4 follow-ups
Runs and outcomes stay linked to their schedule.                                         2 blocked / 1 failed / 1 paused

Tab section | up/down select | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Auftrag, Kosten und Belege stehen direkt nebeneinander.
**Nachteil:** Weniger Listenhöhe je Bereich.

## C — Activity Ledger: die Nutzung als Chronik

Sechs Hero Cards über einer nach Aufträgen gruppierten Chronik. Zahlungen,
Fortsetzungen, Ergebnisse und Rückerstattungen bleiben am jeweiligen Vorgang.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | 30D: 09-25 12:00 to 10-25 12:00

+- REQUESTS ----------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- SCHEDULES ---------+ +- PAID --------------+ +- REFUNDS -----------+
|    OBSERVED / 30D   | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |    IMD / SETTLED    | |    IMD / RECEIVED   |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |          _          | |            _        | |          _          | |     _   _     _     | |             _       |
|       |_| |_|       | |         |_|         | |         | |_        | |         |_          | |    |_   _|   |_     | |        |   | |      |
|       |_|   |       | |         |_|         | |         | |_|       | |         |_|         | |    |_| |_  .  _|    | |        | . |_|      |
|                     | |                     | |                     | |                     | |                     | |                     |
|   paid + attempts   | |      6 deployed     | |     14 attested     | | 2 creates / 4 topups| |    gross payments   | |  linked to requests |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Window [30D]  Show [ALL ACTIVITY]  Type [ALL]  Chain [ALL]  Search [____________________]
Coverage: paid latest 100 | Intake history partial | payments and refunds: observed receipts | [details]

ACTIVITY / newest first                                                                  SELECTED / Atlas v2
                                                                                         -----------------------------------------------------
> 10-25 11:42  REQUEST / job.continue / Atlas v2                                         ACTION    job.continue
    payment settled 0.5 IMD -> job running                                               ROUTE     HTTP order
    <order> -> <project> -> <job>                                                        PAYMENT   settled
                                                                                         RESULT    working
  10-25 10:18  REQUEST / oracle.request / Check release
    payment settled -> panel attested                                                    RELATED EVIDENCE
    <order> -> <oracle> -> signed answer                                                 Order        <order> [open]
                                                                                         Payment      <payment> [open]
  10-25 09:45  REQUEST / launch.open / Harbor                                            Project      <project> [open]
    payment settled -> deployment confirmed                                              Job          <job> [open]
    <order> -> <launch> -> <creation-tx>
                                                                                         One request is one counted order.
  10-24 19:10  REQUEST / workflow.open / Atlas site                                      Payment and result are linked states.
    payment settled -> blocked: hosting                                                  They do not add three requests.

  10-24 18:30  FUNDING / schedule.topup / Daily check                                    SUMMARY / 30D
    3 runs added / schedule owner <other-wallet>                                         42 job / 12 workflow requests
                                                                                         78 settled / 6 unsettled attempts
  10-24 17:20  REFUND / prior request / +1.0 IMD received                                5 in flight / 4 follow-ups
  10-24 16:30  REQUEST / job.open / payment failed                                       2 schedules created / 4 topups
  10-24 15:10  REQUEST / schedule.create / Daily report active

8 activity groups shown | related events stay linked | requests and payments keep separate counting units
up/down select | left/right fold | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Der Ablauf von Beauftragung bis Ergebnis bleibt nachvollziehbar.
**Nachteil:** Weniger direkt vergleichbare Zeilen und mehr Scrollen.

## Empfehlung

**A als erste Ansicht; C als möglicher RECORD-Modus.** Die optische Nähe zur
Agent-Ansicht bleibt erhalten, ihre fachlichen Inhalte werden nicht übernommen.
Alle Zähler und Zeilen dienen ausschließlich der Wallet-Nutzung.

Erst nach Auswahl folgt ein isoliertes Textual-Mock mit DEMO-Daten. Diese
Entwürfe lesen keine Walletdaten und implementieren keine App-Funktion.
