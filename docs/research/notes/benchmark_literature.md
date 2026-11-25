# Empirical semantic word search benchmarks

## Which published results provide the closest comparison?

### Takeaway
WordPolo is the closest verified benchmark, but its 100-attempt frozen GloVe setting cannot establish how well the current 30-attempt live Contexto study should perform. BOPRO supports investigating adaptive exploration, with a much larger budget and richer feedback.

### Cited Findings
- **WordPolo, McDonald and Emami (2026), Table 1:** on the shared 50-puzzle set, solve rates were GPT-4.1 42%, o4-mini 62%, DeepSeek-R1 16%, Qwen3 reasoning 12% versus no-thinking 36%. Three individual humans scored 48%, 72%, and 100%; the expert's solved-game mean was 15.4 guesses. Each table column uses the 50-puzzle evaluation, rather than a 50-person sample. On 1,500 puzzles GPT-4.1 solved 35%, heuristic 39%, Claude3.5 Haiku 4%, Llama4 Maverick16%, Qwen3 no-thinking18%. All had 100 attempts; invalid and duplicate guesses consumed attempts. Feedback was GloVe rank, with full newest-first history. **No aggregate solve-at-30 result was located.** Figure1's under-30 example is one puzzle. — [WordPolo §§2,4,5.1 and Table1](https://arxiv.org/html/2609.19006v1#S5.T1)
- **BOPRO, Agarwal et al., ICLR2025, §7.1/Figure2:** Mistral-Large-2407 searched 10 hidden words, five warm starts each, three repeats, maximum1,000 guesses. Its synthetic Semantle returns **SimCSE cosine similarity**, not Contexto rank. All BOPRO variants exceeded baselines by at least10 percentage points; Figure2 caption specifically compares against greedy OPRO. OPRO improved early then plateaued, while BOPRO continued gaining. GTE-Qwen2 embeddings serve the search representation, separate from the SimCSE scoring oracle. — [BOPRO §§2.1,6.2,7.1](https://proceedings.iclr.cc/paper_files/paper/2025/file/a79237d6c47feef24c1df723cb41f674-Paper-Conference.pdf)
- **MTGBench, EMNLP2026:** adjacent multi-turn methodology across seven games; no Contexto/Semantle task. The benchmark used16 models and476 human sessions, with matched task instances. Findings explicitly emphasize task-dependent model rankings and uneven benefits of reasoning. A shared random seed fixes instances, not API output randomness. — [MTGBench abstract and §4.1](https://aclanthology.org/2026.findings-emnlp.1333.pdf)
- **BOReFT (2026 preprint), §5.1/Table1:** a substantially different intervention-based search study using Llama3.2-1B-Instruct, learned representation interventions, Qwen3-Embedding-0.6B cosine feedback,500 evaluations, and ten-word warm starts. Five held-out targets across three warm starts yielded8/15 exact matches. This is a possible future open-weight methods direction, not a comparable baseline for Gemini prompts. — [BOReFT §§5.1–5.2](https://arxiv.org/html/2609.33722v1)

### Inferences
- WordPolo's 48–100% human range is evidence that experience can matter, not a reliable population estimate: each skill level is represented by one person. The expert's100% is not an appropriate expected human success rate.
- The current experiment's20–24% solves by30 cannot be ranked against WordPolo's100-attempt results. Differences include oracle, vocabulary, targets, model, instructions, and budget. Even recalculating WordPolo at30 would address only the budget mismatch.
- A suitable report can present the benchmark values as context while describing the local control–guided contrast as its actual inference.
- BOPRO's unit hierarchy resembles the local repeated-target design: repeated runs/warm starts must not be treated as150 independent secret words.

### Gaps
- Did not obtain a tabulated WordPolo aggregate30-attempt solve rate or archived complete per-game trajectories. Do not interpolate one from its100-attempt endpoint or solved-game means.
- BOPRO text verifies a gain of at least10pp, not a precise final percentage for each acquisition method. Do not report visually estimated graph endpoints as exact.
- Paper-page source extraction has a200-word per-source synthesis allowance for the final response; keep the report's source-derived summaries compact. The notes provide an evidence index rather than authorizing wholesale copying.

## Which analyses are motivated by the literature?

### Takeaway
The most informative comparisons separate entering a promising region, making progress within it, and actually identifying the target. Prompt adherence and semantic diversity are plausible explanations, but their causal role needs follow-up controls.

### Cited Findings
- WordPolo reports that altered prompt examples change early seed words; altered-prompt performance varies by model. It compares latest-first versus rank-sorted history and top-ten history truncation in AppendixD, with mixed effects. It separately measures final solves, best-rank proximity, and per-step progression. Its proximity score requires a verified vocabulary size. — [WordPolo §§4.3,5.3; AppendicesC–D](https://arxiv.org/html/2609.19006v1#A3)
- BOPRO interprets continued gains versus long plateaus through exploration/exploitation, using a Bayesian search controller rather than merely adding general strategy advice. — [BOPRO §7.1](https://proceedings.iclr.cc/paper_files/paper/2025/file/a79237d6c47feef24c1df723cb41f674-Paper-Conference.pdf)

### Inferences
- **Immediate priority:** plot cumulative attainment of rank≤1,≤10,≤100,≤1,000 by attempt, with paired target summaries. This can reveal whether guidance improves broad localization while leaving a last-step bottleneck. Thresholds are interpretable operational measures, not demonstrated psychological stages.
- **Prompt uptake:** measure proportions of the first5 guesses matching explicit instruction exemplars, plus repetition of opening words across target dates. Separate exact-word adherence from semantic-category diversity. An independent, blinded category annotation is more interpretable than calling raw distinct-word counts semantic diversity.
- **Feedback adaptation:** define stalls prospectively (e.g., consecutive turns without a new best rank) and examine semantic switches after them. Report descriptive associations because difficult games both induce switching and remain hard.
- **Target heterogeneity:** show paired effects per target and variability across the three repetitions; preserve all25 targets when bootstrapping. A condition mean can obscure large reversals on individual targets.
- **Budget-aware performance:** describe solved-game means only alongside survival/cumulative solve curves. Means restricted to solved games condition on a post-treatment outcome and may reverse the apparent advantage.
- **New experiments:** exemplar replacement, exemplar removal, equal-length neutral instructions, shared fixed initial seeds, history ordering, and fixed-oracle replication can distinguish broad guidance from lexical anchoring. These are separate protocols, not post-hoc changes to the finished study.
- **Attainable contribution:** a credible course study can show whether instructions change observable search behavior, whether those changes improve trajectories or solving, and whether humans respond similarly on matched targets. Existing evidence does not warrant a promise of significance or human-equivalent cognition.

### Gaps
- Current local counts supplied by coordinator were not independently audited here; local-data researcher owns that verification.
- No strong reason emerged to include CLADDER: it is not a feedback-driven semantic word-guessing benchmark.

## What additional direct human literature might be useful?

### Takeaway
There are promising primary sources beyond model benchmarks, passed to the coordinator for the cognitive-literature stream. Their full contents were not verified here and should not be cited for numerical claims without reading them.

### Cited Findings
- Search located a UC San Diego thesis with a Contexto chapter and experiment word lists. — [Thesis PDF](https://escholarship.org/content/qt4147574w/qt4147574w.pdf)
- Search located *Comparing Semantic Navigation in Humans and Large Language Models using Natural Language Processing*; its abstract describes82 human participants, eight model temperature settings, entropy, step distance, and centroid dispersion. — [Preprint abstract](https://arxiv.org/abs/2607.12195)

### Inferences
- Such work could motivate separate local/global diversity measures rather than treating novelty as one scalar. Independent embedding geometry must be presented as a proxy, rather than the Contexto oracle's true geometry.

### Gaps
- The navigation paper's arXiv HTML returned404; repository view was blocked by a JavaScript check. Abstract-only claims require clear labeling if used.
- The thesis was discovered late and was sent to coordinator; it was not read in this benchmarking stream.
