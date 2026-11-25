# Optional-hint follow-up: details

Part of [PROGRESS.md](../PROGRESS.md). Collected and audited 23 November 2026.

## What happened (23 November 2026)

1. **Tests first:** wrote `test_hint_study.py` (53 tests: parsing, prompt and eligibility, frozen protocol, controller, recovery, ledger, comparison, end-to-end with a fake site), then `hint_study.py` and `hint_analysis.py`. A test bug was found and fixed on the way: filler words like "w0" contain digits and counted as invalid output, so some tests had passed for the wrong reason; they now use letters-only words. Full suite: 110 tests pass.
2. **First preparation discarded:** the browser probe failed because the hint reader treated the site's temporary "Calculating..." panel as an error. Fixed the reader, which changed the source hashes, so the run was prepared again. The first directory (`_discarded_20261123T175056Z_...`) made no model requests.
3. **Probe (browser only, 23-24 Oct):** passed. Hint in Menu -> Hint, default difficulty Easy; the guess counter did not change; the hint was identical in fresh browser contexts and after reload; guessing the hint word was rejected.
4. **Pilot (23-24 Oct):** audit PASS, 52 requests. 23 Oct solved in 18 attempts; 24 Oct reached rank 2. Both took the hint after guess 1.
5. **Production, first run:** 13 games completed, then it stopped before the 8 Nov game. While replaying archived control 2, the site returned "Oops... there was an error!". As designed it stopped without substituting a target; no model request had been made for that date.
6. **Production, second run (same run resumed):** the 8 Nov replay passed and play continued. It stopped again on 18 Nov: the site did not answer after guess 22 ("savior"), a 45 s browser timeout. The hint had already been delivered.
7. **Recovery:** `recover --game hint_production_2026-11-18` restored the saved answers from the request journal; the resumed run replayed the website actions and finished the game without regenerating any answer.
8. **Finished:** 25/25 games, 717/874 requests, 0 retries, audit PASS. `summarize` wrote the comparison tables.
9. **Follow-up questions:** the hint timing table showed the model nearly always asked at guess 1; this was not planned. Offline mechanism analysis (`hint_mechanism.py`) then found the opener confound and the anchor comparison below.
10. **Progress files** split into this folder because `PROGRESS.md` passed about 6 KB.

## Results

- Run: [runs/20261123T175122Z_hint_study_a22ab6a8](../runs/20261123T175122Z_hint_study_a22ab6a8/README.md) (`AUDIT.md` PASS, `results.json`, `target_scores.csv`, `trajectories.csv`, `strategy_reports.csv`).
- Design: 25 new games, one per date (26 Oct-19 Nov), same model, settings and control instructions as the archived study, plus one paragraph allowing one real website hint (`[HINT]`). 30 guesses; the hint does not use a guess.
- Probe (23-24 Oct): site default is Hints = Easy; hint deterministic, survives reload, does not change the guess counter.
- Pilot (23-24 Oct): audit PASS, 52 requests. Production: 25/25, 717/874 requests in total, 0/10 retries, no exclusions; every target passed baseline replay and sentinel checks.
- Hint-enabled solved 12/25 (48%) vs matched archived control 18/75 (24%): +24 points. Median best rank 2 vs 42; top-10 68% vs 25.3%; top-50 88% vs 53.3%; top-100 96% vs 65.3%; invalid attempts 19 vs 93.
- Paired ordinal score **0.696, 95% bootstrap CI 0.583-0.800** (10,000 whole-target samples, seed 20261123). Per-target 0.11-1.00 (lowest: 13 Nov, 7 Nov, 18 Nov).
- Hint usage: 25/25 requested it (22 after guess 1, others after guesses 2, 5 and 7); none ineligible; no answer revealed by hint; no non-user group.
- Request time: 640 requests, mean 8.6 s, median 6.2 s.
- Interruptions (no answer regenerated): website error during the 8 Nov control replay, before any model request (resumed, replay passed); browser timeout on 18 Nov after guess 22 (`recover`, then resume).

## Hint timing (not planned)

- The prompt never says when to ask. The hint is free and unlocks after guess 1, so the model asked at once; its reports say it wanted an early "semantic anchor".
- Easy hints seem capped at rank 300 (14 games got exactly 300; with best rank under ~600 the hint was about half).
- The hint beat the model's best rank in 25/25 games, and the best rank improved afterwards in 25/25.

## Mechanism

Offline analysis: `hint_mechanism.py` writes `mechanism/MECHANISM.md` and three CSVs in the run directory.

1. **Opener confound:** the hint paragraph changed the first guess (person 18/25 vs water 64/75 in controls), so the lead at attempt 1 (score 0.68) is a prompt effect, not hint information. The gap peaks at guess 3 (0.79), then stays roughly level: mostly a head start.
2. **Hint vs self-found anchor (rank <=300):** every control game found one, usually by guess 5 (median rank 163). Over the next 15 guesses: median best 14 (hint) vs 45.5 (control); solved 5/25 vs 11/68. Confounded by opener and anchor timing.
3. **Use of the hint word:** named in the thought summary in 24/25 games; the model searches the hint's topic loosely (40/125 next guesses at or better than the hint rank). Antonym-like hints sent it the wrong way (dry -> wet, desert; occasional -> frequent, sporadic), including weak targets.

## Limitations

- Archived controls were run three days earlier and use a prompt without the hint paragraph.
- One new repetition per target, 25 targets.
- Every game took the hint early, so this tests "free hint available", not timing or difficulty.
- Thought summaries and reports are partial self-reports.
- `runs/_discarded_20261123T175056Z_hint_study_6a4a52e3` made no model requests and can be deleted.

## Code

`hint_study.py`, `hint_analysis.py`, `hint_mechanism.py`, `test_hint_study.py` (new); original study files untouched. No dependencies added.

## Possible next experiment (not started)

A fresh control group run at the same time **with the same hint paragraph** but no hint delivered, plus fixed-strategy groups: hint forced after guess 1 or 10, hint when stuck (no improvement in 5 guesses), and a costly hint (uses 3 guesses, model decides). A suggested pilot of about 10 dates x 3 groups needs about 930 requests.
