## Conclusions

**Today's Contexto does not use the paper's scoring.** The two give the same kind of rank feedback, but in different environments. Contexto's early English game did use the same vectors as the paper, and it moved to a model I haven't identified around February 2023. Your 5/10 therefore can't be compared directly with the paper's solve rates.

In the answers below, τ is Kendall's rank agreement, where 1 means identical word order.

### Your seven questions
1. **Model:**
   - **Early English game:** GloVe 6B 300d, trained on Wikipedia 2014 + Gigaword 5 (*inferred, very strong*). The site credited Stanford's GloVe page (*confirmed*), but never named the exact set.
   - **Today:** *unknown*. GloVe 6B (τ=0.38), GloVe 42B (0.55) and fastText crawl (0.29) all fall far short of a match. The FAQ's "used on the internet" and 42B being closest hint at web text, but only weakly.
2. **Vocabulary:**
   - **Size:** the highest rank I saw is 78,902 (*confirmed lower bound*), and values bunch up there, so about 79,000 lemmas (*inferred*). The third-party figures of 30,000–70,000 are too low.
   - **Filters:** there are three kinds of rejection (*confirmed*): "too common" (`the`, `however`), "doesn't count" (`sex`, `murder`, apparently a sensitive-word blocklist), and unknown words (`john`, `google`, `1999`).
   - **Exact lists:** *unknown*.
3. **Similarity:**
   - **Early game:** cosine (*inferred*). τ was 0.98, against 0.57 for dot product and 0.34 for Euclidean.
   - **Today:** *unknown*, because the API only returns ranks.
4. **Ranks and normalization:**
   - **Rank:** displayed rank is `distance + 1`, and the browser does the lowercasing and trimming (`PEAR` fails at the API) (*confirmed*).
   - **Word forms:** they share one rank through a custom mapping, such as `colour` to `color`, `launcher` to `launch`, `worse` to `wrong` (*confirmed*). In the early game a lemma took its best form's score (*inferred*).
   - **Ties:** different lemmas never shared a rank in my samples, but the tie-break rule is *unknown*.
5. **Fixed per puzzle:** rankings don't depend on guess history (*confirmed*): 90/90 of your Nov 4 guesses replayed identically in shuffled order, with no cookies. They do change over time, though: 10 of 57 guesses from Oct 6–7 have shifted slightly.
6. **Changes over time:** yes.
   - **Around Feb 2023:** a major re-ranking, applied retroactively to old puzzles.
   - **During 2023:** further re-ordering.
   - **Since 2024:** only word removals (*inferred*). All 122 within-game word pairs kept their order, and none of the 87 archived ranks moved up.
   - **March 2026:** the GloVe credit disappeared, about three years after the ranking changed.
7. **Match with the paper:** similar feedback only. I reproduced the paper's environment exactly with GloVe 6B 300d, cosine, and tokens matching `^[a-z]+$`, which gives exactly 317,756 words. The dimension and filter are *inferred*, as the paper doesn't state them.

### What this means for your experiment
These figures re-score your recorded guesses in the paper's environment. The model would have played differently with other feedback, so they don't predict its performance.
- **Agreement:** across your 515 ranked guesses, Spearman correlation is 0.78. About 1 in 4 transitions (25%) disagree on whether a guess was an improvement, and the median paper rank is about 3× higher.
- **One of your five solves wouldn't count:** on 2026-10-31 `limited` solved `limit` in Contexto, but it ranks 28 in the paper's environment.
- **"Invalid" means something different:** your 34 invalid attempts are 21 lemma repeats, 8 "too common", 5 blocked and 0 unknown words. Most would probably get a rank under the paper's rules; I didn't count them exactly.
- **Don't use C=317,756 for Contexto:** rank 100 scores 0.637 on proximity with that value, but about 0.592 with C≈79,000. Your manifest's `vocabulary_size` is currently null.

### Scoring pipeline
```text
Browser   lowercase and trim; reject multi-word input        [confirmed]
API       GET /machado/en/game/{id}/{guess}, no session      [confirmed]
Server    reject unknown, too common or blocked words        [confirmed]
          map surface form to canonical lemma                [confirmed]
          return the lemma's position as distance            [confirmed]
Browser   rank = distance + 1; distance 0 solves             [confirmed]
          repeated lemma is not counted as a new guess       [confirmed]

Ordering  to Feb 2023: GloVe 6B 300d cosine, best form       [inferred]
          now: unidentified model, words removed over time   [inferred]
```

