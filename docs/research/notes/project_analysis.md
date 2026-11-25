# Local Contexto analysis opportunities

## What is the existing experiment, and what claim can it support?

### Takeaway
The existing batch is a completed, exploratory instruction-guidance study: one model, 25 targets, two prompts, three fresh repetitions, 30 attempts. It can support an analysis of how supplied search guidance changes behavior. It does not directly test whether formulating one's own pregame plan helps.

### Cited Findings
- The batch contains 150 complete games and 150 postgame strategy reports. Model settings are Gemini 3.8 Flash, temperature 0.6, low thinking, 4096 maximum output tokens, automatic thought summaries. Each game receives full previous guess/rank history newest first in a fresh session. [Frozen manifest](../../../results/instruction_study/manifest.json), [README](../../../README.md).
- Literal control wording: "Play an English semantic hidden-word guessing game. Lower ranks are closer; rank 1 identifies the target. Use the provided guesses and ranks. Do not repeat guesses. Return exactly one English word, letters only, in your final answer. You have no external tools. Guess the hidden word using the rank after each guess. You have up to 30 guesses." The guided prompt appends: "Start with guesses from different semantic categories. Compare their ranks. Then focus on words related to your best-ranking guess. If several guesses fail to improve your best rank, switch to a different semantic area." [Manifest](../../../results/instruction_study/manifest.json).
- The report prompt is issued after the game: "The game has ended. In one or two sentences, describe the strategy you used in this game. Return prose rather than another guess." These reports are retrospective descriptions, not separately recorded pregame plans. [Manifest](../../../results/instruction_study/manifest.json).
- The older requirements ask for a player-generated plan stored before the first guess and an open-weight model. Current README explicitly keeps Gemini work separate from the planned open-weight study. [Requirements sections 2-4](../../../Functional_Requirements_Clarification.md), [README](../../../README.md).

### Inferences
- Frame the current question as: "Does explicit advice to explore broadly, exploit promising clues and switch after stagnation change semantic search?" This is an interpretation of the implemented manipulation, not a new protocol change.
- The three advice components are bundled. Existing data cannot isolate which component causes an effect.
- The original planning question requires a later, separately specified experiment. Do not relabel the current data or change the frozen protocol to claim it tested planning.

### Gaps
- Human data have not yet been collected in the inspected project state. No human-versus-AI empirical conclusion is available.
- Semantic breadth, clusters, switches and guidance adherence have not yet been annotated.

## Which Word Superiority analysis ideas transfer to Contexto?

### Takeaway
Transfer the reasoning structure: outcome plus process, matched items, target heterogeneity, response bias, consistency, effort and human comparison. Contexto's sequential ordinal feedback requires different outcome measures and dependence handling than independent letter-recognition trials.

### Cited Findings
- Word Superiority has item/family analyses, response-bias checks, matched human-AI stimuli, shared-error analyses, effort-versus-human-RT comparisons, learning over a session and sensitivity checks. Its progress file warns that repeated observations are not independent and item variation can dominate repetition variation. Word Superiority progress (separate course project).
- Contexto already provides game-level outcomes in `results.csv`, 30-turn best-so-far curves in `trajectories.csv`, target-level guided-vs-control scores in `target_scores.csv`, postgame reports in `strategy_reports.csv`, and per-game `events.jsonl`, `turns.csv`, `timeline.md`. [Batch README](../../../results/instruction_study/README.md), [analysis implementation](../../../study_analysis.py).
- Event records contain submitted word, feedback, rank, request and response timestamps, raw usage including `total_thought_tokens`, `total_input_tokens`, `total_output_tokens`, and model-returned thought summaries. [Example game directory](../../../runs/20261120T213300Z_instruction_study_5625ddd2/production/2026-11-05/control/repeat_01/).

