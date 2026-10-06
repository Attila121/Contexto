# Contexto

A Gemini player for [Contexto](https://contexto.me/). Choose a puzzle date and let
it guess automatically, or enter the website's ranks yourself in manual mode.

## Setup

Run these PowerShell commands from the repository folder (`Project/Contexto` in
this workspace):

```powershell
conda env create --prefix ./.conda --file environment.yml
if (!(Test-Path .env)) { Copy-Item .env.example .env }
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.conda/browsers'
conda run --prefix ./.conda python -m playwright install chromium
```

Put your [Gemini API key](https://aistudio.google.com/apikey) after
`GEMINI_API_KEY=` in `.env`. Keep this file local; API calls may cost money.

## Play

```powershell
conda run --no-capture-output --prefix ./.conda python automated_game.py 2026-09-30
```

Omit the date to be prompted. Games stop when solved or after 30 attempts.
Use `--show-browser` to watch, `--max-guesses 5` for a shorter run, or
`--model MODEL_ID` to choose another compatible model. Ctrl+C stops the game.

Choose memory with `--memory explicit` or `--memory linked`:

| Mode | What Gemini receives |
| --- | --- |
| `explicit` (default) | Instructions and all previous guesses and ranks on every turn. |
| `linked` | Google's stored conversation via `previous_interaction_id`, plus the latest feedback. |

Every game starts fresh. To try linked memory, append `--memory linked` to the
command above.

For manual play:

```powershell
conda run --no-capture-output --prefix ./.conda python gemini_trial.py
```

Enter each suggested word on Contexto, then type its positive integer rank,
`invalid` if rejected, or `quit` to stop.

## Results and experiments

Each game saves `events.jsonl`, `turns.csv`, and a readable `timeline.md` under
`runs/`. Automated games also save browser HTML and screenshots. Logs include
prompts, feedback, usage, and any returned **thought summaries**; these are not
full internal reasoning and may be absent.

See [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md) for ideas to explore. Gemini is
proprietary, so this trial remains separate from the planned open-weight study.
Only the two memory modes are currently implemented.

`.env`, runs, and downloaded `Contexto_files` assets are excluded from Git.
API errors stop the game without automatic retries.

Offline checks:

```powershell
conda run --prefix ./.conda python -m unittest discover -s . -p 'test_*.py'
```
