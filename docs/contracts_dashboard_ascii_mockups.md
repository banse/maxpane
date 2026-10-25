# MY CONTRACTS — drei ASCII-Designvorschläge

Stand: 2026-10-25. Designphase für ein neues Dashboard; keine Implementierung,
keine Live-Abfrage und keine Freigabe einer Datenquelle. Die Skizzen sind je
143 Zeichen breit und höchstens 45 Zeilen hoch. Das passt rechnerisch in den
149×45-Entwurfsrahmen, ist aber noch kein gemessener Textual-Layout-Pin.

**Alle Namen, Zahlen, Zeiten und Verknüpfungen sind DEMO.** Der gemeinsame
Beispielbestand umfasst 42 bestätigte Contract-Identitäten über acht Projekte:
12 SELF und 30 SWARM; 18 auf Ethereum, 17 auf Base und sieben auf RH. Drei
weitere Kandidaten stehen außerhalb dieser Zähler. RH steht hier für die im
Repository geführte Robinhood-Chain. Die Beispielnamen sind keine Behauptung
über reale Nutzerprojekte.

## Gemeinsame Gestaltung und Bedeutung

- Bestehende MaxPane-Rack-Sprache: sechs gleich breite Hero Cards mit großem
  Zahlenfeld, dunklem Inset und ruhigem Rahmen. Werte nehmen die Matrix-Farbe
  an; Titel und erklärender Text bleiben neutral. Die ASCII-Ziffern deuten
  die vorhandenen großen Terminalziffern an.
- Tabellen und Details nutzen die vorhandene Monospace-Schrift. Eine Leerzeile
  trennt Titel und Inhalt. Die gewählte Zeile trägt zusätzlich `>`; Herkunft,
  Chain und Status sind immer ausgeschrieben und nie nur durch Farbe erkennbar.
- Die Karten zählen den bestätigten Profilbestand. Filter begrenzen die Liste;
  ihre Kopfzeile zeigt anschließend etwa `12 matches / 42 confirmed`. Die
  Zähler wechseln damit nicht unbemerkt zwischen Gesamtbestand und Auswahl.
- SELF bedeutet belegte Erstellung durch eine konfigurierte eigene Wallet,
  direkt oder über eine belegte Factory-Transaktion. SWARM bedeutet ein vom
  Nutzer beauftragter und bis zur Contract-Erstellung belegter Launch.
  Mitarbeit an fremden Jobs zählt nicht. Zahler, Auftraggeber und heutiger
  Contract-Owner werden nicht gleichgesetzt. Bei überlappender Provenienz zählt
  dieselbe `(chain, address)`-Identität nur einmal; ein eigener Swarm-Auftrag
  bestimmt die Kategorie SWARM, zusätzliche Wallet-Belege bleiben im Detail.
- Deployment-Herkunft und heutige Kontrolle sind getrennte Fakten. `code
  present` sagt weder `owner` noch `safe`. Owner/Admin wird nur gezeigt, wenn
  separat gelesen; ein Proxy und seine Implementation bleiben zwei Contracts.
- Importierte Adressen ohne vollständigen Beleg bleiben in REVIEW. Die
  Vollständigkeit der Discovery wird separat ausgewiesen. Coverage bezieht
  sich auf die konfigurierten Wallets, Quellen und den ausgewiesenen Zeitraum;
  öffentliche Auftragsseiten können begrenzt sein. Historische Imports bleiben
  ein vorgesehener Ergänzungsweg. 42 bedeutet den
  bestätigten gefundenen Bestand, nicht automatisch „alle jemals deployten“.
- `<contract>`, `<factory>` und ähnliche Platzhalter sind absichtlich keine
  erfundenen Adressen. In der Umsetzung werden Adressen über die gemeinsamen
  Copy-/Explorer-Komponenten verlinkt. Ausgeklappte Details zeigen sie vollständig.
- Bedienung vollständig per Tastatur; Fokus und Auswahl zusätzlich geometrisch
  markiert. Textkontraste sind in der späteren Theme-Umsetzung zu messen
  (Ziel mindestens 4.5:1 für normalen Text). Hier wird keine fertige
  Accessibility-Konformität behauptet.
