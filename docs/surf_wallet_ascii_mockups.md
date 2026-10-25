# WALLET / SWARM — drei ASCII-Entwürfe für den Boardroom

Stand: 2026-10-25. **Designvorschläge, noch keine Implementierung.** MY CONTRACTS
bleibt zurückgestellt. Diese Ansicht betrachtet genau eine Wallet über die
relevanten Chains und zeigt ihre Interaktionen mit dem Swarm, ohne Trading.
Einstiegsvorschlag: eine WALLET-Karte im Boardroom oder der OWNER-Link eines
Agents. Das sind noch keine registrierten Navigationselemente.

Alle Namen, Zahlen, Zeiten, Beziehungen und Zustände sind **DEMO**. Adressen
und IDs sind Platzhalter. Jeder ASCII-Rahmen bleibt innerhalb von 149×45 Zeichen;
das ist kein gemessener Textual-Layout-Pin. Es gibt keine ausführbare Vorschau.
Die [Datengrundlagen](surf_wallet_game_mechanics.md) beschreiben Quellen,
Zuordnung und Grenzen für eine spätere Umsetzung.

## Gemeinsame Gestaltung

- Sechs gleich breite Rack Cards pro Reihe: graues Gehäuse, schwarzes Inset,
  große grüne Ziffern, neutrale Beschriftung. Entwurf A nutzt zwei Reihen wie
  die bestehende AGENT-Ansicht. Monospace bleibt die einzige Schrift.
- Kartenwerte sind zentriert, Tabellen und Details linksbündig. Amber kennzeichnet
  fachlichen Handlungsbedarf; Text und `>` vermitteln Zustand/Fokus zusätzlich
  zur Farbe. Kontraste sind später zu messen, Ziel mindestens 4.5:1 für normalen
  Text. ASCII allein belegt keine Accessibility-Konformität.
- Alles ist per Tastatur erreichbar. Eine Auswahl führt zur passenden Job-,
  Workflow-, Launch-, Oracle- oder Agent-Detailansicht. Escape schließt zuerst
  Details, dann die Wallet-Ansicht. Alle Tasten unten sind Vorschläge.
- Der Zeitraum gilt für Requests, Zahlungen und attribuierte Arbeit. SEATS ist
  ausdrücklich der aktuelle Bestand. Rollen-, Typ- und Suchfilter begrenzen
  RECORD; sie definieren nicht stillschweigend die Hero-Zahlen um.
- Vorhandene Daten derselben Wallet erscheinen sofort. Die Übersicht lädt ihre
  eigenen Quellen ohne Detailbesuch. Walletwechsel und verspätete Antworten
  müssen nach Identität getrennt werden. Ungelesene große Werte bleiben leer;
  der bestehende gemeinsame Ladefooter genügt. Fachliche Zustände und partielle
  Abdeckung bleiben sichtbar, technische Quellenfehler intern.
- Trading, Preise, P/L, LP-Positions- und Renditeanalysen sind ausgeschlossen.
  Belegbare nicht-trading Protokollaktionen wie Pairing, Claim, Stake oder Unstake
  gehören zur Chronik. Andere Aktionstypen benötigen eine verifizierte Quelle.

## Gemeinsamer DEMO-Datensatz

Zeitraum: 2026-09-25 12:00 bis 2026-10-25 12:00 UTC, im Mock `30D`.
Die Zahlen beschreiben bekannte Beobachtungen, keine vollständige Historie.

| Karte | DEMO | Zähleinheit |
|---|---:|---|
| REQUESTS | 84 | Eindeutige beobachtete Requests einschließlich Zahlungsversuchen |
| JOBS | 42 | 32 `job.open` + 10 `job.continue` |
| WORKFLOWS | 12 | `workflow.open`-Requests; 10 verknüpfte Workflows geliefert |
| LAUNCHES | 8 | `launch.open`-Requests; 6 verknüpfte Deployments bestätigt |
| ORACLES | 16 | `oracle.request`-Requests; 14 verknüpfte Antworten attestiert |
| SCHEDULES | 6 | 2 Create- + 4 Topup-Requests, keine Anzahl von Runs |
| SEATS | 3 | Aktuell gehalten, 2 online; kein historischer Nenner |
| ACCEPTED | 960 | Angenommene von 1.000 bekannten Submissions im belegten Wallet-Zuordnungszeitraum, 96.0% |
| EFFORT | 320 h | Belegter zugeordneter Aufwand im Fenster, 1.8M Output-Tokens |
| PAID | 62.5 IMD | 78 bestätigte Zahlungen; 6 unbestätigte Versuche tragen nichts bei |
| RECEIVED | 8.4 IMD | Tatsächliche Reward-Zuflüsse im Fenster, keine Allocations oder Refunds |
| ATTENTION | 4 | Eindeutige offene Follow-ups: 2 blockierte Arbeiten, 1 fehlgeschlagene Lieferung, 1 pausierte Schedule |
| IN FLIGHT | 5 | 2 laufende Jobs, 1 laufender Workflow, 1 Launch in Review, 1 wartende Oracle-Anfrage; blockierte separat |

