"""Manual Contexto feedback loop. SDK imports are lazy for offline testing."""
from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from uuid import uuid4

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_MAX_GUESSES = 70
MEMORY_MODES = ("explicit", "linked")
SETTINGS = {"temperature": 0.6, "thinking_level": "low",
            "max_output_tokens": 4096, "thinking_summaries": "auto"}
INSTRUCTIONS = (
    "Play a semantic hidden-word guessing game in English. After each guess, "
    "you receive its rank: lower is closer, and rank 1 identifies the target. "
    "Use previous guesses and ranks to choose your next word. Do not repeat "
    "guesses. Return exactly one English word, letters only, in your final "
    "answer. Do not give an initial strategy. You have no external tools."
)
CSV_FIELDS = ["turn", "guess", "rank", "feedback", "interaction_id",
              "response_timestamp", "feedback_timestamp", "thought_summary",
              "summary_present", "usage", "termination_reason"]


def now():
    return datetime.now(timezone.utc).isoformat()


def parse_guess(text):
    word = text.strip()
    if not re.fullmatch(r"[A-Za-z]+", word):
        raise ValueError("Expected exactly one word containing English letters only.")
    return word.lower()


def parse_feedback(text):
    value = text.strip().lower()
    if value in {"invalid", "quit"}:
        return value
    if re.fullmatch(r"[0-9]+", value) and int(value) > 0:
        return int(value)
    raise ValueError('Enter a positive integer rank, "invalid", or "quit".')


def unpack_response(raw):
    """Read final text and thought summaries independently, never as guesses."""
    answers, summaries = [], []
    for step in raw.get("steps", []):
        if step.get("type") == "model_output":
            answers.extend(block.get("text", "") for block in step.get("content", [])
                           if block.get("type") == "text")
        elif step.get("type") == "thought":
            summaries.extend(block.get("text", "") for block in step.get("summary") or []
                             if block.get("type") == "text")
    return "\n".join(answers), "\n".join(summaries)


def feedback_text(entry):
    return {"invalid": "rejected as invalid by Contexto",
            "duplicate": "duplicate guess; attempt consumed, no score",
            "invalid_output": "invalid model output; attempt consumed, no score"}.get(
                entry["feedback"], f"rank {entry.get('rank')}")


def build_prompt(history, memory_mode="explicit", evaluation=False, max_guesses=70,
                 instructions=None):
    """Build the explicit history or the latest feedback for linked memory."""
    if memory_mode == "linked" and history:
        entry = history[-1]
        result = feedback_text(entry)
        return (f"Submitted guess: {entry['guess']}. Feedback: {result}. "
                "Lower ranks are closer; rank 1 is the target. "
                "Choose your next guess. Return exactly one English word.")
    lines = [INSTRUCTIONS if instructions is None else instructions]
    if evaluation:
        lines.append(f"You have at most {max_guesses} attempts. Invalid and repeated "
                     "guesses consume an attempt and receive no score.")
    order = "newest first" if evaluation else "oldest first"
    lines.extend(["", f"Complete submitted guess history ({order}):"])
    for entry in reversed(history) if evaluation else history:
        result = feedback_text(entry)
        lines.append(f"Turn {entry['turn']}: {entry['guess']} -> {result}")
    if not history:
        lines.append("No guesses submitted yet.")
    lines.extend(["", "Choose your next guess. Return exactly one English word."
                  if history else "Choose your first guess. Return exactly one English word."])
    return "\n".join(lines)


