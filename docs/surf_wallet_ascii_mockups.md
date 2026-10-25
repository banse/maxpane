# WALLET / SWARM — drei ASCII-Entwürfe für den Boardroom

Stand: 2026-10-25. **ASCII-Entwürfe; A/B für die isolierte DEMO ausgewählt.** Die Wallet als
Nutzerin des Schwarms: Aufträge, Zahlungen, Ergebnisse und die onchain Nutzung
der daraus entstandenen Sites, Contracts und Tokens. Agent-Details und Trading
bleiben ausgeschlossen. Die AGENT-Ansicht liefert ausschließlich die optische
Vorlage. MY CONTRACTS als separates Dashboard bleibt zurückgestellt.

**Nutzerpräzisierung: nur onchain Nutzung.** Keine Besucherzahlen, Pageviews,
Sessions oder HTTP-Verfügbarkeit als Nutzungssignal. Eine Site zeigt lediglich
die onchain Aktivität ihrer nachweislich verknüpften Contracts. Das beweist
keinen Besuch oder Aufruf über das Frontend.

Alle Zahlen, Namen, Zeiten und Beziehungen sind **DEMO**. Jede Skizze passt
rechnerisch in 149×45; keine gemessenen Produktions-Pins. Die ausführbare
Vorschau steht in `scripts/surf_wallet_demo.py`, ihre Spezifikation in
[surf_wallet_PRD.md](surf_wallet_PRD.md).
[Datengrundlagen und Signalregeln](surf_wallet_game_mechanics.md).

## Gemeinsame Darstellung

- Sechs gleich breite Rack Cards pro Reihe, neutrale Rahmen, dunkle Insets,
  große grüne Ziffern. A behält zwölf Karten wie die AGENT-Ansicht.
- `Orders [30D]` gilt für gefundene Requests und Zahlungen. `Assets [ALL KNOWN]`
  umfasst alle belegten Outputs eigener Aufträge, auch ältere. `Usage [24H]`
  misst deren Anwendungsaktionen aller beobachtbaren Akteure. Quellenabdeckung
  ist unabhängig für Aufträge, Artefakte und Nutzung sichtbar.
- SITES zählt Site-Projekte, CONTRACTS eindeutige bestätigte Chain-Adressen.
  TOKENS ist eine Teilmenge von CONTRACTS, kein zusätzlicher Deployment-Zähler.
  Versionen behalten ihre Beziehungen; gleiche Namen reichen nicht als Beleg.
- Erst belegte Anwendungsaktionen zählen als Nutzung. Pro Contract/Token braucht
  es eine versionsgebundene Regel mit passenden erfolgreichen Receipts/Events.
  Allgemeine Transfers, Swaps, Deployments, Approvals und Admin-Setup genügen nicht.
- Zahl und Signal zeigen denselben Umfang. Adressen sind keine Personen;
  kein zusammengesetzter Nutzerscore. Dieselben Events werden nicht durch eine
  zusätzliche Site- oder Token-Zeile erneut gezählt.
- Alle sichtbaren Werte laden ohne Detailbesuch; vorhandene Daten derselben
  Wallet bleiben erhalten. Unbekannte Daten sind keine Nullwerte. Große Ziffern
  bleiben vor dem ersten Read leer, Tabellen zeigen `--` mit sachlichem Kontext.
- Alle Tasten sind Vorschläge, keine implementierten Bindings. Adressen haben
  Copy-/Explorer-Aktionen, Sites einen belegten URL. Nur lesende Navigation.

## Signale

| Signal | Aussage |
|---|---|
| ACTIVE | Mindestens eine belegte Anwendungsaktion im Zeitfenster; bei partieller Abdeckung Zahl als Untergrenze |
| QUIET | Keine passende Aktion bei vollständig gelesenem Fenster und gültiger Regel |
| FIRST SEEN | Erste beobachtete Anwendung seit dokumentiertem Trackingbeginn; nicht erste Nutzung seit Deployment |
| NO DATA | Regel oder Historienabdeckung fehlt; keine Aussage über Nichtnutzung |
| NO ONCHAIN LINK | Site hat nach abgeschlossener Zuordnungsprüfung keinen belegten onchain Pfad; auch eine statische Site kann genutzt werden |

