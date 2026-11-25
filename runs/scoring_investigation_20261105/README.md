# Preserved Contexto scoring investigation

Preserved and reviewed on **5 November 2026**. Start with the updated
[scoring note](../../SCORING.md), the [original report](ORIGINAL_REPORT.md),
and the [independent verification](review/VERIFICATION.json).

The original report is retained verbatim, including its provisional statements
and request to preserve the evidence. Later candidate-model outputs were already
present when this snapshot was copied; the review incorporates those files.

## What is preserved

| Location | Contents |
| --- | --- |
| [api/](api/) | Raw/cached responses, archived/live lists, replay samples, candidate comparisons and fixed-trajectory rescoring |
| [wayback/](wayback/) | Archived public frontend bundles, capture indexes and fetch logs |
| [paper/](paper/) | Paper PDF and extracted text |
| [web/](web/) | Saved public pages, including the creator interview and WordPolo demo |
| [wp/](wp/) | Demo JavaScript and download-list response |
| [scripts/](scripts/) | Original investigation scripts, copied without execution |
| [review/](review/) | Independently generated checks, candidate rank tables, prior scoring note and proposed-change diff |

[PRESERVATION.json](PRESERVATION.json) records the source location, timestamps,
file sizes and SHA-256 hashes for **175 files / 25,486,563 bytes**. All copied bytes
were checked against their source. Python bytecode, the environment, NLTK data,
full vector caches and multi-GB downloads were excluded. They remain external
inputs; this preservation did not delete or move them.

The additional [candidate rank tables](review/candidate_rank_tables.npz) are about
14 MB. They contain the 317,756-token vocabulary and rank arrays for the ten
study targets plus `mirror` and `banana`, not the full embedding matrix.

## Independent checks

The review ran offline against saved data and the existing GloVe cache. It made
no Contexto queries, downloads, or paid model calls. It did not execute the copied
network-probing scripts. It verified:

- All preserved source hashes, and all ten original study event-log hashes
  against the original completed-study audit.
- All 515 accepted recorded guesses against the saved rescoring rows.
- A fresh GloVe 6B 300d / cosine / ASCII-token reconstruction: **317,756 tokens**,
  **7/7 figure ranks**, **43/43 saved demo ranks**, and **515/515 rescored ranks**.
- Spearman correlation **0.78413275**, **127/505** direction disagreements, and
  median reconstructed/live rank ratio **2.97615**.
- `limited` against target `limit`: live rank 1; reconstructed rank 28.
- **37 unscored outputs:** 21 website lemma duplicates, 1 local exact duplicate,
  8 too-common rejections, 5 other exclusions, 2 malformed/empty outputs.
- All 34 website-rejected surface forms are in the reconstructed vocabulary and
  are not exact repeats of previous submitted tokens.
- 90/90 sampled study ranks replayed identically; 10/57 older sampled ranks changed.
- The saved Stanford GloVe credit in September 2022/February 2026 bundles and its
  absence in the saved March 2026 bundle.
- An observed rank of 78,902 and ordering inversions between archived/live game 107.

The other candidate-model tau values are summarized from the preserved analysis
outputs after reviewing their method; those complete candidate fitting jobs were
not independently rerun in this review. Content hashes prove preservation, not
the accuracy of every assertion in the original report.

The live samples were collected in the initial 4 November investigation. The
5 November checks are offline; they do not establish the service's state after
that saved sampling period.

## Qualifications and corrections

The evidence establishes different rank/acceptance environments, not the identity
of today's hidden embedding model. The early checkpoint and paper token filter
are strong reconstructions rather than author-confirmed specifications. The
restricted-form test does not prove that the words are free of every possible
server normalization confound.

The report's approximate 79,000 vocabulary is an estimate; the directly observed
fact is a rank reaching 78,902. The original `vocabulary_size` remains null.
The February 2023 transition date and the "only removals since 2024" explanation
are not established globally by the finite archived samples.

Two candidate results that were pending in the pasted report had completed:
GloVe 840B 300d has mean tau 0.453, and Twitter 27B 200d has 0.246 under the same
cosine/inflection procedure. Neither identifies the live scoring configuration.

The [paper's Appendix A.3](https://arxiv.org/pdf/2609.19006) lists its **50-target
comparison set**. That subset can be selected without access to the complete
1,500-puzzle release. An exact implementation and a matched budget/prompt are
still separate requirements.

Four fixed solving trajectories contain the exact target token in the candidate
environment. This is not a newly measured 4/10 model solve rate: with other
feedback, the model would take other trajectories. The measured **5/10 Contexto
2026 result is preserved**.

## Reproducing the review

The project root contains [verify_scoring_investigation.py](../../verify_scoring_investigation.py).
Run it in an environment with NumPy and SciPy; the reviewed environment reported
NumPy 2.5.4 and SciPy 1.18.1:

```powershell
python -B verify_scoring_investigation.py `
  runs/scoring_investigation_20261105 `
  runs/20261104T121421Z_evaluation_8bc0e311 `
  --vector-cache PATH_TO_GLOVE6B300_NPZ
```

The vector cache must contain `words` and `M`, representing the original 400,000
GloVe 6B 300d tokens and vectors. Its original path and SHA-256 are recorded in
[VERIFICATION.json](review/VERIFICATION.json). Obtaining/rebuilding that external
input is not automated here. The saved scripts document the original derivation.

Omitting `--vector-cache` runs only the cached evidence checks; do that against a
copy of this evidence directory if you want to preserve the original review output,
because the command writes `review/VERIFICATION.json`.

The proposal is reviewable as [SCORING_CHANGES.diff](review/SCORING_CHANGES.diff).
No original trial data or study scores were edited.
