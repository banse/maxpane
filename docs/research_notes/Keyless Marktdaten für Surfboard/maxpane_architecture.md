# MaxPane: keyless Marktdaten, tatsächlicher Ladepfad und KISS-Optionen

## 1. Welche Ansichten und Werte hängen heute von welchen Quellen ab?

### Takeaway

`--game surfboard` (Dashboard 9) ist die sichtbar als **IMD BOARDROOM** betitelte Hub-Ansicht. Surf `b` ist eine andere Ansicht für aufgezeichnete Seats und Fleet; sie besitzt keine eigene DEX-Marktdatenquelle. Die primären IMD-Preise werden bereits onchain berechnet, und Dashboard 9 gibt Cache-Daten ohne Warten auf den vollen Refresh zurück. Ein pauschaler DexScreener-Ersatz ist daher keine belegte Lösung des Ladeproblems. [Dashboard-Titel](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surfboard.py:103), [Board-Modus](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surf.py:2079), [Board-Hero](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/swarm_board_hero.py:26), [Hub-Refresh](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7742)

### Cited Findings

| Oberfläche | Marktwerte / Bedeutung | Quelle und Beleg |
|---|---|---|
| BOARDROOM POOL4-Karte | `pool4_price_usd`, aufeinanderfolgende Preisrichtung, sIMD/IMD-Anteilspreis; Tooltip zusätzlich `imd_change_24h_pct` | Preis aus **CappedBurnHook-Pool** `current_tick` plus ETH/USD; Anteilspreis aus Vault; 24h-Änderung aus separat erhobenem IMD-Referenzmarkt. [Karte](/Users/banse/codex/maxpane/maxpane_dashboard/data/surfboard.py:569), [Tick-Konversion](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:5036) |
| BOARDROOM Footer | IMD Market Cap, ersatzweise ausdrücklich als FDV markiert; Inference-Tokenzahl getrennt | `SLOT_MARKET` Cap/FDV vom verifizierten DexScreener-Pool; Netzwerkzähler aus Overview mit eigener Uhr. [Projektion](/Users/banse/codex/maxpane/maxpane_dashboard/data/surfboard.py:316), [Anzeige](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surfboard/terminal.py:328) |
| BOARDROOM TOKENS-Karte | Tokenanzahl, neue Launches, Ranking mit Preisrichtung, Volumen-Sparkline | Gemeinsamer `SwarmTokensManager`: Launch-Katalog; ausgewählte Pool-Marktwerte via DexScreener; Gecko-OHLCV. Volumenchart summiert acht abgeschlossene 3h-Gruppen über einen festen Pool-Kohortensatz; fehlende Stunden bleiben Lücken. [Karte](/Users/banse/codex/maxpane/maxpane_dashboard/data/surfboard.py:626), [Summary](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:333), [Volumenfold](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:422) |
| Surf IMD MARKET / News-Hero | IMD USD, 24h-Änderung und -Volumen, Pool-Liquidität, FP USD/Parität, Supply/Preisverlauf | Primär `sqrtPriceX96` des hooklosen IMD-v4-Referenzpools × ETH/USD; temporärer Indexer-Preisfallback, falls Onchain-Preis fehlt. 24h/Volumen/Liquidität aus Indexer. [Preiswahl](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:8164), [Widget-Vertrag](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/market.py:811), [Hero](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/news_hero.py:121) |
| Tokenübersicht / Tokendetail | Preis, Cap, FDV getrennt, 24h-%/USD-Volumen, Buy/Sell-Zähler, stündlicher Preisverlauf, Trades | Ausgewählter Pool: DexScreener; Gecko OHLCV und Trades. Eigene ursprüngliche Launch-Position/Liquiditätsklassifikation kommt aus Onchain-Evidence, nicht Indexer-TVL. [Primitive Keys](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_models.py:8), [Detail-Hinweis](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/swarm_token_detail/__init__.py:82), [Client](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_market.py:1) |
| Surf `b` BOARD | Top Seat, Recorded, Accept Rate, Launches, Workers, Effort | Swarm-/Seat-/Launch-Contribution-Daten; kein eigener DEX-Abruf. [Hero](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/swarm_board_hero.py:26), [Leaderboard](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/swarm_leaderboard.py:68) |

