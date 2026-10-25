# WALLET / SWARM — ausgewählte A/B-Ansichten und Chronik-Alternative

Stand: 2026-10-25. **A/B-Dichteüberarbeitung für die isolierte DEMO.** Die Wallet als
Nutzerin des Schwarms: Aufträge, Zahlungen, Ergebnisse und die onchain Nutzung
der daraus entstandenen Sites, Contracts und Tokens. Agent-Details und Trading
bleiben ausgeschlossen. Die AGENT-Ansicht liefert ausschließlich die optische
Vorlage. MY CONTRACTS als separates Dashboard bleibt zurückgestellt.

**Nutzerpräzisierung: nur onchain Nutzung.** Keine Besucherzahlen, Pageviews,
Sessions oder HTTP-Verfügbarkeit als Nutzungssignal. Eine Site zeigt lediglich
die onchain Aktivität ihrer nachweislich verknüpften Contracts. Das beweist
keinen Besuch oder Aufruf über das Frontend.

Alle Zahlen, Namen, Zeiten und Beziehungen sind **DEMO**. Die Skizzen zeigen
die Anordnung für das Ziel 149×45; sie sind keine gemessenen Produktions-Pins. Die ausführbare
Vorschau steht in `scripts/surf_wallet_demo.py`, ihre Spezifikation in
[surf_wallet_PRD.md](surf_wallet_PRD.md).
[Datengrundlagen und Signalregeln](surf_wallet_game_mechanics.md).

## Gemeinsame Darstellung

- Sechs gleich breite Rack Cards pro Reihe, neutrale Rahmen, dunkle Insets,
  große grüne Ziffern. A und B haben jeweils nur eine Reihe mit sechs Karten.
  Die frühere zweite A-Reihe entfällt; ihre Werte bleiben in Fußzeilen und Widgets.
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
- A/B zeigen nur vorhandene Navigation: Pfeile wählen, Enter öffnet B, Escape
  kehrt zu A zurück, q beendet die DEMO. Externe Belege sind Platzhalter ohne
  Copy-/Explorer-Aktionen. Die historische C-Alternative zeigt spätere Vorschläge.

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

## A — eine Kartenreihe, darunter Nutzungs- und Statuswidgets

Die Nutzerkorrektur ersetzt die zweite Hero-Reihe durch unterschiedlich lesbare
Widgets: Verlauf, Verteilungen, Zahlungsübersicht und einen Beziehungspfad.
Die sechs großen Zähler bleiben Orientierung; ihre Fußzeilen übernehmen passende
Nebenzahlen. Die konkrete Fußzeilenverteilung wird am gerenderten Textual-Layout
geprüft. Globale Werte tragen ihren eigenen Scope.