Bei Sites stehen `LINKED ACTIVE` und `LINKED QUIET` statt ACTIVE/QUIET, damit
Contract-Aktivität nicht mit Frontend-Nutzung verwechselt wird. Fehlt schon die
Zuordnungsprüfung, gilt NO DATA. Eigene und Testadressen sind nicht automatisch
organische Nutzer. Read-only-Aufrufe über `eth_call` sind keine beobachtbaren
onchain Transaktionen. Kein Trend ohne vergleichbare belegte Zeitfenster.

## Gemeinsamer DEMO-Datensatz

Orders: 2026-09-25 12:00 bis 2026-10-25 12:00 UTC. Usage: 2026-10-24 12:00
bis 2026-10-25 12:00 UTC, je Chain mit dokumentierten finalisierten Blockgrenzen.
Asset-Zahlen beziehen sich auf alle bislang gefundenen Outputs dieser Wallet.

| Wert | DEMO | Bedeutung |
|---|---:|---|
| REQUESTS | 84 | Beobachtete eindeutige Orders, inklusive Zahlungsversuche |
| JOBS | 42 | 32 neue Jobs und 10 Fortsetzungen |
| WORKFLOWS | 12 | Workflow-Requests; 10 verknüpfte Workflows geliefert |
| LAUNCHES | 8 | Launch-Requests; 6 verknüpfte Deployments bestätigt |
| ORACLES | 16 | Oracle-Requests; 14 verknüpfte Antworten attestiert |
| SCHEDULES | 6 | 2 Creates und 4 Topups; einer finanziert einen fremden Schedule |
| SITES | 10 | Bekannte Site-Projekte; 8 mit belegter onchain Verknüpfung |
| CONTRACTS | 18 | Bestätigte Chain-Adressen einschließlich der 4 Tokens |
| TOKENS | 4 | Token-Teilbestand, kein Wallet-Portfolio |
| IN FLIGHT | 5 | Requests mit laufender Arbeit: 2 Jobs, 1 Workflow, 1 Launch, 1 Oracle |
| PAID | 62.5 IMD | 78 bestätigte Zahlungen; 6 weitere Versuche unbestätigt |
| REFUNDS | 1.0 IMD | Separater belegter Rückfluss zu Aufträgen |
| ATTENTION | 4 | Offene Auftragsprobleme: 2 blockiert, 1 fehlgeschlagene Lieferung, 1 pausierter Schedule |

42 + 12 + 8 + 16 + 6 = 84. Requests, Ergebnisse und Nutzung bleiben verschiedene
Einheiten. Die 10 bekannten Sites sind nicht einfach die Zählung der 10 gelieferten
Workflows, sondern unabhängig nach Site-Projektidentität ermittelt. Contracts
können aus mehreren Auftragsarten stammen. Keine Summe `10 + 18 + 4` als Artefakttotal.

Im Demo gibt es geprüfte Nutzungsregeln für 6 der 18 Contracts, einschließlich
2 der 4 Tokens. Vier dieser sechs Fenster sind vollständig beobachtet. Die
sichtbaren Beispiele Atlas Registry, Harbor Vault und Harbor Credits gehören
dazu; Signal Access hat keine geprüfte Regel. Registry: 27 Registrierungen von
9 Akteuradressen; Vault: 0 Deposits; Credits: 4 Einlösungen von 3 Akteuradressen.
Credits wurde zuerst im seit 10-24 12:00 geführten Tracking beobachtet. Site-Zeilen
spiegeln dieselben Registry-/Vault-Belege, keine zusätzlichen Aktionen. Alle
Verknüpfungen, Regelabdeckungen und Metriken sind reine Beispieldaten.

## A — Wallet Rack mit Created-Übersicht

