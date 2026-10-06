"""Offline behavioral checks; no Gemini key or SDK needed."""
import csv
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gemini_trial import GameLog, parse_feedback, parse_guess, run_game
from gemini_trial import create_client


class Response:
    def __init__(self, word, identifier="i1", summary=None, status="completed"):
        self.raw = {"id": identifier, "status": status,
                    "steps": [{"type": "thought", "summary": summary},
                              {"type": "model_output", "content":
                               [{"type": "text", "text": word}]}],
                    "usage": {"total_tokens": 20}}

    def model_dump(self, **kwargs):
        return self.raw


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.interactions = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.requests.append(request)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class TrialTests(unittest.TestCase):
    def game(self, responses, inputs, limit=30, secret="", memory_mode="explicit"):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        log = GameLog(Path(directory.name) / "run", secret)
        client = Client(responses)
        entries = iter(inputs)
        reason = run_game(client, log, "test-model", "123", limit,
                          read=lambda _: next(entries), show=lambda _: None,
                          memory_mode=memory_mode)
        events = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
        with log.csv_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        return reason, client, events, rows

    def test_feedback_and_guess_validation(self):
        self.assertEqual(parse_guess(" Animal\n"), "animal")
        for word in ["", "two words", "animal.", "**animal**", "apple\npear"]:
            with self.assertRaises(ValueError):
                parse_guess(word)
        for entry in ["0", "-1", "1.2", "", "NaN"]:
            with self.assertRaises(ValueError):
                parse_feedback(entry)
        self.assertEqual(parse_feedback(" INVALID "), "invalid")

    def test_stateless_completed_response_does_not_require_id(self):
        reason, client, events, rows = self.game([Response("material", identifier=None)], ["1"])
        self.assertEqual(reason, "success")
        self.assertFalse(client.requests[0]["store"])

    def test_linked_memory_stores_and_chains_latest_interaction(self):
        reason, client, events, rows = self.game(
            [Response("water", "first"), Response("fire", "second"),
             Response("guard", "third")], ["1598", "244", "1"], memory_mode="linked")
        self.assertEqual(reason, "success")
        self.assertNotIn("previous_interaction_id", client.requests[0])
        self.assertEqual(client.requests[1]["previous_interaction_id"], "first")
        self.assertEqual(client.requests[2]["previous_interaction_id"], "second")
        self.assertTrue(all(request["store"] for request in client.requests))
        self.assertIn("water", client.requests[1]["input"])
        self.assertIn("1598", client.requests[1]["input"])
        self.assertIn("fire", client.requests[2]["input"])
        self.assertIn("244", client.requests[2]["input"])
        self.assertNotIn("1598", client.requests[2]["input"])
        start = next(event for event in events if event["event"] == "start")
        self.assertEqual(start["memory_mode"], "linked")
        self.assertTrue(start["interaction_storage"])
        _, other, _, _ = self.game([Response("water", "new-game")], ["quit"], memory_mode="linked")
        self.assertNotIn("previous_interaction_id", other.requests[0])

    def test_linked_memory_requires_id_and_preserves_invalid_feedback(self):
        reason, client, events, rows = self.game(
            [Response("water", identifier=None)], [], memory_mode="linked")
        self.assertEqual(reason, "invalid_model_output")
        self.assertEqual(events[-1]["submitted_guesses"], 0)
        reason, client, events, rows = self.game(
            [Response("water", "first"), Response("fire", "second")],
            ["invalid", "1"], memory_mode="linked")
        self.assertEqual(reason, "success")
        self.assertIn("rejected as invalid", client.requests[1]["input"])

    def test_continuity_success_and_logs(self):
        summary = [{"type": "text", "text": "Try a broad category."}]
        reason, client, events, rows = self.game(
            [Response("animal", summary=summary), Response("cat", "i2")],
            ["bad input", "1250", "1"])
        self.assertEqual(reason, "success")
        self.assertNotIn("previous_interaction_id", client.requests[0])
        self.assertNotIn("previous_interaction_id", client.requests[1])
        self.assertFalse(client.requests[1]["store"])
        self.assertIn("animal", client.requests[1]["input"])
        self.assertIn("1250", client.requests[1]["input"])
        self.assertEqual(client.requests[0]["tools"], [])
        self.assertEqual(rows[0]["thought_summary"], "Try a broad category.")
        self.assertEqual(rows[1]["summary_present"], "False")
        self.assertEqual(rows[1]["rank"], "1")
        kinds = [event["event"] for event in events]
        self.assertLess(kinds.index("response"), kinds.index("feedback"))
        requests = [event for event in events if event["event"] == "request"]
        self.assertEqual(requests[0]["observed_guess_history"], [])
        self.assertEqual(requests[1]["observed_guess_history"],
                         [{"turn": 1, "guess": "animal", "feedback": "rank", "rank": 1250}])

    def test_timeline_updates_and_old_log_export(self):
        with tempfile.TemporaryDirectory() as directory:
            log = GameLog(Path(directory) / "run")
            reads = iter(["1250", "quit"])
            def read(_):
                timeline = (log.path.parent / "timeline.md").read_text(encoding="utf-8")
                self.assertIn("in progress (snapshot)", timeline)
                self.assertIn("No thought summary returned.", timeline)
                return next(reads)
            run_game(Client([Response("animal"), Response("cat", "second")]),
                     log, "test", "1", read=read, show=lambda _: None)
            # Existing logs do not have per-request snapshots; reconstruct them.
            events = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
            for event in events:
                event.pop("observed_guess_history", None)
            log.path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
            log.export()
            timeline = (log.path.parent / "timeline.md").read_text(encoding="utf-8")
            self.assertIn("Status: quit", timeline)
            self.assertIn("Turn 1: animal — rank 1250", timeline)
            self.assertIn("explicitly supplied local history", timeline)

    def test_complete_history_is_supplied_and_games_are_isolated(self):
        summary = [{"type": "text", "text": "PRIVATE_SUMMARY_FOR_LOCAL_INSPECTION"}]
        reason, client, events, rows = self.game(
            [Response("animal", summary=summary), Response("tree", "i2"),
             Response("water", "i3")], ["1250", "invalid", "1"])
        third = client.requests[2]["input"]
        self.assertIn("Turn 1: animal -> rank 1250", third)
        self.assertIn("Turn 2: tree -> rejected as invalid by Contexto", third)
        self.assertLess(third.index("Turn 1:"), third.index("Turn 2:"))
        for request in client.requests:
            self.assertNotIn("previous_interaction_id", request)
            self.assertFalse(request["store"])
            self.assertIn("Play a semantic hidden-word guessing game", request["input"])
            self.assertNotIn("PRIVATE_SUMMARY_FOR_LOCAL_INSPECTION", request["input"])
        _, new_client, _, _ = self.game([Response("food")], ["quit"])
        self.assertIn("No guesses submitted yet.", new_client.requests[0]["input"])
        self.assertNotIn("1250", new_client.requests[0]["input"])

    def test_invalid_counts_toward_limit(self):
        reason, client, events, rows = self.game(
            [Response("animal"), Response("tree", "i2")], ["invalid", "25"], limit=2)
        self.assertEqual(reason, "guess_limit")
        self.assertIn("rejected as invalid", client.requests[1]["input"])
        self.assertEqual(events[-1]["submitted_guesses"], 2)
        self.assertEqual(rows[0]["feedback"], "invalid")

    def test_malformed_repeated_and_incomplete_stop(self):
        for response in [Response("two words"), Response("apple", status="incomplete")]:
            reason, client, events, rows = self.game([response], [])
            self.assertEqual(reason, "invalid_model_output")
            self.assertEqual(events[-1]["submitted_guesses"], 0)
            self.assertEqual(len(rows), 1)
        reason, client, events, rows = self.game(
            [Response("apple"), Response("APPLE", "i2")], ["300"])
        self.assertEqual(reason, "invalid_model_output")
        self.assertEqual(events[-1]["submitted_guesses"], 1)

    def test_quit_keeps_unsubmitted_response(self):
        reason, client, events, rows = self.game([Response("animal")], ["quit"])
        self.assertEqual(reason, "quit")
        self.assertEqual(events[-1]["submitted_guesses"], 0)
        self.assertEqual(rows[0]["guess"], "animal")

    def test_api_error_no_retry_and_secret_redacted(self):
        reason, client, events, rows = self.game(
            [Response("animal"), RuntimeError("secret-key request failed")],
            ["30"], secret="secret-key")
        self.assertEqual(reason, "api_error")
        self.assertEqual(len(client.requests), 2)
        self.assertNotIn("secret-key", json.dumps(events))
        self.assertIn("[REDACTED]", json.dumps(events))
        self.assertEqual(rows[0]["termination_reason"], "api_error")

    def test_interruption_preserves_response(self):
        with tempfile.TemporaryDirectory() as directory:
            log = GameLog(Path(directory) / "run")
            def interrupted(_):
                raise KeyboardInterrupt()
            reason = run_game(Client([Response("animal")]), log, "test", "1",
                              read=interrupted, show=lambda _: None)
            self.assertEqual(reason, "interrupted")
            self.assertIn("animal", log.csv_path.read_text(encoding="utf-8"))
            log.export()

    def test_real_sdk_request_and_no_transport_retries(self):
        try:
            import httpx
            from google import genai
        except ImportError:
            self.skipTest("Install the Conda environment to check the real SDK transport")
        calls = []
        def respond(request, **kwargs):
            calls.append(json.loads(request.content))
            return httpx.Response(503, request=request,
                                  json={"error": {"code": 503, "message": "Unavailable"}})
        with patch("httpx.Client.send", side_effect=respond):
            client = create_client("offline-dummy-key")
            self.addCleanup(client.close)
            with tempfile.TemporaryDirectory() as directory:
                reason = run_game(client, GameLog(Path(directory) / "run"),
                                  "gemini-3.8-flash", "123", show=lambda _: None)
        self.assertEqual(reason, "api_error")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["generation_config"]["thinking_summaries"], "auto")
        self.assertEqual(calls[0]["generation_config"]["max_output_tokens"], 4096)
        self.assertNotIn("previous_interaction_id", calls[0])
        self.assertFalse(calls[0]["store"])

    def test_real_sdk_successful_response_parsing(self):
        try:
            import httpx
            from google import genai
        except ImportError:
            self.skipTest("Install the Conda environment to check the real SDK transport")
        calls = []
        responses = iter([Response("animal", "first").raw, Response("cat", "second").raw])
        def respond(request, **kwargs):
            calls.append(json.loads(request.content))
            return httpx.Response(200, request=request, json=next(responses))
        with patch("httpx.Client.send", side_effect=respond):
            client = create_client("offline-dummy-key")
            self.addCleanup(client.close)
            with tempfile.TemporaryDirectory() as directory:
                inputs = iter(["1250", "1"])
                reason = run_game(client, GameLog(Path(directory) / "run"),
                                  "gemini-3.8-flash", "123", read=lambda _: next(inputs),
                                  show=lambda _: None)
        self.assertEqual(reason, "success")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("previous_interaction_id", calls[1])
        self.assertFalse(calls[1]["store"])
        self.assertIn("1250", calls[1]["input"])


if __name__ == "__main__":
    unittest.main()
