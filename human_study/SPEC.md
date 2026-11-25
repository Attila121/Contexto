# Human study web app: spec (draft for review)

Status: **draft, 23 November 2026. Nothing built yet.** Decide the items in "Open decisions" before building.

## 1. Purpose

Collect human games on the same Contexto puzzles the AI played, with the same rules and the same records, plus what only humans give us: time per guess, hint timing, and self-reported strategy. Friends play from their own device through a private link.

Questions:

1. How do humans compare with the AI on the same 25 targets (solve rate, best-rank trajectory, invalid attempts)?
2. When and why do humans use the hint, and does it help them as much as the AI?
3. How long do humans take per guess, and does it change when they are close or stuck?

Out of scope: more AI games, new puzzles, public recruitment, prizes.

## 2. Verified facts about Contexto (checked 23 Nov 2026)

| Fact | Evidence |
| --- | --- |
| Guess API: `GET https://api.contexto.me/machado/en/game/{id}/{word}` returns `{"distance", "lemma", "word"}` or `{"error"}` | `lake` on game 1516 -> distance 3 |
| Displayed rank = distance + 1 | `lake` = rank 4 in the AI records for 12 Nov |
| Game id = days since 2022-09-18 (English) | site code `startDates.en`; 26 Oct = 1499, 19 Nov = 1523 |
| Hint API: `GET .../tip/{id}/{distance}` returns the word at that distance | `tip/1000/300` returned a word |
| Easy hint: distance = floor(min(best distance, 598) / 2); if best distance is 1 or less, the smallest unused distance from 2 up | site code; matches all 25 AI hints (e.g. 228 -> 114, 9444 -> 300) |
| Errors: "I'm sorry, I don't know this word", "This word doesn't count, it's too common" | live replies |
| The API sends **no CORS header**, and the site forbids framing | response headers |

Consequence: a page on GitHub Pages cannot call the API directly. A small proxy is required.

## 3. Architecture

```
participant browser -> GitHub Pages (static study page, plain HTML/JS)
                        -> Cloudflare Worker (proxy + rules + logging)
                            -> api.contexto.me          (guess, tip, giveup)
                            -> Cloudflare D1 database   (event log)
```

- **Static page:** no framework or build step. It has its own neutral design and name ("Word-closeness study"), with the credit "Rankings provided by contexto.me". It does not copy Contexto's logo, name or layout.
- **Worker:** the only place that talks to Contexto. It also enforces the rules, so nobody can cheat from the browser.
  - It only allows requests from the study page's address.
  - It requires the access code.
  - It only serves the study and pilot game ids.
  - It computes the hint distance itself from the guesses it has logged (the browser cannot choose it).
  - It only allows a give-up or answer reveal after the game has ended.
  - It rate-limits each session to 1 request per second and 100 per game.
  - It stores no IP addresses.
- **D1 database:** one table of events (see section 6), exported to CSV for analysis.
- **Cost:** within the free tiers (Workers 100k requests per day; D1 5 GB). Expected load is about 50 games x 35 requests.
- **Alternatives considered:**
  - Direct API calls: blocked by CORS.
  - Running it on your laptop with a tunnel: it only works while the laptop is on.
  - Google Apps Script as the proxy: it adds about 1 s of delay to every guess, which spoils the timing data.

## 4. Study design

- **Participants:** about 10 friends, adults, anonymous. Each gets a code like `P07`; no names are collected.
- **Games per person:** 5 dates from the 25 targets (26 Oct-19 Nov 2026), in random order.
- **Balanced assignment:** a table generated in advance with a fixed seed. 10 people x 5 games = 50 games, so each date is played exactly once in each of the two groups (25 + 25). The table is frozen before the first participant, like the AI manifest.
- **Groups (open decision D1):**

| Option | Group A | Group B | Matches AI data |
| --- | --- | --- | --- |
| **H (recommended)** | control instructions, no hint | control instructions + optional hint | A vs AI control (75 games); B vs AI hint study (25 games) |
| G (original plan) | control instructions | guided instructions | AI instruction study; no hint data |

  H is recommended because hint usage is a main interest and the guided effect in the AI was small.
- **Instructions:** the AI wording, rewritten for humans with the same rules. For example: *"Guess the secret English word. After each guess you see its rank: lower is closer, rank 1 is the secret word. You have 30 guesses. Do not use other websites, dictionaries or AI tools."* Group B adds the AI hint paragraph: one free hint, available after the first valid guess, which does not count as a guess and does not count as solving.
- **Rules (same as the AI unless noted):**
  - 30 guess attempts.
  - Invalid words, too-common words and repeats **count as attempts** (open decision D2), as they did for the AI. The page warns before each repeat.
  - The game ends on solving, at the 30th attempt, or on give-up (humans only; recorded, not counted as a solve).
  - A hint at rank 1 ends the game as "answer revealed by hint", as in the AI study.