Zwölf Hero Cards über den erzeugten Artefakten und ihrem onchain Nutzungssignal.
Aufträge, Zahlungsübersicht und ausgewähltes Ergebnis bleiben darunter erreichbar.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | usage = onchain application actions; site traffic is not measured

+- REQUESTS ----------+ +- JOBS --------------+ +- WORKFLOWS ---------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- SCHEDULES ---------+
|    OBSERVED / 30D   | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      | |       REQUESTS      |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |            _        | |            _        | |          _          | |            _        | |          _          |
|       |_| |_|       | |       |_|  _|       | |         |  _|       | |         |_|         | |         | |_        | |         |_          |
|       |_|   |       | |         | |_        | |         | |_        | |         |_|         | |         | |_|       | |         |_|         |
|                     | |                     | |                     | |                     | |                     | |                     |
|   paid + attempts   | |32 open / 10 continue| |      10 shipped     | |      6 deployed     | |     14 attested     | | 2 creates / 4 topups|
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

+- SITES -------------+ +- CONTRACTS ---------+ +- TOKENS ------------+ +- IN FLIGHT ---------+ +- PAID --------------+ +- ATTENTION ---------+
|    KNOWN PROJECTS   | |  DEPLOYED ADDRESSES | |  DEPLOYED ADDRESSES | |   LINKED REQUESTS   | |      IMD / 30D      | | OPEN REQUEST ISSUES |
|                     | |                     | |                     | |                     | |                     | |                     |
|            _        | |            _        | |                     | |          _          | |     _   _     _     | |                     |
|         | | |       | |         | |_|       | |         |_|         | |         |_          | |    |_   _|   |_     | |         |_|         |
|         | |_|       | |         | |_|       | |           |         | |          _|         | |    |_| |_  .  _|    | |           |         |
|                     | |                     | |                     | |                     | |                     | |                     |
|   8 onchain links   | |    6 usage rules    | | subset of contracts | |   excludes blocked  | |   refunds 1.0 IMD   | | 2 blocked / 2 other |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Orders [30D]  Assets [ALL KNOWN]  Usage [24H / ALL ACTORS]  Chain [ALL]  Search [___________________]
Coverage: orders latest 100 | Intake partial | usage rules 6/18 contracts (incl. 2/4 tokens) | complete 24h windows 4/6

CREATED / outputs of this wallet's requests | tokens are included in CONTRACTS
TYPE       OUTPUT               CHAIN   ONCHAIN USE / 24H                           SIGNAL
---------- -------------------- ------- ------------------------------------------ ----------------
>SITE      Atlas portal         BASE    Registry: 27 registrations / 9 addrs       LINKED ACTIVE
 SITE      Harbor portal        ETH     Vault: 0 deposits                          LINKED QUIET
 CONTRACT  Atlas Registry       BASE    27 registrations / 9 addrs                 ACTIVE
 CONTRACT  Harbor Vault         ETH     0 deposits                                 QUIET
 TOKEN     Harbor Credits       BASE    4 redemptions / 3 addrs                    FIRST SEEN
 TOKEN     Signal Access        RH      --                                         NO DATA

RECORD: 10-25 11:42 job.continue / Atlas v2 / paid / working | 10:18 oracle.request / paid / attested
PAYMENTS / 30D: 78 settled / 6 unsettled attempts | 62.5 IMD paid | 1.0 IMD refunded
SELECTED: Atlas portal -> <site-url> [open] -> Base <contract> [copy] [explorer] | frontend origin not proven
Signals describe application events; linked site rows do not count those events again.
Tab created/requests | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Aufträge und daraus entstandene Ergebnisse stehen direkt im vertrauten Rack.
**Nachteil:** Der sichtbare Request-Verlauf ist kürzer; RECORD bleibt separat anwählbar.

## B — Created Explorer mit Nutzungsdetails

Sechs Hero Cards, links die erzeugten Sites, Contracts und Tokens. Rechts stehen
Zuordnung, onchain Anwendungsmetrik, Zeitfenster und Belege der Auswahl.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | usage = onchain application actions; site traffic is not measured

