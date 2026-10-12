#!/usr/bin/env python3
"""Prepare, validate, and consolidate the post-training-geometry priority set.

Semantic decisions are supplied by the current assistant through saved JSON
results.  This module only handles deterministic recall, batching, provenance,
strict validation, and handoff to the existing annotation pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pipeline


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/research-interest"
SCREEN_BATCHES = WORK / "screen-batches"
SCREEN_RESULTS = WORK / "screen-results"
AUDIT_BATCHES = WORK / "audit-batches"
AUDIT_RESULTS = WORK / "audit-results"
AUDIT_ADJUDICATION_BATCHES = WORK / "audit-adjudication-batches"
AUDIT_ADJUDICATION_RESULTS = WORK / "audit-adjudication-results"
ADJUDICATION_BATCHES = WORK / "adjudication-batches"
ADJUDICATION_RESULTS = WORK / "adjudication-results"
ANNOTATION_BATCHES = WORK / "annotation-batches"
ANNOTATION_RESULTS = WORK / "annotation-results"
QA_BATCHES = WORK / "qa-batches"
QA_RESULTS = WORK / "qa-results"
SCREENING = ROOT / "data/research-interest-screening.json"
REPORT = ROOT / "data/research-interest-report.json"
RESULT = ROOT / "work/classification-results/research-interest.json"

GROUPS = {
    "weightUpdateGeometry": [
        r"weight space", r"parameter space", r"weight-space", r"parameter-space",
        r"mode connectivity", r"loss landscape", r"linear mode", r"low[- ]rank update",
        r"update subspace", r"task vector", r"model vector", r"parameter delta",
        r"weight delta", r"weight update",
    ],
    "crossModelAlignment": [
        r"cross[- ]architecture", r"across architectures", r"model alignment",
        r"weight matching", r"permutation alignment", r"neuron alignment",
        r"representation alignment", r"cross[- ]model", r"model stitching",
        r"functional alignment",
    ],
    "mergingTransfer": [
        r"model merging", r"model merge", r"merge models", r"merging models",
        r"task arithmetic", r"model soup", r"parameter transfer", r"knowledge transfer",
    ],
    "postTraining": [
        r"post[- ]training", r"fine[- ]tuning", r"finetuning", r"instruction tuning",
        r"reinforcement learning", r"RLHF", r"RLAIF", r"distillation",
        r"supervised fine[- ]tuning", r"\bSFT\b",
    ],
    "functionalGeometry": [
        r"functional space", r"function space", r"feature geometry",
        r"representation geometry", r"neural tangent", r"Fisher information",
        r"\bCKA\b", r"centered kernel alignment", r"procrustes", r"subspace angle",
    ],
    "interpretability": [
        r"mechanistic interpretability", r"interpretability", r"circuit",
        r"feature attribution", r"causal tracing",
    ],
}
COMPILED = {name: [re.compile(pattern, re.I) for pattern in patterns] for name, patterns in GROUPS.items()}
CORE_GROUPS = ("weightUpdateGeometry", "crossModelAlignment", "mergingTransfer")
SUPPORT_GROUPS = ("postTraining", "functionalGeometry", "interpretability")
TIERS = {"core", "method-reference", "exclude"}
QUESTIONS = {
    "training-method-comparison", "cross-architecture-transfer", "parameter-alignment",
    "function-space-comparison", "update-subspace", "task-vector-merging",
    "capability-mechanism", "mathematical-tool", "other-related",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def reset_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for file in path.glob("*.json"):
        file.unlink()


def load_context():
    snapshot = pipeline.load(pipeline.SNAPSHOT)
    taxonomy = pipeline.load(ROOT / "data/taxonomy.json")
    papers = pipeline.papers_from(snapshot)
    active = {ident: paper for ident, paper in papers.items() if paper["status"] == "active"}
    records = pipeline.annotations()
    return snapshot, taxonomy, active, records


def recall_row(paper):
    text = " ".join([paper["title"], paper["abstract"], " ".join(paper["keywords"])])
    hits = {name: [pattern.pattern for pattern in patterns if pattern.search(text)] for name, patterns in COMPILED.items()}
    core = sum(bool(hits[name]) for name in CORE_GROUPS)
    support = sum(bool(hits[name]) for name in SUPPORT_GROUPS)
    if not ((core >= 1 and support >= 1) or core >= 2):
        return None
    return {
        "id": paper["id"], "fingerprint": paper["fingerprint"], "title": paper["title"],
        "abstract": paper["abstract"], "keywords": paper["keywords"],
        "primaryArea": paper["primaryArea"], "recallGroups": [name for name, values in hits.items() if values],
        "matchedPatterns": {name: values for name, values in hits.items() if values},
        "recallScore": core * 10 + support,
    }


def write_batches(folder: Path, rows: list[dict], size: int, prefix: str) -> None:
    reset_folder(folder)
    for index in range(0, len(rows), size):
        save(folder / f"{prefix}-{index // size + 1:04}.json", rows[index:index + size])


def screening_schema() -> dict:
    return {
        "type": "object", "additionalProperties": False, "required": ["decisions"],
        "properties": {"decisions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "tier", "researchQuestions", "reason"],
            "properties": {
                "id": {"type": "string"}, "tier": {"type": "string", "enum": sorted(TIERS)},
                "researchQuestions": {"type": "array", "minItems": 1, "maxItems": 4,
                    "items": {"type": "string", "enum": sorted(QUESTIONS)}},
                "reason": {"type": "string", "minLength": 12, "maxLength": 260},
            },
        }}},
    }


def annotation_schema(taxonomy) -> dict:
    return {
        "type": "object", "additionalProperties": False, "required": ["annotations"],
        "properties": {"annotations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "titleZh", "summaryZh", "subcategory", "tags", "reason"],
            "properties": {
                "id": {"type": "string"}, "titleZh": {"type": "string", "minLength": 1},
                "summaryZh": {"type": "string", "minLength": 50, "maxLength": 100},
                "subcategory": {"type": "string", "enum": taxonomy["subcategories"]},
                "tags": {"type": "array", "maxItems": 5,
                    "items": {"type": "string", "enum": taxonomy["tags"]}},
                "reason": {"type": "string", "minLength": 8, "maxLength": 220},
            },
        }}},
    }


def qa_schema(taxonomy) -> dict:
    semantic = annotation_schema(taxonomy)["properties"]["annotations"]["items"]["properties"]
    return {
        "type": "object", "additionalProperties": False, "required": ["reviews"],
        "properties": {"reviews": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "verdict", "note", "corrected"],
            "properties": {
                "id": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "corrected"]},
                "note": {"type": "string", "minLength": 8, "maxLength": 220},
                "corrected": {"anyOf": [
                    {"type": "null"},
                    {"type": "object", "additionalProperties": False,
                     "required": ["titleZh", "summaryZh", "subcategory", "tags", "reason"],
                     "properties": {key: value for key, value in semantic.items() if key != "id"}},
                ]},
            },
        }}},
    }


def prepare(args):
    snapshot, taxonomy, active, records = load_context()
    rows = [row for paper in active.values() if (row := recall_row(paper))]
    rows.sort(key=lambda row: (-row["recallScore"], row["id"]))
    manifest = {
        "schemaVersion": 1, "generatedAt": now(), "snapshotFinishedAt": snapshot.get("finishedAt"),
        "activeIdSetSha256": hashlib.sha256("\n".join(sorted(active)).encode()).hexdigest(),
        "candidateCount": len(rows), "batchSize": args.size,
        "criteria": "关键词仅用于高召回；最终层级必须逐篇完整阅读摘要后决定。",
    }
    save(WORK / "manifest.json", manifest)
    save(WORK / "candidates.json", rows)
    save(WORK / "screen-schema.json", screening_schema())
    save(WORK / "annotation-schema.json", annotation_schema(taxonomy))
    save(WORK / "qa-schema.json", qa_schema(taxonomy))
    write_batches(SCREEN_BATCHES, rows, args.size, "screen")
    print(json.dumps({"candidates": len(rows), "batches": (len(rows) + args.size - 1) // args.size}, ensure_ascii=False))


def read_result(path: Path, field: str):
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get(field), list):
        raise ValueError(f"{path}: 缺少 {field} 数组")
    return value[field]


def collect_results(folder: Path, field: str, expected: set[str]):
    result = {}
    files = sorted(folder.glob("*.json"))
    for path in files:
        for row in read_result(path, field):
            ident = row.get("id")
            if ident in result or ident not in expected:
                raise ValueError(f"{path}: 重复或未知 ID {ident}")
            result[ident] = row
    return result, files


def validate_decision(row):
    if row.get("tier") not in TIERS:
        raise ValueError(f"{row.get('id')}: tier 非法")
    questions = row.get("researchQuestions")
    if not isinstance(questions, list) or not questions or len(questions) > 4 or not set(questions) <= QUESTIONS:
        raise ValueError(f"{row.get('id')}: researchQuestions 非法")
    if len(str(row.get("reason", ""))) < 12:
        raise ValueError(f"{row.get('id')}: reason 过短")


def consolidate_screen(args):
    candidates = json.loads((WORK / "candidates.json").read_text())
    by_id = {row["id"]: row for row in candidates}
    decisions, files = collect_results(SCREEN_RESULTS, "decisions", set(by_id))
    if set(decisions) != set(by_id):
        raise ValueError(f"初筛未覆盖全部候选：{len(decisions)} / {len(by_id)}")
    for row in decisions.values():
        validate_decision(row)
    combined = []
    for ident, source in by_id.items():
        decision = decisions[ident]
        combined.append({
            "id": ident, "sourceFingerprint": source["fingerprint"], "title": source["title"],
            "primaryArea": source["primaryArea"], "recallGroups": source["recallGroups"],
            "tier": decision["tier"], "researchQuestions": decision["researchQuestions"],
            "reason": decision["reason"], "screenedAt": now(), "nearMissAudit": False,
        })
    save(WORK / "initial-screening.json", combined)
    excluded = [row for row in combined if row["tier"] == "exclude"]
    # Select the strongest near misses while preventing one official area from dominating.
    source_rank = {row["id"]: row["recallScore"] for row in candidates}
    groups = defaultdict(list)
    for row in excluded:
        groups[row["primaryArea"]].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: (-source_rank[row["id"]], row["id"]))
    sample = []
    while len(sample) < min(args.audit_size, len(excluded)) and any(groups.values()):
        for area in sorted(groups):
            if groups[area] and len(sample) < args.audit_size:
                sample.append(groups[area].pop(0))
    audit_rows = []
    for row in sample:
        source = by_id[row["id"]]
        audit_rows.append({**source, "initialDecision": row})
    save(WORK / "audit-sample.json", audit_rows)
    write_batches(AUDIT_BATCHES, audit_rows, args.audit_batch_size, "audit")
    print(json.dumps({"screened": len(combined), "tiers": Counter(r["tier"] for r in combined),
                      "auditSample": len(audit_rows), "resultFiles": len(files)}, ensure_ascii=False))


def prepare_adjudication(args):
    initial = json.loads((WORK / "initial-screening.json").read_text())
    candidates = {row["id"]: row for row in json.loads((WORK / "candidates.json").read_text())}
    selected = [{**candidates[row["id"]], "initialDecision": row} for row in initial if row["tier"] != "exclude"]
    write_batches(ADJUDICATION_BATCHES, selected, args.size, "adjudication")
    print(json.dumps({"selectedForIndependentAdjudication": len(selected), "batches": (len(selected) + args.size - 1) // args.size}, ensure_ascii=False))


def prepare_audit_adjudication(args):
    """Strictly adjudicate near-miss papers that the audit proposes to promote."""
    candidates = {row["id"]: row for row in json.loads((WORK / "candidates.json").read_text())}
    sample = json.loads((WORK / "audit-sample.json").read_text())
    expected = {row["id"] for row in sample}
    audits, _ = collect_results(AUDIT_RESULTS, "decisions", expected)
    if set(audits) != expected:
        raise ValueError(f"近邻复核未覆盖完整：{len(audits)} / {len(expected)}")
    promoted = [{**candidates[ident], "initialDecision": decision}
                for ident, decision in audits.items() if decision["tier"] != "exclude"]
    promoted.sort(key=lambda row: row["id"])
    write_batches(AUDIT_ADJUDICATION_BATCHES, promoted, args.size, "audit-adjudication")
    print(json.dumps({"promotedForIndependentAdjudication": len(promoted),
                      "batches": (len(promoted) + args.size - 1) // args.size}, ensure_ascii=False))


def apply_adjudication(_args):
    initial = json.loads((WORK / "initial-screening.json").read_text())
    by_id = {row["id"]: row for row in initial}
    expected = {ident for ident, row in by_id.items() if row["tier"] != "exclude"}
    decisions, files = collect_results(ADJUDICATION_RESULTS, "decisions", expected)
    if set(decisions) != expected:
        raise ValueError(f"独立纳入裁决未覆盖完整：{len(decisions)} / {len(expected)}")
    for ident, decision in decisions.items():
        validate_decision(decision)
        row = by_id[ident]
        row["preAdjudicationTier"] = row["tier"]
        row["preAdjudicationReason"] = row["reason"]
        row["tier"] = decision["tier"]
        row["researchQuestions"] = decision["researchQuestions"]
        row["reason"] = decision["reason"]
        row["adjudicatedAt"] = now()
    save(WORK / "initial-screening.json", list(by_id.values()))
    print(json.dumps({"adjudicated": len(decisions), "tiers": Counter(row["tier"] for row in by_id.values()), "resultFiles": len(files)}, ensure_ascii=False))


def finalize_screen(args):
    initial = json.loads((WORK / "initial-screening.json").read_text())
    by_id = {row["id"]: row for row in initial}
    sample = json.loads((WORK / "audit-sample.json").read_text())
    audit_expected = {row["id"] for row in sample}
    audits, files = collect_results(AUDIT_RESULTS, "decisions", audit_expected)
    if set(audits) != audit_expected:
        raise ValueError(f"近邻复核未覆盖完整：{len(audits)} / {len(audit_expected)}")
    for ident, decision in audits.items():
        validate_decision(decision)
        row = by_id[ident]
        row["nearMissAudit"] = True
        row["initialTier"] = row["tier"]
        row["initialReason"] = row["reason"]
        row["tier"] = decision["tier"]
        row["researchQuestions"] = decision["researchQuestions"]
        row["reason"] = decision["reason"]
        row["auditedAt"] = now()
    promoted = {ident for ident, decision in audits.items() if decision["tier"] != "exclude"}
    strict, strict_files = collect_results(AUDIT_ADJUDICATION_RESULTS, "decisions", promoted)
    if set(strict) != promoted:
        raise ValueError(f"近邻晋级独立裁决未覆盖完整：{len(strict)} / {len(promoted)}")
    for ident, decision in strict.items():
        validate_decision(decision)
        row = by_id[ident]
        row["preAuditAdjudicationTier"] = row["tier"]
        row["preAuditAdjudicationReason"] = row["reason"]
        row["tier"] = decision["tier"]
        row["researchQuestions"] = decision["researchQuestions"]
        row["reason"] = decision["reason"]
        row["auditAdjudicatedAt"] = now()
    final = sorted(by_id.values(), key=lambda row: ({"core": 0, "method-reference": 1, "exclude": 2}[row["tier"]], row["id"]))
    payload = {
        "schemaVersion": 1, "generatedAt": now(), "topic": "大模型后训练的权重空间几何与跨架构能力更新分析",
        "scopeNote": "独立研究兴趣筛选清单，不改变固定分类词表，也不表示论文质量排序。",
        "candidateCount": len(final), "nearMissAuditCount": len(audit_expected),
        "counts": dict(Counter(row["tier"] for row in final)), "records": final,
    }
    save(SCREENING, payload)
    _, taxonomy, active, records = load_context()
    selected = [row for row in final if row["tier"] != "exclude"]
    inputs = []
    for row in selected:
        paper = active[row["id"]]
        existing = records.get(row["id"])
        valid = False
        if existing:
            try:
                pipeline.validate_annotation(existing, paper, taxonomy); valid = True
            except (ValueError, KeyError, TypeError):
                pass
        inputs.append({
            "screening": row, "paper": paper,
            "existingAnnotation": existing if valid else None,
            "instruction": "已有有效记录需重新对照完整摘要复核；忠实则原样复用，否则修正。" if valid else "生成新记录。",
        })
    write_batches(ANNOTATION_BATCHES, inputs, args.annotation_batch_size, "annotate")
    print(json.dumps({"counts": payload["counts"], "selected": len(selected),
                      "existingValid": sum(bool(row["existingAnnotation"]) for row in inputs),
                      "annotationBatches": (len(inputs) + args.annotation_batch_size - 1) // args.annotation_batch_size,
                      "auditFiles": len(files), "auditAdjudicationFiles": len(strict_files)}, ensure_ascii=False))


def annotation_from_semantic(raw, paper, taxonomy, model):
    required = {"id", "titleZh", "summaryZh", "subcategory", "tags", "reason"}
    if set(raw) != required or raw.get("id") != paper["id"]:
        raise ValueError(f"{paper['id']}: 注释字段或 ID 错误")
    annotation = {
        **raw, "sourceFingerprint": paper["fingerprint"], "taxonomyVersion": taxonomy["version"],
        "classification": "review" if raw["subcategory"] == "待复核" else "complete",
        "method": "assistant-read-full-abstract", "model": model, "annotatedAt": now(),
    }
    if annotation["classification"] != "complete":
        raise ValueError(f"{paper['id']}: 本专题不能用待复核代替未完成")
    if len(annotation["tags"]) > 5 or len(annotation["tags"]) != len(set(annotation["tags"])):
        raise ValueError(f"{paper['id']}: 标签重复或超过五个")
    pipeline.validate_annotation(annotation, paper, taxonomy)
    return annotation


def consolidate_annotations(args):
    screening = json.loads(SCREENING.read_text())
    expected = {row["id"] for row in screening["records"] if row["tier"] != "exclude"}
    raw, files = collect_results(ANNOTATION_RESULTS, "annotations", expected)
    if set(raw) != expected:
        raise ValueError(f"注释未覆盖全部入选论文：{len(raw)} / {len(expected)}")
    _, taxonomy, active, records = load_context()
    annotations = [annotation_from_semantic(raw[ident], active[ident], taxonomy, args.model) for ident in sorted(expected)]
    save(WORK / "annotations-pre-qa.json", annotations)
    qa_inputs = []
    screening_by_id = {row["id"]: row for row in screening["records"]}
    for annotation in annotations:
        ident = annotation["id"]
        qa_inputs.append({"screening": screening_by_id[ident], "paper": active[ident], "annotation": annotation})
    write_batches(QA_BATCHES, qa_inputs, args.qa_batch_size, "qa")
    print(json.dumps({"annotations": len(annotations), "resultFiles": len(files),
                      "qaBatches": (len(qa_inputs) + args.qa_batch_size - 1) // args.qa_batch_size}, ensure_ascii=False))


def finalize_annotations(args):
    base = {row["id"]: row for row in json.loads((WORK / "annotations-pre-qa.json").read_text())}
    reviews, files = collect_results(QA_RESULTS, "reviews", set(base))
    if set(reviews) != set(base):
        raise ValueError(f"独立复核未覆盖全部入选论文：{len(reviews)} / {len(base)}")
    _, taxonomy, active, records = load_context()
    corrections = 0
    notes = {}
    final = []
    for ident in sorted(base):
        review = reviews[ident]
        verdict = review.get("verdict")
        corrected = review.get("corrected")
        if verdict == "pass" and corrected is not None:
            raise ValueError(f"{ident}: pass 时 corrected 必须为 null")
        if verdict == "corrected" and not isinstance(corrected, dict):
            raise ValueError(f"{ident}: corrected 时必须给出修正记录")
        row = base[ident]
        if corrected is not None:
            row = annotation_from_semantic({"id": ident, **corrected}, active[ident], taxonomy, args.model)
            corrections += 1
        row["reviewedAt"] = now()
        row["reviewNote"] = str(review.get("note", ""))
        pipeline.validate_annotation(row, active[ident], taxonomy)
        final.append(row)
        notes[ident] = row["reviewNote"]
    save(RESULT, final)
    screening = json.loads(SCREENING.read_text())
    report = {
        "schemaVersion": 1, "generatedAt": now(), "screeningFile": str(SCREENING.relative_to(ROOT)),
        "candidateCount": screening["candidateCount"], "nearMissAuditCount": screening["nearMissAuditCount"],
        "tierCounts": screening["counts"], "selectedCount": len(final), "qaReviewedCount": len(reviews),
        "qaCorrections": corrections, "invalid": 0, "unknownIds": [],
        "scope": "研究兴趣优先集已处理并逐篇复核；不代表 42,358 篇全量分类完成或论文质量排序。",
        "qaNotes": notes,
    }
    save(REPORT, report)
    print(json.dumps({"selected": len(final), "reviewed": len(reviews), "corrections": corrections,
                      "result": str(RESULT.relative_to(ROOT)), "qaFiles": len(files)}, ensure_ascii=False))


def verify(_args):
    screening = json.loads(SCREENING.read_text())
    report = json.loads(REPORT.read_text())
    _, taxonomy, active, records = load_context()
    selected = {row["id"] for row in screening["records"] if row["tier"] != "exclude"}
    errors = []
    for ident in selected:
        try:
            pipeline.validate_annotation(records[ident], active[ident], taxonomy)
            if records[ident]["classification"] != "complete" or not records[ident].get("reviewedAt"):
                raise ValueError("未完成或未记录专题复核")
        except Exception as exc:
            errors.append({"id": ident, "error": str(exc)})
    if report["selectedCount"] != len(selected) or report["qaReviewedCount"] != len(selected):
        errors.append({"id": "report", "error": "报告计数与筛选集不一致"})
    if errors:
        print(json.dumps(errors[:20], ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"candidateCount": screening["candidateCount"], "tiers": screening["counts"],
                      "selectedCompleteAndReviewed": len(selected), "errors": 0}, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--size", type=int, default=30); p.set_defaults(fn=prepare)
    p = sub.add_parser("consolidate-screen"); p.add_argument("--audit-size", type=int, default=200); p.add_argument("--audit-batch-size", type=int, default=25); p.set_defaults(fn=consolidate_screen)
    p = sub.add_parser("prepare-adjudication"); p.add_argument("--size", type=int, default=20); p.set_defaults(fn=prepare_adjudication)
    p = sub.add_parser("prepare-audit-adjudication"); p.add_argument("--size", type=int, default=10); p.set_defaults(fn=prepare_audit_adjudication)
    p = sub.add_parser("apply-adjudication"); p.set_defaults(fn=apply_adjudication)
    p = sub.add_parser("finalize-screen"); p.add_argument("--annotation-batch-size", type=int, default=10); p.set_defaults(fn=finalize_screen)
    p = sub.add_parser("consolidate-annotations"); p.add_argument("--model", default="gpt-5.6-sol"); p.add_argument("--qa-batch-size", type=int, default=10); p.set_defaults(fn=consolidate_annotations)
    p = sub.add_parser("finalize-annotations"); p.add_argument("--model", default="gpt-5.6-sol"); p.set_defaults(fn=finalize_annotations)
    p = sub.add_parser("verify"); p.set_defaults(fn=verify)
    args = parser.parse_args()
    try:
        return args.fn(args) or 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"未完成：{exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    sys.exit(main())
