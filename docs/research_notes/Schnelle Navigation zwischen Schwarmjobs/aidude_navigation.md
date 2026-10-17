# aidude: performante Navigation zwischen Schwarmjobs

## 1. Welche Navigation existiert heute tatsächlich?

### Takeaway
aidude enthält wiederverwendbare Abruf- und Cachemuster, aber keinen fertigen schnellen Jobbrowser. `market` baut eine statische HTML-Seite; `hackathon-site` rendert bereits lokal gespeicherte Jobs und Submissions ohne Netzwerkabrufe. Der Wechsel zu einem Job öffnet einen externen API-Link, keinen integrierten Next/Previous-Detailviewer. [Market-Render](/Library/Vibes/aidude/tools/surf/_market_page.py:3325), [Joblinks](/Library/Vibes/aidude/tools/surf/_market_page.py:287), [Hackathon-Zweck](/Library/Vibes/aidude/tools/surf/_hackathon_site.py:2)

### Cited Findings

- **List → Detail → Nodes:** `_market_page.py` lädt `/jobs/{id}` einmal pro benötigtem Detailabruf; Nodes sind bereits darin enthalten. Es speichert maximal 30 Nodes mit nur `key`, `role`, `state`, außerdem zugeordnete Seats, Workflow-ID und `oracleRequestId`. Kein zusätzlicher Node-Request in diesem Pfad; `dependsOn` und andere DAG-Daten bleiben nicht erhalten. [Detailprojektion](/Library/Vibes/aidude/tools/surf/_market_page.py:1135)
- **Result und Submissions sind separate Ressourcen:** `/jobs/{id}/result` wird zu File-Anzahl, Bytes, Delivery und `complete` reduziert; `/jobs/{id}/submissions` zu Usage-/Verdict-Zeilen. Große Resultdateien werden hier nicht als Navigationsinhalt persistiert, Submission-Summaries explizit entfernt. [Result](/Library/Vibes/aidude/tools/surf/_market_page.py:1169), [Submissions](/Library/Vibes/aidude/tools/surf/_market_page.py:1180)
- **Workflow-Beziehungen lokal:** `contractsJobId` und `frontendJobId` bilden Dictionaries Job→Workflow. Ein Planner wird dagegen über den ersten Match des 200-Zeichen-Objective-Präfixes zugeordnet; das ist eine Heuristik, keine verifizierte Graphkante. Workflow-Details kommen über `/workflows/{id}`. [Mapping](/Library/Vibes/aidude/tools/surf/_market_page.py:1078), [Relationen](/Library/Vibes/aidude/tools/surf/_market_page.py:1276), [Workflowdetail](/Library/Vibes/aidude/tools/surf/_market_page.py:1202)
- **Jobketten als Daten verfügbar:** `_launch_watch.py` nutzt `detail.project.versions` mit `jobId`, sonst den aktuellen Job als Einzelliste. Ein per-Prozess-Memo vermeidet wiederholte Jobdetailabrufe einschließlich mehrfacher Fehlversuche auf dieselbe ID. Das ist ein nützlicher Ansatz für verwandte Jobs, noch keine UI-Navigation. [Projektversionen](/Library/Vibes/aidude/tools/surf/_launch_watch.py:412), [Memo](/Library/Vibes/aidude/tools/surf/_launch_watch.py:355)
- **Hackathon-Seite:** lokale Daten werden als Jobkarten mit Schritt-/Seat-/Verdict-/Modell-/Usage-Tabelle und `parentJobId`-abhängiger Kennzeichnung „Continuation“ gerendert. Die Browser-JavaScript-Interaktion filtert Todos; sie implementiert keine Jobdetail-Fetches oder Nachbarjob-Prefetches. [Karten](/Library/Vibes/aidude/tools/surf/_hackathon_site.py:777), [JS](/Library/Vibes/aidude/tools/surf/_hackathon_site.py:310)
- **`_swarm_watch.py` ist keine Navigationsvorlage:** seine Pools mit sechs bzw. acht Threads dienen unabhängigen Health-/Route-/Release-Probes. Das ist vorhandene Parallelität, aber keine parallelisierte Jobhydration. [Routeprobes](/Library/Vibes/aidude/tools/surf/_swarm_watch.py:159), [Orchestrierung](/Library/Vibes/aidude/tools/surf/_swarm_watch.py:482)

### Inferences

