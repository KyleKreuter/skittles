# Skittles Exchange — KI-Agenten-Trading-Experiment

Ein Research-Framework, um zu beobachten, **wie unterschiedliche LLM-Provider und
-Modelle strategisch handeln**, wenn man ihnen dasselbe Problem stellt. Mehrere
KI-Agenten handeln Skittles an einer börsenähnlichen Doppelauktion und versuchen,
möglichst viele Skittles **einer einzigen Farbe** anzuhäufen. Das Verhalten der
Modelle — welche Strategie sie wählen, wie konsequent sie sie verfolgen, wer
gewinnt — ist die Forschungsvariable.

---

## Inhaltsverzeichnis

1. [Die Idee in einem Absatz](#1-die-idee-in-einem-absatz)
2. [Die Spielregeln](#2-die-spielregeln)
3. [Markt-Mechanik im Detail](#3-markt-mechanik-im-detail)
4. [Die Erhaltungs-Invariante](#4-die-erhaltungs-invariante)
5. [Architektur](#5-architektur)
6. [Ablauf einer Simulation](#6-ablauf-einer-simulation)
7. [Die Agenten](#7-die-agenten)
8. [Die Tool-API der Agenten](#8-die-tool-api-der-agenten)
9. [Konfigurations-Referenz](#9-konfigurations-referenz)
10. [Ausgabe-Artefakte](#10-ausgabe-artefakte)
11. [Setup & Ausführen](#11-setup--ausführen)
12. [Auswertung](#12-auswertung)
13. [Provider mischen](#13-provider-mischen)
14. [Tests](#14-tests)
15. [Bisherige Ergebnisse](#15-bisherige-ergebnisse)
16. [Erweitern](#16-erweitern)
17. [Limitationen & Forschungs-Hinweise](#17-limitationen--forschungs-hinweise)

---

## 1. Die Idee in einem Absatz

Jeder Agent startet mit 100 zufällig auf fünf Farben verteilten Skittles
(Rot, Grün, Blau, Orange, Gelb). Über `n` Runden handeln die Agenten an einer
zentralen Börse. Gewonnen hat, wer am Ende **die meisten Skittles einer einzelnen
Farbe** besitzt — welche Farbe ist egal. Die Agenten sind LLMs, die **autonom über
Tool-Calls** entscheiden, oder eine regelbasierte Heuristik als Kontrollgruppe.
Welcher Provider/welches Modell mitspielt, ist reine Konfigurationssache
(über die LiteLLM-Abstraktion). Gestartet wird mit Mistral.

## 2. Die Spielregeln

- **Startkapital:** 100 Skittles pro Agent, multinomial-zufällig auf fünf Farben
  verteilt (seed-gesteuert, also reproduzierbar).
- **Ziel:** maximaler Bestand **einer** Farbe am Ende der letzten Runde.
- **Handel:** nicht Peer-to-Peer, sondern über ein **Order-Book je Farbpaar**
  (kontinuierliche Doppelauktion). Man kennt seine Gegenpartei nicht — wie an
  einer echten Börse.
- **Kommunikation:** zusätzlich gibt es ein **namentliches Broadcast-Forum**
  (Chat). Jeder Agent kann einen Beitrag posten (Name + Nachricht), den **alle**
  Agenten sehen — zum Verhandeln, Signalisieren, Koordinieren oder Bluffen
  (siehe §7.3). Der Handel selbst läuft weiter ausschließlich über das Order-Book.
- **Escrow:** Beim Eingeben einer Order werden die angebotenen Skittles **sofort
  gesperrt**.
- **Gebühr:** Die Börse ist ein Clearinghouse mit Gebühr — sie behält pro Trade
  einen Anteil von dem, was jede Seite erhält. Der Umlauf sinkt also mit jedem
  Handel.
- **Runden:** Pro Runde hat jeder Agent genau einen Zug (in zufälliger
  Reihenfolge). Offene Orders bleiben über Runden hinweg im Buch liegen, bis sie
  ausgeführt oder storniert werden.
- **Spielende:** Nach `n` Runden werden alle offenen Orders storniert (Escrow
  zurück), dann wird gewertet.

## 3. Markt-Mechanik im Detail

### 3.1 Farben und Märkte

Es gibt fünf Farben mit einer festen Rangfolge:

```
RED < GREEN < BLUE < ORANGE < YELLOW
```

Bei fünf Farben existieren **C(5,2) = 10 Märkte**. Jedes ungeordnete Farbpaar
wird auf genau ein Marktpaar `(base, quote)` abgebildet, wobei `base` die in der
Rangfolge **niedrigere** Farbe ist (`canonical_pair` in
`src/skittles/domain/colors.py`). Beispiel: Rot und Blau ergeben den Markt
`(RED, BLUE)`.

### 3.2 Order-Seiten

Eine Order wird immer relativ zur `base`-Farbe ausgedrückt:

| Seite | Bedeutung | Escrow (sofort gesperrt) |
|---|---|---|
| **BUY** base | `base` erwerben, mit `quote` bezahlen | `quantity × price` von `quote` |
| **SELL** base | `base` abgeben, `quote` erhalten | `quantity` von `base` |

- **Preis** ist eine ganze Zahl: wie viele `quote`-Skittles **1** `base`-Skittle
  kosten.
- **Menge** ist eine ganze Zahl (`base`-Skittles).

Ganzzahligkeit garantiert, dass nie Skittle-Bruchstücke entstehen. Jeder
Farb-für-Farb-Tausch ist als BUY oder SELL auf dem passenden kanonischen Markt
darstellbar — eine nicht-kanonische Orientierung (z. B. „SELL BLUE für RED" auf
`(BLUE, RED)`) wird abgelehnt, mit einer Fehlermeldung, die die richtige
Orientierung nennt.

### 3.3 Matching (kontinuierliche Doppelauktion)

Trifft eine neue Order ein, wird sie sofort gegen die Gegenseite des Buchs
gematcht — **Preis-Zeit-Priorität**:

- Eine neue **SELL** matcht gegen ruhende **BUY**-Orders mit `bid ≥ ask`, beste
  (höchste) Gebote zuerst, bei Gleichstand das ältere zuerst.
- Eine neue **BUY** matcht gegen ruhende **SELL**-Orders mit `ask ≤ bid`,
  günstigste zuerst, dann älteste.
- **Ausführung zum Maker-Preis** (Preis der ruhenden Order). Hat ein Taker-Käufer
  mit einem höheren Limit eingestellt, wird ihm die Differenz **zurückerstattet**.
- Teilausführungen sind möglich; der Rest bleibt als ruhende Order im Buch.

### 3.4 Gebühr (Clearinghouse-Modell)

Bei jedem Trade behält die Börse einen Anteil `fee_rate` (Default **10 %**) von
dem, was **jede Seite erhält**, abgerundet auf ganze Skittles. Die Gebühr kommt
aus den *Einnahmen*, nicht aus dem Bezahlten — daher ist kein zusätzlicher Escrow
nötig. Die einbehaltenen Skittles landen im **Börsen-Tresor**
(`exchange.fees_collected`) und verlassen den Umlauf der Agenten.

### 3.5 Durchgerechnetes Beispiel

> Alice stellt **SELL 10 RED @ 2 BLUE** ein. Bob stellt danach **BUY 10 RED @ 2
> BLUE** ein. Gebühr = 10 %.

1. **Escrow:** Alice werden 10 ROT gesperrt. Bob werden 10×2 = 20 BLAU gesperrt.
2. **Match:** 10 ROT zum Preis 2 → Handelsvolumen 20 BLAU.
3. **Settlement mit Gebühr:**
   - Alice (Verkäuferin) erhält 20 BLAU − ⌊20×0.1⌋ = 20 − 2 = **18 BLAU**.
   - Bob (Käufer) erhält 10 ROT − ⌊10×0.1⌋ = 10 − 1 = **9 ROT**.
   - Tresor behält **2 BLAU + 1 ROT**.
4. **Ergebnis:** Alice 40 ROT / 68 BLAU (Start 50/50), Bob 59 ROT / 30 BLAU.
   Pro Farbe gilt weiter: Summe über Agenten + Tresor = Ausgangsmenge.

Kleine Trades zahlen durch das Abrunden gar keine Gebühr (z. B. 1 ROT @ 1 BLAU →
⌊0.1⌋ = 0).

### 3.6 Wertung am Ende

Nach der letzten Runde werden **alle offenen Orders storniert** (sämtlicher
Escrow fließt zurück in `available`). Dann gilt:

- **Score** = höchster `available`-Bestand einer einzelnen Farbe.
- **Sieger** = höchster Score. Tie-Break: meiste Skittles gesamt, dann
  Agenten-ID (stabil/reproduzierbar).

## 4. Die Erhaltungs-Invariante

Skittles werden nie erzeugt oder vernichtet. Für **jede Farbe** ist die Summe

```
Σ (available + reserved) über alle Agenten   +   Tresor[Farbe]
```

über die gesamte Simulation **konstant** und gleich der Anfangsmenge. Skittles
wandern nur: zwischen `available` und `reserved` (Escrow), zwischen Agenten
(Trade) oder in den Gebühren-Tresor. Diese Invariante wird in den Tests über
Tausende zufälliger Orders abgesichert (`tests/test_escrow_invariants.py`,
`tests/test_fees.py`).

## 5. Architektur

```
src/skittles/
  domain/
    colors.py        # Color-Enum, Rangfolge, kanonische Marktpaare
    inventory.py     # Inventory: available[] + reserved[] (Escrow) je Farbe
  market/
    order.py         # Order, Side(BUY/SELL), OrderStatus, Trade
    order_book.py    # ein Buch pro Farbpaar (Bids/Asks, FIFO je Preislevel)
    exchange.py      # alle Märkte, Matching, Escrow, Settlement, Gebühr, Invariante
  agents/
    base.py          # Agent-Interface (act)
    tools.py         # ToolContext (Aktions-API) + Tool-Schemas + dispatch
    heuristic_agent.py  # regelbasierter Baseline-Agent (keine API-Kosten)
    llm_agent.py     # LiteLLM-Agent + Tool-Call-Loop
    prompts.py       # System-Prompt + Beobachtungs-Text fürs LLM
    cost.py          # CostTracker (gemeinsamer Kosten-Deckel)
  social/
    forum.py         # geteiltes Broadcast-Forum (namentlicher Chat)
  sim/
    config.py        # pydantic-Config-Modelle + YAML-Loader
    engine.py        # Orchestrierung: Runden, Zugreihenfolge, Snapshots
    scoring.py       # Sieger-Ermittlung + Tie-Break
  obs/
    events.py        # JSONL-Event-/Snapshot-Logging
    report.py        # report.json (Sieger, Trajektorien, Kosten, Gebühren)
  cli.py             # Einstiegspunkt: skittles run -c <config>
scripts/
  analyze.py         # pandas/matplotlib-Plots eines Laufs
config/              # Experiment-Konfigurationen (YAML)
runs/                # pro Lauf: events.jsonl, snapshots.jsonl, report.json, *.png
reports/             # konsolidierte Markdown-Berichte
tests/               # pytest: Engine, Matching, Escrow, Scoring, Gebühr, LLM-Loop
```

**Datenfluss:** `cli` lädt die Config → `SimulationEngine` verteilt die Skittles
und baut die `Exchange` und die Agenten → pro Runde bekommt jeder Agent einen
`ToolContext` und handelt → die `Exchange` matcht und protokolliert über den
`EventLogger` → am Ende erzeugt `report.py` die `report.json`.

Die zentrale Idee: **`ToolContext` ist die einzige Aktions-Schnittstelle.** Sowohl
der Heuristik- als auch der LLM-Agent nutzen sie — die Spielregeln liegen damit an
genau einer Stelle.

## 6. Ablauf einer Simulation

1. **Austeilen:** Jeder Agent erhält 100 Skittles, multinomial-zufällig auf die
   Farben verteilt (RNG mit `seed`).
2. **Initial-Snapshot** (Runde 0) wird geloggt.
3. **Für jede Runde `1..n`:**
   - Die Zugreihenfolge wird zufällig gemischt (eigener, seed-abgeleiteter RNG).
   - Jeder Agent erhält einen `ToolContext` und ruft `act()` auf. Das Matching
     läuft kontinuierlich — eine neue Order kann sofort gegen ruhende Orders
     anderer Agenten ausgeführt werden.
   - Ein Snapshot der Runde wird geschrieben (Inventare, führende Farbe je Agent,
     offene Orders, Trades dieser Runde).
4. **Abschluss:** Alle offenen Orders werden storniert, dann gewertet, der Report
   geschrieben und das Lauf-Verzeichnis geschlossen.

Stürzt ein einzelner Agent in seinem Zug ab (z. B. API-Fehler), wird der Fehler
geloggt (`agent_error`) und der Lauf läuft weiter.

## 7. Die Agenten

### 7.1 HeuristicAgent (Baseline, kostenlos)

Eine bewusst einfache Vergleichsstrategie und gleichzeitig der Testharness, mit
dem die komplette Simulation **ohne API-Kosten** läuft. Pro Zug:

1. Storniert die eigenen ruhenden Orders (gibt Escrow frei).
2. Wählt als Ziel die Farbe, von der es aktuell **am meisten** hat.
3. Versucht, jede andere Farbe in die Zielfarbe umzuwandeln — kreuzt günstige
   ruhende Orders, sonst stellt es eine passive 1:1-Order ein.

Nicht optimal, sondern als Referenzpunkt gedacht.

### 7.2 LLMAgent (LiteLLM)

Ein vollständig autonomer Trader. Pro Zug ein frischer Tool-Loop:

- **Kein Verlauf über Runden hinweg.** System-Prompt + eine kompakte Beobachtung
  (Inventar + Markt-Digest) als User-Message. Der Marktzustand selbst ist der
  persistente Speicher, den das Modell neu beobachtet — das hält die Token-Kosten
  über viele Runden beschränkt.
- Das Modell ruft in einer Schleife Tools auf (max. `max_tool_calls_per_turn`),
  bis es `end_turn` aufruft oder das Budget erreicht ist.
- **Fehler-Feedback:** Ungültige Aktionen (falscher Markt, zu wenig Inventar)
  liefern strukturierte `{"error": ...}`-Antworten zurück, sodass das Modell
  korrigieren kann (im Lauf beobachtet: mistral-large korrigierte einen
  nicht-kanonischen Markt selbstständig).
- **Kosten:** Jeder Completion-Call wird über LiteLLM bepreist und gegen den
  gemeinsamen `CostTracker` gezählt. Ist `max_cost_usd` erreicht, setzen die
  LLM-Agenten aus.
- Die kurze Begründung, die das Modell pro Zug ausgibt, wird als `notes` für den
  Report gespeichert — die Grundlage der Strategie-Analyse.

### 7.3 Das Forum (Chat)

Ein **geteiltes, namentliches Broadcast-Forum** (`social/forum.py`) gibt den
Agenten einen Kommunikationskanal — der bewusste Gegenpol zum anonymen
Order-Book:

- Mit `broadcast(message)` postet ein Agent eine Nachricht, die **seinen Namen
  trägt** und von **allen** Agenten gesehen wird.
- Die jüngsten Beiträge (Default 15, `forum_feed_size`) erscheinen bei jedem
  Agenten direkt in der Beobachtung (Push); `view_forum` liest sie erneut.
- Es ist **Cheap Talk**: niemand ist an seine Aussagen gebunden, Agenten dürfen
  bluffen. Getauscht wird ausschließlich über das Order-Book.
- Nachrichten sind auf 500 Zeichen begrenzt; nur LLM-Agenten nutzen das Forum
  (die Heuristik schweigt).
- Per `forum_enabled: false` lässt sich der Kanal abschalten — für
  Ablations-Studien (Handel mit vs. ohne Kommunikation).

Beiträge werden als `broadcast`-Events geloggt; `report.json` enthält die
Beitrags-Anzahl je Agent (`broadcasts`), die Gesamtzahl (`total_broadcasts`) und
das vollständige `forum_transcript`. In einem kurzen Testlauf pivotierte ein
Agent sichtbar weg vom angekündigten Ziel eines Rivalen („*targeting highest
color with least competition*") — emergente strategische Kommunikation.

## 8. Die Tool-API der Agenten

Alle Aktionen laufen über den `ToolContext` (`src/skittles/agents/tools.py`).
Dem LLM werden sie als Function-Calling-Tools angeboten:

| Tool | Wirkung |
|---|---|
| `get_state()` | Eigenes Inventar (available/reserved/total), führende Farbe, Runde, Restrunden, `fee_rate`. |
| `view_markets()` | Order-Books aller 10 Märkte (Top-Levels, anonym). |
| `view_market(base, quote)` | Ein einzelnes Order-Book. |
| `my_orders()` | Eigene ruhende Orders mit IDs. |
| `place_order(side, base, quote, quantity, price)` | Order setzen (validiert, escrowt, matcht). |
| `cancel_order(order_id)` | Eigene Order stornieren, Escrow zurück. |
| `broadcast(message)` | Namentliche Nachricht ins Forum posten (alle sehen sie). *Nur wenn Forum aktiv.* |
| `view_forum()` | Jüngste Forum-Beiträge aller Agenten lesen. *Nur wenn Forum aktiv.* |
| `end_turn()` | Zug beenden. |

Argumente werden über pydantic validiert (`PlaceOrderArgs` etc.); ungültige Calls
geben einen Fehler zurück, statt den Lauf abzubrechen.

## 9. Konfigurations-Referenz

Eine Experiment-Config ist eine YAML-Datei (Beispiele in `config/`). Felder:

| Feld | Default | Bedeutung |
|---|---|---|
| `rounds` | 50 | Anzahl Runden. |
| `seed` | 42 | Steuert Anfangsverteilung **und** Zugreihenfolge (Reproduzierbarkeit). |
| `initial_skittles` | 100 | Startmenge je Agent. |
| `fee_rate` | 0.1 | Börsengebühr (Anteil des Erhaltenen, abgerundet). `0` = keine Gebühr. |
| `max_tool_calls_per_turn` | 12 | Obergrenze an Tool-Calls je LLM-Zug (begrenzt Kosten). |
| `max_cost_usd` | 5.0 | Harter Kosten-Deckel pro Lauf; LLM-Agenten setzen bei Erreichen aus. `null` = unbegrenzt. |
| `market_depth` | 5 | Wie viele Preis-Levels je Buch-Seite in Beobachtungen erscheinen. |
| `forum_enabled` | `true` | Broadcast-Forum (Chat) an/aus. `false` für Ablations-Studien. |
| `forum_feed_size` | 15 | Wie viele jüngste Forum-Beiträge je Zug gezeigt werden. |
| `output_dir` | `runs` | Wohin Lauf-Artefakte geschrieben werden. |
| `agents` | — | Liste der Teilnehmer (mind. 2, eindeutige IDs). |

**Agent-Felder:**

| Feld | Bedeutung |
|---|---|
| `id` | Eindeutiger Name (taucht im Report/Log auf). |
| `type` | `llm` oder `heuristic`. |
| `provider` | z. B. `mistral`, `openai`, `anthropic` (nur für `llm`). |
| `model` | z. B. `mistral-large-latest`. Mit `/` darin wird es direkt als LiteLLM-Modellstring genutzt. |
| `temperature` | Sampling-Temperatur (Default 0.7). |
| `persona` | Optionaler Zusatz zum System-Prompt. |

**Beispiel (`config/dry-run.yaml`):**

```yaml
rounds: 30
seed: 42
initial_skittles: 100
fee_rate: 0.1
max_tool_calls_per_turn: 12
market_depth: 5
agents:
  - id: heuristic-a
    type: heuristic
  - id: heuristic-b
    type: heuristic
  - id: heuristic-c
    type: heuristic
```

Mitgelieferte Configs: `dry-run.yaml` (API-frei), `mistral-smoke.yaml` (kurzer
echter Lauf), `experiment.yaml` (50 Runden, 2 Modelle + Baseline),
`temp-study.yaml` (10 LLMs über Temperaturen + Baseline).

## 10. Ausgabe-Artefakte

Jeder Lauf schreibt nach `runs/<timestamp>/`:

### `events.jsonl` — jedes Ereignis, eine JSON-Zeile

Typen: `run_started`, `initial_inventory`, `order_placed`, `trade`,
`order_cancelled`, `agent_error`, `run_finished`. Trades enthalten Maker/Taker,
Preis, Menge, Volumen **und die Gebühren** (`base_fee`, `quote_fee`).

### `snapshots.jsonl` — Zustand je Runde

Pro Runde: führende Farbe + Bestand je Agent, verfügbare Mengen, gesperrte Menge,
Anzahl offener Orders, Trades dieser Runde.

### `report.json` — die Zusammenfassung

Sieger, Endstand (Score/Farbe/Gesamt je Agent), **Kosten je Agent**,
**Trajektorie** (führende Farbe über die Runden, fürs Plotten), Strategie-`notes`,
Trade-Gesamtzahl und der **Gebühren-Tresor** (`fees_collected` je Farbe + Summe).

### Plots (nach `scripts/analyze.py`)

`leading_over_time.png`, `trades_per_round.png`, `cost_per_agent.png`.

## 11. Setup & Ausführen

```bash
# 1. Umgebung
uv venv
uv pip install -e ".[dev,analysis]"     # Code + Tests + Plots

# 2. API-Key (für echte LLM-Läufe)
cp .env.example .env                      # dann MISTRAL_API_KEY eintragen
```

LiteLLM liest die Provider-Keys automatisch aus der Umgebung (`.env`).

```bash
# API-freier Trockenlauf (nur Heuristik, kostenlos, deterministisch)
skittles run -c config/dry-run.yaml --verbose

# Kurzer echter Mistral-Lauf (braucht MISTRAL_API_KEY)
skittles run -c config/mistral-smoke.yaml --verbose

# Voller Lauf
skittles run -c config/experiment.yaml --verbose

# Ohne Editable-Install
PYTHONPATH=src python -m skittles.cli run -c config/dry-run.yaml -v
```

`--verbose` zeigt pro Runde Trades und den führenden Bestand je Agent. Am Ende
folgt der Endstand mit Sieger, Trades und Kosten.

## 12. Auswertung

```bash
python scripts/analyze.py runs/<timestamp>
```

Erzeugt die drei Plots direkt im Lauf-Verzeichnis. Für eine erzählende
Auswertung siehe die konsolidierten Berichte in `reports/`.

## 13. Provider mischen

Provider-Wechsel ist reine Config-Sache (LiteLLM-Abstraktion). Beispiel:

```yaml
agents:
  - id: gpt
    type: llm
    provider: openai
    model: gpt-4o
  - id: claude
    type: llm
    provider: anthropic
    model: claude-sonnet-4-6
  - id: mistral
    type: llm
    provider: mistral
    model: mistral-large-latest
  - id: baseline
    type: heuristic
```

Die jeweiligen Keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …) gehören in die
`.env`.

## 14. Tests

```bash
pytest          # 31 Tests, < 1 s, kein Netz nötig
```

Abgedeckt:

- **`test_order_book.py`** — Preis-Zeit-Priorität, Aggregation der Buch-Levels.
- **`test_exchange_matching.py`** — Crossing, Maker-Preis-Ausführung,
  Teilausführung, Käufer-Rückerstattung, Ablehnung ungültiger Orders.
- **`test_escrow_invariants.py`** — Erhaltung über 2000 zufällige Orders/Cancels.
- **`test_fees.py`** — Gebühr auf beiden Seiten, Tresor, Erhaltung inkl. Tresor
  unter Last.
- **`test_scoring.py`** — Sieger-Ermittlung, Tie-Breaks, Wertung nur auf
  `available`.
- **`test_forum.py`** — Posten, geteilter Feed, Nachrichten-Cap, Tool-Verdrahtung,
  An/Aus-Schalter.
- **`test_llm_agent.py`** — Tool-Loop, Kostenerfassung, Budget-Gate, Fehler-
  Robustheit — alles mit injizierter Fake-Completion, **ohne echte API-Calls**.

## 15. Bisherige Ergebnisse

Der erste größere Lauf ist eine **Temperatur-Studie**: 5× `mistral-large` und 5×
`mistral-small` (je eigene Temperatur) plus Heuristik-Baseline, 25 Runden. Der
vollständige Bericht liegt unter
[`reports/temperature-study.md`](reports/temperature-study.md). Kernbefunde:

- **Sieger:** `large-t03` (mistral-large, Temp 0.3) mit 93× Gelb — gewann durch
  **frühe, konsequente Festlegung** auf eine Zielfarbe.
- **Das kleinere Modell war im Schnitt besser** (Ø 81.2 vs. 68.8 führende
  Skittles) und ~6× günstiger pro Score-Punkt.
- **Mittlere Temperaturen (0.3–0.6) dominierten**; sehr niedrige (0.1) wurde
  Letzter.
- Die **kostenlose Baseline schlug 8 von 10 LLMs** im Kosten-Nutzen-Verhältnis —
  ein nüchterner Realitäts-Check.

## 16. Erweitern

- **Neuer Agententyp:** von `Agent` (`agents/base.py`) erben, `act(ctx)`
  implementieren, im Factory in `engine.py` registrieren.
- **Andere Gebühr/Regeln:** `fee_rate` in der Config; die Mechanik sitzt in
  `Exchange._settle` / `Exchange._fee`.
- **Mehr/andere Modelle:** Agenten in der Config ergänzen (siehe §13).
- **Statistik über viele Seeds:** denselben Lauf mit variierenden Seeds
  wiederholen und mitteln (geplant als Batch-Skript).
- **W&B-Logging:** als optionale Erweiterung vorgesehen, aktuell nicht im Kern.

## 17. Limitationen & Forschungs-Hinweise

- **Reproduzierbarkeit:** `seed` macht Anfangsverteilung und Zugreihenfolge
  deterministisch — die **LLM-Antworten bleiben nicht-deterministisch**, das ist
  die untersuchte Variable. Einzelne Läufe sind daher anekdotisch; für belastbare
  Aussagen über viele Seeds mitteln.
- **Gekoppelte Umgebung:** Agenten beeinflussen sich gegenseitig; die Stärke
  eines Agenten hängt auch vom Feld ab.
- **Gleichgewicht:** Sind alle Minderheitsfarben verkauft, versiegt der Handel —
  Farben, die niemandes Ziel sind (oft Blau/Orange), finden keine Gegenseite.
- **Kein Gedächtnis:** Agenten beobachten den Markt jede Runde neu, ohne Verlauf —
  beobachtetes „Hin-und-Her" kann teils Artefakt der zustandslosen Beobachtung
  sein.
- **Kosten:** Richtwert ~$0.0036 pro Runde mit large+small; `mistral-large` macht
  den Großteil aus. `max_cost_usd` ist die harte Bremse.
