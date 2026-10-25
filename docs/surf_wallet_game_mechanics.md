# WALLET / Boardroom — Entwurfsgrundlage

Stand: 2026-10-25. Recherche und ausgewählte A/B-Vorschau mit DEMO-Daten.
Aktuelle Layoutkorrektur: eine Hero-Reihe, ergänzt durch Verlauf, Statusbalken,
Zahlungswidget, Beziehungspfad und offene Auftragsprobleme.
Die isolierte Textual-DEMO liegt in `scripts/surf_wallet_demo.py`; keine
Produktionsintegration und keine Wallet-/RPC-Datenanbindung.
MY CONTRACTS ist zurückgestellt. Der Nutzer möchte eine Wallet-Übersicht im
Boardroom, ähnlich der AGENT-Ansicht, über ihre Swarm-Aktivitäten ohne Trading.
Die Vorschläge stehen in `surf_wallet_ascii_mockups.md`.

## Aufgabe und Betrachtungsbereich

Eine ausgewählte öffentliche Wallet beantwortet vier Fragen: Was habe ich
beauftragt, was habe ich dafür bezahlt, was wurde daraus, und welche onchain
Nutzung haben die daraus entstandenen Sites, Contracts und Tokens? Tatsächliche
Zahlungen und Rückerstattungen bleiben getrennt. Agent-Details, Seats,
Worker-Status, geleistete Arbeit, Rechenaufwand und Agent-Rewards sind auf
ausdrücklichen Nutzerwunsch vollständig außerhalb dieser Ansicht. Die
AGENT-Ansicht ist ausschließlich die visuelle Vorlage.

Vorgeschlagener Einstieg: WALLET-Karte im Boardroom. Ein Wallet-Wechsel betrifft
die gesamte Ansicht. Ein neues
Tastenkürzel ist noch nicht vergeben. Es geht um eine Wallet, nicht automatisch
um alle Adressen, die derselbe Mensch kontrolliert. Kettenübergreifende
Verbindungen brauchen Belege; eine gleiche Adresse allein beweist keine
identische Smart-Account-Kontrolle auf verschiedenen Chains.

Enthalten sind Jobs, Fortsetzungen, Workflows, Launches, Oracle-Anfragen,
Schedules und Top-ups samt belegten Ergebnissen. Weitere ausdrücklich von der
Wallet ausgelöste nichtmarktbezogene Swarm-Protokollaktionen können im Verlauf
erscheinen, sobald ihre Quelle und Zuordnung geprüft sind. Dies erweitert den
Entwurf nicht um Agent-Betrieb oder eine allgemeine Wallet-Portfolioanalyse.
Weitere Aktionstypen sind keine bereits zugesagte Datenintegration.
Trades, Kurscharts, P/L und LP-/Staking-Positionsanalysen gehören nicht hinein.
Ein Swap in derselben Transaktion wird dadurch nicht als Swarm-Aktion übernommen.

Die vom Swarm gelieferten Artefakte bilden einen eigenen Bestand innerhalb
dieser Wallet-Ansicht. Es sind nur belegte Ergebnisse ihrer Aufträge, keine
beliebigen Wallet-Holdings, selbst deployten Contracts oder Outputs ihrer Agents.
Nutzung dieser Artefakte darf auch von anderen Adressen stammen; sie wird nicht
als direkte Aktion der beauftragenden Wallet ausgegeben. Nutzerkorrektur:
**ausschließlich onchain Nutzung**, keine Visits, Pageviews, Sessions,
Browser-Telemetrie oder HTTP-Probes als Nutzungssignale.

## Artefaktbestand und onchain Nutzung

- SITES zählt unterschiedliche belegte Site-Projekte. Neue CIDs oder Versionen
  desselben Projekts erhöhen den Zähler nicht. Aktuelle Version und belegter
  kanonischer URL bleiben sichtbar; keinen Hostnamen aus dem Label konstruieren.
- CONTRACTS zählt eindeutige bestätigte `(chain_id, address)`-Deployments.
  Proxy und Implementation bleiben unterschiedliche Adressen. TOKENS ist der
  verifizierte Token-Teilbestand dieser Contracts. `18 contracts / 4 tokens`
  bedeutet vier Tokens innerhalb der 18, nicht 22 Deployments. Site- und
  Contract-Zahlen werden ebenfalls nicht zu einer beliebigen Gesamtzahl addiert.
- Eine Site wird anhand ihrer belegten Deployment-Konfiguration mit Contracts
  verknüpft. Die Zeile zeigt deren Aktivität als `LINKED ACTIVE` oder
  `LINKED QUIET`. Contract-Aufrufe beweisen nicht, dass das Frontend benutzt
  wurde. Auch eine veröffentlichte Site ohne onchain Funktion kann genutzt
  werden; hier lautet ihr Zustand `NO ONCHAIN LINK`, nicht ungenutzt.