```text
WALLET / SWARM | <demo-wallet> | DEMO DATA | 2026-10-25 12:00 UTC

+- REQUESTS ----------+ +- JOBS --------------+ +- WORKFLOWS ---------+ +- LAUNCHES ----------+ +- ORACLES -----------+ +- SCHEDULES ---------+
|    ORDERS / 30D     | |    REQUESTS / 30D   | |    REQUESTS / 30D   | |    REQUESTS / 30D   | |    REQUESTS / 30D   | |    REQUESTS / 30D   |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |            _        | |            _        | |          _          | |            _        | |          _          |
|       |_| |_|       | |       |_|  _|       | |         |  _|       | |         |_|         | |         | |_        | |         |_          |
|       |_|   |       | |         | |_        | |         | |_        | |         |_|         | |         | |_|       | |         |_|         |
|   paid + attempts   | |  32 new / 10 cont   | |     10 shipped      | |      6 deployed     | |     14 attested     | |    not run count    |
|   paid 62.5 IMD     | | 5 in flight / all   | | 10 sites / ALL KNOWN| |18 ctr incl. 4 tokens| |4 follow-ups / all   | | 2 new / 4 topups     |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+
Orders 30D | Assets ALL KNOWN | Usage 24H / ALL ACTORS | ETH / BASE / RH
Coverage: latest 100 orders / Intake partial | usage rules 6/18 contracts (2/4 tokens) | complete windows 4/6

REQUEST ACTIVITY / 30D               REQUEST STATUS                      ONCHAIN USE / 24H                   PAYMENTS / 30D
                                    exclusive request buckets           18 contracts incl. 4 tokens
     |     |     ||                  Labeled bars from all 84 orders      ACTIVE + FIRST SEEN   #### 4        Paid          62.5 IMD
   | |   | |  || ||                  Current state / count / proportion  QUIET                 #    1        Refunded       1.0 IMD
 __|_|___|_|__||_||_____              Running is separate from blocked    NO DATA               ############# 13
 fixed daily order counts            Four follow-up flags shown below    Rules                  6/18          Settled        78 / 84
 start ---------------- end          No order counted twice              Complete rule windows  4/6           [##################..]
 84 observed / no live history        No inferred success rate            Linked sites add no extra usage      6 unsettled attempts

CREATED / 28 rows: 10 sites + 18 contracts, including 4 tokens                                        SELECTED RELATIONSHIP
TYPE      OUTPUT              CHAIN  ONCHAIN USE / 24H       SIGNAL                                  Atlas portal
>SITE     Atlas portal        BASE   27 registrations        LINKED ACTIVE                            order -> site -> Atlas Registry
 SITE     Harbor portal       ETH    0 deposits              LINKED QUIET                             27 registrations / 9 addresses
 CONTRACT Atlas Registry      BASE   27 registrations        ACTIVE                                   Shared contract evidence;
 CONTRACT Harbor Vault        ETH    0 deposits              QUIET                                    frontend origin not proven.
 TOKEN    Harbor Credits      BASE   4 redemptions           FIRST SEEN
 TOKEN    Signal Access       RH     --                      NO DATA                                  OPEN FOLLOW-UPS / 4
 SITE     Cedar handbook      --     --                      NO ONCHAIN LINK                          ! blocked request
 ... internal scrolling: all 28 artifacts                                                             ! blocked request
                                                                                                      ! failed delivery
                                                                                                      ! paused schedule
RECORD / 84 observed requests, newest first
WHEN UTC      ACTION             OBJECT          PAYMENT       RESULT
10-25 11:42   job.continue       Atlas v2        settled       working
10-25 10:18   oracle.request     Check release   settled       attested
10-25 09:45   launch.open        Harbor          settled       deployed
arrows select | Enter artifact detail | Tab records | Esc/q quit | DEMO DATA / no external actions
```

Die Statusbalken werden aus der vorhandenen Fixture berechnet; dieser Entwurf
legt keine neue Bedeutung für „erfolgreich“ fest. Onchain-Balken zählen
Contract-Identitäten, keine Summe unterschiedlicher Events oder Akteuradressen.
Im Beispiel sind vier Contracts positiv, einer nach vollständig gelesenem
Fenster ruhig und dreizehn ohne ausreichende Nutzungsdaten. FIRST SEEN gehört
zum positiven Teil, bleibt am einzelnen Artefakt aber eigenständig sichtbar.

**Vorteil:** Verlauf, laufende Arbeit und Datenabdeckung sind auf einen Blick
lesbar, während Liste und Record erreichbar bleiben.
**Abwägung:** Die kompakte Tabelle zeigt die Aktionseinheit; Akteuradressen und
vollständige Belege stehen am ausgewählten Artefakt beziehungsweise in B.

## B — Created Explorer mit Nutzungsdetails

Eine Reihe mit sechs Karten bleibt bestehen. Links die Liste, rechts die
vollständigen Artefaktdetails; unter der Liste ersetzt das Zahlungswidget den
bisherigen reinen Textblock. Enter/Escape behalten die gemeinsame Artefakt-ID.

