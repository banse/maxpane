# SURFBOARD-Marktdaten und Swarm-Laden: Implementierungsspezifikation

Stand: 17.10.2026. Status: spezifiziert, nicht implementiert. Umsetzung: **Tier 2**, weil gemeinsame Datenverträge und mehrere Ansichten betroffen sind. Diese Arbeit liefert ausschließlich Dokumentation; kein Commit, Runner, Job oder Anwendungscode gehört dazu.
Ziel: korrekte keylose Pooldaten unabhängig erhalten und ausgewählte AGENT-Inhalte früher bereitstellen, ohne WORK-Provenienz oder bestehende lokale Navigation zu schwächen.
Der ausführbare Ablauf steht in [surf_data_loading_plan.md](surf_data_loading_plan.md). Maßgeblich bleiben `CLAUDE.md` und `.claude/rules/{data,surf}.md`.

## 1. Ausgangspunkt und Abgrenzung

- Marktziel ist `--game surfboard`, **IMD BOARDROOM**; Surf `b` bleibt das separate Seat-/Fleet-Board.
- Quellen sind die beiden vorhandenen [Markt](reports/Keyless%20Marktdaten%20f%C3%BCr%20Surfboard.md)- und [Navigationsberichte](reports/Schnelle%20Navigation%20zwischen%20Schwarmjobs.md), keine neue Anbieterrecherche.
- `SurfClient.fetch_market()` wartet heute auf vier parallele Zweige; ein IMD-Ausfall kann erfolgreiches ETH/USD verwerfen. Gecko übernimmt bisher einen nicht gleichwertig verifizierten Pool.
- Warme RECORD-Popups öffnen kopierte Zeilen ohne HTTP. WORK wechselt Job/Schritt ebenfalls lokal. Offene Modals bleiben bewusst auf ihrem Snapshot.
- `AgentCardSources.read()` wartet auf Earnings und bis zu 64 Membership-Details in Vierergruppen, bevor weitere RECORD-Stufen laufen.
- Scores laufen separat alle 1.800 s: höchstens 100 Listenjobs, Details sequenziell. Das sind keine 100 Requests pro Klick und kein nachgewiesener UI-Lock.
- RECORD behält 400 Einträge/48 h, vier Submission-Jobs und zwei Popup-Details pro Zyklus. Seat-Singleflight, Wechsel-Cancellation und sechs Seat-Snapshots existieren bereits.
- **Keine erreichte Beschleunigung behaupten:** vorhandene Endpointproben messen weder produktiven First Paint noch vollständige Navigation. P0 erhebt zuerst eine reproduzierbare Baseline.

## 2. Entscheidung und Gegenleistungen

| Option | Umfang | Gegenleistung |
|---|---|---|
| A: nur vorhandene Stufen umordnen | Poolidentität/ETH-Teilerfolg korrigieren, RECORD vor breite Karten stellen | Kleinster Eingriff, aber unabhängige Leser fragen dieselben Details weiter mehrfach ab. |
| **B: A plus begrenztes Client-Memo, gewählt** | Gemeinsame Detailreads, explizite Beobachtungszeiten, endliche Frische und unveränderte volle Payload | Etwas mehr Cancellation-/Invalidierungslogik; weniger doppelte Reads innerhalb belegter Überlappung. |
| C: Provider-Router, persistentes Ressourcenrepository oder Indexer | Allgemeine Quellenwahl und Vollhistorie | Für diese beiden Probleme zu großer Betriebs- und Migrationsaufwand; entfällt. |

Die vorhandene Richtung bleibt `client → cache → manager → screen → widgets`; pure Folds/Analytics bleiben ohne I/O und Uhr.
Ethskills `indexing.md` begründet aktuelle RPC-/Multicall-Reads statt neuer Vollhistorien-Scans; bestehende API-Historie bleibt eigenständig. `testing.md` wird auf Python-Fixtures, Fehlerfälle und Invarianten angewandt, nicht auf Foundry/Forks.
Akzeptierte Abhängigkeit: öffentliche API-Anbieter können ausfallen oder widersprechen. Ausweg sind vorhandene onchain Zustandsreads und erhaltene Daten mit wahrer Quellenzeit; kein Key, kein bezahlter Fallback, keine neue Serverkomponente.

