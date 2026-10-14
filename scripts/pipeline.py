#!/usr/bin/env python3
"""OpenReview public metadata → resumable snapshots → assistant annotations → static data.
No PDF downloads, keyword classifier, credentials on disk, or paid model calls.
"""
import argparse
import csv
import hashlib
import gzip
import shutil
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
VENUE = 'ICLR.cc/2027/Conference/Submission'
SOURCE = 'https://openreview.net/group?id=ICLR.cc/2027/Conference#tab-active-submissions'
API = 'https://api2.openreview.net/notes'
SNAPSHOT = ROOT / 'data/raw/snapshot.json'

def now():
    return datetime.now(timezone.utc).isoformat()

def load(path, default=None):
    if not path.exists():
        return default
    return json.loads(gzip.decompress(path.read_bytes())) if path.suffix == '.gz' else json.loads(path.read_text())

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)

def save_compressed(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    path.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))

def value(content, name, default=''):
    v = content.get(name, default)
    return v.get('value', default) if isinstance(v, dict) else v

def strings(v):
    if isinstance(v, list):
        return [str(x) for x in v]
    return [x.strip() for x in str(v or '').replace(';', ',').split(',') if x.strip()]

def normalize(note):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(note.get('id', ''))):
        raise ValueError('非法投稿 ID')
    c = note.get('content', {})
    p = {
        'id': note['id'], 'number': note.get('number'),
        'title': str(value(c, 'title') or ''), 'abstract': str(value(c, 'abstract') or ''),
        'keywords': strings(value(c, 'keywords', [])),
        'primaryArea': value(c, 'primary_area') or '未填写官方方向',
        'venueId': value(c, 'venueid'),
        'modified': note.get('tmdate') or note.get('mdate'),
        'status': 'active' if value(c, 'venueid') == VENUE else 'inactive',
    }
    p['fingerprint'] = fingerprint(p)
    return p

