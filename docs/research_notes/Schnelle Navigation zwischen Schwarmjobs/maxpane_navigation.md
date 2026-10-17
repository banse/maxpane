# MaxPane: Jobnavigation und gezielte Swarm-Hydration

Stand: 17.10.2026, aktuelle lokale Quellen; reine Recherche. Ergänzt die Marktdatenanalyse, ersetzt sie nicht. `surfboard` ist IMD BOARDROOM; Surf `b` ist das separate Seat-BOARD. „Navigation“ wird hier sowohl als interaktiver Wechsel als auch als Traversieren zusammenhängender Jobdaten untersucht.

## 1. Was geschieht heute beim Wechsel zum Job?

### Takeaway

Warme Jobauswahl ist überwiegend bereits lokal. Der belegte Ansatzpunkt ist die erstmalige beziehungsweise fällige Hydration eines ausgewählten Seats und gemeinsam benötigter Jobs, nicht ein HTTP-Abruf bei jedem Klick. aidude liefert Datenmuster, keinen fertigen interaktiven Next/Previous-Browser. [Popup-Handler](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surf.py:4560), [WORK-Auswahl](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/work.py:401), [aidude-Vergleich](</Users/banse/codex/maxpane/docs/research_notes/Schnelle Navigation zwischen Schwarmjobs/aidude_navigation.md>)

### Cited Findings

| Pfad | Tatsächliches Verhalten | Quelle |
|---|---|---|
| BOARD → Seat → AGENT | Ausgewählten Seat setzen, RECORD-Filter/Fenster zurücksetzen, AGENT-Modus und Refresh starten. Der Eventhandler wartet nicht selbst auf HTTP. | [Auswahl](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surf.py:4173), [Seatwechsel](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surf.py:4196), [Manager](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6208) |
| AGENT RECORD → Submission/Oracle-Antwort | Aktuelle Zeile anhand **Job-ID plus Submission-Hash** suchen, validieren und als Snapshot im Modal öffnen. Kein Abruf im Öffnungspfad. | [Handler](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surf.py:4560), [RECORD-Aktion](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/swarm_seat_record.py:418) |
| Popup → Nodes/Antwort | Bereits enthaltene Node-/Reply-/Other-Seats-Daten rendern; `deepcopy(row)` schützt die ausgewählte Momentaufnahme. Kein Node-Endpunkt oder Unterdetailabruf. | [Snapshot](/Users/banse/codex/maxpane/maxpane_dashboard/screens/record_detail.py:37), [Submissionansicht](/Users/banse/codex/maxpane/maxpane_dashboard/screens/submission_detail.py:38) |
| SWARM → Launch/Workflow | Tabellenmessage enthält kopierte Zeile; öffnet daraus Launch-/Workflow-Modal. | [Tabelle](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/_swarm_table.py:213), [Handler](/Users/banse/codex/maxpane/maxpane_dashboard/screens/surf.py:4109), [Modal](/Users/banse/codex/maxpane/maxpane_dashboard/screens/swarm_detail.py:1) |
| WORK → Job/Schritt → anderer Job | Baumknoten wählen, Detail-Scroll zurücksetzen, lokale Detailprojektion rendern. Verknüpfte Job-IDs und Nodes stammen aus dem fertigen Snapshot. Suche baut den lokalen Baum neu auf. | [Knoten](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/work.py:258), [Auswahl](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/work.py:401), [Details](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/work.py:465), [Suche](/Users/banse/codex/maxpane/maxpane_dashboard/widgets/surf/work.py:204) |

