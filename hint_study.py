"""Optional-hint follow-up: prepare, probe, pilot, collect, recover, summarize and audit.

The original 150-game study is only read, never modified. Everything here writes
to a separate run directory with its own frozen manifest and audit.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from automated_game import ContextoBrowser, ROOT, classify_feedback
import hint_analysis as analysis
from evaluation_metrics import read_events
from gemini_trial import (SETTINGS, GameLog, create_client, feedback_text, now, parse_guess,
                          read_api_key, sdk_version, unpack_response)
from study_batch import (BatchLock, RequestLedger, SENTINELS, digest, open_log, preflight,
                         report_complete, report_events, request_model, sentinel_probe, write_json)

SCHEMA = "contexto-hint-study/v1"
HINT_TOKEN = "[HINT]"
MAX_GUESSES = 30
SEED = analysis.SEED
BASELINE = ROOT / "runs" / "20261120T213300Z_instruction_study_5625ddd2"
# 25 targets x (30 guesses + 1 hint) actions; one report per game; two pilot games.
LIMITS = {"production_action": 775, "production_report": 25, "pilot_action": 62, "pilot_report": 2}
RETRY_RESERVE = 10
MAX_REQUESTS = sum(LIMITS.values()) + RETRY_RESERVE
SOURCES = ("hint_study.py", "hint_analysis.py", "study_batch.py", "study_analysis.py",
           "gemini_trial.py", "automated_game.py", "evaluation_metrics.py")
FINAL = {analysis.SUCCESS, analysis.REVEAL, analysis.LIMIT}
HINT_PARAGRAPH = (
    "You may request one website hint during the game. To request it, return the exact token "
    f"{HINT_TOKEN} as your final answer instead of a word. A hint does not use a guess attempt. "
    "The hint is a real word and rank supplied by the website. It is not one of your guesses and "
    "does not count as solving the game. The hint becomes available after your first valid ranked "
    "guess. A hint request that is not available, or a second request, uses one guess attempt.")
REPORT_PROMPT = ("The game has ended. In one or two sentences, describe the strategy you used in this "
                 "game, and explain why you did or did not request the hint. Return prose rather "
                 "than another guess.")
HINT_STATUS = {
    "unavailable": "Hint status: not yet available (it unlocks after your first valid ranked guess; "
                   "a request now would use a guess attempt).",
    "available": f"Hint status: available (one hint; return {HINT_TOKEN} as your final token to request it; "
                 "it does not use a guess attempt).",
    "used": f"Hint status: already used (another {HINT_TOKEN} request would use a guess attempt)."}
SENTINEL_TARGETS = SENTINELS

# --- action parsing, eligibility and prompts -------------------------------------------------


def parse_action(text):
    """Final whitespace token: the reserved hint token, otherwise the original word parser."""
    tokens = text.split()
    if not tokens:
        raise ValueError("Expected a word or the hint token.")
    if tokens[-1] == HINT_TOKEN:
        return "hint", None
    return "guess", parse_guess(tokens[-1])


def guess_entries(history):
    return [e for e in history if e["kind"] == "guess"]


def hint_status(history, max_guesses=MAX_GUESSES):
    if any(e["kind"] == "hint" for e in history):
        return "used"
    guesses = guess_entries(history)
    if len(guesses) < max_guesses and any(e["feedback"] == "rank" for e in guesses):
        return "available"
    return "unavailable"


def hint_eligible(history, max_guesses=MAX_GUESSES):
    return hint_status(history, max_guesses) == "available"


def entry_line(entry):
    if entry["kind"] == "hint":
        return (f"Action {entry['action']} (hint after guess {entry['after_guess']}): "
                f"{entry['word']} -> rank {entry['rank']} [website hint; not your guess]")
    result = ("hint request not eligible; attempt consumed, no score"
              if entry["feedback"] == "ineligible_hint" else feedback_text(entry))
    return f"Action {entry['action']} (guess {entry['guess_number']}): {entry['guess']} -> {result}"


def build_hint_prompt(history, instructions, max_guesses=MAX_GUESSES):
    remaining = max_guesses - len(guess_entries(history))
    lines = [instructions,
             f"You have at most {max_guesses} guess attempts. Invalid, repeated, malformed and "
             "ineligible-hint outputs consume an attempt and receive no score.",
             f"Guess attempts remaining: {remaining} of {max_guesses}.",
             HINT_STATUS[hint_status(history, max_guesses)], "",
             "Complete action history (newest first):"]
    lines.extend(entry_line(e) for e in reversed(history))
    if not history:
        lines.append("No actions yet.")
    lines.extend(["", f"Choose your next action. Your final answer must be exactly one English word, "
                      f"or {HINT_TOKEN}."])
    return "\n".join(lines)


def decide(raw, history, seen, max_guesses=MAX_GUESSES):
    """Classify one returned answer. Shared by the controller and the audit."""
    answer, _ = unpack_response(raw)
    try:
        if raw.get("status") != "completed":
            raise ValueError("Interaction is not completed.")
        kind, word = parse_action(answer)
    except ValueError as error:
        return {"action": "local", "feedback": "invalid_output", "guess": "[invalid output]",
                "message": str(error)}
    if kind == "hint":
        if hint_eligible(history, max_guesses):
            return {"action": "hint"}
        return {"action": "local", "feedback": "ineligible_hint", "guess": HINT_TOKEN,
                "message": "The hint was not eligible."}
    if word in seen:
        return {"action": "local", "feedback": "duplicate", "guess": word,
                "message": "Model repeated an earlier guess."}
    return {"action": "guess", "guess": word}


# --- state reconstruction -----------------------------------------------------------------------


def state_from_events(events):
    """Rebuild the controller state from authoritative events only."""
    history, replay, responses, outcomes = [], [], {}, set()
    dispatched, delivered, final = {}, set(), False
    for event in events:
        kind, turn = event["event"], event.get("turn")
        if kind == "response":
            responses[turn] = event["raw_response"]
        elif kind == "feedback":
            outcomes.add(turn)
            history.append({"kind": "guess", "action": turn, "guess_number": event["guess_number"],
                            "guess": event["guess"], "feedback": event["feedback"], "rank": event.get("rank")})
            if event["feedback"] in {"rank", "invalid"}:
                replay.append(("guess", turn, event["guess"],
                               event["rank"] if event["feedback"] == "rank" else "invalid"))
        elif kind == "hint_dispatch":
            dispatched[turn] = True
        elif kind == "hint_delivered":
            outcomes.add(turn)
            delivered.add(turn)
            dispatched.pop(turn, None)
            history.append({"kind": "hint", "action": turn, "after_guess": event["after_guess"],
                            "word": event["word"], "rank": event["rank"]})
            replay.append(("hint", turn, event["word"], event["rank"]))
        elif kind == "hint_ambiguity_resolved":
            dispatched.pop(turn, None)
        elif kind == "termination":
            final = event["reason"] in FINAL
    open_turns = sorted(t for t in responses if t not in outcomes)
    if len(open_turns) > 1:
        raise ValueError("More than one saved response lacks an outcome; manual investigation required")
    next_turn = max(outcomes, default=0) + 1
    if open_turns and open_turns[0] != next_turn:
        raise ValueError("Saved response turn does not follow the recorded outcomes")
    if sorted(outcomes) != list(range(1, len(outcomes) + 1)):
        raise ValueError("Recorded action identifiers are not contiguous")
    return {"history": history, "replay": replay, "next_turn": next_turn,
            "pending": ({"turn": open_turns[0], "raw": responses[open_turns[0]]} if open_turns else None),
            "attempts": len(guess_entries(history)), "ambiguous_turns": sorted(dispatched),
            "ambiguous": bool(dispatched), "final": final}


# --- the controller -----------------------------------------------------------------------------


def game_directory(directory, game):
    return analysis.game_path(directory, game)


def replay_website(adapter, state, log):
    for kind, turn, word, expected in state["replay"]:
        if kind == "guess":
            if adapter.submit(word, turn) != expected:
                raise ValueError("Website replay changed ranks or rejections; no further model calls allowed")
        else:
            result = adapter.request_hint(turn)
            if (result["word"], result["rank"]) != (word, expected):
                raise ValueError("Website replay changed the hint; no further model calls allowed")
    log.write("browser_replay_verified", model_requests=0, replayed_actions=len(state["replay"]))


def start_fields(manifest, game):
    return {"puzzle": game["date"], "language": "English", "model": manifest["model"],
            "generation_config": manifest["settings"], "max_guesses": manifest["max_guesses"],
            "instructions": manifest["hint_instructions"], "condition": "hint",
            "protocol": SCHEMA, "memory_mode": "explicit", "evaluation": True,
            "history_order": "newest_first", "invalid_policy": "consume_attempt",
            "output_parser": "final_whitespace_token_letters_only_or_hint_token",
            "hint_policy": manifest["hint_policy"], "feedback_source": "browser", "tools": [],
            "automatic_retries": False}


def play_game(create, log, adapter, manifest, game, show=print):
    """Run or resume one hint-enabled game. `create(turn, request)` returns a model response."""
    max_guesses = manifest["max_guesses"]
    events = read_events(log.path) if log.path.exists() else []
    expected = start_fields(manifest, game)
    start = next((e for e in events if e["event"] == "start"), None)
    if start is None:
        log.write("start", **expected, sdk_version=sdk_version())
    elif any(start.get(k) != expected[k] for k in ("puzzle", "model", "generation_config",
                                                    "max_guesses", "instructions")):
        raise ValueError("Resume configuration must match the original game.")
    state = state_from_events(events)
    if state["final"]:
        raise ValueError("Cannot resume a finished game.")
    if state["ambiguous"]:
        raise ValueError("Ambiguous hint delivery for action(s) "
                         f"{state['ambiguous_turns']}; investigate before any further request.")
    if state["replay"]:
        log.write("resume", next_turn=state["next_turn"], previous_attempts=state["attempts"])
        replay_website(adapter, state, log)
    history, pending, turn = state["history"], state["pending"], state["next_turn"]
    seen = {e["guess"] for e in guess_entries(history) if e["feedback"] in {"rank", "invalid"}}
    attempts, reason = state["attempts"], analysis.LIMIT
    try:
        while attempts < max_guesses:
            if pending is not None:
                raw, pending = pending["raw"], None
                log.write("reuse_saved_response", turn=turn, new_model_requests=0)
            else:
                request = {"model": manifest["model"],
                           "input": build_hint_prompt(history, manifest["hint_instructions"], max_guesses),
                           "generation_config": dict(manifest["settings"]), "tools": [], "store": False}
                log.write("request", turn=turn, request=request, observed_history=history)
                try:
                    raw = create(turn, request).model_dump(mode="json", exclude_none=True)
                except Exception as error:
                    log.write("api_error", turn=turn, error_type=type(error).__name__, message=str(error))
                    show("API request failed; see the log. No automatic retry was made.")
                    reason = "api_error"
                    break
                log.write("response", turn=turn, raw_response=raw)
            _, summary = unpack_response(raw)
            log.write("thought_summary", turn=turn, text=summary, present=bool(summary))
            log.export(csv_export=False)
            decision = decide(raw, history, seen, max_guesses)
            if decision["action"] == "local":
                attempts += 1
                log.write("output_error", turn=turn, message=decision["message"])
                log.write("feedback", turn=turn, guess_number=attempts, guess=decision["guess"],
                          feedback=decision["feedback"], rank=None)
                history.append({"kind": "guess", "action": turn, "guess_number": attempts,
                                "guess": decision["guess"], "feedback": decision["feedback"], "rank": None})
                show(f"Action {turn}: {decision['feedback']}; guess attempt consumed.")
            elif decision["action"] == "hint":
                log.write("hint_dispatch", turn=turn, after_guess=attempts)  # journaled before the click
                try:
                    result = adapter.request_hint(turn)
                except Exception as error:
                    log.write("browser_error", turn=turn, error_type=type(error).__name__, message=str(error))
                    show(f"Browser hint failed: {error}")
                    reason = "browser_error"
                    break
                log.write("hint_delivered", turn=turn, after_guess=attempts, word=result["word"],
                          rank=result["rank"], settings=result.get("settings"),
                          evidence=result.get("evidence"))
                history.append({"kind": "hint", "action": turn, "after_guess": attempts,
                                "word": result["word"], "rank": result["rank"]})
                show(f"Action {turn}: hint {result['word']} (rank {result['rank']}).")
                if result["rank"] == 1:
                    reason = analysis.REVEAL
                    turn += 1
                    break
            else:
                word = decision["guess"]
                show(f"\nAction {turn}\nModel guess: {word}")
                try:
                    feedback = adapter.submit(word, turn)
                except Exception as error:
                    log.write("browser_error", turn=turn, error_type=type(error).__name__, message=str(error))
                    show(f"Browser feedback failed: {error}")
                    reason = "browser_error"
                    break
                if feedback != "invalid" and not (isinstance(feedback, int) and feedback > 0):
                    raise ValueError(f"Unexpected website feedback: {feedback!r}")
                attempts += 1
                seen.add(word)
                kind = "invalid" if feedback == "invalid" else "rank"
                rank = feedback if kind == "rank" else None
                log.write("feedback", turn=turn, guess_number=attempts, guess=word, feedback=kind, rank=rank)
                history.append({"kind": "guess", "action": turn, "guess_number": attempts, "guess": word,
                                "feedback": kind, "rank": rank})
                if rank == 1:
                    reason = analysis.SUCCESS
                    turn += 1
                    break
            log.export(csv_export=False)
            turn += 1
    except (KeyboardInterrupt, EOFError):
        reason = "interrupted"
    finally:
        guesses = guess_entries(history)
        log.write("termination", reason=reason, attempts_used=len(guesses),
                  submitted_guesses=sum(e["feedback"] in {"rank", "invalid"} for e in guesses),
                  actions=len(history), hint_delivered=any(e["kind"] == "hint" for e in history),
                  success=reason == analysis.SUCCESS)
        log.export()
    show(f"\nStopped: {reason}. Guess attempts used: {attempts}.")
    return reason


# --- real browser adapter -----------------------------------------------------------------------

READ_SETTINGS = """() => {
    const modal = document.querySelector('.modal-bg .modal');
    if (!modal) return null;
    const result = {selected: {}, options: {}};
    for (const section of modal.querySelectorAll(':scope > div > div')) {
        if (section.classList.contains('modal-title') || section.children.length !== 2) continue;
        const label = section.children[0].innerText.trim();
        const options = Array.from(section.children[1].children).map(option => ({
            name: (option.children[1]?.children[0]?.innerText || '').trim(),
            description: (option.children[1]?.children[1]?.innerText || '').trim(),
            checked: !!option.querySelector('input[type="radio"]')?.checked}));
        result.options[label] = options;
        result.selected[label] = options.filter(o => o.checked).map(o => o.name).join(',');
    }
    return result;
}"""

# A real hint is a row marked by an icon, with the hint counter incremented. Never infer it.
READ_HINT = """({before, hintsBefore}) => {
    const message = document.querySelector('main .message');
    if (!message || message.innerHTML === before) return false;
    const text = message.querySelector('.message-text');
    if (text) {
        const content = text.innerText.trim();
        if (/^calculating[.\\u2026]*$/i.test(content)) return false;
        return {kind: 'error', message: content};
    }
    const row = message.querySelector('.row');
    if (!row) return false;
    const wordNode = row.querySelector('.row-word');
    const rankNode = row.querySelector(':scope > span:last-child');
    const rankText = rankNode?.textContent.trim();
    if (!wordNode || !/^\\d+$/.test(rankText || '') || Number(rankText) < 1) return false;
    const info = (document.querySelector('.info-bar')?.innerText || '').replace(/\\s+/g, ' ').trim();
    const counter = info.match(/HINTS:\\s*(\\d+)/i);
    if ((counter ? Number(counter[1]) : 0) !== hintsBefore + 1) return false;
    const word = Array.from(wordNode.childNodes).filter(n => n.nodeType === 3)
        .map(n => n.textContent).join('').trim();
    return {kind: 'hint', word, rank: Number(rankText), icon: !!wordNode.querySelector('svg'),
            repeated: !!row.querySelector('.row-note'), info, message: message.innerText.trim()};
}"""


class HintBrowser(ContextoBrowser):
    """Local extension of the original adapter. It requests the website's actual hint."""
    def __init__(self, page, log, expected_settings=None, timeout_ms=45000, artifact_subdir="browser"):
        super().__init__(page, log, timeout_ms=timeout_ms, evaluation=True, artifact_subdir=artifact_subdir)
        self.expected_settings = expected_settings

    def relative(self, name):
        return str((self.artifacts / name).relative_to(self.log.path.parent)).replace("\\", "/")

    def info(self):
        text = " ".join(self.page.locator(".info-bar").inner_text().split())
        guesses = re.search(r"GUESSES:\s*(\d+)", text, re.IGNORECASE)
        hints = re.search(r"HINTS:\s*(\d+)", text, re.IGNORECASE)
        return {"text": text, "guesses": int(guesses.group(1)) if guesses else None,
                "hints": int(hints.group(1)) if hints else 0}

    def open_menu(self, item):
        self.page.locator('button[aria-label="Menu"]').click()
        self.page.locator(".dropdown .menu-item", has_text=item).click()

    def read_settings(self, name=None):
        """Read the visible settings dialog and close it again without changing anything."""
        self.open_menu("Settings")
        self.page.locator(".modal-bg .modal").wait_for(state="visible")
        found = self.page.evaluate(READ_SETTINGS)
        if name:
            (self.artifacts / f"{name}.html").write_text(
                self.page.locator(".modal-bg .modal").inner_html(), encoding="utf-8")
        self.page.locator("button.modal-close-button").click()
        self.page.locator(".modal-bg").wait_for(state="detached")
        if not found or not found["selected"].get("Hints"):
            raise RuntimeError("Could not read the website hint settings")
        self.last_settings_options = found["options"]
        return found["selected"]

    def request_hint(self, turn):
        settings = self.read_settings(f"settings_{turn:02d}")
        if self.expected_settings is not None and settings != self.expected_settings:
            raise RuntimeError(f"Website settings differ from the probe: {settings}")
        message = self.page.locator("main .message")
        before = message.inner_html() if message.count() else ""
        info_before = self.info()
        self.log.write("browser_hint_submit", turn=turn, settings=settings, info=info_before)
        try:
            self.open_menu("Hint")
            result = self.page.wait_for_function(
                READ_HINT, arg={"before": before, "hintsBefore": info_before["hints"]},
                timeout=self.timeout_ms).json_value()
            self.snapshot(f"hint_{turn:02d}")
            info_after = self.info()
            if result["kind"] != "hint" or not result["icon"] or result["repeated"]:
                raise RuntimeError(f"The website did not deliver a recognisable hint: {result}")
            if info_after["guesses"] != info_before["guesses"]:
                raise RuntimeError("The hint changed the website guess counter")
        except Exception:
            self.snapshot(f"error_hint_{turn:02d}")
            raise
        observed = {"word": result["word"], "rank": result["rank"], "settings": settings,
                    "info_before": info_before, "info_after": info_after,
                    "evidence": {"html": self.relative(f"hint_{turn:02d}.html"),
                                 "screenshot": self.relative(f"hint_{turn:02d}.png"),
                                 "settings_html": self.relative(f"settings_{turn:02d}.html")}}
        self.log.write("browser_hint", turn=turn, observed=observed, url=self.page.url)
        return observed


