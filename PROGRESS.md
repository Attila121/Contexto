# Contexto progress

Updated: 21 November 2026.

## Done

- **AI instruction study collected and audited.** 25 dates (26 October–19 November 2026) × control/guided × 3 repetitions = **150/150 production games**, 30 attempts each, Gemini 3.8 Flash with the frozen settings. All 150 strategy reports were saved. **Production audit: PASS.** Run: [runs/20261120T213300Z_instruction_study_5625ddd2](runs/20261120T213300Z_instruction_study_5625ddd2/README.md) (`AUDIT.md`, `results.csv`, `trajectories.csv`, `target_scores.csv`, `strategy_reports.csv`, `human_targets.csv`).
- Separate pilot (23–24 October × both conditions): passed 56 audit checks; 117 requests, no retries.
- Requests: **4,327/4,824** in total (pilot included), every one returned; **0/50** transport retries; no API failures.
- Results:
  - Control solved 18/75 (24.0%); guided solved 15/75 (20.0%).
  - Median best rank at attempt 30: 42 (control) vs 28 (guided).
  - Mean guesses to solve, solved games only: 17.8 vs 15.3.
  - Invalid attempts: 93 in 48 control games; 128 in 54 guided games.
  - Paired ordinal trajectory score: **0.566, 95% bootstrap interval 0.492–0.636**. Guidance leans towards better trajectories, but the interval includes 0.5. Per-target scores range from 0.10 to 0.91.
- Interruptions: two cookie-preference overlays (during probes) and one duplicate-lemma panel (30 October, guided repetition 1, turn 17). All were recovered by replaying saved answers; no answer was regenerated. Reader fixes are recorded as three archived source revisions in `source_amendments.json`. Prompts, settings, schedule, budgets and analysis are unchanged.
- Code: `study_batch.py`, `study_analysis.py`, optional protocol parameters in `gemini_trial.py`, reader fixes in `automated_game.py`. **57 offline tests pass**; `git diff --check` is clean. No dependencies added.
- Earlier data remain separate (not pooled): the 10-game 70-attempt evaluation (5/10 solved) and older pilot/debug runs.

## Next

1. Optional AI analysis: read the strategy reports and early guess sequences by condition (diversity annotation is still to do; word counts alone are not semantic diversity). Compare per-target scores with the sentinel drift checks.
2. Human study on the same 25 dates (`human_targets.csv`). The planned design is 10 people, 5 per condition, 5 distinct games each. Check live feedback stability against the archived sentinel ranks before collecting.
3. Write up for the course: AI results and limitations, then the human-vs-AI comparison.

## Protocol reminders

- Control/guided wording is frozen in the manifest; stateless full-history prompts, newest first; fresh browser per game; invalid, duplicate and rejected outputs consume attempts.
- Primary outcome: best-so-far rank trajectory. Ordinal score: guided win = 1, tie = 0.5, loss = 0, averaged over 9 repetition pairs × 30 turns, then equally over targets. 10,000 whole-target bootstrap samples, seed 20261120.

## Open decisions and limitations

- Live Contexto scoring is not frozen. Sentinel and repeated-word checks detect only some drift.
- Exploratory: 25 targets with repeated runs, not 150 independent puzzles. Nine dates overlap the earlier pilot.
- With 10–20 humans, the human-AI difference in guidance effects will remain uncertain.
- Human session length and recruitment are not yet decided.
- Thought summaries and self-reports are not full internal reasoning.
- The Contexto `.git` folder is owned by the former sandbox user. Git commands need `-c safe.directory=<path>` (no global config change was made).

## Research references

- [WordPolo](https://arxiv.org/html/2609.19006v1): 1,500 puzzles; 50 human/model comparison targets; 100 guesses, GloVe scoring.
- [BOPRO, section 7.1](https://proceedings.iclr.cc/paper_files/paper/2025/file/a79237d6c47feef24c1df723cb41f674-Paper-Conference.pdf): 10 Semantle targets × 5 warm starts × 3 repeats = 150 runs/method.
- [MTGBench](https://aclanthology.org/2026.findings-emnlp.1333.pdf): 100 shared episodes per game/configuration.
- [Adding Error Bars to Evals](https://arxiv.org/html/2411.00640v1): separate target variation from generation randomness; preserve pairing.
- [NIST TN 2119](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2119.pdf): about 100 independent targets for roughly ±10-point solve-rate precision.