- Die unten genannten Tasten sind Designvorschläge, keine bereits registrierten
  Bindings. Escape schließt zuerst Suche/Filter/Details, dann das Dashboard.

## A — Registry: alles finden, eine Adresse verstehen

Die Contract-Liste bekommt etwa zwei Drittel der Breite; die rechte Spalte
zeigt dauerhaft den ausgewählten Contract samt Herkunft und Beziehungen.
Die zuletzt bestätigten Deployments und die getrennte Kandidatenliste bleiben
im unteren Bereich der Listenhälfte erreichbar.

```text
MY CONTRACTS / REGISTRY | profile: my wallets + my Swarm requests
DEMO DATA | all names, counts and records are illustrative

+- CONTRACTS ---------+ +- SELF --------------+ +- SWARM -------------+ +- ETHEREUM ----------+ +- BASE --------------+ +- RH ----------------+
|      CONFIRMED      | |      CONTRACTS      | |      CONTRACTS      | |       MAINNET       | |       MAINNET       | |       MAINNET       |
|                     | |                     | |                     | |                     | |                     | |                     |
|            _        | |            _        | |        _   _        | |            _        | |            _        | |          _          |
|       |_|  _|       | |         |  _|       | |        _| | |       | |         | |_|       | |         |   |       | |           |         |
|         | |_        | |         | |_        | |        _| |_|       | |         | |_|       | |         |   |       | |           |         |
|                     | |                     | |                     | |                     | |                     | |                     |
|      8 projects     | |   deployment route  | |   deployment route  | |      contracts      | |      contracts      | |      contracts      |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Chain [ALL]  Origin [ALL]  Type [ALL]  Project [ALL]  Search [______________________]
Coverage: ETH complete | BASE complete | RH partial | scope: configured wallets / imported history

CONTRACT REGISTRY / 42 confirmed                                                               SELECTED / Atlas Proxy
PROJECT   CONTRACT            CHAIN  ORIGIN  TYPE       DEPLOYED    CODE
--------- ------------------- ------ ------- ---------- ----------- --------                   Address  <contract> [copy] [explorer]
> Atlas   Atlas Proxy         ETH    SWARM   proxy      10-24 16:42 present                    Chain    Ethereum mainnet
  Atlas   Atlas Logic v2      ETH    SWARM   logic      10-24 16:42 present                    Project  Atlas
  Atlas   Atlas Registry      BASE   SELF    registry   10-23 09:18 present                    Origin   SWARM / my launch
  Harbor  Harbor Vault        BASE   SWARM   vault      10-22 21:03 present                    Type     proxy
  Signal  Signal Router       RH     SWARM   router     10-22 11:29 present
  Cedar   Cedar Collection    ETH    SELF    ERC-721    10-20 14:08 present                    DEPLOYMENT EVIDENCE
  Harbor  Harbor Factory      ETH    SELF    factory    10-18 18:35 present                    Request  <my-request> [open]
  Signal  Signal Access       RH     SELF    access     10-17 07:52 present                    Launch   <launch> [open]
                                                                                               Requester <profile identity>
8 of 42 shown | sort: deployed newest | source coverage available in details                   Created  <creation-tx> [open]
                                                                                               Creator  <factory> [copy] [explorer]
RECENT DEPLOYMENTS
10-24 16:42  ETH   Atlas        2 contracts   SWARM   launch <launch>                          RELATIONSHIPS
10-23 09:18  BASE  Atlas        1 contract    SELF    tx <creation-tx>                         Logic    Atlas Logic v2 [open]
                                                                                               Control  not read
REVIEW QUEUE / 3 candidates excluded from confirmed totals
2 need creation evidence | 1 needs requester attribution                                       Creation attribution is not current control.
                                                                                               Observed <source-time> | coverage [details]

up/down select | Enter detail | / search | f filters | w profile | x explorer | c copy | r refresh | Esc hub
```

