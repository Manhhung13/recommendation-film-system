from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path
from typing import Any

ML_FILES = ("movies.csv", "ratings.csv", "tags.csv", "links.csv", "genome-scores.csv", "genome-tags.csv")
IMDB_FILES = ("title.basics.tsv.gz", "title.crew.tsv.gz", "title.principals.tsv.gz", "name.basics.tsv.gz")
TMDB_FILES = ("movie_details.jsonl", "keywords.jsonl", "credits.jsonl")


def inspect_csv(path: Path, required: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "size_bytes": 0, "valid": False}
    if not path.is_file():
        return result
    result["size_bytes"] = path.stat().st_size
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            columns = set(next(csv.reader(handle)))
        result.update(valid=result["size_bytes"] > 0 and required <= columns, columns=sorted(columns))
    except Exception as exc:
        result["error"] = str(exc)
    return result


def inspect_gzip(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "size_bytes": 0, "valid": False}
    if not path.is_file():
        return result
    result["size_bytes"] = path.stat().st_size
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            header = handle.readline().rstrip("\n").split("\t")
        result.update(header=header, valid=bool(header and header[0] in {"tconst", "nconst"}))
    except Exception as exc:
        result["error"] = str(exc)
    return result


def jsonl_ids(path: Path) -> tuple[set[int], list[str], int]:
    ids: set[int] = set()
    errors: list[str] = []
    row_count = 0
    if not path.is_file():
        return ids, errors, row_count
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            row_count += 1
            try:
                ids.add(int(json.loads(line)["tmdbId"]))
            except Exception as exc:
                errors.append(f"line {number}: {exc}")
                if len(errors) >= 10:
                    break
    return ids, errors, row_count


def verify(workdir: Path) -> tuple[dict[str, Any], bool]:
    raw = workdir / "raw"
    ml_dir = raw / "movielens" / "ml-25m"
    ml_checks = {name: inspect_csv(ml_dir / name, {"movieId"}) for name in ML_FILES}
    ml_checks["genome-tags.csv"] = inspect_csv(ml_dir / "genome-tags.csv", {"tagId", "tag"})
    archive = raw / "_archives" / "ml-25m.zip"
    ml_ready = all(item["valid"] for item in ml_checks.values()) and archive.is_file() and archive.stat().st_size > 0
    imdb_checks = {name: inspect_gzip(raw / "imdb" / name) for name in IMDB_FILES}
    imdb_ready = all(item["valid"] for item in imdb_checks.values())
    tmdb_dir = raw / "tmdb"
    tmdb_sets: dict[str, set[int]] = {}
    tmdb_checks: dict[str, Any] = {}
    for name in TMDB_FILES:
        ids, errors, row_count = jsonl_ids(tmdb_dir / name)
        tmdb_sets[name] = ids
        tmdb_checks[name] = {"path": str(tmdb_dir / name), "exists": (tmdb_dir / name).is_file(), "rows": row_count, "unique_tmdb_ids": len(ids), "duplicate_rows": row_count - len(ids), "errors": errors}
    checkpoint_path = tmdb_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {}
    completed = {int(value) for value in checkpoint.get("completed_tmdb_ids", [])}
    target_count = int(checkpoint.get("target_count", 0))
    common = completed.intersection(*(tmdb_sets[name] for name in TMDB_FILES)) if completed else set()
    summary = checkpoint.get("summary", {})
    success = int(summary.get("success", len(common)))
    failed = int(summary.get("failed", len(checkpoint.get("permanent_errors", {}))))
    pending = int(summary.get("pending", max(target_count - success - failed, 0)))
    tmdb_ready = target_count > 0 and success + failed == target_count and pending == 0 and len(common) >= success and not any(v["errors"] for v in tmdb_checks.values())
    tmdb_checks["checkpoint"] = {"path": str(checkpoint_path), "version": checkpoint.get("version"), "mode": checkpoint.get("mode"), "target_count": target_count, "success": success, "failed": failed, "pending": pending, "consistent_complete_count": len(common)}
    ready = bool(ml_ready and imdb_ready and tmdb_ready)
    report = {
        "schema_version": 3, "workdir": str(workdir),
        "readiness": {"movielens": ml_ready, "imdb": imdb_ready, "tmdb": tmdb_ready},
        "movielens": {"ready": ml_ready, "archive": str(archive), "files": ml_checks},
        "imdb": {"ready": imdb_ready, "files": imdb_checks},
        "tmdb": {"ready": tmdb_ready, "files": tmdb_checks},
        "linkage": {"movielens_to_imdb": "links.csv imdbId -> IMDb tconst (tt + zero-padded numeric id)", "movielens_to_tmdb": "links.csv tmdbId -> TMDb movie id"},
        "database_design_can_start": ready,
    }
    (workdir / "raw_data_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, ready


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify v3 raw-data readiness")
    parser.add_argument("--workdir", default="dataset_linkage_work")
    args = parser.parse_args()
    workdir = Path(args.workdir).resolve()
    report, ready = verify(workdir)
    print(json.dumps(report["readiness"], indent=2))
    print(f"database_design_can_start={str(ready).lower()}")
    print(f"report={workdir / 'raw_data_report.json'}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