class GameLog:
    def __init__(self, directory, secret=""):
        directory.mkdir(parents=True, exist_ok=False)
        self.path = directory / "events.jsonl"
        self.csv_path = directory / "turns.csv"
        self.secret = secret

    def write(self, event, **fields):
        record = {"event": event, "timestamp": now(), **fields}
        text = json.dumps(record, ensure_ascii=False)
        if self.secret:
            text = text.replace(self.secret, "[REDACTED]")
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def export(self, csv_export=True):
        # Rebuild from authoritative events, including responses without feedback.
        rows, reason, events = {}, "", []
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                events.append(event)
                turn = event.get("turn")
                if event["event"] == "response":
                    raw = event["raw_response"]
                    answer, summary = unpack_response(raw)
                    rows[turn] = {"turn": turn, "guess": answer.strip(),
                                  "interaction_id": raw.get("id", ""),
                                  "response_timestamp": event["timestamp"],
                                  "thought_summary": summary,
                                  "summary_present": bool(summary),
                                  "usage": json.dumps(raw.get("usage"))}
                elif event["event"] == "feedback":
                    rows[turn].update(guess=event["guess"], rank=event.get("rank", ""),
                                      feedback=event["feedback"],
                                      feedback_timestamp=event["timestamp"])
                elif event["event"] == "termination":
                    reason = event["reason"]
        self.export_timeline(events, reason)
        if not csv_export:
            return
        with self.csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows.values():
                row["termination_reason"] = reason
                # Avoid spreadsheet formula evaluation of malformed model output.
                row = {key: ("'" + value if isinstance(value, str) and
                              value.startswith(("=", "+", "-", "@")) else value)
                       for key, value in row.items()}
                writer.writerow(row)

    def export_timeline(self, events, reason):
        """Show locally observed history and summaries, without inventing thoughts."""
        start = next((event for event in events if event["event"] == "start"), {})
        lines = ["# Contexto game timeline", "",
                 f"Puzzle: {start.get('puzzle', 'unknown')}",
                 f"Model: {start.get('model', 'unknown')}",
                 f"Memory: {start.get('memory_mode', start.get('context_mode', 'not recorded'))}",
                 f"Status: {reason or 'in progress (snapshot)'}", "",
                 "Thought summaries are generated summaries returned by Gemini, not "
                 "full internal reasoning. Local history below records observed guesses "
                 "and feedback, not Google's hidden context or thought signatures.", "",
                 "## Initial instructions", "", start.get("instructions", "Not recorded."), ""]
        history = []
        for event in events:
            kind = event["event"]
            if kind == "request":
                request = event["request"]
                lines.extend([f"## Turn {event['turn']}", "",
                              "### Prior submitted guesses", ""])
                snapshot = event.get("observed_guess_history", history)
                lines.extend([f"- Turn {entry['turn']}: {entry['guess']} — "
                              + feedback_text(entry) for entry in snapshot]
                             or ["No prior submitted guesses."])
                mode = ("Previous interaction: " + str(request["previous_interaction_id"])
                        if request.get("previous_interaction_id") else
                        "Context: explicitly supplied local history (stateless request)"
                        if request.get("store") is False else
                        "Previous interaction: none (fresh game)")
                lines.extend(["", "### New input sent to Gemini", "", request["input"], "",
                              mode, ""])
            elif kind == "response":
                answer, summary = unpack_response(event["raw_response"])
                lines.extend(["### Returned thought summary", "",
                              summary or "No thought summary returned.", "",
                              "### Model answer", "", answer or "No final answer returned.", ""])
            elif kind == "feedback":
                feedback = event["feedback"]
                result = f"rank {event['rank']}" if feedback == "rank" else feedback
                label = ("### Controller feedback (no website submission)"
                         if feedback in {"duplicate", "invalid_output"} else
                         "### Website feedback read by the browser"
                         if start.get("feedback_source") == "browser" else
                         "### Website feedback entered by the operator")
                lines.extend([label, "", result, ""])
                if feedback != "quit":
                    history.append({"turn": event["turn"], "guess": event["guess"],
                                    "feedback": feedback, "rank": event.get("rank")})
            elif kind in {"api_error", "output_error", "browser_error"}:
                lines.extend(["### Error", "", event["message"], ""])
        (self.path.parent / "timeline.md").write_text("\n".join(lines), encoding="utf-8")