### Inferences
- Proposed mapping: Word Superiority overall context effect -> guidance effect on trajectories and success; font/family heterogeneity -> target heterogeneity; repeated fixed-letter responses -> stereotyped openers, repeated words/lemmas and cluster trapping; blur curves -> performance by allowed attempts; human/model shared difficulty -> targetwise difficulty agreement; thinking tokens versus RT -> effort measures within matched target and search stage.
- Suggested core figures, all pending: cumulative attainment by attempt for rank 1/10/100; target-level score forest/dot plot with repetitions shown; two or three representative guess trajectories; semantic switching/adherence summary; human-AI target difficulty comparison after collection.
- Keep the primary question small. A guidance effect plus an observable process shift would be a useful course-project result even without a significant solve-rate difference.

### Gaps
- A target's distance to its answer is not an independent psychophysical difficulty manipulation analogous to randomized blur. Attempt number is also not randomized. Plots by attempt describe search development, not a causal effect of time.
- Latency is API/network/service time plus computation, not a direct cognitive RT equivalent.

## What should the planned analysis prioritize?

### Takeaway
First preserve the frozen paired ordinal primary outcome, then ask whether guidance changes reaching a useful neighborhood versus finding the exact answer. Next investigate heterogeneity and observable strategy adherence. These are proposed next analyses; no analysis implementation is requested.

### Cited Findings
- Existing reported primary score is 0.566, whole-target bootstrap 95% interval 0.492-0.636. Scores above 0.5 favor guided. All nine guided/control repetition pairs at each of 30 turns are averaged within target; 25 target scores are averaged equally. Solved games retain rank 1, invalid attempts retain the best prior rank, and initially absent ranks compare as infinity. [Existing output](../../../results/instruction_study/results.json), [implementation](../../../study_analysis.py).
- Existing reported outcomes are control 18/75 solves (24%), guided 15/75 (20%); median best final rank 42 versus 28; mean attempts among solved games 17.83 versus 15.27. Invalid attempts total 93 versus 128. [Existing results](../../../results/instruction_study/results.json).
- Read-only descriptive inspection during initial research, before the user clarified "Plan the analysis do not do it yet", found these threshold counts, all with denominator 75 per condition. Source is existing `trajectories.csv`; these were not saved into the project results or fitted as new inferential analyses. [Trajectories](../../../results/instruction_study/trajectories.csv).

| Condition | Attempt | Rank <=1000 | Rank <=100 | Rank <=10 | Rank 1 |
|---|---:|---:|---:|---:|---:|
| control | 10 | 72 | 30 | 7 | 5 |
| guided | 10 | 73 | 27 | 8 | 5 |
| control | 20 | 75 | 45 | 12 | 11 |
| guided | 20 | 75 | 46 | 15 | 11 |
| control | 30 | 75 | 49 | 19 | 18 |
| guided | 30 | 75 | 55 | 21 | 15 |

- The same initial read-only inspection found one control game and six guided games ended at rank <=10 without solving. The existing target trajectory scores favor guided on 18 dates and control on seven; none equal 0.5. These are descriptive counts without new uncertainty estimates. [Results](../../../results/instruction_study/results.json).

### Inferences
- Priority 1: report the existing primary result and its uncertainty faithfully. A score of 0.566 is a win/tie summary of relative best-so-far ordinal ranks, not 56.6% solve probability, and the interval includes the no-advantage value.
- Priority 2: plan cumulative attainment curves at rank <=100, <=10 and rank 1, plus best-so-far rank distribution at the final budget. Use equal target weights and paired whole-target uncertainty. Interpret the approach-versus-solving pattern as an exploratory question, not evidence already established.
- Priority 3: targetwise plots with all six runs, leave-one-target-out sensitivity and a prespecified small set of descriptive target features. Possible examples already visible in saved outputs: 1 November strongly favors control (score .100; control final ranks 18/1/1 vs guided 2/365/647); 5 November favors guided (.909; control 57/106/106 vs guided 1/28/62). Avoid selecting only attractive case studies.
- Priority 4: describe within-target repetition variation. Three repetitions provide a limited view of generation variability; they do not turn 25 targets into 150 independent problems.
- Priority 5: process, error and effort analyses listed below. Mark all analyses selected after seeing results as exploratory; record the plan before implementation, without claiming retrospective preregistration.
- Do not compare mean attempts on solved games as the principal efficiency outcome: groups condition on different successful subsets. Plan a cumulative solve curve or a 30-attempt restricted time-to-solve measure with unsolved games handled explicitly; do not pretend unsolved games solved on attempt 31.
- Do not treat improvement in rank as a fixed semantic-distance gain. An ordinal win score is robust to monotone rank transformations; averages/log-rank curves impose additional descriptive scale choices.

