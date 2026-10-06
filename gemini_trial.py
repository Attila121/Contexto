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


def build_prompt(history, memory_mode="explicit"):
    """Build the explicit history or the latest feedback for linked memory."""
    if memory_mode == "linked" and history:
        entry = history[-1]
        result = ("rejected as invalid by Contexto" if entry["feedback"] == "invalid"
                  else f"rank {entry['rank']}")
        return (f"Submitted guess: {entry['guess']}. Feedback: {result}. "
                "Lower ranks are closer; rank 1 is the target. "
                "Choose your next guess. Return exactly one English word.")
    lines = [INSTRUCTIONS, "", "Complete submitted guess history (oldest first):"]
    for entry in history:
        result = ("rejected as invalid by Contexto" if entry["feedback"] == "invalid"
                  else f"rank {entry['rank']}")
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
                              + ("invalid" if entry['feedback'] == "invalid"
                                 else f"rank {entry['rank']}") for entry in snapshot]
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
                label = ("### Website feedback read by the browser"
                         if start.get("feedback_source") == "browser" else
                         "### Website feedback entered by the operator")
                lines.extend([label, "", result, ""])
                if feedback != "quit":
                    history.append({"turn": event["turn"], "guess": event["guess"],
                                    "feedback": feedback, "rank": event.get("rank")})
            elif kind in {"api_error", "output_error", "browser_error"}:
                lines.extend(["### Error", "", event["message"], ""])
        (self.path.parent / "timeline.md").write_text("\n".join(lines), encoding="utf-8")


def run_game(client, log, model, puzzle, max_guesses=30, read=input, show=print,
             get_feedback=None, memory_mode="explicit"):
    if memory_mode not in MEMORY_MODES:
        raise ValueError(f"Unknown memory mode: {memory_mode}")
    linked = memory_mode == "linked"
    previous_id = None
    seen = set()
    history = []
    submitted = 0
    reason = "guess_limit"
    log.write("start", puzzle=puzzle, language="English", model=model,
              generation_config=SETTINGS, max_guesses=max_guesses,
              instructions=INSTRUCTIONS, condition="no_initial_plan",
              context_mode="previous_interaction_id" if linked else "explicit_guess_history",
              memory_mode=memory_mode, interaction_storage=linked,
              feedback_source="browser" if get_feedback else "operator",
              sdk_version=sdk_version(), tools=[], automatic_retries=False)
    try:
        for turn in range(1, max_guesses + 1):
            request = {"model": model, "input": build_prompt(history, memory_mode),
                       "generation_config": dict(SETTINGS), "tools": [], "store": linked}
            if linked and previous_id:
                request["previous_interaction_id"] = previous_id
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
            answer, summary = unpack_response(raw)
            log.write("thought_summary", turn=turn, text=summary, present=bool(summary))
            log.export(csv_export=False)
            try:
                if raw.get("status") != "completed":
                    raise ValueError("Interaction is not completed.")
                if linked and not raw.get("id"):
                    raise ValueError("Linked memory requires a returned interaction ID.")
                guess = parse_guess(answer)
                if guess in seen:
                    raise ValueError("Model repeated an earlier guess.")
            except ValueError as error:
                log.write("output_error", turn=turn, message=str(error))
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
    parser.add_argument("--max-guesses", type=int, default=30)
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