def run_game(client, log, model, puzzle, max_guesses=DEFAULT_MAX_GUESSES, read=input, show=print,
             get_feedback=None, memory_mode="explicit", evaluation=False, resume=False,
             instructions=None, condition="no_initial_plan"):
    if memory_mode not in MEMORY_MODES:
        raise ValueError(f"Unknown memory mode: {memory_mode}")
    if evaluation and memory_mode != "explicit":
        raise ValueError("The evaluation protocol requires explicit full history.")
    if max_guesses < 1:
        raise ValueError("max_guesses must be positive")
    instructions = INSTRUCTIONS if instructions is None else instructions
    linked = memory_mode == "linked"
    previous_id = None
    seen = set()
    history = []
    submitted = 0
    attempts_used = 0
    reason = "guess_limit"
    first_turn = 1
    pending_response = None
    if resume:
        if not evaluation or linked:
            raise ValueError("Only stateless evaluation games can be resumed.")
        events = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
        start = next(e for e in events if e["event"] == "start")
        if (start["model"] != model or start["puzzle"] != puzzle or
                start["max_guesses"] != max_guesses or not start.get("evaluation") or
                start["generation_config"] != SETTINGS or
                start.get("instructions", INSTRUCTIONS) != instructions or
                start.get("condition", "no_initial_plan") != condition):
            raise ValueError("Resume configuration must match the original evaluation.")
        history = [{key: e.get(key) for key in ("turn", "guess", "feedback", "rank")}
                   for e in events if e["event"] == "feedback" and e["feedback"] != "quit"]
        responses = [e for e in events if e["event"] == "response"]
        if [e["turn"] for e in responses] != [e["turn"] for e in history]:
            if (len(responses) == len(history) + 1 and
                    [e["turn"] for e in responses[:-1]] == [e["turn"] for e in history]):
                pending_response = responses[-1]["raw_response"]
            else:
                raise ValueError("Response and feedback histories do not align for resume.")
        if any(e["rank"] == 1 for e in history):
            raise ValueError("Cannot resume an already solved game.")
        seen = {e["guess"] for e in history if e["feedback"] in {"rank", "invalid"}}
        submitted = sum(e["feedback"] in {"rank", "invalid"} for e in history)
        attempts_used = len(responses)
        first_turn = len(history) + 1
        failed_requests = [e for e in events if e["event"] == "api_error" and e["turn"] == first_turn]
        log.write("resume", next_turn=first_turn, previous_attempts=attempts_used,
                  pending_response_turn=first_turn if pending_response else None,
                  model_requests_repeated=int(bool(failed_requests)),
                  previous_transport_failures=len(failed_requests))
    else:
        log.write("start", puzzle=puzzle, language="English", model=model,
              generation_config=SETTINGS, max_guesses=max_guesses,
              instructions=instructions, condition=condition,
              context_mode="previous_interaction_id" if linked else "explicit_guess_history",
              memory_mode=memory_mode, interaction_storage=linked,
              evaluation=evaluation,
              history_order="newest_first" if evaluation else "oldest_first",
              output_parser="final_whitespace_token_letters_only" if evaluation else "strict_one_word",
              invalid_policy="consume_attempt" if evaluation else "stop_on_output_error",
              feedback_source="browser" if get_feedback else "operator",
              sdk_version=sdk_version(), tools=[], automatic_retries=False)
    try:
        for turn in range(first_turn, max_guesses + 1):
            request = {"model": model, "input": build_prompt(history, memory_mode,
                                                            evaluation, max_guesses, instructions),
                       "generation_config": dict(SETTINGS), "tools": [], "store": linked}
            if linked and previous_id:
                request["previous_interaction_id"] = previous_id
            if pending_response is not None:
                raw, pending_response = pending_response, None
                log.write("reuse_saved_response", turn=turn, new_model_requests=0)
            else:
                log.write("request", turn=turn, request=request, observed_guess_history=history)
                try:
                    response = client.interactions.create(**request)
                    raw = response.model_dump(mode="json", exclude_none=True)
                except Exception as error:
                    log.write("api_error", turn=turn, error_type=type(error).__name__,
                              message=str(error))
                    show("API request failed; see the log. No automatic retry was made.")
                    reason = "api_error"
                    break
                log.write("response", turn=turn, raw_response=raw)
                attempts_used += 1
            answer, summary = unpack_response(raw)
            log.write("thought_summary", turn=turn, text=summary, present=bool(summary))
            log.export(csv_export=False)
            guess = ""
            try:
                if raw.get("status") != "completed":
                    raise ValueError("Interaction is not completed.")
                if linked and not raw.get("id"):
                    raise ValueError("Linked memory requires a returned interaction ID.")
                guess = parse_guess(answer.split()[-1] if evaluation and answer.split() else answer)
                if guess in seen:
                    raise ValueError("Model repeated an earlier guess.")
            except ValueError as error:
                log.write("output_error", turn=turn, message=str(error))
                if evaluation:
                    kind = "duplicate" if guess in seen else "invalid_output"
                    entry = {"turn": turn, "guess": guess or "[invalid output]",
                             "feedback": kind, "rank": None}
                    log.write("feedback", **entry)
                    history.append(entry)
                    log.export(csv_export=False)
                    show(f"Turn {turn}: {kind}; attempt consumed.")
                    continue
                show(f"Stopped before submission: {error}")
                reason = "invalid_model_output"
                break
            if linked:
                previous_id = raw["id"]
            show(f"\nTurn {turn}\nModel guess: {guess}")
            if get_feedback:
                try:
                    feedback = parse_feedback(str(get_feedback(guess, turn)))
                    show(f"Contexto feedback: {feedback}")
                except Exception as error:
                    log.write("browser_error", turn=turn, error_type=type(error).__name__,
                              message=str(error))
                    show(f"Browser feedback failed: {error}")
                    reason = "browser_error"
                    break
            else:
                show("Enter this word on Contexto, then enter its rank here.")
                while True:
                    try:
                        feedback = parse_feedback(read('Rank, "invalid", or "quit": '))
                        break
                    except ValueError as error:
                        show(str(error))
            if feedback == "quit":
                log.write("feedback", turn=turn, guess=guess, feedback="quit")
                reason = "quit"
                break
            submitted += 1
            seen.add(guess)
            log.write("feedback", turn=turn, guess=guess,
                      feedback="invalid" if feedback == "invalid" else "rank",
                      rank=feedback if isinstance(feedback, int) else None)
            history.append({"turn": turn, "guess": guess,
                            "feedback": "invalid" if feedback == "invalid" else "rank",
                            "rank": feedback if isinstance(feedback, int) else None})
            log.export(csv_export=False)
            if feedback == 1:
                reason = "success"
                break
    except (KeyboardInterrupt, EOFError):
        reason = "interrupted"
    finally:
        log.write("termination", reason=reason, submitted_guesses=submitted,
                  attempts_used=attempts_used,
                  success=reason == "success")
        log.export()
    show(f"\nStopped: {reason}. Submitted guesses: {submitted}.")
    show(f"Records: {log.path.parent}")
    return reason