+- REQUESTS ----------+ +- SITES -------------+ +- CONTRACTS ---------+ +- TOKENS ------------+ +- PAID --------------+ +- ATTENTION ---------+
|    OBSERVED / 30D   | |    KNOWN PROJECTS   | |  DEPLOYED ADDRESSES | |  DEPLOYED ADDRESSES | |      IMD / 30D      | | OPEN REQUEST ISSUES |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |            _        | |            _        | |                     | |     _   _     _     | |                     |
|       |_| |_|       | |         | | |       | |         | |_|       | |         |_|         | |    |_   _|   |_     | |         |_|         |
|       |_|   |       | |         | |_|       | |         | |_|       | |           |         | |    |_| |_  .  _|    | |           |         |
|                     | |                     | |                     | |                     | |                     | |                     |
|   paid + attempts   | |   8 onchain links   | |    6 usage rules    | | subset of contracts | |   refunds 1.0 IMD   | | 2 blocked / 2 other |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Orders [30D]  Assets [ALL KNOWN]  Usage [24H / ALL ACTORS]  Chain [ALL]  Search [___________________]
Coverage: orders latest 100 | Intake partial | usage rules 6/18 contracts (incl. 2/4 tokens) | complete 24h windows 4/6

CREATED / known outputs of this wallet                                                  SELECTED / Atlas portal
TYPE       OUTPUT              CHAIN  SIGNAL                                            ------------------------------------------------------
> SITE     Atlas portal        BASE   LINKED ACTIVE                                     Site        <site-url> [open]
  SITE     Harbor portal       ETH    LINKED QUIET                                      Request     <order> [open]
  CONTRACT Atlas Registry      BASE   ACTIVE                                            Workflow    <workflow> [open]
  CONTRACT Harbor Vault        ETH    QUIET                                             Version     <site-version>
  TOKEN    Harbor Credits      BASE   FIRST SEEN
  TOKEN    Signal Access       RH     NO DATA                                           LINKED ONCHAIN USE / 24H
                                                                                        Base / Atlas Registry
REQUESTS / 30D                                                                          <contract> [copy] [explorer]
42 jobs / 12 workflows / 8 launches / 16 oracles / 6 schedule actions                   27 registrations / 9 actor addresses
Atlas v2       job.continue    paid      working                                        Last action 11:32 UTC
Atlas site     workflow.open   paid      blocked: hosting                               Window complete / <from-block>..<to-block>
Daily check    schedule.topup  paid      3 runs added                                   Rule        <version> [details]

PAYMENTS / 30D                                                                          LINKED ACTIVE
78 settled / 6 unsettled attempts                                                       Activity belongs to the linked contract.
Paid 62.5 IMD / Refunded 1.0 IMD                                                        Use through this frontend is not proven.

4 request follow-ups | usage gaps are not counted as request failures                   Site and contract share the same event evidence.

Tab section | up/down select | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Beste Prüfbarkeit der Nutzung eines einzelnen Ergebnisses.
**Nachteil:** Weniger Hero-Zähler für die einzelnen Auftragstypen.

## C — Requests und onchain Nutzung als Chronik

Die Timeline verbindet Beauftragung, Lieferung und später beobachtete Anwendung.
REQUEST und ONCHAIN USE bleiben ausdrücklich unterschiedliche Ereignistypen.

