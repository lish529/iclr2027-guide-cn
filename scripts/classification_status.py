#!/usr/bin/env python3
"""Audit local annotation coverage without rebuilding or publishing the website.
This validates structure and coverage, not semantic accuracy or final QA.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import pipeline as p


def audit(snapshot, records, taxonomy):
    papers = p.papers_from(snapshot)
    active = {i: row for i, row in papers.items() if row['status'] == 'active'}
    counts = Counter(complete=0, review=0, missing=0, invalid=0)
    missing, invalid, review, other, issues = [], [], [], [], []
    groups = {}
    for ident, row in active.items():
        group = groups.setdefault(row['primaryArea'], Counter(total=0, complete=0, review=0, missing=0, invalid=0))
        group['total'] += 1
        a = records.get(ident)
        if a is None:
            state = 'missing'; missing.append(ident)
        else:
            try:
                p.validate_annotation(a, row, taxonomy)
                state = a['classification']
                if state == 'review':
                    review.append({'id': ident, 'reason': a['reason']})
                if a['subcategory'] == '其他': other.append(ident)
                if len(a['tags']) > 5 or len(a['tags']) != len(set(a['tags'])):
                    issues.append({'id': ident, 'issue': '标签超过 5 个或重复'})
                if not a.get('method'):
                    issues.append({'id': ident, 'issue': '缺少生成方式记录 method'})
            except (ValueError, KeyError, TypeError) as e:
                state = 'invalid'; invalid.append({'id': ident, 'reason': str(e)})
        counts[state] += 1; group[state] += 1
    unknown = sorted(set(records) - set(papers))
    verified = (snapshot.get('kind') == 'complete' and bool(snapshot.get('verifiedAt'))
                and snapshot.get('officialCount') == len(active))
    processed = bool(active) and verified and not (missing or invalid or unknown or issues)
    return {
        'schemaVersion': 1, 'generatedAt': p.now(),
        'snapshotFinishedAt': snapshot.get('finishedAt'),
        'snapshotVerified': verified,
        'activeIdSetSha256': hashlib.sha256('\n'.join(sorted(active)).encode()).hexdigest(),
        'taxonomyVersion': taxonomy['version'], 'taxonomyStage': taxonomy.get('stage'),
        'total': len(active), **dict(counts),
        'unprocessed': len(missing) + len(invalid),
        'allActiveProcessed': processed,
        'scope': '结构与覆盖检查；不能替代摘要忠实度、分类准确性和最终质量抽查。',
        'areas': [{'name': name, **dict(count)} for name, count in sorted(groups.items())],
        'missingIds': missing, 'invalidRecords': invalid,
        'reviewQueue': review, 'otherIds': other, 'unknownIds': unknown,
        'protocolIssues': issues,
        'retainedInactiveAnnotations': sum(i in records for i, row in papers.items() if row['status'] != 'active'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', type=Path, help='Save full coverage report including missing/review IDs')
    parser.add_argument('--require-processed', action='store_true', help='Fail unless all active IDs have structurally valid records')
    args = parser.parse_args()
    snapshot = p.load(p.SNAPSHOT)
    if not snapshot: raise ValueError('本地原始快照不存在；不能只依靠已发布网页统计接续')
    report = audit(snapshot, p.annotations(), p.load(p.ROOT / 'data/taxonomy.json'))
    if args.write: p.save(args.write, report)
    print(json.dumps({k: report[k] for k in ['total','complete','review','missing','invalid','unprocessed','allActiveProcessed','taxonomyVersion','taxonomyStage']}, ensure_ascii=False, indent=2))
    print('协议问题:', len(report['protocolIssues']), '未知 ID:', len(report['unknownIds']))
    if args.require_processed and not report['allActiveProcessed']: return 1
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as e:
        print(f'无法完成覆盖核验：{e}', file=sys.stderr); sys.exit(1)
