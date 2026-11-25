"""Offline checks for the optional-hint follow-up. No browser, network or API key is used."""
from contextlib import nullcontext
from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from evaluation_metrics import read_events
from gemini_trial import GameLog
from test_gemini_trial import Client, Response
import hint_analysis as analysis
import hint_study as hint
import study_batch as study

DATES = [(date(2026, 10, 26) + timedelta(days=i)).isoformat() for i in range(25)]
PILOT_DATES = ["2026-10-23", "2026-10-24"]
HINT = ("completion", 300)


def word_for(i):
    """Distinct letters-only filler words (the parser rejects digits)."""
    return "w" + chr(97 + i // 26) + chr(97 + i % 26)


def control_events(date_text, repetition, ranks):
    """Archived control game: one ranked guess per entry; None marks a rejected word."""
    events = [{"event": "start", "puzzle": date_text, "max_guesses": len(ranks), "condition": "control"}]
    for turn, rank in enumerate(ranks, 1):
        word = f"w{repetition}_{turn}"
        events.append({"event": "response", "turn": turn})
        events.append({"event": "feedback", "turn": turn, "guess": word,
                       "feedback": "rank" if rank is not None else "invalid", "rank": rank})
    solved = 1 in ranks
    events.append({"event": "termination", "reason": "success" if solved else "guess_limit"})
    return events


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def synthetic_baseline(root, settings=None):
    """A small archived study with a valid fingerprint, audit, checks and control games."""
    root = Path(root)
    (root / "checks").mkdir(parents=True)
    manifest = {"schema": "contexto-instruction-study/v1", "model": "test-model",
                "settings": settings or hint.SETTINGS, "max_guesses": 30,
                "report_settings": {**(settings or hint.SETTINGS), "max_output_tokens": 512},
                "instructions": {"control": "Control wording. You have up to 30 guesses.",
                                 "guided": "Guided wording."},
                "target_dates": DATES,
                "pilot_games": [{"date": d, "condition": c} for d in PILOT_DATES
                                for c in ("control", "guided")]}
    manifest["fingerprint"] = study.digest(manifest)
    study.write_json(root / "manifest.json", manifest)
    study.write_json(root / "AUDIT.json", {"passed": True})
    for index, target in enumerate(DATES):
        for repetition in (1, 2, 3):
            ranks = [900 + index, 500 - repetition, 300, 120 + repetition] + [100] * 26
            write_events(root / "production" / target / "control" / f"repeat_{repetition:02d}" /
                         "events.jsonl", control_events(target, repetition, ranks))
        study.write_json(root / "checks" / f"production_{target}.json",
                         {"passed": True, "before": {"water": 5, "person": 6, "object": 7},
                          "after": {"water": 5, "person": 6, "object": 7}, "ranks_consistent": True})
    for target in PILOT_DATES:
        write_events(root / "pilot" / target / "control" / "repeat_01" / "events.jsonl",
                     control_events(target, 1, [800, 400] + [90] * 28))
        study.write_json(root / "checks" / f"pilot_{target}.json",
                         {"passed": True, "before": {"water": 5, "person": 6, "object": 7},
                          "after": {"water": 5, "person": 6, "object": 7}, "ranks_consistent": True})
    return root


class HintTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = synthetic_baseline(self.root / "baseline")

    def prepare(self):
        return hint.prepare(self.root / "study", baseline=self.baseline)

    def manifest(self):
        return hint.load_manifest(self.prepare())


class FakeAdapter:
    """Stand-in for the browser adapter. Mirrors the real site: a hint word is 'already guessed'."""
    def __init__(self, ranks=None, hint_word=HINT, default=500):
        self.ranks, self.hint_word, self.default = ranks or {}, hint_word, default
        self.submits, self.hint_calls, self.hint_given = [], [], False

    def submit(self, word, turn):
        self.submits.append((word, turn))
        if self.hint_given and word == self.hint_word[0]:
            return "invalid"
        return self.ranks.get(word, self.default)

    def request_hint(self, turn):
        self.hint_calls.append(turn)
        self.hint_given = True
        return {"word": self.hint_word[0], "rank": self.hint_word[1], "settings": {"Hints": "Easy"},
                "evidence": {"html": "hint.html", "screenshot": "hint.png"}}


def play(case, answers, adapter=None, ranks=None, manifest=None, log=None, client=None):
    manifest = manifest or case.manifest()
    log = log or GameLog(case.root / f"game_{len(list(case.root.iterdir()))}")
    adapter = adapter or FakeAdapter(ranks)
    client = client or Client([Response(a) for a in answers])
    game = {"id": "hint_pilot_2026-10-23", "phase": "pilot", "date": "2026-10-23"}
    reason = hint.play_game(lambda step, request: client.create(**request), log, adapter,
                            manifest, game, show=lambda _: None)
    return reason, client, adapter, read_events(log.path), log


class ParsingTests(unittest.TestCase):
    def test_hint_token_and_ordinary_words(self):
        self.assertEqual(hint.parse_action("[HINT]"), ("hint", None))
        self.assertEqual(hint.parse_action("I will ask.\n[HINT]\n"), ("hint", None))
        self.assertEqual(hint.parse_action(" Animal\n"), ("guess", "animal"))
        self.assertEqual(hint.parse_action("Reasoning first.\nanimal"), ("guess", "animal"))
        self.assertEqual(hint.parse_action("hint"), ("guess", "hint"))  # the word, not the token
        self.assertEqual(hint.parse_action("[HINT] apple"), ("guess", "apple"))  # final token wins

    def test_malformed_outputs_are_rejected(self):
        for text in ["", "   ", "[hint]", "[HINT].", "HINT!", "**animal**", "[HINT", "apple."]:
            with self.assertRaises(ValueError, msg=text):
                hint.parse_action(text)


class PromptAndEligibilityTests(HintTestCase):
    def history(self):
        return [{"kind": "guess", "action": 1, "guess_number": 1, "guess": "water",
                 "feedback": "rank", "rank": 2761},
                {"kind": "guess", "action": 2, "guess_number": 2, "guess": "zzz",
                 "feedback": "invalid", "rank": None}]

    def test_eligibility_needs_a_valid_ranked_guess_and_an_unused_hint(self):
        self.assertFalse(hint.hint_eligible([]))
        self.assertFalse(hint.hint_eligible(self.history()[1:]))  # rejected word only
        self.assertTrue(hint.hint_eligible(self.history()))
        used = self.history() + [{"kind": "hint", "action": 3, "after_guess": 2,
                                  "word": "completion", "rank": 300}]
        self.assertFalse(hint.hint_eligible(used))
        self.assertEqual([hint.hint_status(h) for h in ([], self.history(), used)],
                         ["unavailable", "available", "used"])

    def test_hint_is_available_until_the_final_attempt_is_spent(self):
        full = [{"kind": "guess", "action": n, "guess_number": n, "guess": f"w{n}",
                 "feedback": "rank", "rank": 100} for n in range(1, 30)]
        self.assertTrue(hint.hint_eligible(full))  # one guess still remains
        full.append({"kind": "guess", "action": 30, "guess_number": 30, "guess": "w30",
                     "feedback": "rank", "rank": 100})
        self.assertFalse(hint.hint_eligible(full))

    def test_prompt_states_remaining_guesses_hint_status_and_keeps_labelled_hint(self):
        instructions = "Basic wording."
        first = hint.build_hint_prompt([], instructions)
        self.assertTrue(first.startswith(instructions))
        self.assertIn("Guess attempts remaining: 30 of 30.", first)
        self.assertIn("Hint status: not yet available", first)
        self.assertIn("No actions yet.", first)
        history = self.history()
        prompt = hint.build_hint_prompt(history, instructions)
        self.assertIn("Guess attempts remaining: 28 of 30.", prompt)
        self.assertIn("Hint status: available", prompt)
        history.append({"kind": "hint", "action": 3, "after_guess": 2, "word": "completion", "rank": 300})
        history.append({"kind": "guess", "action": 4, "guess_number": 3, "guess": "person",
                        "feedback": "rank", "rank": 40})
        prompt = hint.build_hint_prompt(history, instructions)
        self.assertIn("Guess attempts remaining: 27 of 30.", prompt)
        self.assertIn("Hint status: already used", prompt)
        lines = [l for l in prompt.splitlines() if l.startswith("Action ")]
        self.assertEqual(lines, [
            "Action 4 (guess 3): person -> rank 40",
            "Action 3 (hint after guess 2): completion -> rank 300 [website hint; not your guess]",
            "Action 2 (guess 2): zzz -> rejected as invalid by Contexto",
            "Action 1 (guess 1): water -> rank 2761"])  # newest first, separate numbering

    def test_consumed_local_failures_are_labelled(self):
        history = [{"kind": "guess", "action": 1, "guess_number": 1, "guess": "[HINT]",
                    "feedback": "ineligible_hint", "rank": None}]
        prompt = hint.build_hint_prompt(history, "Basic.")
        self.assertIn("hint request not eligible; attempt consumed", prompt)
        self.assertIn("Guess attempts remaining: 29 of 30.", prompt)


class ProtocolFreezeTests(HintTestCase):
    def test_ceilings_match_the_plan(self):
        self.assertEqual(hint.LIMITS["production_action"] + hint.LIMITS["production_report"], 800)
        self.assertEqual(hint.LIMITS["pilot_action"] + hint.LIMITS["pilot_report"], 64)
        self.assertEqual(hint.MAX_REQUESTS, 874)
        self.assertEqual(hint.RETRY_RESERVE, 10)
        self.assertEqual(sum(hint.LIMITS.values()) + hint.RETRY_RESERVE, 874)

    def test_prepare_is_offline_reads_baseline_and_freezes_everything(self):
        with patch.object(hint, "create_client", side_effect=AssertionError("network")):
            directory = self.prepare()
        manifest = hint.load_manifest(directory)
        archived = json.loads((self.baseline / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["model"], archived["model"])
        self.assertEqual(manifest["settings"], archived["settings"])
        self.assertEqual(manifest["target_dates"], DATES)
        self.assertEqual([g["date"] for g in manifest["games"]], DATES)  # chronological
        self.assertEqual([g["date"] for g in manifest["pilot_games"]], PILOT_DATES)
        self.assertEqual(manifest["max_guesses"], 30)
        self.assertEqual(manifest["seed"], 20261123)
        self.assertTrue(manifest["hint_instructions"].startswith(archived["instructions"]["control"]))
        self.assertIn(hint.HINT_TOKEN, manifest["hint_instructions"])
        self.assertEqual(len(manifest["baseline"]["control_games"]), 25 * 3 + 2)
        self.assertEqual(manifest["maximum_requests"], 874)
        self.assertEqual(manifest["automatic_retries"], False)
        manifest["max_guesses"] = 70
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest"):
            hint.load_manifest(directory)

    def test_changed_baseline_blocks_execution(self):
        directory = self.prepare()
        path = self.baseline / "production" / DATES[3] / "control" / "repeat_02" / "events.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "[Bb]aseline"):
            hint.load_manifest(directory)

    def test_prepare_stops_on_incomplete_baseline(self):
        (self.baseline / "production" / DATES[0] / "control" / "repeat_03" / "events.jsonl").unlink()
        with self.assertRaises(ValueError):
            self.prepare()

    def test_original_study_is_untouched_by_a_hint_study_directory(self):
        before = (self.baseline / "manifest.json").read_bytes()
        self.prepare()
        self.assertEqual((self.baseline / "manifest.json").read_bytes(), before)
        self.assertFalse(list(self.baseline.glob("hint*")))

    def test_preflight_refuses_unavailable_model_without_interactions(self):
        directory = self.prepare()
        client = Client([])
        client.models = SimpleNamespace(get=lambda **_: (_ for _ in ()).throw(ValueError("not found")))
        with self.assertRaises(ValueError):
            hint.preflight(directory, hint.load_manifest(directory), client)
        self.assertFalse(client.requests)


class ControllerTests(HintTestCase):
    def test_request_is_stateless_and_uses_archived_settings(self):
        manifest = self.manifest()
        reason, client, _, _, _ = play(self, ["water"] * 30, manifest=manifest, ranks={"water": 100})
        request = client.requests[0]
        self.assertEqual(request["model"], manifest["model"])
        self.assertEqual(request["generation_config"], manifest["settings"])
        self.assertEqual(request["tools"], [])
        self.assertFalse(request["store"])
        self.assertNotIn("previous_interaction_id", request)
        self.assertIn("Guess attempts remaining: 30 of 30.", request["input"])

    def test_hint_does_not_consume_a_guess_and_numbers_stay_separate(self):
        answers = ["water", "[HINT]"] + [word_for(i) for i in range(29)]
        reason, client, adapter, events, _ = play(self, answers, ranks={"water": 2761})
        self.assertEqual(reason, "guess_limit")
        self.assertEqual(len(client.requests), 31)  # 30 guesses + 1 hint
        self.assertEqual(adapter.hint_calls, [2])
        feedback = [e for e in events if e["event"] == "feedback"]
        self.assertEqual([e["guess_number"] for e in feedback], list(range(1, 31)))
        self.assertEqual([e["turn"] for e in feedback][:3], [1, 3, 4])  # action 2 was the hint
        delivered = [e for e in events if e["event"] == "hint_delivered"]
        self.assertEqual(len(delivered), 1)
        self.assertEqual((delivered[0]["turn"], delivered[0]["after_guess"]), (2, 1))
        self.assertEqual(events[-1]["event"], "termination")
        self.assertEqual(events[-1]["attempts_used"], 30)
        self.assertTrue(events[-1]["hint_delivered"])

    def test_every_later_prompt_retains_the_labelled_hint(self):
        answers = ["water", "[HINT]", "person", "object"] + [word_for(i) for i in range(27)]
        _, client, _, _, _ = play(self, answers, ranks={"water": 2761, "person": 40})
        for request in client.requests[2:]:
            self.assertIn("completion -> rank 300 [website hint; not your guess]", request["input"])
            self.assertIn("Hint status: already used", request["input"])
        self.assertIn("Hint status: available", client.requests[1]["input"])

    def test_hint_before_any_ranked_guess_is_ineligible_and_consumes_an_attempt(self):
        answers = ["[HINT]"] + [word_for(i) for i in range(29)]
        reason, client, adapter, events, _ = play(self, answers)
        self.assertEqual(adapter.hint_calls, [])  # the website is never asked
        first = next(e for e in events if e["event"] == "feedback")
        self.assertEqual((first["feedback"], first["guess_number"]), ("ineligible_hint", 1))
        self.assertEqual(len(client.requests), 30)

    def test_rejected_word_does_not_unlock_the_hint(self):
        answers = ["zzz", "[HINT]"] + [word_for(i) for i in range(28)]
        _, _, adapter, events, _ = play(self, answers, ranks={"zzz": "invalid"})
        self.assertEqual(adapter.hint_calls, [])
        self.assertEqual([e["feedback"] for e in events if e["event"] == "feedback"][:2],
                         ["invalid", "ineligible_hint"])

    def test_second_hint_request_is_ineligible_and_consumes_an_attempt(self):
        answers = ["water", "[HINT]", "[HINT]"] + [word_for(i) for i in range(28)]
        reason, client, adapter, events, _ = play(self, answers, ranks={"water": 900})
        self.assertEqual(adapter.hint_calls, [2])
        feedback = [e for e in events if e["event"] == "feedback"]
        self.assertEqual(feedback[1]["feedback"], "ineligible_hint")
        self.assertEqual(len(client.requests), 31)

    def test_hint_on_the_last_remaining_guess_is_still_eligible(self):
        answers = [word_for(i) for i in range(29)] + ["[HINT]", "final"]
        reason, client, adapter, _, _ = play(self, answers, ranks={word_for(i): 100 for i in range(29)})
        self.assertEqual(adapter.hint_calls, [30])
        self.assertEqual(len(client.requests), 31)

    def test_hint_never_makes_more_than_31_requests_in_the_worst_case(self):
        answers = ["[HINT]"] * 40
        reason, client, _, _, _ = play(self, answers)
        self.assertEqual(len(client.requests), 30)  # all ineligible; each consumes a guess
        self.assertEqual(reason, "guess_limit")

    def test_direct_answer_reveal_terminates_without_a_model_solve(self):
        adapter = FakeAdapter({"water": 2}, hint_word=("target", 1))
        reason, client, _, events, _ = play(self, ["water", "[HINT]", "never"], adapter=adapter)
        self.assertEqual(reason, "answer_revealed_by_hint")
        self.assertEqual(len(client.requests), 2)
        end = events[-1]
        self.assertEqual((end["reason"], end["success"], end["hint_delivered"]),
                         ("answer_revealed_by_hint", False, True))
        record = analysis.game_record(events)
        self.assertTrue(record["complete"])
        self.assertTrue(record["revealed"])
        self.assertFalse(record["solved"])
        self.assertEqual(analysis.trajectory(events)[:3], [2, 2, 2])  # never rank 1
        self.assertEqual(analysis.trajectory(events)[-1], 2)

    def test_model_solve_is_a_success(self):
        reason, client, _, events, _ = play(self, ["water", "target"], ranks={"water": 80, "target": 1})
        self.assertEqual(reason, "success")
        record = analysis.game_record(events)
        self.assertTrue(record["solved"] and not record["revealed"])
        self.assertEqual(record["guesses_to_solve"], 2)
        self.assertEqual(analysis.trajectory(events)[1:3], [1, 1])

    def test_guessing_the_hint_word_is_an_invalid_attempt_with_no_credit(self):
        answers = ["water", "[HINT]", "completion", "person"] + [word_for(i) for i in range(27)]
        _, _, adapter, events, _ = play(self, answers, ranks={"water": 2761, "person": 40})
        feedback = [e for e in events if e["event"] == "feedback"]
        repeat = next(e for e in feedback if e["guess"] == "completion")
        self.assertEqual((repeat["feedback"], repeat["rank"]), ("invalid", None))
        record = analysis.game_record(events)
        self.assertEqual(record["best_rank"], 40)  # never the hint's rank 300 or better
        self.assertGreaterEqual(record["invalid_attempts"], 1)

    def test_repeated_and_malformed_outputs_consume_attempts_without_the_website(self):
        answers = ["water", "water", "two words are not one!", "person"] + [word_for(i) for i in range(26)]
        _, client, adapter, events, _ = play(self, answers, ranks={"water": 100})
        feedback = [e for e in events if e["event"] == "feedback"]
        self.assertEqual([e["feedback"] for e in feedback[:3]], ["rank", "duplicate", "invalid_output"])
        self.assertEqual([w for w, _ in adapter.submits].count("water"), 1)

    def test_incomplete_response_status_is_an_invalid_attempt(self):
        client = Client([Response("water", status="failed")] + [Response(word_for(i)) for i in range(29)])
        _, _, _, events, _ = play(self, [], client=client)
        self.assertEqual(next(e for e in events if e["event"] == "feedback")["feedback"], "invalid_output")

    def test_api_failure_stops_without_retry(self):
        client = Client([Response("water"), RuntimeError("boom")])
        reason, _, _, events, _ = play(self, [], client=client, ranks={"water": 10})
        self.assertEqual(reason, "api_error")
        self.assertEqual(len(client.requests), 2)
        self.assertFalse(analysis.game_record(events)["complete"])

    def test_requests_are_journaled_before_dispatch(self):
        order = []
        client = Client([Response("water")])
        log = GameLog(self.root / "journal")
        def create(step, request):
            order.append([e["event"] for e in read_events(log.path)][-1])
            raise RuntimeError("stop")
        game = {"id": "g", "phase": "pilot", "date": "2026-10-23"}
        hint.play_game(create, log, FakeAdapter(), self.manifest(), game, show=lambda _: None)
        self.assertEqual(order, ["request"])


class RecoveryTests(HintTestCase):
    def crash_after(self, answers, ranks, stop_after_events=None):
        """Play until the client raises; the saved log is then a genuinely interrupted game."""
        manifest = self.manifest()
        log = GameLog(self.root / "interrupted")
        client = Client([Response(a) for a in answers] + [RuntimeError("network down")])
        adapter = FakeAdapter(ranks)
        game = {"id": "hint_pilot_2026-10-23", "phase": "pilot", "date": "2026-10-23"}
        reason = hint.play_game(lambda s, r: client.create(**r), log, adapter, manifest, game,
                                show=lambda _: None)
        self.assertEqual(reason, "api_error")
        return manifest, log, game

    def resume(self, manifest, log, game, answers, adapter):
        client = Client([Response(a) for a in answers])
        reason = hint.play_game(lambda s, r: client.create(**r), log, adapter, manifest, game,
                                show=lambda _: None)
        return reason, client

    def test_resume_replays_guesses_and_hint_without_regenerating(self):
        manifest, log, game = self.crash_after(["water", "[HINT]", "person"], {"water": 2761, "person": 40})
        adapter = FakeAdapter({"water": 2761, "person": 40})
        reason, client = self.resume(manifest, log, game, [word_for(i) for i in range(28)], adapter)
        self.assertEqual(reason, "guess_limit")
        self.assertEqual([w for w, _ in adapter.submits[:2]], ["water", "person"])  # replay order
        self.assertEqual(adapter.hint_calls[0], 2)
        self.assertEqual(len(client.requests), 28)  # only the missing guesses
        events = read_events(log.path)
        self.assertTrue(any(e["event"] == "browser_replay_verified" for e in events))
        self.assertEqual(analysis.game_record(events)["attempts"], 30)
        self.assertEqual(len([e for e in events if e["event"] == "hint_delivered"]), 1)  # a replay is not a new delivery

    def test_replay_order_places_hint_between_the_guesses(self):
        manifest, log, game = self.crash_after(["water", "[HINT]", "person"], {"water": 2761})
        calls = []
        class Spy(FakeAdapter):
            def submit(self, word, turn):
                calls.append(("guess", word)); return super().submit(word, turn)
            def request_hint(self, turn):
                calls.append(("hint", turn)); return super().request_hint(turn)
        self.resume(manifest, log, game, [word_for(i) for i in range(28)], Spy({"water": 2761}))
        self.assertEqual(calls[:3], [("guess", "water"), ("hint", 2), ("guess", "person")])

    def test_changed_rank_on_replay_stops_before_any_model_request(self):
        manifest, log, game = self.crash_after(["water", "person"], {"water": 100, "person": 50})
        client = Client([Response("never")])
        with self.assertRaisesRegex(ValueError, "changed"):
            hint.play_game(lambda s, r: client.create(**r), log, FakeAdapter({"water": 101}),
                           manifest, game, show=lambda _: None)
        self.assertFalse(client.requests)

    def test_changed_hint_on_replay_stops(self):
        manifest, log, game = self.crash_after(["water", "[HINT]"], {"water": 2761})
        client = Client([Response("never")])
        with self.assertRaisesRegex(ValueError, "changed"):
            hint.play_game(lambda s, r: client.create(**r), log,
                           FakeAdapter({"water": 2761}, hint_word=("completion", 299)),
                           manifest, game, show=lambda _: None)
        self.assertFalse(client.requests)

    def test_ambiguous_hint_delivery_stops_for_investigation(self):
        manifest, log, game = self.crash_after(["water"], {"water": 2761})
        log.write("request", turn=2, request={"input": "x"})
        log.write("response", turn=2, raw_response=Response("[HINT]").raw)
        log.write("hint_dispatch", turn=2, after_guess=1)  # crash before delivery was recorded
        client = Client([Response("never")])
        adapter = FakeAdapter({"water": 2761})
        with self.assertRaisesRegex(ValueError, "[Aa]mbiguous"):
            hint.play_game(lambda s, r: client.create(**r), log, adapter, manifest, game,
                           show=lambda _: None)
        self.assertFalse(client.requests)
        self.assertFalse(adapter.submits)  # nothing replayed either

    def test_saved_response_without_outcome_is_reused(self):
        manifest = self.manifest()
        log = GameLog(self.root / "pending")
        game = {"id": "hint_pilot_2026-10-23", "phase": "pilot", "date": "2026-10-23"}
        client = Client([Response("water")])
        adapter = FakeAdapter({"water": 100})
        class Crash(FakeAdapter):
            def submit(self, word, turn):
                raise RuntimeError("browser died")
        hint.play_game(lambda s, r: client.create(**r), log, Crash(), manifest, game, show=lambda _: None)
        self.assertEqual(len(client.requests), 1)
        resumed = Client([Response(word_for(i)) for i in range(29)])
        hint.play_game(lambda s, r: resumed.create(**r), log, adapter, manifest, game, show=lambda _: None)
        self.assertEqual(adapter.submits[0][0], "water")  # the saved answer, not a new one
        self.assertEqual(len(resumed.requests), 29)
        self.assertTrue(any(e["event"] == "reuse_saved_response" for e in read_events(log.path)))

    def test_finished_game_cannot_be_resumed(self):
        manifest = self.manifest()
        reason, _, _, _, log = play(self, ["water"], ranks={"water": 1}, manifest=manifest)
        self.assertEqual(reason, "success")
        game = {"id": "hint_pilot_2026-10-23", "phase": "pilot", "date": "2026-10-23"}
        with self.assertRaises(ValueError):
            hint.play_game(lambda s, r: None, log, FakeAdapter(), manifest, game, show=lambda _: None)

    def test_recover_restores_returned_answer_from_the_journal(self):
        directory = self.prepare()
        manifest = hint.load_manifest(directory)
        game = manifest["pilot_games"][0]
        path = hint.game_directory(directory, game)
        log = GameLog(path)
        log.write("start", puzzle=game["date"], model=manifest["model"], max_guesses=30,
                  instructions=manifest["hint_instructions"], generation_config=manifest["settings"])
        request = {"input": "saved"}
        log.write("request", turn=1, request=request)
        ledger = study.RequestLedger(directory, manifest["limits"], manifest["retry_reserve"])
        reservation = ledger.reserve(game["id"], "pilot_action", 1, request)
        ledger.finish(reservation, raw=Response("water").raw)
        hint.recover(directory, game["id"])
        events = read_events(log.path)
        self.assertEqual(len([e for e in events if e["event"] == "response"]), 1)
        self.assertEqual(events[-1]["reason"], "recovered_pending")
        self.assertEqual(len(study.RequestLedger(directory, manifest["limits"], 10).reservations), 1)

    def test_recover_refuses_an_ambiguous_hint_unless_explicitly_resolved(self):
        directory = self.prepare()
        manifest = hint.load_manifest(directory)
        game = manifest["pilot_games"][0]
        log = GameLog(hint.game_directory(directory, game))
        log.write("start", puzzle=game["date"])
        log.write("hint_dispatch", turn=2, after_guess=1)
        with self.assertRaisesRegex(ValueError, "[Aa]mbiguous"):
            hint.recover(directory, game["id"])
        hint.recover(directory, game["id"], resolve_ambiguous_hint=True)
        events = read_events(log.path)
        self.assertTrue(any(e["event"] == "hint_ambiguity_resolved" for e in events))
        state = hint.state_from_events(events)
        self.assertFalse(state["ambiguous"])


class LedgerTests(HintTestCase):
    def test_action_budget_caps_requests_per_phase_and_total(self):
        directory = self.prepare()
        manifest = hint.load_manifest(directory)
        ledger = study.RequestLedger(directory, manifest["limits"], manifest["retry_reserve"])
        for i in range(62):
            ledger.reserve(f"pilot_{i // 31}", "pilot_action", i % 31 + 1, {})
        with self.assertRaises(ValueError):
            ledger.reserve("pilot_extra", "pilot_action", 1, {})
        ledger.reserve("pilot_0", "pilot_report", 1, {})
        ledger.reserve("pilot_1", "pilot_report", 1, {})
        with self.assertRaises(ValueError):
            ledger.reserve("pilot_2", "pilot_report", 1, {})

    def test_retry_reserve_is_ten_and_automatic_retries_are_disabled(self):
        manifest = self.manifest()
        self.assertEqual(manifest["retry_reserve"], 10)
        self.assertEqual(manifest["settings"], hint.SETTINGS)
        text = Path(hint.__file__).read_text(encoding="utf-8")
        self.assertIn("create_client", text)  # reuses the original no-retry client


class ComparisonTests(unittest.TestCase):
    def test_trajectory_ignores_hint_events_and_carries_forward(self):
        events = [{"event": "start", "max_guesses": 30},
                  {"event": "feedback", "turn": 1, "guess_number": 1, "guess": "a",
                   "feedback": "rank", "rank": 900},
                  {"event": "hint_delivered", "turn": 2, "after_guess": 1, "word": "h", "rank": 5},
                  {"event": "feedback", "turn": 3, "guess_number": 2, "guess": "b",
                   "feedback": "invalid", "rank": None},
                  {"event": "feedback", "turn": 4, "guess_number": 3, "guess": "c",
                   "feedback": "rank", "rank": 400}]
        self.assertEqual(analysis.trajectory(events, 5), [900, 900, 400, 400, 400])

    def test_hint_word_rank_never_improves_trajectory_even_if_the_site_returned_it(self):
        events = [{"event": "start", "max_guesses": 3},
                  {"event": "feedback", "turn": 1, "guess_number": 1, "guess": "a",
                   "feedback": "rank", "rank": 900},
                  {"event": "hint_delivered", "turn": 2, "after_guess": 1, "word": "h", "rank": 5},
                  {"event": "feedback", "turn": 3, "guess_number": 2, "guess": "h",
                   "feedback": "rank", "rank": 5}]
        self.assertEqual(analysis.trajectory(events, 3), [900, 900, 900])
        self.assertEqual(analysis.game_record(events)["best_rank"], 900)

    def test_incomplete_game_is_never_complete(self):
        events = [{"event": "start", "max_guesses": 30},
                  {"event": "response", "turn": 1},
                  {"event": "feedback", "turn": 1, "guess_number": 1, "guess": "a",
                   "feedback": "rank", "rank": 900},
                  {"event": "termination", "reason": "api_error"}]
        record = analysis.game_record(events)
        self.assertFalse(record["complete"])

    def test_scores_use_win_tie_loss_and_equal_target_weights(self):
        controls = [[100] * 30] * 3
        self.assertEqual(analysis.score_target([10] * 30, controls), 1.0)
        self.assertEqual(analysis.score_target([100] * 30, controls), 0.5)
        self.assertEqual(analysis.score_target([500] * 30, controls), 0.0)
        mixed = [10] * 15 + [500] * 15
        self.assertEqual(analysis.score_target(mixed, controls), 0.5)
        self.assertEqual(analysis.score_target([None] * 30, [[None] * 30] * 3), 0.5)
        self.assertEqual(analysis.score_target([50] * 30, [[None] * 30] * 3), 1.0)

    def test_comparison_aggregates_by_target_with_exact_seeded_bootstrap(self):
        targets = {"a": {"new": [10] * 30, "controls": [[100] * 30] * 3},
                   "b": {"new": [500] * 30, "controls": [[100] * 30] * 3},
                   "c": {"new": [100] * 30, "controls": [[100] * 30] * 3}}
        result = analysis.compare(targets, samples=500)
        self.assertEqual(result["targets"], 3)
        self.assertEqual(result["target_scores"], {"a": 1.0, "b": 0.0, "c": 0.5})
        self.assertEqual(result["score"], 0.5)
        self.assertEqual(result["seed"], 20261123)
        self.assertEqual(result, analysis.compare(targets, samples=500))
        lo, hi = result["ci95"]
        self.assertLessEqual(lo, 0.5)
        self.assertGreaterEqual(hi, 0.5)

    def test_every_baseline_game_must_be_verified_and_exclusions_are_reported(self):
        games = {"a": {"new": [10] * 30, "controls": [[100] * 30] * 3, "reasons": []},
                 "b": {"new": None, "controls": [[100] * 30] * 3, "reasons": ["new game incomplete"]},
                 "c": {"new": [10] * 30, "controls": [[100] * 30] * 2, "reasons": []}}
        included, excluded = analysis.select_targets(games)
        self.assertEqual(sorted(included), ["a"])
        self.assertEqual(excluded["b"], ["new game incomplete"])
        self.assertIn("fewer than three verified baseline games", excluded["c"][0])

    def test_game_metrics_and_top_rates(self):
        records = [{"complete": True, "solved": True, "revealed": False, "best_rank": 1,
                    "invalid_attempts": 2},
                   {"complete": True, "solved": False, "revealed": False, "best_rank": 9,
                    "invalid_attempts": 0},
                   {"complete": True, "solved": False, "revealed": False, "best_rank": 60,
                    "invalid_attempts": 1},
                   {"complete": True, "solved": False, "revealed": False, "best_rank": None,
                    "invalid_attempts": 0}]
        summary = analysis.outcome_summary(records)
        self.assertEqual((summary["games"], summary["solved"]), (4, 1))
        self.assertEqual(summary["solve_rate"], 0.25)
        self.assertEqual(summary["top10_rate"], 0.5)
        self.assertEqual(summary["top50_rate"], 0.5)
        self.assertEqual(summary["top100_rate"], 0.75)
        self.assertEqual(summary["invalid_attempts"], 3)
        self.assertEqual(summary["median_best_rank"], 34.5)

    def test_revealed_games_are_not_solves_in_outcome_summary(self):
        record = {"complete": True, "solved": False, "revealed": True, "best_rank": 2, "invalid_attempts": 0}
        summary = analysis.outcome_summary([record])
        self.assertEqual((summary["solved"], summary["revealed"]), (0, 1))

    def test_historical_replay_comparison_detects_changed_ranks_and_rejections(self):
        archived = [{"guess": "a", "feedback": "rank", "rank": 10},
                    {"guess": "b", "feedback": "invalid", "rank": None},
                    {"guess": "c", "feedback": "duplicate", "rank": None}]
        self.assertEqual(hint.compare_replay(archived, {"a": 10, "b": "invalid"}), [])
        self.assertTrue(hint.compare_replay(archived, {"a": 11, "b": "invalid"}))
        self.assertTrue(hint.compare_replay(archived, {"a": 10, "b": 7}))
        self.assertTrue(hint.compare_replay(archived, {"a": 10}))

    def test_sentinel_comparison_requires_both_before_and_after_to_match(self):
        archived = {"before": {"water": 1}, "after": {"water": 1}}
        self.assertEqual(hint.compare_sentinels(archived, {"water": 1}, {"water": 1}), [])
        self.assertTrue(hint.compare_sentinels(archived, {"water": 2}, {"water": 1}))
        self.assertTrue(hint.compare_sentinels(archived, {"water": 1}, {"water": 2}))


class EndToEndTests(HintTestCase):
    """Pilot, probe, production, audit and summary with a fake browser and a fake model."""
    def setUp(self):
        super().setUp()
        self.directory = self.prepare()
        self.clients = []

    def client_factory(self, key):
        # Each game: a first guess, a hint request, then guesses until the budget is spent.
        responses = [Response("water"), Response("[HINT]")] + [Response(word_for(i)) for i in range(29)]
        responses.append(Response("I used the hint after a first anchor word because progress had stalled."))
        client = Client(responses)
        client.close = lambda: None
        client.models = SimpleNamespace(get=lambda **_: Response("model"))
        self.clients.append(client)
        return client

    def run_phase(self, phase, replay=None):
        evidence = self.root / "evidence"
        evidence.mkdir(exist_ok=True)
        class Browser:
            hinted = set()
            def __init__(self, page, log, **kwargs):
                self.log, self.artifacts = log, evidence
                self.settings = kwargs.get("expected_settings")
            def open_game(self, target):
                self.log.write("browser_ready", requested_date=target.isoformat(), fresh_game=True)
                self.hinted = False
            def read_settings(self):
                return {"Hints": "Easy", "Sort by": "Similarity"}
            def submit(self, word, turn):
                self.log.write("browser_submit", turn=turn, guess=word)
                rank = 2761 if word == "water" else 400
                observed = {"kind": "rank", "word": word, "rank": rank, "repeated": False}
                self.log.write("browser_feedback", turn=turn, submitted_word=word, observed=observed)
                return rank
            def request_hint(self, turn):
                (evidence / f"hint_{turn}.html").write_text("<html></html>", encoding="utf-8")
                (evidence / f"hint_{turn}.png").write_bytes(b"png")
                result = {"word": "completion", "rank": 300, "settings": self.read_settings(),
                          "evidence": {"html": str(evidence / f"hint_{turn}.html"),
                                       "screenshot": str(evidence / f"hint_{turn}.png")}}
                self.log.write("browser_hint", turn=turn, observed=result)
                return result
            def snapshot(self, name):
                pass
        context = SimpleNamespace(new_page=lambda: None, close=lambda: None)
        browser = SimpleNamespace(new_context=lambda **_: context, close=lambda: None)
        playwright = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **_: browser))
        sentinel = lambda *a, **k: {"water": 5, "person": 6, "object": 7}
        archive = {"before": {"water": 5, "person": 6, "object": 7},
                   "after": {"water": 5, "person": 6, "object": 7}}
        with patch.object(hint, "read_api_key", return_value="test-secret"), \
             patch.object(hint, "create_client", side_effect=self.client_factory), \
             patch.object(hint, "HintBrowser", Browser), \
             patch.object(hint, "sentinel_probe", side_effect=sentinel), \
             patch.object(hint, "replay_baseline", return_value=[] if replay is None else replay), \
             patch("playwright.sync_api.sync_playwright", side_effect=lambda: nullcontext(playwright)), \
             patch("builtins.print"):
            return hint.execute(self.directory, phase)

    def write_probe(self):
        study.write_json(self.directory / "probe.json", {
            "passed": True, "expected_settings": {"Hints": "Easy", "Sort by": "Similarity"},
            "default_hint_difficulty": "Easy", "dates": {}})

    def test_execution_requires_probe_and_pilot_first(self):
        with self.assertRaisesRegex(ValueError, "probe"):
            self.run_phase("pilot")
        self.write_probe()
        with self.assertRaisesRegex(ValueError, "pilot"):
            self.run_phase("production")

    def test_pilot_then_production_are_auditable_idempotent_and_within_ceilings(self):
        self.write_probe()
        self.assertEqual(self.run_phase("pilot"), 0)
        self.assertTrue(hint.audit(self.directory, "pilot")["passed"])
        pilot_requests = len(study.RequestLedger(self.directory, hint.LIMITS, 10).reservations)
        self.assertEqual(pilot_requests, 2 * (31 + 1))
        self.assertEqual(self.run_phase("production"), 0)
        result = hint.audit(self.directory, "production")
        self.assertTrue(result["passed"], [c for c in result["checks"] if not c["passed"]])
        total = len(study.RequestLedger(self.directory, hint.LIMITS, 10).reservations)
        self.assertEqual(total, 27 * 32)
        self.assertLessEqual(total, 874)
        self.assertEqual(self.run_phase("production"), 0)  # idempotent: nothing is regenerated
        self.assertEqual(len(study.RequestLedger(self.directory, hint.LIMITS, 10).reservations), total)
        summary = json.loads((self.directory / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["completed"], 25)
        self.assertEqual(summary["comparison"]["targets"], 25)
        self.assertEqual(summary["hint"]["delivered"], 25)
        for name in ("results.csv", "trajectories.csv", "target_scores.csv", "strategy_reports.csv"):
            self.assertTrue((self.directory / name).exists(), name)

    def test_contaminated_prompt_or_missing_hint_evidence_fails_the_audit(self):
        self.write_probe()
        self.run_phase("pilot")
        self.assertTrue(hint.audit(self.directory, "pilot")["passed"])
        manifest = hint.load_manifest(self.directory)
        path = hint.game_directory(self.directory, manifest["pilot_games"][0]) / "events.jsonl"
        original = path.read_text(encoding="utf-8")
        events = read_events(path)
        next(e for e in events if e["event"] == "request")["request"]["input"] = "contaminated"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        self.assertFalse(hint.audit(self.directory, "pilot")["passed"])
        path.write_text(original, encoding="utf-8")
        self.assertTrue(hint.audit(self.directory, "pilot")["passed"])
        (self.root / "evidence" / "hint_2.png").unlink()
        self.assertFalse(hint.audit(self.directory, "pilot")["passed"])

    def test_scoring_drift_stops_the_target_and_nothing_is_substituted(self):
        self.write_probe()
        self.run_phase("pilot")
        self.assertEqual(self.run_phase("production", replay=["rank changed"]), 1)
        manifest = hint.load_manifest(self.directory)
        started = [g for g in manifest["games"]
                   if (hint.game_directory(self.directory, g) / "events.jsonl").exists()]
        self.assertEqual(started, [])  # stopped before the first model request
        marker = json.loads((self.directory / "checks" / "production_2026-10-26.json").read_text(encoding="utf-8"))
        self.assertFalse(marker["passed"])

    def test_changed_hint_settings_stop_execution(self):
        self.write_probe()
        study.write_json(self.directory / "probe.json", {
            "passed": True, "expected_settings": {"Hints": "Hard", "Sort by": "Similarity"},
            "default_hint_difficulty": "Hard", "dates": {}})
        self.assertEqual(self.run_phase("pilot"), 1)


if __name__ == "__main__":
    unittest.main()
