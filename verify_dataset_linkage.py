from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import requests

ML25M_URL = "https://files.grouplens.org/datasets/movielens/ml-25m.zip"
IMDB_URLS = {
    "title.basics.tsv.gz": "https://datasets.imdbws.com/title.basics.tsv.gz",
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[skip] {dest.name} already exists")
        return
    print(f"[download] {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"[ok] {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")


def extract_ml25m(zip_path: Path, raw_dir: Path) -> Path:
    expected = raw_dir / "ml-25m" / "movies.csv"
    if expected.exists():
        return raw_dir / "ml-25m"
    print(f"[extract] {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(raw_dir)
    return raw_dir / "ml-25m"


def imdb_tconst(value) -> str | None:
    if pd.isna(value):
        return None
    try:
        # MovieLens imdbId is the numeric part of IMDb tconst.
        return "tt" + str(int(float(value))).zfill(7)
    except Exception:
        return None


def filter_csv_by_movie_ids(path: Path, movie_ids: set[int], out_cols: list[str] | None = None,
                            max_rows: int | None = None, chunksize: int = 300_000) -> pd.DataFrame:
    pieces = []
    total = 0
    for chunk in pd.read_csv(path, chunksize=chunksize):
        hit = chunk[chunk["movieId"].isin(movie_ids)]
        if not hit.empty:
            if out_cols:
                hit = hit[out_cols]
            pieces.append(hit)
            total += len(hit)
            if max_rows and total >= max_rows:
                break
    if not pieces:
        return pd.DataFrame(columns=out_cols or [])
    result = pd.concat(pieces, ignore_index=True)
    if max_rows:
        result = result.head(max_rows)
    return result


def load_genome_sample(ml_dir: Path, movie_ids: set[int], top_tags: int = 8) -> tuple[pd.DataFrame, set[int]]:
    tags = pd.read_csv(ml_dir / "genome-tags.csv")
    pieces = []
    matched_movies: set[int] = set()
    for chunk in pd.read_csv(ml_dir / "genome-scores.csv", chunksize=400_000):
        hit = chunk[chunk["movieId"].isin(movie_ids)]
        if not hit.empty:
            pieces.append(hit)
            matched_movies.update(hit["movieId"].astype(int).unique().tolist())
    if not pieces:
        return pd.DataFrame(columns=["movieId", "tagId", "relevance", "tag"]), matched_movies
    scores = pd.concat(pieces, ignore_index=True)
    scores = scores.merge(tags, on="tagId", how="left")
    scores = scores.sort_values(["movieId", "relevance"], ascending=[True, False])
    top = scores.groupby("movieId", as_index=False).head(top_tags)
    return top, matched_movies


def load_imdb_title_basics(imdb_gz: Path, tconsts: set[str]) -> pd.DataFrame:
    usecols = ["tconst", "titleType", "primaryTitle", "originalTitle", "startYear", "runtimeMinutes", "genres"]
    pieces = []
    for chunk in pd.read_csv(
        imdb_gz,
        sep="\t",
        compression="gzip",
        dtype=str,
        na_values="\\N",
        usecols=usecols,
        chunksize=250_000,
        low_memory=False,
    ):
        hit = chunk[chunk["tconst"].isin(tconsts)]
        if not hit.empty:
            pieces.append(hit)
    if not pieces:
        return pd.DataFrame(columns=usecols)
    return pd.concat(pieces, ignore_index=True).drop_duplicates("tconst")


def fetch_tmdb(tmdb_ids: list[int], bearer_token: str, limit: int) -> pd.DataFrame:
    headers = {"Authorization": f"Bearer {bearer_token}", "accept": "application/json"}
    rows = []
    for tmdb_id in tmdb_ids[:limit]:
        base = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        try:
            detail = requests.get(base, headers=headers, timeout=30)
            detail.raise_for_status()
            d = detail.json()

            kw_resp = requests.get(base + "/keywords", headers=headers, timeout=30)
            keywords = []
            if kw_resp.ok:
                keywords = [x.get("name") for x in kw_resp.json().get("keywords", [])[:10]]

            cr_resp = requests.get(base + "/credits", headers=headers, timeout=30)
            actors, directors = [], []
            if cr_resp.ok:
                cr = cr_resp.json()
                actors = [x.get("name") for x in cr.get("cast", [])[:5]]
                directors = [x.get("name") for x in cr.get("crew", []) if x.get("job") == "Director"][:3]

            rows.append({
                "tmdbId": tmdb_id,
                "tmdb_title": d.get("title"),
                "overview": d.get("overview"),
                "release_date": d.get("release_date"),
                "runtime": d.get("runtime"),
                "original_language": d.get("original_language"),
                "tmdb_genres": "|".join(g.get("name", "") for g in d.get("genres", [])),
                "keywords": "|".join(k for k in keywords if k),
                "directors": "|".join(x for x in directors if x),
                "actors": "|".join(x for x in actors if x),
            })
            print(f"[tmdb] {tmdb_id} -> {d.get('title')}")
            time.sleep(0.08)
        except Exception as exc:
            print(f"[warn] TMDb {tmdb_id}: {exc}")
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify MovieLens/Tag Genome/IMDb/TMDb linkage")
    parser.add_argument("--workdir", default="dataset_linkage_work", help="Working directory")
    parser.add_argument("--sample-size", type=int, default=30, help="Number of MovieLens movies in linkage sample")
    parser.add_argument("--with-imdb", action="store_true", help="Download IMDb title.basics and validate imdbId")
    parser.add_argument("--with-tmdb", action="store_true", help="Fetch TMDb metadata using TMDB_BEARER_TOKEN")
    parser.add_argument("--tmdb-limit", type=int, default=15, help="Max TMDb API calls for sample")
    args = parser.parse_args()

    work = Path(args.workdir).resolve()
    raw = work / "raw"
    out = work / "output"
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    ml_zip = raw / "ml-25m.zip"
    download(ML25M_URL, ml_zip)
    ml_dir = extract_ml25m(ml_zip, raw)

    movies = pd.read_csv(ml_dir / "movies.csv")
    links = pd.read_csv(ml_dir / "links.csv")

    base = movies.merge(links, on="movieId", how="left")
    base = base[base["imdbId"].notna() & base["tmdbId"].notna()].head(args.sample_size).copy()
    base["imdb_tconst"] = base["imdbId"].map(imdb_tconst)
    base["tmdbId"] = base["tmdbId"].astype("Int64")

    movie_ids = set(base["movieId"].astype(int).tolist())
    base.to_csv(out / "01_movies_links_sample.csv", index=False)

    ratings = filter_csv_by_movie_ids(
        ml_dir / "ratings.csv", movie_ids,
        out_cols=["userId", "movieId", "rating", "timestamp"], max_rows=3000
    )
    ratings.to_csv(out / "02_ratings_sample.csv", index=False)

    tags = filter_csv_by_movie_ids(
        ml_dir / "tags.csv", movie_ids,
        out_cols=["userId", "movieId", "tag", "timestamp"], max_rows=2000
    )
    tags.to_csv(out / "03_tags_sample.csv", index=False)

    genome, genome_movies = load_genome_sample(ml_dir, movie_ids)
    genome.to_csv(out / "04_tag_genome_top_tags_sample.csv", index=False)

    audit = base[["movieId", "title", "genres", "imdbId", "imdb_tconst", "tmdbId"]].copy()
    audit["has_rating_sample"] = audit["movieId"].isin(set(ratings["movieId"].astype(int)))
    audit["has_user_tags_sample"] = audit["movieId"].isin(set(tags["movieId"].astype(int)))
    audit["has_tag_genome"] = audit["movieId"].isin(genome_movies)

    if args.with_imdb:
        imdb_gz = raw / "title.basics.tsv.gz"
        download(IMDB_URLS["title.basics.tsv.gz"], imdb_gz)
        imdb = load_imdb_title_basics(imdb_gz, set(audit["imdb_tconst"].dropna()))
        imdb.to_csv(out / "05_imdb_title_basics_sample.csv", index=False)
        audit = audit.merge(imdb.add_prefix("imdb_"), left_on="imdb_tconst", right_on="imdb_tconst", how="left")
        audit["imdb_join_ok"] = audit["imdb_primaryTitle"].notna()
    else:
        audit["imdb_join_ok"] = pd.NA

    if args.with_tmdb:
        token = os.getenv("TMDB_BEARER_TOKEN")
        if not token:
            raise SystemExit("--with-tmdb requires environment variable TMDB_BEARER_TOKEN")
        tmdb_ids = [int(x) for x in audit["tmdbId"].dropna().tolist()]
        tmdb = fetch_tmdb(tmdb_ids, token, args.tmdb_limit)
        tmdb.to_csv(out / "06_tmdb_metadata_sample.csv", index=False)
        audit = audit.merge(tmdb, on="tmdbId", how="left")
        audit["tmdb_join_ok"] = audit["tmdb_title"].notna()
    else:
        audit["tmdb_join_ok"] = pd.NA

    audit.to_csv(out / "07_linkage_audit.csv", index=False)

    genome_summary = genome.groupby("movieId").apply(
        lambda g: " | ".join(f"{r.tag}:{r.relevance:.3f}" for r in g.itertuples()),
        include_groups=False,
    ).rename("top_genome_tags") if not genome.empty else pd.Series(dtype=str, name="top_genome_tags")
    summary = base.merge(genome_summary, on="movieId", how="left")
    summary.to_csv(out / "08_movie_enriched_preview.csv", index=False)

    report = {
        "sample_movies": len(base),
        "rating_rows_sampled": len(ratings),
        "user_tag_rows_sampled": len(tags),
        "movies_with_tag_genome": int(audit["has_tag_genome"].sum()),
        "imdb_join_checked": bool(args.with_imdb),
        "imdb_join_ok": None if not args.with_imdb else int(audit["imdb_join_ok"].sum()),
        "tmdb_join_checked": bool(args.with_tmdb),
        "tmdb_join_ok": None if not args.with_tmdb else int(audit["tmdb_join_ok"].sum()),
        "join_keys": {
            "MovieLens_to_TagGenome": "movieId",
            "MovieLens_to_IMDb": "links.csv imdbId -> IMDb tconst ('tt' + zero-padded imdbId)",
            "MovieLens_to_TMDB": "links.csv tmdbId -> TMDb movie id"
        }
    }
    (out / "linkage_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== LINKAGE REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nOutput: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
