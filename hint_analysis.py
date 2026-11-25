"""Hint follow-up analysis: new hint-enabled games against archived control games.

Standard library only. Hint words never enter a model trajectory, and a direct
answer reveal is never a model solve.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
from datetime import datetime
from statistics import mean, median

from evaluation_metrics import game_metrics, read_events
from study_analysis import trajectory as archived_trajectory, write_csv

SEED = 20261123
BUDGET = 30
SUCCESS, REVEAL, LIMIT = "success", "answer_revealed_by_hint", "guess_limit"


def game_path(directory, game):
    return Path(directory) / game["phase"] / game["date"] / "hint"


def hint_events(events):
    return [e for e in events if e["event"] == "hint_delivered"]


def is_hint_word_repeat(entry, hints):
    """A guess of the supplied hint word, made after the hint arrived, earns no credit."""
    return any(entry["guess"] == h["word"] and entry["turn"] > h["turn"] for h in hints)


def model_ranks(events):
    """Ranked guesses made by the model itself, in order. Never includes the hint."""
    hints = hint_events(events)
    return [e for e in events if e["event"] == "feedback" and e["feedback"] == "rank"
            and not is_hint_word_repeat(e, hints)]


def trajectory(events, budget=None):
    """Best model-generated rank after each guess attempt; None before the first ranked guess."""
    start = next((e for e in events if e["event"] == "start"), {})
    budget = budget or start.get("max_guesses") or BUDGET
    ranked = model_ranks(events)
    values, best = [], None
    for number in range(1, budget + 1):
        for entry in ranked:
            if entry["guess_number"] == number:
                best = entry["rank"] if best is None else min(best, entry["rank"])
        values.append(best)
    return values


def game_record(events):
    start = next((e for e in events if e["event"] == "start"), {})
    end = next((e for e in reversed(events) if e["event"] == "termination"), {})
    feedback = [e for e in events if e["event"] == "feedback"]
    responses = [e for e in events if e["event"] == "response"]
    hints = hint_events(events)
    ranked = model_ranks(events)
    budget = start.get("max_guesses") or BUDGET
    status = end.get("reason", "incomplete")
    solved = any(e["rank"] == 1 for e in ranked)
    revealed = bool(hints) and any(h["rank"] == 1 for h in hints)
    attempts = len(feedback)
    complete = (len(responses) == len(feedback) + len(hints) and
                ((status == SUCCESS and solved) or
                 (status == REVEAL and revealed and not solved) or
                 (status == LIMIT and not solved and not revealed and attempts == budget)))
    best = min(ranked, key=lambda e: e["rank"], default=None)
    ineligible = sum(e["feedback"] == "ineligible_hint" for e in feedback)
    return {"puzzle": start.get("puzzle"), "status": status, "complete": complete,
            "solved": solved, "revealed": revealed, "attempts": attempts,
            "actions": len(responses), "max_guesses": budget,
            "invalid_attempts": sum(e["feedback"] != "rank" for e in feedback) +
            sum(e["feedback"] == "rank" and is_hint_word_repeat(e, hints) for e in feedback),
            "ineligible_hint_requests": ineligible,
            "hint_delivered": len(hints), "hint_requests": len(hints) + ineligible,
            "hint_after_guess": hints[0]["after_guess"] if hints else None,
            "hint_action": hints[0]["turn"] if hints else None,
            "best_rank": best["rank"] if best else None,
            "best_word": best["guess"] if best else None,
            "guesses_to_solve": next((e["guess_number"] for e in ranked if e["rank"] == 1), None)}


def request_seconds(events):
    """Seconds between each journaled request and its returned response."""
    sent = {e["turn"]: e["timestamp"] for e in events if e["event"] == "request"}
    values = []
    for event in events:
        if event["event"] == "response" and event["turn"] in sent:
            delta = (datetime.fromisoformat(event["timestamp"]) -
                     datetime.fromisoformat(sent[event["turn"]])).total_seconds()
            values.append(max(0.0, delta))
    return values


def score_target(new, controls):
    """Mean over controls and attempts: win 1, tie 0.5, loss 0. Missing rank is infinity."""
    scores = []
    for control in controls:
        for mine, theirs in zip(new, control, strict=True):
            mine = math.inf if mine is None else mine
            theirs = math.inf if theirs is None else theirs
            scores.append(1.0 if mine < theirs else .5 if mine == theirs else 0.0)
    return mean(scores)


def select_targets(games):
    """Keep targets with a completed new game and all three verified baseline games."""
    included, excluded = {}, {}
    for target, item in sorted(games.items()):
        reasons = list(item.get("reasons", []))
        if len(item.get("controls", [])) != 3:
            reasons.append("fewer than three verified baseline games")
        if item.get("new") is None and "new game incomplete" not in reasons:
            reasons.append("new game incomplete")
        if reasons:
            excluded[target] = reasons
        else:
            included[target] = {"new": item["new"], "controls": item["controls"]}
    return included, excluded


def compare(targets, samples=10000, seed=SEED):
    scores = {t: score_target(v["new"], v["controls"]) for t, v in sorted(targets.items())}
    values = list(scores.values())
    rng = random.Random(seed)
    draws = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples)) if values else []
    return {"targets": len(values), "score": mean(values) if values else None,
            "ci95": [draws[int(.025 * (samples - 1))], draws[int(.975 * (samples - 1))]] if draws else None,
            "target_scores": scores, "bootstrap_samples": samples, "seed": seed,
            "interpretation": "Above 0.5 favours the hint-enabled game; compared with archived "
                              "controls, so exploratory and not a clean causal estimate."}


def outcome_summary(records):
    complete = [r for r in records if r["complete"]]
    n = len(complete)
    ranks = sorted(math.inf if r["best_rank"] is None else r["best_rank"] for r in complete)
    middle = median(ranks) if ranks else None
    def rate(count):
        return count / n if n else None
    def top(limit):
        return rate(sum(r["best_rank"] is not None and r["best_rank"] <= limit for r in complete))
    return {"games": n, "solved": sum(r["solved"] for r in complete),
            "revealed": sum(bool(r.get("revealed")) for r in complete),
            "solve_rate": rate(sum(r["solved"] for r in complete)),
            "median_best_rank": None if middle is None or math.isinf(middle) else middle,
            "top10_rate": top(10), "top50_rate": top(50), "top100_rate": top(100),
            "invalid_attempts": sum(r["invalid_attempts"] for r in complete),
            "games_with_invalid_attempts": sum(r["invalid_attempts"] > 0 for r in complete)}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline_games(directory, manifest, target, phase="production"):
    """Archived control games for one date. Each is verified against the frozen hashes."""
    base = Path(manifest["baseline"]["directory"])
    games, problems = [], []
    for identifier, expected in manifest["baseline"]["control_games"].items():
        if expected["phase"] != phase or expected["date"] != target:
            continue
        file = base / expected["path"]
        if not file.exists() or sha256_file(file) != expected["sha256"]:
            problems.append(f"baseline file changed or missing: {identifier}")
            continue
        events = read_events(file)
        metric = game_metrics(events)
        if not metric["complete"]:
            problems.append(f"baseline game incomplete: {identifier}")
            continue
        games.append({"id": identifier, "metric": metric,
                      "trajectory": archived_trajectory(events, manifest["max_guesses"])})
    return games, problems


def percentile_text(value):
    return "n/a" if value is None else f"{value:.1%}"


def summarize(directory, manifest, phase="production"):
    directory = Path(directory)
    rows, curves, reports, targets_input = [], [], [], {}
    baseline_records, latencies, hint_gaps = [], [], []
    games = manifest["games"] if phase == "production" else manifest["pilot_games"]
    for game in games:
        path = game_path(directory, game)
        control, problems = baseline_games(directory, manifest, game["date"], phase)
        marker = directory / "checks" / f"{phase}_{game['date']}.json"
        state = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        reasons = list(problems)
        if not (path / "events.jsonl").exists():
            targets_input[game["date"]] = {"new": None, "controls": control,
                                           "reasons": reasons + ["new game not started"]}
            continue
        events = read_events(path / "events.jsonl")
        record = game_record(events)
        times = request_seconds(events)
        latencies.extend(times)
        report_file = path / "strategy_report.jsonl"
        usable = False
        if report_file.exists():
            for event in read_events(report_file):
                if event["event"] == "report_response":
                    usable = usable or event["usable"]
                    reports.append({"id": game["id"], "date": game["date"], "hint_delivered": record["hint_delivered"],
                                    "text": event["text"], "usable": event["usable"]})
        usage = [e["raw_response"].get("usage") or {} for e in events if e["event"] == "response"]
        rows.append({"id": game["id"], "date": game["date"], **{k: record[k] for k in (
            "status", "complete", "solved", "revealed", "attempts", "actions", "invalid_attempts",
            "ineligible_hint_requests", "hint_delivered", "hint_requests", "hint_after_guess",
            "hint_action", "best_rank", "best_word", "guesses_to_solve")},
            "report_usable": usable,
            "total_tokens": sum(u.get("total_tokens", 0) or 0 for u in usage),
            "mean_response_seconds": mean(times) if times else None,
            "total_response_seconds": sum(times) if times else None})
        values = trajectory(events, manifest["max_guesses"])
        observed = max((e["guess_number"] for e in events if e["event"] == "feedback"), default=0)
        curves.extend({"id": game["id"], "puzzle": game["date"], "attempt": i, "best_rank": value,
                       "complete": record["complete"]}
                      for i, value in enumerate(values, 1) if record["complete"] or i <= observed)
        if record["hint_after_guess"] is not None:
            hint_gaps.append(record["hint_after_guess"])
        if not record["complete"]:
            reasons.append("new game incomplete")
        if not state.get("passed"):
            reasons.append("target consistency checks not passed")
        targets_input[game["date"]] = {"new": values if record["complete"] else None,
                                       "controls": [c["trajectory"] for c in control], "reasons": reasons}
        baseline_records.append({"date": game["date"], "controls": [c["metric"] for c in control],
                                 "record": record, "included": not reasons})
    included, excluded = select_targets(targets_input)
    comparison = compare(included)
    chosen_new = [b["record"] for b in baseline_records if b["date"] in included]
    chosen_control = [m for b in baseline_records if b["date"] in included for m in b["controls"]]
    new_summary, control_summary = outcome_summary(chosen_new), outcome_summary(chosen_control)
    complete_all = [r for r in (b["record"] for b in baseline_records) if r["complete"]]
    users = [r for r in complete_all if r["hint_delivered"]]
    others = [r for r in complete_all if not r["hint_delivered"]]
    difference = (new_summary["solve_rate"] - control_summary["solve_rate"]
                  if new_summary["solve_rate"] is not None and control_summary["solve_rate"] is not None else None)
    result = {"phase": phase, "planned": len(games), "started": len(rows),
              "completed": sum(r["complete"] for r in rows), "reports": sum(r["usable"] for r in reports),
              "comparison": comparison, "included_targets": sorted(included), "excluded_targets": excluded,
              "new_games": new_summary, "matched_baseline": control_summary,
              "solve_rate_difference": difference,
              "all_completed_hint_games": outcome_summary(complete_all),
              "hint": {"delivered": sum(r["hint_delivered"] for r in complete_all),
                       "never_requested": sum(not r["hint_delivered"] and not r["hint_requests"] for r in complete_all),
                       "ineligible_requests": sum(r["ineligible_hint_requests"] for r in complete_all),
                       "answer_revealed": sum(r["revealed"] for r in complete_all),
                       "median_guess_before_hint": median(hint_gaps) if hint_gaps else None,
                       "descriptive_users": outcome_summary(users),
                       "descriptive_non_users": outcome_summary(others),
                       "note": "Requesting help is self-selected; user/non-user comparisons are descriptive."},
              "request_timing_seconds": {"requests": len(latencies),
                                         "mean": mean(latencies) if latencies else None,
                                         "median": median(latencies) if latencies else None,
                                         "total": sum(latencies)},
              "games": rows}
    if phase == "production":
        (directory / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        write_csv(directory / "results.csv", rows)
        write_csv(directory / "trajectories.csv", curves)
        write_csv(directory / "strategy_reports.csv", reports)
        write_csv(directory / "target_scores.csv", [{"puzzle": k, "hint_score": v}
                                                   for k, v in comparison["target_scores"].items()])
        (directory / "README.md").write_text(readme(result), encoding="utf-8")
    return result


def readme(result):
    new, base, comparison = result["new_games"], result["matched_baseline"], result["comparison"]
    hint = result["hint"]
    def row(name, summary):
        return (f"| {name} | {summary['games']} | {summary['solved']} | {percentile_text(summary['solve_rate'])} | "
                f"{summary['median_best_rank']} | {percentile_text(summary['top10_rate'])} | "
                f"{percentile_text(summary['top50_rate'])} | {percentile_text(summary['top100_rate'])} | "
                f"{summary['invalid_attempts']} |")
    lines = ["# Contexto optional-hint follow-up", "",
             f"Completed **{result['completed']}/{result['planned']}** hint-enabled games; usable strategy reports: "
             f"{result['reports']}. Comparison targets: {comparison['targets']}.", "",
             "Exploratory comparison with archived control games (not contemporaneous controls).", "",
             "| Group | Games | Solved | Solve rate | Median best rank | Top 10 | Top 50 | Top 100 | Invalid attempts |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
             row("hint-enabled (new)", new), row("archived control (matched)", base), "",
             f"Paired ordinal trajectory score: **{comparison['score']}**, 95% whole-target bootstrap interval "
             f"{comparison['ci95']} ({comparison['bootstrap_samples']} samples, seed {comparison['seed']}). "
             "Above 0.5 favours the hint-enabled game.", "",
             f"Hints delivered: {hint['delivered']}; never requested: {hint['never_requested']}; ineligible "
             f"requests: {hint['ineligible_requests']}; answers revealed by hint (not counted as solves): "
             f"{hint['answer_revealed']}.", "",
             "Excluded targets: " + (json.dumps(result["excluded_targets"]) if result["excluded_targets"] else "none"), "",
             "Successful replay checks cannot rule out every website or model-backend change, and one new "
             "repetition per target limits precision. Hint users and non-users are self-selected; compare "
             "them descriptively only. Postgame reports are self-report, not internal reasoning.", ""]
    return "\n".join(lines)