42 + 12 + 8 + 16 + 6 = 84. Interne Workflow-Jobs oder Deployments erhöhen die
Wallet-Request-Zahl nicht. HTTP- und onchain Belege desselben Vorgangs werden
verknüpft und einmal gezählt. Request, Zahlung, Outcome und Agent-Submission
sind verschiedene Einheiten, deshalb kein gemeinsamer „alle Aktionen“-Zähler.

Die Kosten stammen aus fiktiven Receipts, nicht aus einem angenommenen Tarif.
Refunds sind separat 1.0 IMD. Andere Assets bleiben getrennte Summen, ohne
Dollar-Gesamtwert. RECEIVED ist ein Zufluss an die Wallet, keine Addition der
auf Seats verteilten OWNER-SHARE-Anzeigen.

Von zwei erstellten eigenen Schedules ist eine aktiv und eine pausiert. Einer
der vier Topups finanziert eine fremde Schedule: FUNDER bedeutet nicht Owner.
Ein erfolgreicher Topup belegt keine erfolgreichen späteren Runs. Verknüpfte
Läufe behalten eigene Zustände und erhöhen nicht die Request-Zahl des Topups.

Agent-Arbeit ist zeitlich zur Wallet zugeordnet und berücksichtigt alle
relevanten Bindings. Aktueller Seat-Besitz belegt keine Lifetime-Historie. Im
Demo liefern die drei Seats 600/625, 300/315 und 60/60 angenommene/bekannte
Versuche sowie 200/100/20 Stunden. Ehemals gehaltene Seats bleiben für historische
Arbeit relevant, auch wenn sie nicht zum aktuellen SEATS-Zähler gehören.

## A — Wallet Rack: die AGENT-Ansicht auf Wallet-Ebene

Zwei Reihen mit sechs Hero Cards, darunter ein gemeinsamer RECORD. Oben stehen
die Wallet-Aufträge, darunter Agent-Engagement, Geldflüsse und offene Punkte.
Das ist die engste visuelle Fortsetzung der bestehenden Agent-Ansicht.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | 30D: 09-25 12:00 to 10-25 12:00

+- REQUESTS ----------+ +- JOBS --------------+ +- WORKFLOWS ---------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- SCHEDULES ---------+
|       OBSERVED      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |            _        | |            _        | |          _          | |            _        | |          _          |
|       |_| |_|       | |       |_|  _|       | |         |  _|       | |         |_|         | |         | |_        | |         |_          |
|       |_|   |       | |         | |_        | |         | |_        | |         |_|         | |         | |_|       | |         |_|         |
|                     | |                     | |                     | |                     | |                     | |                     |
|paid + attempts / 30d| |32 open / 10 continue| |      10 shipped     | |      6 deployed     | |     14 attested     | | 2 creates / 4 topups|
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

+- SEATS -------------+ +- ACCEPTED ----------+ +- EFFORT ------------+ +- PAID --------------+ +- RECEIVED ----------+ +- ATTENTION ---------+
|       HELD NOW      | |      KNOWN WORK     | |     HOURS / 30D     | |    IMD / SETTLED    | |    IMD / REWARDS    | |      FOLLOW-UPS     |
|                     | |                     | |                     | |                     | |                     | |                     |
|          _          | |      _   _   _      | |      _   _   _      | |     _   _     _     | |       _             | |                     |
|          _|         | |     |_| |_  | |     | |      _|  _| | |     | |    |_   _|   |_     | |      |_|   |_|      | |         |_|         |
|          _|         | |      _| |_| |_|     | |      _| |_  |_|     | |    |_| |_  .  _|    | |      |_| .   |      | |           |         |
|                     | |                     | |                     | |                     | |                     | |                     |
| 2 online / 1 offline| |   of 1000 / 96.0%   | |  1.8M output tokens | |   refunds 1.0 IMD   | |  verified receipts  | | 2 blocked / 2 other |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

RECORD [ALL]  Role [ALL]  Type [ALL]  Chain [ALL]  Search [___________________]  Cards: known 30D + current seats
Coverage: paid latest 100 | Intake history partial | agent history partial | [details]