### Gaps
- Thresholds and new secondary outcomes were not frozen in the original primary analysis. They must be labeled exploratory.
- The small number of top-10-but-unsolved games precludes a reliable claim that guidance specifically harms final retrieval. Conditioning on reaching top 10 can also introduce selection bias.

## How should search strategy, invalids and effort be operationalized?

### Takeaway
The strongest process analysis tests whether the actual guess sequences implement the three instructions: breadth, exploitation and switching. Start with a transparent coding scheme and observable behavior; treat returned summaries as secondary descriptive material.

### Cited Findings
- Initial read-only inspection found first guesses: control water 64/75, person 10/75, time 1/75; guided water 53/75, animal 14/75, person 8/75. This is opener stereotypy, not a measurement of sequence-level semantic diversity. [Per-game production records](../../../runs/20261120T213300Z_instruction_study_5625ddd2/production/).
- Invalid attempts consume the study budget even though the website's own accepted-word counter treats rejected/duplicate lemmas differently. Contexto canonicalizes surface forms; the exact mapping is unknown. [Scoring review](../../../SCORING.md), [README](../../../README.md).
- Raw summaries are not complete internal reasoning, and postgame reports are retrospective. [README](../../../README.md).

### Inferences
- Breadth: predefine an early window, e.g. first five attempts; code coarse semantic categories and category coverage/entropy, with ambiguous or invalid words handled by a fixed rule. Distinct word counts alone are not semantic breadth.
- Exploitation: measure semantic relation of the next guess to the current best clue, alongside whether it establishes a new best rank. The current-best clue must be determined only from feedback available at that turn.
- Switching: predefine stagnation as a run of non-improving best-so-far ranks, then code whether the next guess moves to another category and whether subsequent guesses improve. Use a few declared sensitivity thresholds because the guidance says only "several". A category change is not identical to a bad rank, and semantic distance to the previous guess is not necessarily a category change.
- Validation: manually code a balanced blinded subset, hide condition labels where practical, use independent coders and agreement/reconciliation rules. If embeddings later automate coding, freeze the embedding model, distance definition and thresholds, and validate against human coding. The scorer's own hidden embeddings cannot be assumed known.
- Separate two ideas: semantic spread among the model's guesses versus alignment with the game's scoring environment. Independent embeddings measure a proxy semantic space; they do not recover Contexto's hidden geometry.
- Invalids: plan categories for malformed output, exact repeated word, server-recognized repeated lemma, out-of-vocabulary/rejected word and other operational events. Keep primary attempt-budget accounting unchanged; accepted-guesses-only views can be labeled sensitivity analyses because they remove part of the observed treatment cost.
- Stagnation and traps: plot consecutive attempts without a new best rank, revisiting the same categories and repeated use of a strong clue's neighbors. A lack of new best rank alone does not prove irrational behavior: exploratory probes can be informative.
- Reports: compare self-described exploration/switching against coded behavior, and count mismatches. Do not infer a causal mechanism or faithful internal strategy from prose alone.
- Effort: analyze per-turn thought tokens and latency with target, attempt number/history length, current best rank and stagnation considered. Report input tokens separately because the guided prompt and accumulating history mechanically affect token totals. Relate effort to the next observed improvement descriptively; difficult states can cause both more effort and lower success.
- New dependencies, embedding downloads and paid model coding are not needed for the first manual pilot; ask before adding dependencies. Do not claim embeddings are already available in this environment without checking.