```text
WALLET / SWARM | <demo-wallet> | DEMO DATA | 2026-10-25 12:00 UTC

+-- REQUESTS ---------+ +-- SITES ------------+ +-- CONTRACTS --------+ +-- TOKENS -----------+ +-- PAID -------------+ +-- ATTENTION --------+
|    ORDERS / 30D     | |    KNOWN PROJECTS   | |      DEPLOYED       | |      DEPLOYED       | |      IMD / 30D      | |   OPEN FOLLOW-UPS   |
|                     | |                     | |                     | |                     | |                     | |                     |
|        _            | |            _        | |            _        | |                     | |     _   _     _     | |                     |
|       |_| |_|       | |         | | |       | |         | |_|       | |         |_|         | |    |_   _|   |_     | |         |_|         |
|       |_|   |       | |         | |_|       | |         | |_|       | |           |         | |    |_| |_  .  _|    | |           |         |
|   paid + attempts   | |      8 linked       | |    incl. 4 tokens   | |    in contracts     | |   refunds 1.0 IMD   | |    2 blocked + 2    |
|    30D / observed   | |      ALL KNOWN      | |     6 usage rules   | |      ALL KNOWN      | |     78 settled      | |     follow-ups      |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+
Orders 30D | Assets ALL KNOWN | Usage 24H / ALL ACTORS | ETH / BASE / RH
Coverage: latest 100 orders / Intake partial | usage rules 6/18 (2/4 tokens) | complete windows 4/6

CREATED / all 28 artifacts                                                            SELECTED ARTIFACT
TYPE       OUTPUT               CHAIN   SIGNAL                                        Atlas portal / SITE / BASE
>SITE      Atlas portal         BASE    LINKED ACTIVE                                 Order      <demo-order>
 SITE      Harbor portal        ETH     LINKED QUIET                                  Project    <demo-project>
 CONTRACT  Atlas Registry       BASE    ACTIVE                                        Version    <demo-version>
 CONTRACT  Harbor Vault         ETH     QUIET                                         Linked     Atlas Registry
 TOKEN     Harbor Credits       BASE    FIRST SEEN
 TOKEN     Signal Access        RH      NO DATA                                       ONCHAIN USE / 24H
 SITE      Cedar handbook       --      NO ONCHAIN LINK                               27 registrations / 9 addresses
 ... internal scrolling                                                               Rule       <demo-rule>
                                                                                       Window     complete / <demo-blocks>
PAYMENTS / 30D                                                                         Latest     <demo-observation>
Paid       62.5 IMD                                                                    Evidence   <demo-receipt>
Refunded    1.0 IMD
78 settled / 6 unsettled attempts                                                      Linked contract evidence only.
[##################..]                                                                Frontend origin not proven.

arrows select | Tab pane | Esc overview | q quit | DEMO DATA / no external actions
```

**Vorteil:** Einzelne Artefakte bleiben nachvollziehbar; die Zahlungsdarstellung
verwendet denselben Widget-Baustein wie A.
**Abwägung:** Die Übersicht der Auftragstypen steht in A; B priorisiert das
gewählte Artefakt und seine Belege.

## C — historische, nicht ausgewählte Chronik-Alternative

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

A als Startansicht und B als Artefakt-Detailmodus bleiben ausgewählt. Die
aktuelle Überarbeitung verwendet eine Kartenreihe und die oben gezeigten
Widgets; der frühere Zwölf-Karten-Stand ist abgelöst. C bleibt ein nicht
umgesetzter historischer Entwurf.
Start: `.venv/bin/python scripts/surf_wallet_demo.py`. Enter öffnet das
ausgewählte Artefakt in B, Escape kehrt mit gleicher Auswahl zu A zurück.
Der Mock nutzt feste Scope-Beschriftungen statt nicht implementierter Filter
und inline DEMO-Belege statt externer Link-/Copy-Aktionen. Er liest keine
Walletdaten und ist noch nicht in den Boardroom eingebunden.
