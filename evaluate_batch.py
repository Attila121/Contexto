"""Freeze, execute and summarize a paper-inspired Contexto evaluation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo

from automated_game import ContextoBrowser, ROOT, classify_feedback, parse_date
from evaluation_metrics import aggregate, game_metrics, read_events
from gemini_trial import (DEFAULT_MAX_GUESSES, DEFAULT_MODEL, INSTRUCTIONS, SETTINGS,
                          GameLog, create_client, now, read_api_key, run_game)

SOURCES = ("gemini_trial.py", "automated_game.py", "evaluate_batch.py", "evaluation_metrics.py")


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def prepare(start_date, games=10, model=DEFAULT_MODEL, max_guesses=DEFAULT_MAX_GUESSES,
            output_root=None):
    if games < 1 or max_guesses < 1:
        raise ValueError("Game count and guess limit must be positive.")
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(games)]
    today = datetime.now(ZoneInfo("Europe/Budapest")).date()
    if date.fromisoformat(dates[-1]) >= today:
        raise ValueError("Use completed daily puzzles strictly before today in Budapest.")
    previously_played = set()
    # Include ignored historical logs; a filesystem scan is intentional.
    for path in (ROOT / "runs").glob("**/events.jsonl"):
        for event in read_events(path):
            if event["event"] == "start":
                try:
                    previously_played.add(parse_date(event["puzzle"]).isoformat())
                except (ValueError, KeyError):
                    pass
    if previously_played.intersection(dates):
        raise ValueError("Fresh-puzzle selection overlaps previously started games: "
                         + ", ".join(sorted(previously_played.intersection(dates))))
    directory = (output_root or ROOT / "runs") / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_evaluation_" + uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": 1, "prepared_at": now(), "model": model, "max_guesses": max_guesses,
        "puzzle_dates": dates, "selection": "consecutive dates fixed before any study guesses",
        "freshness": "no matching puzzle date in prior local start events",
        "maximum_model_requests": games * max_guesses,
        "environment": "live Contexto English website; not the paper's GloVe WordPolo",
        "memory": "explicit", "history_order": "newest_first", "instructions": INSTRUCTIONS,
        "settings": SETTINGS, "condition": "no_initial_plan", "external_tools_for_model": [],
        "output_parser": "final whitespace token, ASCII letters only; no punctuation stripping",
        "invalid_policy": "consume attempt for malformed, incomplete, repeated or OOV outputs",
        "operational_errors": "stop batch on API/browser error; no automatic retries",
        "vocabulary_size": None,
        "metric_convention": "exclude first attempt from progression; invalid transitions zero; "
                             "next valid compares to last valid; average per game then across games",
        "paper": "https://arxiv.org/pdf/2609.19006",
        "deviations": ["live Contexto scoring and 10 new dates, not the paper's target set",
                       f"{max_guesses} attempts instead of 100", "Gemini instead of GPT-4.1",
                       "our existing no-plan instructions plus explicit attempt budget",
                       "proximity and weighted progression unavailable without verified vocabulary size"],
        "source_sha256": source_hashes(),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summarize(directory)
    return directory


def summarize(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    games = []
    for puzzle in manifest["puzzle_dates"]:
        path = directory / puzzle / "events.jsonl"
        if path.exists():
            metrics = game_metrics(read_events(path))
            metrics["puzzle"] = puzzle
            games.append(metrics)
    totals = aggregate(games)
    result = {"planned": len(manifest["puzzle_dates"]), **totals, "games": games}
    (directory / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if games:
        with (directory / "results.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(games[0]))
            writer.writeheader()
            writer.writerows(games)
    fmt = lambda value: "not available" if value is None else f"{value:.3f}"
    lines = [f"# Contexto {manifest['max_guesses']}-attempt evaluation", "",
             f"Model: **{manifest['model']}**. Limit: **{manifest['max_guesses']} attempts** per game.",
             f"Completed: **{totals['completed']}/{result['planned']}**. Solved: **{totals['solved']}**.",
             "", "Fresh games, explicit full history newest first, no initial plan or model tools.",
             "Invalid/repeated outputs consume attempts. API/browser errors are reported separately.",
             "", f"Solve rate among completed games: {fmt(totals['solve_rate'])}.",
             f"Average attempts on solved games: {fmt(totals['average_guesses_solved'])}.",
             f"Mean progression across completed games: {fmt(totals['mean_progression'])}.", "",
             "Incomplete games are excluded from these averages; the completed/planned count must "
             "always accompany any partial result.", "",
             "| Puzzle | Status | Attempts | Best word | Best rank | At attempt | Mean progression |",
             "| --- | --- | ---: | --- | ---: | ---: | ---: |"]
    by_puzzle = {g["puzzle"]: g for g in games}
    for puzzle in manifest["puzzle_dates"]:
        g = by_puzzle.get(puzzle)
        if not g:
            lines.append(f"| {puzzle} | scheduled | — | — | — | — | — |")
        else:
            lines.append(f"| [{puzzle}]({puzzle}/timeline.md) | {g['status']} | {g['attempts']} | "
                         f"{g['best_word'] or '—'} | {g['best_rank'] or '—'} | "
                         f"{g['best_rank_turn'] or '—'} | {fmt(g['mean_progression'])} |")
    lines.extend(["", "## Comparison with the paper", "",
                  "GPT-4.1: 35% solved over 1,500 puzzles, 49.9 guesses on solved puzzles, "
                  "mean progression 0.462. On its 50-puzzle subset: 42%, 42.8 guesses, 0.466.",
                  "[Source: WordPolo, Table 1](https://arxiv.org/pdf/2609.19006).", "",
                  "This is a paper-inspired Contexto pilot, not a matched replication. "
                  "Different scoring, targets, prompt, model and attempt budget prevent a direct "
                  "performance ranking against the paper. No human data are collected here.", "",
                  "Normalized proximity and weighted progression are omitted: live Contexto's "
                  "vocabulary size has not been verified. The paper's 317,756 must not be "
                  "substituted for the website's vocabulary size.", "",
                  "Progression is the fraction of attempts after the first whose rank improves "
                  "over the preceding valid rank. Invalid attempts score zero. Each game is "
                  "averaged first; the report then averages completed games equally.", "",
                  "The frozen configuration and source hashes are in [manifest.json](manifest.json). "
                  "Per-game logs retain raw responses, prompts, feedback and browser evidence.", ""])
    amendments = directory / "execution_amendments.json"
    if amendments.exists():
        lines.extend(["## Execution corrections", "",
                      "See [execution_amendments.json](execution_amendments.json) for preserved "
                      "source hashes and correction reasons. A website rejection initially "
                      "classified as an operational error may be reclassified from saved evidence; "
                      "its model response is not regenerated. A corrected game resumes with its "
                      "full saved history and original total attempt budget.", ""])
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def recover_rejection(directory, operational=False):
    """Explicit controller repair using saved website evidence; no network or model calls."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    corrected = []
    for puzzle in manifest["puzzle_dates"]:
        path = directory / puzzle / "events.jsonl"
        if not path.exists():
            continue
        events = read_events(path)
        end = next((e for e in reversed(events) if e["event"] == "termination"), {})
        if end.get("reason") not in ({"browser_error", "api_error"} if operational else {"browser_error"}):
            continue
        api_error = next((e for e in reversed(events) if e["event"] == "api_error"), None)
        retry_api = end["reason"] == "api_error"
        response = next((e for e in reversed(events) if e["event"] == "response"), None)
        if response is None and not retry_api:
            raise ValueError("No saved model answer exists for browser recovery.")
        turn = api_error["turn"] if retry_api else response["turn"]
        if any(e["event"] == "feedback" and e["turn"] == turn for e in events):
            continue
        observed = next((e for e in reversed(events) if e["event"] == "browser_feedback"
                         and e["turn"] == turn), None)
        submission = next((e for e in reversed(events) if e["event"] == "browser_submit"
                           and e["turn"] == turn), None)
        rejected = False
        if observed:
            try:
                rejected = classify_feedback(observed["observed"]) == "invalid"
            except RuntimeError:
                if not operational:
                    raise
        if observed and not rejected and not operational:
            raise ValueError("Saved feedback is not an ordinary invalid-word rejection.")
        if not observed and not submission and not retry_api:
            raise ValueError("Saved evidence does not establish a pending browser submission.")
        log = object.__new__(GameLog)
        log.path, log.csv_path, log.secret = path, path.parent / "turns.csv", ""
        action = ("retry explicitly after API transport error; no response was received" if retry_api else
                  "verified website rejection is an invalid guess" if rejected else
                  "resubmit saved model answer to obtain missing browser feedback")
        log.write("controller_recovery", turn=turn, reason=action,
                  original_termination=end, website_evidence=observed or submission,
                  api_error=api_error if retry_api else None, model_requests_repeated=int(retry_api))
        if rejected:
            log.write("feedback", turn=turn, guess=observed["submitted_word"], feedback="invalid", rank=None)
        log.write("termination", reason="recovered_pending", success=False,
                  submitted_guesses=end["submitted_guesses"] + int(rejected),
                  attempts_used=sum(e["event"] == "response" for e in events))
        log.export()
        corrected.append({"puzzle": puzzle, "turn": turn,
                          "guess": observed["submitted_word"] if observed else submission["guess"] if submission else None,
                          "action": action})
    if not corrected:
        raise ValueError("No recoverable saved website rejection found.")
    amendment_path = directory / "execution_amendments.json"
    amendments = json.loads(amendment_path.read_text(encoding="utf-8")) if amendment_path.exists() else []
    amendments.append({"timestamp": now(), "reason": "classify ordinary word rejections as invalid; "
                       "clear transient error panels; resume missing feedback without new model calls; "
                       "isolate concurrent games; explicitly recover operational errors under original request cap",
                       "previous_source_sha256": (amendments[-1]["source_sha256"] if amendments
                                                  else manifest["source_sha256"]),
                       "source_sha256": source_hashes(), "corrected": corrected,
                       "unchanged": ["dates", "model", "settings", "prompt", "70-attempt total budget"]})
    amendment_path.write_text(json.dumps(amendments, indent=2) + "\n", encoding="utf-8")
    summarize(directory)
    return corrected


