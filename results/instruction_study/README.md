# Contexto instruction study

Completed **150/150** production games; usable strategy reports: 150.
25 targets, two conditions, three repetitions, 30 attempts. Earlier runs are not pooled.

| Condition | Completed | Solved | Solve rate |
| --- | ---: | ---: | ---: |
| control | 75/75 | 18 | 24.0% |
| guided | 75/75 | 15 | 20.0% |

## Paired ordinal trajectory comparison

{
  "targets": 25,
  "score": 0.5660000000000001,
  "ci95": [
    0.4918518518518519,
    0.6364444444444445
  ],
  "target_scores": {
    "2026-10-26": 0.8018518518518518,
    "2026-10-27": 0.3074074074074074,
    "2026-10-28": 0.6648148148148149,
    "2026-10-29": 0.5611111111111111,
    "2026-10-30": 0.6092592592592593,
    "2026-10-31": 0.3296296296296296,
    "2026-11-01": 0.1,
    "2026-11-02": 0.5314814814814814,
    "2026-11-03": 0.6814814814814815,
    "2026-11-04": 0.5148148148148148,
    "2026-11-05": 0.9092592592592592,
    "2026-11-06": 0.6814814814814815,
    "2026-11-07": 0.43333333333333335,
    "2026-11-08": 0.6425925925925926,
    "2026-11-09": 0.2722222222222222,
    "2026-11-10": 0.7925925925925926,
    "2026-11-11": 0.562962962962963,
    "2026-11-12": 0.5055555555555555,
    "2026-11-13": 0.7981481481481482,
    "2026-11-14": 0.4648148148148148,
    "2026-11-15": 0.6037037037037037,
    "2026-11-16": 0.4166666666666667,
    "2026-11-17": 0.7314814814814815,
    "2026-11-18": 0.5351851851851852,
    "2026-11-19": 0.6981481481481482
  },
  "bootstrap_samples": 10000,
  "seed": 20261120,
  "interpretation": "Above 0.5 favors guided; exploratory, resampling whole targets."
}

Only targets with all six games completed enter this comparison. Missing initial ranks compare as infinity; invalid attempts retain the best rank; solved games retain rank 1.
The confidence interval resamples targets, not individual repetitions. These are exploratory results on 25 dates, nine previously used in the 70-attempt pilot.

Live scoring is not frozen. Sentinel checks detect some changes but do not prove stability.
See manifest.json, requests.jsonl, checks/, trajectories.csv and per-game records.
Returned thought summaries and postgame self-reports are not full internal reasoning.