# --- protocol freeze ----------------------------------------------------------------------------


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: sha256_file(ROOT / name) for name in SOURCES}


def baseline_files(baseline, archived):
    """Control games and consistency checks of the archived study, frozen by hash."""
    controls, checks = {}, {}
    pilot_dates = sorted({g["date"] for g in archived["pilot_games"]})
    for phase, dates, minimum in (("production", sorted(archived["target_dates"]), 3), ("pilot", pilot_dates, 1)):
        for target in dates:
            files = sorted((baseline / phase / target / "control").glob("repeat_*/events.jsonl"))
            if len(files) < minimum:
                raise ValueError(f"Baseline has fewer than {minimum} control games for {target}")
            for file in files:
                repetition = int(file.parent.name.split("_")[1])
                controls[f"{phase}_{target}_control_{repetition}"] = {
                    "phase": phase, "date": target, "repetition": repetition,
                    "path": file.relative_to(baseline).as_posix(), "sha256": sha256_file(file)}
            marker = baseline / "checks" / f"{phase}_{target}.json"
            if not marker.exists() or not json.loads(marker.read_text(encoding="utf-8")).get("passed"):
                raise ValueError(f"Baseline sentinel check missing or failed for {target}")
            checks[f"{phase}_{target}"] = {"path": marker.relative_to(baseline).as_posix(),
                                            "sha256": sha256_file(marker)}
    return controls, checks