## 3. Unveränderliche Grenzen

- Ausschließlich keylose Reads. Keine Signaturen, Transaktionen, Secrets, Runner-Anbindung, bezahlten Jobs oder externen Feedbackposts.
- Tests benutzen committed Fixtures, einen bei unerwarteter Nutzung fehlschlagenden Transport, injizierte Uhren und steuerbare Events. Keine Netzwerke, Forks, Sleeps zur Synchronisation oder echte Zwischenablage.
- Ein Fehler bleibt `None`; bestätigte leere Daten und numerische Null bleiben unterscheidbar. Keine FDV-als-Cap-Ersetzung, keine geratenen Decimals, keine Preis-Mittelwerte aus widersprüchlichen Anbietern.
- Die Surf-Anzeigevorgabe vom 16.10.2026 gilt: Quellenfehler/Frische bleiben intern, fehlende Werte neutrale Striche, bestehende neutrale Zeitmarker bleiben. Operative Status und partielle Abdeckung bleiben sichtbar.
- Keine neue Next/Previous-Navigation, keine Nachbar-Prefetches, kein allgemeiner Scheduler, keine neuen Widgetkeys oder Layoutpins in dieser Änderung.
- Retention und Frische sind getrennt: 400/48 h werden nicht durch die unten vorgeschlagenen 600/120 s ersetzt. Fällige Nachprüfungen bleiben innerhalb bestehender Lesebudgets.

## 4. Marktvertrag

```python
async def SurfClient.fetch_market(real_pool_id: str | None = None) -> MarketSnapshot | None: ...
async def SurfClient.fetch_eth_usd() -> float | None: ...
def _decode_imd_dex(body: object, real_pool_id: str) -> MarketSnapshot | None: ...
def _decode_imd_gecko(body: object, real_pool_id: str) -> MarketSnapshot | None: ...
```

`fetch_eth_usd()` verwendet zunächst den vorhandenen CoinGecko-Endpunkt; nur endliche positive Zahlen, keine bools. Kein neuer Anbieter.
`SLOT_ETH_USD` enthält `{"eth_usd": float, "source": "CoinGecko", "provider_ts": None}`; der Slotzeitpunkt ist der erfolgreiche tatsächliche Abrufabschluss.
Ein Marktfehler verändert diesen Slot nicht. Ein Quotenfehler erhält Wert und Zeitpunkt des vorherigen Erfolgs und setzt ausschließlich seinen internen Fehlerzustand.
`MarketSnapshot` erhält defaultete interne Felder `market_source`, `chain_id`, `pool_id`, `base_token`, `quote_token`, `base_decimals`, `quote_decimals`, `target_side`, `provider_ts`, `block_number`; vorhandene numerische Felder bleiben kompatibel. Decimals kommen nur aus bereits verifizierten Tokenmetadaten; unbekannte Decimals verhindern keine Human-unit-Providerwerte.
Metadaten sind optional: IDs/Adressen/Quelle `str`, Chain/Decimals/Block `int`, Providerzeit `float`, Zielseite `"base"|"quote"`; Standard jeweils `None`. Interne Quotenfamilie heißt `quote`, nicht `market`.
Unbekannte Providerzeit und Blocknummer bleiben `None`. HTTP-Cachezeit, Pool-Erstellungsdatum und lokale Abrufzeit sind keine Provider-Marktzeit.

### 4.1 Identität und Auswahl