def execute_game(directory, manifest, puzzle, key):
    """Each worker owns its SDK client, Playwright instance and fresh browser context."""
    game_dir = directory / puzzle
    resume = game_dir.exists()
    if resume:
        events = read_events(game_dir / "events.jsonl")
        if game_metrics(events)["status"] != "recovered_pending":
            raise ValueError(f"Unfinished game at {game_dir}; no automatic retry.")
        log = object.__new__(GameLog)
        log.path, log.csv_path, log.secret = game_dir / "events.jsonl", game_dir / "turns.csv", key
    else:
        log = GameLog(game_dir, key)
        log.write("batch_game", puzzle_date=puzzle, manifest="../manifest.json")
    from playwright.sync_api import sync_playwright
    client = create_client(key)
    reason = "browser_setup_error"
    started = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
                try:
                    adapter = ContextoBrowser(
                        context.new_page(), log, evaluation=True,
                        artifact_subdir="browser_resume_" + uuid4().hex[:8] if resume else "browser")
                    adapter.open_game(date.fromisoformat(puzzle))
                    if resume:
                        for entry in events:
                            if entry["event"] == "feedback" and entry["feedback"] in {"rank", "invalid"}:
                                actual = adapter.submit(entry["guess"], entry["turn"])
                                expected = entry["rank"] if entry["feedback"] == "rank" else "invalid"
                                if actual != expected:
                                    raise ValueError(f"Website replay changed feedback at turn {entry['turn']}")
                        log.write("browser_replay_verified", model_requests=0)
                    started = True
                    reason = run_game(
                        client, log, manifest["model"], puzzle, manifest["max_guesses"],
                        get_feedback=adapter.submit, memory_mode="explicit", evaluation=True, resume=resume,
                        show=lambda message: print(f"[{puzzle}] {message}", flush=True))
                    adapter.snapshot("final")
                finally:
                    context.close()
            finally:
                browser.close()
    except (Exception, KeyboardInterrupt) as error:
        log.write("browser_error", message=str(error).replace(key, "[REDACTED]"))
        reason = "interrupted" if isinstance(error, KeyboardInterrupt) else "browser_setup_error"
        if not started:
            log.write("termination", reason=reason, submitted_guesses=0, success=False)
        log.export()
        print(f"[{puzzle}] stopped: {reason}", flush=True)
    finally:
        client.close()
    return reason


