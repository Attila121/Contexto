"""Outcome and trajectory measures from authoritative Contexto event logs."""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean


def read_events(path):
    events = []
    lines = Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # A different game worker may still be appending its final record.
            if index == len(lines) - 1 and not line.endswith("\n"):
                break
            raise
    return events


def game_metrics(events, vocabulary_size=None):
    start = next((e for e in events if e["event"] == "start"), {})
    end = next((e for e in reversed(events) if e["event"] == "termination"), {})
    feedback = [e for e in events if e["event"] == "feedback" and e["feedback"] != "quit"]
    responses = [e for e in events if e["event"] == "response"]
    ranked = [e for e in feedback if e["feedback"] == "rank"]
    best = min(ranked, key=lambda e: e["rank"], default=None)
    solved = any(e["rank"] == 1 for e in ranked)
    status = end.get("reason", "incomplete")
    budget = start.get("max_guesses")
    # A transport error, interruption or missing feedback is never a completed loss.
    complete = (len(responses) == len(feedback) and
                ((status == "success" and solved) or
                 (status == "guess_limit" and not solved and len(feedback) == budget)))
    if vocabulary_size is not None:
        if vocabulary_size <= 1 or any(e["rank"] > vocabulary_size for e in ranked):
            raise ValueError("Vocabulary size must exceed 1 and contain all observed ranks.")
    previous_rank = None
    progression, weighted = [], []
    for index, entry in enumerate(feedback):
        rank = entry.get("rank") if entry["feedback"] == "rank" else None
        improved = rank is not None and previous_rank is not None and rank < previous_rank
        # First attempt has no preceding guess. Later invalid attempts score zero;
        # the following valid guess compares with the last valid rank (paper footnote 5).
        if index:
            progression.append(int(improved))
            if vocabulary_size is not None:
                weighted.append(math.exp(-math.log(rank) / math.log(vocabulary_size))
                                if improved else 0.0)
        if rank is not None:
            previous_rank = rank
    return {
        "puzzle": start.get("puzzle"), "model": start.get("model"),
        "status": status, "complete": complete, "solved": solved,
        "max_guesses": budget, "attempts": len(responses),
        "scored_guesses": len(ranked),
        "invalid_attempts": sum(e["feedback"] != "rank" for e in feedback),
        "best_word": best["guess"] if best else None,
        "best_rank": best["rank"] if best else None,
        "best_rank_turn": best["turn"] if best else None,
        "guesses_to_solve": next((e["turn"] for e in ranked if e["rank"] == 1), None),
        "mean_progression": mean(progression) if progression else None,
        "weighted_progression": mean(weighted) if weighted else None,
        "proximity_unsolved": (1 - math.log(best["rank"]) / math.log(vocabulary_size)
                               if best and not solved and vocabulary_size else None),
    }


def aggregate(games):
    complete = [g for g in games if g["complete"]]
    solved = [g for g in complete if g["solved"]]
    progress = [g["mean_progression"] for g in complete if g["mean_progression"] is not None]
    return {"completed": len(complete), "solved": len(solved),
            "solve_rate": len(solved) / len(complete) if complete else None,
            "average_guesses_solved": mean(g["guesses_to_solve"] for g in solved) if solved else None,
            "mean_progression": mean(progress) if progress else None}
