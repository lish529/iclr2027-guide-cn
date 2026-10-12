import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import classification_status as c


def note(ident):
    return {'id':ident,'content':{'title':{'value':'A title'},'abstract':{'value':'Full abstract'},
            'primary_area':{'value':'optimization'},'venueid':{'value':c.p.VENUE}}}

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {'kind':'complete','verifiedAt':'time','finishedAt':'time','officialCount':2,'notes':[note('a'),note('b')]}
        self.taxonomy = {'version':'v1','stage':'draft','subcategories':['优化','待复核'],'tags':['效率']}
        self.a = {'id':'a','sourceFingerprint':c.p.normalize(note('a'))['fingerprint'],
                  'taxonomyVersion':'v1','classification':'complete','titleZh':'中文标题','summaryZh':'研究问题与方法'*10,
                  'subcategory':'优化','tags':['效率'],'reason':'摘要支持','method':'model-read-full-abstract'}

    def test_missing_and_stale_remain_unprocessed(self):
        report = c.audit(self.snapshot, {'a':self.a}, self.taxonomy)
        self.assertEqual((report['complete'],report['missing']), (1,1))
        self.assertFalse(report['allActiveProcessed'])
        stale = {**self.a,'sourceFingerprint':'old'}
        report = c.audit(self.snapshot, {'a':stale}, self.taxonomy)
        self.assertEqual((report['invalid'],report['unprocessed']),(1,2))

    def test_review_is_processed_but_not_claimed_complete_or_semantically_approved(self):
        b={**self.a,'id':'b','classification':'review','subcategory':'待复核','reason':'边界需要人工核对'}
        report=c.audit(self.snapshot,{'a':self.a,'b':b},self.taxonomy)
        self.assertTrue(report['allActiveProcessed'])
        self.assertEqual((report['complete'],report['review']),(1,1))
        self.assertEqual(report['reviewQueue'][0]['id'],'b')
        self.assertEqual(report['taxonomyStage'],'draft')

    def test_unknown_ids_protocol_issues_and_unverified_snapshot_block_completion(self):
        b={**self.a,'id':'b'}
        for records,snapshot in [
            ({'a':self.a,'b':b,'outside':self.a},self.snapshot),
            ({'a':{**self.a,'tags':['效率']*6},'b':b},self.snapshot),
            ({'a':self.a,'b':b},{**self.snapshot,'kind':'incomplete'}),
        ]:
            self.assertFalse(c.audit(snapshot,records,self.taxonomy)['allActiveProcessed'])

if __name__ == '__main__':unittest.main()
