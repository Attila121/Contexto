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

Omit the date to be prompted. Games stop when solved or after 70 attempts.
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

`runs/` is not in Git (about 1.6 GB). Summary files of the two audited studies
are tracked in [results/instruction_study](results/instruction_study/) and
[results/hint_study](results/hint_study/) (results, per-target scores, guess
trajectories, strategy reports, audits). The scoring evidence
(`runs/scoring_*`) is tracked too, except third-party copies. The literature
review and analysis plan are in [docs/research](docs/research/). Other
`runs/...` links below work only with the full raw logs, which are shared separately as a zip
(`Contexto_raw_runs.zip`,
[Google Drive folder](https://drive.google.com/drive/folders/1wfoKKR-jA8gTIdhg64-O-iU1vi7iQb06?usp=sharing));
unzip it into the project folder.

### 150-game instruction study

Records: [study results](runs/20261120T213300Z_instruction_study_5625ddd2/README.md),
[production audit](runs/20261120T213300Z_instruction_study_5625ddd2/AUDIT.md),
[pilot audit](runs/20261120T213300Z_instruction_study_5625ddd2/PILOT_AUDIT.md).
The separate four-game pilot passed all 56 audit checks (117 requests, no retries).

**Collection complete (21 November 2026): 150/150 production games and 150
strategy reports; production audit PASS.** The study used 4,327 of 4,824 requests
(pilot included), all returned, with 0/50 transport retries.

| Condition | Solved | Median best rank at 30 | Mean guesses to solve | Invalid attempts (games affected) |
| --- | ---: | ---: | ---: | ---: |
| control | 18/75 (24.0%) | 42 | 17.8 | 93 (48) |
| guided | 15/75 (20.0%) | 28 | 15.3 | 128 (54) |

Paired ordinal trajectory score (guided vs control, 25 complete targets):
**0.566, 95% whole-target bootstrap interval 0.492–0.636.** This leans towards
better best-so-far ranks under guidance, but the interval includes 0.5. Solve
rates point slightly the other way. Per-target scores range from 0.10 to 0.91.
The result is exploratory and does not establish an effect of the instructions.

The smaller kickoff study uses the fixed **26 October–19 November 2026** dates:
25 targets × control/guided × three fresh repetitions, with **30 attempts** per
game. Nine dates overlap the earlier 70-attempt pilot; every study game is new.
Conditions use the kickoff wording and otherwise identical settings. The frozen
manifest records prompts, model, source hashes, schedule, and budgets.

```powershell
$studyDirectory = ./.conda/python.exe study_batch.py prepare
./.conda/python.exe -u study_batch.py pilot $studyDirectory --workers 2
./.conda/python.exe -u study_batch.py run $studyDirectory --workers 3
./.conda/python.exe study_batch.py audit $studyDirectory
```

Preparation is offline. The separate four-game pilot uses 23–24 October under
both conditions and must pass its audit before production. Live execution checks
the configured model without substitution. Keep the printed study directory;
use it for subsequent commands rather than preparing another batch.

Request ceilings: 4,500 production guesses, 150 postgame strategy reports,
124 pilot guesses/reports, and a shared 50-request transport-retry reserve:
**4,824 maximum**. Each request is journaled before dispatch; ambiguous requests
after a crash still count. There are no automatic model retries. Failed games
are not silently replaced. To explicitly prepare an interrupted game or report
for recovery, inspect its records, then run:

```powershell
./.conda/python.exe study_batch.py recover $studyDirectory --game GAME_ID_FROM_LOG
```

Run the same `pilot` or `run` command afterward. Returned answers are restored
from the durable journal and reused, not regenerated; browser replay must match
saved feedback. An OS-held study lock prevents concurrent runner processes.

An explicit operational reader correction can be recorded in
`source_amendments.json`, preserving the original manifest and verified archives
of both source versions. Unrecorded source changes still block execution. The
active batch records reader corrections for repeated-lemma panels and delayed
cookie-preferences dialogs, with each original/revised source version archived;
prompts, model settings, targets, attempt limits and analysis remain unchanged.
Three browser-side interruptions occurred during production (two cookie overlays
during probes, one duplicate-lemma panel at 30 October guided repetition 1,
turn 17). Each was recovered without regenerating any model answer.

Records include raw responses, prompts, usage, timings, returned thought summaries,
browser evidence, and separate postgame strategy reports. `results.csv` has game
outcomes; `trajectories.csv` has best-so-far ranks; `human_targets.csv` preserves
the shared dates. `target_scores.csv` and `results.json` contain the paired
ordinal comparison: guided wins score 1, ties 0.5, losses 0, averaged over all
nine repeat pairs and 30 attempts per target. Only complete six-game targets
enter the comparison. The interval uses 10,000 whole-target bootstrap samples.
These are exploratory results on 25 targets, not 150 independent puzzles.

Separate sentinel checks before/after each target group and repeated-word rank
checks detect some scoring changes. **Live Contexto scoring is not frozen**;
later human collection must use the same targets and check feedback stability.
Postgame reports and returned thought summaries are not full internal reasoning.

### Earlier evaluation and scoring evidence

- [Scoring and comparability review, updated 5 November](SCORING.md)
- [Preserved scoring investigation and independent checks](runs/scoring_investigation_20261105/README.md)

- [10-puzzle evaluation with a 70-attempt limit](runs/20261104T121421Z_evaluation_8bc0e311/README.md)
- [Frozen schedule and protocol](runs/20261104T121421Z_evaluation_8bc0e311/manifest.json)
- [30/70 cutoff comparison](runs/20261104T121421Z_evaluation_8bc0e311/BUDGET_COMPARISON.md)
- [Final verification report](runs/20261104T121421Z_evaluation_8bc0e311/AUDIT.md)

The 4 November batch completed all 10 games: **5/10 solved**, averaging **40.4
attempts on solved games**. One was solved by attempt 30; four additional games
were solved by attempt 70. There were 552 returned model responses and one
separately logged transport timeout (553 requests in total).

For the paper-inspired evaluation, freeze a schedule of 10 fresh daily puzzles,
then execute it with a 70-attempt limit:

```powershell
./.conda/python.exe evaluate_batch.py prepare --start-date 2026-10-25 --games 10 --max-guesses 70 --model gemini-3.8-flash
./.conda/python.exe -u evaluate_batch.py run runs/BATCH_DIRECTORY_PRINTED_ABOVE
```

Preparation makes no browser or model requests and rejects dates used in earlier
local game logs. Execution starts each game in a fresh browser context and model
session, sends full history newest first, and counts invalid/repeated outputs
against the budget. It extracts the final whitespace-separated answer token,
requiring letters only, following the paper's final-word approach. Existing
single-game commands retain their strict one-word parser and stop-on-output-error
behavior. Up to three independent game workers run in parallel, each owning its
client, browser and context (`--workers 1` selects sequential play). On an
API/browser error, no new games start; already running games finish. There are no
automatic retries. Finished games are skipped when re-running the same batch;
unfinished games are not retried automatically.

If saved browser evidence proves that a stopped game encountered an ordinary
invalid-word rejection, `evaluate_batch.py recover-rejection runs/BATCH_DIRECTORY`
can append a documented correction without repeating its model call. A subsequent
run restores the browser history, checks its ranks against the saved records, and
continues from the next attempt. The original records and manifest stay intact;
execution corrections record the updated source hashes separately.

`recover-operational` explicitly prepares a stopped browser/API game to continue.
A saved unscored answer is submitted again to the website without another model
call. An API transport timeout with no returned answer can be retried explicitly;
the extra request is logged separately and is not scored as a wrong guess. The
runner checks the original total model-request cap before continuing. None of
these recoveries runs automatically.

The batch README, results.csv and results.json report outcomes, best rank and mean
progression. Incomplete games remain separate. Normalized proximity and weighted
progression require a verified vocabulary size and are not calculated for the live
website. This uses Contexto's rankings and new daily targets, rather than the
paper's GloVe environment and target set; it is an adaptation, not an exact
replication or a matched GPT-4.1 comparison. See the frozen manifest for all settings.

Each game saves `events.jsonl`, `turns.csv`, and a readable `timeline.md` under
`runs/`. Automated games also save browser HTML and screenshots. Logs include
prompts, feedback, usage, and any returned **thought summaries**; these are not
full internal reasoning and may be absent.

See [EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md) for ideas to explore. Gemini is
proprietary, so this trial remains separate from the planned open-weight study.
The single-game commands expose the two memory modes; the dedicated study runner
adds the fixed control/guided comparison described above.

`.env`, runs, and downloaded `Contexto_files` assets are excluded from Git.
API errors stop the game without automatic retries.

Offline checks:

```powershell
conda run --prefix ./.conda python -m unittest discover -s . -p 'test_*.py'
```
