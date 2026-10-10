import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pipeline', Path(__file__).resolve().parents[1] / 'scripts/pipeline.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

def note(ident, abstract='abstract', **extra):
    return {'id': ident, 'number': int(ident) if ident.isdigit() else 1,
            'content': {'title': {'value': 'title'}, 'abstract': {'value': abstract},
                        'primary_area': {'value': 'optimization'}, 'venueid': {'value': p.VENUE}}, **extra}

class PipelineTests(unittest.TestCase):
    def test_resume_after_network_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(p.time, 'sleep'):
            cp = Path(folder) / 'checkpoint.json'
            def fail_on_second(params):
                if params['offset']:
                    raise RuntimeError('network interrupted')
                return {'count': 3, 'notes': [note('1'), note('2')]}
            with self.assertRaises(RuntimeError):
                p.collect(cp, {}, fail_on_second, 2)
            offsets = []
            def resume(params):
                offsets.append(params['offset'])
                return {'count': 3, 'notes': [note('3')]}
            result = p.collect(cp, {}, resume, 2)
            self.assertEqual(offsets, [2])
            self.assertEqual(set(result['notes']), {'1', '2', '3'})
            self.assertTrue(result['done'])
            p.collect(cp, {}, lambda _: self.fail('completed checkpoint fetched again'), 2)

    def test_duplicate_ids_cannot_inflate_unique_coverage(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(p.time, 'sleep'):
            result = p.collect(Path(folder) / 'c.json', {},
                lambda q: {'count': 2, 'notes': [note('1'), note('1')]}, 2)
            self.assertNotEqual(len(result['notes']), result['count'])

    def test_modification_invalidates_only_changed_classification_inputs(self):
        first = p.normalize(note('1'))
        modified = p.normalize(note('1', tmdate=99))
        changed = p.normalize(note('1', 'changed abstract'))
        self.assertEqual(first['fingerprint'], modified['fingerprint'])
        self.assertNotEqual(first['fingerprint'], changed['fingerprint'])

    def test_partial_fetch_never_marks_missing_papers_withdrawn(self):
        old = {i: p.normalize(note(i)) for i in ['1', '2']}
        current = {'2': p.normalize(note('2')), '3': p.normalize(note('3'))}
        partial = p.reconcile(old, current, False)
        self.assertEqual(partial['1']['status'], 'active')
        full = p.reconcile(old, current, True)
        self.assertEqual(full['1']['status'], 'inactive')
        self.assertEqual(full['3']['status'], 'active')
        self.assertEqual(p.reconcile(full, current, True), full)

    def test_annotations_cannot_silently_use_stale_abstract_or_empty_summary(self):
        paper = p.normalize(note('1'))
        taxonomy = {'version': 'v1', 'subcategories': ['优化'], 'tags': ['效率']}
        a = {'classification': 'complete', 'subcategory': '优化', 'tags': ['效率'],
             'titleZh': '优化方法', 'summaryZh': '研究' * 30, 'reason': '摘要说明优化问题',
             'sourceFingerprint': paper['fingerprint'], 'taxonomyVersion': 'v1'}
        p.validate_annotation(a, paper, taxonomy)
        for invalid in [{'sourceFingerprint': 'stale'}, {'summaryZh': ''}, {'tags': ['invented']}, {'taxonomyVersion': 'v0'}]:
            with self.assertRaises(ValueError):
                p.validate_annotation({**a, **invalid}, paper, taxonomy)

    def test_missing_abstract_and_unsafe_id(self):
        self.assertEqual(p.normalize(note('1', None))['abstract'], '')
        with self.assertRaises(ValueError):
            p.normalize(note('../escape'))

    def test_checked_in_sample_cannot_pass_full_release_gate(self):
        m = p.load(p.ROOT / 'public/data/manifest.json')
        if m['snapshotKind'] != 'complete':
            with self.assertRaisesRegex(AssertionError, '尚非完整快照'):
                p.check(type('Args', (), {'release': True})())

if __name__ == '__main__':
    unittest.main()