- Der allgemeine Record-Dialog kennt Space/Escape zum Schließen; ein durchgängiger Job→Node→Submission→Next/Previous-Viewer ist hier nicht implementiert. Bestehender Jobwechsel erfolgt im WORK-Baum oder über Schließen und Auswahl einer anderen Tabellenzeile. Zusätzliche Nachbartasten wären eine optionale UX-Änderung, keine Voraussetzung für schnellere Datenversorgung. [Bindings](/Users/banse/codex/maxpane/maxpane_dashboard/screens/record_detail.py:15)
- Ein geöffnetes Modal bleibt absichtlich auf seinem Snapshot. Spätere Cache-Anreicherung aktualisiert es nicht automatisch; vor vollständiger Hydration geöffnete Inhalte können bis zum Wiederöffnen unvollständig bleiben. Das ist getrennt von der Öffnungsgeschwindigkeit zu behandeln. [Snapshot-Test](/Users/banse/codex/maxpane/tests/screens/test_submission_detail.py:80)
- Ein wiederverwendeter `httpx.AsyncClient` existiert bereits, mit 15-s-Timeout. `_get` wartet vor jedem logischen Abruf 120 ms und versucht maximal die zwei erlaubten Deployment-Hosts nacheinander. Diese Pause ist **kein globaler Request-Lock**: parallele Leser können zugleich nach ihrer Pause senden. Im Client gibt es keinen gemeinsamen Jobdetailcache beziehungsweise Inflight-Eintrag je Job-ID. [Client](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:138), [GET](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:154)
- API-Nutzung: Joblisten default 100, erlaubt 1–500 mit exklusivem `before`; `/jobs/{id}` liefert volle Details ohne verwendeten Projektionsparameter; `/jobs/{id}/submissions` alle Submissions; Oracle-Details werden bereits mit `members=<submissionHash>` gefiltert, Launch-Jobs bereits `light=1`. [Listen](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:287), [Details](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:393), [Submissions](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:412), [Oraclefilter](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:245), [Light](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm_client.py:317)

### Inferences

Für warme Auswahl sind UI-Dispatch/Rendering zu messen; für erstmalig vollständige Inhalte zusätzlich die Hintergrund-Hydration. Ein schnellerer Provider oder zusätzliche Parallelität kann einen bereits lokalen Klick nicht beschleunigen. Payloadreduktion im Cache spart Speicher/Projektion, aber reduziert einen weiterhin vollständig abgerufenen `/jobs/{id}`-Body nicht.

### Gaps

Keine frische UI-Latenz- oder Payloadmessung. Der lokale API-Vermerk nennt für September 2026 Oracle-Details 159.079 Bytes ungefiltert versus 2.979 Bytes mit Memberfilter; das ist historische Evidenz für einen bereits vorhandenen Fix, kein heutiger Benchmark. [API-Vermerk](/Users/banse/codex/maxpane/docs/imd_swarm_api.md:513)

## 2. Welche Arbeit liegt tatsächlich vor sichtbaren Detaildaten?

### Takeaway

Der wichtigste konkrete Kaltpfad ist AGENT: Die erste Seat-Antwort wird früh gespeichert, danach wartet RECORD-Hydration auf weitere Kartenquellen. Deren Membership-Leser kann bis zu 64 volle Jobdetails in Vierergruppen abrufen. Der separate Scores-Sweep kann zusätzlich bis zu 100 Details pro fälligem Durchlauf laden; er läuft **im Hintergrund und wird nicht pro Jobklick abgewartet**. [Seatpipeline](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6650), [Membership](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_agent_card_sources.py:68), [Scores-Spawn](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6235)

### Cited Findings