- Für MaxPane eignen sich `jobId`-Caches und explizite Workflow-/Projektbeziehungen als Grundlage für lokalen Wechsel zwischen bekannten Jobs. Eine vollständige Node-Grafik braucht eine eigene kompakte Projektion mit allen benötigten Kanten; aidudes 30-Node-Projektion reicht dafür nicht. [Nodeprojektion](/Library/Vibes/aidude/tools/surf/_market_page.py:1158), [Beziehungen](/Library/Vibes/aidude/tools/surf/_market_page.py:1276)

### Gaps

- Kein implementiertes integriertes Next/Previous-Jobdetail, kein selektionsgesteuerter Prefetch und keine Latenzmessung eines solchen aidude-Flows gefunden. Nicht als fertigen schnellen Browser darstellen.
- Kein `_market.py` vorhanden; der relevante aktuelle Code heißt `_market_page.py`. Die Alexandria-Suche nach aidude/surf/swarm/job/cursor lieferte keinen spezifischen Navigationsartikel.

## 2. Welche Performance- und Cachemuster lassen sich übernehmen?

### Takeaway
Übertragbar sind cursorbasiertes Nachladen, kompakte Projektionen und getrennte Detail-/Result-/Submission-Caches. aidudes blockierende Fetch- und Terminalregeln sollten dagegen nicht unverändert in eine interaktive Navigation übernommen werden. [Paging](/Library/Vibes/aidude/tools/surf/_market_page.py:927), [Caches](/Library/Vibes/aidude/tools/surf/_market_page.py:3227), [Transport](/Library/Vibes/aidude/tools/surf/_market_page.py:475)

### Cited Findings

