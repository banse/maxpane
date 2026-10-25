# WALLET / Boardroom — Entwurfsgrundlage

Stand: 2026-10-25. Nur Recherche und ASCII-Preview, keine Implementierung.
MY CONTRACTS ist zurückgestellt. Der Nutzer möchte eine Wallet-Übersicht im
Boardroom, ähnlich der AGENT-Ansicht, über ihre Swarm-Aktivitäten ohne Trading.
Die Vorschläge stehen in `surf_wallet_ascii_mockups.md`.

## Aufgabe und Betrachtungsbereich

Eine ausgewählte öffentliche Wallet beantwortet drei Fragen: Was habe ich
beauftragt, was habe ich dafür bezahlt, und was wurde daraus? Tatsächliche
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

Das Design übernimmt die zwölf Rack-Karten der AGENT-Ansicht, ihre großen
Ziffern und RECORD-Tabelle. Alternativen reduzieren die Hero-Anzahl zugunsten
von Auftragsdetails, Zahlungsbelegen oder mehr Chronikplatz. Zielgröße 149×45;
ASCII-Abmessungen sind kein gemessener Textual-Layout-Pin.

## Laden und Bedienung

Alle sichtbaren Karten laden eigenständig beim Öffnen der Wallet-Ansicht.
Die Übersicht darf keinen vorherigen Besuch einer Auftragsdetail-Ansicht
brauchen. Retained Cache für dieselbe Wallet erscheint sofort; Reads
haben getrennte Zeitstempel. Wallet-Wechsel isolieren Daten und abbrechbare
Reads anhand ihrer Identität. Boardroom-Kompaktkarte und Detailansicht behalten
getrennte, begrenzte Ladebudgets.

Zeitraum steuert Aktivitäten und Summen. Aktuelle Auftragszustände beziehen sich
auf die gefundenen Aufträge dieses Zeitraums. Typ-/Statusfilter betreffen die Liste; Überschrift und Treffer-
zahl machen das sichtbar. Quellenabdeckung bleibt lesbar, API-Fehlerzustände
intern; noch ungelesene große Ziffern bleiben entsprechend den aktuellen
Projektregeln leer. Keine falschen Null-Fakten, keine Loader pro Karte.

Adressen erhalten Copy-/Explorer-Aktionen, Ergebnisse Links zu Job, Launch,
Site oder Receipt. MaxPane bleibt keyless und ausschließlich lesend. Alle
Mockup-Werte sind DEMO. Erst nach Auswahl folgen PRD und Implementierungsplan;
dieser Entwurf fügt keine Screen-Registrierung, RPC-Quelle oder Wallet-Aktion hinzu.
