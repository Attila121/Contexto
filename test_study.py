"""Offline study checks: write-ahead budgets, isolation, recovery and paired analysis."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation_metrics import game_metrics, read_events
from gemini_trial import GameLog, INSTRUCTIONS, build_prompt, run_game
from test_gemini_trial import Client, Response
import study_batch as study
from study_analysis import trajectory, paired_analysis


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def prepare(self):
        return study.prepare(self.root / "study")

    def test_schedule_has_exactly_150_unique_balanced_games(self):
        games = study.schedule()
        self.assertEqual(len(games), 150)
        self.assertEqual(len({g["id"] for g in games}), 150)
        self.assertEqual(len({g["date"] for g in games}), 25)
        self.assertEqual(min(g["date"] for g in games), "2026-10-26")
        self.assertEqual(max(g["date"] for g in games), "2026-11-19")
        self.assertEqual(games, study.schedule())
        first = [g["condition"] for g in games[::2]]
        self.assertEqual(first.count("control"), 38)
        for index in range(0, len(games), 6):
            block = games[index:index + 6]
            self.assertEqual(len({g["date"] for g in block}), 1)
            self.assertEqual({(g["condition"], g["repetition"]) for g in block},
                             {(c, r) for c in study.CONDITIONS for r in (1, 2, 3)})
            self.assertNotEqual(block[0]["condition"], block[2]["condition"])
            self.assertEqual(block[0]["condition"], block[4]["condition"])

    def test_prepare_is_offline_and_freezes_protocol(self):
        with patch.object(study, "create_client", side_effect=AssertionError("network")):
            directory = self.prepare()
        manifest = study.load_manifest(directory)
        self.assertEqual(manifest["max_guesses"], 30)
        self.assertEqual(len(manifest["pilot_games"]), 4)
        self.assertEqual(manifest["maximum_requests"], 4824)
        self.assertTrue((directory / "human_targets.csv").exists())
        self.assertNotEqual(manifest["instructions"]["control"], manifest["instructions"]["guided"])
        manifest["max_guesses"] = 70
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest"):
            study.load_manifest(directory)

    def test_process_lock_is_exclusive_and_released(self):
        with study.BatchLock(self.root):
            with self.assertRaises((OSError, ValueError)):
                with study.BatchLock(self.root):
                    self.fail("second runner acquired lock")
        with study.BatchLock(self.root):
            pass

    def test_source_amendment_requires_archives_and_unchanged_manifest(self):
        import hashlib
        import shutil
        directory = self.prepare()
        manifest = study.load_manifest(directory)
        original = directory / "source_original"
        revised = directory / "source_revision_01"
        original.mkdir()
        revised.mkdir()
        for name in manifest["source_sha256"]:
            shutil.copy2(study.ROOT / name, original / name)
            shutil.copy2(study.ROOT / name, revised / name)
        changed = revised / "automated_game.py"
        changed.write_bytes(changed.read_bytes() + b"\n# Mechanical reader repair fixture.\n")
        hashes = {name: hashlib.sha256((revised / name).read_bytes()).hexdigest()
                  for name in manifest["source_sha256"]}
        amendment = {"timestamp": "2026-11-21T00:05:00+00:00", "reason": "Mechanical browser repair",
                     "manifest_fingerprint": manifest["fingerprint"],
                     "previous_source_sha256": manifest["source_sha256"], "source_sha256": hashes,
                     "previous_archive": "source_original", "source_archive": "source_revision_01"}
        with patch.object(study, "source_hashes", return_value=hashes):
            with self.assertRaises(ValueError):
                study.load_manifest(directory)
            study.write_json(directory / "source_amendments.json", [amendment])
            self.assertEqual(study.load_manifest(directory), manifest)
            amendment["manifest_fingerprint"] = "changed-protocol"
            study.write_json(directory / "source_amendments.json", [amendment])
            with self.assertRaises(ValueError):
                study.load_manifest(directory)
        amendment["manifest_fingerprint"] = manifest["fingerprint"]
        study.write_json(directory / "source_amendments.json", [amendment])
        changed.write_text("unrecorded change", encoding="utf-8")
        with patch.object(study, "source_hashes", return_value=hashes):
            with self.assertRaises(ValueError):
                study.load_manifest(directory)

    def test_concurrent_ledger_never_exceeds_cap(self):
        ledger = study.RequestLedger(self.root, limits={"production_guess": 7}, retry_limit=0)
        def reserve(index):
            try:
                return ledger.reserve(str(index), "production_guess", 1, {})
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            accepted = [x for x in pool.map(reserve, range(40)) if x is not None]
        self.assertEqual(len(accepted), 7)
        reopened = study.RequestLedger(self.root, limits={"production_guess": 7}, retry_limit=0)
        self.assertEqual(len(reopened.reservations), 7)
        with self.assertRaises(ValueError):
            reopened.reserve("new", "production_guess", 1, {})

    def test_retries_use_reserve_and_returned_answers_cannot_be_regenerated(self):
        ledger = study.RequestLedger(self.root, limits={"production_guess": 1}, retry_limit=1)
        reservation = ledger.reserve("game", "production_guess", 1, {})
        ledger.finish(reservation, error="timeout")
        retry = ledger.reserve("game", "production_guess", 1, {})
        ledger.finish(retry, raw=Response("water").raw)
        with self.assertRaises(ValueError):
            ledger.reserve("game", "production_guess", 1, {})
        with self.assertRaises(ValueError):
            ledger.reserve("other", "production_guess", 1, {})
        self.assertEqual(ledger.retry_count, 1)

    def test_unknown_outcome_is_accounted_and_corrupt_journal_is_rejected(self):
        ledger = study.RequestLedger(self.root, limits={"production_guess": 1}, retry_limit=0)
        ledger.reserve("game", "production_guess", 1, {})
        reopened = study.RequestLedger(self.root, limits={"production_guess": 1}, retry_limit=0)
        with self.assertRaises(ValueError):
            reopened.reserve("game", "production_guess", 1, {})
        with (self.root / "requests.jsonl").open("a", encoding="utf-8") as stream:
            stream.write('{"event":')
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            study.RequestLedger(self.root)

    def test_condition_prompts_do_not_change_legacy_defaults(self):
        self.assertTrue(build_prompt([]).startswith(INSTRUCTIONS))
        control = study.instructions("control")
        guided = study.instructions("guided")
        self.assertEqual(guided, control + " " + study.GUIDANCE)
        self.assertNotIn(study.GUIDANCE, build_prompt([], evaluation=True, instructions=control))
        self.assertIn(study.GUIDANCE, build_prompt([], evaluation=True, instructions=guided))

    def test_study_game_records_condition_and_consumes_30_outputs(self):
        log = GameLog(self.root / "game")
        client = Client([Response("water") for _ in range(30)])
        reason = run_game(client, log, "test", "2026-11-01", 30, evaluation=True,
                          instructions=study.instructions("guided"), condition="guided",
                          get_feedback=lambda *_: 100, show=lambda _: None)
        events = read_events(log.path)
        self.assertEqual(reason, "guess_limit")
        self.assertEqual(game_metrics(events)["attempts"], 30)
        self.assertEqual(events[0]["condition"], "guided")
        self.assertTrue(all(study.GUIDANCE in r["input"] for r in client.requests))
        self.assertTrue(all(not r["store"] and "previous_interaction_id" not in r
                            for r in client.requests))
        self.assertIn("at most 30 attempts", client.requests[0]["input"])
        with self.assertRaisesRegex(ValueError, "configuration"):
            run_game(Client([]), log, "test", "2026-11-01", 30, evaluation=True, resume=True,
                     instructions=study.instructions("control"), condition="control")

    def test_report_is_separate_from_attempts_and_idempotent(self):
        directory = self.prepare()
        manifest = study.load_manifest(directory)
        game = manifest["games"][0]
        game_dir = study.game_directory(directory, game)
        log = GameLog(game_dir)
        run_game(Client([Response("water")]), log, manifest["model"], game["date"], 30,
                 evaluation=True, instructions=manifest["instructions"][game["condition"]],
                 condition=game["condition"], get_feedback=lambda *_: 1, show=lambda _: None)
        before = log.path.read_bytes()
        client = Client([Response("I explored categories, then narrowed my search.")])
        ledger = study.RequestLedger(directory)
        study.strategy_report(directory, manifest, game, client, ledger)
        study.strategy_report(directory, manifest, game, client, ledger)
        self.assertEqual(log.path.read_bytes(), before)
        self.assertEqual(len(client.requests), 1)
        self.assertFalse(client.requests[0]["store"])
        self.assertIn("water", client.requests[0]["input"])
        self.assertEqual(game_metrics(read_events(log.path))["attempts"], 1)
        self.assertTrue(study.report_complete(game_dir))

    def test_recovery_restores_returned_response_without_regenerating(self):
        directory = self.prepare()
        manifest = study.load_manifest(directory)
        game = manifest["games"][0]
        log = GameLog(study.game_directory(directory, game))
        log.write("start", puzzle=game["date"], model=manifest["model"], max_guesses=30,
                  instructions=manifest["instructions"][game["condition"]], condition=game["condition"],
                  generation_config=manifest["settings"], evaluation=True)
        request = {"input": "saved"}
        log.write("request", turn=1, request=request)
        ledger = study.RequestLedger(directory)
        reservation = ledger.reserve(game["id"], "production_guess", 1, request)
        ledger.finish(reservation, raw=Response("water").raw)
        study.recover(directory, game["id"])
        events = read_events(log.path)
        self.assertEqual(len([e for e in events if e["event"] == "response"]), 1)
        self.assertEqual(events[-1]["reason"], "recovered_pending")
        self.assertEqual(len(study.RequestLedger(directory).reservations), 1)

    def test_scheduler_stops_after_failed_group_and_waits_for_active_groups(self):
        launched = []
        def worker(group):
            launched.append(group)
            return False
        self.assertFalse(study.dispatch(list(range(10)), worker, workers=1))
        self.assertEqual(launched, [0])

    def test_active_group_does_not_start_next_game_after_peer_failure(self):
        import threading
        directory = self.prepare()
        manifest = study.load_manifest(directory)
        group = manifest["games"][:6]
        stopped = threading.Event()
        def finish_active(*args):
            stopped.set()
            return True
        with patch.object(study, "sentinel_probe", return_value={"water": 10}), \
             patch.object(study, "execute_game", side_effect=finish_active) as execute, \
             patch("builtins.print"):
            self.assertFalse(study.execute_group(directory, manifest, group,
                                                study.RequestLedger(directory), "key", stopped))
        self.assertEqual(execute.call_count, 1)

    def test_preflight_refuses_unavailable_model_without_interactions(self):
        directory = self.prepare()
        client = Client([])
        from types import SimpleNamespace
        client.models = SimpleNamespace(get=lambda **_: (_ for _ in ()).throw(ValueError("not found")))
        with self.assertRaises(ValueError):
            study.preflight(directory, study.load_manifest(directory), client)
        self.assertFalse(client.requests)

    def test_end_to_end_pilot_and_production_are_auditable_and_idempotent(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        clients = []
        def client_factory(_):
            client = Client([Response("water", identifier=None),
                             Response("I explored categories before narrowing my guesses.", identifier=None)])
            client.close = lambda: None
            client.models = SimpleNamespace(get=lambda **_: Response("model", identifier=None))
            clients.append(client)
            return client
        class BrowserAdapter:
            def __init__(self, page, log, **kwargs):
                self.log = log
            def open_game(self, target):
                self.log.write("browser_ready", requested_date=target.isoformat(), fresh_game=True)
            def submit(self, word, turn):
                self.log.write("browser_submit", turn=turn, guess=word)
                self.log.write("browser_feedback", turn=turn, submitted_word=word,
                               observed={"kind": "rank", "word": word, "rank": 1, "repeated": False})
                return 1
            def snapshot(self, name):
                pass
        context = SimpleNamespace(new_page=lambda: None, close=lambda: None)
        browser = SimpleNamespace(new_context=lambda **_: context, close=lambda: None)
        playwright = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **_: browser))
        directory = self.prepare()
        with patch.object(study, "read_api_key", return_value="test-secret"), \
             patch.object(study, "create_client", side_effect=client_factory), \
             patch.object(study, "ContextoBrowser", BrowserAdapter), \
             patch.object(study, "sentinel_probe", return_value={"water": 1, "person": 20, "object": 30}), \
             patch("playwright.sync_api.sync_playwright", side_effect=lambda: nullcontext(playwright)), \
             patch("builtins.print"):
            with self.assertRaisesRegex(ValueError, "pilot"):
                study.execute(directory, workers=3)
            self.assertEqual(study.execute(directory, "pilot", workers=2), 0)
            self.assertTrue(study.audit(directory, "pilot")["passed"])
            self.assertEqual(study.execute(directory, workers=3), 0)
            self.assertTrue(study.audit(directory)["passed"])
            total = len(study.RequestLedger(directory).reservations)
            self.assertEqual(total, 308)  # 154 one-guess games and 154 reports.
            self.assertEqual(study.execute(directory, workers=3), 0)
            self.assertEqual(len(study.RequestLedger(directory).reservations), total)
        result = json.loads((directory / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(result["completed"], 150)
        self.assertEqual(result["paired"]["targets"], 25)
        self.assertEqual(result["paired"]["score"], .5)
        # A changed prompt must invalidate the audit even if outcomes still look plausible.
        manifest = study.load_manifest(directory)
        path = study.game_directory(directory, manifest["games"][0]) / "events.jsonl"
        events = read_events(path)
        next(e for e in events if e["event"] == "request")["request"]["input"] = "contaminated"
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        self.assertFalse(study.audit(directory)["passed"])

    def test_ledger_redacts_secrets_in_errors_and_raw_responses(self):
        ledger = study.RequestLedger(self.root, secret="private-key")
        reservation = ledger.reserve("game", "production_guess", 1, {"input": "private-key"})
        ledger.finish(reservation, error="failure private-key")
        self.assertNotIn("private-key", ledger.path.read_text(encoding="utf-8"))

    def test_unreadable_credentials_stop_cleanly_without_second_traceback(self):
        directory = self.prepare()
        with patch.object(study, "read_api_key", side_effect=PermissionError("credential file inaccessible")), \
             patch("sys.argv", ["study_batch.py", "pilot", str(directory)]), \
             patch("builtins.print") as output:
            self.assertEqual(study.main(), 1)
        self.assertIn("credential file inaccessible", output.call_args.args[0])


def fixture(ranks, solved=False):
    events = [{"event": "start", "max_guesses": len(ranks)}]
    for turn, rank in enumerate(ranks, 1):
        events.extend([{"event": "response", "turn": turn},
                       {"event": "feedback", "turn": turn, "guess": "word",
                        "feedback": "rank" if rank is not None else "invalid", "rank": rank}])
    events.append({"event": "termination", "reason": "success" if solved else "guess_limit"})
    return events


class AnalysisTests(unittest.TestCase):
    def test_trajectory_carries_invalid_and_success_forward(self):
        self.assertEqual(trajectory(fixture([None, 100, None, 20]), 5), [None, 100, 100, 20, 20])
        self.assertEqual(trajectory(fixture([50, 1], True), 5), [50, 1, 1, 1, 1])

    def test_paired_score_uses_all_nine_combinations_and_whole_targets(self):
        groups = {"a": {"control": [[100] * 30] * 3, "guided": [[10] * 30] * 3},
                  "b": {"control": [[10] * 30] * 3, "guided": [[100] * 30] * 3}}
        result = paired_analysis(groups)
        self.assertEqual(result["targets"], 2)
        self.assertEqual(result["score"], .5)
        self.assertEqual(result["target_scores"], {"a": 1.0, "b": 0.0})
        self.assertEqual(result, paired_analysis(groups))
        groups["b"]["guided"].pop()
        self.assertEqual(paired_analysis(groups)["targets"], 1)

    def test_ties_and_missing_ranks_are_ordinal(self):
        groups = {"a": {c: [[None, 100] for _ in range(3)] for c in study.CONDITIONS}}
        self.assertEqual(paired_analysis(groups)["score"], .5)


if __name__ == "__main__":
    unittest.main()
