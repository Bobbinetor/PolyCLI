# Polymarket CLI Guide

This file is the canonical usage guide for the project.

Rule:
- Whenever commands, flows, slash commands, prompts, scheduler behavior, or terminal UX change, update this file in the same change.

## What this project is

Polymarket CLI is a terminal-first workspace for:
- discovery on Polymarket via Gamma API
- recurring keyword jobs
- CSV snapshot generation
- LLM ranking on saved datasets
- public live market streaming
- paper trading simulation
- an interactive terminal console with slash commands

## Current interaction model

There are two ways to use the project.

1. Standard CLI commands from the shell.
2. Interactive terminal console via `uv run polymarket tui` or `uv run polymarket console`.

The interactive console is the preferred operator experience. It includes:
- live dashboard panels
- slash-command input
- activity log
- integrated websocket feed
- keyboard shortcuts

## Setup

1. Install dependencies:

```bash
uv sync --extra dev
```

2. Create local environment settings if needed:

```bash
cp .env.example .env
```

3. Check configured watchlists:

```bash
uv run polymarket watchlists list
```

## Fast start

1. Generate a snapshot:

```bash
uv run polymarket discover keywords bitcoin election --label smoke --limit 10
```

2. Rank the saved snapshot in heuristic mode:

```bash
uv run polymarket rank latest smoke --dry-run
```

3. Launch the interactive console:

```bash
uv run polymarket tui --label smoke
```

Or:

```bash
uv run polymarket console --label smoke
```

## Standard CLI commands

### Watchlists

```bash
uv run polymarket watchlists list
uv run polymarket watchlists add
uv run polymarket watchlists edit crypto-headlines
uv run polymarket watchlists enable crypto-headlines
uv run polymarket watchlists disable crypto-headlines
uv run polymarket watchlists remove crypto-headlines --yes
```

### Discovery

```bash
uv run polymarket discover keywords bitcoin macro --label smoke --limit 5
uv run polymarket run-job crypto-headlines
```

### Scheduler

```bash
uv run polymarket scheduler jobs
uv run polymarket scheduler once
uv run polymarket scheduler once --name crypto-headlines
uv run polymarket scheduler start --cycles 4
uv run polymarket scheduler install crypto-headlines
uv run polymarket scheduler remove crypto-headlines
```

### Ranking

```bash
uv run polymarket rank latest smoke --dry-run
uv run polymarket rank latest smoke --provider ollama
uv run polymarket rank latest smoke --provider openrouter
```

### Paper trading

```bash
uv run polymarket paper enter --event-id 1 --market-id m1 --outcome Yes --size 10 --price 0.42
uv run polymarket paper positions
uv run polymarket paper close POSITION_ID --exit-price 0.55
```

### Feed only

```bash
uv run polymarket stream latest smoke --limit 10
```

## Interactive console

Launch it with:

```bash
uv run polymarket tui --label smoke
```

or:

```bash
uv run polymarket console --label smoke
```

### Keyboard shortcuts

- `r`: refresh dashboard panels
- `s`: restart websocket feed
- `q`: quit

### Slash commands

All interactive commands start with `/`.

### Core

```text
/help
/refresh
/label smoke
/label clear
/stream restart
/stream stop
/quit
```

### Discovery from inside the console

```text
/discover bitcoin election label=smoke limit=5
/discover trump fed label=macro-live limit=20
```

Behavior:
- saves a fresh raw JSON snapshot
- saves `events.csv` and `markets.csv`
- updates the dashboard label focus
- restarts the integrated live feed on the new snapshot

### Ranking from inside the console

```text
/rank label=smoke provider=ollama dry_run=true
/rank label=smoke provider=openrouter prompt=default-ranking.md
```

### Watchlist management from inside the console

```text
/watch list
/watch add alpha keywords=bitcoin,fed every=15 limit=12 live=true enabled=true
/watch edit alpha keywords=bitcoin,fed,election every=20
/watch enable alpha
/watch disable alpha
/watch remove alpha
```

Supported watch options:
- `keywords=bitcoin,fed`
- `every=15`
- `limit=25`
- `live=true|false`
- `closed=true|false`
- `enabled=true|false`
- `tags=crypto,macro`
- `prompt=default-ranking.md`