def fingerprint(p):
    content = {k: p.get(k) for k in ['title', 'abstract', 'keywords', 'primaryArea']}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def get_json(params):
    url = API + '?' + urllib.parse.urlencode(params)
    headers = {'Accept': 'application/json', 'User-Agent': 'ICLR2027-Guide-CN/0.1 (public metadata only)'}
    token = os.environ.get('OPENREVIEW_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token.removeprefix('Bearer ')
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in [401, 403]:
                raise RuntimeError('OpenReview 要求登录或浏览器验证；已保留检查点。请通过官方验证流程，不重复请求或绕过验证。') from None
            if e.code == 429 or e.code >= 500:
                if attempt == 4:
                    raise RuntimeError(f'OpenReview HTTP {e.code}，重试失败') from None
                delay = min(30, int(e.headers.get('Retry-After', '0')) or (2 ** attempt))
                time.sleep(delay)
            else:
                raise RuntimeError(f'OpenReview HTTP {e.code}') from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 4:
                raise RuntimeError('OpenReview 网络请求失败；已保留检查点') from e
            time.sleep(2 ** attempt)

def collect(checkpoint, query, request=get_json, page_size=1000):
    """Stable server ordering; every committed page is resumable. Verification catches shifts."""
    state = load(checkpoint, {'offset': 0, 'notes': {}, 'count': None, 'done': False})
    if state['done']:
        return state
    while True:
        result = request({**query, 'limit': page_size, 'offset': state['offset'], 'sort': 'number:asc'})
        batch = result.get('notes')
        if not isinstance(batch, list) or not isinstance(result.get('count'), int):
            raise RuntimeError('API 返回格式不完整，停止采集以避免遗漏')
        state['count'] = result['count']
        for note in batch:
            state['notes'][note['id']] = note
        state['offset'] += len(batch)
        state['done'] = not batch or state['offset'] >= state['count']
        save(checkpoint, state)
        print(f"已保存 {len(state['notes'])} / {state['count']} 条元数据", flush=True)
        if state['done']:
            return state
        time.sleep(0.35)

def reconcile(previous, current, verified):
    """Never infer withdrawals from a failed/partial fetch."""
    result = dict(previous)
    if verified:
        for ident, old in previous.items():
            if ident not in current:
                result[ident] = {**old, 'status': 'inactive'}
    result.update(current)
    return result

def fetch(args):
    run_path = ROOT / 'data/checkpoints/run.json'
    run = load(run_path)
    if args.new or not run or run.get('done'):
        run = {'startedAt': now(), 'runId': str(time.time_ns()), 'done': False}
        save(run_path, run)
    folder = ROOT / 'data/checkpoints' / run['runId']
    query = {'content.venueid': VENUE}
    first = collect(folder / 'pass1.json', query)
    second = collect(folder / 'pass2.json', query)
    verified = (set(first['notes']) == set(second['notes'])
                and len(second['notes']) == second['count'] == first['count'])
    # Read the second pass's newest metadata; retained revisions can be reclassified incrementally.
    notes = second['notes']
    previous = load(SNAPSHOT, {'notes': []})
    old = {n['id']: n for n in previous['notes']}
    current = {i: {**n, '_active': True} for i, n in notes.items()}
    if verified:
        for i, n in old.items():
            if i not in current:
                current[i] = {**n, '_active': False}
    else:
        current = {**old, **current}
    snapshot = {'kind': 'complete' if verified else 'incomplete',
        'startedAt': run['startedAt'], 'finishedAt': now(),
        'verifiedAt': now() if verified else None,
        'officialCount': second['count'], 'failures': 0,
        'notes': list(current.values()),
        'note': '' if verified else '两轮采集的 ID 集合或总数不一致，尚未完成全量核验。'}
    if SNAPSHOT.exists():
        save(ROOT / 'data/raw/history' / (run['runId'] + '.json'), previous)
    save(SNAPSHOT, snapshot)
    run['done'] = True
    save(run_path, run)
    if not verified:
        raise RuntimeError('列表采集期间发生变化；已保留未核验快照，请运行 fetch --new 重新核对。')
    print(f"全量 ID 核验通过：{second['count']} 篇有效投稿。")

def papers_from(snapshot):
    result = {}
    for n in snapshot['notes']:
        p = normalize(n)
        if n.get('_active') is False:
            p['status'] = 'inactive'
        result[p['id']] = p
    return result

def annotations():
    result = {}
    for path in sorted((ROOT / 'data/annotations').glob('*.json')):
        for a in load(path, []):
            if a['id'] in result:
                raise ValueError(f"重复分类记录：{a['id']}")
            result[a['id']] = a
    return result

def validate_annotation(a, p, taxonomy):
    if a.get('sourceFingerprint') != p['fingerprint']:
        raise ValueError('摘要或分类依据已改变，需重新分类')
    if a.get('taxonomyVersion') != taxonomy['version']:
        raise ValueError('分类词表版本不匹配')
    if a.get('classification') not in ['complete', 'review']:
        raise ValueError('分类状态必须是 complete 或 review')
    if a.get('subcategory') not in taxonomy['subcategories']:
        raise ValueError('未知二级分类')
    if not isinstance(a.get('tags'), list) or not set(a['tags']) <= set(taxonomy['tags']):
        raise ValueError('标签必须属于固定词表')
    if not a.get('titleZh') or not a.get('reason'):
        raise ValueError('中文标题和分类依据不能为空')
    if a['classification'] == 'complete':
        if not p['abstract'] or not (50 <= len(a.get('summaryZh', '')) <= 100):
            raise ValueError('完成记录需要摘要和 50–100 字导读')
    if a['subcategory'] == '待复核' and a['classification'] != 'review':
        raise ValueError('待复核类别不能标记完成')

def prepare(args):
    snapshot = load(SNAPSHOT)
    if not snapshot:
        raise RuntimeError('尚无采集快照')
    records = papers_from(snapshot)
    done = annotations()
    taxonomy = load(ROOT / 'data/taxonomy.json')
    groups = {}
    for p in records.values():
        if p['status'] != 'active':
            continue
        a = done.get(p['id'], {})
        if a.get('sourceFingerprint') == p['fingerprint'] and a.get('taxonomyVersion') == taxonomy['version']:
            continue
        groups.setdefault(p['primaryArea'], []).append(p)
    rng = random.Random(2027)
    for group in groups.values():
        rng.shuffle(group)
    ordered = []
    while any(groups.values()):
        for group in groups.values():
            if group:
                ordered.append(group.pop())
    folder = ROOT / 'data/batches' / str(time.time_ns())
    for i in range(0, len(ordered), args.size):
        save(folder / f'batch-{i // args.size + 1:05}.json', ordered[i:i + args.size])
    save(folder / 'calibration.json', ordered[:200])
    print(f'待分类 {len(ordered)} 篇；按官方方向分层抽样与轮转排序。输出：{folder}')

def ingest(args):
    snapshot = load(SNAPSHOT)
    if not snapshot:
        raise RuntimeError('尚无采集快照')
    papers = papers_from(snapshot)
    taxonomy = load(ROOT / 'data/taxonomy.json')
    batch = load(Path(args.file))
    if not isinstance(batch, list):
        raise ValueError('分类文件必须是 JSON 数组')
    seen = set()
    for a in batch:
        if a['id'] in seen or a['id'] not in papers:
            raise ValueError('重复或未知投稿 ID')
        seen.add(a['id'])
        validate_annotation(a, papers[a['id']], taxonomy)
    # One file per ID makes replacement deterministic and avoids duplicate batch merges.
    existing = annotations()
    existing.update({a['id']: a for a in batch})
    save(ROOT / 'data/annotations/records.json', list(existing.values()))
    print(f'校验并保存 {len(batch)} 篇分类。')

def build(args):
    snapshot = load(SNAPSHOT)
    if not snapshot:
        raise RuntimeError('尚无元数据。请先采集或导入已核验的网页样本。')
    taxonomy = load(ROOT / 'data/taxonomy.json')
    classified = annotations()
    raw = papers_from(snapshot)
    topic_specs = [{
        'slug': 'heterogeneous-model-transfer',
        'name': '异构模型合并与迁移',
        'description': '不同模型之间的能力、知识或内部状态合并与迁移；相关性层级不表示论文质量。',
        'file': ROOT / 'data/heterogeneous-transfer-screening.json',
    }]
    topic_members = {}
    topic_manifest = []
    for spec in topic_specs:
        data = load(spec['file'])
        if not data:
            continue
        members = {row['id']: {
            'slug': spec['slug'], 'tier': row['tier'],
            'dimensions': row.get('heterogeneityDimensions', []),
            'forms': row.get('transferForms', []),
        } for row in data.get('records', []) if row.get('tier') in ['core', 'method-reference']}
        topic_members.update({(spec['slug'], ident): value for ident, value in members.items()})
        topic_manifest.append({'slug': spec['slug'], 'name': spec['name'], 'description': spec['description'],
            'count': len(members), 'core': sum(v['tier'] == 'core' for v in members.values()),
            'methodReference': sum(v['tier'] == 'method-reference' for v in members.values())})
    index, details, search = [], {}, []
    for p in sorted(raw.values(), key=lambda p: ((p['number'] or 0), p['id']), reverse=True):
        a = classified.get(p['id'])
        if a:
            try:
                validate_annotation(a, p, taxonomy)
            except ValueError:
                a = None
        item = {k: v for k, v in p.items() if k not in ['abstract', 'venueId']}
        paper_topics = [value for (slug, ident), value in topic_members.items() if ident == p['id']]
        item.update({'areaZh': taxonomy['areaLabels'].get(p['primaryArea'], p['primaryArea']),
            'titleZh': a['titleZh'] if a else '', 'summaryZh': a.get('summaryZh', '') if a else '',
            'subcategory': a['subcategory'] if a else '待分类', 'tags': a['tags'] if a else [],
            'classification': a['classification'] if a else 'pending',
            'rating': None, 'topics': paper_topics, 'detail': f"data/details-{len(index) // 500:04}.json.gz"})
        index.append(item)
        details[p['id']] = {**item, 'abstract': p['abstract'], 'classificationReason': a['reason'] if a else ''}
        search.append({'id': p['id'], 'text': ' '.join([p['title'], item['titleZh'], item['summaryZh'],
            p['abstract'], p['primaryArea'], item['areaZh'], item['subcategory'], *p['keywords'], *item['tags']])})
    active = [p for p in index if p['status'] == 'active']
    area_groups, tags = {}, {}
    for p in active:
        area = area_groups.setdefault(p['primaryArea'], {'name': p['primaryArea'], 'label': p['areaZh'], 'count': 0, 'subs': {}})
        area['count'] += 1
        sub = p['subcategory']
        area['subs'][sub] = area['subs'].get(sub, 0) + 1
        for t in p['tags']:
            tags[t] = tags.get(t, 0) + 1
    areas = []
    for area in sorted(area_groups.values(), key=lambda g: (-g['count'], g['name'])):
        area['subcategories'] = [{'name': k, 'count': v} for k, v in sorted(area.pop('subs').items(), key=lambda i: (-i[1], i[0]))]
        areas.append(area)
    folder = ROOT / 'public/data'
    # Rebuild generated assets in a staging directory; old shards cannot leak into a release.
    staging = ROOT / 'public/data-next'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    detail_rows = list(details.values())
    detail_shards = []
    for i in range(0, len(detail_rows), 500):
        name = f'details-{i // 500:04}.json.gz'
        save_compressed(staging / name, detail_rows[i:i+500])
        detail_shards.append('data/' + name)
    shards = []
    for i in range(0, len(search), 1500):
        name = f'search-{i // 1500:04}.json.gz'
        save_compressed(staging / name, search[i:i+1500])
        shards.append('data/' + name)
    manifest = {'schemaVersion': 2, 'publicationMode': 'metadata-preview', 'indexUrl': 'data/index.json.gz', 'detailShards': detail_shards, 'sourceUrl': SOURCE, 'snapshotKind': snapshot['kind'],
        'startedAt': snapshot['startedAt'], 'finishedAt': snapshot['finishedAt'],
        'verifiedAt': snapshot.get('verifiedAt'), 'officialCount': snapshot.get('officialCount'),
        'total': len(active), 'inactive': len(index) - len(active),
        'classified': sum(p['classification'] == 'complete' for p in active),
        'review': sum(p['classification'] == 'review' for p in active),
        'pending': sum(p['classification'] == 'pending' for p in active),
        'missingAbstract': sum(not raw[p['id']]['abstract'] for p in active),
        'failures': snapshot.get('failures', 0), 'note': snapshot.get('note', ''),
        'taxonomyVersion': taxonomy['version'], 'taxonomyStage': taxonomy['stage'],
        'areas': areas, 'tags': [{'name': k, 'count': v} for k, v in sorted(tags.items(), key=lambda i: (-i[1], i[0]))],
        'topics': topic_manifest,
        'searchShards': shards, 'activeIdSetSha256': hashlib.sha256('\n'.join(sorted(p['id'] for p in active)).encode()).hexdigest()}
    save_compressed(staging / 'index.json.gz', index)
    save(staging / 'manifest.json', manifest)
    save(staging / 'taxonomy.json', taxonomy)
    if folder.exists():
        shutil.rmtree(folder)
    staging.replace(folder)
    print(json.dumps({k: v for k, v in manifest.items() if k not in ['areas', 'tags', 'searchShards', 'detailShards']}, ensure_ascii=False, indent=2))

def check(args):
    folder = ROOT / 'public/data'
    m = load(folder / 'manifest.json')
    rows = load(ROOT / 'public' / m['indexUrl']) if m and m.get('indexUrl') else load(folder / 'index.json')
    assert m and rows is not None, '缺少发布数据'
    assert len({p['id'] for p in rows}) == len(rows), '重复投稿 ID'
    active = [p for p in rows if p['status'] == 'active']
    assert len(active) == m['total'] == sum(a['count'] for a in m['areas']), '数量不一致'
    assert m['classified'] + m['pending'] + m['review'] == m['total'], '分类进度不一致'
    for state, key in [('complete','classified'), ('pending','pending'), ('review','review')]:
        assert sum(p['classification'] == state for p in active) == m[key], '分类实际状态不一致'
    for topic in m.get('topics', []):
        members = [p for p in active if any(t.get('slug') == topic['slug'] for t in p.get('topics', []))]
        assert len(members) == topic['count'], '专题数量不一致'
        assert sum(any(t.get('slug') == topic['slug'] and t.get('tier') == 'core' for t in p.get('topics', [])) for p in active) == topic['core'], '专题核心数量不一致'
        assert sum(any(t.get('slug') == topic['slug'] and t.get('tier') == 'method-reference' for t in p.get('topics', [])) for p in active) == topic['methodReference'], '专题方法参考数量不一致'
    for area in m['areas']:
        group = [p for p in active if p['primaryArea'] == area['name']]
        assert len(group) == area['count'], '官方方向数量不一致'
        assert sum(s['count'] for s in area['subcategories']) == len(group), '细类合计不一致'
        for sub in area['subcategories']:
            assert sum(p['subcategory'] == sub['name'] for p in group) == sub['count'], '细类数量不一致'
    if m.get('activeIdSetSha256'):
        assert hashlib.sha256('\n'.join(sorted(p['id'] for p in active)).encode()).hexdigest() == m['activeIdSetSha256'], 'ID 集合指纹不一致'
    detail_map = {}
    for path in dict.fromkeys(p['detail'] for p in rows):
        data = load(ROOT / 'public' / path)
        for d in data if isinstance(data, list) else [data]:
            assert d['id'] not in detail_map, '重复摘要详情'
            detail_map[d['id']] = d
    assert set(detail_map) == {p['id'] for p in rows}, '详情集合不一致'
    for p in rows:
        detail = detail_map[p['id']]
        assert detail['fingerprint'] == p['fingerprint'], '详情指纹不一致'
    assert sum(not detail_map[p['id']]['abstract'] for p in active) == m['missingAbstract']
    search_ids = [p['id'] for shard in m['searchShards'] for p in load(ROOT / 'public' / shard)]
    assert set(search_ids) == {p['id'] for p in rows} and len(search_ids) == len(rows), '搜索索引不一致'
    if m['snapshotKind'] == 'complete':
        assert m['officialCount'] == len(active) and m['verifiedAt'], '全量覆盖未经核验'
    if args.release:
        assert m['snapshotKind'] == 'complete', '尚非完整快照，不允许作为全量站发布'
        assert m['pending'] == 0, '仍有未处理投稿'
        assert m['taxonomyStage'] == 'calibrated', '尚未完成约 200 篇词表校准'
        qa = load(ROOT / 'data/qa.json', {})
        assert qa.get('snapshotFinishedAt') == m['finishedAt'], '缺少当前快照的分类复核记录'
        for area in m['areas']:
            ids = {p['id'] for p in active if p['primaryArea'] == area['name']}
            assert len(ids & set(qa.get('reviewedIds', []))) >= min(10, len(ids)), '一级方向抽查不足'
    print('数据结构、数量、详情和搜索索引校验通过。')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fetch'); p.add_argument('--new', action='store_true'); p.set_defaults(fn=fetch)
    p = sub.add_parser('prepare'); p.add_argument('--size', type=int, default=20); p.set_defaults(fn=prepare)
    p = sub.add_parser('ingest'); p.add_argument('file'); p.set_defaults(fn=ingest)
    p = sub.add_parser('build'); p.set_defaults(fn=build)
    p = sub.add_parser('check'); p.add_argument('--release', action='store_true'); p.set_defaults(fn=check)
    args = parser.parse_args()
    if getattr(args, 'size', 1) < 1:
        parser.error('--size must be positive')
    try:
        args.fn(args)
    except (RuntimeError, ValueError, AssertionError) as e:
        print(f'未完成：{e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
