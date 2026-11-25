# Contexto scoring: verified behavior

Checked 4 November 2026 against the original **contexto.me**, its public frontend,
three public API responses, and our runner. No Gemini calls were made for this check.

## The website's ranking

Contexto's official explanation says words are ordered by contextual similarity to
the hidden word, learned from patterns in text. Related contexts need not imply
synonymy. The displayed number is a position in that ordering, not a percentage
or a continuous semantic distance. Rank gaps do not measure equal semantic gaps.

The frontend requests:

```text
GET https://api.contexto.me/machado/en/game/{game_id}/{guess}
```

The server returns a canonical `lemma` and a zero-based integer called `distance`.
The frontend displays `distance + 1`; a raw value of zero solves the game.

Verified examples for game 1500, the pear puzzle used in our study:

| Submitted guess | Returned lemma | API distance | Displayed rank |
| --- | --- | ---: | ---: |
| pear | pear | 0 | 1 |
| apple | apple | 1 | 2 |
| apples | apple | 1 | 2 |

Input is lowercased and trimmed. The frontend checks returned lemmas against prior
guesses, so a different surface form can be a duplicate. Invalid words and repeated
lemmas do not increment the website's guess counter. The ordinary game allows
unlimited guesses. Its colors use displayed ranks 1–300 (green), 301–1,500
(yellow), and 1,501 onward (red). These thresholds are presentation rules.

## What our study counts

Our [browser adapter](automated_game.py) reads the displayed rank directly from
the latest response row. It does not calculate semantic similarity or add 1 again.
There is no off-by-one correction needed in the recorded results.

Our evaluation limit is **70 model-output attempts**. Invalid words, duplicate
guesses, and malformed/empty final outputs consume attempts. This differs from
the website's accepted-word counter. For example, the pear game used **46 study
attempts**, comprising **42 accepted ranked guesses and 4 invalid/duplicate
attempts**. The website's ordinary counter is not our experimental budget.

In [evaluation_metrics.py](evaluation_metrics.py), solve rate is solved/completed
games. Attempts-to-solve includes invalid and duplicate attempts. Mean progression
compares each valid rank with the previous valid rank; invalid attempts score zero,
the first attempt is excluded, and completed games receive equal weight. API and
browser interruptions remain separate operational records. A transport request
without a returned model answer is not scored as a wrong guess.

## What remains unverified

The inspected official frontend/API do not identify the current English embedding
checkpoint, embedding dimension, vocabulary size, exact similarity formula, or
tie-breaking policy. The API exposes an ordinal rank, not a cosine score.
The frontend's bar scaling constant is not evidence of vocabulary size.

The paper specifies a GloVe/cosine implementation. Our observations confirm the
same general kind of rank feedback, but do not establish identical or different
embedding weights, vocabulary, or similarity calculations. Earlier descriptions
of a necessarily different underlying scoring algorithm were too definite.
Independent Contexto clones and third-party solvers cannot verify the original
backend's exact configuration.

## Evidence

- [Official frontend inspected](https://contexto.me/assets/index-Cqg9suKP.js):
  API wrapper `lX`, response/lemma handling in `le`/`fe`, row renderer `qj`, and
  English how-to-play/FAQ text.
- [Official app description](https://apps.apple.com/us/app/contexto-official/id6444917886).
- Public API examples: [pear](https://api.contexto.me/machado/en/game/1500/pear),
  [apple](https://api.contexto.me/machado/en/game/1500/apple),
  [apples](https://api.contexto.me/machado/en/game/1500/apples).
- [Saved API responses](runs/scoring_inspection_20261104/api_examples.json) and
  [inspected frontend](runs/scoring_inspection_20261104/frontend.js).
  Frontend SHA-256:
  `55c493f86e86da3521d4836968f9d26651777e99be32d11e6e4750c99799b2a0`.
- [WordPolo paper](https://arxiv.org/pdf/2609.19006), sections 2.2 and 4.3.

This inspection does not modify the experiment's scores or collected records.