- `SurfClient.fetch_market` startet gleichzeitig **vier** GETs: DexScreener legacy IMD, Gecko IMD-Token mit `include=top_pools`, DexScreener legacy FP/Base, CoinGecko ETH/USD. Der Snapshot entsteht erst nach allen Antworten. Bei fehlendem IMD-Paar **und** fehlendem Gecko-Preis wird der gesamte Snapshot verworfen, auch wenn ETH/USD erfolgreich war. [Fetch](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:2876)
- DexScreener-IMD wird nach `pairAddress == real_pool_id` ausgewählt, nicht nach Liquidität. Gecko dagegen liest Token-Preis und `included[0].attributes`, ohne denselben Pool zu prüfen; diese ungeprüften Poolwerte liefern bei fehlendem DS-Paar 24h-%/Volumen/Liquidität. Cap/FDV bleiben DS-only. [Identität](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:2832), [Fallback](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:2902), [Felder](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:2932)
- Onchain-Hauptpreis ist schon vorhanden: `fetch_pool_v4` liest per Multicall die v4-Storagewerte, die Hauptprojektion bevorzugt daraus `chain_price_usd`; Pool4 verwendet seinen eigenen Tick. Diese Daten gehören verschiedenen Pools. [Storage-Lesen](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:1730), [Hauptpreis](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:8167), [Pool4](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:5040)
- Echte öffentliche Targets: Ethereum IMD `0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7`; hookloser v4-Referenzpool `0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3`; Base FP `0xff0c532fdb8cd566ae169c1cb157ff2bdc83e105`. Referenzpool-ID ist produktiv über `LaunchpadHook.imdEthPoolId()` zu lesen, der konstante Wert ist nur Fallback. Nicht PoolManager-Adresse oder Hook-Adresse mit einer v4-Pool-ID verwechseln. [Adressen](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_addresses.py:38), [Pool-ID](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_addresses.py:71), [FP](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_addresses.py:121)
- Zwei repräsentative Ethereum-Launch-Token aus echten committed Captures: ZTO `0xd782bdea4ef02a0bd391eb9089470c8080f0a68e`, FREE1376 `0x4543e6b511a9a7a75b56607e27997c987ea05878`. Beide wurden im aktuellen Probe-Lauf von DS gefunden. Pool4-Capture vom 2026-09-02 nennt separat Hook `0xc6c965bd164c483e87d0b550671798e9a3602840` und Pool-ID `0x415829f72e9f54531c26eae76f107618540e898a45d6ae35959e143f5faca704`; diese Pool4-Identität wurde nicht frisch onchain nachgelesen. [ZTO-Capture](/Users/banse/codex/maxpane/tests/fixtures/surf/swarm/v8/launch_737.json), [FREE-Capture](/Users/banse/codex/maxpane/tests/fixtures/surf/swarm/v9/launch_775.json), [Pool4-Capture](/Users/banse/codex/maxpane/tests/fixtures/surf/pool4/mainnet_hook_state.json), [Live-Probe](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json)

### Inferences

- Auf BOARDROOM wird der DEX-Wechsel hauptsächlich Footer- und 24h-/Rankingdaten verändern. POOL4-Preis und sIMD-Anteilspreis sollten ihre vorhandenen Onchain-Quellen behalten. Für den aktuellen POOL4-Tooltip muss die fachliche Bedeutung der Referenzmarkt-24h-Änderung separat festgehalten werden; das ist keine gemessene 24h-Rendite des Pool4-Pools.
- Ein aktueller Poolzustand liefert Preisverhältnis, Tick und positionsbezogene Größen, aber keine vollständige vergangene 24h-Handelsmenge, historischen Trade-Liste oder rollierende Preisänderung. Dafür braucht es gespeicherte Beobachtungen beziehungsweise vollständige Swap-Logs/Indexer. Kein neuer Vollhistorien-Indexer allein für einen schnelleren Screen.
- Ein Fallback darf Quelle wechseln, aber nicht einzelne Felder aus verschiedenen Pools oder Zeitfenstern zu einem scheinbar gemeinsamen Pool-Snapshot zusammenbauen. Cap, FDV und originale Launch-Position bleiben unterschiedliche fachliche Größen.

