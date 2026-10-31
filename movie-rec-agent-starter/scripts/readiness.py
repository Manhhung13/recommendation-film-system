"""Read-only dataset integrity checks for research prerequisites. No signing."""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

PROTECTED_TASKS = frozenset({'DATA-QUALITY-001', 'RESEARCH-001', 'EDA-001', 'SPLIT-001'})
REQUIRED_SOURCES = {
    **{f'movielens/ml-25m/{n}': 'movielens' for n in (
        'ratings.csv', 'movies.csv', 'tags.csv', 'links.csv', 'genome-scores.csv', 'genome-tags.csv')},
    **{f'imdb/{n}.tsv.gz': 'imdb' for n in (
        'title.basics', 'title.crew', 'title.principals', 'name.basics')},
    **{f'tmdb/{n}.jsonl': 'tmdb' for n in ('movie_details', 'keywords', 'credits')},
}
SHA256 = re.compile(r'^[0-9a-f]{64}$')


class ReadinessError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReadinessError(message)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ReadinessError('Non-finite JSON')))


def utc(value):
    require(isinstance(value, str), 'Missing timestamp')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0), 'Timestamp must be UTC')
    return stamp


def local_path(root, value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
            'Invalid repository-relative evidence path')
    rel = PurePosixPath(value)
    require(not rel.is_absolute() and '..' not in rel.parts, 'Evidence path traversal')
    path = (root / value).resolve(strict=True)
    require(path.is_relative_to(root.resolve()) and path.is_file(), 'Evidence outside repository or missing')
    return path


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def artifact(root, reference):
    require(isinstance(reference, dict), 'Missing evidence artifact')
    expected = reference.get('sha256')
    require(isinstance(expected, str) and SHA256.fullmatch(expected), 'Invalid artifact digest')
    path = local_path(root, reference.get('path'))
    require(digest(path) == expected, 'Artifact changed: ' + reference['path'])
    return path


def prerequisite_ids(tasks, task_id):
    found = set()
    active = set()

    def visit(tid):
        require(tid in tasks and tid not in active, 'Invalid dependency graph')
        if tid in found:
            return
        active.add(tid)
        for dep in tasks[tid].get('dependencies', []):
            visit(dep)
            found.add(dep)
        active.remove(tid)

    visit(task_id)
    return sorted(found)


def verify_manifest(root, reference):
    manifest = read_json(artifact(root, reference))
    require(manifest.get('schema_version') == 1, 'Unsupported dataset manifest')
    require(manifest.get('raw_root') == 'dataset_linkage_work/raw', 'Unexpected raw root')
    entries = manifest.get('files')
    require(isinstance(entries, list) and entries, 'Empty dataset manifest')
    seen = set()
    for entry in entries:
        name = entry['path']
        require(name not in seen, 'Duplicate manifest path')
        seen.add(name)
        path = artifact(root, entry)
        require(path.is_relative_to((root / manifest['raw_root']).resolve()), 'Manifest source outside raw root')
        require(type(entry.get('size_bytes')) is int and entry['size_bytes'] > 0
                and path.stat().st_size == entry['size_bytes'], 'Source size mismatch')
        require(isinstance(entry.get('source_version'), str) and entry['source_version'].strip(),
                'Missing source version')
        utc(entry.get('retrieved_at_utc'))
    by_path = {entry['path']: entry for entry in entries}
    for suffix, family in REQUIRED_SOURCES.items():
        entry = by_path.get(manifest['raw_root'] + '/' + suffix, {})
        require(entry.get('source') == family, 'Missing required source: ' + suffix)


def verify_readiness(tasks, task_id, root, **_):
    """Keep data gates without reviewer signatures or product CI blockers.

    DATA-QUALITY produces the comprehensive manifest; research consumes it.
    Dependency receipts and owner business decisions are checked by agentctl.
    """
    if task_id == 'DATA-QUALITY-001':
        return set()
    path = root / '.runtime/dataset-manifest.json'
    require(path.is_file(), 'Dataset manifest missing; complete DATA-QUALITY-001 first')
    proof=read_json(root/'.runtime/evidence/DATA-QUALITY-001/completion.json')
    reference=proof.get('dataset_manifest')
    require(isinstance(reference,dict) and reference.get('path')==path.relative_to(root).as_posix(),
            'Missing completed DATA-QUALITY manifest reference')
    verify_manifest(root, reference)
    return set()
