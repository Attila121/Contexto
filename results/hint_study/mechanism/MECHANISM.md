# Why the hint helped: exploratory offline analyses

Hint run: `20261123T175122Z_hint_study_a22ab6a8`; archived controls: `20261120T213300Z_instruction_study_5625ddd2` (75 control games).
No model or website requests. Descriptive only; thresholds were chosen after seeing the main result.

## 1. When the gap opens

| Attempt | Paired score | Median best (hint) | Median best (control) |
| ---: | ---: | ---: | ---: |
| 1 | 0.680 | 628 | 1446 |
| 2 | 0.767 | 384 | 765 |
| 3 | 0.793 | 210 | 482 |
| 5 | 0.713 | 163 | 298 |
| 10 | 0.673 | 35 | 132 |
| 15 | 0.687 | 27 | 90 |
| 20 | 0.673 | 12 | 64 |
| 25 | 0.660 | 9 | 54 |
| 30 | 0.713 | 2 | 42 |

Opening guess (before any hint): hint: person 18, water 4, time 3; control: water 64, person 10, time 1. The hint paragraph changed the opener, so the attempt-1 lead is not hint information.

## 2. Hint anchor vs a self-found anchor (rank <= 300)

Control games that found a rank <= 300 word themselves: 75/75. Outcome = best model rank in the next N guesses after the anchor (games with fewer than N guesses left are dropped).

| Window | Group | Anchor ranks | Games | Median anchor guess | Median anchor rank | Median best in window | Solved | Top 10 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | hint | all | 25 | 1 | 300 | 35 | 3 | 5 |
| 10 | control | all | 73 | 5 | 186 | 122 | 9 | 11 |
| 10 | hint | 100-300 | 21 | 1 | 300 | 35 | 1 | 3 |
| 10 | control | 100-300 | 52 | 6 | 234 | 134 | 2 | 3 |
| 15 | hint | all | 25 | 1 | 300 | 14 | 5 | 9 |
| 15 | control | all | 68 | 5 | 163 | 45.5 | 11 | 15 |
| 15 | hint | 100-300 | 21 | 1 | 300 | 16 | 3 | 7 |
| 15 | control | 100-300 | 47 | 5 | 239 | 90 | 2 | 3 |

Guesses needed to beat the anchor rank (games that did): hint median 4 (25/25), control median 4.5 (64/75).

## 3. What the model did with the hint word

Next 5 guesses after the hint; how many ranked at or better than the hint rank.

| Date | Hint (rank) | After guess | Next guesses (rank) | <= hint rank | Thought summary names hint | Report names hint |
| --- | --- | ---: | --- | ---: | :---: | :---: |
| 2026-10-26 | seem (114) | 1 | appear(544) feel(171) sense(116) perception(1099) think(39) | 1/5 | yes | no |
| 2026-10-27 | hibiscus (300) | 1 | flower(303) plant(461) rose(236) petal(317) blossom(90) | 2/5 | yes | yes |
| 2026-10-28 | christmas (300) | 1 | holiday(1120) winter(138) snow(68) frost(1442) blizzard(4313) | 2/5 | yes | no |
| 2026-10-29 | window (300) | 1 | door(115) gate(228) lock(1538) entrance(427) doorway(793) | 2/5 | yes | no |
| 2026-10-30 | plenty (300) | 1 | abundance(3286) time(269) money(925) space(153) room(402) | 2/5 | yes | no |
| 2026-10-31 | result (160) | 1 | outcome(1782) test(465) score(1825) patient(1627) subject(63) | 1/5 | yes | no |
| 2026-11-01 | decommission (300) | 1 | dismantle(2148) commission(588) service(357) retire(860) military(41) | 1/5 | yes | yes |
| 2026-11-02 | particular (138) | 2 | individual(122) specific(637) personal(597) single(909) human(636) | 1/5 | yes | no |
| 2026-11-03 | slayer (242) | 1 | reaper(454) death(382) killer(247) assassin(1133) hunter(161) | 1/5 | yes | yes |
| 2026-11-04 | screenplay (45) | 1 | script(143) film(95) scene(966) movie(540) writer(1) | 1/5 | yes | yes |
| 2026-11-05 | doctor (300) | 1 | nurse(977) patient(445) hospital(487) medical(167) medicine(118) | 2/5 | yes | no |
| 2026-11-06 | tie (224) | 1 | match(122) game(44) play(117) sport(85) player(118) | 5/5 | yes | no |
| 2026-11-07 | dry (300) | 1 | wet(1183) desert(4444) moisture(8948) towel(657) wash(1690) | 0/5 | yes | yes |
| 2026-11-08 | ambition (256) | 1 | success(210) achievement(332) goal(543) victory(6306) motivation(34) | 2/5 | yes | no |
| 2026-11-09 | danger (32) | 5 | victim(240) threat(131) harm(1033) safety(64) risk(529) | 0/5 | yes | yes |
| 2026-11-10 | life (300) | 1 | death(2127) living(1219) human(208) animal(1367) humanity(560) | 1/5 | yes | no |
| 2026-11-11 | fin (300) | 1 | fish(2712) tail(120) wing(750) paw(57) claw(111) | 3/5 | yes | no |
| 2026-11-12 | reservoir (45) | 1 | dam(62) lake(4) pond(12) river(7) stream(64) | 3/5 | yes | yes |
| 2026-11-13 | forward (300) | 1 | front(676) ahead(439) advance(1291) onward(6664) back(276) | 1/5 | yes | yes |
| 2026-11-14 | edible (300) | 1 | food(384) fruit(87) apple(27) pear(101) peach(135) | 4/5 | yes | yes |
| 2026-11-15 | word (110) | 7 | name(694) bro(1783) noun(6796) character(896) term(1157) | 0/5 | yes | yes |
| 2026-11-16 | fury (259) | 1 | anger(3290) fighter(32) boxer(2059) warrior(3) soldier(11) | 3/5 | yes | no |
| 2026-11-17 | occasional (300) | 1 | frequent(730) rare(542) sporadic(4167) infrequent(3528) regular(1397) | 0/5 | yes | no |
| 2026-11-18 | grateful (300) | 1 | thankful(422) gratitude(552) appreciative(7362) blessed(26) blessing(37) | 2/5 | no | no |
| 2026-11-19 | thing (82) | 1 | object(980) entity(2930) human(355) place(479) noun(8101) | 0/5 | yes | yes |

Overall: 40/125 follow-up guesses ranked at or better than the hint; thought summary names the hint word in 24/25 games; strategy report names it in 11/25.

Limitations: archived controls were run three days earlier; anchors differ in timing and in who found them; thought summaries and reports are partial self-reports, and an empty summary does not mean the hint was ignored.