1. Erwartete Identität stammt aus dem bereits gelesenen Live-Pool: Chain/Netzwerk, vollständige Pool-ID, Tokenadressen und Zielseite. Ohne gültige Pool-ID kein geratener Cold-Start-Pool.
2. Primär `GET /latest/dex/pairs/ethereum/{live_pool_id}`, bei tatsächlicher Lücke exakt derselbe Pool über `GET /api/v2/networks/eth/pools/{live_pool_id}`.
3. Decoder prüfen Chain/Netzwerk, Pool-ID einschließlich bytes32-v4-IDs, Tokenzugehörigkeit und base/quote-Zuordnung. Ein schneller fremder Pool oder `included[0]` ist keine Antwort.
4. Steht IMD auf der Quote-Seite, dürfen nur explizite Quote-USD-Daten verwendet werden. Base-Cap, Base-FDV und Base-24h-Änderung werden nicht umetikettiert; mehrdeutige Felder bleiben `None`.
5. Eine vollständige Quellenprojektion gewinnt, keine Mischung von Cap/FDV/Preis verschiedener Pools oder Anbieter. Cap `null` bleibt unbekannt, Volumen `0` bleibt ein echtes Nullvolumen.
6. Human-unit-Preise werden nicht erneut mit Decimals dividiert. Raw-unit-Konversionen benötigen verifizierte Decimals. Referenzpool und CappedBurnHook-POOL4 bleiben getrennt.
7. Onchain `sqrtPriceX96`-/Tick-Preise behalten Vorrang in den vorhandenen Pfaden. Referenzmarkt-24h-Änderung im POOL4-Tooltip bezeichnet weiterhin den Referenzmarkt, keine POOL4-Rendite.
8. Der bestehende FP/Base-Zweig bleibt separat fachlich zugeordnet. Kein Einmischen alter FP-Daten in einen neuen Snapshot mit neuem Datum; gegebenenfalls bleibt FP `None` wie beim bisherigen Fehlerpfad.

### 4.2 Aktualisierung, Budgets und Projektion

- ETH-Teilerfolg wird unabhängig vom Performancebefund erhalten. Eigene detached Tasks werden aktiviert, wenn P0 die Kopplung an Full/Chain reproduziert: `_offer_market(now)` und `_offer_eth_usd(now)` vor dem Chain-Await.
- `TIER_MARKET` und `TIER_ETH_USD`: Erfolg 90 s, Fehlerbackoff 60 s. Pro Familie ein Manager-Task; parallele Angebote teilen ihn. Jeder abgeschlossene Slot wird ohne Warten auf den anderen veröffentlicht.
- Passive `get_snapshot()`-/Hub-Projektion startet keine Reads. Cancellation eines einzelnen Wartenden beendet keinen manager-eigenen Refresh; `close()` cancelt und awaited alle eigenen Tasks.
- Die Korrektheitsänderung behält zunächst die vorhandene Timeoutpolitik; der exakte Gecko-Fallback wird nur bei einer Primärlücke angeboten. Ein valider schneller Primärwert wartet nicht auf Gecko.
- Erst P0 friert anhand tatsächlicher Laufzeiten begrenzte Primär-/Gesamtdeadlines und Versuchszahlen ein. Gate-Wartezeit und HTTP-Laufzeit werden getrennt gemessen; die Gesamtdeadline muss dem budgetierten Fallback eine echte Chance lassen. Bei ausgeschöpftem Budget bleibt Last-good.
- Ein verzögert paralleles Backup ist nur eine Folgeoption bei gemessenem Bedarf; niemals gewinnt einfach das schnellste HTTP 200.
- Bestehendes Token-Pacing von 2,1 s bleibt zunächst; P0 zählt die kombinierten tatsächlichen Gecko-Versuche einschließlich Retries beider Clients. Die widersprüchlichen dokumentierten 10/30 Calls/min werden nicht als geklärte Anbieterzusage ausgegeben.
- Nur bei belegter Überschreitung eines begründeten Gesamtbudgets folgt ein separates konditionales Paket: ein injizierter, pro Prozess geteilter Gate für beide Clients, ohne versteckte weitere Instanz. Eine konservative 6,2-s-Option würde History spürbar verzögern; diese Gegenleistung ist Teil der Entscheidung.
- Launch-Token-DexScreener-Batches bleiben 30, History/Trades und Volumen behalten ihre bestehenden Grenzen. Falls ein Gate eingeführt wird, zählen alle tatsächlichen Retry-Starts mit; eine ausgeschöpfte Deadline umgeht das Gate niemals.
- Der zentrale Integrator ergänzt synchron `_project_market_values(data, *, market_entry, quote_entry, launchpad_entry, pool4_entry, now)` und verwendet ihn sowohl im Zyklus als auch im passiven Hub.
- Der Helper erfasst die vier Versionen einmal und berechnet alle betroffenen USD-Werte konsistent neu. Ein neuer ETH-Kurs macht keinen alten Poolzustand frisch; Pool- und Quotenzeiten bleiben getrennt.
- `data/surfboard.py::_launchpad_volume` liest den neuen Quotenfamilienzustand. `SurfManager._hub_pool4_price_direction` berücksichtigt beide Zeiten und setzt die Vergleichsbasis bei Chain-/Pool-/Tokenorientierungswechsel zurück.
- Passive Repaints hängen keine Historienpunkte an und vergleichen keine unzulässige alte Pfeilbasis. Bestehende Marktdaten-Caches ohne neue Metadaten bleiben ladbar, aber ohne erfundene Provenienz.