def prepare(output=None, baseline=BASELINE):
    baseline = Path(baseline).resolve()
    archived = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
    if digest({k: v for k, v in archived.items() if k != "fingerprint"}) != archived.get("fingerprint"):
        raise ValueError("The archived manifest fingerprint is invalid.")
    audit_file = baseline / "AUDIT.json"
    if not audit_file.exists() or not json.loads(audit_file.read_text(encoding="utf-8")).get("passed"):
        raise ValueError("The archived study must have a passing production audit.")
    controls, checks = baseline_files(baseline, archived)
    directory = Path(output) if output else ROOT / "runs" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_hint_study_" + uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    dates = sorted(archived["target_dates"])
    pilot_dates = sorted({g["date"] for g in archived["pilot_games"]})
    control = archived["instructions"]["control"]
    manifest = {
        "schema": SCHEMA, "prepared_at": now(), "model": archived["model"],
        "settings": dict(archived["settings"]),
        "report_settings": {**archived["settings"], "max_output_tokens": 512},
        "max_guesses": MAX_GUESSES, "seed": SEED, "repetitions": 1,
        "instructions": control, "hint_paragraph": HINT_PARAGRAPH,
        "hint_instructions": control + " " + HINT_PARAGRAPH,
        "report_prompt": REPORT_PROMPT,
        "hint_policy": {
            "token": HINT_TOKEN, "valid_requests": 1,
            "eligible": "after the first valid ranked guess, while at least one guess attempt remains",
            "ineligible_requests": "consume a guess attempt; the website is not asked",
            "hint_does_not_consume_guess": True, "difficulty": "website default, recorded by the probe",
            "answer_revealed": "terminate as answer_revealed_by_hint; never a model solve",
            "guessing_the_hint_word": "website rejection counts as an invalid attempt",
            "trajectory": "model-generated ranks only; hint rank never inserted"},
        "games": [{"id": f"hint_production_{d}", "date": d, "phase": "production", "order": i}
                  for i, d in enumerate(dates, 1)],
        "pilot_games": [{"id": f"hint_pilot_{d}", "date": d, "phase": "pilot", "order": i}
                        for i, d in enumerate(pilot_dates, 1)],
        "target_dates": dates, "pilot_dates": pilot_dates,
        "baseline": {"directory": str(baseline), "manifest_fingerprint": archived["fingerprint"],
                     "manifest_sha256": sha256_file(baseline / "manifest.json"),
                     "audit_sha256": sha256_file(audit_file), "control_games": controls, "checks": checks},
        "execution": {"workers": 1, "order": "chronological", "fresh_english_context_per_game": True,
                      "memory": "explicit full history, newest first, store=false, no previous_interaction_id",
                      "invalid_policy": "malformed, repeated, rejected and ineligible outputs consume attempts",
                      "automatic_retries": False},
        "automatic_retries": False, "sentinels": list(SENTINELS), "limits": LIMITS,
        "retry_reserve": RETRY_RESERVE, "maximum_requests": MAX_REQUESTS,
        "environment": "live Contexto English; not a frozen or reconstructed scorer",
        "analysis": {"primary": "mean target-level ordinal win/tie/loss of the new best-rank trajectory against each "
                                "of three archived controls over 30 attempts; equal weight per target",
                     "bootstrap": "10000 whole-target resamples", "seed": SEED,
                     "inclusion": "completed new game and three verified baseline games"},
        "source_sha256": source_hashes()}
    manifest["fingerprint"] = digest(manifest)
    write_json(directory / "manifest.json", manifest)
    return directory


