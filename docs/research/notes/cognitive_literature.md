# Cognitive literature for Contexto semantic search

Research date: 21 November 2026. Scope: primary empirical sources and actionable hypotheses; this is a literature assessment, not a new analysis of the local games. Other researchers cover the local data audit and game benchmarks.

## Which cognitive findings transfer most directly to Contexto?

### Takeaway

The strongest human precedent is a controlled Contexto adaptation, not generic verbal fluency. It supports separating semantic navigation from exact-target discovery and manipulating starting proximity in a later matched experiment.

### Cited Findings

- **Hurwitz (2024), dissertation Chapter 2, Experiment 1:** 61 undergraduates played nine targets, at most ten guesses each, with supplied starting words near ranks 10, 100 or 1,000. The environment used GloVe and a filtered dictionary of 80,224 words. Solve proportions were **61%, 22%, and 8%**, respectively. Mean cosine similarity between successive guesses was **.435, .410, and .393**; proximity affected this measure, F(2,114.2)=15.09, p<.001. However, the probability that a subsequent guess improved over the previous guess did not differ significantly, chi-square(2)=4.24, p=.12. Experiment 2 retained 22 of 41 recruits after exclusions, used 20 guesses without supplied starts over three weekly sessions, and found no evidence of improved performance or changed successive-guess similarity with practice. The source is a dissertation; Chapter 2 was being prepared for publication. See printed pp31–42 / PDF pages45–56. [Primary dissertation](https://escholarship.org/content/qt4147574w/qt4147574w.pdf).
- **Hills, Jones & Todd (2012):** 141 undergraduates generated animal names for three minutes, producing a mean 36.8 valid animals. Search combined a local semantic-similarity cue and a global word-frequency cue. The dynamic similarity-drop model fit **131/141** participants better than the static model; the hand-coded category-switch version improved fits in 85 participants. Retrieval slowed around patch transitions, with switching patterns consistent with marginal value theory. This was free retrieval of many category members, with no hidden target or rank feedback. [Primary paper, DOI 10.1037/a0027373](https://willamannering.weebly.com/uploads/1/2/1/7/121718304/hillsetalpsychrev2012__1_.pdf).
- **Troyer, Moscovitch & Winocur (1997):** Experiment 1 included 41 younger and 54 older adults. Clustering and switching both correlated with semantic word production; younger adults produced more words and switched more frequently. In a separate 22-person experiment, divided attention reduced phonemic switching. The study operationalizes cluster size and category switches as separable outcomes, rather than treating total word count as a sufficient summary. [Primary paper](https://www.rotman-baycrest.on.ca/files/publicationmodule/@random45f5724eba2f8/pid1042.pdf).

### Inferences

- **Main candidate question:** Does guidance change how the model explores and exploits semantic regions, even when it does not increase solving within 30 attempts? The existing guidance manipulation permits a condition comparison; it does not by itself identify a mechanism.
- Derive **time to first top-1,000 / top-100 / top-10 guess**, plus **time to solve**, using all games and the same attempt budget. These thresholds are descriptive milestones, not equal units of semantic distance. Show cumulative attainment curves and the numbers still unsolved.
- Separate **reaching a useful region** from **finishing once near the target**. A top-100 breakthrough followed by twenty unsuccessful guesses is a different failure from never getting near the target. Compare later progress against earlier rank descriptively; do not call a post-treatment subgroup causal, since guidance may change which games enter that subgroup.
- Measure **stall length** as attempts since the last best-so-far improvement. With annotated semantic categories, examine whether a category switch becomes more likely after a longer stall and whether new best ranks follow switches. These temporal associations do not establish that switching caused progress.
- A strong future manipulation, analogous to matched difficulty in Word Superiority, gives humans and models **the same seed words at the same ranks**, with identical targets, feedback and attempt cap. It isolates behavior at comparable starting information. The thesis's 61% solve rate is not a human baseline for unseeded live Contexto.
- Practice is a useful secondary question for human game order. The thesis supplies no basis to assume either that practice must help or that practice effects are absent in this local protocol.

### Gaps

- The live game's ranking geometry is not established by the dissertation's controlled GloVe environment. An external embedding can describe guesses but cannot be assumed to reproduce live scores.
- Experiment 2's solve-rate text contains apparent percentage-format inconsistencies (values printed as .13%, .19%, .03%); do not reproduce those numbers as dependable benchmarks.
- Generic animal-fluency clusters cannot simply be reused for open-vocabulary Contexto. New categories and annotation rules must be defined.

## What human–LLM differences and semantic measures are supported?

### Takeaway

Recent primary studies support a testable hypothesis that LLMs remain in local semantic clusters longer than people. They also show why matching one overall performance score does not demonstrate matching search behavior.

### Cited Findings

- **Lacosse et al. (2026), preliminary mechanistic-interpretability workshop preprint:** started with 699 human animal-fluency sequences and generated corresponding sequences using instruction-tuned Llama-3 models of 1B, 3B, 8B and 70B parameters. Each model sequence was seeded with the human's first animal and truncated to 35 responses. After whole-sequence validity filtering, analyses included 681 human and 2,285 model sequences. Human–model category-transition matrices correlated **Spearman rho=.701, p<.001**. Nevertheless, the mean category-switch ratio was approximately **.55 for humans versus .40 for LLMs**, Mann–Whitney p<.0001. LLMs thus remained within clusters longer under this protocol. This is category fluency, not feedback-guided target search, and the filtering protocol differs from counting invalids as attempts. [Primary preprint](https://arxiv.org/html/2603.01822v1).
- **Paris-Colombo, Cabral-Carvalho & Toro-Hernández (2026), CogSci proceedings paper:** compared fluency from **82 humans** with GPT-4o, Gemini-2.5-Pro and Claude-Sonnet-4.5 across eight temperature settings. Metrics were step-length entropy, distance to the next item, and distance to the trajectory centroid. Humans had higher entropy, larger semantic steps and wider dispersion. Some temperature settings matched individual human metrics, but none reproduced the complete profile. This gives directly reusable measurement ideas; it is not evidence about Gemini 3.8 Flash or Contexto solve rates. [Primary PDF](https://arxiv.org/pdf/2607.12195), [paper metadata](https://arxiv.org/abs/2607.12195).
- **Hill, Reichart & Korhonen (2015), SimLex-999:** demonstrates the distinction between conceptual similarity and association/relatedness. Associated pairs such as Freud–psychology can be rated low in similarity. The benchmark includes concrete and abstract nouns, verbs and adjectives and independent association/concreteness ratings. [Primary paper](https://aclanthology.org/J15-4004.pdf).

### Inferences

- **Most valuable semantic outcomes:** consecutive-guess cosine distance; dispersion around the guesses' centroid; mean cluster length; switch ratio; number of semantic regions visited; and revisits to previously abandoned regions. Use a fixed embedding model or a documented human coding scheme. A count of distinct spellings measures lexical variety, not semantic variety.
- Compare **early exploration** and **later exploitation**, initially using fixed attempt windows such as 1–10 and 11–20. Solving early shortens observed sequences: handle that explicitly rather than treating solved games as having no diversity. A common early prefix is particularly useful.
- Distinguish **strategy change** from **strategy success**. Guidance could increase broad searching and still reduce solving if it delays local refinement; alternatively, it could improve approach without helping the final semantic distinction. Neither direction is established by these studies.
- Use at least two complementary semantic measures. A long jump can move to a new region or merely reflect an embedding's unusual geometry. A scalar diversity score can hide coherent, useful cluster switches.
- Code qualitatively interpretable errors: synonyms, co-category items, thematic associates, alternate senses, morphological variants, repeated rejected words, and returns to exhausted regions. Annotation should be blind to condition/outcome where feasible, with a second coder checking a subset. Mark ambiguous words rather than forcing every transition into a unique category.
- Treat **polysemy traps** as a hypothesis supported by examples and external annotation, not an established mechanism. A sequence such as bank→loan→credit for a river-related target would be an illustrative pattern, not actual local evidence.
- Candidate visual: a guess timeline colored by annotated region, with actual and best-so-far ranks beneath it, for one guidance-helped and one guidance-hurt target. A two-dimensional embedding map can illustrate those cases, but its projected distances should not be used for inference.

### Gaps

- These fluency studies do not establish an optimal amount of exploration for Contexto or imply that greater diversity is always better.
- Embeddings, annotation, and any independent validation are additional work. Do not add dependencies or pay for annotation/model calls without authorization. Existing thought reports are not a validated replacement.
- Thirty guesses per game give limited information for estimating entropy reliably; short-sequence entropy depends strongly on binning and estimator choices. Prefer simple distances/clustering for a first analysis.

## How can the comparisons remain statistically and cognitively defensible?

### Takeaway

The important unit for puzzle generalization is the target, while human generalization also requires independent people. Repeat runs and guesses are useful measurements, but do not turn a small target or participant sample into a large independent experiment.

### Cited Findings

- **Miller (2024), Adding Error Bars to Evals:** separates question difficulty from answer-generation variation; recommends inference on question-level paired differences when comparing systems. Repeated answers reduce conditional generation variance, with diminishing benefit once question variation dominates. Pooling all repeated answers into a standard error that assumes independent draws is inconsistent. Related questions require clustered uncertainty estimates. [Primary paper, sections 2.2, 3.1 and 4.2](https://arxiv.org/html/2411.00640v1).
- **Turpin et al. (NeurIPS 2023):** biasing prompt features changed GPT-3.5 and Claude 1.0 answers on 13 BIG-Bench Hard tasks, while generated explanations often omitted those influences and rationalized the answer. The paper reports accuracy drops as large as 36% in its tested settings. It establishes that plausible chain-of-thought text can misrepresent a prediction's causes; it does not directly measure the faithfulness of this project's Gemini summaries. [Primary proceedings paper](https://papers.nips.cc/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract-Conference.html).

### Inferences

- Keep the frozen **ordinal best-rank trajectory score** primary. Add solve curves, milestone curves, per-target effects and invalid-attempt summaries as exploratory outcomes, with uncertainty. Ranks are ordinal: moving 1,001→501 need not represent the same semantic improvement as 501→1.
- Retain the **target-paired comparison** and resample whole targets for target-generalizing uncertainty. The nine cross-condition repetition pairs within each target and thirty serial attempts are dependent, not 270 independent replications.
- For repeat reliability, plot each target's three runs per condition. Targets consistently hard across repeats differ from targets with sporadic lucky discoveries. A between-target versus within-target variance description is more informative than reporting only pooled game variance.
- The planned ten humans, five per instruction condition and five games per person, yield **five independent people per condition**, not twenty-five. Balance target assignment and game order across conditions. A human–AI interaction in guidance effects is likely imprecise; report intervals and descriptive effects rather than a binary claim of equivalence or difference.
- If human analyses are fitted, account for crossed **participant and target** structure; AI repetitions belong within target and condition. A complicated mixed model does not repair five people per arm. Design-specific simulation is a better next power calculation than borrowing a raw published effect size.
- Keep invalid/repeated outputs in the attempt budget for the primary comparison. A valid-guesses-only curve can describe the source of inefficiency, but removing failures changes the estimand and cannot be presented as the original treatment effect.
- Analyze timing **within each agent type**: human decision intervals and AI token/latency usage can each relate to stalls or switches. Network, service, context-length and browser time make API latency an unsuitable direct measure of human-like deliberation. More tokens may accompany harder decisions without causing worse performance.
- Use postgame strategy reports to state **what the model reports doing**, then compare reports with actual sequences. Agreement is useful description; it does not reveal internal reasoning. A causal mechanism claim requires an intervention such as seeded histories, alternative feedback or a frozen scoring task.
- The defensible initial conclusion can be that guidance has uncertain performance effects while revealing structured, target-dependent changes in search. A clear null/uncertain effect plus good process evidence is an achievable course-project contribution.

### Gaps

- No direct statistical power calculation for this exact crossed human/target design was performed here.
- No new local game-level estimates, semantic annotations, or token regressions were calculated in this literature task. Numerical local findings must come from the project-data researcher.