```text
WALLET / SWARM | <wallet> [copy] [explorer] | ETH / BASE / RH
DEMO DATA | 2026-10-25 12:00 UTC | usage = onchain application actions; site traffic is not measured

+- SITES -------------+ +- CONTRACTS ---------+ +- TOKENS ------------+ +- REQUESTS ----------+ +- IN FLIGHT ---------+ +- PAID --------------+
|    KNOWN PROJECTS   | |  DEPLOYED ADDRESSES | |  DEPLOYED ADDRESSES | |    OBSERVED / 30D   | |   LINKED REQUESTS   | |      IMD / 30D      |
|                     | |                     | |                     | |                     | |                     | |                     |
|            _        | |            _        | |                     | |        _            | |          _          | |     _   _     _     |
|         | | |       | |         | |_|       | |         |_|         | |       |_| |_|       | |         |_          | |    |_   _|   |_     |
|         | |_|       | |         | |_|       | |           |         | |       |_|   |       | |          _|         | |    |_| |_  .  _|    |
|                     | |                     | |                     | |                     | |                     | |                     |
|   8 onchain links   | |    6 usage rules    | | subset of contracts | |   paid + attempts   | |   excludes blocked  | |   refunds 1.0 IMD   |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Orders [30D]  Assets [ALL KNOWN]  Usage [24H / ALL ACTORS]  Chain [ALL]  Search [___________________]
Coverage: orders latest 100 | Intake partial | usage rules 6/18 contracts (incl. 2/4 tokens) | complete 24h windows 4/6

ACTIVITY [REQUESTS + ONCHAIN USE] / newest first                                        SELECTED / Harbor Credits
                                                                                        ------------------------------------------------------
  10-25 11:42  REQUEST / job.continue / Atlas v2                                        Type        TOKEN / Base
    payment settled 0.5 IMD -> job running                                              <contract> [copy] [explorer]
                                                                                        Created by  <launch> [open]
  10-25 11:32  ONCHAIN USE / Atlas Registry / registration                              My request  <order> [open]
    ACTIVE: 27 registrations / 9 addresses in 24h
    Linked site: Atlas portal; frontend origin not proven                               UTILITY / 24H
                                                                                        4 redemptions / 3 actor addresses
> 10-25 11:20  ONCHAIN USE / Harbor Credits / redemption                                Consumer    <consumer> [open]
    FIRST SEEN: first observed use in tracked history                                   Rule        <version> [details]
    4 redemptions / 3 addresses in 24h -> <tx> [open]                                   Latest      <tx> [open]

  10-25 10:18  REQUEST / oracle.request / Check release                                 FIRST SEEN
    paid -> answer attested                                                             Tracking since 10-24 12:00 UTC.
                                                                                        No claim about first-ever use.
  10-25 09:45  REQUEST / launch.open / Harbor
    paid -> deployed contracts -> created tokens                                        WINDOW
                                                                                        10-24 12:00 to 10-25 12:00 UTC
  10-24 19:10  REQUEST / workflow.open / Atlas site                                     Complete / <from-block>..<to-block>
    paid -> blocked: hosting
                                                                                        Swaps, distributions and generic transfers
Use can come from other addresses; it is not another wallet request.                    do not establish token utility use.

Usage evidence is deduplicated across site, contract and token views; no combined requests + usage total.
up/down select | left/right fold | Enter detail | / search | f filters | i wallet | x evidence | Esc boardroom
```

**Vorteil:** Zeigt, was nach der Lieferung passiert, ohne den Auftragskontext zu verlieren.
**Nachteil:** Unterschiedliche Metriken brauchen mehr Platz als eine reine Tabelle.

## Empfehlung

**A als Startansicht, B als Artefakt-Detailmodus.** Die Wallet-Nutzung und ihre
Ergebnisse bleiben gleichberechtigt sichtbar. C ist eine alternative Chronik.
Die Nutzungsregeln brauchen später eigene Quellen- und Abdeckungsprüfungen;
fehlende Regeln bleiben NO DATA. Kein automatischer Rückgriff auf Trading-Daten.

A als Startansicht und B als Artefakt-Detailmodus sind ausgewählt und als
isolierte Textual-DEMO umgesetzt; C bleibt ein nicht umgesetzter Entwurf.
Start: `.venv/bin/python scripts/surf_wallet_demo.py`. Enter öffnet das
ausgewählte Artefakt in B, Escape kehrt mit gleicher Auswahl zu A zurück.
Der Mock nutzt feste Scope-Beschriftungen statt nicht implementierter Filter
und inline DEMO-Belege statt externer Link-/Copy-Aktionen. Er liest keine
Walletdaten und ist noch nicht in den Boardroom eingebunden.
