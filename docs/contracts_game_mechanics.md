# CONTRACTS — Grundlagen der Designrunde

Stand: 2026-10-25. Status: Designvorschlag, keine freigegebene Implementierung.
Auftrag: drei ASCII-Mockups mit Hero Cards für eine persönliche Übersicht über
selbst oder im eigenen Auftrag durch den IMD-Swarm deployte Contracts auf
Ethereum Mainnet, Base und RH. Im bestehenden MaxPane bezeichnet RH Robinhood.

## Das Produktproblem

Die Übersicht beantwortet: Welche Contracts habe ich deployt oder deployen
lassen, auf welcher Chain liegen sie, zu welchem Projekt gehören sie und wie
komme ich zu Adresse, Deployment und Quellcode? Tokens, NFTs und allgemeine
Anwendungscontracts gehören gleichermaßen hinein. Dies ist kein Tokenportfolio.

Eine aus mehreren öffentlichen Wallets bestehende persönliche Auswahl bildet
den Betrachtungsbereich. Die konkrete Wallet-Liste ist für die spätere
Datenanbindung zu bestimmen; die Entwürfe benötigen keine echten Walletdaten.
Zielgröße ist die bisher verwendete Terminalgröße 149×45. Das ist ein Designziel,
noch keine durch Textual-Rendering nachgewiesene Mindestgröße.

## Was eine Zeile und eine Zahl bedeuten

- Ein Contract wird durch `(chain_id, address)` identifiziert. Derselbe Name oder
  dieselbe Adresse auf zwei Chains ergibt keine gemeinsame Contract-Identität.
- Gezählt werden bestätigte Deployment-Adressen, nicht Jobs, Launches oder
  Projekte. Ein Launch mit drei deployten Anwendungscontracts ergibt drei Zeilen.
- SELF bezeichnet einen belegten Deployment-Pfad aus der eigenen Wallet-Auswahl,
  einschließlich belegbarer Factory-Deployments. Der technische Creator kann
  dabei eine Factory sein; die auslösende Wallet bleibt separat sichtbar.
- SWARM bezeichnet eine belegte eigene Beauftragung mit zugehörigem Deployment.
  Ein eigener Agent als Contributor oder eine erhaltene Tokenzuteilung reicht
  dafür nicht aus. Überlappende Belege werden am Contract zusammengeführt;
  die Gesamtzahl zählt jede Chain-Adresse nur einmal. Im Demo sind die beiden
  Herkunftsgruppen absichtlich disjunkt.
- Aktueller Owner/Admin und Deployment-Herkunft sind getrennte Eigenschaften.
  Abgegebene oder renouncte Rechte entfernen ein eigenes Deployment nicht aus
  seiner Historie. Ein fehlender `owner()`-Getter ist kein Beweis für Renouncement.
- Proxy und Implementation sind getrennte Adressen. Beziehungen werden nur
  gezeigt, wenn belegt. Externe Referenzen und gemeinsam genutzte Infrastruktur
  zählen nicht automatisch als eigene Deployments.
- Historische Versionen bleiben auffindbar. CURRENT/SUPERSEDED benötigt eine
  belegte oder explizit gepflegte Projektzuordnung; vorhandener Code allein
  bedeutet weder aktuelle Version noch aktive Nutzung.
- Kandidaten ohne vollständigen Deployment-/Zuordnungsnachweis stehen separat.
  Source verification, Bytecode-Existenz und persönliche Herkunft bleiben drei
  verschiedene Aussagen. Kein grünes Symbol behauptet ein Security-Audit.

## Tatsächliche Ausgangspunkte im Repository

| Vorhanden | Verwendung im möglichen späteren Dashboard |
|---|---|
| `docs/portfolio_PRD.md` und Portfolio-Wallet-Auswahl | Wallet setzen, gespeicherten Zustand behalten, Wechsel sauber abgrenzen |
| `widgets/surf/news_hero.py` / bestehende Rack-Heroes | Sechs gleich große Hero Cards, vorhandene Theme-Farben und Zahlendarstellung |
| `SwarmClient.fetch_launches`, `fetch_launch`, `fetch_launch_jobs`, `SwarmTokensClient.fetch_page` | Vorhandene öffentliche Launch-Leser und Pagination; persönliche Zuordnung zusätzlich erforderlich |
| `surf_launch_contribution.py` | Beispiel für begrenzte Joins; Contributor-Rang ist kein persönlicher Deployment-Katalog |
| `surf_nft_*` und `swarm_tokens_*` | Chain-/Adressidentität, Deployment-Prüfung, Links und bestehende Detailmuster |
| `surf_launch_base_client.py`, `surf_launch_rh_client.py` | Vorhandene keyless State-Reader, keine Zusage vollständiger Creator-Historie |
| Gemeinsame Address-/Explorer- und Filter-Widgets | Kopieren, chainrichtige Links, Filter, Suche und Tastaturbedienung |

