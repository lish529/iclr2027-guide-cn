"""Import the eight explicitly observed public browser records; never claim full coverage."""
from pipeline import ROOT, SNAPSHOT, VENUE, load, save, now, normalize, validate_annotation

if SNAPSHOT.exists():
    raise SystemExit('已有快照，不覆盖；此脚本仅用于第一次载入已观察到的网页样本。')
samples = load(ROOT / 'data/browser-samples.json')
taxonomy = load(ROOT / 'data/taxonomy.json')
notes, annotations = [], []
for sample in samples:
    note = {'id': sample['id'], 'number': sample['number'],
        '_source': 'Public OpenReview active-submission page, expanded visible DOM',
        '_modifiedDisplay': '19 Sept 2026 (modified: 06 Oct 2026)',
        'content': {k: {'value': sample[k]} for k in ['title', 'abstract', 'primary_area', 'keywords']}}
    note['content']['venueid'] = {'value': VENUE}
    notes.append(note)
    record = normalize(note)
    a = {k: sample[k] for k in ['id', 'titleZh', 'summaryZh', 'subcategory', 'tags', 'reason']}
    a.update({'classification': 'complete', 'sourceFingerprint': record['fingerprint'],
        'taxonomyVersion': taxonomy['version'], 'annotatedAt': now(), 'method': 'assistant-read-full-abstract'})
    validate_annotation(a, record, taxonomy)
    annotations.append(a)
save(SNAPSHOT, {'kind': 'sample', 'startedAt': now(), 'finishedAt': now(),
    'officialCount': None, 'verifiedAt': None, 'failures': 1,
    'note': '仅收录从公开网页读取并逐篇整理的 8 篇真实样本；API 要求验证，全量投稿数量尚未核验，分类词表尚待约 200 篇分层样本校准。',
    'notes': notes})
save(ROOT / 'data/annotations/records.json', annotations)
print(f'导入 {len(notes)} 篇网页样本及人工阅读摘要后的中文分类。')
