"""Exploratory, offline analyses of why the optional hint helped (no model or website calls).

1. Gap by attempt: when the hint-enabled games pull ahead of the archived controls.
2. Anchor comparison: control games that found a rank <= 300 word themselves vs hint games,
   over the same number of guesses after that anchor.
3. Hint follow-up: what the model did with the hint word in the next guesses.

Usage: python hint_mechanism.py [hint_run_dir]
"""
from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent
HINT_RUN = ROOT / "runs" / "20261123T175122Z_hint_study_a22ab6a8"
BASELINE = ROOT / "runs" / "20261120T213300Z_instruction_study_5625ddd2"
MAX_GUESSES = 30
ANCHOR_RANK = 300          # Easy hints are capped at 300, so this is the comparable threshold.
WINDOWS = (10, 15)         # guesses after the anchor
FOLLOW = 5                 # guesses inspected after the hint


def events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def trajectories(path, condition=None):
    games = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if condition and row.get("condition") != condition:
                continue
            rank = None if row["best_rank"] in ("", "None") else int(row["best_rank"])
            games.setdefault(row["id"], {"puzzle": row["puzzle"], "ranks": {}})["ranks"][int(row["attempt"])] = rank
    return games


def at(game, attempt):
    return game["ranks"].get(attempt)


def compare(a, b):
    a = float("inf") if a is None else a
    b = float("inf") if b is None else b
    return 1.0 if a < b else 0.5 if a == b else 0.0


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def gap_by_attempt(hint, control):
    by_target = {}
    for game in control.values():
        by_target.setdefault(game["puzzle"], []).append(game)
    rows = []
    for t in range(1, MAX_GUESSES + 1):
        scores = [statistics.mean(compare(at(h, t), at(c, t)) for c in by_target[h["puzzle"]])
                  for h in hint.values()]
        rows.append({"attempt": t, "paired_score": round(statistics.mean(scores), 4),
                     "median_best_hint": median(at(g, t) for g in hint.values()),
                     "median_best_control": median(at(g, t) for g in control.values())})
    return rows


def hint_games(run):
    games = []
    for path in sorted((run / "production").glob("*/hint/events.jsonl")):
        ev = events(path)
        hint = next(e for e in ev if e["event"] == "browser_hint")["observed"]
        dispatch = next(e for e in ev if e["event"] == "hint_dispatch")
        ranked = [(e["guess_number"], e["guess"], e["rank"]) for e in ev
                  if e["event"] == "feedback" and e["feedback"] == "rank" and e["guess"] != hint["word"]]
        summaries = {e["turn"]: e.get("text", "") for e in ev if e["event"] == "thought_summary"}
        report = path.parent / "strategy_report.jsonl"
        report_text = " ".join(e.get("text", "") for e in events(report) if e["event"] == "report_response") \
            if report.exists() else ""
        games.append({"date": path.parent.parent.name, "anchor_guess": dispatch["after_guess"],
                      "anchor_rank": hint["rank"], "hint_word": hint["word"], "ranked": ranked,
                      "next_summary": summaries.get(dispatch["turn"] + 1, ""), "report": report_text})
    return games


def control_games(run):
    games = []
    for path in sorted((run / "production").glob("*/control/*/events.jsonl")):
        ev = events(path)
        ranked = [(e["turn"], e["guess"], e["rank"]) for e in ev
                  if e["event"] == "feedback" and e["feedback"] == "rank"]
        anchor = next(((n, r) for n, _, r in ranked if r <= ANCHOR_RANK), None)
        games.append({"date": path.parent.parent.parent.name, "repeat": path.parent.name,
                      "anchor_guess": anchor[0] if anchor else None,
                      "anchor_rank": anchor[1] if anchor else None, "ranked": ranked})
    return games


def window(game, size):
    """Best model rank in the `size` guesses after the anchor, or None when too few remain."""
    start = game["anchor_guess"]
    if start is None or start + size > MAX_GUESSES:
        return None
    ranks = [r for n, _, r in game["ranked"] if start < n <= start + size]
    best = min(ranks) if ranks else None
    beat = next((n - start for n, _, r in game["ranked"] if n > start and r < game["anchor_rank"]), None)
    return {"best": best, "solved": best == 1, "beat_anchor_after": beat}


def anchor_rows(hint, control):
    rows = []
    for group, games in (("hint", hint), ("control", control)):
        for g in games:
            row = {"group": group, "date": g["date"], "repeat": g.get("repeat", ""),
                   "anchor_guess": g["anchor_guess"], "anchor_rank": g["anchor_rank"]}
            for size in WINDOWS:
                w = window(g, size)
                row[f"best_in_{size}"] = w["best"] if w else ""
                row[f"solved_in_{size}"] = w["solved"] if w else ""
            w = window(g, MAX_GUESSES - (g["anchor_guess"] or MAX_GUESSES))
            row["guesses_to_beat_anchor"] = w["beat_anchor_after"] if w and w["beat_anchor_after"] else ""
            rows.append(row)
    return rows


def summarise_anchor(rows, group, size, low=0):
    chosen = [r for r in rows if r["group"] == group and r[f"best_in_{size}"] != ""
              and r["anchor_rank"] is not None and r["anchor_rank"] >= low]
    if not chosen:
        return {"games": 0}
    return {"games": len(chosen),
            "median_anchor_guess": median(r["anchor_guess"] for r in chosen),
            "median_anchor_rank": median(r["anchor_rank"] for r in chosen),
            "median_best": median(r[f"best_in_{size}"] for r in chosen),
            "solved": sum(r[f"solved_in_{size}"] is True for r in chosen),
            "top10": sum(r[f"best_in_{size}"] <= 10 for r in chosen)}


