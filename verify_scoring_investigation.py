"""Offline review of preserved Contexto scoring evidence; no API/model calls."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, median


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def review(evidence, study, vector_cache=None):
    import numpy as np
    from scipy.stats import spearmanr

    evidence, study = Path(evidence), Path(study)
    output = evidence / "review"
    output.mkdir(exist_ok=True)
    preservation = read_json(evidence / "PRESERVATION.json")
    hashes_valid = all(digest(evidence / f["path"]) == f["sha256"] for f in preservation["files"])
    if not hashes_valid:
        raise ValueError("A preserved source differs from its import hash.")
    events_by_date, ranked, invalid, invalid_kinds = {}, [], Counter(), Counter()
    trial_hashes = {}
    for path in sorted(study.glob("*/events.jsonl")):
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        day = path.parent.name
        events_by_date[day] = events
        trial_hashes[day] = digest(path)
        for event in events:
            if event["event"] != "feedback" or event["feedback"] == "quit":
                continue
            kind = event["feedback"]
            if kind == "rank":
                ranked.append((day, event["guess"], event["rank"]))
                continue
            invalid_kinds[kind] += 1
            if kind == "invalid_output":
                invalid["malformed_or_empty"] += 1
                continue
            observed = [e.get("observed", {}) for e in events
                        if e["event"] == "browser_feedback" and e["turn"] == event["turn"]]
            last = observed[-1] if observed else {}
            if kind == "duplicate" or last.get("repeated"):
                invalid["duplicate"] += 1
            elif "too common" in last.get("message", "").lower():
                invalid["too_common"] += 1
            elif "doesn't count" in last.get("message", "").lower():
                invalid["other_rejected"] += 1
            else:
                invalid["unclassified"] += 1
    stored = read_json(evidence / "api/counterfactual.json")
    original_audit = read_json(study / "AUDIT.json")
    if original_audit["event_log_sha256"] != trial_hashes:
        raise ValueError("Original trial logs differ from their completed-study audit hashes.")
    rows = stored["rows"]
    if Counter(ranked) != Counter((r["date"], r["word"], r["ctx"]) for r in rows):
        raise ValueError("Counterfactual rows do not match the original accepted trial guesses.")
    paired = [r for r in rows if r["paper"] is not None]
    grouped = defaultdict(list)
    for row in paired:
        grouped[row["date"]].append(row)
    transitions, disagreements = 0, 0
    for values in grouped.values():
        for previous, current in zip(values, values[1:]):
            transitions += 1
            disagreements += ((current["ctx"] < previous["ctx"]) !=
                              (current["paper"] < previous["paper"]))
    fixed_sequence_targets = {}
    for day, values in grouped.items():
        fixed_sequence_targets[day] = {
            "target": values[0]["target"],
            "contexto_hit": any(r["ctx"] == 1 for r in values),
            "exact_token_hit": any(r["word"] == r["target"] for r in values),
        }
    replay = read_json(evidence / "api/replay.json")
    replay_counts = defaultdict(lambda: Counter())
    for row in replay:
        # Recompute matches from raw payload rather than trusting the stored flag.
        match = row["live"].get("distance", -99) + 1 == row["rec_rank"]
        replay_counts[row["rec_date"]]["matched" if match else "changed"] += 1
    vocabulary = read_json(evidence / "api/vocab_probe.json")
    ranks_seen = [(r["resp"]["distance"] + 1, r["word"])
                  for r in vocabulary["res"] if r["status"] == 200 and "distance" in r["resp"]]
    ranks_seen.extend((distance + 1, key) for key, distance in vocabulary["multi"].items())
    candidates = []
    for path in sorted((evidence / "api").glob("cand_*.json")):
        candidates.extend(row for row in read_json(path)
                          if row["era"] == "live 2026" and row["forms"] == "inflections"
                          and row["metric"] == "cos")
    singleton = read_json(evidence / "api/singleton_glove.6B.300d_needed.json")
    exact_old = [row for row in singleton["old"] if row["disc_cos"] == 0]
    credit_checks = []
    for filename in ("20220928230730_main.318224d4.js", "20260228231225_main.27ee7aa2.js",
                     "20260311234956_main.e7748afa.js"):
        path = evidence / "wayback/bundles" / filename
        raw = path.read_bytes()
        decoded = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
        credit_checks.append({"file": filename,
                              "stanford_glove_link": b"nlp.stanford.edu/projects/glove" in decoded,
                              "bytes_decoded": len(decoded)})
    archived = read_json(evidence / "api/arch_tops.json")
    live = read_json(evidence / "api/live_for_arch.json")
    key = next(k for k in sorted(archived) if k.endswith("|107"))
    old_list, new_list = archived[key], live["107"]
    positions = {word: index for index, word in enumerate(new_list)}
    common = [word for word in old_list if word in positions]
    inversions = sum(positions[a] > positions[b] for i, a in enumerate(common) for b in common[i+1:])
    result = {
        "preserved_source_files_verified": len(preservation["files"]),
        "preserved_source_bytes": preservation["copied_bytes"],
        "trial_log_sha256": trial_hashes,
        "trial_hashes_match_original_completed_audit": True,
        "ranked_responses": len(ranked), "invalid_counts": dict(invalid),
        "invalid_feedback_kinds": dict(invalid_kinds),
        "model_outputs": len(ranked) + sum(invalid.values()),
        "counterfactual_rows_match_original_trials": True,
        "spearman_contexto_vs_candidate": float(spearmanr(
            [r["ctx"] for r in paired], [r["paper"] for r in paired]).statistic),
        "transitions": transitions, "direction_disagreements": disagreements,
        "direction_disagreement_fraction": disagreements / transitions,
        "median_candidate_to_contexto_rank_ratio": median(r["paper"] / r["ctx"] for r in paired),
        "fixed_sequence_targets": fixed_sequence_targets,
        "limited_example": [r for r in rows if r["date"] == "2026-10-31" and r["word"] == "limited"],
        "replay_counts": {key: dict(value) for key, value in replay_counts.items()},
        "highest_observed_displayed_rank": max(ranks_seen),
        "candidate_model_comparisons": candidates,
        "early_restricted_tests": {
            "lists": len(singleton["old"]), "perfect_lists": len(exact_old),
            "perfect_list_pairs": sum(r["pairs"] for r in exact_old),
            "all_lists_discordant_pairs": sum(r["disc_cos"] for r in singleton["old"]),
            "all_lists_pairs": sum(r["pairs"] for r in singleton["old"]),
            "mean_kendall_tau": mean(r["cos"] for r in singleton["old"]),
            "limitation": "WordNet/simple-inflection exclusion is not a verified model of server normalization."},
        "archived_credit_checks": credit_checks,
        "archived_vs_live_game107": {"archive_key": key, "common_words": len(common),
                                     "inverted_pairs": inversions},
        "proximity_formula_checks": {str(c): {str(r): 1 - math.log(r) / math.log(c)
                                             for r in (10, 100, 1000)} for c in (317756, 79000)},
        "caveats": ["Original records are not regraded or modified.",
                    "Fixed-trajectory rescoring does not estimate how the model would play with new feedback.",
                    "Matched examples identify a plausible reconstruction, not all undocumented paper details.",
                    "A finite candidate comparison does not identify or exhaust possible live models."]}
    if vector_cache is not None:
        with np.load(vector_cache, allow_pickle=False) as cache:
            words = cache["words"]
            matrix = cache["M"]
        mask = np.array([bool(re.fullmatch(r"[a-z]+", str(word))) for word in words])
        tokens = words[mask]
        normalized = matrix[mask].astype(np.float32)
        del matrix, words
        normalized /= np.linalg.norm(normalized, axis=1, keepdims=True)
        position = {str(word): index for index, word in enumerate(tokens)}
        rank_tables = {}
        targets = sorted({r["target"] for r in rows} | {"mirror", "banana"})
        for target in targets:
            similarities = normalized @ normalized[position[target]]
            order = np.argsort(-similarities)
            ranks = np.empty(len(tokens), dtype=np.uint32)
            ranks[order] = np.arange(1, len(tokens) + 1, dtype=np.uint32)
            rank_tables[target] = ranks
        mismatches = [{**r, "recomputed": int(rank_tables[r["target"]][position[r["word"]]])}
                      for r in rows if r["word"] in position and
                      int(rank_tables[r["target"]][position[r["word"]]]) != r["paper"]]
        figure = {"look": 15, "vision": 34, "eye": 43, "smile": 206,
                  "happiness": 916, "emotion": 3575, "animal": 10867}
        figure_results = {word: {"reported": rank, "recomputed": int(rank_tables["mirror"][position[word]])}
                          for word, rank in figure.items()}
        rejection_checks = []
        for day, events in events_by_date.items():
            target = fixed_sequence_targets[day]["target"]
            seen = set()
            for event in events:
                if event["event"] != "feedback" or event["feedback"] == "quit":
                    continue
                word = event["guess"].lower()
                if event["feedback"] != "rank":
                    rejection_checks.append({
                        "date": day, "turn": event["turn"], "word": word,
                        "original_feedback": event["feedback"],
                        "in_candidate_vocabulary": word in position,
                        "exact_token_already_seen": word in seen,
                        "candidate_rank": int(rank_tables[target][position[word]]) if word in position else None})
                seen.add(word)
        demo = read_json(evidence / "api/wp_vs_ctx_banana.json")
        demo_results = [{"word": r["word"], "reported": r["wordpolo"][1]["rank"],
                         "recomputed": int(rank_tables["banana"][position[r["word"]]])}
                        for r in demo if isinstance(r["wordpolo"][1], dict) and
                        "rank" in r["wordpolo"][1] and r["word"] in position]
        np.savez_compressed(output / "candidate_rank_tables.npz", words=tokens,
                            **{"rank_" + target: values for target, values in rank_tables.items()})
        result["independent_vector_checks"] = {
            "input": str(Path(vector_cache).resolve()), "sha256": digest(vector_cache),
            "numpy": np.__version__, "vocabulary": len(tokens), "dimensions": normalized.shape[1],
            "cached_rank_mismatches": mismatches,
            "figure2": figure_results, "demo": demo_results,
            "figure_matches": sum(r["reported"] == r["recomputed"] for r in figure_results.values()),
            "demo_matches": sum(r["reported"] == r["recomputed"] for r in demo_results),
            "rank_table_file": "review/candidate_rank_tables.npz",
            "rank_table_sha256": digest(output / "candidate_rank_tables.npz"),
            "rejection_checks": rejection_checks,
            "rejected_words_valid_as_new_candidate_tokens": sum(
                r["in_candidate_vocabulary"] and not r["exact_token_already_seen"]
                for r in rejection_checks)}
        if mismatches:
            raise ValueError(f"Independent rank reconstruction disagrees with {len(mismatches)} cached rows.")
    (output / "VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("study", type=Path)
    parser.add_argument("--vector-cache", type=Path)
    args = parser.parse_args()
    result = review(args.evidence, args.study, args.vector_cache)
    print(json.dumps({key: result[key] for key in (
        "preserved_source_files_verified", "model_outputs", "ranked_responses", "invalid_counts",
        "spearman_contexto_vs_candidate", "transitions", "direction_disagreements",
        "highest_observed_displayed_rank")}, indent=2))
    if "independent_vector_checks" in result:
        vector = result["independent_vector_checks"]
        print(json.dumps({key: vector[key] for key in (
            "vocabulary", "dimensions", "figure_matches", "demo_matches", "cached_rank_mismatches")}, indent=2))