### Gaps

- Kein frisches Onchain-Ground-Truth-Sample für die exakte Börsenpreis-/Reserve-/Supply-Differenz; der Benchmark bestätigt API-Abdeckung, nicht korrekte Marktpreise. Die Pool4-Markt-API-Abdeckung wurde nicht zusätzlich abgefragt.
- Keine Behauptung, dass alle sichtbaren Verzögerungen von Marktquellen kommen: Swarm-/Oracle-/Seat-/Logpfade sind eigene Domänen.

## 2. Was blockiert heute, und was zeigen offizielle API-Dokumentation und kleine Messung?

### Takeaway

Das Risiko liegt in gemeinsamem Refresh und verschiedenen Datenaltern, nicht in einem bewiesenen generell langsamen DexScreener. BOARDROOM hat bereits Cache-first-Verhalten; der vollständige Surf-Zyklus wartet dagegen auf mehrere Familien. Im kleinen aktuellen Probe-Lauf antworteten alle 41 GETs mit HTTP 200, aber HTTP-Erfolg bedeutete weder Feldabdeckung noch Übereinstimmung. [Hub](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7742), [Full-Zyklus](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7934), [Probe](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json), [Gather-Probe](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_gather_results.json)

### Cited Findings

**Ladepfad und Limits im Code**

- `fetch_hub_snapshot()` startet vorhandene Aufgaben und projiziert Cache-Daten synchron; `get_hub_snapshot()` startet gar keine Netzwerkarbeit. Der Screen holt bei laufender Ladeanzeige sekündlich passiv die abgeschlossenen Cache-Schreibvorgänge ab. [Manager](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7742), [passiv](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7684), [Screen](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surfboard.py:138)
- Der gemeinsame vollständige Zyklus macht zuerst `await _pool_chain`, danach `gather(market, logs, channel, nft, activity)`; `fetch_and_compute` wartet mit `shield` auf den geteilten Full-Task. `_offer_full` erlaubt nur einen laufenden Task und begrenzt Neustarts auf den Poll-Abstand. Lange Launchpad-/Pool4-/Swarm-Tiers laufen separat als Tasks; deren Resultate werden aus Cache-Snapshots projiziert. [Chain/Gather](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7929), [Gather](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:8051), [Single-flight](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7755), [Await](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7792)
- Markt-TTL ist 90 s, Slow 420 s, Launchpad und Pool4 je 600 s; Markt-Fehlerbackoff 60 s. Last-good wird pro Slot gespeichert. Main-REST hat 15-s-httpx-Timeout, zwei Versuche, zwischen ihnen 0,5 s Backoff sowie 0,12-s-Pacing über `_last_rpc_at`. Das ist kein harter Gesamtdurchlauf-Timeout; httpx-Timeouts gelten für Phasen. Es gibt dort keine per-Host-Lock/Semaphore wie im Tokens-Gecko-Client. [Tiers](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_cache.py:139), [Slot](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:1456), [REST](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:1447), [Konstanten](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_client.py:148), [Pacing](/Users/banse/codex/maxpane/maxpane_dashboard/data/rpc_common.py:124)
- Tokenmärkte sind **bereits gebatcht**: `/tokens/v1/{chain}/{addresses}`, bis 30 Adressen, Chain-/Base-Token-/Pool-ID-Validierung, deterministische Auswahl nur wenn kein `launch_pool` vorgegeben ist. Chain-Batches laufen sequenziell. Ein vorhandener `launch_pool` darf nicht zugunsten eines anderen tiefen Pools verworfen werden. [Client](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_market.py:64)
- Token-Markt-TTL 120 s, History 900 s, Trades 120 s; Catalogue 300 s; ein refreshender Task pro Family. Pro Runde maximal 30 Markt-Token, zwei History-/Trade-Token, zehn Hub-Volume-Token. Detailabrufe pro Family sind sequenziell; History/Trades/Volume teilen einen Gecko-Lock mit 2,1 s Mindestabstand zwischen Starts. Diese Drosselung zählt nur diesen Client, nicht den separaten `SurfClient`-Gecko-Abruf. [TTL/Budgets](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:53), [Tasks](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:88), [Details](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:267), [Scheduling](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:473), [Lock](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_market.py:42)

