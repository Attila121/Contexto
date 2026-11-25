# Contexto progress

Updated: 23 November 2026 (hint follow-up collected, audited and analysed).

Current state only. Details are in the sub-progress files: [instruction study](progress/instruction_study.md), [hint follow-up](progress/hint_study.md), [references](progress/references.md). When this file grows beyond about 6 KB, move details into a sub-file instead.

## Done

- **Instruction study (no hint):** 150 games (25 dates x control/guided x 3), audit PASS. Control solved 18/75, guided 15/75; paired score 0.566, CI 0.492-0.636 (includes 0.5). [Details](progress/instruction_study.md)
- **Optional-hint follow-up:** 25 games, audit PASS, 717/874 requests, no retries or exclusions. Hint-enabled solved 12/25 (48%) vs archived control 18/75 (24%); median best rank 2 vs 42; paired score **0.696, CI 0.583-0.800**. [Details](progress/hint_study.md)
- **Hint mechanism (offline):** the model always took the free hint almost immediately. Part of the lead comes from a changed opening word (prompt confound); the rest looks mainly like a head start. A site hint at rank ~300 beat a self-found <=300 word over the next 15 guesses. [Details](progress/hint_study.md#mechanism)
- Code: unit tests and `git diff --check` pass; no dependencies added.
- Shared with team (25 Nov): all code, docs and `results/` summaries pushed to GitHub; raw `runs/` zipped separately as `../Contexto_raw_runs.zip` (559 MB), uploaded to Google Drive (link in README).

## Next

1. Optional: design the hint-strategy experiment (fresh control with the same hint paragraph; forced, stuck-triggered and costly hints). Write a spec before running.
2. Optional AI analysis: strategy reports and early guess sequences by condition; compare per-target scores with sentinel drift checks.
3. Human study on the same 25 dates: web app (GitHub Pages + Cloudflare Worker proxy to the Contexto API, logging timing and hints). Draft spec: [human_study/SPEC.md](human_study/SPEC.md); decide its open decisions D1-D7 before building. 10 people x 5 games, balanced so each date is played once per group.
4. Course write-up: AI results and limitations, then human vs AI.

## Open decisions and limitations

- The hint result compares with archived controls that used a prompt without the hint paragraph; it tests "free hint available", not timing or difficulty.
- Live Contexto scoring is not frozen; sentinel checks detect only some drift.
- 25 targets with repeated runs, not independent puzzles. With 10-20 humans the human-AI difference will stay uncertain.
- Human session length and recruitment are not decided.
- Thought summaries and self-reports are not full internal reasoning.
- The Contexto `.git` folder is owned by the former sandbox user; Git needs `-c safe.directory=<path>`.
- `runs/_discarded_20261123T175056Z_hint_study_6a4a52e3` can be deleted (no model requests).
