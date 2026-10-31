"""DATA-001 ACs: typed streaming, immutable provenance and deterministic rejection.

Only the optional bounded local-source case reads real data; all writes target
pytest's synthetic tmp_path. CI does not acquire or require MovieLens datasets.
"""
from contextlib import closing
import csv
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from recommender.data import DataValidationError, MovieLens, batches, source_snapshot, validate_movielens
from recommender.data.movielens import MAX_TIMESTAMP, SCHEMAS
from verify_raw_data import inspect_csv  # Existing read-only preflight, not verify().


def write_table(root, table, rows, header=None):
    with (root / table).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SCHEMAS[table] if header is None else header)
        writer.writerows(rows)


@pytest.fixture
def raw(tmp_path):
    write_table(tmp_path, "movies.csv", [(1, 'Toy, Story (1995)', 'Adventure|Comedy'),
                                         (2, 'Misérables, Les (1995)', '(no genres listed)')])
    write_table(tmp_path, "ratings.csv", [(1, 1, '0.5', 0), (2, 2, '5.0', 1450000000)])
    write_table(tmp_path, "tags.csv", [(1, 2, '  café, "great"  ', 123)])
    write_table(tmp_path, "links.csv", [(1, '0114709', 862), (2, '0000001', '')])
    return tmp_path


SCHEMA_CASES = [(table, issue) for table in SCHEMAS
                for issue in ("missing", "extra", "duplicate", "row_short", "row_long", "blank_record")]
REFERENCE_CASES = ["rating_movie", "tag_movie", "link_movie", "tag_user",
                   "missing_link", "duplicate_movie", "duplicate_link"]


@pytest.mark.parametrize("case", ["types", "reordered_bom", "nullable_fields", "full_audit",
                                  *SCHEMA_CASES, *REFERENCE_CASES])
def test_data_001_ac_01(raw, case):
    """Required types/schema and complete movie/user reference checks."""
    data = MovieLens(raw)
    if case == "types":
        ratings = list(data.ratings(movie_ids={1, 2}))
        assert ratings[0].user_id == 1 and type(ratings[0].user_id) is int
        assert type(ratings[0].movie_id) is int and type(ratings[0].rating) is float
        assert ratings[0].rating == 0.5
        assert ratings[0].timestamp == datetime(1970, 1, 1, tzinfo=timezone.utc)
        assert all(row.timestamp.tzinfo is timezone.utc for row in ratings)
        assert list(data.movies())[0].title == 'Toy, Story (1995)'
        assert list(data.movies())[0].genres == ('Adventure', 'Comedy')
        assert list(data.movies())[1].genres == ('(no genres listed)',)
        assert next(data.tags()).tag == '  café, "great"  '
        links = list(data.links(movie_ids={1, 2}))
        assert links[0].imdb_id == '0114709' and links[0].tmdb_id == 862
        assert links[1].tmdb_id is None
    elif case == "reordered_bom":
        for table in SCHEMAS:
            path = raw / table
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                csv.writer(handle).writerows([row[::-1] for row in rows])
        assert validate_movielens(raw)["rows"]["ratings.csv"] == 2
    elif case == "nullable_fields":
        write_table(raw, "tags.csv", [(1, 2, '', 123), (1, 2, '  ', 124)])
        write_table(raw, "links.csv", [(1, '', ''), (2, '0000001', '')])
        assert [tag.tag for tag in data.tags()] == ['', '  ']
        report = validate_movielens(raw)
        assert report['blank_tag_rows'] == 2
        assert report['missing_tmdb_ids'] == 2 and report['missing_imdb_ids'] == 1
    elif case == "full_audit":
        report = validate_movielens(raw)
        assert report['scan'] == 'FULL' and report['status'] == 'PASS'
        assert report['rows'] == {'ratings.csv': 2, 'movies.csv': 2, 'tags.csv': 1, 'links.csv': 2}
        assert report['rating_users'] == 2 and report['source_unchanged']
    elif isinstance(case, tuple):
        table, issue = case
        with (raw / table).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        header = rows[0]
        if issue == "missing": header = header[:-1]
        if issue == "extra": header = [*header, 'unexpected']
        if issue == "duplicate": header = [header[0], *header[:-1]]
        if issue == "row_short": rows[1] = rows[1][:-1]
        if issue == "row_long": rows[1].append('unexpected')
        if issue == "blank_record": rows[1] = []
        write_table(raw, table, rows[1:], header)
        with pytest.raises(DataValidationError) as error:
            list(getattr(data, table.removesuffix('.csv'))())
        assert error.value.code == ('schema' if issue in {'missing','extra','duplicate'} else 'row_width')
    else:
        mutations = {
            'rating_movie': ('ratings.csv', [(1, 999, 4, 0)], 'unknown_movieId'),
            'tag_movie': ('tags.csv', [(1, 999, 'tag', 0)], 'unknown_movieId'),
            'link_movie': ('links.csv', [(999, '0114709', 862)], 'unknown_movieId'),
            'tag_user': ('tags.csv', [(999, 1, 'tag', 0)], 'unknown_userId'),
            'missing_link': ('links.csv', [(1, '0114709', 862)], 'missing_movie_link'),
            'duplicate_movie': ('movies.csv', [(1, 'one', 'Drama'), (1, 'again', 'Comedy')], 'duplicate_movieId'),
            'duplicate_link': ('links.csv', [(1, '0114709', 862), (1, '0114709', 862)], 'duplicate_movieId'),
        }
        table, rows, code = mutations[case]
        write_table(raw, table, rows)
        with pytest.raises(DataValidationError) as error: validate_movielens(raw)
        assert error.value.code == code