### Evidence
| Finding | Status | Evidence |
|---|---|---|
| English credited Stanford GloVe, 2022–2026 | Confirmed | [Sept 2022](https://web.archive.org/web/20220928230730/https://contexto.me/static/js/main.318224d4.js), [Feb 2026](https://web.archive.org/web/20260228231225/https://contexto.me/static/js/main.27ee7aa2.js) |
| Credit removed by 11 Mar 2026 | Confirmed | [Bundle](https://web.archive.org/web/20260311234956/https://contexto.me/static/js/main.e7748afa.js) |
| Portuguese: GloVe 300d from NILC | Confirmed, Portuguese only | [March 2022](https://web.archive.org/web/20220309131825/https://contexto.me/static/js/main.56a93f19.js), [TechTudo](https://www.techtudo.com.br/noticias/2022/04/conheca-contextome-e-saiba-como-jogar-o-game-de-adivinhar-palavras.ghtml) |
| Creator mentions word vectors and training data, names no model for Contexto | Confirmed | [Interview](https://www.hey.gg/blog/contexto) |
| Early order is 6B 300d cosine | Inferred | [top/107](https://web.archive.org/web/20230207194608/https://api.contexto.me/machado/en/top/107), [top/135](https://web.archive.org/web/20230206151718/https://api.contexto.me/machado/en/top/135): τ=1.000 on 6 of 8 lists (0 of 55,280 pairs out of order) |
| Old puzzles were re-ranked | Confirmed | [Archived top/107](https://web.archive.org/web/20230207194608/https://api.contexto.me/machado/en/top/107) vs [live](https://api.contexto.me/machado/en/top/107) |
| Order stable by 2024 | Inferred | [May 2024 top/168](https://web.archive.org/web/20240530181933/https://api.contexto.me/machado/en/top/168): τ=1.000 against live, on one list |
| Rank reaches 78,902 | Confirmed | [game/0/responsbility](https://api.contexto.me/machado/en/game/0/responsbility) (misspelling is in the vocabulary) |
| Paper's stated setup | Confirmed | [Paper](https://arxiv.org/pdf/2609.19006) §2.1–2.2, 4.1, Table 8 |
| Replication of the paper | Inferred | 7/7 Figure 2 ranks; 43/43 [demo](https://wordpolo-demo.vercel.app/demo) ranks on `banana` |

The method tests above are my own analyses of these sources, and nothing official confirms them. In these lemma-free tests, I kept only words with no other surface form, so merging can't affect their order.

### What's still needed
**To reproduce today's scoring:**
- The model and its version from Daydash, or the full ordered list for each puzzle.
- The vocabulary, stop-list, blocklist and lemma table, all dated. Rankings keep changing, so save each puzzle's data when you run it.

**To compare fairly with the paper:**
- Run your model in the replicated environment: exact-token solves, 100 guesses, and invalid only for out-of-vocabulary words. This means paid Gemini calls, so it's your decision.
- Use the same targets in both environments. The paper's dataset is withheld and its [code link](https://anonymous.4open.science/r/wordpolo-data-CA8D) has expired, so ask the authors. Only its 979 Contexto answers are publicly traceable.
- Report your current results as a separate "Contexto 2026" condition.

### Limits and open items
- **Candidate models:** GloVe 840B and Twitter are still downloading, and word2vec failed twice, so none of the three is ruled out as today's model.
- **Timing of the switch:** I can't yet say whether it followed the calendar date or the game number. That analysis is still running.
- **Lemmatizer:** still unidentified, as WordNet variants fit no better than my rough rules. The 2 of 8 early lists below τ=1 are probably down to irregular forms, but I didn't check them word by word.
- **Sources I couldn't read:** Stanford's page was blocked, so the corpus description comes from the paper's Table 8. The Poatek and Positivo articles returned 403; both are third-party, so they wouldn't count as evidence anyway.
- **Paper oddities:** Figure 2 shows `smile` at 0.215 where I get 0.281, though its rank matches. Its proximity example (0.80 and 0.60) also doesn't fit its formula, which gives 0.818 and 0.455 at C=317,756.
- **Your records:** I wrote only to the scratchpad and made no model calls, using about 1,500 read-only requests to the Contexto API. A timestamp check on the project folder is still running, and `git status` was blocked by a repo ownership setting, which I left unchanged.

`SCORING.md` is now out of date where it says your observations don't establish whether the embeddings are identical or different. It also doesn't mention the archived GloVe credit or the blocklist rejection. I haven't edited it.

The evidence and scripts are in a temporary folder, along with several GB of vectors to delete afterward (local, since deleted). Do you want me to copy the evidence into a new folder under `runs/` and draft the `SCORING.md` changes for your review?