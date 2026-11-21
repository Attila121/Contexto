"""Ordinal target-paired trajectory analysis, using only the standard library."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import random
from statistics import mean

from evaluation_metrics import game_metrics, read_events

SEED = 20261120


def trajectory(events, budget=30):
    feedback = {e["turn"]: e for e in events if e["event"] == "feedback"}
    best, values = None, []
    for turn in range(1, budget + 1):
        entry = feedback.get(turn, {})
        if entry.get("feedback") == "rank":
            best = min(best or math.inf, entry["rank"])
        values.append(best)
    return values


def paired_analysis(groups, repeats=3, samples=10000):
    scores = {}
    for target, conditions in sorted(groups.items()):
        control, guided = conditions.get("control", []), conditions.get("guided", [])
        if len(control) != repeats or len(guided) != repeats:
            continue
        comparisons = []
        for c in control:
            for g in guided:
                for cv, gv in zip(c, g, strict=True):
                    cv, gv = cv if cv is not None else math.inf, gv if gv is not None else math.inf
                    comparisons.append(1.0 if gv < cv else .5 if gv == cv else 0.0)
        scores[target] = mean(comparisons)
    values = list(scores.values())
    rng = random.Random(SEED)
    draws = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples)) if values else []
    return {"targets": len(values), "score": mean(values) if values else None,
            "ci95": [draws[int(.025 * (samples - 1))], draws[int(.975 * (samples - 1))]] if draws else None,
            "target_scores": scores, "bootstrap_samples": samples, "seed": SEED,
            "interpretation": "Above 0.5 favors guided; exploratory, resampling whole targets."}


def write_csv(path, rows, fields=None):
    if not rows and fields is None:
        return
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                             else v for k, v in row.items()})


def summarize(directory, manifest):
    directory = Path(directory)
    rows, curves, groups, reports, all_groups = [], [], {}, [], {}
    for game in manifest["games"]:
        path = directory / "production" / game["date"] / game["condition"] / f"repeat_{game['repetition']:02d}"
        if not (path / "events.jsonl").exists():
            continue
        events = read_events(path / "events.jsonl")
        metric = game_metrics(events)
        request_times = {e["turn"]: e["timestamp"] for e in events if e["event"] == "request"}
        response_events = [e for e in events if e["event"] == "response"]
        usage = [e["raw_response"].get("usage") or {} for e in response_events]
        from datetime import datetime
        latency = [max(0, (datetime.fromisoformat(e["timestamp"]) -
                            datetime.fromisoformat(request_times[e["turn"]])).total_seconds())
                   for e in response_events if e["turn"] in request_times]
        rows.append({"id": game["id"], "condition": game["condition"], "repetition": game["repetition"],
                     **metric, "total_tokens": sum(u.get("total_tokens", 0) or 0 for u in usage),
                     "mean_response_seconds": mean(latency) if latency else None})
        values = trajectory(events, manifest["max_guesses"])
        # Incomplete trajectories must not be silently carried forward to turn 30.
        observed = max((e["turn"] for e in events if e["event"] == "feedback"), default=0)
        curves.extend({"id": game["id"], "puzzle": game["date"], "condition": game["condition"],
                       "repetition": game["repetition"], "attempt": i, "best_rank": value,
                       "complete": metric["complete"]}
                      for i, value in enumerate(values, 1) if metric["complete"] or i <= observed)
        if metric["complete"]:
            groups.setdefault(game["date"], {}).setdefault(game["condition"], []).append(values)
        all_groups.setdefault(game["date"], []).append(game["id"])
        report_path = path / "strategy_report.jsonl"
        if report_path.exists():
            for event in read_events(report_path):
                if event["event"] == "report_response":
                    reports.append({"id": game["id"], "condition": game["condition"],
                                    "text": event["text"], "usable": event["usable"]})
    result = {"planned": len(manifest["games"]), "started": len(rows),
              "completed": sum(r["complete"] for r in rows), "reports": sum(r["usable"] for r in reports),
              "paired": paired_analysis(groups), "conditions": {}, "games": rows}
    for condition in ("control", "guided"):
        complete = [r for r in rows if r["condition"] == condition and r["complete"]]
        solved = [r for r in complete if r["solved"]]
        result["conditions"][condition] = {
            "completed": len(complete), "planned": 75,
            "solved": len(solved), "solve_rate": len(solved) / len(complete) if complete else None,
            "mean_attempts_solved": mean(r["guesses_to_solve"] for r in solved) if solved else None,
            "invalid_attempts": sum(r["invalid_attempts"] for r in complete)}
    (directory / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_csv(directory / "results.csv", rows)
    write_csv(directory / "trajectories.csv", curves)
    write_csv(directory / "strategy_reports.csv", reports)
    write_csv(directory / "target_scores.csv", [{"puzzle": k, "guided_score": v}
              for k, v in result["paired"]["target_scores"].items()])
    lines = ["# Contexto instruction study", "",
             f"Completed **{result['completed']}/150** production games; usable strategy reports: {result['reports']}.",
             "25 targets, two conditions, three repetitions, 30 attempts. Earlier runs are not pooled.", "",
             "| Condition | Completed | Solved | Solve rate |", "| --- | ---: | ---: | ---: |"]
    for c, item in result["conditions"].items():
        rate = f"{item['solve_rate']:.1%}" if item["solve_rate"] is not None else "pending"
        lines.append(f"| {c} | {item['completed']}/75 | {item['solved']} | {rate} |")
    lines.extend(["", "## Paired ordinal trajectory comparison", "",
                  json.dumps(result["paired"], indent=2), "",
                  "Only targets with all six games completed enter this comparison. Missing initial ranks "
                  "compare as infinity; invalid attempts retain the best rank; solved games retain rank 1.",
                  "The confidence interval resamples targets, not individual repetitions. These are "
                  "exploratory results on 25 dates, nine previously used in the 70-attempt pilot.", "",
                  "Live scoring is not frozen. Sentinel checks detect some changes but do not prove stability.",
                  "See manifest.json, requests.jsonl, checks/, trajectories.csv and per-game records.",
                  "Returned thought summaries and postgame self-reports are not full internal reasoning.", ""])
    (directory / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return result