- CONTRACT-Nutzung braucht eine geprüfte, versionsgebundene Anwendungsregel,
  etwa `Registered`, `Claimed` oder `Deposited`, und erfolgreiche kanonische
  Transaktionen bzw. passende Events. Deployment, Admin-Setup, Approvals und
  bloße Code-Existenz sind keine Anwendungsnutzung. Gescheiterte Versuche
  werden nicht zu erfolgreichen Anwendungen. `eth_call`-Lesezugriffe sind
  nicht als onchain Historie beobachtbar.
- TOKEN-Nutzung zeigt belegte Utility-Aktionen wie Einlösungen, Zugangs-Claims
  oder verbrauchte Credits am nachgewiesenen Consumer. Ein einfacher Transfer,
  Holder-Anstieg oder eine Verteilung belegt keine solche Nutzung. Swaps,
  Handelsvolumen, Preis und P/L bleiben ausgeschlossen. Unklassifizierte
  Aktivität wird nicht automatisch als Nicht-Trading-Nutzung gezählt.
- Jede Metrik zeigt ihre Einheit, Chain, Zeitfenster und Abdeckung: etwa
  `27 registrations / 9 addresses / 24h`. Adressen sind keine Menschen; die
  Menge hängt vom belegten Actor-Feld ab, nicht pauschal vom Relayer oder
  `tx.from`. Owner-/Testaktivität ist nicht automatisch organische Nachfrage.
- Site, Token und Contract dürfen denselben Beleg verlinken. Gemeinsame Events
  werden anhand ihrer Chain-/Receipt-/Log-Identität dedupliziert, auch beim
  Delegieren durch Proxies. Ein einheitlicher Aktivitäts- oder Nutzergesamtwert
  über unterschiedliche Anwendungen wird nicht erfunden.

| Signal | Beleg und Bedeutung |
|---|---|
| ACTIVE | Mindestens eine bestätigte relevante Anwendungsaktion im ausgewiesenen Fenster; bei lückenhafter Historie ist der Zähler nur eine Untergrenze |
| QUIET | Null passende Aktionen bei vollständiger Abdeckung des Fensters und gültiger Anwendungsregel; keine Aussage über andere Nutzung |
| FIRST SEEN | Erste beobachtete relevante Nutzung seit dem dokumentierten Trackingbeginn; kein Anspruch auf erste Nutzung seit Deployment |
| NO DATA | Unvollständige Beobachtung ohne positiven Beleg oder fehlende verifizierte Anwendungsregel; kein Nullwert |
| NO ONCHAIN LINK | Nach abgeschlossener Zuordnungsprüfung keine belegte Verknüpfung der Site zu einem onchain Nutzungspfad; bei noch offener Prüfung gilt NO DATA |

Bei Sites wird ACTIVE/QUIET immer mit `LINKED` qualifiziert. Eine identische
Contract-Aktivität wird nicht mehreren Frontends als eigener Traffic zugeschrieben.
Positive Signale, ruhige Fenster und Datenlücken sind keine Security- oder
Qualitätsbewertungen. Keine Trendpfeile ohne zwei vergleichbare vollständige
Fenster. Reorgs, Receipt-Status, Code-/Proxywechsel und abgelaufene Interpretationen
sind vor einer späteren Datenanbindung zu behandeln. Alle Beobachtungen tragen
Blockgrenzen und einen eigenen Aktualisierungszeitpunkt.

## Zählregeln

- REQUESTS zählt eindeutige gefundene Orders im gewählten Zeitraum, inklusive
  fehlgeschlagener Zahlungsversuche. JOBS enthält `job.open` und `job.continue`;
  WORKFLOWS, LAUNCHES, ORACLES und SCHEDULES bezeichnen die jeweils anderen
  Request-Arten. Diese Kategorien sind disjunkt. Untergeordnete Workflow-Jobs,
  Schedule-Runs und Ergebnis-Deployments sind keine zusätzlichen bezahlten Orders.
- Ein Auftrag behält sein Zahlungs- und Admission-Ergebnis getrennt vom Zustand
  seines Jobs, Workflows, Launches oder Oracle-Requests. Bezahlt bedeutet weder
  geliefert noch deployt oder attestiert. Auch eine Attestation beweist noch
  keinen erfolgreichen Consumer-Callback.
- Direkte Wallet-Aktionen, Zahlungen, automatisch ausgeführte Schedule-Runs und
  zugeordnete Ergebnisse sind eigene Zeilentypen. Verknüpfte Ereignisse dienen
  als Kontext der Wallet-Nutzung, nicht als zusätzliche direkte Wallet-Aktionen.