### Job execution from inside the console

```text
/job list
/job run crypto-headlines
/job run
```

`/job run` without a name runs all enabled watchlists once.

### Paper trading from inside the console

```text
/paper positions
/paper positions all=true
/paper enter event=1 market=m1 outcome=Yes side=buy size=10 price=0.42
/paper enter event=1 market=m1 outcome=Yes side=buy size=10 label=smoke
/paper close POSITION_ID 0.55
```

If `price` is omitted, the console tries to infer it from the latest `markets.csv` for the selected label.

## Files and data layout

- `config/watchlists.yaml`: editable keyword jobs
- `config/prompts/default-ranking.md`: prompt template for ranking
- `data/raw/<label>/...json`: raw discovery payloads
- `data/processed/<label>/<run-id>/events.csv`: normalized events snapshot
- `data/processed/<label>/<run-id>/markets.csv`: normalized markets snapshot
- `exports/<label>/ranking.json`: latest ranking report
- `.local/state.db`: watch jobs, discovery runs, ranking runs, paper positions

## Notes

- Gamma discovery is unauthenticated and uses `/public-search` plus `/events/keyset`.
- The console auto-starts the public market websocket from the latest discovery snapshot for the active label.
- Live order placement is intentionally not implemented. Trading is paper-only for now.

## Testing

Run all tests:

```bash
uv run pytest
```

Minimal manual test flow:

```bash
uv run polymarket discover keywords bitcoin election --label tui-smoke --limit 5
uv run polymarket rank latest tui-smoke --dry-run
uv run polymarket tui --label tui-smoke
```

Inside the console, then try:

```text
/help
/watch list
/rank label=tui-smoke dry_run=true provider=ollama
/paper positions
```

## Flusso completo pratico

Questo e` il flusso end-to-end consigliato per usare il progetto da zero fino alla TUI interattiva.

1. Installa le dipendenze:

```bash
uv sync --extra dev
```

2. Crea il file ambiente locale se vuoi configurare Ollama o OpenRouter:

```bash
cp .env.example .env
```

3. Controlla o crea una watchlist:

```bash
uv run polymarket watchlists list
uv run polymarket watchlists add
```

Esempio watchlist pratica:
- nome: crypto-headlines
- keywords: bitcoin, ethereum, solana
- poll interval: 20
- limit: 25
- live only: yes
- include closed: no
- enabled: yes

4. Fai una discovery iniziale manuale per avere subito dati da vedere:

```bash
uv run polymarket discover keywords bitcoin election --label demo --limit 8
```

Questo comando salva:
- raw JSON in `data/raw/demo/...json`
- eventi in `data/processed/demo/.../events.csv`
- mercati in `data/processed/demo/.../markets.csv`

5. Fai una scrematura iniziale dei risultati:

```bash
uv run polymarket rank latest demo --dry-run
```

Se hai Ollama o OpenRouter configurati, puoi usare anche:

```bash
uv run polymarket rank latest demo --provider ollama
uv run polymarket rank latest demo --provider openrouter
```

6. Avvia la TUI interattiva con il label appena creato:

```bash
uv run polymarket tui --label demo
```

7. Dentro la TUI usa questo percorso pratico:

```text
/help
/watch list
/discover bitcoin fed label=macro limit=6
/rank label=macro provider=ollama dry_run=true
/paper positions
/stream restart
```

8. Esempio pratico completo dentro la TUI:

```text
/discover bitcoin election label=demo limit=5
/rank label=demo provider=ollama dry_run=true
/paper enter event=1 market=m1 outcome=Yes side=buy size=10 label=demo
/paper positions
```

9. Se vuoi automatizzare la discovery:

```bash
uv run polymarket scheduler jobs
uv run polymarket scheduler once --name crypto-headlines
uv run polymarket scheduler install crypto-headlines
```

10. Se vuoi solo il feed live senza TUI:

```bash
uv run polymarket stream latest demo --limit 10 --max-messages 20
```

Riassunto operativo:
- usa `discover` per creare snapshot
- usa `rank` per scremare gli eventi piu` interessanti
- usa `tui` per controllare feed live, slash commands e stato dei job
- usa `paper` per simulare entrate e uscite
- usa `scheduler` per rendere persistente il processo di discovery