1. **Kalter Seat:** `_offer_swarm_seat` startet nur einen ausgewählten Seat-Task; gleicher Seat nutzt den laufenden Task. Wechsel zu B cancelt und awaited den alten A-Task. Bis zu sechs Seat-Snapshots bleiben erhalten. Die Seatantwort wird gespeichert, bevor die weiteren Leser laufen. [Tasksteuerung](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6565), [Cancel](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6611), [Frühes Speichern](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6650), [Cachecap](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm.py:62)
2. **Reihenfolge nach erfolgreichem Seat:** bei aktivem AGENT `await card_sources.read` → ENS → Rewards → Submission-Antworten → Oracle-Anreicherung → Popup-Jobdetails. `card_sources.read` startet Earnings und Membership zwar parallel, wartet aber auf beide, bevor die folgenden RECORD-Stufen beginnen. Membership schreibt Ergebnisse bereits einzeln in ihren Cache; der nachfolgende Leser wartet trotzdem auf den vollständigen Batch. Maximal 64 fällige Details, je vier gleichzeitig. Das ist ein Maximum, keine Behauptung von 64 Requests in jedem Zyklus. [Stufen](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6667), [Gather](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_agent_card_sources.py:38), [Batch](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_agent_card_sources.py:88)
3. **RECORD ist bereits begrenzt:** Standardfenster 40, einstellbar 40–400; zuerst Filter/Fenster, dann bis zu vier verschiedene Submission-Jobs pro Zyklus. Gleiche Job-IDs werden gruppiert. Danach höchstens vier Oracle-Detailgruppen und zwei normale Popup-Jobdetails. Oracle-Index kann zusätzlich bis zu vier 500er-Seiten lesen. Answers/Popup-Details haben begrenzte persistente Slots (400 Punkte/Jobs, 48 h); nichtterminale/fehlende Fakten werden nach 120 s erneut fällig. [Fenster](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_models.py:1832), [Managerfilter](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6220), [Answers](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6809), [Jobdetails](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6842), [Oracle](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6864)
4. **Scores-Sweep:** eigenes abgekoppeltes Task/Singleflight, TTL 1.800 s. Holt `fetch_jobs()` ohne Limitparameter, also maximal 100 Listenjobs, anschließend deren Details sequenziell. `_swarm_sweep_ids` hat zwar Cap 200, die Defaultliste liefert hier nur bis zu 100; kein Terminal-/Revisionscache in diesem Sweep. Ein Busy-Ergebnis stoppt den Fanout. Live-SWARM dagegen hydratisiert nur ausführende Jobs. [TTL](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_cache.py:150), [Scores](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6978), [IDs](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:1015), [Sequenz](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6146), [Live](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6100)
5. **Keine belegte globale Warteschlange hinter Scores:** Scores und Live können gleichzeitig laufen; der Client hat keine gemeinsame Pace-Sperre. Zusätzliche Netzwerk-/Backendlast ist plausibel, ihre heutige Wirkung ungemessen. Unabhängig davon offered der normale `fetch_and_compute` den ausgewählten Seat erst **nach** dem awaited allgemeinen Full-Task; WORK/ORACLES haben eigene Cache-Abkürzungen. Deshalb ist der Start der Seat-Hydration nicht in jedem Pfad sofort. [Concurrent-Test](/Users/banse/codex/maxpane/tests/data/test_surf_manager_swarm.py:327), [Full vor Seat](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7779)
6. **Loading-Anzeige ≠ blockierter Klick:** AGENT-Loading berücksichtigt unter anderem Full-, Swarm-, Scores-, Board-, Seat- und Runtime-Tasks. Ein laufender Hintergrundtask kann das Signal aufrechterhalten, obwohl lokale Zeilen bereits geöffnet werden können. [Loading](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:7269)
7. **WORK-Datentraversierung:** ein Reader-Task mit kontrollierter Cancellation; sequenzielle Jobliste, Workflowliste und Overview, dann aktive Jobs und explizite Projekt-/Workflow-/Versionsbeziehungen. `read_job` dedupliziert innerhalb **dieses** Sweeps. Bedarfsgesteuerte Rückwärtspagination bis zu 100 Seiten à 500 und Kontextbudget bis 512 Detailreads sind Obergrenzen; optionale Details sind auf 24 begrenzt. Erst der konsistente Gesamt-Snapshot wird veröffentlicht, keine Teilergebnisse bei Cancellation. [Reader](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work_reader.py:16), [Listen/Local-Memo](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work_reader.py:54), [Scan](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work_reader.py:86), [Beziehungsauflösung](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work_reader.py:130), [Publish](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work_reader.py:207), [Limits](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work.py:15)
8. **Überlappende Verbraucher:** Live-SWARM, Scores, AGENT-Membership, RECORD-Jobdetails und WORK können dieselbe Job-ID unabhängig abrufen. Es gibt lokale Memoisierung und Ressourcencaches, aber keinen gemeinsamen Jobdetail-Singleflight dieser fünf Leser. Der genaue aktuelle Überschneidungsgrad wurde nicht gemessen. [Live/Scores](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6146), [Membership](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_agent_card_sources.py:76), [Record](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_manager.py:6842), [Work-Memo](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_work_reader.py:72)

### Inferences

- **Priorität 1:** die ausgewählte RECORD-Zeile beziehungsweise ihr kleines sichtbares Fenster nicht hinter der kompletten Membership-Historie und Earnings/ENS warten lassen. Das bedeutet eine gezielte Entkopplung von Stufen, nicht unbegrenztes Parallelisieren. Bestehende Membership-/Provenienzbedingungen müssen weiterhin darüber entscheiden, welche Antwort zu welchem Seat gehört; ungeprüfte Zeilen dürfen nicht vorzeitig als bestätigt erscheinen.
- **Priorität 2:** abgeleitete Jobdetails gemeinsam wiederverwenden, zunächst zwischen nachweislich überlappenden Lesern. Der Scores-Sweep ist eine Quelle unnötiger Hintergrundarbeit, kein Beleg für 100 Requests pro Klick. Eine reine Reduktion des Scores-Sweeps garantiert daher keine kürzere Modalöffnung.
- **Priorität 3:** WORK inkrementell ergänzen und unveränderte Detailressourcen wiederverwenden, ohne seinen Vollständigkeits-/Provenienzvertrag zu lockern. Ein reiner `createdAt`-Cursor findet neue Jobs; er erkennt nicht zuverlässig spätere Zustandsänderungen älterer Jobs und ersetzt deshalb den Active-Scan nicht allein.