def followup_rows(hint):
    rows = []
    for g in hint:
        nxt = [(n, w, r) for n, w, r in g["ranked"] if n > g["anchor_guess"]][:FOLLOW]
        word = g["hint_word"].lower()
        rows.append({"date": g["date"], "hint_word": g["hint_word"], "hint_rank": g["anchor_rank"],
                     "after_guess": g["anchor_guess"],
                     "next_guesses": " ".join(f"{w}({r})" for _, w, r in nxt),
                     "next_within_hint_rank": sum(r <= g["anchor_rank"] for _, _, r in nxt),
                     "next_count": len(nxt),
                     "summary_mentions_hint": word in g["next_summary"].lower(),
                     "report_mentions_hint": word in g["report"].lower()})
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    return "-" if value is None else (f"{value:g}" if isinstance(value, float) else str(value))


def main(run=HINT_RUN):
    out = run / "mechanism"
    out.mkdir(exist_ok=True)
    gap = gap_by_attempt(trajectories(run / "trajectories.csv"),
                         trajectories(BASELINE / "trajectories.csv", "control"))
    hint, control = hint_games(run), control_games(BASELINE)
    anchors, follow = anchor_rows(hint, control), followup_rows(hint)
    write_csv(out / "gap_by_attempt.csv", gap)
    write_csv(out / "anchor_comparison.csv", anchors)
    write_csv(out / "hint_followup.csv", follow)

    lines = ["# Why the hint helped: exploratory offline analyses", "",
             f"Hint run: `{run.name}`; archived controls: `{BASELINE.name}` (75 control games).",
             "No model or website requests. Descriptive only; thresholds were chosen after seeing the main result.",
             "", "## 1. When the gap opens", "",
             "| Attempt | Paired score | Median best (hint) | Median best (control) |",
             "| ---: | ---: | ---: | ---: |"]
    for row in gap:
        if row["attempt"] in (1, 2, 3, 5, 10, 15, 20, 25, 30):
            lines.append(f"| {row['attempt']} | {row['paired_score']:.3f} | {fmt(row['median_best_hint'])} "
                         f"| {fmt(row['median_best_control'])} |")
    openers = {name: Counter(g["ranked"][0][1] for g in games if g["ranked"])
               for name, games in (("hint", hint), ("control", control))}
    lines += ["", "Opening guess (before any hint): "
              + "; ".join(f"{name}: " + ", ".join(f"{w} {n}" for w, n in c.most_common(4))
                          for name, c in openers.items())
              + ". The hint paragraph changed the opener, so the attempt-1 lead is not hint information."]
    reached = sum(r["anchor_rank"] is not None for r in anchors if r["group"] == "control")
    lines += ["", "## 2. Hint anchor vs a self-found anchor (rank <= 300)", "",
              f"Control games that found a rank <= {ANCHOR_RANK} word themselves: {reached}/75. "
              "Outcome = best model rank in the next N guesses after the anchor (games with fewer than N "
              "guesses left are dropped).", "",
              "| Window | Group | Anchor ranks | Games | Median anchor guess | Median anchor rank "
              "| Median best in window | Solved | Top 10 |",
              "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for size in WINDOWS:
        for low, label in ((0, "all"), (100, "100-300")):
            for group in ("hint", "control"):
                s = summarise_anchor(anchors, group, size, low)
                if s["games"]:
                    lines.append(f"| {size} | {group} | {label} | {s['games']} | {fmt(s['median_anchor_guess'])} "
                                 f"| {fmt(s['median_anchor_rank'])} | {fmt(s['median_best'])} "
                                 f"| {s['solved']} | {s['top10']} |")
                else:
                    lines.append(f"| {size} | {group} | {label} | 0 | - | - | - | - | - |")
    beat = {g: [r["guesses_to_beat_anchor"] for r in anchors if r["group"] == g and r["guesses_to_beat_anchor"] != ""]
            for g in ("hint", "control")}
    lines += ["", "Guesses needed to beat the anchor rank (games that did): "
              f"hint median {fmt(median(beat['hint']))} ({len(beat['hint'])}/25), "
              f"control median {fmt(median(beat['control']))} ({len(beat['control'])}/{reached}).",
              "", "## 3. What the model did with the hint word", "",
              f"Next {FOLLOW} guesses after the hint; how many ranked at or better than the hint rank.", "",
              "| Date | Hint (rank) | After guess | Next guesses (rank) | <= hint rank | Thought summary names hint | Report names hint |",
              "| --- | --- | ---: | --- | ---: | :---: | :---: |"]
    for r in follow:
        lines.append(f"| {r['date']} | {r['hint_word']} ({r['hint_rank']}) | {r['after_guess']} | {r['next_guesses']} "
                     f"| {r['next_within_hint_rank']}/{r['next_count']} | {'yes' if r['summary_mentions_hint'] else 'no'} "
                     f"| {'yes' if r['report_mentions_hint'] else 'no'} |")
    within = sum(r["next_within_hint_rank"] for r in follow)
    total = sum(r["next_count"] for r in follow)
    lines += ["", f"Overall: {within}/{total} follow-up guesses ranked at or better than the hint; "
              f"thought summary names the hint word in {sum(r['summary_mentions_hint'] for r in follow)}/25 games; "
              f"strategy report names it in {sum(r['report_mentions_hint'] for r in follow)}/25.",
              "", "Limitations: archived controls were run three days earlier; anchors differ in timing and in who "
              "found them; thought summaries and reports are partial self-reports, and an empty summary does not "
              "mean the hint was ignored."]
    (out / "MECHANISM.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HINT_RUN)