def execute(directory, workers=3):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    amendments_path = directory / "execution_amendments.json"
    amendments = json.loads(amendments_path.read_text(encoding="utf-8")) if amendments_path.exists() else []
    expected_hashes = amendments[-1]["source_sha256"] if amendments else manifest["source_sha256"]
    if expected_hashes != source_hashes() or manifest["settings"] != SETTINGS:
        raise ValueError("Study sources/settings changed after preparation; prepare a new batch.")
    key = read_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is missing; no model requests were made.")
    if not 1 <= workers <= 3:
        raise ValueError("Use between one and three independent workers.")
    pending = []
    requests_used = 0
    remaining_capacity = 0
    for puzzle in manifest["puzzle_dates"]:
        path = directory / puzzle / "events.jsonl"
        if path.exists():
            events = read_events(path)
            requests_used += sum(e["event"] == "request" for e in events)
            metrics = game_metrics(events)
            if metrics["complete"]:
                continue
            if metrics["status"] != "recovered_pending":
                raise ValueError(f"Unfinished game at {path.parent}; not retried automatically.")
            remaining_capacity += manifest["max_guesses"] - metrics["attempts"]
        else:
            remaining_capacity += manifest["max_guesses"]
        pending.append(puzzle)
    if requests_used + remaining_capacity > manifest["maximum_model_requests"]:
        raise ValueError("Continuing could exceed the original total model-request cap.")
    execution = {"timestamp": now(), "workers": workers, "pending_dates": pending,
                 "source_sha256": source_hashes()}
    with (directory / "executions.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(execution) + "\n")
    failed = False
    try:
        # Schedule only one game per worker initially; stop launching new games on error.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            active = {}
            remaining = iter(pending)
            for _ in range(workers):
                puzzle = next(remaining, None)
                if puzzle:
                    print(f"Starting {puzzle}", flush=True)
                    active[pool.submit(execute_game, directory, manifest, puzzle, key)] = puzzle
            while active:
                future = next(as_completed(active))
                puzzle = active.pop(future)
                reason = future.result()
                print(f"Finished {puzzle}: {reason}", flush=True)
                summarize(directory)
                failed = failed or reason not in {"success", "guess_limit"}
                following = next(remaining, None) if not failed else None
                if following:
                    print(f"Starting {following}", flush=True)
                    active[pool.submit(execute_game, directory, manifest, following, key)] = following
    finally:
        summarize(directory)
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Freeze the schedule; no browser or paid calls")
    prep.add_argument("--start-date", required=True, type=parse_date)
    prep.add_argument("--games", type=int, default=10)
    prep.add_argument("--max-guesses", type=int, default=DEFAULT_MAX_GUESSES)
    prep.add_argument("--model", default=DEFAULT_MODEL)
    for name in ("run", "summarize", "recover-rejection", "recover-operational"):
        command = commands.add_parser(name)
        command.add_argument("batch", type=Path)
        if name == "run":
            command.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.start_date, args.games, args.model, args.max_guesses))
            return 0
        if args.command == "summarize":
            print(json.dumps(summarize(args.batch), indent=2))
            return 0
        if args.command in {"recover-rejection", "recover-operational"}:
            print(json.dumps(recover_rejection(args.batch, operational=args.command == "recover-operational"), indent=2))
            return 0
        return execute(args.batch, args.workers)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    sys.exit(main())
