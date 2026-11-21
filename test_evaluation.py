"""Offline checks for evaluation budgets, error handling and scientific measures."""
from datetime import date
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate_batch
from evaluation_metrics import aggregate, game_metrics, read_events
from gemini_trial import GameLog, run_game
from test_gemini_trial import Client, Response


class EvaluationTests(unittest.TestCase):
    def run_trial(self, responses, feedback, limit):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        log = GameLog(Path(temporary.name) / "game")
        submitted = []
        def submit(guess, turn):
            submitted.append((guess, turn))
            return feedback[len(submitted) - 1]
        client = Client(responses)
        reason = run_game(client, log, "test", "2026-10-25", max_guesses=limit,
                          evaluation=True, get_feedback=submit, show=lambda _: None)
        return reason, client, submitted, read_events(log.path), log

    def test_full_70_attempt_budget_with_duplicates_and_malformed_answers(self):
        responses = [Response("water"), Response("water"), Response("**word**")]
        responses.extend(Response("water") for _ in range(67))
        reason, client, submitted, events, log = self.run_trial(responses, [100], 70)
        self.assertEqual(reason, "guess_limit")
        self.assertEqual(len(client.requests), 70)
        self.assertEqual(submitted, [("water", 1)])
        metrics = game_metrics(events)
        self.assertTrue(metrics["complete"])
        self.assertEqual(metrics["attempts"], 70)
        self.assertEqual(metrics["invalid_attempts"], 69)
        self.assertEqual(metrics["mean_progression"], 0)
        self.assertIn("70 attempts", client.requests[0]["input"])
        self.assertIn("duplicate guess", client.requests[2]["input"])
        self.assertIn("invalid model output", client.requests[3]["input"])

    def test_history_final_token_parser_and_fresh_stateless_requests(self):
        reason, client, submitted, events, log = self.run_trial(
            [Response("water"), Response("I choose fire"), Response("guard")], [100, 20, 1], 70)
        self.assertEqual(reason, "success")
        self.assertEqual(submitted, [("water", 1), ("fire", 2), ("guard", 3)])
        prompt = client.requests[2]["input"]
        self.assertLess(prompt.index("Turn 2:"), prompt.index("Turn 1:"))
        self.assertTrue(all(not r["store"] and "previous_interaction_id" not in r
                            for r in client.requests))
        self.assertEqual(game_metrics(events)["guesses_to_solve"], 3)

    def test_api_failure_is_incomplete_not_unsolved_and_not_retried(self):
        reason, client, submitted, events, log = self.run_trial(
            [Response("water"), RuntimeError("connection failed")], [100], 70)
        self.assertEqual(reason, "api_error")
        self.assertEqual(len(client.requests), 2)
        self.assertFalse(game_metrics(events)["complete"])
        self.assertIsNone(aggregate([game_metrics(events)])["solve_rate"])

    def test_resume_preserves_total_budget_and_does_not_repeat_model_calls(self):
        _, _, _, events, log = self.run_trial([Response("water")], [100], 1)
        # Fixture represents the prefix of a longer interrupted game.
        events[0]["max_guesses"] = 3
        events[-1]["reason"] = "recovered_pending"
        log.path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        client = Client([Response("fire"), Response("guard")])
        submitted = []
        def feedback(guess, turn):
            submitted.append((guess, turn))
            return 10
        reason = run_game(client, log, "test", "2026-10-25", max_guesses=3,
                          evaluation=True, resume=True, get_feedback=feedback, show=lambda _: None)
        self.assertEqual(reason, "guess_limit")
        self.assertEqual(submitted, [("fire", 2), ("guard", 3)])
        self.assertEqual(len(client.requests), 2)
        self.assertIn("water -> rank 100", client.requests[0]["input"])
        metrics = game_metrics(read_events(log.path))
        self.assertTrue(metrics["complete"])
        self.assertEqual(metrics["attempts"], 3)

    def test_resume_submits_unscored_saved_answer_without_calling_model_again(self):
        _, _, _, events, log = self.run_trial([Response("water")], [100], 1)
        events[0]["max_guesses"] = 2
        events.insert(-1, {"event": "response", "turn": 2,
                          "raw_response": Response("guard").raw, "timestamp": "saved"})
        events[-1]["reason"] = "recovered_pending"
        log.path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        client = Client([])
        submitted = []
        def feedback(guess, turn):
            submitted.append((guess, turn))
            return 1
        reason = run_game(client, log, "test", "2026-10-25", max_guesses=2,
                          evaluation=True, resume=True, get_feedback=feedback, show=lambda _: None)
        self.assertEqual(reason, "success")
        self.assertEqual(client.requests, [])
        self.assertEqual(submitted, [("guard", 2)])
        metrics = game_metrics(read_events(log.path))
        self.assertEqual(metrics["attempts"], 2)
        self.assertTrue(metrics["complete"])

    def test_recovery_requires_saved_rejection_and_preserves_original_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            game = directory / "2026-10-25"
            game.mkdir()
            manifest = {"puzzle_dates": ["2026-10-25"], "model": "test", "max_guesses": 70,
                        "settings": {}, "source_sha256": {}}
            (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            events = [{"event": "start", "model": "test", "puzzle": "2026-10-25", "max_guesses": 70},
                      {"event": "response", "turn": 1, "raw_response": Response("someone").raw},
                      {"event": "browser_feedback", "turn": 1, "submitted_word": "someone",
                       "observed": {"kind": "error", "message": "This word doesn't count, it's too common"}},
                      {"event": "termination", "reason": "browser_error", "submitted_guesses": 0}]
            # Real event timestamps are required for the readable timeline.
            for event in events:
                event["timestamp"] = "2026-11-04T12:00:00+00:00"
            path = game / "events.jsonl"
            original = "".join(json.dumps(e) + "\n" for e in events)
            path.write_text(original, encoding="utf-8")
            corrected = evaluate_batch.recover_rejection(directory)
            self.assertEqual(corrected[0]["guess"], "someone")
            self.assertTrue(path.read_text(encoding="utf-8").startswith(original))
            self.assertEqual(game_metrics(read_events(path))["status"], "recovered_pending")
            with self.assertRaisesRegex(ValueError, "No recoverable"):
                evaluate_batch.recover_rejection(directory)

    def test_explicit_operational_recovery_does_not_score_service_errors_as_guesses(self):
        for reason in ("api_error", "browser_error"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                game = directory / "2026-10-25"
                game.mkdir()
                manifest = {"puzzle_dates": ["2026-10-25"], "model": "test", "max_guesses": 70,
                            "settings": {}, "source_sha256": {}}
                (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                events = [{"event": "start", "model": "test", "puzzle": "2026-10-25", "max_guesses": 70}]
                if reason == "api_error":
                    events.append({"event": "api_error", "turn": 1, "message": "timeout"})
                else:
                    events.extend([
                        {"event": "response", "turn": 1, "raw_response": Response("water").raw},
                        {"event": "browser_feedback", "turn": 1, "submitted_word": "water",
                         "observed": {"kind": "error", "message": "Oops... there was an error!"}}])
                events.append({"event": "termination", "reason": reason, "submitted_guesses": 0})
                for event in events:
                    event["timestamp"] = "saved"
                path = game / "events.jsonl"
                path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
                evaluate_batch.recover_rejection(directory, operational=True)
                recovered = read_events(path)
                self.assertFalse(any(e["event"] == "feedback" for e in recovered))
                self.assertEqual(game_metrics(recovered)["status"], "recovered_pending")

    def test_progression_uses_last_valid_rank_and_equal_game_weight(self):
        _, _, _, events, _ = self.run_trial(
            [Response("water"), Response("fire"), Response("tree"), Response("guard")],
            [100, "invalid", 50, 8], 4)
        metrics = game_metrics(events, vocabulary_size=1000)
        self.assertAlmostEqual(metrics["mean_progression"], 2 / 3)
        self.assertAlmostEqual(metrics["proximity_unsolved"], 1 - math.log(8) / math.log(1000))
        self.assertAlmostEqual(metrics["weighted_progression"],
                               (math.exp(-math.log(50) / math.log(1000)) +
                                math.exp(-math.log(8) / math.log(1000))) / 3)
        with self.assertRaises(ValueError):
            game_metrics(events, vocabulary_size=90)
        _, _, _, solved_events, _ = self.run_trial([Response("material")], [1], 4)
        total = aggregate([metrics, game_metrics(solved_events)])
        self.assertEqual(total["solve_rate"], 0.5)
        self.assertEqual(total["average_guesses_solved"], 1)

    def test_schedule_frozen_without_paid_calls_and_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prior = root / "runs" / "old"
            prior.mkdir(parents=True)
            (prior / "events.jsonl").write_text(json.dumps({
                "event": "start", "puzzle": "2026-10-25"}) + "\n", encoding="utf-8")
            with patch.object(evaluate_batch, "ROOT", root), \
                    patch.object(evaluate_batch, "source_hashes", return_value={}):
                with self.assertRaisesRegex(ValueError, "overlaps"):
                    evaluate_batch.prepare(date(2026, 10, 25), 1)
                directory = evaluate_batch.prepare(date(2026, 10, 26), 2)
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["puzzle_dates"], ["2026-10-26", "2026-10-27"])
            self.assertEqual(manifest["maximum_model_requests"], 140)
            report = evaluate_batch.summarize(directory)
            self.assertEqual(report["completed"], 0)
            self.assertIsNone(report["solve_rate"])


if __name__ == "__main__":
    unittest.main()
