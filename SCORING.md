# Contexto scoring: evidence and implications

Updated **5 November 2026**, incorporating the initial investigation and an independent
offline check of its saved evidence. The original 4 November note is preserved
[here](runs/scoring_investigation_20261105/review/SCORING_BEFORE_20261105.md).

**Our live Contexto results and the reconstructed WordPolo environment have
different rankings and acceptance rules.** The current Contexto embedding model
is still unidentified. Our **5/10 solves at 70 attempts** remain valid as a
Contexto 2026 pilot; they are not a matched estimate of performance on WordPolo.

The investigation's [evidence index](runs/scoring_investigation_20261105/README.md)
links the original report, preserved sources, scripts, verification results and
reconstructed rank tables. This review made no Contexto API or paid model calls.
The live-API observations below are from the saved 4 November investigation;
the 5 November review rechecks those artifacts rather than sampling the service again.

## What the live website returns

Contexto orders words by their association with the target in contexts of language
use. The number is an ordinal position, not a percentage or a continuous semantic
distance. Rank gaps do not measure equal semantic gaps. The creator describes
using word vectors but does not name the current English checkpoint in the
[interview](https://www.hey.gg/blog/contexto).

```text
Browser: lowercase, trim, reject multi-word input
API:     GET https://api.contexto.me/machado/en/game/{game_id}/{guess}
Server:  return canonical lemma and zero-based integer distance, or an error
Browser: displayed rank = distance + 1; raw distance 0 solves
```

These are confirmed in the [official frontend](https://contexto.me/assets/index-Cqg9suKP.js)
and saved API responses. Our [adapter](automated_game.py) reads the displayed rank
directly, so the experiment has no off-by-one conversion error.

| Submitted guess, game 1500 | Canonical lemma | API distance | Displayed rank |
| --- | --- | ---: | ---: |
| pear | pear | 0 | 1 |
| apple | apple | 1 | 2 |
| apples | apple | 1 | 2 |

[Saved examples](runs/scoring_inspection_20261104/api_examples.json).
Distinct surface forms can map to the same lemma and then count as repeated
guesses. The exact mapping remains unknown; it should not be assumed to be
standard WordNet lemmatization.

The saved probes distinguish unknown-word errors, explicit too-common-word
rejections, and other "doesn't count" rejections. An exclusion/blocklist is a
plausible explanation for the latter, but its exact contents and purpose are not
officially established. Some words associated with sensitive topics are accepted,
so this is not a simple blanket topic filter.

The ordinary website allows unlimited guesses. Rejected or repeated lemmas do not
increase its accepted-word counter. Current colors correspond to displayed ranks
1–300, 301–1,500, and 1,501 onward; colors and bar lengths are presentation rules.

## History and model identification

The saved official bundles credit Stanford's GloVe page in September 2022 and
February 2026; the credit is absent in the saved 11 March 2026 bundle. A credit
does not identify an exact checkpoint or prove when scoring changed.
[Verified bundle checks](runs/scoring_investigation_20261105/review/VERIFICATION.json).

Early archived rankings strongly support **GloVe 6B, 300 dimensions, cosine
similarity**, with form merging. This is an inference, not an author-confirmed
English specification. The simple-inflection test averages Kendall rank agreement
of 0.980 over eight early lists. A stricter heuristic-selected word subset has
zero inversions in six lists comprising 55,280 word pairs; across all eight lists,
there are 142 inversions among 64,916 pairs. That subset excludes forms identified
by WordNet/simple rules, not every possible server-side mapping.

Archived/live comparisons confirm changes in the ordering, including old puzzles
being re-ranked. Game 107 has **11,375 inverted pairs among 259 common words**
between its February 2023 archived list and the saved live list. The February
2023 samples suggest a transition around that period, but do not establish its
exact date or whether embeddings, normalization, similarity, or several components
changed. "Only removals since 2024" remains a hypothesis from limited samples,
not an established global rule.

The newer saved results complete two analyses that were pending in the initial
pasted report. None of these tested configurations reproduces the live ordering:

| Candidate vectors | Mean Kendall tau against 34 live lists |
| --- | ---: |
| GloVe 6B 300d | 0.378 |
| GloVe 42B 300d | 0.554 |
| GloVe 840B 300d | 0.453 |
| GloVe Twitter 27B 200d | 0.246 |
| fastText crawl 300d | 0.294 |

This table uses the same cosine/simple-inflection-max procedure for each model.
Tau 1 would mean identical tested ordering. These finite comparisons neither
identify the live model nor rule out every variant of an embedding family.
Word2vec remains untested successfully in the preserved investigation.

## Vocabulary size and temporal stability

A saved probe of game 0 and `responsbility` returned displayed rank **78,902**.
This establishes the observed rank range, not an exact current vocabulary size:
form merging, filters and possible rank gaps complicate the interpretation.
Approximately 79,000 is an estimate, not a verified denominator.

All **90 sampled guesses from our 4 November study** reproduced their recorded
ranks in the cookie-free shuffled replay. Among 57 older sampled guesses, 10
changed. Thus rankings were stable in the tested replay but are not immutable
across time. [Replay evidence](runs/scoring_investigation_20261105/api/replay.json).

Keep `vocabulary_size` null in the original manifest. Do not substitute the paper's
317,756 or the approximate 79,000 into a reported Contexto normalized score.

## Reconstruction of the paper's environment

The [paper](https://arxiv.org/pdf/2609.19006), sections 2.1–2.2, specifies GloVe 6B,
cosine ranking and a vocabulary of 317,756. Its dimension and exact token filter
are not explicitly established by those statements alone.

The independently checked candidate reconstruction uses **GloVe 6B 300d, cosine,
and tokens matching `^[a-z]+$`**, producing exactly 317,756 tokens. It reproduces:

- All **7/7** reported Figure 2 ranks.
- All **43/43** saved public-demo ranks for `banana`.
- All **515/515** ranks in the initial investigation's saved rescoring of our accepted guesses.

These checks strongly support this reconstruction. They do not certify every
undocumented paper implementation detail. The independent calculations and
compressed rank tables are in [review/](runs/scoring_investigation_20261105/review/).

The equation for proximity is `1 - log(rank) / log(C)`. At C = 317,756 it yields
0.818 for rank 10 and 0.455 for rank 1,000; the paper's illustrative 0.80/0.60
numbers do not both follow that equation. Use the equation rather than the example.

## Consequences for our 70-attempt study

The original [results](runs/20261104T121421Z_evaluation_8bc0e311/README.md) remain
unchanged: 552 outputs, five Contexto solves, and 40.4 attempts per solved game.
All ten authoritative event-log hashes still match the original completed-study
audit.

Across the 515 accepted guesses, live and reconstructed ranks have Spearman
correlation **0.784**. Their improvement directions disagree on **127/505
transitions between accepted guesses (25.15%)**, and the median reconstructed/live
rank ratio is **2.98**.
These compare fixed recorded trajectories: a model receiving other feedback would
choose other guesses. Rescoring cannot estimate its new solve rate or justify
relabeling the original 5/10 as 4/10.

One clear example is the 31 October puzzle:

| Submitted word | Live Contexto target/rule | Candidate exact-token rule |
| --- | --- | --- |
| limited | maps to `limit`, rank 1, accepted solve | `limited` ranks 28 against `limit` |

Our experiment counts all outputs toward its limit, whereas the website's counter
counts accepted unique lemmas. The detailed invalid-output accounting is:

| Category | Count |
| --- | ---: |
| Server-recognized lemma duplicates | 21 |
| Locally detected exact duplicate | 1 |
| Explicit too-common rejections | 8 |
| Other website exclusions | 5 |
| Malformed/empty model outputs | 2 |
| **Total unscored outputs** | **37** |

The initial investigation's 34 rejected attempts cover website responses only; the remaining three
are one local duplicate and two malformed/empty outputs. All 34 website-rejected
surface forms are new valid tokens under the tested reconstruction. That is a
vocabulary/acceptance check, not a prediction of a rerun's outcome.

## What a matched comparison needs

Freeze the target set, vectors, token vocabulary, normalization, ranking/tie rules,
prompt, and budget before collection. For our requested 70-attempt comparison,
evaluate both models at 70 in that same environment; the paper's published
100-attempt solve rates cannot simply be converted to 70.

The **50 comparison targets are listed in Appendix A.3**, so that subset does not
require obtaining the full 1,500-puzzle release. Access to the complete dataset
and original implementation remains a separate reproducibility question.
The current model, exact live lists, and exact vocabulary/normalization remain
necessary to reproduce the live Contexto backend itself.

## Preserved evidence and reproducibility

- [Original report](runs/scoring_investigation_20261105/ORIGINAL_REPORT.md).
- [Preservation manifest](runs/scoring_investigation_20261105/PRESERVATION.json):
  175 files, 25,486,563 bytes; copied content verified by SHA-256.
- [Independent verification](runs/scoring_investigation_20261105/review/VERIFICATION.json).
- [Prior note and review diff](runs/scoring_investigation_20261105/review/).
- [Preservation script](preserve_scoring_evidence.py) and
  [offline verification script](verify_scoring_investigation.py).

The original multi-GB downloads, Python environment and full vector cache were
not copied. Their paths/sizes and the input cache fingerprint are recorded; the
derived candidate rank tables are retained. Rebuilding from vectors requires the
external GloVe input and NumPy/SciPy. No copied network-probing script was run in
this review, and no original experiment score was changed.