def load_manifest(directory, verify_sources=True):
    manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
    if digest({k: v for k, v in manifest.items() if k != "fingerprint"}) != manifest.get("fingerprint"):
        raise ValueError("Hint study manifest fingerprint changed; do not modify a prepared study.")
    base = Path(manifest["baseline"]["directory"])
    frozen = {"manifest.json": manifest["baseline"]["manifest_sha256"],
              "AUDIT.json": manifest["baseline"]["audit_sha256"],
              **{v["path"]: v["sha256"] for v in manifest["baseline"]["control_games"].values()},
              **{v["path"]: v["sha256"] for v in manifest["baseline"]["checks"].values()}}
    for name, expected in frozen.items():
        if not (base / name).exists() or sha256_file(base / name) != expected:
            raise ValueError(f"Baseline file changed or missing after preparation: {name}")
    if verify_sources and manifest["source_sha256"] != source_hashes():
        raise ValueError("Study sources changed after preparation; no execution allowed.")
    return manifest


def load_probe(directory):
    path = Path(directory) / "probe.json"
    probe = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not probe.get("passed"):
        raise ValueError("The browser-only probe has not passed; run the probe command first.")
    return probe


# --- baseline comparison checks -----------------------------------------------------------------


def compare_replay(archived_entries, observed):
    """Differences between archived ranked feedback/rejections and a fresh replay."""
    differences = []
    for entry in archived_entries:
        if entry["feedback"] not in {"rank", "invalid"}:
            continue
        expected = entry["rank"] if entry["feedback"] == "rank" else "invalid"
        if entry["guess"] not in observed:
            differences.append(f"{entry['guess']}: not replayed")
        elif observed[entry["guess"]] != expected:
            differences.append(f"{entry['guess']}: archived {expected}, observed {observed[entry['guess']]}")
    return differences