## 5. Gemeinsamer Jobdetailvertrag

`SurfManager` erzeugt bereits genau einen `self.swarm_client` und gibt ihn an `AgentCardSources` und `WorkReader` weiter (`surf_manager.py:1090–1105`). Live, Scores, RECORD und auch SITES verwenden dieselbe Instanz. Es braucht keinen globalen Cache.
Die bestehende öffentliche Methode heißt **`fetch_job`**, nicht `fetch_job_detail`.

```python
@dataclass(frozen=True)
class JobDetailRead:  # in surf_swarm_client.py, kein neuer Model-/Repository-Layer
    payload: dict | None
    observed_at: float | None  # Wallclock des erfolgreichen HTTP-Abschlusses
    started_mono: float        # Beginn des tatsächlichen HTTP-Reads
    revision: str | None       # nur valide gelieferte Revisionsinformation
    from_cache: bool

async def SwarmClient.read_job_detail(
    job_id: str, *, fresh_after: float | None = None
) -> JobDetailRead: ...
async def SwarmClient.fetch_job(job_id: str) -> dict | None: ...
```

`fetch_job` bleibt der kompatible Payload-Adapter; nur Verbraucher mit Quellenzeit-/Frischebedarf nutzen `read_job_detail`. Busy bleibt eine frische Kopie von `SEAT_BUSY`, Fehler `None`.
Das gilt auch für SITES, Live und Scores: Zyklusabschluss/Projektion darf jetzt datiert sein, eine darin verwendete Detailbeobachtung nicht. Wer Details in einen datierten Quellen-Slot faltet, übernimmt deshalb die Envelope-Zeit intern; ein gemeinsamer Quellenmarker darf die älteste benötigte Beobachtung nicht verjüngen. Tier-Schedulingzeit bleibt davon getrennt; keine neuen Widgetkeys nötig.
Constructor erhält injizierbare `clock` und `monotonic`. Monotone Zeit entscheidet TTL/Deadlines; `observed_at` ist die Quellenbeobachtung für Projektionen. Eine Wallclock-Korrektur verlängert keine Memo-TTL.
Jede Rückgabe enthält eine Deepcopy; das frozen Envelope allein macht verschachtelte Dicts nicht unveränderlich. Kein Verbraucher kann einen anderen mutieren.
Gespeichert wird die vollständige gültige API-Payload einschließlich Projekt-/Workflow-/Versionsdaten, Nodes, Rollen und Kanten. Keine 16-/30-Node-Projektion als gemeinsames Detail verwenden.
Die bestehende knappe Popup-Projektion bleibt ausschließlich Popup-Projektion. Ein Body mit fremder Job-ID wird verworfen; der bestehende Whole-Payload-Test muss dieselbe angefragte Fixture-ID verwenden.

### 5.1 Identität, Speicher und Frische

- Key ist innerhalb der Clientinstanz `(normalisierter erlaubter Hostpool/base_url, lokale API-Vertragsversion, job_id)`. Keine gemeinsame Nutzung zwischen Instanzen, Netzwerken oder frei konfigurierten Deployment-URLs.
- Die zwei bekannten Hosts desselben Deployments dürfen innerhalb dieser Instanz teilen. Änderungen des Scopes leeren Memo und Inflight; keine fremde Job-ID-Aliasbildung.
- LRU: höchstens 400 abgeschlossene Einträge und insgesamt 16 MiB serialisierte Payload; pro Eintrag höchstens 512 KiB. Limits werden auch für negative Einträge gezählt.
- Größere gültige Details werden ungekürzt geliefert und nur während ihres laufenden Requests geteilt, anschließend nicht behalten. Kein stilles Abschneiden von WORK-Kontext.
- Höchstens acht unterschiedliche Detailflights gleichzeitig. Gleiche IDs treten einem vorhandenen Flight bei, andere warten auf einen freien Platz; keine zusätzliche Prefetch-Warteschlange.