@pytest.mark.parametrize("case", ['read_only', 'duplicate_events', 'multiline', 'batch_bounds',
                                  'lazy', 'source_change', 'real_sample'])
def test_data_001_ac_02(raw, case, monkeypatch):
    """Byte integrity, unique logical/physical provenance and bounded consumption."""
    data = MovieLens(raw)
    if case == 'read_only':
        before = source_snapshot(raw)
        original = Path.open
        def read_only(path, mode='r', *args, **kwargs):
            if path.resolve().is_relative_to(raw.resolve()): assert mode in ('r','rb')
            return original(path, mode, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', read_only)
        validate_movielens(raw)
        assert source_snapshot(raw) == before
    elif case == 'duplicate_events':
        write_table(raw, 'ratings.csv', [(1, 1, 3, 0), (1, 1, 3, 0)])
        rows = list(data.ratings())
        assert len(rows) == 2 and rows[0].rating == rows[1].rating
        assert rows[0].source.key != rows[1].source.key
        assert [r.source.record_number for r in rows] == [2, 3]
        assert all(Path(r.source.source_file) == raw.resolve()/'ratings.csv' for r in rows)
    elif case == 'multiline':
        write_table(raw, 'tags.csv', [(1, 1, 'line 1,\n"line 2" Δ', 0), (2, 2, 'next', 1)])
        rows = list(data.tags())
        assert rows[0].tag == 'line 1,\n"line 2" Δ'
        assert (rows[0].source.record_number, rows[0].source.line_start, rows[0].source.line_end) == (2, 2, 3)
        assert (rows[1].source.record_number, rows[1].source.line_start) == (3, 4)
    elif case == 'batch_bounds':
        expected = list(data.ratings())
        for size in (1, 2, 3, 100):
            chunks = list(batches(data.ratings(), size))
            assert all(0 < len(chunk) <= size for chunk in chunks)
            assert [row for chunk in chunks for row in chunk] == expected
        for size in (0, -1, True, 1.5):
            with pytest.raises(ValueError): list(batches(data.ratings(), size))
    elif case == 'lazy':
        consumed = []
        def rows():
            for i in range(1_000_000):
                consumed.append(i)
                yield i
        stream = batches(rows(), 10)
        assert next(stream) == tuple(range(10)) and len(consumed) == 10
        stream.close()
        # Invalid tail must not be parsed while taking a bounded prefix.
        write_table(raw, 'ratings.csv', [(1, 1, 3, 0), ('bad', 1, 3, 0)])
        with closing(data.ratings()) as stream: assert next(stream).user_id == 1
        with pytest.raises(DataValidationError): list(data.ratings())
    elif case == 'source_change':
        stream = data.ratings()
        next(stream)
        with (raw/'ratings.csv').open('a', encoding='utf-8') as handle: handle.write('1,1,3,0\n')
        with pytest.raises(DataValidationError) as error: list(stream)
        assert error.value.code == 'source_changed'
    elif case == 'real_sample':
        root = ROOT/'dataset_linkage_work/raw/movielens/ml-25m'
        if not all((root/table).is_file() for table in SCHEMAS):
            pytest.skip('Local MovieLens source not installed; no download in tests')
        before = source_snapshot(root)
        for table, fields in SCHEMAS.items():
            assert inspect_csv(root/table, set(fields))['valid']
        real = MovieLens(root)
        ids = {movie.movie_id for movie in real.movies()}
        assert len(ids) > 0
        assert sum(1 for _ in real.links(movie_ids=ids)) == len(ids)
        for stream in (real.ratings(movie_ids=ids), real.tags(movie_ids=ids)):
            with closing(stream):
                count = sum(1 for _ in islice(stream, 2048))
            assert count == 2048
        assert source_snapshot(root) == before


BAD_FIELDS = [
    ('ratings.csv', 'userId', value, 'invalid_id')
    for value in ('', '0', '-1', '1.0', ' 1', '１', '9223372036854775808')
] + [
    ('ratings.csv', 'rating', value, 'invalid_rating')
    for value in ('', 'NaN', 'inf', '-inf', '0', '5.5', '4.25', '4e0', '4.50000000000000000001')
] + [
    (table, 'timestamp', value, 'invalid_timestamp')
    for table in ('ratings.csv', 'tags.csv')
    for value in ('', '-1', '1.0', '+1', ' 1', 'NaN', str(MAX_TIMESTAMP+1), '9'*5000)
] + [
    ('movies.csv','movieId','0','invalid_id'),
    ('ratings.csv','movieId','1.0','invalid_id'),
    ('tags.csv','userId','-1','invalid_id'),
    ('tags.csv','tag','private\0text','invalid_text'),
    ('movies.csv','title',' ','invalid_text'),
    ('movies.csv','genres','Drama||Comedy','invalid_text'),
    ('links.csv','imdbId','tt0114709','invalid_id'),
    ('links.csv','imdbId','0000000','invalid_id'),
    ('links.csv','tmdbId','862.0','invalid_id'),
    ('links.csv','tmdbId','NaN','invalid_id'),
]


@pytest.mark.parametrize('table,field,value,code', BAD_FIELDS + [
    ('ratings.csv','record','unterminated','csv_syntax'),
    ('movies.csv','record','invalid_utf8','encoding'),
    ('ratings.csv','record','empty_file','schema'),
    ('tags.csv','record','missing_file','source_unavailable'),
    ('tags.csv','record','header_only','empty_table'),
    ('ratings.csv','timestamp',str(MAX_TIMESTAMP),'valid_boundary'),
])
def test_data_001_ac_03(raw, table, field, value, code):
    """Fail at the first bad record with stable code, field and provenance."""
    path = raw/table
    if value == 'unterminated': path.write_text('userId,movieId,rating,timestamp\n1,1,3,"123\n', encoding='utf-8')
    elif value == 'invalid_utf8': path.write_bytes(b'movieId,title,genres\n1,\xff,Drama\n')
    elif value == 'empty_file': path.write_bytes(b'')
    elif value == 'missing_file': path.unlink()
    elif value == 'header_only': write_table(raw, table, [])
    else:
        with path.open(encoding='utf-8', newline='') as handle: rows = list(csv.reader(handle))
        rows[1][rows[0].index(field)] = value
        write_table(raw, table, rows[1:])
    data = MovieLens(raw)
    if code == 'valid_boundary':
        row = next(data.ratings())
        assert row.timestamp == datetime(9999,12,31,23,59,59,tzinfo=timezone.utc)
        return
    errors = []
    for _ in range(2):
        with pytest.raises(DataValidationError) as error:
            if code == 'empty_table': validate_movielens(raw)
            else: list(getattr(data, table.removesuffix('.csv'))())
        errors.append(error.value)
    assert str(errors[0]) == str(errors[1])
    assert errors[0].code == code
    assert errors[0].source.source_file == str(path.resolve())
    if field != 'record':
        assert errors[0].field == field
        assert errors[0].source.record_number == 2
    assert 'private' not in str(errors[0])