**Offizielle Dokumente, geprüft am 17.10.2026 lokal**

| Quelle | Keyless-Funktion und Grenze | Ergebnis für MaxPane |
|---|---|---|
| DexScreener | `/tokens/v1/{chain}/{addresses}` bis 30 Token; `/token-pairs/v1/{chain}/{token}`; `/latest/dex/pairs/{chain}/{pairId}` für einzelne/mehrere Pools, jeweils 300 Requests/min laut Referenz | Batch schon implementiert. Bei festem Pool ist gezielter Pair-Abruf fachlich enger als Token-Aggregation. Kein unbestätigtes „30 Pools“-Limit aus dem 30-Token-Limit ableiten. [Offizielle Referenz](https://docs.dexscreener.com/api/reference) |
| GeckoTerminal | Public-API ist keyless im Probe-Lauf. Offizieller Support vom 02.10.2026 nennt 30 Calls/min; die eigene Landingpage nennt weiterhin 10/min | Dokumentationswiderspruch ausdrücklich offen; konservativer Probe-Abstand 6,2 s. `/networks/eth/pools/{bytes32}` und Token-Pools funktionieren für die Targets, Cap kann fehlen. [Support](https://support.coingecko.com/articles/6867086195-does-geckoterminal-have-an-api), [Landingpage](https://www.geckoterminal.com/dex-api), [Public API](https://api.geckoterminal.com/docs/index.html) |
| DefiLlama | Keyless Current-/Historical-/Chart-/Percentage-Coin-Preise, mehrere `chain:address` in einem Request | `coins.llama.fi/prices/current/...` live bestätigt; die aktuelle LLM-Doku schreibt generisch `api.llama.fi`, daher Host nicht blind aus dieser Tabelle übernehmen. Keine ausgewählten Poolvolumen-/Reserve-/BuySell-Felder im Coin-Preis-Antwortschema. [Offizielle freie Referenz](https://api-docs.defillama.com/llms-free.txt), [Live-Probe](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json) |
| DexPaprika | **Ohne Key** 15 Requests/min und 10.000 Credits/IP in rollierenden 30 Tagen; Batchpreise bis 10 Token kosten weiter pro Token. Keyless Pool-OHLCV 1h+ und letzte 24h; Pool-Transactions und Token-OHLCV paid-only | Nur gezielter Zusatzkandidat. Das aus Baseboard bekannte Token-Endpoint liefert tokenweite Zusammenfassungen; nicht als Ersatz ausgewählter Poolwerte einsetzen. Alte „kostenlos/unlimitiert“-Aussagen nicht übernehmen. [Offizielle Limits](https://docs.dexpaprika.com/knowledge-base/rate-limits), [Dokumentationsindex](https://docs.dexpaprika.com/llms.txt) |

**Reproduzierbare Messung**

- Manuelles Research, keine Tests und kein App-Start: `market_probe.py` macht 11 Endpointvarianten × 3 Requests = 33 GETs, null Retry; `market_gather_probe.py` macht zwei parallele Vierergruppen = 8 GETs. Ausschließlich öffentliche Markt-GETs; keinerlei Keys, Signatur, Zahlung oder App-Cache-Schreibzugriff. Die Shell-Sandbox hatte zunächst DNS-Fehler; der genehmigte reine Netzwerkprobe-Lauf funktionierte. [Script](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe.py), [Gather-Script](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_gather_probe.py)
- Hauptprobe: **2026-10-16 22:20:20–22:21:33 UTC**, entsprechend **17.10.2026 00:20:20–00:21:33 Europe/Berlin**. macOS 26.6.2 arm64, Python 3.13.12, httpx 0.28.1, HTTP/1.1, `trust_env=False`, 12-s-Timeout, keine Redirects/Retry. Pro Endpoint neuer Client: erster Request „cold“, folgende zwei gleicher Client „warm“. OS-DNS/CDN-Caches unkontrolliert; tatsächlich offene Serververbindung nicht getraced. [Ergebnis-Metadaten](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json)

| Endpoint / Target | Cold ms (n=1) | Warm-Median ms (n=2) | Semantische Abdeckung der Antworten |
|---|---:|---:|---|
| DS legacy IMD token | 273.18 | 26.79 | Verifizierter Referenzpool enthalten; Preis, Cap, FDV, Volumen, Change, Liquidität, Buy/Sell |
| DS batch IMD token | 216.91 | 33.00 | Referenzpool enthalten; dieselbe Feldfamilie |
| DS exakter IMD-Pool | 189.25 | 42.55 | Referenzpool enthalten; dieselbe Feldfamilie |
| Gecko exakter IMD-Pool | 286.62 | 69.20 | Preis/FDV/Volumen/Change/Reserve/BuySell; Cap null |
| Gecko IMD token/pools | 410.33 | 128.66 | Mehrere Pools; gezielte Auswahl erforderlich |
| Llama IMD + ETH | 216.13 | 24.09 | Beide Preise, Symbol/Confidence/Quellenzeit; keine Poolmetriken |
| Paprika IMD token | 452.17 | 150.70 | Tokenweite Zusammenfassung, 757 Pools; kein ausgewählter Referenzpool im Payload |
| DS ZTO + FREE1376 Batch | 220.67 | 22.07 | Beide Token mit Poolmarkt-Feldern vorhanden |
| Gecko ZTO token/pools | 652.63 | 66.92 | ZTO-Pool vorhanden, Cap null, erhebliche Preisabweichung |
| Paprika ZTO token | 321.68 | 148.40 | Tokenweite Zusammenfassung, 23 Pools |
| Llama ZTO + FREE1376 | 235.93 | 23.53 | HTTP 200, aber `coins: {}`: beide ohne Preisabdeckung |

Alle Zahlen und die normalisierten Antwortfelder stammen aus [market_probe_results.json](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json). **Keine Rangfolge allgemeiner Anbieterqualität aus n=3.** DS legacy Antwort 32.280 Bytes, Batch 1.503 Bytes, exakter Pair-Abruf 3.046 Bytes im ersten Sample; der kleine Payload ist ein konkreter Effizienzvorteil, kein bewiesener großer UI-Speedup. [Messdaten](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json)

- Rohes paralleles Vierer-Gather mit denselben URLs wie `fetch_market`: 22:22:06 UTC cold **328.27 ms**, langsamster FP/DS **324.20 ms**; 22:22:13 UTC warm **262.47 ms**, langsamster IMD/DS **262.01 ms**. Je vier HTTP 200. Kein produktives 120-ms-Pacing/Retry, keine vorgelagerte Chain-Runde, keine konkurrierenden Log-/NFT-Aufgaben, keine UI-/Renderzeit enthalten. [Gather-Rohdaten](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_gather_results.json)
- **Frische ist etwas anderes:** Llama lieferte IMD mit Quellzeit **1.685 s** vor Request (~28,1 min), ETH **55 s** vorher. Paprika IMD `last_updated` 22:19:30 bei Abruf 22:20:54. DS und Gecko haben HTTP-Cache-/Date-Header, aber keine eindeutige Marktbeobachtungszeit im erfassten Poolpayload. `Date`, `pairCreatedAt`, `pool_created_at`, Cache-Max-Age und Abrufzeit beweisen keinen aktuellen Preisblock. [Rohdaten](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json)
- **Übereinstimmung ist nochmals separat:** gleicher IMD-Pool DS 5,37 USD / FDV 22,44 Mio. / Cap 22,45 Mio.; Gecko 5,4228 USD / FDV 17,03 Mio. / Cap null. Gleicher ZTO-Pool `0x888b07bd282f587d3c6b0fcb23e7fc55bbb33abe8910dd7492db815dc8dc5592`: DS 0,00007841 USD, Gecko 0,00020686 USD (~2,64×). Gecko und Paprika behalten IMD-Namen VIBE. Ursachen von Preis-/FDV-Differenzen **nicht bewiesen**: Zeitversatz, Methodik, Quote-Konversion, Supply-Version oder andere Verarbeitung kommen infrage. Nicht zu einem Mittelwert mischen. [Rohdaten](/Users/banse/codex/maxpane/docs/research_notes/Keyless%20Marktdaten%20für%20Surfboard/market_probe_results.json)

### Inferences

- Es gibt in diesen Samples keinen Beleg, dass ein neuer Anbieter einen langsamen Screen zuverlässig beschleunigt. Schon der Roh-Gather liegt unter 0,4 s, während Markt-TTL 90 s und Onchain-Pool-TTL 600 s betragen; diese messen verschiedene Dinge.
- Die größte konkret nachgewiesene semantische Lücke ist der ungeprüfte Gecko-Top-Pool-Fallback. Die höchste begründete Entkopplungspriorität ist ETH/USD, das zurzeit an den Erfolg des gesamten IMD-Markt-Snapshots gekoppelt ist und mehrere Onchain-USD-Projektionen speist.
- Ein zehnteiliger Gecko-Volume-Durchlauf braucht allein wegen 2,1-s-Startabständen mindestens ca. 18,9 s zwischen erstem und letztem Start, plus Netzwerkzeit; andere Gecko-Familien teilen dieselbe Drosselung. Das blockiert nicht den Eventloop oder initialen Hub-Paint, aber verlängert die Zeit bis alle Karten Daten haben. Dies ist eine Ableitung aus dem Scheduler, keine gemessene UI-Zeit.
- Rate-Limit-Budget über beide MaxPane-Gecko-Clients hinweg zu betrachten ist sinnvoll. Kein schnelleres Parallelisieren mit unbegrenztem `gather`; das wäre keine KISS-Verbesserung.

### Gaps

- Kein End-to-end-Profil der produktiven App und kein Zeitstempel „erste brauchbare Karte vollständig“. Kein belastbares p95/p99 und keine Ausfallquote über längere Zeit; die aktuelle Stichprobe enthält keine Fehler.
- Gecko 10-vs-30/min bleibt widersprüchlich. Keine Langzeitgarantie für irgendeinen keyless Anbieter oder Robinhood-Abdeckung aus diesem Ethereum-Probe-Lauf.

## 3. Welche KISS-Architektur und Arbeitspakete folgen daraus?

### Takeaway

Empfohlen ist **Option A: bestehende Quellen und Cache-Grenzen gezielt verbessern**, zuerst korrekte Poolidentität und unabhängige ETH/USD-Versorgung. **Option B: ein kleiner gemeinsamer Marktdatenadapter mit genau einem gezielten Poolfallback** wird erst sinnvoll, wenn reale Ausfälle beziehungsweise zusätzliche Feldabdeckung seinen Aufwand rechtfertigen. Dies ist ein Vorschlag, kein implementierter oder bereits akzeptierter Architekturentscheid.

### Cited Findings

- Bestehende Schichten sind Client → Cache → Manager → Screen → rendernde Widgets. Die Tokenstrecke besitzt bereits Source-/Read-Zeit-/Poolidentität sowie Last-good/Scheduling; ein neuer Microservice, Framework oder allgemeiner Provider-Router wäre nicht erforderlich. [Projektarchitektur](/Users/banse/codex/maxpane/CLAUDE.md:75), [Token-Vertrag](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_models.py:16), [Identity-baseline](/Users/banse/codex/maxpane/maxpane_dashboard/data/swarm_tokens_manager.py:234)
- Sichtbare stale/unavailable/source-failure-Hinweise wurden am 16.10.2026 für Surf, BOARDROOM und Tokenseiten ausdrücklich entfernt. Interne Fehler-/TTL-/Last-good-Informationen bleiben; Anzeige fehlender Werte neutral. Daher keinen neuen „stale“-Banner oder Status-Overhaul in dieses Marktdatenvorhaben einschmuggeln. [Aktuelle Regel](/Users/banse/codex/maxpane/.claude/rules/surf.md:13)
- Neue gemeinsame Data-/Contract-Flächen oder >1 Dashboard führen bei Umsetzung zu Tier 2. Offline-Fixtures und kein Netzwerk in Tests sind zwingend; diese Research-Notiz führt keinen Implementierungs-/Review-Pipeline-Schritt aus. [Triage](/Users/banse/codex/maxpane/CLAUDE.md:25), [Read-only/Keyless/Tests](/Users/banse/codex/maxpane/CLAUDE.md:11)

### Inferences

| Option | Konkrete Entscheidung | Nutzen | Preis / Grenze |
|---|---|---|---|
| **A, empfohlen** | DexScreener für ausgewählte Poolmetriken behalten; Gecko weiter für History/Trades. Fallback immer exakt chain+token+pool prüfen. ETH/USD als unabhängigen kleinen Slot anbieten/publizieren. Bekannten IMD-Pool gezielt abrufen; bestehende Token-Batches behalten. | Kleine, reversible Änderungen; weniger Payload und weniger Kopplung; keine neue Aggregationssemantik. | Kein vollständiger Ausfallschutz vor DS; Provider-Limits und History-Wartezeit bleiben. Der gemessene Speedup ist noch offen. |
| **B, ergänzend** | Kleiner gemeinsamer `MarketRead`-Vertrag im Data-Layer: chain, token, pool, source, read_at, provider_at/block wenn verfügbar, fields, coverage. DS primär; exakt gleicher Gecko-Pool nur nach echter Primärlücke oder in langsamer Kontrollrunde. Quote-Referenz separat. | Konsistente Provenienz und Quellenbudget über Surf/Tokenansichten, selektiver Fallback. | Zusätzliche Adapter/Fixture-Matrix; Gecko hat für Targets Cap-Lücken und belegte Wertabweichungen. Kein „schnellster HTTP-200 gewinnt“. |

**Option A in Reihenfolge:**

1. Bestehende Marktwerte fachlich festziehen: Referenzpool versus CappedBurnHook-Pool, Price/Change-Basis, Cap versus FDV. Gecko-Fallback auf den erwarteten Pool und Token normalisieren; fehlendes erwartetes Paar bleibt intern unknown/unindexed. Keine Umdeutung eines Aggregat-Tokenvolumens in Poolvolumen.
2. ETH/USD unabhängig aus erfolgreicher Antwort speichern und nutzen, selbst bei IMD-Indexer-Ausfall. Vorhandenen CoinGecko-Endpunkt behalten; Llama höchstens als kleiner optionaler ETH-Fallback mit eigener Zeitprüfung, nicht als IMD-Markt-Ersatz. Hier ist zusätzlicher Quellcode erst nach wiederholtem Ausfallbedarf gerechtfertigt.
3. Marktrefresh mit eigener Single-flight-Task/TTL bedienen und auf neue Slots projizieren, soweit der Full-Surf-Zyklus sonst darauf wartet. Das bereits existierende sofortige Hub-Cache-Rendering behalten. Keine Netzwerk-I/O im Widget, kein zweiter Manager für dieselbe Datenfamilie.
4. Bekannte Pool-ID für gezielten DS-Pair-Abruf nutzen; nicht annehmen, dass ein Token-Batch jede gewünschte Nebenpool-Variante zurückgibt. FP bleibt andere Chain, also kein gemeinsamer Ethereum-Batch. Vorhandene 30er-Batches der Launch-Token nicht neu implementieren.
5. Noch kleinere Ad-hoc-Messung im realen Refresh für `request_started/finished`, erfolgreiche Quelle, Quellzeit/-block, Slot-Publish und erste datenhaltige Projektion. Erst danach Onchain-Spot-Sweep von 600-s-Discovery/History-Tier lösen, falls die beobachtete Preisaktualität das Problem ist. Dies wäre Feldfrische, nicht REST-Latenz.

**Onchain-Abgrenzung:** Ein enger, wiederverwendeter Multicall für validierte Pools kann Spot/Positionen unabhängig von einem Indexer liefern. PoolKey, Currency-Reihenfolge, ERC20-Decimals, native ETH und Quote-Pfad müssen explizit sein; aus anderen Projekten keine WETH-/18-Decimals-/fixe-Supply-Annahmen übernehmen. Hook-Ökonomie kann die Interpretation des Spotpreises begrenzen. Volumen/24h-Änderung/Trades bleiben Indexer- oder Eventhistorien-Arbeit; kein Block-für-Block-Vollscan. Die bestehende lokale Onchain-Strecke ist zuerst wiederzuverwenden.

**Disjunkte Arbeitspakete für eine spätere Umsetzung (Vorschlag):**

| Paket / Zuständigkeit | Eigentum | Abhängigkeit / Prüfkriterium |
|---|---|---|
| WP0 Semantik + kleine Messung | Spezifikation/ADR in `docs/`, nur Research-Harness | Zuerst: Ansichten, Poolidentitäten, Quellenzeit, Akzeptanzmetriken festhalten. Keine Behauptung eines p95-Gewinns vor Messung. |
| WP1 Adapter/Normalisierung | `data/swarm_tokens_market.py`, ggf. enges neues Data-Helpermodul, eigene Adaptertests/Fixtures | Nach WP0. Falsche Chain/Token/Pool-ID, leere 200, Cap-null, 429 und widersprüchliche Werte offline abdecken; keine Testnetzwerknutzung. |
| WP2 Quote-/Surf-Transport | `data/surf_client.py`, eigene Clienttests/Fixtures | Nach WP0, parallel WP1 nur bei klar getrennten Dateien. ETH-Teilerfolg darf nicht verschwinden; gezielter Poolread und no-decoy-Fälle prüfen. |
| WP3 Integration/Slots/Contract, ein Owner | `data/surf_manager.py`, `data/surf_cache.py`, `data/surf_models.py`; zugehörige Manager-/Composing-Tests | Nach WP1+WP2. Ein gemeinsamer Task; Timeouts/Fallback dürfen gesunde Teilfamilien nicht sperren; korrekte Read-Zeit; Close/Cancel; Hub bleibt sofortiger Cache-Paint. |
| WP4 UI nur falls fachlich notwendig | konkret betroffene Widget-/Screen-Dateien und deren Composing-Tests | Nach WP3. Keine neuen Layout-/Statusänderungen als Nebenarbeit. Falls Source-/Venue-Bedeutung anders sichtbar werden muss, separat spezifizieren und live rendern nach Projektregeln. |

TDD für tatsächliche Features/Bugfixes; zunächst fehlschlagende fixturebasierte Fälle, danach minimale Umsetzung. Kein pauschaler Full-Suite-Lauf für dieses Research. Das übergreifende Vorhaben ist Tier 2; ein isolierter ≤2-Dateien-Poolmatch-Fix kann anhand des endgültigen Diffs niedriger eingestuft werden, sofern kein Tier-2-Trigger berührt wird.

### Gaps

- Aufwand/Dateizahl und endgültiger Payload-Vertrag noch nicht festgelegt; die Pakete sind abgrenzbare Verantwortungen, keine genehmigte Implementierungsplanung.
- Ob ein geteilter Provideradapter besser ist als zwei sehr kleine vorhandene Clients, entscheidet erst die konkrete gemeinsame Funktion. KISS spricht gegen eine universelle Provider-Plattform ohne mindestens zwei tatsächliche Nutzer derselben Regel.