- **Inkrementelle Listen:** `/jobs?limit=500`, weitere Seiten mit `before=letztes.createdAt`; warmer Durchlauf bis gespeicherter Newest-Cursor minus 60 s, kalter bis Zeitboden. Maximal 20 warme/120 kalte Seiten. Warme unvollständige Durchläufe verschieben den Cursor nicht; Lücken werden gespeichert und nach kontinuierlichem Nachlesen geheilt. Das schließt Neuankunftslücken, ist aber kein Feed von Änderungen alter Jobs. [Walk](/Library/Vibes/aidude/tools/surf/_market_page.py:927), [Cursor-/Gaplogik](/Library/Vibes/aidude/tools/surf/_market_page.py:995), [Heilung](/Library/Vibes/aidude/tools/surf/_market_page.py:1034)
- **Nicht alle Listen sind so robust:** Workflow-/Launch-Listen verwenden `fetch_small_list` mit genau einem Abruf ohne Pagingparameter; vorhandene Datensätze werden gemerged. Der aktuelle Code implementiert dort keine vollständige Workflow-Historienpagination. [Small list](/Library/Vibes/aidude/tools/surf/_market_page.py:1063)
- **Persistenz und Grenzen:** getrennte `objects.json`, `details.json`, `usage.json`, `seats.json`, atomisches Ersetzen; Listobjekte werden schlank gespeichert und alte unbezahlte Oracle-Jobs nach 48 h gefaltet. Die 8-MB-Grenze gilt für `objects.json`, nicht als genereller Deckel aller Detail-/Usage-Dateien. [Atomisches Schreiben](/Library/Vibes/aidude/tools/surf/_market_page.py:298), [Retention](/Library/Vibes/aidude/tools/surf/_market_page.py:1786), [Ceiling](/Library/Vibes/aidude/tools/surf/_market_page.py:1835), [Persistenz](/Library/Vibes/aidude/tools/surf/_market_page.py:3343)
- **Planmäßige erfolgreiche Detailkosten:** Für einen Durchlauf von `tier_paid_details` gilt ohne Retries `Q = D + R + S + W + O`: D = fehlende/nichtterminale Jobdetails, R = fehlende Results terminaler Jobs, S = fehlende Submissions terminaler Nicht-Research-Jobs, W = fehlende/nichtterminale bezahlte Workflows, O = nichtterminale bezahlte Oracle-Details. Neue terminale Nicht-Research-Jobs brauchen dabei höchstens 3 Requests/Job, fertig gecachte 0; Nodes kosten keinen Extraabruf. Andere Tiers, Listen und Join-Suche kommen zusätzlich hinzu. [Detailtier](/Library/Vibes/aidude/tools/surf/_market_page.py:1699)
- **Globale Abrufgrenzen:** Standard 300 API-Attempts/Run, mindestens 120 ms Abstand und höchstens 60/min; die Detailtiers laufen sequenziell. Transport ist blockierendes `urllib.request.urlopen` mit 25-s-Timeout; kein expliziter wiederverwendeter Connection-Pool, kein Async-Client, kein Request-Singleflight. [Budgets](/Library/Vibes/aidude/tools/surf/_market_page.py:56), [Pacing](/Library/Vibes/aidude/tools/surf/_market_page.py:451), [Transport](/Library/Vibes/aidude/tools/surf/_market_page.py:475), [Tierfolge](/Library/Vibes/aidude/tools/surf/_market_page.py:3318)
- **Fehlerbehandlung:** je logischem GET ein zusätzlicher 429-Attempt nach `Retry-After` (1–30 s), ein zusätzlicher 5xx-/Netzwerk-Attempt nach 1 s; bei gemischten Fehlern können beide Retryregeln greifen. Zweite 429 setzt einen Stop für weitere API-Arbeit dieses Runs. Normale 404-/5xx-Fehler haben keine persistente oder pro-Run-Negativcache-Zeile. [GET](/Library/Vibes/aidude/tools/surf/_market_page.py:505)
- **Doppelte Fehlerarbeit:** fehlgeschlagene Result-/Submission-Abrufe schreiben keinen Cacheeintrag. Deshalb kann nach `paid_details` der spätere `backfill` denselben fehlenden Endpunkt im selben Run erneut anfragen: beispielsweise 2 HTTP404-Requests oder 4 HTTP5xx-Requests bei je einem Retry. Dies ist aus den zwei Aufrufstellen abgeleitet, nicht live gemessen. [Fetchguards](/Library/Vibes/aidude/tools/surf/_market_page.py:1169), [Detailtier](/Library/Vibes/aidude/tools/surf/_market_page.py:1708), [Backfill](/Library/Vibes/aidude/tools/surf/_market_page.py:1761)
- **Besseres lokales Failure-Memo in launch-watch:** `_JOBS[id]=None` dedupliziert Fehlversuche innerhalb des Prozesses; `seen.pop(id)` erlaubt einen erneuten Versuch im nächsten Run. Übertragbar als kurzlebiger negativer Cache, nicht als dauerhaftes „existiert nicht“. [Memo](/Library/Vibes/aidude/tools/surf/_launch_watch.py:358), [Retry nächster Run](/Library/Vibes/aidude/tools/surf/_launch_watch.py:412)
- **Terminal ist hier zu aggressiv:** Ein Detail wird terminal, wenn State terminal ist oder `updatedAt` über sieben Tage zurückliegt. Ein terminaler Detailcache wird nicht gegen ein neueres Listen-`updatedAt` invalidiert. Jeder erfolgreiche Result-Dict wird gespeichert, auch `complete:false`/leere Files; erfolgreiche Submissions `[]` ebenfalls. Später prüfen die Tiers nur Schlüsselpräsenz. Spät veröffentlichte Ergebnisse oder ergänzte Attempts können damit dauerhaft fehlen. [Terminal](/Library/Vibes/aidude/tools/surf/_market_page.py:1163), [Result-/Usage-Schreiben](/Library/Vibes/aidude/tools/surf/_market_page.py:1169), [Presence-Guards](/Library/Vibes/aidude/tools/surf/_market_page.py:1699)

### Inferences

- Für MaxPane als **vorgeschlagenes Verhalten**: ausgewählten Job sofort aus gemeinsamen Caches anzeigen; dessen fehlende Details mit Priorität laden; Result/Submissions unabhängig nachladen; höchstens bekannte Nachbarjobs begrenzt vorladen. Dafür muss weder die gesamte Seat-Historie noch ein kompletter Scores-Sweep vorher fertig sein. aidudes getrennte Ressourcen/Caches unterstützen diese Aufteilung strukturell, implementieren die Priorisierung aber noch nicht. [Ressourcen](/Library/Vibes/aidude/tools/surf/_market_page.py:1135)
- Endgültigkeit pro Ressource behandeln: terminaler Job ist nicht automatisch fertiges Result oder vollständige Attemptliste. Incomplete/empty/unavailable kurz negativ cachen und erneut prüfen; erfolgreich abgeschlossene Inhalte länger cachen, bei verändertem `updatedAt` invalidieren. Das korrigiert die oben belegten Presence-only-Guards. [aktuelle Guards](/Library/Vibes/aidude/tools/surf/_market_page.py:1704)