**Vorteil:** Schnellster Weg von Name, Adresse oder Chain zum richtigen Contract.
**Nachteil:** Zusammenhängende Deployments sind zunächst einzelne Tabellenzeilen.

## B — Projects: Systeme statt einzelner Adressen

Der Projektbaum ordnet Contracts über Chains hinweg und zeigt belegte
Proxy-/Implementation-Verbindungen direkt unter dem zugehörigen Contract.
Alte Versionen bleiben sichtbar, werden aber nicht als aktuelle Verknüpfung
markiert. Gruppierung in einem Projekt behauptet keine onchain Verbindung.

```text
MY CONTRACTS / PROJECTS | profile: my wallets + my Swarm requests
DEMO DATA | all names, counts and records are illustrative

+- CONTRACTS ---------+ +- PROJECTS ----------+ +- SELF --------------+ +- SWARM -------------+ +- NETWORKS ----------+ +- REVIEW ------------+
|      CONFIRMED      | |       GROUPED       | |      CONTRACTS      | |      CONTRACTS      | |     REPRESENTED     | |      CANDIDATES     |
|                     | |                     | |                     | |                     | |                     | |                     |
|            _        | |          _          | |            _        | |        _   _        | |          _          | |          _          |
|       |_|  _|       | |         |_|         | |         |  _|       | |        _| | |       | |          _|         | |          _|         |
|         | |_        | |         |_|         | |         | |_        | |        _| |_|       | |          _|         | |          _|         |
|                     | |                     | |                     | |                     | |                     | |                     |
| unique chain/address| | user labels + links | | confirmed contracts | | confirmed contracts | |   ETH / BASE / RH   | |    not in the 42    |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Chain [ALL]  Origin [ALL]  Type [ALL]  Project [ALL]  Search [______________________]
Coverage: ETH complete | BASE complete | RH partial | scope: configured wallets / imported history

PROJECTS / 8 | ETH 18 / BASE 17 / RH 7                                                         ATLAS / selected contract

v Atlas                                      7 contracts | ETH + BASE                          Atlas Proxy
  v Ethereum                                 4 contracts                                       <contract> [copy] [explorer]
    > Atlas Proxy                  proxy     SWARM   <contract> [copy]                         Ethereum mainnet | SWARM
      +-- uses Atlas Logic v2      logic     SWARM   current link
      +-- prior Atlas Logic v1    logic     SWARM   historical link                            CONTRACT MAP
      Atlas Access                 access    SWARM                                             Proxy -> Logic v2
  v Base                                     3 contracts                                       Access module -> Proxy
      Atlas Registry               registry  SELF                                              Base Registry: same project
      Atlas Factory                factory   SELF                                              No cross-chain call link inferred.
      Atlas Mirror                 module    SWARM
                                                                                               PROVENANCE
> Harbor                                     6 contracts | ETH + BASE                          My request -> launch -> creation tx
> Signal                                     5 contracts | BASE + RH                           <my-request> / <launch> [open]
> Cedar                                      4 contracts | ETH                                 Created via <factory> [copy] [explorer]
> 4 more projects                           20 contracts
                                                                                               Control not read | code present
UNASSIGNED / 0 confirmed contracts                                                             Logic v1 retained as deployment history.
REVIEW / 3 candidates  [open]                                                                  Observed <source-time> | evidence [details]

up/down select | left/right fold | Enter detail | / search | f filters | w profile | x explorer | r refresh | Esc hub
```

**Vorteil:** Beste Übersicht über mehrteilige Systeme, Versionen und Deployment-Familien.
**Nachteil:** Braucht gepflegte Projektzuordnung; eine tiefe Baumstruktur kostet Listenfläche.

## C — Chains: drei Netzwerke gleichzeitig im Blick

Jede Chain bekommt zwei zusammengehörige Hero Cards und eine eigene Liste.
Die Auswahl in einer der Spalten steuert den gemeinsamen Detailbereich unten.
Ein Chain-Filter kann eine Spalte maximieren, ohne den Profilbestand umzudefinieren.

