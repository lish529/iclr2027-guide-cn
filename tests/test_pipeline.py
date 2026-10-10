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

    def test_sharded_build_is_complete_deterministic_and_not_classified_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / 'data/raw/snapshot.json'
            p.save(snapshot, {'kind':'complete', 'notes':[note(str(i)) for i in range(501)],
                'startedAt':'2026-10-10', 'finishedAt':'2026-10-10', 'verifiedAt':'2026-10-10',
                'officialCount':501})
            p.save(root / 'data/taxonomy.json', {'version':'draft','stage':'draft',
                'areaLabels':{'optimization':'优化'},'tags':[],'subcategories':['待复核']})
            args = type('Args', (), {'release':False})()
            with patch.object(p, 'ROOT', root), patch.object(p, 'SNAPSHOT', snapshot), patch('builtins.print'):
                p.build(args)
                p.check(args)
                m = p.load(root / 'public/data/manifest.json')
                self.assertEqual(m['pending'],501)
                self.assertEqual(len(m['detailShards']),2)
                self.assertEqual(len(p.load(root / 'public' / m['detailShards'][1])),1)
                with self.assertRaisesRegex(AssertionError, '仍有未处理投稿'):
                    p.check(type('Args', (), {'release':True})())
                before = {f.name:f.read_bytes() for f in (root / 'public/data').glob('*.gz')}
                (root / 'public/data/obsolete.json').write_text('{}')
                p.build(args)
                after = {f.name:f.read_bytes() for f in (root / 'public/data').glob('*.gz')}
                self.assertEqual(before,after)
                self.assertFalse((root / 'public/data/obsolete.json').exists())
                m['classified'] = 1
                m['pending'] -= 1
                p.save(root / 'public/data/manifest.json',m)
                with self.assertRaisesRegex(AssertionError,'分类实际状态不一致'):
                    p.check(args)

if __name__ == '__main__':
    unittest.main()
