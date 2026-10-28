from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import acquire_all_data as acquire
import requests
from verify_raw_data import verify


class FakeResponse:
    def __init__(self, tmdb_id: int, status_code: int = 200, headers: dict[str, str] | None = None):
        self.tmdb_id = tmdb_id
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self) -> dict:
        return {
            "id": self.tmdb_id,
            "title": f"Movie {self.tmdb_id}",
            "keywords": {"keywords": [{"id": 1, "name": "test"}]},
            "credits": {"cast": [{"id": 2, "name": "Actor"}], "crew": []},
        }


class FakeSession:
    def __init__(self):
        self.calls = 0

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls += 1
        self.last_verify = kwargs.get("verify")
        return FakeResponse(int(url.rsplit("/", 1)[-1]))


class SequenceSession:
    def __init__(self, outcomes: list[object]):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url: str, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class PipelineV3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.sleep_patch = patch.object(acquire.time, "sleep", return_value=None)
        self.sleep_patch.start()

    def tearDown(self) -> None:
        self.sleep_patch.stop()

    def test_tmdb_30_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw"
            ml = raw / "movielens" / "ml-25m"
            ml.mkdir(parents=True)
            source = Path(__file__).parent / "dataset_linkage_work" / "raw" / "movielens" / "ml-25m" / "links.csv"
            (ml / "links.csv").write_bytes(source.read_bytes())
            fake = FakeSession()
            with patch.dict(os.environ, {"TMDB_BEARER_TOKEN": "test-token"}), patch.object(acquire, "make_session", return_value=fake):
                acquire.crawl_tmdb(raw, 30, 0)
                self.assertEqual(fake.calls, 30)
                acquire.crawl_tmdb(raw, 30, 0)
                self.assertEqual(fake.calls, 30, "resume must not call completed movies again")
            tmdb = raw / "tmdb"
            for name in ("movie_details.jsonl", "keywords.jsonl", "credits.jsonl"):
                rows = [json.loads(line) for line in (tmdb / name).read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(rows), 30)
                self.assertTrue(all({"movieId", "imdbId", "tmdbId", "data"} <= row.keys() for row in rows))
            checkpoint = json.loads((tmdb / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(len(checkpoint["completed_tmdb_ids"]), 30)
            report = json.loads((tmdb / "tmdb_crawl_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"], {"target": 30, "success": 30, "failed": 0, "pending": 0, "transient_pending": 0})

    def test_dns_timeout_and_429_retry_then_success(self) -> None:
        cases = [
            requests.ConnectionError("Failed to resolve api.themoviedb.org ([Errno 11001] getaddrinfo failed)"),
            requests.Timeout("read timed out"),
            FakeResponse(862, 429, {"Retry-After": "3"}),
            FakeResponse(862),
        ]
        client = SequenceSession(cases)
        payload, error, transient = acquire.request_tmdb(client, "https://api.themoviedb.org/3/movie/862", {}, {})
        self.assertEqual(payload["id"], 862)
        self.assertIsNone(error)
        self.assertFalse(transient)
        self.assertEqual(client.calls, 4)
        self.assertEqual(client.last_kwargs["timeout"], (acquire.TMDB_CONNECT_TIMEOUT, acquire.TMDB_READ_TIMEOUT))
        self.assertTrue(client.last_kwargs["verify"])

    def test_permanent_404_is_not_retried(self) -> None:
        client = SequenceSession([FakeResponse(999, 404)])
        payload, error, transient = acquire.request_tmdb(client, "https://api.themoviedb.org/3/movie/999", {}, {})
        self.assertIsNone(payload)
        self.assertEqual(error["category"], "http_404")
        self.assertFalse(transient)
        self.assertEqual(client.calls, 1)

    def test_old_dns_failure_is_retried_and_partial_jsonl_is_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw"
            ml = raw / "movielens" / "ml-25m"
            tmdb = raw / "tmdb"
            ml.mkdir(parents=True)
            tmdb.mkdir(parents=True)
            (ml / "links.csv").write_text("movieId,imdbId,tmdbId\n1,114709,862\n", encoding="utf-8")
            existing = {"movieId": 1, "imdbId": 114709, "tmdbId": 862, "data": {"id": 862}}
            (tmdb / "movie_details.jsonl").write_text(json.dumps(existing) + "\n", encoding="utf-8")
            (tmdb / "checkpoint.json").write_text(json.dumps({
                "version": 1, "completed_tmdb_ids": [862],
                "failed": {"862": "Failed to resolve api.themoviedb.org ([Errno 11001] getaddrinfo failed)"},
            }), encoding="utf-8")
            client = FakeSession()
            with patch.dict(os.environ, {"TMDB_BEARER_TOKEN": "test-token"}), patch.object(acquire, "make_session", return_value=client):
                acquire.crawl_tmdb(raw, 1, 0)
            self.assertEqual(client.calls, 1)
            for name in acquire.TMDB_JSONL_FILES:
                self.assertEqual(len((tmdb / name).read_text(encoding="utf-8").splitlines()), 1)
            checkpoint = json.loads((tmdb / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["version"], 2)
            self.assertEqual(checkpoint["completed_tmdb_ids"], [862])
            self.assertEqual(checkpoint["transient_errors"], {})

    def test_transient_failure_stays_pending_for_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw"
            ml = raw / "movielens" / "ml-25m"
            ml.mkdir(parents=True)
            (ml / "links.csv").write_text("movieId,imdbId,tmdbId\n1,114709,862\n", encoding="utf-8")
            failures = [requests.ConnectionError("Failed to resolve api.themoviedb.org ([Errno 11001])") for _ in range(acquire.TMDB_MAX_ATTEMPTS)]
            with patch.dict(os.environ, {"TMDB_BEARER_TOKEN": "test-token"}), patch.object(acquire, "make_session", return_value=SequenceSession(failures)):
                acquire.crawl_tmdb(raw, 1, 0)
            report = json.loads((raw / "tmdb" / "tmdb_crawl_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["pending"], 1)
            self.assertEqual(report["summary"]["failed"], 0)
            self.assertEqual(report["pending_errors"]["862"]["category"], "dns")

    def test_current_raw_report_is_generated(self) -> None:
        workdir = Path(__file__).parent / "dataset_linkage_work"
        report, ready = verify(workdir)
        self.assertTrue(report["readiness"]["movielens"])
        self.assertTrue(report["readiness"]["imdb"])
        self.assertEqual(ready, report["database_design_can_start"])


if __name__ == "__main__":
    unittest.main()