```text
MY CONTRACTS / CHAINS | profile: my wallets + my Swarm requests
DEMO DATA | all names, counts and records are illustrative

+- ETHEREUM ----------+ +- ETH ORIGIN --------+ +- BASE --------------+ +- BASE ORIGIN -------+ +- RH ----------------+ +- RH ORIGIN ---------+
|       MAINNET       | |   DEPLOYMENT ROUTE  | |       MAINNET       | |   DEPLOYMENT ROUTE  | |       MAINNET       | |   DEPLOYMENT ROUTE  |
|                     | |                     | |                     | |                     | |                     | |                     |
|            _        | |     SELF       6    | |            _        | |     SELF       4    | |          _          | |     SELF       2    |
|         | |_|       | |     SWARM     12    | |         |   |       | |     SWARM     13    | |           |         | |     SWARM      5    |
|         | |_|       | |                     | |         |   |       | |                     | |           |         | |                     |
|                     | |                     | |                     | |                     | |                     | |                     |
| confirmed contracts | |    confirmed only   | | confirmed contracts | |    confirmed only   | | confirmed contracts | |    confirmed only   |
+---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+ +---------------------+

Chain [ALL]  Origin [ALL]  Type [ALL]  Project [ALL]  Search [______________________]
Coverage: ETH complete | BASE complete | RH partial | scope: configured wallets / imported history

ETHEREUM / 18 confirmed                         BASE / 17 confirmed                             RH / 7 confirmed
CONTRACT                ORIGIN  TYPE            CONTRACT                ORIGIN  TYPE            CONTRACT                ORIGIN  TYPE
> Atlas Proxy           SWARM   proxy             Atlas Registry        SELF    registry          Signal Router         SWARM   router
  Atlas Logic v2        SWARM   logic             Harbor Vault          SWARM   vault             Signal Access         SELF    access
  Cedar Collection      SELF    NFT               Atlas Factory         SELF    factory           Signal Registry       SWARM   registry
  Harbor Factory        SELF    factory           Atlas Mirror          SWARM   module            Beacon Factory        SELF    factory
  Atlas Access          SWARM   access            Signal Router         SWARM   router            Beacon Logic          SWARM   logic

5 of 18 shown | newest first                    5 of 17 shown | newest first                    5 of 7 shown | newest first

-----------------------------------------------------------------------------------------------------------------------------------------------
SELECTED / Atlas Proxy | Ethereum mainnet | Atlas | SWARM

Address <contract> [copy] [explorer]    Created <creation-tx> [open]    Creator <factory> [copy] [explorer]
My request <my-request> -> launch <launch> -> creation evidence    |    Code present    |    Control not read
Proxy -> Atlas Logic v2 [open]    |    Observed <source-time>    |    Evidence and coverage [details]

42 confirmed / 8 projects | 12 SELF + 30 SWARM | review 3 candidates, excluded from totals

left/right chain | up/down select | Enter detail | / search | f filters | w profile | x explorer | c copy | Esc hub
```

**Vorteil:** Verteilung und unterschiedliche Deployment-Herkunft der drei Chains sind sofort vergleichbar.
**Nachteil:** Kürzere Contract-Namen und weniger Spalten; ungleich große Bestände nutzen den Platz schlechter.

## Empfehlung

**A als Startansicht.** Die Hauptaufgabe ist eine verlässliche Übersicht über
alle eigenen Deployments mit schneller Suche und klarer Herkunft. Dafür liefert
A die höchste Informationsdichte und den kürzesten Weg zur Adresse. Die
Projektstruktur aus B eignet sich anschließend als alternative Gruppierung
innerhalb desselben Bestands. C ist die stärkste Alternative, wenn der laufende
Vergleich der drei Chains wichtiger ist als viele Vertragsdetails nebeneinander.

Der nächste Designschritt nach Auswahl ist ein isoliertes Textual-Mockup mit
sichtbarem DEMO-Marker und echten Interaktionen bei 149×45. Erst danach werden
Live-Mapping, gemessene Layout-Grenzen und Integration geplant.