def compare_sentinels(archived, before, after):
    differences = []
    if before != archived.get("before"):
        differences.append(f"sentinels before differ: archived {archived.get('before')}, observed {before}")
    if after != archived.get("after"):
        differences.append(f"sentinels after differ: archived {archived.get('after')}, observed {after}")
    return differences


def archived_controls(manifest, game):
    base = Path(manifest["baseline"]["directory"])
    return {k: v for k, v in manifest["baseline"]["control_games"].items()
            if v["phase"] == game["phase"] and v["date"] == game["date"]}, base


def replay_baseline(directory, manifest, game, secret):
    """Replay each archived control history in its own browser context. Evidence is retained."""
    from playwright.sync_api import sync_playwright
    controls, base = archived_controls(manifest, game)
    evidence = Path(directory) / "checks" / f"{game['phase']}_{game['date']}_baseline_{uuid4().hex[:8]}"
    differences = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for identifier, item in sorted(controls.items()):
                archived = [e for e in read_events(base / item["path"]) if e["event"] == "feedback"]
                log = GameLog(evidence / identifier, secret)
                context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
                observed = {}
                try:
                    adapter = ContextoBrowser(context.new_page(), log, evaluation=True)
                    adapter.open_game(date.fromisoformat(game["date"]))
                    for entry in archived:
                        if entry["feedback"] not in {"rank", "invalid"}:
                            continue
                        try:
                            observed[entry["guess"]] = adapter.submit(entry["guess"], entry["turn"])
                        except Exception as error:
                            differences.append(f"{identifier}: {entry['guess']}: {error}")
                            break
                finally:
                    context.close()
                found = compare_replay(archived, observed) if not differences else []
                differences.extend(f"{identifier}: {d}" for d in found)
                write_json(evidence / identifier / "replay.json", {"observed": observed, "differences": found})
        finally:
            browser.close()
    return differences


def consistent_ranks(directory, manifest, game):
    """No word may have different ranks in the new game and the archived controls."""
    controls, base = archived_controls(manifest, game)
    observed = {}
    for item in controls.values():
        for event in read_events(base / item["path"]):
            if event["event"] == "feedback" and event["feedback"] == "rank":
                observed[event["guess"]] = event["rank"]
    for event in read_events(game_directory(directory, game) / "events.jsonl"):
        if event["event"] == "feedback" and event["feedback"] == "rank":
            if observed.get(event["guess"], event["rank"]) != event["rank"]:
                return False
    return True


# --- reports, execution, recovery ---------------------------------------------------------------


def report_input(manifest, game, events):
    history = state_from_events(events)["history"]
    return (manifest["report_prompt"] + "\n\nCompleted game's instructions (historical record):\n" +
            manifest["hint_instructions"] + "\n\nCompleted game history, oldest first:\n" +
            "\n".join(entry_line(e) for e in history) + "\n\n" + manifest["report_prompt"])


def hint_report(directory, manifest, game, client, ledger):
    path = game_directory(directory, game)
    if report_complete(path):
        return
    previous = report_events(path)
    if previous and previous[-1]["event"] != "report_recovery":
        raise ValueError("Unfinished report requires explicit recover command: " + game["id"])
    events = read_events(path / "events.jsonl")
    if not analysis.game_record(events)["complete"]:
        raise ValueError("Strategy reports require a completed game")
    log = open_log(path, ledger.secret)
    log.path = path / "strategy_report.jsonl"
    request = {"model": manifest["model"], "input": report_input(manifest, game, events),
               "generation_config": manifest["report_settings"], "tools": [], "store": False}
    log.write("report_request", request=request)
    try:
        raw = request_model(client, ledger, game, "report", 1, request).model_dump(mode="json", exclude_none=True)
        text, summary = unpack_response(raw)
        usable = raw.get("status") == "completed" and bool(text.strip())
        log.write("report_response", raw_response=raw, text=text, thought_summary=summary, usable=usable)
        if not usable:
            raise ValueError("Returned strategy report is empty or incomplete; preserve it, do not reroll")
    except Exception as error:
        log.write("report_error", message=str(error))
        raise


def execute_game(directory, manifest, game, ledger, key, probe):
    from playwright.sync_api import sync_playwright
    path = game_directory(directory, game)
    events = read_events(path / "events.jsonl") if (path / "events.jsonl").exists() else []
    record = analysis.game_record(events) if events else {}
    if record.get("complete"):
        if report_complete(path):
            return True
        client = create_client(key)
        try:
            hint_report(directory, manifest, game, client, ledger)
            return True
        finally:
            client.close()
    if events and record["status"] != "recovered_pending":
        raise ValueError("Unfinished game requires explicit recovery: " + game["id"])
    log = open_log(path, key)
    if not events:
        log.write("study_game", **game, manifest_fingerprint=manifest["fingerprint"])
    client = create_client(key)
    def create(step, request):
        return request_model(client, ledger, game, "action", step, request)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
                try:
                    adapter = HintBrowser(context.new_page(), log, expected_settings=probe["expected_settings"],
                                          artifact_subdir="browser_" + uuid4().hex[:8])
                    adapter.open_game(date.fromisoformat(game["date"]))
                    settings = adapter.read_settings()
                    log.write("hint_settings", stage="start", settings=settings)
                    if settings != probe["expected_settings"]:
                        raise ValueError(f"Website settings differ from the probe: {settings}")
                    reason = play_game(create, log, adapter, manifest, game,
                                       show=lambda message: print(f"[{game['id']}] {message}", flush=True))
                    adapter.snapshot("final")
                finally:
                    context.close()
            finally:
                browser.close()
        if reason not in FINAL:
            return False
        if any(e["event"] == "artifact_error" for e in read_events(log.path)):
            raise ValueError("Missing browser evidence; investigate before continuing")
        hint_report(directory, manifest, game, client, ledger)
        return True
    except Exception as error:
        log.write("study_error", message=str(error))
        if not any(e["event"] == "termination" for e in read_events(log.path)):
            log.write("termination", reason="browser_setup_error", success=False)
        log.export()
        raise
    finally:
        client.close()


