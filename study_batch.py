"""Prepare, pilot, collect and audit the fixed 150-game Contexto instruction study."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import threading
from types import SimpleNamespace
from uuid import uuid4

from automated_game import ContextoBrowser, ROOT, classify_feedback, parse_date
from evaluation_metrics import game_metrics, read_events
from gemini_trial import (DEFAULT_MODEL, SETTINGS, GameLog, build_prompt, create_client,
                          feedback_text, now, read_api_key, run_game, unpack_response)
from gemini_trial import parse_guess
from study_analysis import SEED, summarize, write_csv

CONDITIONS = ("control", "guided")
GUIDANCE = ("Start with guesses from different semantic categories. Compare their ranks. "
            "Then focus on words related to your best-ranking guess. If several guesses fail "
            "to improve your best rank, switch to a different semantic area.")
CONTROL = "Guess the hidden word using the rank after each guess. You have up to 30 guesses."
COMMON = ("Play an English semantic hidden-word guessing game. Lower ranks are closer; "
          "rank 1 identifies the target. Use the provided guesses and ranks. "
          "Do not repeat guesses. Return exactly one English word, letters only, in your final answer. "
          "You have no external tools. ")
SENTINELS = ("water", "person", "object")
LIMITS = {"production_guess": 4500, "production_report": 150,
          "pilot_guess": 120, "pilot_report": 4}
SOURCES = ("study_batch.py", "study_analysis.py", "gemini_trial.py", "automated_game.py",
           "evaluation_metrics.py")


def instructions(condition):
    if condition not in CONDITIONS:
        raise ValueError("Unknown instruction condition")
    return COMMON + CONTROL + (" " + GUIDANCE if condition == "guided" else "")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp." + uuid4().hex)
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def schedule(pilot=False):
    rng = random.Random(SEED + int(pilot))
    dates = (["2026-10-23", "2026-10-24"] if pilot else
             [(date(2026, 10, 26) + timedelta(days=i)).isoformat() for i in range(25)])
    rng.shuffle(dates)
    firsts = ["control"] * ((len(dates) + 1) // 2) + ["guided"] * (len(dates) // 2)
    rng.shuffle(firsts)
    games = []
    for target in dates:
        initial = firsts.pop()
        for repetition in range(1, 2 if pilot else 4):
            first = initial if repetition % 2 else ("guided" if initial == "control" else "control")
            for condition in (first, "guided" if first == "control" else "control"):
                phase = "pilot" if pilot else "production"
                games.append({"id": f"{phase}_{target}_{condition}_{repetition}", "date": target,
                              "condition": condition, "repetition": repetition, "phase": phase})
    return games


def prepare(output=None):
    directory = Path(output) if output else ROOT / "runs" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_instruction_study_" + uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    used = set()
    for path in (ROOT / "runs").glob("**/events.jsonl"):
        for entry in read_events(path):
            if entry["event"] == "start":
                try:
                    used.add(parse_date(entry["puzzle"]).isoformat())
                except (ValueError, KeyError):
                    pass
    games = schedule()
    dates = sorted({g["date"] for g in games})
    manifest = {"schema": "contexto-instruction-study/v1", "prepared_at": now(),
                "model": DEFAULT_MODEL, "settings": dict(SETTINGS),
                "report_settings": {**SETTINGS, "max_output_tokens": 512},
                "max_guesses": 30, "seed": SEED, "repetitions": 3,
                "instructions": {c: instructions(c) for c in CONDITIONS},
                "report_prompt": "The game has ended. In one or two sentences, describe the strategy "
                                 "you used in this game. Return prose rather than another guess.",
                "games": games, "pilot_games": schedule(pilot=True), "target_dates": dates,
                "previously_started_dates": sorted(set(dates) & used),
                "selection": "last 25 completed dates as of 20 November 2026, fixed by user",
                "environment": "live Contexto English; not a frozen or reconstructed scorer",
                "sentinels": list(SENTINELS), "limits": LIMITS, "retry_reserve": 50,
                "maximum_requests": sum(LIMITS.values()) + 50,
                "memory": "explicit, newest first, store=false, no previous_interaction_id",
                "invalid_policy": "malformed/duplicate/website-rejected outputs consume attempts",
                "parser": "last whitespace token; ASCII letters only, lowercase",
                "analysis": "mean target-level guided ordinal wins over all 9 repeat pairs and 30 turns; "
                            "ties=0.5; 10000 whole-target bootstrap resamples; complete six-game targets only",
                "source_sha256": source_hashes()}
    manifest["fingerprint"] = digest(manifest)
    write_json(directory / "manifest.json", manifest)
    write_csv(directory / "human_targets.csv", [{"puzzle_date": d, "previous_pilot": d in used} for d in dates])
    summarize(directory, manifest)
    return directory


def source_amendments(directory, manifest):
    """Explicit operational repairs preserve the original manifest and both source versions."""
    directory = Path(directory).resolve()
    path = directory / "source_amendments.json"
    amendments = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    previous = manifest["source_sha256"]
    for amendment in amendments:
        if (amendment.get("manifest_fingerprint") != manifest["fingerprint"] or
                amendment.get("previous_source_sha256") != previous or not amendment.get("reason") or
                set(amendment.get("source_sha256", {})) != set(previous)):
            raise ValueError("Invalid source amendment; the frozen protocol must remain unchanged")
        for key, hashes in (("previous_archive", previous), ("source_archive", amendment["source_sha256"])):
            archive = (directory / amendment[key]).resolve()
            if not archive.is_relative_to(directory):
                raise ValueError("Source amendment archive must stay inside the study")
            for name, expected in hashes.items():
                file = archive / name
                if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                    raise ValueError("Source amendment archive is missing or changed: " + name)
        previous = amendment["source_sha256"]
    return amendments


def load_manifest(directory, verify_sources=True):
    manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
    unsigned = {k: v for k, v in manifest.items() if k != "fingerprint"}
    if digest(unsigned) != manifest.get("fingerprint"):
        raise ValueError("Study manifest fingerprint changed; do not modify a prepared study.")
    amendments = source_amendments(directory, manifest)
    expected = amendments[-1]["source_sha256"] if amendments else manifest["source_sha256"]
    if verify_sources and (expected != source_hashes() or manifest["settings"] != SETTINGS):
        raise ValueError("Study sources/settings changed after preparation; no execution allowed.")
    return manifest


class BatchLock(AbstractContextManager):
    """OS-held lock survives the file but is released on process exit/crash."""
    def __init__(self, directory):
        self.path = Path(directory) / "runner.lock"

    def __enter__(self):
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise ValueError("Another runner holds this study's process lock.") from None
        return self

    def __exit__(self, *args):
        self.stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream, fcntl.LOCK_UN)
        self.stream.close()


class RequestLedger:
    """Thread-safe, write-ahead accounting. Count ambiguous/crashed requests conservatively."""
    def __init__(self, directory, limits=None, retry_limit=50, secret=""):
        self.path = Path(directory) / "requests.jsonl"
        self.limits = dict(LIMITS if limits is None else limits)
        self.retry_limit, self.secret = retry_limit, secret
        self.lock = threading.Lock()
        # A damaged journal must never silently reset the budget.
        self.records = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()
                        if line.strip()] if self.path.exists() else []
        self.reservations = [e for e in self.records if e["event"] == "request_reserved"]

    def append(self, event, **fields):
        record = {"event": event, "timestamp": now(), **fields}
        text = json.dumps(record, ensure_ascii=False)
        if self.secret:
            text = text.replace(self.secret, "[REDACTED]")
            record = json.loads(text)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.records.append(record)
        return record

    @property
    def retry_count(self):
        return sum(e["retry"] for e in self.reservations)

    def reserve(self, owner, kind, step, request):
        with self.lock:
            if kind not in self.limits:
                raise ValueError("Unknown request category")
            previous = [e for e in self.reservations if (e["owner"], e["kind"], e["step"]) ==
                        (owner, kind, step)]
            if previous:
                if any(e["event"] == "request_returned" and e["reservation"] in
                       {p["reservation"] for p in previous} for e in self.records):
                    raise ValueError("A returned answer already exists; reuse it instead of regenerating.")
                if self.retry_count >= self.retry_limit:
                    raise ValueError("Transport-retry reserve exhausted")
            elif sum(e["kind"] == kind and not e["retry"] for e in self.reservations) >= self.limits[kind]:
                raise ValueError("Request category budget exhausted")
            if len(self.reservations) >= sum(self.limits.values()) + self.retry_limit:
                raise ValueError("Overall request ceiling exhausted")
            identifier = uuid4().hex
            record = self.append("request_reserved", reservation=identifier, owner=owner, kind=kind,
                                 step=step, retry=bool(previous), request=request)
            self.reservations.append(record)
            return identifier

    def finish(self, reservation, raw=None, error=None):
        with self.lock:
            self.append("request_returned" if error is None else "request_failed",
                        reservation=reservation, **({"raw_response": raw} if error is None else {"error": error}))


def request_model(client, ledger, game, category, step, request):
    reservation = ledger.reserve(game["id"], game["phase"] + "_" + category, step, request)
    try:
        response = client.interactions.create(**request)
        raw = response.model_dump(mode="json", exclude_none=True)
    except Exception as error:
        ledger.finish(reservation, error=str(error))
        raise
    ledger.finish(reservation, raw=raw)
    return response


def game_directory(directory, game):
    return Path(directory) / game["phase"] / game["date"] / game["condition"] / f"repeat_{game['repetition']:02d}"


def open_log(path, secret=""):
    if path.exists():
        log = object.__new__(GameLog)
        log.path, log.csv_path, log.secret = path / "events.jsonl", path / "turns.csv", secret
        return log
    return GameLog(path, secret)


def report_events(path):
    file = Path(path) / "strategy_report.jsonl"
    return read_events(file) if file.exists() else []


def report_complete(path):
    return any(e["event"] == "report_response" and e["usable"] for e in report_events(path))


def report_prompt(manifest, game, events):
    # Quote the completed condition as data, rather than leaving a one-word instruction active.
    history = [e for e in events if e["event"] == "feedback"]
    return (manifest["report_prompt"] + "\n\nCompleted game's instructions (historical record):\n" +
            manifest["instructions"][game["condition"]] + "\n\nCompleted game history, oldest first:\n" +
            "\n".join(f"Turn {e['turn']}: {e['guess']} -> {feedback_text(e)}" for e in history) +
            "\n\n" + manifest["report_prompt"])


def strategy_report(directory, manifest, game, client, ledger):
    path = game_directory(directory, game)
    if report_complete(path):
        return
    previous = report_events(path)
    if previous and previous[-1]["event"] != "report_recovery":
        raise ValueError("Unfinished report requires explicit recover command: " + game["id"])
    events = read_events(path / "events.jsonl")
    if not game_metrics(events)["complete"]:
        raise ValueError("Strategy reports require a completed game")
    log = open_log(path, ledger.secret)
    log.path = path / "strategy_report.jsonl"
    request = {"model": manifest["model"], "input": report_prompt(manifest, game, events),
               "generation_config": manifest["report_settings"], "tools": [], "store": False}
    log.write("report_request", request=request)
    try:
        response = request_model(client, ledger, game, "report", 1, request)
        raw = response.model_dump(mode="json", exclude_none=True)
        text, summary = unpack_response(raw)
        usable = raw.get("status") == "completed" and bool(text.strip())
        log.write("report_response", raw_response=raw, text=text, thought_summary=summary, usable=usable)
        if not usable:
            raise ValueError("Returned strategy report is empty or incomplete; preserve it, do not reroll")
    except Exception as error:
        log.write("report_error", message=str(error))
        raise


def preflight(directory, manifest, client):
    try:
        model = client.models.get(model=manifest["model"])
        metadata = model.model_dump(mode="json", exclude_none=True)
    except Exception as error:
        raise ValueError("Configured model availability check failed; no substitution: " + str(error)) from error
    write_json(Path(directory) / "model_preflight.json", {"timestamp": now(), "model": metadata})


def dispatch(groups, worker, workers=3, on_finish=None, stop=None):
    if not 1 <= workers <= 3:
        raise ValueError("Use one to three workers")
    failed = False
    stop = stop if stop is not None else threading.Event()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        iterator = iter(groups)
        active = {}
        for _ in range(workers):
            group = next(iterator, None)
            if group is not None:
                active[pool.submit(worker, group)] = group
        try:
            while active:
                future = next(as_completed(active))
                group = active.pop(future)
                try:
                    ok = future.result()
                except Exception:
                    ok = False
                failed = failed or not ok
                if failed:
                    stop.set()
                if on_finish:
                    on_finish(group, ok)
                following = next(iterator, None) if not failed and not stop.is_set() else None
                if following is not None:
                    active[pool.submit(worker, following)] = following
        except BaseException:
            stop.set()
            raise
    return not failed


def recover(directory, game_id):
    """Offline, explicit recovery; restore returned answers from the durable journal."""
    directory = Path(directory)
    with BatchLock(directory):
        manifest = load_manifest(directory)
        game = next((g for g in manifest["games"] + manifest["pilot_games"] if g["id"] == game_id), None)
        if game is None:
            raise ValueError("Unknown game identity")
        path = game_directory(directory, game)
        if not path.exists():
            raise ValueError("Game has not started; no recovery needed")
        log = open_log(path)
        ledger = RequestLedger(directory)
        reservations = {e["reservation"]: e for e in ledger.reservations if e["owner"] == game_id}
        for returned in ledger.records:
            if returned["event"] != "request_returned" or returned["reservation"] not in reservations:
                continue
            reservation = reservations[returned["reservation"]]
            raw = returned["raw_response"]
            if reservation["kind"].endswith("_guess"):
                events = read_events(log.path)
                existing = [e for e in events if e["event"] == "response" and e["turn"] == reservation["step"]]
                if existing:
                    if len(existing) != 1 or digest(existing[0]["raw_response"]) != digest(raw):
                        raise ValueError("Saved response differs from request journal; manual investigation required")
                else:
                    log.write("response", turn=reservation["step"], raw_response=raw,
                              restored_from_reservation=reservation["reservation"])
            elif not report_complete(path):
                text, summary = unpack_response(raw)
                if raw.get("status") != "completed" or not text.strip():
                    raise ValueError("Returned report is unusable; preserve it without regenerating")
                report = open_log(path)
                report.path = path / "strategy_report.jsonl"
                report.write("report_response", raw_response=raw, text=text, thought_summary=summary,
                             usable=True, restored_from_reservation=reservation["reservation"])
        events = read_events(log.path)
        if game_metrics(events)["complete"]:
            if not report_complete(path):
                report = open_log(path)
                report.path = path / "strategy_report.jsonl"
                report.write("report_recovery", reason="explicit retry of report with no returned answer")
        else:
            log.write("controller_recovery", reason="explicit operational recovery; preserve all returned answers",
                      source_sha256=source_hashes())
            log.write("termination", reason="recovered_pending", success=False)
            log.export()
    return {"game": game_id, "status": "recovery_prepared", "new_model_requests": 0}


def sentinel_probe(directory, game, stage, secret):
    from playwright.sync_api import sync_playwright
    probe_dir = Path(directory) / "checks" / (game["phase"] + "_" + game["date"] + "_" + stage + "_" + uuid4().hex[:8])
    values = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for word in SENTINELS:
                log = GameLog(probe_dir / word, secret)
                context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
                try:
                    adapter = ContextoBrowser(context.new_page(), log, evaluation=True)
                    adapter.open_game(date.fromisoformat(game["date"]))
                    values[word] = adapter.submit(word, 1)
                    if any(e["event"] == "artifact_error" for e in read_events(log.path)):
                        raise ValueError("Sentinel browser evidence could not be saved")
                finally:
                    context.close()
        finally:
            browser.close()
    write_json(probe_dir / "values.json", {"timestamp": now(), "values": values})
    return values


def execute_game(directory, manifest, game, ledger, key):
    from playwright.sync_api import sync_playwright
    path = game_directory(directory, game)
    events = read_events(path / "events.jsonl") if (path / "events.jsonl").exists() else []
    if events and game_metrics(events)["complete"]:
        if report_complete(path):
            return True
        client = create_client(key)
        try:
            strategy_report(directory, manifest, game, client, ledger)
            return True
        finally:
            client.close()
    if events and game_metrics(events)["status"] != "recovered_pending":
        raise ValueError("Unfinished game requires explicit recovery: " + game["id"])
    log = open_log(path, key)
    if not events:
        log.write("study_game", **game, manifest_fingerprint=manifest["fingerprint"])
    resume = any(e["event"] == "start" for e in events)
    client = create_client(key)
    def create(**request):
        step = next(e["turn"] for e in reversed(read_events(log.path)) if e["event"] == "request")
        return request_model(client, ledger, game, "guess", step, request)
    proxy = SimpleNamespace(interactions=SimpleNamespace(create=create))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
                try:
                    adapter = ContextoBrowser(context.new_page(), log, evaluation=True,
                                             artifact_subdir="browser_" + uuid4().hex[:8])
                    adapter.open_game(date.fromisoformat(game["date"]))
                    if resume:
                        for entry in events:
                            if entry["event"] == "feedback" and entry["feedback"] in {"rank", "invalid"}:
                                expected = entry["rank"] if entry["feedback"] == "rank" else "invalid"
                                if adapter.submit(entry["guess"], entry["turn"]) != expected:
                                    raise ValueError("Website replay changed ranks; no further model calls allowed")
                        log.write("browser_replay_verified", model_requests=0)
                    reason = run_game(proxy, log, manifest["model"], game["date"], 30,
                                      get_feedback=adapter.submit, evaluation=True, resume=resume,
                                      instructions=manifest["instructions"][game["condition"]],
                                      condition=game["condition"],
                                      show=lambda message: print(f"[{game['id']}] {message}", flush=True))
                    adapter.snapshot("final")
                finally:
                    context.close()
            finally:
                browser.close()
        if reason not in {"success", "guess_limit"}:
            return False
        if any(e["event"] == "artifact_error" for e in read_events(log.path)):
            raise ValueError("Missing browser evidence; investigate before continuing")
        strategy_report(directory, manifest, game, client, ledger)
        return True
    except Exception as error:
        log.write("study_error", message=str(error))
        # Preserve a guessing termination, particularly when only a report failed.
        if not any(e["event"] == "termination" for e in read_events(log.path)):
            log.write("termination", reason="browser_setup_error", success=False)
        log.export()
        raise
    finally:
        client.close()


def consistent_ranks(directory, games):
    observed = {}
    for game in games:
        for event in read_events(game_directory(directory, game) / "events.jsonl"):
            if event["event"] == "feedback" and event["feedback"] == "rank":
                key = (game["date"], event["guess"])
                if key in observed and observed[key] != event["rank"]:
                    return False
                observed[key] = event["rank"]
    return True


def execute_group(directory, manifest, games, ledger, key, stop=None):
    stop = stop if stop is not None else threading.Event()
    checks = Path(directory) / "checks"
    checks.mkdir(exist_ok=True)
    marker = checks / (games[0]["phase"] + "_" + games[0]["date"] + ".json")
    state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    try:
        before = sentinel_probe(directory, games[0], "before", key)
        if "before" in state and state["before"] != before:
            raise ValueError("Sentinel feedback changed since earlier execution")
        state.update(before=before, passed=False, timestamp=now())
        write_json(marker, state)
        for game in games:
            if stop.is_set():
                return False
            print("Starting " + game["id"], flush=True)
            if not execute_game(directory, manifest, game, ledger, key):
                stop.set()
                return False
        after = sentinel_probe(directory, games[0], "after", key)
        state.update(after=after, ranks_consistent=consistent_ranks(directory, games))
        state["passed"] = before == after and state["ranks_consistent"]
        write_json(marker, state)
        if not state["passed"]:
            raise ValueError("Scoring drift detected; investigation required")
        return True
    except Exception as error:
        stop.set()
        state.update(passed=False, error=str(error).replace(key, "[REDACTED]"), timestamp=now())
        write_json(marker, state)
        print(f"Stopped target {games[0]['date']}: {state['error']}", flush=True)
        return False


def feedback_matches_evidence(events):
    """Recompute parsing/local rejections and match ranked guesses to browser evidence."""
    responses = {e["turn"]: e["raw_response"] for e in events if e["event"] == "response"}
    seen = set()
    for entry in (e for e in events if e["event"] == "feedback"):
        raw = responses.get(entry["turn"], {})
        answer, _ = unpack_response(raw)
        try:
            if raw.get("status") != "completed":
                raise ValueError("incomplete")
            guess = parse_guess(answer.split()[-1] if answer.split() else "")
        except ValueError:
            if entry["feedback"] != "invalid_output" or entry.get("rank") is not None:
                return False
            continue
        if guess in seen:
            if entry["feedback"] != "duplicate" or entry.get("rank") is not None:
                return False
            continue
        if entry["guess"] != guess or entry["feedback"] not in {"rank", "invalid"}:
            return False
        seen.add(guess)
        expected = entry["rank"] if entry["feedback"] == "rank" else "invalid"
        matches = False
        for observed in (e for e in events if e["event"] == "browser_feedback" and
                         e.get("turn") == entry["turn"] and e.get("submitted_word") == guess):
            try:
                matches = matches or classify_feedback(observed["observed"], allow_duplicate=True) == expected
            except (ValueError, RuntimeError, KeyError):
                continue
        if not matches:
            return False
    return True


def audit(directory, phase="production"):
    directory = Path(directory)
    manifest = load_manifest(directory)
    games = manifest["pilot_games"] if phase == "pilot" else manifest["games"]
    ledger = RequestLedger(directory, manifest["limits"], manifest["retry_reserve"])
    checks, hashes = [], {}
    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
    check("unique scheduled game identities", len({g["id"] for g in games}) == len(games))
    for game in games:
        label = game["id"] + ": "
        path = game_directory(directory, game)
        file = path / "events.jsonl"
        if not file.exists():
            check(label + "game completed", False)
            continue
        hashes[game["id"]] = hashlib.sha256(file.read_bytes()).hexdigest()
        events = read_events(file)
        metric = game_metrics(events)
        check(label + "game completed", metric["complete"])
        starts = [e for e in events if e["event"] == "start"]
        check(label + "one correct original start", len(starts) == 1 and
              starts[0].get("model") == manifest["model"] and starts[0].get("puzzle") == game["date"] and
              starts[0].get("max_guesses") == 30 and starts[0].get("condition") == game["condition"] and
              starts[0].get("instructions") == manifest["instructions"][game["condition"]] and
              starts[0].get("generation_config") == manifest["settings"] and
              starts[0].get("evaluation") and starts[0].get("memory_mode") == "explicit")
        identities = [e for e in events if e["event"] == "study_game"]
        check(label + "correct study identity", len(identities) == 1 and
              all(identities[0].get(k) == v for k, v in game.items()) and
              identities[0].get("manifest_fingerprint") == manifest["fingerprint"])
        feedback = [e for e in events if e["event"] == "feedback"]
        responses = [e for e in events if e["event"] == "response"]
        turns = [e["turn"] for e in responses]
        check(label + "unique contiguous attempts and feedback", turns == list(range(1, len(turns) + 1)) and
              turns == [e["turn"] for e in feedback] and len(turns) <= 30)
        check(label + "parsing and feedback match saved browser evidence", feedback_matches_evidence(events))
        check(label + "fresh browser and complete evidence", any(
            e["event"] == "browser_ready" and e.get("fresh_game") and e.get("requested_date") == game["date"]
            for e in events) and not any(e["event"] == "artifact_error" for e in events))
        valid_requests = True
        for event in (e for e in events if e["event"] == "request"):
            history = [{k: e.get(k) for k in ("turn", "guess", "feedback", "rank")}
                       for e in feedback if e["turn"] < event["turn"]]
            expected = {"model": manifest["model"], "input": build_prompt(
                history, "explicit", True, 30, manifest["instructions"][game["condition"]]),
                "generation_config": manifest["settings"], "tools": [], "store": False}
            valid_requests = valid_requests and event["request"] == expected
        check(label + "exact isolated full-history prompts", valid_requests)
        reserved = {e["reservation"]: e for e in ledger.reservations if e["owner"] == game["id"]}
        returned = [e for e in ledger.records if e["event"] == "request_returned" and
                    e["reservation"] in reserved]
        guessing = [e for e in returned if reserved[e["reservation"]]["kind"].endswith("_guess")]
        guessing_requests = [e for e in reserved.values() if e["kind"].endswith("_guess")]
        local_requests = [e for e in events if e["event"] == "request"]
        check(label + "guess requests match durable reservations", len(guessing_requests) == len(local_requests) and
              all(any(r["step"] == e["turn"] and r["request"] == e["request"] for r in guessing_requests)
                  for e in local_requests))
        check(label + "returned answers match journal", len(guessing) == len(responses) and all(
            any(reserved[r["reservation"]]["step"] == e["turn"] and
                digest(r["raw_response"]) == digest(e["raw_response"]) for r in guessing) for e in responses))
        import csv
        csv_file = path / "turns.csv"
        with csv_file.open(encoding="utf-8", newline="") if csv_file.exists() else open(os.devnull) as stream:
            csv_rows = list(csv.DictReader(stream))
        check(label + "CSV count matches responses", len(csv_rows) == len(responses))
        report = report_events(path)
        report_requests = [e for e in report if e["event"] == "report_request"]
        expected_report = {"model": manifest["model"], "input": report_prompt(manifest, game, events),
                           "generation_config": manifest["report_settings"], "tools": [], "store": False}
        report_returned = [e for e in returned if reserved[e["reservation"]]["kind"].endswith("_report")]
        report_answers = [e for e in report if e["event"] == "report_response"]
        check(label + "separate strategy report", report_complete(path) and bool(report_requests) and
              all(e["request"] == expected_report for e in report_requests) and
              len(report_returned) == len(report_answers) == 1 and
              digest(report_returned[0]["raw_response"]) == digest(report_answers[0]["raw_response"]))
    for target in sorted({g["date"] for g in games}):
        file = directory / "checks" / (phase + "_" + target + ".json")
        state = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
        check(target + ": stable sentinel checks and repeated ranks", state.get("passed") and
              state.get("before") == state.get("after") and state.get("ranks_consistent"))
    check("request reservation IDs unique", len({e["reservation"] for e in ledger.reservations}) ==
          len(ledger.reservations))
    known = {g["id"]: g for g in manifest["games"] + manifest["pilot_games"]}
    check("all journal entries belong to scheduled request slots", all(
        e["owner"] in known and e["kind"] in {known[e["owner"]]["phase"] + "_guess",
                                              known[e["owner"]]["phase"] + "_report"} and
        1 <= e["step"] <= (30 if e["kind"].endswith("_guess") else 1) for e in ledger.reservations))
    preflight_path = directory / "model_preflight.json"
    check("configured model preflight recorded", preflight_path.exists())
    for kind, cap in manifest["limits"].items():
        check(kind + " budget", sum(e["kind"] == kind and not e["retry"] for e in ledger.reservations) <= cap)
    check("transport-retry budget", ledger.retry_count <= manifest["retry_reserve"])
    check("overall request ceiling", len(ledger.reservations) <= manifest["maximum_requests"])
    result = {"passed": all(e["passed"] for e in checks), "phase": phase, "checks": checks,
              "manifest_fingerprint": manifest["fingerprint"], "event_log_sha256": hashes,
              "requests_reserved": len(ledger.reservations), "retry_requests": ledger.retry_count,
              "source_amendments": source_amendments(directory, manifest),
              "timestamp": now()}
    prefix = "PILOT_AUDIT" if phase == "pilot" else "AUDIT"
    write_json(directory / (prefix + ".json"), result)
    failed = [e["check"] for e in checks if not e["passed"]]
    (directory / (prefix + ".md")).write_text(
        f"# {phase.title()} verification\n\nStatus: **{'PASS' if result['passed'] else 'INCOMPLETE / CHECK REQUIRED'}**.\n\n" +
        f"Requests reserved: {len(ledger.reservations)}/4824; retries: {ledger.retry_count}/50.\n\n" +
        "\n".join("- " + name for name in failed) + "\n", encoding="utf-8")
    return result


def execute(directory, phase="production", workers=3):
    directory = Path(directory).resolve()
    with BatchLock(directory):
        manifest = load_manifest(directory)
        if phase == "production" and not audit(directory, "pilot")["passed"]:
            raise ValueError("The separate four-game pilot must pass its audit before production")
        key = read_api_key()
        if not key:
            raise ValueError("GEMINI_API_KEY is missing; no model requests were made")
        client = create_client(key)
        try:
            preflight(directory, manifest, client)
        except Exception as error:
            message = str(error).replace(key, "[REDACTED]")
            write_json(directory / "LAST_STATUS.json", {"stage": "preflight", "error": message,
                                                       "timestamp": now()})
            raise ValueError(message) from None
        finally:
            client.close()
        ledger = RequestLedger(directory, manifest["limits"], manifest["retry_reserve"], key)
        games = manifest["pilot_games"] if phase == "pilot" else manifest["games"]
        groups = []
        for target in dict.fromkeys(g["date"] for g in games):
            group = [g for g in games if g["date"] == target]
            marker = directory / "checks" / (phase + "_" + target + ".json")
            checked = json.loads(marker.read_text(encoding="utf-8")).get("passed") if marker.exists() else False
            if checked and all((game_directory(directory, g) / "events.jsonl").exists() and
                               game_metrics(read_events(game_directory(directory, g) / "events.jsonl"))["complete"] and
                               report_complete(game_directory(directory, g)) for g in group):
                continue
            groups.append(group)
        def finished(group, ok):
            if phase == "production":
                summary = summarize(directory, manifest)
                print(f"Progress: {summary['completed']}/150 games, {len(ledger.reservations)}/4824 requests", flush=True)
        stop = threading.Event()
        ok = dispatch(groups, lambda group: execute_group(directory, manifest, group, ledger, key, stop),
                      workers=workers, on_finish=finished, stop=stop)
        summarize(directory, manifest)
        result = audit(directory, phase)
        write_json(directory / "LAST_STATUS.json", {"phase": phase, "passed": result["passed"],
                                                   "requests_reserved": len(ledger.reservations), "timestamp": now()})
        return 0 if ok and result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Freeze the fixed study; no network or model calls")
    prep.add_argument("--output", type=Path)
    for name in ("pilot", "run", "recover", "summarize", "audit"):
        command = sub.add_parser(name)
        command.add_argument("batch", type=Path)
        if name in {"pilot", "run"}:
            command.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
        if name == "recover":
            command.add_argument("--game", required=True)
        if name == "audit":
            command.add_argument("--phase", choices=("pilot", "production"), default="production")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.output))
            return 0
        if args.command in {"pilot", "run"}:
            return execute(args.batch, "pilot" if args.command == "pilot" else "production", args.workers)
        if args.command == "recover":
            print(json.dumps(recover(args.batch, args.game)))
            return 0
        with BatchLock(args.batch):
            if args.command == "audit":
                result = audit(args.batch, args.phase)
                print(json.dumps({k: v for k, v in result.items() if k not in {"checks", "event_log_sha256"}}))
                return 0 if result["passed"] else 1
            result = summarize(args.batch, load_manifest(args.batch))
            print(json.dumps({k: v for k, v in result.items() if k != "games"}, indent=2))
            return 0
    except Exception as error:
        try:
            secret = read_api_key()
        except OSError:
            secret = ""
        message = str(error).replace(secret, "[REDACTED]") if secret else str(error)
        print("Study stopped: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