### Gaps
- Complete invalid subtype information may require browser evidence and event context; the common `invalid` feedback label alone does not distinguish every cause.
- No validated category taxonomy, automated semantic encoder or inter-rater reliability estimates currently exist in the inspected analysis outputs.

## How should the future human comparison be designed and interpreted?

### Takeaway
Match the targets, feedback, attempt limit and available history. Compare the effect of guidance across humans and the selected model while accounting for target and participant dependence. The currently planned human sample is a feasibility design, with limited precision for an interaction.

### Cited Findings
- Current project progress proposes 10 humans, five per condition, five distinct games each, on the same 25 dates. It explicitly warns that the human-AI difference in guidance effects will remain uncertain with 10-20 humans. [Contexto progress](../../../PROGRESS.md).
- Live ranks are not frozen; past puzzles have been re-ranked. The current embedding checkpoint and exact vocabulary are unknown. Sentinel checks only detect some drift. [Scoring review](../../../SCORING.md), [batch README](../../../results/instruction_study/README.md).
- Earlier 10-game evaluation used a different 70-attempt protocol and must remain separate; its 5/10 solves cannot be pooled with the 30-attempt instruction study or directly compared to 100-attempt published benchmarks. [README](../../../README.md), [Scoring review](../../../SCORING.md).

### Inferences
- Allocate the 50 human games to cover each target once in each condition while ensuring each person sees five distinct targets, randomized/counterbalanced in order. With five humans per condition, participant-level uncertainty is substantial even though there are 25 game records per condition.
- Record full guesses/ranks, invalid attempts, timestamps, participant code, game order, English proficiency, Contexto experience and prior puzzle exposure. Do not treat participants' repeated games as independent people.
- If later testing a guidance-by-agent interaction, use a crossed target/participant approach or an appropriate hierarchical bootstrap. The AI sample is one selected model under frozen settings, not a population of independent AI participants.
- Compare within-target relative guidance effects and target difficulty ordering rather than overclaiming identical search mechanisms from similar means.
- Humans cannot reset all prior experience between games, unlike fresh AI sessions. Measure practice/order effects. Keep targets disjoint within each participant and avoid replaying the same target under both instructions.
- Define whether human instructions match the supplied-guidance study or the original pregame-planning question before collecting. Mixing a self-generated human plan with supplied model advice changes the manipulation.
- Later human RT versus AI thought tokens is most interpretable at matched target and search state; API wall-clock time is not the same construct as human deliberation time.

### Gaps
- Human session length, recruitment, exact interface, trial logging and feedback-stability acceptance criteria remain unresolved.
- A frozen external scorer would improve reproducibility but changes the experimental environment; it needs a separate declared protocol and is not an authorized change to the existing study.

## What work has actually occurred during this research?

### Takeaway
No study implementation, live play, model calls, dependency changes, or frozen data/protocol edits occurred. After the user's clarification to plan only, further calculations, tests and project-state edits stopped.

### Cited Findings
- Before clarification, read-only standard-library summaries were run on existing saved CSV/JSON/JSONL records: threshold counts at attempts 10/20/30, per-target final ranks and scores, solve consistency across three repetitions, opener counts, invalid labels, saved token totals and latency, and sentinel record structure. No new inferential test or figure pipeline was implemented. Sources are the batch files cited above.
- Before clarification, the README-documented offline check ran as `./.conda/python.exe -m unittest discover -s . -p 'test_*.py'` from `Project/Contexto`: 57 tests passed in 54.222 seconds. Existing production audit was inspected; it was not rerun or rewritten. [Documented check](../../../README.md), [existing audit](../../../results/instruction_study/AUDIT.md).

### Inferences
- The next deliverable should be a reviewable analysis plan, followed by implementation only when the user requests it.
- No `PROGRESS.md` changes were made by this research agent because the later user instruction restricted this work to planning.

### Gaps
- This notes file documents a proposed analysis. It is not a completed analysis package or a confirmatory statistical result.