| Detail/Versuch | Vorgeschlagene Memo-Frische | Begründung |
|---|---:|---|
| aktiver/nichtterminaler vollständiger Job | 30 s | kürzer als die vorhandenen 60-/120-s-Leser, Wiederverwendung über gleichzeitige Leser |
| terminaler vollständiger Job (`completed`, `failed`, `cancelled`) | 600 s | an bestehende Membership-Frische angelehnt; terminal bedeutet nicht unveränderlich |
| `None`, ungültiger Body, Busy | 15 s | kurze gemeinsame Fehlerbremse; keine erfolgreiche Beobachtung |

Das rohe Detailmemo errät keine fachliche Veröffentlichungs-Vollständigkeit aus fehlenden Launch-/Resultfeldern. Ein Verbraucher mit nach seinem bestehenden Vertrag unvollständigen Fakten wird nach 120 s erneut fällig und fordert nötigenfalls über `fresh_after` einen echten Detailread; die Submissionressource bleibt separat.
TTL ist eine Obergrenze für Reuse, nicht eine zusätzliche Pollschleife. Fehler überschreiben weder Last-good-Payload noch deren `observed_at`; der Aufrufer erhält trotzdem den Fehler, keinen als neu bestätigten Altwert.
`fresh_after` ist eine monotone Untergrenze für den Start des akzeptierten Reads. Ein älterer Cachehit erfüllt sie nicht. Ein früher gestarteter gemeinsamer Flight wird abgewartet; danach startet genau ein geteilter Folgeread.
Gültige geänderte `updatedAt`-/State-Angaben in bereits gelesenen Joblisten markieren betroffene Einträge dirty; keine zusätzliche Listen-API. Unveränderte oder fehlende Angaben beweisen keine Unveränderlichkeit.
Ein Dirty-Epoch verhindert, dass eine vor der Änderung begonnene Response den neuen Zustand überschreibt; sie wird nicht als aktuell veröffentlicht. Der nächste zulässige Read bestätigt den Zustand.
`revision` bleibt `None`, solange ein zuverlässiger Wert fehlt. Kein lokaler Zeitstempel oder Payloadhash wird als Serverrevision ausgegeben. TTL und WORK-Revalidierung bleiben auch bei Revisionen bestehen.

### 5.2 Cancellation und Ressourcenidentitäten

- Wartende verwenden `asyncio.shield` plus Waiter-Zähler. Abbruch eines Seat-/WORK-Konsumenten beendet keinen Flight, auf den ein anderer Leser noch wartet.
- Bei null Wartenden darf der Flight gecancelt werden; Registrierung/Counter werden in `finally` bereinigt. Ein neuer Leser wartet eine bereits laufende Cancellation ab und kann anschließend neu starten.
- Client-Shutdown cancelt und awaited sämtliche Flights vor Schließen des owned HTTP-Clients; Fehler und CancelledError werden nicht als erfolgreiche Cachepunkte gespeichert.
- Seat-/Token-/Viewwechsel erhöhen eine Generation. Nach jedem Await prüft der publizierende Consumer Identität und Generation; A→B→A kann keine alte A-Response in die neue A-Auswahl schreiben.
- Eine überlebende gemeinsame Response darf nur in ihren passenden Ressourcenmemo gelangen. Aus ihr folgt keine Berechtigung, aktuelle globale Auswahl, Filter oder einen fremden Seat zu überschreiben.
- Jobdetail, Result und Submissions bleiben verschiedene Ressourcen. Kein neuer Result-Endpunkt. Ein `completed`-Job beweist keine vollständige Result-/Submission-/Launch-Veröffentlichung.
- Submissionidentität bleibt `(job_id, exakter submission_hash)` plus geprüfte Seatzuordnung; Oracle-Antworten verlangen weiterhin Request- und exakte Member-Hash-Verifikation. API-Daten ersetzen keine onchain Nachweise.
- Persistente RECORD-Popupdetails werden bei terminalen Jobs nach 600 s erneut fällig; unvollständige/aktive behalten 120 s. Fehlende/leere/`not_served`/`no_reply`-Submissions prüfen nach 120 s erneut, vollständig positive terminale Fakten spätestens nach 600 s.
- Hash-/State-/bekannte Revisionswechsel invalidieren betroffene Projektionen früher. Positive alte Daten bleiben im 400/48-h-Retentionsfenster verfügbar, aber ihre Uhr wird durch Memo-Hits nicht erneuert.
- Existierende vier Submission-Jobs/zwei Popup-Details pro Zyklus und Oracle-Grenzen bleiben; keine Zusatzwelle durch jede verspätete Einzelantwort. Neue Frischegrenzen werden gegen P0-Requestzahlen geprüft.
- Das Detailmemo startet nach Prozessneustart leer. Bestehende persistente Slots behalten Schema und Retention; aus restaurierten terminalen Punkten wird keine bestätigte neue Beobachtung abgeleitet.