- Ein Schedule-Top-up ist eine Aktion des Zahlers. Ein fremder Schedule wird
  dadurch nicht sein eigener. Runs werden am Schedule verknüpft, nicht jedem
  Geldgeber als selbst ausgelöste Anfrage zugerechnet.
- Ein über HTTP und Intake beobachteter Auftrag wird anhand seiner belegten
  Order-/Request-Verknüpfung einmal gezählt. Eine Transaktion kann mehrere
  Intake-Events enthalten. Chain, Contract, Request-ID und Log-Index gehören
  zur Identität; Hash oder Textähnlichkeit allein reichen nicht.
- PAID summiert belegte gezahlte Beträge je Asset und Chain, ohne fehlgeschlagene
  Versuche. PAYMENTS zählt die zugehörigen bestätigten Zahlungen. REFUNDS zeigt
  belegte Rückzahlungen zu diesen Aufträgen separat; Gas bleibt ebenfalls
  separat. Passive Reward-Zuflüsse und Allocations gehören nicht in diese Ansicht.
- ATTENTION umfasst klar benannte, deduplizierte Probleme im geladenen Bestand,
  etwa blockierte Arbeit, verweigerte Admission oder fehlgeschlagene Zahlungen.
  Normales Pending ist kein Fehler. Keine willkürliche Erfolgsquote über Rollen.

## Aktuelle öffentliche Quellen