def sdk_version():
    try:
        return importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        return "not installed (offline test)"


def create_client(key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key, vertexai=False, http_options=types.HttpOptions(
        timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)))
    # SDK 2.28.0 maps attempts=0/1 to one retry in Interactions. Its generated
    # transport supports an explicit "none" strategy; verify this in transport tests.
    client.interactions.sdk_configuration.retry_config.strategy = "none"
    return client


def read_api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.strip() == "GEMINI_API_KEY":
                key = value.strip()
                if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
                    key = key[1:-1]
                return key.strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--memory", choices=MEMORY_MODES, default="explicit",
                        help="explicit: send all guesses/ranks; linked: use previous_interaction_id")
    parser.add_argument("--puzzle", help="Contexto puzzle identifier")
    parser.add_argument("--max-guesses", type=int, default=DEFAULT_MAX_GUESSES)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parent / "runs")
    parser.add_argument("--export", type=Path,
                        help="Rebuild turns.csv from a previous run directory, without API calls")
    args = parser.parse_args()
    if args.export:
        log = object.__new__(GameLog)
        log.path = args.export / "events.jsonl"
        log.csv_path = args.export / "turns.csv"
        log.export()
        print(log.csv_path)
        return 0
    if args.max_guesses < 1:
        parser.error("--max-guesses must be positive")
    key = read_api_key()
    if not key:
        parser.error("Set GEMINI_API_KEY in the .env next to this script or your environment (see README.md).")
    try:
        client = create_client(key)
    except ImportError:
        parser.error("Install the Conda environment from environment.yml first.")
    try:
        puzzle = args.puzzle or input("Contexto puzzle identifier: ").strip()
        if not puzzle.strip():
            parser.error("Puzzle identifier cannot be empty")
        directory = args.output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                       + "_" + uuid4().hex[:8])
        reason = run_game(client, GameLog(directory, key), args.model, puzzle, args.max_guesses,
                          memory_mode=args.memory)
        return 1 if reason in {"api_error", "invalid_model_output", "interrupted"} else 0
    except (KeyboardInterrupt, EOFError):
        print("Cancelled before the game started.")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
