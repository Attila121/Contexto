# Instruction study (no hint): details

Part of [PROGRESS.md](../PROGRESS.md). Collected 21 November 2026; reviewed 23 November.

## What happened

1. Built the batch runner (`study_batch.py`) and analysis (`study_analysis.py`) with a frozen manifest, request ledger, process lock and offline tests (57).
2. Pilot on 23-24 Oct, both conditions: passed 56 audit checks, 117 requests.
3. Production: 150 games over 25 dates, collected by 21 November. Three interruptions (two cookie-preference overlays during probes, one duplicate-lemma panel on 30 Oct guided rep 1, turn 17) were recovered by replaying saved answers; the reader fixes are saved as three archived source revisions.
4. Audit PASS; results, trajectories and target scores written; reviewed on 23 November, including the closeness analysis below.
5. Its 75 control games were later reused (unchanged) as the comparison group for the [hint follow-up](hint_study.md).

## Results

- Design: 25 dates (26 Oct-19 Nov 2026) x control/guided x 3 repetitions = 150 games, 30 attempts each, Gemini 3.8 Flash, frozen settings. All 150 strategy reports saved. **Production audit: PASS.**
- Run: [runs/20261120T213300Z_instruction_study_5625ddd2](../runs/20261120T213300Z_instruction_study_5625ddd2/README.md) (`AUDIT.md`, `results.csv`, `trajectories.csv`, `target_scores.csv`, `strategy_reports.csv`, `human_targets.csv`).
- Pilot (23-24 Oct, both conditions): 56 audit checks passed; 117 requests, no retries.
- Requests: 4,327/4,824 including the pilot, all returned; 0/50 transport retries.
- Control solved 18/75 (24.0%), guided 15/75 (20.0%). Median best rank at attempt 30: 42 vs 28. Mean guesses to solve (solved games): 17.8 vs 15.3. Invalid attempts: 93 in 48 control games, 128 in 54 guided games.
- Paired ordinal trajectory score **0.566, 95% bootstrap CI 0.492-0.636** (includes 0.5). Per-target scores 0.10-0.91.
- Closeness: 33/150 solved; 40/150 reached rank <=10, 82/150 <=50, 104/150 <=100, 144/150 <=300. Among 117 unsolved games the median best rank was 64. 13/25 targets were solved at least once.
- Interruptions: two cookie overlays (probes) and one duplicate-lemma panel (30 Oct, guided rep 1, turn 17), recovered by replaying saved answers. Reader fixes are three archived source revisions in `source_amendments.json`.
- Code: `study_batch.py`, `study_analysis.py`, optional protocol parameters in `gemini_trial.py`, reader fixes in `automated_game.py`.
- Earlier data stay separate: the 10-game 70-attempt run (1/10 solved by 30, 5/10 by 70) and older pilots.

## Protocol

- Control/guided wording frozen in the manifest; stateless full-history prompts, newest first; fresh browser per game; invalid, duplicate and rejected outputs use attempts.
- Ordinal score: guided win = 1, tie = 0.5, loss = 0, over 9 repetition pairs x 30 turns, then equally over targets. 10,000 whole-target bootstrap samples, seed 20261120.

## Limitations

- 25 targets with repeated runs, not 150 independent puzzles; nine dates overlap the earlier pilot.
- Live Contexto scoring is not frozen; sentinel and repeated-word checks detect only some drift.
