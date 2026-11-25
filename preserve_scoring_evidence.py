"""Preserve a scoring investigation's small artifacts, without downloads or API calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


FOLDERS = ("api", "paper", "scripts", "wayback", "web", "wp")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preserve(source, destination, report):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not all((source / name).is_dir() for name in FOLDERS):
        raise ValueError("Expected investigation evidence directories are missing.")
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for name in FOLDERS:
        for original in sorted((source / name).rglob("*")):
            if not original.is_file() or original.suffix == ".pyc" or "__pycache__" in original.parts:
                continue
            if original.is_symlink() or not original.resolve().is_relative_to(source):
                raise ValueError(f"Unexpected external link: {original}")
            relative = original.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            before = original.stat()
            shutil.copy2(original, target)
            after = original.stat()
            source_hash, copy_hash = sha256(original), sha256(target)
            if source_hash != copy_hash or before.st_mtime_ns != after.st_mtime_ns:
                raise ValueError(f"Source changed during preservation: {original}")
            records.append({"path": relative.as_posix(), "bytes": after.st_size,
                            "source_mtime_ns": after.st_mtime_ns, "sha256": copy_hash})
    report = Path(report)
    shutil.copy2(report, destination / "ORIGINAL_REPORT.md")
    records.append({"path": "ORIGINAL_REPORT.md", "bytes": report.stat().st_size,
                    "sha256": sha256(destination / "ORIGINAL_REPORT.md")})
    excluded = []
    for name in ("vec", "venv", "nltk_data"):
        directory = source / name
        for path in sorted(directory.rglob("*")):
            if path.is_file() and (name == "vec" or path.name in {"pyvenv.cfg", "requirements.txt"}):
                excluded.append({"path": path.relative_to(source).as_posix(), "bytes": path.stat().st_size})
    manifest = {"copied_at_utc": datetime.now(timezone.utc).isoformat(), "source_directory": str(source),
                "files": records, "copied_bytes": sum(r["bytes"] for r in records),
                "excluded_directories": ["vec", "venv", "nltk_data", "__pycache__"],
                "external_inputs": excluded,
                "notes": ["No source files deleted or moved.", "Copied scripts were not executed.",
                          "Archives, environments and vector caches remain external inputs.",
                          "SHA-256 equality checks preservation, not the truth of every research claim."]}
    (destination / "PRESERVATION.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = preserve(args.source, args.destination, args.report)
    print(json.dumps({"files": len(result["files"]), "bytes": result["copied_bytes"],
                      "destination": str(args.destination)}, indent=2))