WHEN         ROLE       ACTION             OBJECT           ORDER / WORK       RESULT / RECEIPT
------------ ---------- ------------------ ---------------- ------------------ ---------------------------------------------------------------
>10-25 11:42 PAYER      job.continue       Atlas v2         paid               working / <job>
 10-25 10:18 PAYER      oracle.request     Check release    paid               attested / <oracle>
 10-25 09:45 PAYER      launch.open        Harbor           paid               deployed / <launch>
 10-24 19:10 PAYER      workflow.open      Atlas site       paid               blocked / hosting
 10-24 18:30 FUNDER     schedule.topup     Daily check      paid               3 runs added / owned by <other-wallet>
 10-24 17:20 WALLET     claim              Agent rewards    confirmed          +1.2 IMD received / <tx>
 10-24 16:30 WALLET     stake              Protocol         confirmed          <amount> <asset> / <tx>
 10-24 15:10 AGENT      review             Seat <seat>      accepted           attributed at work time / <job>
Newest 8 records shown | requests, outcomes, protocol actions and agent work keep separate counting units

SELECTED: Atlas v2 | paid 0.5 IMD | work running | request <order> -> project <project> -> job <job>
Enter details | / search | f filters | a agents | i wallet | x open evidence | r refresh | Esc boardroom
```

**Vorteil:** Alle wesentlichen Zahlen stehen sofort im vertrauten Rack; die
Chronik verbindet die Aktivitäten. **Nachteil:** Ausführliche Details benötigen
einen eigenen Bereich, der auf Auswahl geöffnet wird.

## B — Auftraggeber und Betreiber: zwei Rollen, eine Wallet

Sechs Hero Cards über getrennten Bereichen für Aufträge, Agent-Arbeit und
Protokollaktionen. Rechts bleibt die ausgewählte Aktivität mit ihren Belegen
sichtbar. Diese Trennung erklärt die beiden Wallet-Rollen am deutlichsten.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | 30D: 09-25 12:00 to 10-25 12:00

+- REQUESTS ----------+ +- IN FLIGHT ---------+ +- SEATS -------------+ +- ACCEPTED ----------+ +- PAID --------------+ +- RECEIVED ----------+
|       OBSERVED      | |     LINKED WORK     | |       HELD NOW      | |      KNOWN WORK     | |    IMD / SETTLED    | |    IMD / REWARDS    |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |          _          | |          _          | |      _   _   _      | |     _   _     _     | |       _             |
|       |_| |_|       | |         |_          | |          _|         | |     |_| |_  | |     | |    |_   _|   |_     | |      |_|   |_|      |
|       |_|   |       | |          _|         | |          _|         | |      _| |_| |_|     | |    |_| |_  .  _|    | |      |_| .   |      |
|                     | |                     | |                     | |                     | |                     | |                     |
|paid + attempts / 30d| |   excludes blocked  | | 2 online / 1 offline| |   of 1000 / 96.0%   | |   refunds 1.0 IMD   | |  verified receipts  |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Window [30D]  Role [ALL]  Type [ALL]  Chain [ALL]  Search [______________________]
Coverage: paid latest 100 | Intake history partial | agent history partial | [details]

COMMISSIONED / 84 observed requests                                                        SELECTED / Atlas v2
JOBS 42 | WORKFLOWS 12 | LAUNCHES 8 | ORACLES 16 | SCHEDULE ACTIONS 6                       -----------------------------------------------
OBJECT            ACTION             ORDER        RESULT                                  My role      payer
> Atlas v2        job.continue       paid         working                                 Paid          0.5 IMD
  Check release   oracle.request     paid         attested                                Order         <order> [open]
  Harbor          launch.open        paid         deployed                                Project       <project> [open]
  Atlas site      workflow.open      paid         blocked                                 Job           <job> [open]
  Daily check     schedule.topup     paid         3 runs added                            Continued     previous version

MY AGENTS / 3 seats held now | historical work: wallet-attributed only                      RESULT
SEAT       NOW       ACCEPTED  KNOWN ATTEMPTS  EFFORT                                      Work running
  <seat-A> online         600             625   200h                                       Artifacts appear when delivered.
  <seat-B> online         300             315   100h
  <seat-C> offline         60              60    20h                                       COSTS / 30D
  known work total       960            1000   320h                                       Gross paid   62.5 IMD
                                                                                          Refunded      1.0 IMD
PROTOCOL / verified wallet actions                                                        Received      8.4 IMD rewards
10-24 17:20  claim   +1.2 IMD rewards     <tx> [open]                                       Other assets remain separate.
10-24 16:30  stake   <amount> <asset>     <tx> [open]
                                                                                          ATTENTION / 4 follow-ups
2 schedules created / 1 active / 1 paused | topups may fund another wallet                  2 blocked / 1 failed / 1 paused

Tab section | up/down select | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Beauftragte und geleistete Arbeit lassen sich kaum verwechseln;
Details sind ständig sichtbar. **Nachteil:** Die drei Listen teilen sich die
Höhe und brauchen bei größerem Bestand mehr Navigation.

## C — Activity Ledger: eine zusammenhängende Chronik

Sechs Hero Cards über einer gruppierten Timeline. Jeder Request zeigt seine
Zahlung, seine verknüpfte Arbeit und das Ergebnis. Eigenständige Wallet- und
Agent-Ereignisse behalten ihre Rolle und werden zeitlich eingeordnet.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | 30D: 09-25 12:00 to 10-25 12:00

+- REQUESTS ----------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- SCHEDULES ---------+ +- PAID --------------+ +- RECEIVED ----------+
|       OBSERVED      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |    IMD / SETTLED    | |    IMD / REWARDS    |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |          _          | |            _        | |          _          | |     _   _     _     | |       _             |
|       |_| |_|       | |         |_|         | |         | |_        | |         |_          | |    |_   _|   |_     | |      |_|   |_|      |
|       |_|   |       | |         |_|         | |         | |_|       | |         |_|         | |    |_| |_  .  _|    | |      |_| .   |      |
|                     | |                     | |                     | |                     | |                     | |                     |
|paid + attempts / 30d| |      6 deployed     | |     14 attested     | | 2 creates / 4 topups| |   refunds 1.0 IMD   | |  verified receipts  |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Window [30D]  Show [ALL ACTIVITY]  Role [ALL]  Chain [ALL]  Search [____________________]
Coverage: paid latest 100 | Intake history partial | agent history partial | [details]

ACTIVITY / newest first                                                                   SELECTED / Atlas v2
                                                                                          -----------------------------------------------
> 10-25 11:42  MY REQUEST    job.continue / Atlas v2                                       ROLE      payer
    payment settled 0.5 IMD -> job running                                                 ROUTE     HTTP order
    <order> -> <project> -> <job>                                                          PAYMENT   settled
                                                                                          RESULT    working
  10-25 10:18  MY REQUEST    oracle.request / Check release
    payment settled -> panel attested                                                     RELATED EVIDENCE
    <order> -> <oracle> -> signed answer                                                   Order        <order> [open]
                                                                                          Payment      <payment> [open]
  10-25 09:45  MY REQUEST    launch.open / Harbor                                          Project      <project> [open]
    payment settled -> deployment confirmed                                               Job          <job> [open]
    <order> -> <launch> -> <creation-tx>
                                                                                          One request is one counted order.
  10-24 19:10  MY REQUEST    workflow.open / Atlas site                                    Payment and work are linked states.
    payment settled -> blocked: hosting                                                   They do not add three requests.

  10-24 18:30  MY FUNDING    schedule.topup / Daily check                                  SUMMARY / 30D
    3 runs added / schedule owner <other-wallet>                                           42 job / 12 workflow requests
                                                                                          3 current seats / 960 known accepted
  10-24 17:20  MY WALLET     claim / +1.2 IMD reward receipt                               320h / 1.8M output tokens
  10-24 16:30  MY WALLET     stake / <amount> <asset>                                      4 follow-ups [open]
  10-24 15:10  MY AGENT      review accepted / Seat <seat> / <job>

8 activity groups shown | linked events collapse together | no combined request + work + payment total
up/down select | left/right fold | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Der Ablauf vom Auftrag bis zum Ergebnis wird direkt lesbar;
Fortsetzungen und wiederkehrende Aufträge sind gut nachvollziehbar.
**Nachteil:** Weniger direkt vergleichbare Tabellenzeilen, mehr Scrollen.

## Empfehlung und nächste Designstufe

**A als erste Ansicht.** Sie erfüllt „wie Agent, aber Wallet“ am unmittelbarsten.
Die Rollen aus B bleiben durch die RECORD-Spalte sichtbar; die gruppierte
Chronik aus C eignet sich als späterer Record-Modus.

Die Quellenbegrenzungen aus den [Datengrundlagen](surf_wallet_game_mechanics.md)
bleiben in Coverage sichtbar: unter anderem die neuesten maximal 100 Paid-
Orders, partielle Intake-Discovery und unvollständige historische Agent-Zuordnung.
Bekannte Daten dürfen deshalb nicht als vollständige Lifetime-Werte erscheinen.

Nach Auswahl folgt ein isoliertes Textual-Mock bei 149×45 mit DEMO-Marker.
API-Anbindung, vollständige Discovery und gemessene Layout-Pins sind spätere
Arbeit. Diese Entwürfe lesen keine Walletdaten und führen keine Aktionen aus.
