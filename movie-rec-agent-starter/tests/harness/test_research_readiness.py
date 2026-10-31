"""Dataset integrity remains mandatory after retirement of signature gates."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from readiness import REQUIRED_SOURCES, digest, verify_manifest, verify_readiness, ReadinessError

class DatasetIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.raw='dataset_linkage_work/raw'
        entries=[]
        for suffix,source in REQUIRED_SOURCES.items():
            path=self.root/self.raw/suffix;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'synthetic fixture only')
            entries.append(dict(path=path.relative_to(self.root).as_posix(),sha256=digest(path),
                size_bytes=path.stat().st_size,source=source,source_version='fixture-v1',
                retrieved_at_utc='2026-10-31T00:00:00+00:00'))
        self.manifest={'schema_version':1,'raw_root':self.raw,'files':entries}
        self.path=self.root/'.runtime/dataset-manifest.json';self.path.parent.mkdir()
    def write(self):
        self.path.write_text(json.dumps(self.manifest),encoding='utf-8')
        reference={'path':self.path.relative_to(self.root).as_posix(),'sha256':digest(self.path)}
        proof=self.root/'.runtime/evidence/DATA-QUALITY-001/completion.json'
        proof.parent.mkdir(parents=True,exist_ok=True)
        proof.write_text(json.dumps({'dataset_manifest':reference}),encoding='utf-8')
        return reference
    def test_all_source_families_required_without_signatures(self):
        verify_manifest(self.root,self.write())
        verify_readiness({},'RESEARCH-001',self.root)
    def test_mutated_source_fails_without_changing_raw(self):
        reference=self.write();source=self.root/self.manifest['files'][0]['path']
        source.write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ReadinessError,'Artifact changed'):
            verify_manifest(self.root,reference)
        self.assertEqual(b'changed fixture',source.read_bytes())
    def test_missing_source_and_wrong_source_family_block(self):
        self.manifest['files'].pop()
        with self.assertRaisesRegex(ReadinessError,'Missing required source'):
            verify_manifest(self.root,self.write())
    def test_duplicate_traversal_size_and_non_utc_fail(self):
        import copy
        original=copy.deepcopy(self.manifest)
        variants=[lambda e:e.update(size_bytes=1),lambda e:e.update(path='../outside'),
                  lambda e:e.update(retrieved_at_utc='2026-10-31T01:00:00+01:00')]
        for mutation in variants:
            self.manifest=copy.deepcopy(original);mutation(self.manifest['files'][0])
            with self.assertRaises((ValueError,OSError)):verify_manifest(self.root,self.write())
        self.manifest=original;self.manifest['files'].append(original['files'][0])
        with self.assertRaisesRegex(ReadinessError,'Duplicate'):verify_manifest(self.root,self.write())
    def test_quality_can_produce_manifest_but_research_requires_it(self):
        verify_readiness({},'DATA-QUALITY-001',self.root)
        with self.assertRaisesRegex(ReadinessError,'manifest missing'):
            verify_readiness({},'RESEARCH-001',self.root)

if __name__=='__main__':unittest.main()
