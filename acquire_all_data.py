from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import socket
import sys
import time
from pathlib import Path
from typing import Any

import certifi
import requests

ML_URL = "https://files.grouplens.org/datasets/movielens/ml-25m.zip"
IMDB_BASE = "https://datasets.imdbws.com"
IMDB_FILES = ("title.basics.tsv.gz", "title.crew.tsv.gz", "title.principals.tsv.gz", "name.basics.tsv.gz")
ML_FILES = ("movies.csv", "ratings.csv", "tags.csv", "links.csv", "genome-scores.csv", "genome-tags.csv", "README.txt")
TMDB_JSONL_FILES = ("movie_details.jsonl", "keywords.jsonl", "credits.jsonl")
TMDB_CONNECT_TIMEOUT = 10
TMDB_READ_TIMEOUT = 45
TMDB_MAX_ATTEMPTS = 5
TMDB_BACKOFF_BASE = 1.0
TMDB_BACKOFF_CAP = 30.0


def replace_with_retry(source: Path, destination: Path, attempts: int = 10) -> None:
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.25 * (attempt + 1))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    replace_with_retry(tmp, path)


def move_if_needed(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.exists():
        if source.is_file() and destination.is_file() and source.stat().st_size == destination.stat().st_size:
            print(f"[keep] {destination}")
            return
        raise RuntimeError(f"Refusing to overwrite existing destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    print(f"[migrate] {source} -> {destination}")


def migrate_v2(raw: Path) -> None:
    for directory in (raw / "movielens", raw / "imdb", raw / "_archives", raw / "tmdb"):
        directory.mkdir(parents=True, exist_ok=True)
    move_if_needed(raw / "ml-25m", raw / "movielens" / "ml-25m")
    move_if_needed(raw / "ml-25m.zip", raw / "_archives" / "ml-25m.zip")
    for name in IMDB_FILES:
        move_if_needed(raw / name, raw / "imdb" / name)


def make_session() -> requests.Session:
    client = requests.Session()
    client.headers.update({"User-Agent": "Dataset-Linkage-Check-Toolkit/3.0"})
    return client


def download_resumable(client: requests.Session, url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        print(f"[skip] {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with client.get(url, headers=headers, stream=True, timeout=(20, 120), verify=certifi.where()) as response:
        if offset and response.status_code == 416:
            match = re.search(r"\*/(\d+)", response.headers.get("Content-Range", ""))
            if match and offset == int(match.group(1)):
                replace_with_retry(partial, destination)
                print(f"[ok] {destination} ({destination.stat().st_size:,} bytes; resumed complete file)")
                return
            response.raise_for_status()
        if offset and response.status_code == 200:
            offset = 0
        elif response.status_code not in (200, 206):
            response.raise_for_status()
        mode = "ab" if offset and response.status_code == 206 else "wb"
        print(f"[download] {url} (resume={offset:,} bytes)")
        with partial.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    replace_with_retry(partial, destination)
    print(f"[ok] {destination} ({destination.stat().st_size:,} bytes)")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 2, "completed_tmdb_ids": [], "transient_errors": {}, "permanent_errors": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("completed_tmdb_ids", [])
    data.setdefault("transient_errors", {})
    data.setdefault("permanent_errors", {})
    for tmdb_id, message in data.pop("failed", {}).items():
        category, transient = classify_error_message(str(message))
        target = data["transient_errors"] if transient else data["permanent_errors"]
        target.setdefault(str(tmdb_id), {"category": category, "message": str(message), "attempts": 1})
    data["version"] = 2
    return data


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def classify_error_message(message: str) -> tuple[str, bool]:
    lowered = message.lower()
    if any(marker in lowered for marker in ("nameresolution", "failed to resolve", "getaddrinfo", "errno 11001", "errno 11004")):
        return "dns", True
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout", True
    if "429" in lowered or "rate limit" in lowered:
        return "http_429", True
    match = re.search(r"\b([45]\d\d)\b", lowered)
    if match:
        status = int(match.group(1))
        return f"http_{status}", status in {408, 425, 429} or status >= 500
    return "network", True


def classify_exception(exc: BaseException) -> tuple[str, bool, int | None]:
    if isinstance(exc, requests.Timeout):
        return "timeout", True, None
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        return f"http_{status}", status in {408, 425, 429} or status >= 500, status
    if isinstance(exc, (requests.ConnectionError, socket.gaierror)):
        category, _ = classify_error_message(str(exc))
        return category, True, None
    category, transient = classify_error_message(str(exc))
    return category, transient, None


def jsonl_id_sets(tmdb_dir: Path) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for name in TMDB_JSONL_FILES:
        ids: set[int] = set()
        path = tmdb_dir / name
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        ids.add(int(json.loads(line)["tmdbId"]))
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
        result[name] = ids
    return result


def error_record(category: str, message: str, attempts: int, status: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"category": category, "message": message, "attempts": attempts, "last_attempt_utc": utc_now()}
    if status is not None:
        record["http_status"] = status
    return record


def request_tmdb(client: requests.Session, url: str, headers: dict[str, str], params: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, bool]:
    last_error: dict[str, Any] | None = None
    for attempt in range(1, TMDB_MAX_ATTEMPTS + 1):
        try:
            response = client.get(
                url, headers=headers, params=params,
                timeout=(TMDB_CONNECT_TIMEOUT, TMDB_READ_TIMEOUT), verify=certifi.where(),
            )
            if response.status_code == 429:
                retry_after = max(float(response.headers.get("Retry-After", "0") or 0), 0.0)
                exc = requests.HTTPError("429 rate limit", response=response)
                category, transient, status = classify_exception(exc)
                last_error = error_record(category, str(exc), attempt, status)
                if attempt < TMDB_MAX_ATTEMPTS:
                    time.sleep(max(retry_after, min(TMDB_BACKOFF_BASE * (2 ** (attempt - 1)), TMDB_BACKOFF_CAP)))
                    continue
                return None, last_error, transient
            response.raise_for_status()
            return response.json(), None, False
        except (requests.RequestException, ValueError, socket.gaierror) as exc:
            category, transient, status = classify_exception(exc)
            last_error = error_record(category, str(exc), attempt, status)
            if not transient or attempt >= TMDB_MAX_ATTEMPTS:
                return None, last_error, transient
            time.sleep(min(TMDB_BACKOFF_BASE * (2 ** (attempt - 1)), TMDB_BACKOFF_CAP))
    return None, last_error, True


def staged_rows(link: dict[str, int], payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = dict(payload)
    common = {**link, "fetched_at_utc": utc_now()}
    keywords = payload.pop("keywords", {})
    credits = payload.pop("credits", {})
    return {
        "movie_details.jsonl": {**common, "data": payload},
        "keywords.jsonl": {**common, "data": keywords},
        "credits.jsonl": {**common, "data": credits},
    }


def commit_staged(tmdb_dir: Path, stage_path: Path, id_sets: dict[str, set[int]]) -> int:
    rows = json.loads(stage_path.read_text(encoding="utf-8"))
    tmdb_id = int(rows["movie_details.jsonl"]["tmdbId"])
    for name in TMDB_JSONL_FILES:
        if tmdb_id not in id_sets[name]:
            append_jsonl(tmdb_dir / name, rows[name])
            id_sets[name].add(tmdb_id)
    return tmdb_id


def update_crawl_report(tmdb_dir: Path, checkpoint: dict[str, Any], target_ids: set[int], completed: set[int]) -> None:
    permanent = {int(value) for value in checkpoint["permanent_errors"] if int(value) in target_ids and int(value) not in completed}
    transient = {int(value) for value in checkpoint["transient_errors"] if int(value) in target_ids and int(value) not in completed}
    pending = target_ids - completed - permanent
    summary = {"target": len(target_ids), "success": len(target_ids & completed), "failed": len(permanent), "pending": len(pending), "transient_pending": len(transient)}
    checkpoint["summary"] = summary
    report = {
        "generated_at_utc": utc_now(), "mode": checkpoint.get("mode"), "summary": summary,
        "failed": {key: value for key, value in checkpoint["permanent_errors"].items() if int(key) in target_ids},
        "pending_errors": {key: value for key, value in checkpoint["transient_errors"].items() if int(key) in target_ids},
    }
    atomic_json(tmdb_dir / "tmdb_crawl_report.json", report)


def linked_movies(path: Path) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append({"movieId": int(row["movieId"]), "imdbId": int(float(row["imdbId"])), "tmdbId": int(float(row["tmdbId"]))})
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def crawl_tmdb(raw: Path, limit: int | None, delay: float) -> None:
    token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not token and not api_key:
        raise RuntimeError("Set TMDB_BEARER_TOKEN or TMDB_API_KEY before crawling TMDb")
    tmdb_dir = raw / "tmdb"
    all_rows = linked_movies(raw / "movielens" / "ml-25m" / "links.csv")
    targets = all_rows if limit is None else all_rows[:limit]
    checkpoint_path = tmdb_dir / "checkpoint.json"
    checkpoint = load_checkpoint(checkpoint_path)
    id_sets = jsonl_id_sets(tmdb_dir)
    completed_on_disk = set.intersection(*(id_sets[name] for name in TMDB_JSONL_FILES))
    # Three durable rows are the source of truth if the process stopped before
    # the final checkpoint replace.
    completed = completed_on_disk
    checkpoint["completed_tmdb_ids"] = sorted(completed)
    client = make_session()
    headers = {"accept": "application/json"}
    params = {"append_to_response": "keywords,credits"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        params["api_key"] = api_key
    target_ids = {row["tmdbId"] for row in targets}
    checkpoint.update({"mode": "full" if limit is None else "test", "target_count": len(target_ids), "available_link_count": len(all_rows)})
    update_crawl_report(tmdb_dir, checkpoint, target_ids, completed)
    atomic_json(checkpoint_path, checkpoint)
    target_by_id = {row["tmdbId"]: row for row in targets}
    retry_first = [int(value) for value in checkpoint["transient_errors"] if int(value) in target_by_id and int(value) not in completed]
    ordered_ids = retry_first + [row["tmdbId"] for row in targets if row["tmdbId"] not in set(retry_first)]
    staging_dir = tmdb_dir / "_staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    for index, tmdb_id in enumerate(ordered_ids, 1):
        link = target_by_id[tmdb_id]
        tmdb_id = link["tmdbId"]
        if tmdb_id in completed:
            print(f"[tmdb {index}/{len(ordered_ids)}] skip {tmdb_id}")
            continue
        stage_path = staging_dir / f"{tmdb_id}.json"
        if stage_path.exists():
            commit_staged(tmdb_dir, stage_path, id_sets)
            if all(tmdb_id in id_sets[name] for name in TMDB_JSONL_FILES):
                completed.add(tmdb_id)
                checkpoint["completed_tmdb_ids"] = sorted(completed)
                checkpoint["transient_errors"].pop(str(tmdb_id), None)
                checkpoint["permanent_errors"].pop(str(tmdb_id), None)
                update_crawl_report(tmdb_dir, checkpoint, target_ids, completed)
                atomic_json(checkpoint_path, checkpoint)
                stage_path.unlink(missing_ok=True)
                print(f"[tmdb {index}/{len(ordered_ids)}] recovered {tmdb_id}")
                continue
        if str(tmdb_id) in checkpoint["permanent_errors"]:
            print(f"[tmdb {index}/{len(ordered_ids)}] permanent-skip {tmdb_id}")
            continue
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        payload, error, transient = request_tmdb(client, url, headers, params)
        if payload is not None:
            atomic_json(stage_path, staged_rows(link, payload))
            commit_staged(tmdb_dir, stage_path, id_sets)
            completed.add(tmdb_id)
            checkpoint["completed_tmdb_ids"] = sorted(completed)
            checkpoint["transient_errors"].pop(str(tmdb_id), None)
            checkpoint["permanent_errors"].pop(str(tmdb_id), None)
            checkpoint["updated_at_utc"] = utc_now()
            update_crawl_report(tmdb_dir, checkpoint, target_ids, completed)
            atomic_json(checkpoint_path, checkpoint)
            stage_path.unlink(missing_ok=True)
            print(f"[tmdb {index}/{len(ordered_ids)}] ok {tmdb_id}: {payload.get('title')}")
        else:
            bucket = checkpoint["transient_errors"] if transient else checkpoint["permanent_errors"]
            other = checkpoint["permanent_errors"] if transient else checkpoint["transient_errors"]
            bucket[str(tmdb_id)] = error
            other.pop(str(tmdb_id), None)
            update_crawl_report(tmdb_dir, checkpoint, target_ids, completed)
            atomic_json(checkpoint_path, checkpoint)
            label = "pending" if transient else "permanent-failed"
            print(f"[tmdb {index}/{len(ordered_ids)}] {label} {tmdb_id}: {error['category']}: {error['message']}", file=sys.stderr)
            if transient and error["category"] == "dns":
                print("[tmdb] DNS is unavailable; stopping this run with checkpoint preserved", file=sys.stderr)
                break
        time.sleep(max(delay, 0))
    update_crawl_report(tmdb_dir, checkpoint, target_ids, completed)
    atomic_json(checkpoint_path, checkpoint)


def acquire(workdir: Path, tmdb_limit: int | None, skip_tmdb: bool, delay: float) -> None:
    raw = workdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    migrate_v2(raw)
    client = make_session()
    download_resumable(client, ML_URL, raw / "_archives" / "ml-25m.zip")
    ml_dir = raw / "movielens" / "ml-25m"
    missing = [name for name in ML_FILES if not (ml_dir / name).exists()]
    if missing:
        raise RuntimeError(f"MovieLens extraction is incomplete; missing: {', '.join(missing)}")
    for name in IMDB_FILES:
        download_resumable(client, f"{IMDB_BASE}/{name}", raw / "imdb" / name)
    if not skip_tmdb:
        crawl_tmdb(raw, tmdb_limit, delay)


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire and resume MovieLens, IMDb and TMDb raw data (v3)")
    parser.add_argument("--workdir", default="dataset_linkage_work")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tmdb-limit", type=int)
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--skip-tmdb", action="store_true")
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()
    if args.tmdb_limit is not None and args.tmdb_limit < 1:
        parser.error("--tmdb-limit must be positive")
    acquire(Path(args.workdir).resolve(), None if args.full else (args.tmdb_limit or 30), args.skip_tmdb, args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