## 6. Ausgewählter RECORD-Pfad

```python
async def AgentCardSources.read_membership(
    seat: dict, now: float, *, job_ids: Sequence[str], cap: int
) -> tuple[str, ...]: ...  # tatsächlich versuchte Job-IDs, höchstens vier parallel
async def AgentCardSources.read_earnings(seat: dict, now: float) -> None: ...
```

`read_membership` prüft IDs, bestehende Fälligkeit und Seat-Kandidaten selbst und schreibt einzelne verifizierte Punkte mit echter Quellenzeit. Der bisherige `read()` kann ein kompatibler Wrapper bleiben; die frühe Managerstufe wartet ihn nicht ab.

1. Ausgewählten Seat früh anbieten, bevor ein allgemeiner Full-Read abgewartet wird, sofern P0 diesen verzögerten Einstieg reproduziert. Bestehendes Seat-Singleflight erhalten.
2. Nach erfolgreichem Seat-Read bereits vorhandene Zeilen projizieren. Noch fehlende Fakten bleiben unbekannt; keine bestätigte Membership, Antwort oder Null aus fehlenden Daten erzeugen.
3. Aus dem bestehenden gefilterten 40–400-Fenster die ersten höchstens vier unterschiedlichen erforderlichen Jobs priorisieren. Keine neue Cursor- oder Navigations-API voraussetzen.
4. Für diese Jobs minimale Membership lesen und mit tatsächlichem `observed_at` speichern. Launch-Filter benötigen verifizierte Live-Launch-ID/Chain, nicht `work[].launch` als Absicht.
5. Erst passende Seat-/Job-/Hash-Fakten beziehungsweise verifizierte Oracle-Membership erlauben bestätigte Antwortprojektion. Fehlende Membership bleibt partiell; breite Historie muss dafür nicht fertig sein.
6. Innerhalb des bestehenden Zyklusbudgets Submissions, Oracle-Anreicherung und Popupdetails nachführen; vor und nach Await Generation prüfen. Einzelne Fehler dürfen andere bereits verifizierte Zeilen nicht verwerfen.
7. Übrige Membership danach über dieselbe Methode mit `cap=64-len(attempted)` bearbeiten und die zuvor versuchten IDs ausschließen; insgesamt höchstens 64 Jobs in Vierergruppen. ENS, `read_earnings()` und Rewards dürfen diesen frühen RECORD-Schritt nicht blockieren.
8. Karten behalten ihre unabhängigen Zustände und vollständigen Summenregeln. Solange relevante Membership fehlt, bleiben launches/other oder worked-on-Teilzahlen unbekannt; kein vorzeitiges Nullergebnis.

Die Ergänzung verändert die Reihenfolge vorhandener Stufen. Sie erzeugt keinen zweiten Seat-Leser, keine unbeschränkten Tasks und keine API-Abfrage im Messagehandler.
Scores bleiben detached und sequenziell; der gemeinsame Client reduziert nur nachweislich doppelte Detailreads. Ein eigenständiger Score-Scheduler oder größerer Fanout ist nicht Bestandteil der Umsetzung.

## 7. WORK-Reuse ohne falsche Aktualität