- **After each game:** the AI's postgame question: "Describe the strategy you used in this game, and explain why you did or did not request the hint." Plus a rating: "How hard was this? (1-5)".
- **Session:** about 45-60 minutes for 5 games, which can be split over several days (the code resumes). There is no per-guess time limit; time is only recorded (open decision D3).
- **Pilot:** 1-2 people on the pilot dates 23-24 Oct, then an audit, before any friend plays the study dates.

## 5. Screens

1. **Access:** enter the access code from the private link. A wrong code ends the session there.
2. **Information and consent:** what the study is, what is recorded (guesses, ranks, timing, answers), that it is anonymous, that it is voluntary, that you can withdraw with your code, and who to contact. A checkbox, then continue.
3. **Short questions:** English level (native / fluent / intermediate), and whether you have played Contexto or Semantle before (never / a few times / often).
4. **Instructions** for your group, then a short example game on a practice word that is not stored.
5. **Game:**
   - word input; last guess shown on top;
   - history sorted by rank, with colour bands (green 1-300, yellow 301-1500, red above);
   - "Attempts used: n/30";
   - the hint button (group B only);
   - a give-up button with confirmation.
6. **After the game:** answer revealed, the strategy question, and the difficulty rating.
7. **End:** thanks, and the option to download your own data as JSON.

The page works on phones. Each game resumes after a reload, because the state is on the server.

## 6. Logged data

One event row per action: `event_id`, `session_id`, `participant_code`, `group`, `puzzle_date`, `game_id`, `event`, `attempt`, `client_ms` (time since game start), `server_time`, `payload` (JSON).

| Event | Payload |
| --- | --- |
| `session_start`, `consent`, `questions` | answers, browser type (no IP) |
| `game_start` | assigned order (1-5) |
| `first_keypress` | ms since the previous result (thinking time) |
| `guess` | word typed, attempt number, ms since the previous result, keystrokes and deletions |
| `result` | kind (rank / unknown / too_common / repeat), rank, lemma |
| `hint_request` | eligible yes/no, after which attempt |
| `hint_result` | hint word, rank |
| `focus_lost` / `focus_back` | duration (leaving the page could mean outside help) |
| `give_up`, `game_end` | reason, attempts, best rank, total time |
| `report` | strategy text, difficulty rating |

**Analysis:** an export script writes the same CSVs as the AI runs (`results.csv`, `trajectories.csv`, `strategy_reports.csv`) into `runs/<timestamp>_human_study/`. The AI metrics are then reused unchanged:
- best-rank trajectory, solve rate, median best rank, top-10/50/100, invalid attempts;
- hint timing, and the hint word compared with the next guesses.

Human-only measures: time per guess, and time near the target vs when stuck.

## 7. Privacy, ethics and Contexto

- Anonymous codes only. The code-to-person list stays with you, offline. No IPs or e-mail addresses are stored. Data is deleted by code on request.
- **Check with the course** whether approval or a consent template is required (open decision D4).
- **Contexto:** low-volume use of their public API through a proxy. Send them a short e-mail first describing the study and asking for permission. Stop if they object. Credit them on the page.

## 8. Testing and delivery

1. Write the tests first, because access control, the rules and the assignment are security-sensitive. Tests run with `node --test` (Node 24 is installed; no packages).
   - Worker logic: access code, CORS origin, allowed game ids, rate limit, attempt counting, the hint rule (the 25 AI hints as test cases), give-up only after the end, resume.
   - Assignment table: balanced 25 + 25, a fixed seed, and 5 dates per person.
2. Build the Worker and the page. Run locally against a **fake Contexto** that never contacts the real site.
3. **One live check** (with your OK): replay a few archived AI guesses through the Worker and compare the ranks.
4. **You deploy:** a GitHub repository with Pages, plus a Cloudflare account with a Worker and D1. Deploying needs the `wrangler` tool (open decision D5). I will write step-by-step instructions.
5. Pilot with 1-2 people on 23-24 Oct, export the data, and audit it (event counts, attempt limits, hint rule, no missing results).
6. Send the friend links; export and analyse when they are done.

## 9. Open decisions

- **D1:** groups H (control vs control + hint, recommended) or G (control vs guided).
- **D2:** invalid words and repeats count as attempts (recommended, matches the AI) or not.
- **D3:** no time limit, only recorded (recommended), or a cap per game (e.g. 15 min).
- **D4:** does the course need ethics approval or a specific consent text?
- **D5:** OK to use `wrangler` (Cloudflare's deploy tool, through `npx`, not added to the project), and do you have, or will you create, GitHub and Cloudflare accounts?
- **D6:** send the permission e-mail to Contexto before building, before the pilot, or not at all?
- **D7:** language of the page: English only (recommended, the puzzles are English) or also Hungarian instructions.