### Gaps

- Kein Backend-Bulk-Detail-Endpunkt oder ETag-/If-Modified-Since-Verfahren in den geprüften aidude-Clients. Query-/Pagination-Semantik ist durch Code und datierte lokale API-Beobachtungen belegt; sie wurde hier nicht live neu geprüft. [GET-Header](/Library/Vibes/aidude/tools/surf/_market_page.py:475), [datierte API-Korrektur](/Library/Vibes/aidude/docs/imd-api-changelog.md:1139)

## 3. Was belegen die alten MaxPane-Messungen – und was nicht?

### Takeaway
Die Oktober-Reviewdaten zeigen die Kosten von breiten Detail-Sweeps und kompletter Seat-Hydration. Sie sind historische Messungen an MaxPane-Snapshots, keine heutigen aidude- oder MaxPane-Navigationsbenchmarks. [Review-Methode](/Library/Vibes/aidude/docs/superpowers/specs/2026-10-04-maxpane-surfboard-review/swarm-fetch.md:12)

### Cited Findings

- **Gesunder historischer swarm2-Run:** 105 `/jobs/{uuid}`-Requests, davon 100 im Scores-Sweep, Median 168 ms/Max 2112 ms; vier Seat-Requests zusammen 10,87 MB roh. Nur vier Joblisten-Requests. Die vermeidbare Arbeit lag in der breiten Hydration, nicht in den lokalen Job-IDs. [Routentabelle](/Library/Vibes/aidude/docs/superpowers/specs/2026-10-04-maxpane-surfboard-review/harness/r2/runs/swarm2.summary.md:49)
- **Alte RECORD-Hydration:** vier Submissions, vier Oracle-Details, zwei Jobdetails pro Seat-Zyklus; 40-Zeilen-Fenster mit 37 Jobs benötigte im Snapshot-Simulator zehn Zyklen/20 min, jedes Mal zuvor komplette Seat-Liste. Das ist eine alte Simulation, keine heutige Nutzerwartezeit. [Fan-outs](/Library/Vibes/aidude/docs/superpowers/specs/2026-10-04-maxpane-surfboard-review/swarm-fetch.md:136)
- **Alte unnötige Indexarbeit:** `oracleRequestId` stand bereits im Jobdetail sowie `oracleResult.requestId` in Submissions; trotzdem wurde ein globaler Oracle-Index nachgeladen. Aktuelles aidude speichert `oracleRequestId` unmittelbar im Detail und benutzt ihn bei Zuordnung. [historischer Nachweis](/Library/Vibes/aidude/docs/superpowers/specs/2026-10-04-maxpane-surfboard-review/swarm-model.md:261), [heutige Projektion](/Library/Vibes/aidude/tools/surf/_market_page.py:1156), [Zuordnung](/Library/Vibes/aidude/tools/surf/_market_page.py:1386)
- **Alte Listenlücke:** Review fand newest-100 ohne Pagination und veraltete executing-Zustände nach Bursts. Aktuelles aidude implementiert dagegen `limit=500`, Cursor-Overlap und Coverage/Gaps. Das verbessert Neuankunftsabdeckung; sein Terminalcacheproblem bleibt davon unabhängig. [Review](/Library/Vibes/aidude/docs/superpowers/specs/2026-10-04-maxpane-surfboard-review/swarm-fetch.md:211), [heutiger Walk](/Library/Vibes/aidude/tools/surf/_market_page.py:927)

### Inferences

- Den heutigen MaxPane-Engpass als separate Messung behandeln: Zeit bis gecachter Job sichtbar, Zeit bis ausgewähltes Detail vollständig, zusätzliche Requests pro Jobwechsel und doppelte Requests je Job-ID. Nicht den gesamten Batch-Run oder fremde Providerlatenz als Navigationslatenz ausgeben. Die historischen Routen liefern dafür konkrete Verdachtsstellen, keine aktuelle Diagnose. [historische Routen](/Library/Vibes/aidude/docs/superpowers/specs/2026-10-04-maxpane-surfboard-review/harness/r2/runs/swarm2.summary.md:49)

### Gaps

- Keine Anwendung geändert oder gestartet, keine Runtime-Joboutputs/Secrets gelesen, keine Runner-/Signing-/Payment-/Submission-Pfade ausgeführt. Keine frischen Netzwerkbenchmarks. Aktuelle MaxPane-Integration wird vom zuständigen Architektur-Agenten getrennt untersucht.