Die [offizielle IMD-Dokumentation](https://imd.fun/docs/llms.txt) wurde am
2026-10-25 frisch abgerufen. Die nachfolgenden Grenzen stammen aus ihr; konkrete
Wallet-Abdeckung und Endpoint-Payloads wurden für dieses Mockup nicht gemessen.

| Quelle | Geeignet für | Grenze |
|---|---|---|
| `GET /requests/paid-by/:address` | Öffentliche bezahlte oder versuchte Orders, Action, Payment und Result-Links | Höchstens neueste 100; ohne Input/Signaturen; keine zugesagte Vollhistorie |
| `GET /intake/:chainId/:transactionHash` | Events einer bereits bekannten Intake-Transaktion, Payer, Order, Admission und Completion | Kein Wallet-Discovery-Endpunkt; mehrere Events pro Transaktion; historische Log-Discovery separat nötig |
| `GET /jobs/:id`, `/workflows/:id`, `/launches/:id` | Ausführung, Parent-/Child-Links, Artefakte und Deployments | Zuordnung erfolgt über belegte IDs; Contributor oder Owner ist nicht automatisch der Payer |
| `GET /oracle/requests/:id` und `/attestation` | Oracle-Verlauf, Panel-Ergebnis, Attestation | Anfrage, Attestation und Consumer-Ausführung getrennt |
| `GET /schedules?owner=:wallet` | Paginierte eigene Schedules | Fremde Top-ups zusätzlich über Zahlungsbelege erfassen |
| `GET /schedules/:id` | Zustand, verbleibende Runs und jüngste Ausführungen | `latest` enthält höchstens 50 Runs |
| `GET /sites`, `/sites/:id`, Site-/Launch-/Workflow-Links | Site-Projekt, Veröffentlichung und Zuordnung zum eigenen Auftrag | Liste der neuesten 100, kein persönlicher Gesamtkatalog und keine Nutzungsstatistik; kanonischen URL aus tatsächlichem Artefakt lesen |
| Keyless RPC-Receipts, Logs und geprüfte anwendungsspezifische Getter | Onchain Nutzungsbelege und Regeln pro Deployment/Consumer | Keine universelle Nutzungs-API; vollständige Fenster und Quellen pro Chain vor Integration prüfen |

Freie Checks, ungesendete Entwürfe und ausschließlich lokale Aktivitäten haben
keine zugesagte öffentliche Wallet-Historie. Von Contracts oder Relays bezahlte
Requests gehören nur mit explizitem Beleg in eine verknüpfte Rolle, nicht als
direkt von der gewählten Wallet bezahlt. Callback-Ziel oder heutiger Contract-
Owner allein ist kein solcher Beleg. Begrenzte APIs und fehlende Archive
verhindern vorerst die Zusage „alle jemals“. Seat-, Worker-, Contributor- und
Agent-Earnings-Quellen werden für diese Ansicht nicht benötigt oder angeboten.

## Bestehende MaxPane-Bausteine

`SwarmClient` in `data/surf_swarm_client.py` besitzt bereits Job-, Workflow-,
Launch- und Oracle-Leser. `surf_work_reader.py` zeigt begrenzte Detail-Joins.
Eine vollständige Wallet-Order-Historie ist damit noch nicht vorhanden.
`SwarmClient.fetch_sites` und die Deployment-/Artifact-Joins liefern weitere
Katalogbausteine. Die vorhandenen Token-Marktleser sind keine Quelle für diese
Nutzungssignale. Die geprüften NFT-Adapter zeigen versionsgebundene Event-/State-
Interpretation, decken aber nicht automatisch alle Contract-Arten oder Chains ab.
Eine allgemeine Non-Trading-Nutzungsquelle ist in dieser Entwurfsrunde nicht
nachgewiesen; bis zu einer geeigneten Regel bleibt ein Artefakt `NO DATA`.

Das Design übernimmt den Stil der Rack-Karten und ihre großen Ziffern aus der
AGENT-Ansicht. Nach der gerenderten Vorschau verlangt der Nutzer effizientere
Raumnutzung, mehr unterschiedliche Widgets und nur eine Kartenreihe. A behält
sechs Karten für REQUESTS, JOBS, WORKFLOWS, LAUNCHES, ORACLES und SCHEDULES.
Die zweite Reihe entfällt. Site-/Contract-/Tokenzahlen, laufende Aufträge,
Zahlungsbeträge und offene Punkte bleiben in Fußzeilen und Widgets lesbar.

Unter den Karten zeigt A vier kompakte Widgets: tägliche beobachtete Requests
als Sparkline, disjunkte Auftragszustände als Balken, Onchain-Nutzung und deren
Abdeckung als Contract-Verteilung sowie Zahlungen und Erstattungen mit einer
Settlement-Verteilung. Die Statusverteilung zählt jeden der 84 Demo-Requests
genau einmal; Follow-up-Markierungen sind eine separate Sicht und kein weiterer
additiver Zustand. Ein Trend der beobachteten Requests ist keine Aussage über
die Vollständigkeit einer späteren begrenzten API-Historie.

Die Onchain-Verteilung zählt nur die 18 Contract-Identitäten, Tokens inklusive.
Vier haben positive Nutzungsbelege (einschließlich FIRST SEEN), einer ist nach
vollständigem Fenster QUIET und dreizehn sind NO DATA. Die acht verknüpften
Sites erhöhen diese Zahlen nicht. Regelabdeckung (6/18) und vollständige
Regelfenster (4/6) bleiben getrennt; ein teilweise gelesenes positives Fenster
kann ACTIVE sein, ein teilweise gelesenes Nullfenster nicht QUIET.

CREATED steht neben dem Beziehungspfad des ausgewählten Artefakts und vier
benannten offenen Auftragsproblemen; RECORD bleibt darunter. Der Pfad zeigt
Auftrag, Artefakt und gegebenenfalls verknüpften Contract, ohne daraus
Frontend-Traffic abzuleiten. B behält seine eine Kartenreihe und den Explorer;
unter der Liste ersetzt dasselbe Zahlungswidget den bisherigen Textblock.
Zielgröße 149×45, bei 100×30 erreichbar durch Scrollen. ASCII-Abmessungen sind
kein gemessener Textual-Layout-Pin; die genaue Aufteilung wird gerendert geprüft.

## Laden und Bedienung

Alle sichtbaren Karten laden eigenständig beim Öffnen der Wallet-Ansicht.
Die Übersicht darf keinen vorherigen Besuch einer Auftragsdetail-Ansicht
brauchen. Retained Cache für dieselbe Wallet erscheint sofort; Reads
haben getrennte Zeitstempel. Wallet-Wechsel isolieren Daten und abbrechbare
Reads anhand ihrer Identität. Boardroom-Kompaktkarte und Detailansicht behalten
getrennte, begrenzte Ladebudgets.

`Orders [30D]` steuert Aufträge, Zahlungen und ihre aktuellen Zustände.
`Assets [ALL KNOWN]` zeigt alle bislang belegten Outputs eigener Aufträge,
einschließlich älterer Ergebnisse. `Usage [24H]` steuert deren onchain Messfenster,
standardmäßig für alle belegten Akteure. Diese Bereiche sind sichtbar getrennt.
Typ-/Statusfilter betreffen die Liste; Überschrift und Trefferzahl machen das
sichtbar. Quellenabdeckung bleibt lesbar, API-Fehlerzustände
intern; noch ungelesene große Ziffern bleiben entsprechend den aktuellen
Projektregeln leer. Keine falschen Null-Fakten, keine Loader pro Karte.

Adressen erhalten Copy-/Explorer-Aktionen, Ergebnisse Links zu Job, Launch,
Site oder Receipt. MaxPane bleibt keyless und ausschließlich lesend. Alle
Mockup-Werte sind DEMO. Die gewählte A/B-Vorschau ist durch `surf_wallet_PRD.md`
und `surf_wallet_mockup_plan.md` spezifiziert. Der Standalone-Mock verwendet
ausdrückliche Beleg-Platzhalter ohne externe Aktionen; echte Address-/Explorer-
Interaktionen gehören zur späteren Datenintegration. Keine Screen-Registrierung,
RPC-Quelle oder Wallet-Aktion wird dem Produktionsdashboard hinzugefügt.