Keine bereits fertige, nachweislich vollständige persönliche Discovery für alle
drei Chains wurde in dieser Designrunde festgestellt. Die bestehende Launch-
und Contribution-Logik darf nicht mit dieser Anforderung gleichgesetzt werden.

## Öffentliche Quellen und ihre Grenzen

Die offizielle [IMD-Dokumentation](https://imd.fun/docs/llms.txt) wurde am
2026-10-25 gelesen. Sie dokumentiert `GET /requests/paid-by/:address` als
öffentlichen Einstieg zu bezahlten beziehungsweise versuchten Orders, begrenzt
auf die neuesten 100. Das reicht allein nicht für eine vollständige Historie.
Ein Order-Resultat muss erst zum passenden Job/Launch und zu dessen Deployment
verknüpft und geprüft werden. Eine bezahlte, fehlgeschlagene oder abgeschlossene
Arbeitsanfrage ist noch kein deployter Contract.

Die Dokumentation erlaubt einen vom zahlenden Wallet abweichenden `owner` bei
bestimmten Launch-Arten. Owner, Payer, technischer Deployer und Contributor sind
deshalb eigene Rollen. Unterstützte Launch-Chains sind vor einer späteren
Integration aus den aktuellen Capabilities zu lesen; ältere Tabellen dürfen
nicht als aktuelle Freigabe verwendet werden. Das Dashboard kann historische
Deployments anzeigen, unabhängig davon, ob neue Launches dort gerade offen sind.

Für eigene Deployments sind je nach Pfad Erstellungsreceipts, Factory-Events,
Creation-Traces oder passende Deployment-Manifeste erforderlich. Öffentliche
Explorer können Kandidaten liefern; die tatsächliche keyless Verfügbarkeit und
Historienabdeckung pro Chain sind vor Implementierung zu messen. Ein gespeicherter
Import ergänzt die Discovery, statt eine lückenlose Suche vorzutäuschen.

## Gemeinsame Designentscheidungen

- Sechs Hero Cards und sichtbare Filter für Chain, Herkunft und Contract-Typ.
  Die Hero-Zahlen bleiben ausdrücklich auf den bestätigten Profilbestand bezogen.
  Die gefilterte Liste zeigt ihre Treffermenge daneben, etwa `12 matches / 42
  confirmed`. Quellenabdeckung und Gesamtbestand wechseln beim Filtern nicht
  unbemerkt ihre Bedeutung.
- Selektion öffnet eine sofort aus dem Katalog lesbare Detailansicht: Contract,
  Chain, Herkunft, Projekt, Adresse, Creation-Tx, technischer Deployer, eigene
  Zuordnung, aktueller Owner/Admin falls bekannt, Source/Repo und Proxy-Bezüge.
- Adressen haben Explorer-Link und Copy-Aktion. Die ASCII-Entwürfe verwenden
  ausschließlich Platzhalter ohne erfundene reale Adressen.
- Ein sichtbarer Coverage-Hinweis unterscheidet bekannte Funde von vollständiger
  Discovery; unbekannte Werte bleiben unbekannt. Eine leere Liste nach einem
  abgeschlossenen Scan unterscheidet sich von einem noch nicht erfolgten Scan.
- Bereits geladene Zeilen und Hero-Zahlen erscheinen ohne vorheriges Öffnen von
  Contract-Details. Enrichment hat eigene Source-Zeiten und blockiert den
  Katalog nicht. Detailauswahl startet keinen unbeschränkten Historien-Scan.
- Nur Lesen, keine Wallet-Signaturen, keine Transaktionen, keine Secrets und
  keine API-Key-Pflicht. Keine erfundenen TVL-, P/L- oder Sicherheitskennzahlen.
- Dunkle MaxPane-Flächen, neutrale Rahmen/Labels und grüne Werte; Amber nur bei
  einem tatsächlichen Prüfbedarf. Keine dekorativen Alarmfarben.

## Drei vorgeschlagene Ansichten und nächster Schritt

Die Wireframes stehen in `contracts_dashboard_ascii_mockups.md`. Sie zeigen
denselben ausdrücklich erfundenen Beispielbestand: 42 bestätigte Contracts,
12 SELF / 30 SWARM, davon 18 Ethereum / 17 Base / 7 RH, verteilt auf acht Projekte.
Drei zusätzliche Kandidaten gehören nicht zu den 42.

1. Registry: schnelle Suche über alle Contracts, Detailspalte für die Auswahl.
2. Projects: Projektbaum mit Chain-Untergruppen, Versionen und Komponenten.
3. Chains: nebeneinanderliegende Chain-Listen und gemeinsamer Detailbereich.

Erst nach Auswahl einer Richtung folgen PRD, Implementierungsplan und ein
separater Textual-Mock mit sichtbaren Beispieldaten. Vollständige Historien-
Discovery und persönliche Swarm-Zuordnung sind eigene Datenarbeit, keine mit
einem Wireframe bereits nachgewiesenen Eigenschaften.