def execute_target(directory, manifest, game, ledger, key, probe):
    """Baseline replay, sentinels before/after, then the one new game. Stops on any difference."""
    (Path(directory) / "checks").mkdir(exist_ok=True)
    marker = Path(directory) / "checks" / f"{game['phase']}_{game['date']}.json"
    state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    path = game_directory(directory, game)
    events = read_events(path / "events.jsonl") if (path / "events.jsonl").exists() else []
    done = bool(events) and analysis.game_record(events)["complete"] and report_complete(path)
    if state.get("passed") and done:
        return True
    base = Path(manifest["baseline"]["directory"])
    archived = json.loads((base / manifest["baseline"]["checks"][f"{game['phase']}_{game['date']}"]["path"])
                          .read_text(encoding="utf-8"))
    try:
        differences = replay_baseline(directory, manifest, game, key)
        state.update(baseline_replay_differences=differences)
        if differences:
            raise ValueError("Archived control replay differs: " + "; ".join(differences[:5]))
        before = sentinel_probe(directory, game, "before", key)
        if "before" in state and state["before"] != before:
            raise ValueError("Sentinel feedback changed since earlier execution")
        state.update(before=before, passed=False, timestamp=now())
        write_json(marker, state)
        print("Starting " + game["id"], flush=True)
        if not execute_game(directory, manifest, game, ledger, key, probe):
            state.update(passed=False, error="game did not complete; see its events", timestamp=now())
            write_json(marker, state)
            return False
        after = sentinel_probe(directory, game, "after", key)
        differences = compare_sentinels(archived, before, after)
        state.update(after=after, archived_sentinels={k: archived.get(k) for k in ("before", "after")},
                     sentinel_differences=differences, ranks_consistent=consistent_ranks(directory, manifest, game))
        state["passed"] = not differences and state["ranks_consistent"]
        write_json(marker, state)
        if not state["passed"]:
            raise ValueError("Scoring drift detected; investigation required")
        return True
    except Exception as error:
        state.update(passed=False, error=str(error).replace(key, "[REDACTED]"), timestamp=now())
        write_json(marker, state)
        print(f"Stopped target {game['date']}: {state['error']}", flush=True)
        return False


def execute(directory, phase="production"):
    directory = Path(directory).resolve()
    with BatchLock(directory):
        manifest = load_manifest(directory)
        probe = load_probe(directory)
        if phase == "production" and not audit(directory, "pilot")["passed"]:
            raise ValueError("The two-game pilot must pass its audit before production")
        key = read_api_key()
        if not key:
            raise ValueError("GEMINI_API_KEY is missing; no model requests were made")
        client = create_client(key)
        try:
            preflight(directory, manifest, client)
        except Exception as error:
            message = str(error).replace(key, "[REDACTED]")
            write_json(directory / "LAST_STATUS.json", {"stage": "preflight", "error": message, "timestamp": now()})
            raise ValueError(message) from None
        finally:
            client.close()
        ledger = RequestLedger(directory, manifest["limits"], manifest["retry_reserve"], key)
        games = manifest["pilot_games"] if phase == "pilot" else manifest["games"]
        ok = True
        for game in games:  # one worker, chronological, no substitution after a stop
            if not execute_target(directory, manifest, game, ledger, key, probe):
                ok = False
                break
            if phase == "production":
                print(f"Progress: {game['order']}/{len(games)} games, {len(ledger.reservations)} requests", flush=True)
        if phase == "production":
            analysis.summarize(directory, manifest)
        result = audit(directory, phase)
        write_json(directory / "LAST_STATUS.json", {"phase": phase, "passed": result["passed"],
                                                   "requests_reserved": len(ledger.reservations),
                                                   "timestamp": now()})
        return 0 if ok and result["passed"] else 1


def recover(directory, game_id, resolve_ambiguous_hint=False):
    """Offline, explicit recovery: restore returned answers from the durable journal."""
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
        state = state_from_events(read_events(log.path))
        if state["ambiguous"]:
            if not resolve_ambiguous_hint:
                raise ValueError(f"Ambiguous hint delivery for action(s) {state['ambiguous_turns']}: inspect the "
                                 "browser evidence, then rerun with --resolve-ambiguous-hint")
            for turn in state["ambiguous_turns"]:
                log.write("hint_ambiguity_resolved", turn=turn,
                          reason="operator authorised redelivery after inspecting the evidence")
        ledger = RequestLedger(directory, manifest["limits"], manifest["retry_reserve"])
        reservations = {e["reservation"]: e for e in ledger.reservations if e["owner"] == game_id}
        for returned in ledger.records:
            if returned["event"] != "request_returned" or returned["reservation"] not in reservations:
                continue
            reservation, raw = reservations[returned["reservation"]], returned["raw_response"]
            if reservation["kind"].endswith("_action"):
                existing = [e for e in read_events(log.path)
                            if e["event"] == "response" and e["turn"] == reservation["step"]]
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
        if analysis.game_record(events)["complete"]:
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


# --- browser-only probe -------------------------------------------------------------------------

PROBE_WORD, PROBE_SECOND = "water", "person"


def probe_date(browser, directory, target):
    """Request a real hint in a throwaway context, then replay it in a second fresh context."""
    folder = Path(directory) / "probe" / target
    result = {"date": target}
    context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
    try:
        log = GameLog(folder / "first")
        adapter = HintBrowser(context.new_page(), log)
        adapter.open_game(date.fromisoformat(target))
        result["settings_before_guess"] = adapter.read_settings("settings_initial")
        result["info_before"] = adapter.info()
        result["first_rank"] = adapter.submit(PROBE_WORD, 1)
        hint = adapter.request_hint(2)
        result["hint"] = {k: hint[k] for k in ("word", "rank", "info_before", "info_after", "evidence")}
        result["hint_word_guess"] = adapter.submit(hint["word"], 3)  # expected: rejected as already guessed
        result["second_rank"] = adapter.submit(PROBE_SECOND, 4)
        result["info_after_reload"] = adapter.info()
        result["settings_after"] = adapter.read_settings("settings_final")
    finally:
        context.close()
    context = browser.new_context(locale="en-US", timezone_id="Europe/Budapest")
    try:
        log = GameLog(folder / "replay")
        adapter = HintBrowser(context.new_page(), log)
        adapter.open_game(date.fromisoformat(target))
        replay_rank = adapter.submit(PROBE_WORD, 1)
        replay_hint = adapter.request_hint(2)
        result["replay"] = {"rank": replay_rank, "word": replay_hint["word"], "rank_of_hint": replay_hint["rank"],
                            "settings": replay_hint["settings"]}
    finally:
        context.close()
    result["checks"] = {
        "default_settings_visible": bool(result["settings_before_guess"].get("Hints")),
        "settings_unchanged": result["settings_before_guess"] == result["settings_after"] == result["replay"]["settings"],
        "hint_counter_incremented": result["hint"]["info_after"]["hints"] == result["hint"]["info_before"]["hints"] + 1,
        "guess_counter_unchanged": result["hint"]["info_after"]["guesses"] == result["hint"]["info_before"]["guesses"],
        "hint_word_guess_rejected": result["hint_word_guess"] == "invalid",
        "hint_counter_survives_reload": result["info_after_reload"]["hints"] == 1,
        "replay_identical": (result["replay"]["word"], result["replay"]["rank_of_hint"]) ==
                            (result["hint"]["word"], result["hint"]["rank"])}
    result["passed"] = all(result["checks"].values())
    return result


