"""Verify a finished evaluation against its frozen schedule and per-turn records."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

from evaluation_metrics import aggregate, game_metrics, read_events
from gemini_trial import build_prompt


def audit(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    checks, metrics, all_ids, cutoffs = [], [], [], []
    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
    dates = manifest["puzzle_dates"]
    check("Puzzle dates are unique", len(dates) == len(set(dates)))
    for puzzle in dates:
        prefix = f"{puzzle}: "
        path = directory / puzzle / "events.jsonl"
        if not path.exists():
            check(prefix + "game completed", False)
            continue
        events = read_events(path)
        metric = game_metrics(events)
        metrics.append(metric)
        check(prefix + "game completed", metric["complete"])
        starts = [e for e in events if e["event"] == "start"]
        check(prefix + "one original game start", len(starts) == 1)
        if not starts:
            continue
        start = starts[0]
        check(prefix + "model, settings, budget and protocol match",
              start["model"] == manifest["model"] and start["puzzle"] == puzzle and
              start["generation_config"] == manifest["settings"] and
              start["max_guesses"] == manifest["max_guesses"] and
              start.get("evaluation") and start.get("memory_mode") == "explicit")
        requests = [e for e in events if e["event"] == "request"]
        responses = [e for e in events if e["event"] == "response"]
        feedback = [e for e in events if e["event"] == "feedback" and e["feedback"] != "quit"]
        if metric["complete"]:
            first30 = [e for e in feedback if e["turn"] <= 30 and e["feedback"] == "rank"]
            cutoffs.append({"puzzle": puzzle, "solved_by_30": any(e["rank"] == 1 for e in first30),
                            "best_rank_by_30": min((e["rank"] for e in first30), default=None),
                            "solved_by_70": metric["solved"], "best_rank_by_70": metric["best_rank"],
                            "attempts": metric["attempts"]})
        turns = [e["turn"] for e in responses]
        errors = [e for e in events if e["event"] == "api_error"]
        check(prefix + "one completed response per attempt; extra requests match transport errors",
              Counter(e["turn"] for e in requests) == Counter(turns) + Counter(e["turn"] for e in errors) and
              len(turns) == len(set(turns)) and turns == list(range(1, len(turns) + 1)))
        check(prefix + "one classified feedback per response",
              [e["turn"] for e in feedback] == turns)
        check(prefix + "attempt limit respected", len(responses) <= manifest["max_guesses"])
        valid_requests = True
        for event in requests:
            request = event["request"]
            history = [{key: f.get(key) for key in ("turn", "guess", "feedback", "rank")}
                       for f in feedback if f["turn"] < event["turn"]]
            valid_requests = valid_requests and (
                request["input"] == build_prompt(history, "explicit", True, manifest["max_guesses"]) and
                request["store"] is False and "previous_interaction_id" not in request and
                request["tools"] == [] and request["generation_config"] == manifest["settings"] and
                request["model"] == manifest["model"])
        check(prefix + "every prompt contains exact full history; no linked context or tools", valid_requests)
        check(prefix + "at least one verified fresh browser start", any(
            e["event"] == "browser_ready" and e.get("fresh_game") and
            e.get("requested_date") == puzzle for e in events))
        check(prefix + "all browser snapshots saved", not any(e["event"] == "artifact_error" for e in events))
        csv_path = path.parent / "turns.csv"
        import csv
        rows = []
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
        check(prefix + "CSV has one row per model response", len(rows) == len(responses))
        all_ids.extend(e["raw_response"].get("id") for e in responses)
    totals = aggregate(metrics)
    check("All planned games completed", totals["completed"] == len(dates))
    total_requests = sum(e["event"] == "request" for puzzle in dates
                         if (directory / puzzle / "events.jsonl").exists()
                         for e in read_events(directory / puzzle / "events.jsonl"))
    check("Original total model-request cap respected", total_requests <= manifest["maximum_model_requests"])
    normalized_ids = [identifier for identifier in all_ids if identifier]
    duplicate_ids = [identifier for identifier, count in Counter(normalized_ids).items() if count > 1]
    result = {"passed": all(c["passed"] for c in checks), "checks": checks,
              "completed": totals["completed"], "planned": len(dates),
              "model_responses": len(all_ids), "nonempty_provider_ids": len(normalized_ids),
              "model_requests": total_requests, "transport_requests_without_response": total_requests - len(all_ids),
              "duplicate_nonempty_provider_ids": duplicate_ids,
              "event_log_sha256": {puzzle: hashlib.sha256(
                  (directory / puzzle / "events.jsonl").read_bytes()).hexdigest()
                  for puzzle in dates if (directory / puzzle / "events.jsonl").exists()}}
    check_ids = not duplicate_ids
    result["passed"] = result["passed"] and check_ids
    (directory / "AUDIT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    failures = [c["check"] for c in checks if not c["passed"]]
    lines = ["# Evaluation verification", "",
             f"Status: **{'PASS' if result['passed'] else 'INCOMPLETE / CHECK REQUIRED'}**.",
             f"Completed {totals['completed']}/{len(dates)} games; {len(all_ids)} saved model responses.", "",
             f"Model requests: {total_requests}; requests without a returned response: "
             f"{total_requests - len(all_ids)}. Original total cap: {manifest['maximum_model_requests']}.", "",
             "Checked the frozen dates, model/settings, total attempt budgets, unique local turn "
             "sequences, one completed response/feedback per attempt, extra requests reconciled "
             "with recorded transport errors, exact full-history prompts, "
             "fresh browser starts, absence of model tools/linked context, CSV counts and snapshot errors.", "",
             "Controller corrections remain in the event logs and execution amendments. Browser "
             "history replays do not add model requests or attempts.", "",
             f"Nonempty provider IDs: {len(normalized_ids)}/{len(all_ids)}. "
             f"Duplicate nonempty IDs: {len(duplicate_ids)}. "
             "When IDs are missing, provider-side uniqueness cannot be independently verified; "
             "the local request/response sequence remains available.", "",
             "[Machine-readable checks and final event-log hashes](AUDIT.json).", ""]
    if failures:
        lines.extend(["Failed or incomplete checks:", "", *[f"- {item}" for item in failures], ""])
    (directory / "AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    cutoff_lines = ["# Outcomes at 30 and 70 attempts", "",
                    f"Completed games: {len(cutoffs)}/{len(dates)}. "
                    f"Solved by 30: {sum(g['solved_by_30'] for g in cutoffs)}; "
                    f"solved by 70: {sum(g['solved_by_70'] for g in cutoffs)}.", "",
                    "| Puzzle | Best rank by 30 | Best rank by 70 | Attempts used |",
                    "| --- | ---: | ---: | ---: |"]
    cutoff_lines.extend(f"| {g['puzzle']} | {g['best_rank_by_30']} | {g['best_rank_by_70']} | "
                        f"{g['attempts']} |" for g in cutoffs)
    cutoff_lines.extend(["", "This is a retrospective cutoff within the same 70-attempt games. "
                         "The model was told it had 70 attempts from the start. It is not a "
                         "separate randomized comparison of 30- versus 70-attempt instructions.", ""])
    (directory / "BUDGET_COMPARISON.md").write_text("\n".join(cutoff_lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    result = audit(args.batch)
    print(json.dumps({k: result[k] for k in ("passed", "completed", "planned", "model_responses")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