- Jeder fällige WORK-Sweep liest seine aktuellen Job-/Workflowseiten und Overview wie bisher; ein `createdAt`-Cursor allein ersetzt keinen Active-Scan.
- Aktuelle und zuvor aktive Job-IDs benötigen `read_job_detail(..., fresh_after=...)` mit einer nach den aktuellen Discovery-Reads erfassten monotonen Grenze. Ein alter aktiver Memo-Eintrag autorisiert keine frische Zählung.
- Auch auf späteren Discovery-Seiten neu gefundene aktive Jobs benötigen einen danach begonnenen Bestätigungsread. Misslingt dieser, bleiben Discovery/Counts entsprechend partiell oder unbekannt.
- Nur durch frische aktive Details autorisierte Projekt-/Workflow-/Versionsbeziehungen dürfen terminalen Kontext aus dem Memo nutzen. Projektzugehörigkeit, Workflowanker, Node-Kanten und Widerspruchsprüfungen bleiben vollständig.
- Wiederverwendeter historischer Kontext wird nicht Teil der aktuellen Active-Counts. Fehlende aktive Details oder unvollständige Erkennung dürfen kein `0 active` erzeugen.
- Bestehende Grenzen bleiben: bis 100 Jobseiten, 512 erforderliche Jobdetails, 128 Workflowdetails, 256 Versionen pro Projekt und 24 optionale Details. Cachehits heben diese semantischen Grenzen nicht auf.
- Der Reader publiziert ausschließlich einen konsistenten Gesamtsnapshot. Cancellation/Busy publizieren keine halbfertige neue Version; vorherige Daten bleiben erhalten.
- Snapshot-`read_ts` beschreibt aktuelle Discovery; Wiederverwendung verjüngt keine historischen Quellenfakten. Lokale Auswahl, Suche und Tree-Expansion bleiben I/O-frei.

## 8. Messung und deterministische Abnahme

P0 zählt logische Ressourcenreads **und** echte Transportversuche einschließlich Hostrotation/Retry getrennt. Erfasst werden Request-Ende, Slot-Veröffentlichung, erste nutzbare Projektion, Vollständigkeit, Cachealter und UI-Auswahlzeit.
Ein fixturebasierter Harness hält alle Aufträge/Events kontrollierbar und liefert vorher/nachher Requestzahlen; keine erfundenen absoluten Beschleunigungsziele. Optionaler manueller Livevergleich ist keylos, höchstens 90 s/80 Transportversuche, außerhalb von Tests.
Abbruch/Limit führt zu ausdrücklich zensierter beziehungsweise unvollständiger Messung. Wenige Proben liefern keinen belastbaren p95. Reale UI-Verbesserung wird nur anhand derselben Umgebung und Ansichtsgröße behauptet.

| Fall | Exakte Abnahme im kontrollierten Einzelhost-Harness |
|---|---|
| Fünf gleichzeitige Leser desselben kalten Jobs | genau 1 Detail-GET; 5 unabhängige Payloadkopien |
| Danach warmer Lookup innerhalb TTL | 0 zusätzliche Detail-GETs; unverändertes `observed_at` |
| Ein Wartender cancelt, ein anderer bleibt | weiterhin insgesamt 1 GET; verbleibender Leser erhält Antwort |
| Zwei unterschiedliche Clientscopes, gleiche Job-ID | genau 2 GETs, keine Vermischung |
| Frischegrenze nach altem Flightstart | genau 1 Folgeread für alle neuen Wartenden; keine alte WORK-Bestätigung |
| Terminaldetail an TTL-Grenze, mehrere Leser | nach erstem GET genau 1 zusätzlicher GET; gültige alte Retention bleibt |
| Fehler, Wiederholung vor/nach 15 s | 1 Versuch vorher, genau 1 neuer Versuch an/nach Grenze; keine Null/Erfolgsuhr |
| Neuer Hash/späte Submissionpublikation | eigener Identitätsschlüssel; erneuter fälliger Read innerhalb 4/2-Caps |
| Warmer Popupwechsel bzw. WORK-Auswahl | 0 zusätzliche HTTP-Requests und 0 Reader-Angebote |
| Seat mit 64 fälligen Membershipjobs, langsamen Earnings | frühe verifizierte RECORD-Antwort nach höchstens 4 priorisierten Membershipreads; nicht erst nach allen 64; insgesamt weiterhin ≤64 |
| Gesperrter Full-/Chain-Read, erfolgreicher ETH-Read | neuer ETH-Slot/korrekte Projektion sichtbar vor Freigabe des Full-Reads |
| Primärer exakter Pool liefert gültige Daten | 1 IMD-Dex-Request, 0 Gecko-Fallbacks; ETH/FP getrennt gezählt |
| Primärantwort leer/429, exakter Fallback gültig | genau 1 logischer Dex- und 1 logischer Gecko-Abruf; tatsächliche Attempts durch bestehende bzw. in P0 eingefrorene Retrygrenzen begrenzt; sonst Last-good |
| passive Hub-Reprojektion | 0 HTTP-Requests und 0 neue Historienpunkte |