### Gaps

Keine Messung heutiger HTTP-Laufzeiten oder End-to-End-UI-Dispatch-Zeiten. Cache-/Requestzahlen oben sind aus Code abgeleitete Obergrenzen. Die historischen Oktober-Reviewwerte in aidude dürfen nicht als heutige Wartezeit oder Anzahl pro Klick ausgegeben werden.

## 3. Welche KISS-Optionen lassen sich sauber abgrenzen?

### Takeaway

Zuerst die vorhandenen Stufen gezielt entkoppeln und eng messen. Ein gemeinsamer begrenzter Jobdetail-Leser kann danach redundante Arbeit reduzieren. aidudes inkrementelle Listen und schlanke Ressourcencaches passen dazu; sein blockierender Transport und „terminal für immer“-Verhalten passen nicht unverändert in MaxPane. [aidude-Muster und Grenzen](</Users/banse/codex/maxpane/docs/research_notes/Schnelle Navigation zwischen Schwarmjobs/aidude_navigation.md>)

### Cited Findings

- MaxPanes Popup-Jobdetails speichern `state`, `blocked_reason`, `nodes`, `read_ts`, `terminal`, aber **kein `updatedAt`/Revision**. Terminale Punkte werden innerhalb der 48-h-Retention nicht erneut fällig. Answers werden pro genauer Submission-Identität wiederverwendet. Eine neue allgemeine Cache-Schicht darf daraus keine unbegrenzte Unveränderlichkeit des gesamten Jobs, Results oder aller Submissions ableiten. Späte Ergänzungen sind hier ein Invalidierungsrisiko, kein in dieser Recherche nachgewiesener Produktionsfehler. [Felder](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm.py:1786), [Retention/Fälligkeit](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm.py:1829), [Answers-Fälligkeit](/Users/banse/codex/maxpane/maxpane_dashboard/data/surf_swarm.py:1973)
- A→B-Seatwechsel cancelt alte Arbeit bereits, und die Cacheidentität trennt genaue Submission-Hashes. Ein zusätzlicher gemeinsamer Inflight-Cache braucht bewusstes Cancellation-Verhalten: Der Abbruch eines UI-Konsumenten darf nicht versehentlich den ebenfalls auf denselben Job wartenden Hintergrundleser abbrechen. Antwortpublikation bleibt an Job-ID/Revision gebunden, nicht an eine inzwischen geänderte globale Auswahl. [Wechseltest](/Users/banse/codex/maxpane/tests/data/test_surf_manager_answers.py:100), [Seat-Test](/Users/banse/codex/maxpane/tests/data/test_surf_manager_swarm.py:1125)

### Inferences / Optionen

| Option | Konkreter Umfang | Nutzen und Gegenleistung |
|---|---|---|
| **A — vorhandene Reader priorisieren (erster kleiner Schritt)** | Seat-Hydration früh anbieten; minimale Membership für sichtbare RECORD-Zeilen priorisieren; unabhängige Earnings/ENS und restliche Membership nachführen. Vorhandene 4/2-Caps und Cacheprojektionen behalten. | Kürzerer belegter Kaltpfad bei begrenzter Änderung. Verbraucht weiterhin redundante Detailreads verschiedener Reader. Konsistente Membership vor bestätigten Antworten bleibt Pflicht. |
| **B — begrenzten gemeinsamen Jobdetail-Leser ergänzen** | `jobId`-bezogener Inflight-Eintrag plus kompakter, zeitlich begrenzter Snapshot; separate Frische für aktive/terminale Details und getrennte Submission-/Resultidentitäten. Zuerst Membership/RECORD, danach Scores/WORK einzeln anschließen. | Weniger doppelte Requests über Verbraucher und Zyklen; mehr Verantwortung für Invalidierung, Cancellation und gemeinsam benötigte Felder. Kein neuer Server, kein Vollhistorienindex. |