def probe(directory):
    from playwright.sync_api import sync_playwright
    directory = Path(directory).resolve()
    with BatchLock(directory):
        manifest = load_manifest(directory)
        dates, outcomes = manifest["pilot_dates"], {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for target in dates:
                    outcomes[target] = probe_date(browser, directory, target)
            finally:
                browser.close()
        settings = [o["settings_before_guess"] for o in outcomes.values()]
        consistent = all(s == settings[0] for s in settings)
        report = {"timestamp": now(), "manifest_fingerprint": manifest["fingerprint"], "dates": outcomes,
                  "expected_settings": settings[0], "default_hint_difficulty": settings[0].get("Hints"),
                  "settings_consistent_across_dates": consistent,
                  "passed": consistent and all(o["passed"] for o in outcomes.values())}
        write_json(directory / "probe.json", report)
        return report


# --- audit --------------------------------------------------------------------------------------


def audit(directory, phase="production"):
    directory = Path(directory)
    manifest = load_manifest(directory)
    games = manifest["pilot_games"] if phase == "pilot" else manifest["games"]
    ledger = RequestLedger(directory, manifest["limits"], manifest["retry_reserve"])
    probe_file = directory / "probe.json"
    probe_data = json.loads(probe_file.read_text(encoding="utf-8")) if probe_file.exists() else {}
    expected_settings = probe_data.get("expected_settings")
    base = Path(manifest["baseline"]["directory"])
    checks, hashes = [], {}
    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
    check("unique scheduled game identities", len({g["id"] for g in games}) == len(games))
    check("browser-only probe passed with recorded default settings", bool(probe_data.get("passed")) and
          bool(expected_settings))
    for game in games:
        label = game["id"] + ": "
        path = game_directory(directory, game)
        file = path / "events.jsonl"
        if not file.exists():
            check(label + "game completed", False)
            continue
        hashes[game["id"]] = sha256_file(file)
        events = read_events(file)
        record = analysis.game_record(events)
        check(label + "game completed", record["complete"])
        starts = [e for e in events if e["event"] == "start"]
        wanted = start_fields(manifest, game)
        check(label + "one correct original start", len(starts) == 1 and
              all(starts[0].get(k) == wanted[k] for k in ("puzzle", "model", "max_guesses", "instructions",
                                                          "generation_config", "condition", "evaluation",
                                                          "memory_mode")))
        identities = [e for e in events if e["event"] == "study_game"]
        check(label + "correct study identity", len(identities) == 1 and
              all(identities[0].get(k) == v for k, v in game.items()) and
              identities[0].get("manifest_fingerprint") == manifest["fingerprint"])
        try:
            state = state_from_events(events)
            contiguous = True
        except ValueError:
            state, contiguous = {"history": [], "attempts": 0}, False
        responses = [e for e in events if e["event"] == "response"]
        feedback = [e for e in events if e["event"] == "feedback"]
        delivered = [e for e in events if e["event"] == "hint_delivered"]
        check(label + "contiguous action ids and guess numbers", contiguous and
              [e["turn"] for e in responses] == list(range(1, len(responses) + 1)) and
              [e["guess_number"] for e in feedback] == list(range(1, len(feedback) + 1)) and
              len(feedback) <= manifest["max_guesses"] and len(delivered) <= 1 and
              len(responses) <= manifest["max_guesses"] + 1)
        # Recompute every decision from the saved raw answers and the history at that moment.
        decisions_ok, history, seen = True, [], set()
        saved = {e["turn"]: e["raw_response"] for e in responses}
        outcome_events = [e for e in events if e["event"] in {"feedback", "hint_delivered"}]
        for outcome in outcome_events:
            raw = saved.get(outcome["turn"])
            if raw is None:
                decisions_ok = False
                break
            decision = decide(raw, history, seen, manifest["max_guesses"])
            if outcome["event"] == "hint_delivered":
                decisions_ok = decisions_ok and decision["action"] == "hint" and \
                    outcome["after_guess"] == len(guess_entries(history))
                history.append({"kind": "hint", "action": outcome["turn"], "after_guess": outcome["after_guess"],
                                "word": outcome["word"], "rank": outcome["rank"]})
                continue
            if decision["action"] == "local":
                decisions_ok = decisions_ok and outcome["feedback"] == decision["feedback"] and \
                    outcome["guess"] == decision["guess"] and outcome.get("rank") is None
            else:
                decisions_ok = decisions_ok and decision["action"] == "guess" and \
                    outcome["guess"] == decision["guess"] and outcome["feedback"] in {"rank", "invalid"}
                matches = False
                expected = outcome["rank"] if outcome["feedback"] == "rank" else "invalid"
                for observed in (e for e in events if e["event"] == "browser_feedback" and
                                 e.get("turn") == outcome["turn"] and e.get("submitted_word") == outcome["guess"]):
                    try:
                        matches = matches or classify_feedback(observed["observed"], allow_duplicate=True) == expected
                    except (ValueError, RuntimeError, KeyError):
                        continue
                decisions_ok = decisions_ok and matches
                seen.add(outcome["guess"])
            history.append({"kind": "guess", "action": outcome["turn"], "guess_number": outcome["guess_number"],
                            "guess": outcome["guess"], "feedback": outcome["feedback"], "rank": outcome.get("rank")})
        check(label + "parsing, hint eligibility and feedback match saved answers and browser evidence", decisions_ok)
        check(label + "fresh browser and complete evidence", any(
            e["event"] == "browser_ready" and e.get("fresh_game") and e.get("requested_date") == game["date"]
            for e in events) and not any(e["event"] == "artifact_error" for e in events))
        hint_ok = True
        for event in delivered:
            observed_hints = [e for e in events if e["event"] == "browser_hint" and e.get("turn") == event["turn"] and
                              (e["observed"]["word"], e["observed"]["rank"]) == (event["word"], event["rank"])]
            files = [v for v in (event.get("evidence") or {}).values()]
            hint_ok = hint_ok and bool(observed_hints) and event.get("settings") == expected_settings and bool(files) \
                and all((Path(v) if Path(v).is_absolute() else path / v).exists() for v in files)
        starts_settings = [e for e in events if e["event"] == "hint_settings" and e.get("stage") == "start"]
        check(label + "actual hint evidence, settings and files", hint_ok and bool(starts_settings) and
              all(e["settings"] == expected_settings for e in starts_settings))
        valid_requests = True
        for event in (e for e in events if e["event"] == "request"):
            prior = [e for e in state["history"] if e["action"] < event["turn"]]
            expected_request = {"model": manifest["model"],
                                "input": build_hint_prompt(prior, manifest["hint_instructions"], manifest["max_guesses"]),
                                "generation_config": manifest["settings"], "tools": [], "store": False}
            valid_requests = valid_requests and event["request"] == expected_request
        check(label + "exact isolated full-history prompts", valid_requests)
        reserved = {e["reservation"]: e for e in ledger.reservations if e["owner"] == game["id"]}
        returned = [e for e in ledger.records if e["event"] == "request_returned" and e["reservation"] in reserved]
        action_returns = [e for e in returned if reserved[e["reservation"]]["kind"].endswith("_action")]
        action_requests = [e for e in reserved.values() if e["kind"].endswith("_action")]
        local_requests = [e for e in events if e["event"] == "request"]
        check(label + "action requests match durable reservations", len(action_requests) == len(local_requests) and
              all(any(r["step"] == e["turn"] and r["request"] == e["request"] for r in action_requests)
                  for e in local_requests))
        check(label + "returned answers match journal", len(action_returns) == len(responses) and all(
            any(reserved[r["reservation"]]["step"] == e["turn"] and
                digest(r["raw_response"]) == digest(e["raw_response"]) for r in action_returns) for e in responses))
        csv_file = path / "turns.csv"
        with csv_file.open(encoding="utf-8", newline="") if csv_file.exists() else open(os.devnull) as stream:
            csv_rows = list(csv.DictReader(stream))
        check(label + "CSV count matches responses", len(csv_rows) == len(responses))
        report = report_events(path)
        report_requests = [e for e in report if e["event"] == "report_request"]
        report_answers = [e for e in report if e["event"] == "report_response"]
        report_returned = [e for e in returned if reserved[e["reservation"]]["kind"].endswith("_report")]
        expected_report = {"model": manifest["model"], "input": report_input(manifest, game, events),
                           "generation_config": manifest["report_settings"], "tools": [], "store": False}
        check(label + "separate strategy report", report_complete(path) and bool(report_requests) and
              all(e["request"] == expected_report for e in report_requests) and
              len(report_returned) == len(report_answers) == 1 and
              digest(report_returned[0]["raw_response"]) == digest(report_answers[0]["raw_response"]))
        marker_file = directory / "checks" / f"{phase}_{game['date']}.json"
        marker = json.loads(marker_file.read_text(encoding="utf-8")) if marker_file.exists() else {}
        archived_file = base / manifest["baseline"]["checks"][f"{phase}_{game['date']}"]["path"]
        archived = json.loads(archived_file.read_text(encoding="utf-8"))
        check(label + "archived controls replayed and sentinels match before and after",
              marker.get("passed") and not marker.get("baseline_replay_differences") and
              marker.get("before") == archived.get("before") and marker.get("after") == archived.get("after") and
              marker.get("ranks_consistent"))
    check("request reservation IDs unique", len({e["reservation"] for e in ledger.reservations}) ==
          len(ledger.reservations))
    known = {g["id"]: g for g in manifest["games"] + manifest["pilot_games"]}
    check("all journal entries belong to scheduled request slots", all(
        e["owner"] in known and e["kind"] in {known[e["owner"]]["phase"] + "_action",
                                              known[e["owner"]]["phase"] + "_report"} and
        1 <= e["step"] <= (manifest["max_guesses"] + 1 if e["kind"].endswith("_action") else 1)
        for e in ledger.reservations))
    check("configured model preflight recorded", (directory / "model_preflight.json").exists())
    for kind, cap in manifest["limits"].items():
        check(kind + " budget", sum(e["kind"] == kind and not e["retry"] for e in ledger.reservations) <= cap)
    check("transport-retry budget", ledger.retry_count <= manifest["retry_reserve"])
    check("overall request ceiling", len(ledger.reservations) <= manifest["maximum_requests"])
    result = {"passed": all(e["passed"] for e in checks), "phase": phase, "checks": checks,
              "manifest_fingerprint": manifest["fingerprint"], "event_log_sha256": hashes,
              "requests_reserved": len(ledger.reservations), "retry_requests": ledger.retry_count,
              "timestamp": now()}
    prefix = "PILOT_AUDIT" if phase == "pilot" else "AUDIT"
    write_json(directory / (prefix + ".json"), result)
    failed = [e["check"] for e in checks if not e["passed"]]
    (directory / (prefix + ".md")).write_text(
        f"# {phase.title()} verification (hint follow-up)\n\n"
        f"Status: **{'PASS' if result['passed'] else 'INCOMPLETE / CHECK REQUIRED'}**.\n\n"
        f"Requests reserved: {len(ledger.reservations)}/{manifest['maximum_requests']}; "
        f"retries: {ledger.retry_count}/{manifest['retry_reserve']}.\n\n" +
        "\n".join("- " + name for name in failed) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Freeze the follow-up; offline, no model or browser")
    prep.add_argument("--output", type=Path)
    prep.add_argument("--baseline", type=Path, default=BASELINE)
    for name in ("probe", "pilot", "run", "recover", "summarize", "audit"):
        command = sub.add_parser(name)
        command.add_argument("batch", type=Path)
        if name == "recover":
            command.add_argument("--game", required=True)
            command.add_argument("--resolve-ambiguous-hint", action="store_true")
        if name == "audit":
            command.add_argument("--phase", choices=("pilot", "production"), default="production")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.output, args.baseline))
            return 0
        if args.command == "probe":
            report = probe(args.batch)
            print(json.dumps({k: v for k, v in report.items() if k != "dates"}, indent=2))
            return 0 if report["passed"] else 1
        if args.command in {"pilot", "run"}:
            return execute(args.batch, "pilot" if args.command == "pilot" else "production")
        if args.command == "recover":
            print(json.dumps(recover(args.batch, args.game, args.resolve_ambiguous_hint)))
            return 0
        with BatchLock(args.batch):
            if args.command == "audit":
                result = audit(args.batch, args.phase)
                print(json.dumps({k: v for k, v in result.items() if k not in {"checks", "event_log_sha256"}}))
                return 0 if result["passed"] else 1
            result = analysis.summarize(args.batch, load_manifest(args.batch))
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