Zusätzliche Pflichtfälle: falscher Pool/Chain/Token/erste Decoy-Beziehung, Quoteorientierung, Cap-null, Nullvolumen, NaN/Inf/bools, Identitätswechsel mit Pfeilreset, Cold-Start ohne Pool, ETH-Teilerfolg und ETH-Ausfall ohne Uhrsprung.
Concurrency-Prüfungen: A→B→A, verspäteter Publish, Dirty-Epoch, alle Wartenden abbrechen, wiederöffnen während Cancel, Close mit laufenden Reads, acht aktive Flights, LRU-/Bytegrenzen und übergroße vollständige WORK-Payload.
Ein eigener SITES-/Scores-Kompositionstest kombiniert warme Details mit frisch gelesenen übrigen Ressourcen: genau null zusätzliche Detailrequests innerhalb TTL, ursprüngliches Detaildatum bleibt erhalten, der erfolgreiche Tierzyklus bleibt trotzdem korrekt terminiert.
WORK-Prüfungen: alter aktiver Cache bei neuem Discoverystand, spätes Terminal→Active, fremdes Projekt/Workflow, fehlender Kontext, gekürzte Seite, widersprüchlicher Overview, Cancel ohne Teilpublikation.
TDD zuerst an diesen Fällen; bei Decodern und Concurrency Mutation-Proof über `scripts/mutate.py`. Bestehende Tests mit dauerhafter Terminal-Frische werden ausdrücklich auf endliche Revalidierung umgestellt.

## 9. Eigentum und Umsetzungsschranken

- P0/Vertragsfreeze vor Performancearbeit: messbare Ausgangszahlen, Fixtureidentitäten und oben genannte Interfaces im Plan festhalten.
- Ein zentraler Integrator besitzt `surf_manager.py`, `surf_cache.py`, `surf_models.py`, `data/surfboard.py` und die gemeinsame Clientverdrahtung; keine parallelen Änderungen dieser Dateien.
- Nach dessen Model-Seed dürfen Marktdecoder in `surf_client.py` und Detailmemo in `surf_swarm_client.py` parallel entstehen, jeweils mit eigenen Tests/Fixtures.
- Ein durch P0 begründeter gemeinsamer Gecko-Gate/Clientverdrahtung folgt als konditionales Paket sequenziell unter einem Eigentümer. Seat-Stufen und persistente Revalidierung folgen unter dem Integrator; WORK kann danach mit disjunkten Reader-/Fold-Dateien separat erfolgen.
- Komponierende Regressionen umfassen Surf, BOARDROOM, AGENT/RECORD, WORK und den bestehenden SITES-Detailverbraucher; keine bloße Client-Testfreigabe.
- Der Plan schätzt Produktionsumfang ehrlich; oberhalb etwa 1.000 Zeilen gelten Taskreviews pro Diff plus finale Review gemäß Tier 2. Kein Full-Suite-Gate ohne Nutzerauftrag/Tag.
- Änderungen am gemalten Dashboard werden vor Hardening/Review am echten keylosen Render gezeigt. Performancebefunde ohne reproduzierbare Zahl bleiben Folgearbeit; Korrektheitsfixes hängen nicht von einem Speedup ab.
- Nicht enthalten: weitere Anbieter, schnellere POOL4-Spot-TTL, neue Navigation, persistenter Detailindex und eigener Score-Scheduler. Jede Erweiterung benötigt einen konkreten gemessenen Bedarf.