Für B: Listen-`updatedAt`/Revision nur dann als Invalidierung verwenden, wenn der Endpointvertrag diese Information zuverlässig liefert; sonst kurze gezielte Revalidierung für unvollständige Ergebnisse und begrenzte längere TTL für bestätigte terminale Inhalte. Eine leere Submissionliste oder `complete:false` darf nicht dauerhaft „fertig“ bedeuten. Ein schlanker Job-Snapshot muss die wirklich verwendeten Projekt-/Workflow-/Version-IDs, Node-Kanten und Rollen behalten; aidudes 30-Node-Projektion ist kein vollständiges Modell für MaxPanes WORK-Kontext.

**Mögliche Arbeitspakete bei späterer Implementierung (noch nicht umgesetzt):**

1. **Datenvertrag/Reader, eigener Verantwortlicher:** gemeinsamer Jobdetail-Leser und Tests für Inflight-Dedup, Revision/TTL, negative Resultate und Cancellation; kleine neue Datendatei plus zugehörige Tests. Keine UI-Dateien. Voraussetzung für Option B.
2. **Manager-Integration, ein Verantwortlicher:** `surf_manager.py` und `surf_agent_card_sources.py` zusammen verantworten, da beide den Seat-Kaltpfad steuern. Für A unabhängig startbar; für B nach Paket 1 zuerst Membership/RECORD, danach Scores. Bestehende Identitäts- und Cachetests erweitern, insbesondere A→B→A sowie langsame Earnings bei schnell verfügbarem Record.
3. **WORK-Reuse, separater Verantwortlicher:** `surf_work_reader.py` und dessen Tests; nach Paket 1, parallel zur Manager-Anbindung möglich. Vollständigkeits-/Projektprovenienzprüfungen und atomisches Snapshot-Publish erhalten.
4. **Optionale UI-Navigation, separater Verantwortlicher:** erst bei gewünschter UX `record_detail.py`/Submissiondialog und Screenhandler; Snapshotwechsel aus vorhandenen Rows, keine versteckte Vollhistorienhydration. Datenoptimierung benötigt dieses Paket nicht.

Abnahmekriterien getrennt halten: (a) warme Auswahl ohne neue Requests, (b) Zeit bis ausgewählter kalter Record vollständig, (c) zusätzliche und doppelte Requests pro Job-ID, (d) korrekter Inhalt nach A→B→A und verspäteter Response. HTTP-Latenz, Cachealter und Zeit bis UI-Daten nutzbar sind verschiedene Messgrößen.

### Verifikation und Grenzen

Sechs vorhandene fixturebasierte Tests am 17.10.2026 lokal ausgeführt: **6 passed in 0.93s**. Keine Netzwerkzugriffe in diesen Tests; keine neuen Tests, Anwendungsänderungen, Jobs, Signaturen oder Zahlungen. Die Tests belegen Cache-/Task-Invarianten; sie messen keine reale Navigation oder API-Latenz.

```text
.venv/bin/python -m pytest \
  tests/data/test_surf_manager_answers.py::test_record_window_job_grouping_and_definitive_terminal_answers_never_reread \
  tests/data/test_surf_manager_answers.py::test_switch_isolates_exact_hash_and_cancels_inflight_answer \
  tests/data/test_surf_manager_answers.py::test_popup_job_details_cap_terminal_blocked_retry_and_failure \
  tests/data/test_surf_manager_swarm.py::test_the_scores_sweep_runs_even_while_the_live_read_is_still_in_flight \
  tests/data/test_surf_manager_swarm.py::test_one_seat_read_per_cycle_and_a_token_change_cancels_the_old_one \
  tests/data/test_surf_work_reader.py::test_cancellation_does_not_publish_partial_or_failure -q
```

Zusätzlich nur gelesen: Screen-Regressionen belegen, dass das Öffnen eines Submission-/Oracle-Modals keine zusätzlichen Managerabrufe auslöst und die kopierte Zeile stabil bleibt. Diese Screen-Tests wurden für diese Recherche nicht erneut ausgeführt. [Submission-Test](/Users/banse/codex/maxpane/tests/screens/test_submission_detail.py:80), [Oracle-Test](/Users/banse/codex/maxpane/tests/screens/test_oracle_answer.py:125)
