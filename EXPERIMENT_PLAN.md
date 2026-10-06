# Contexto: directions to explore

We have a working AI player. The next step is to play with how it remembers,
prepares, and uses information, and see what changes in its search.

## Ideas worth trying

- **Memory:** compare the full guess history with Google's linked conversation
  memory. Could a short summary work as well? What happens if older guesses fade?
- **Planning:** let the model make a strategy before playing. Does it follow the
  plan, adapt it, or become stuck because of it?
- **Notes:** give it a notebook for promising clues, hypotheses, and unsuccessful
  directions. Let it decide what to write and revise. Do notes help, or reinforce
  a mistaken idea?
- **Reflection:** let it review a completed game before trying another. Does it
  learn a useful approach that transfers to a different target?
- **External information:** try Wikipedia passages or Wikipedia search. When does
  outside information help, and when does it distract from the rank feedback?
  Restricting external sources does not remove the model's existing knowledge.

## What might be interesting to watch?

Finding the word is one outcome. The path may be just as interesting: how broadly
it explores, when it changes direction, what it does with a strong clue, and what
it forgets or keeps repeating.

For example, our September 30 run reached `guard = 8` but did not find the target.
Would a plan, some notes, or a different memory help it use that clue?

We can try small comparisons on the same puzzle dates, keep the game records,
and let the results suggest the next question. Prompts, run counts, note formats,
and the order of experiments can stay open for now.

## Where we are

Explicit and linked memory are already selectable with `--memory`. Planning,
notes, reflection, and Wikipedia assistance are ideas for future additions.
The recorded thought summaries offer something to inspect, but are not a complete
view of the model's internal reasoning.
