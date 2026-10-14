#!/usr/bin/env python3
"""Build and validate the heterogeneous-model merging and transfer topic."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pipeline
import research_interest as common


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/heterogeneous-transfer"
SCREENING = ROOT / "data/heterogeneous-transfer-screening.json"
REPORT = ROOT / "data/heterogeneous-transfer-report.json"
RESULT = ROOT / "work/classification-results/heterogeneous-transfer.json"
TIERS = {"core", "method-reference", "exclude"}
DIMENSIONS = {"parameters", "scale", "architecture", "model-family", "tokenizer", "backbone",
              "modality", "client-model", "representation", "module-interface", "other"}
FORMS = {"weight-merging", "task-vector-transfer", "knowledge-distillation", "policy-transfer",
         "feature-transfer", "logit-transfer", "model-stitching", "latent-communication",
         "kv-memory-transfer", "federated-knowledge-sharing", "alignment-measure", "other"}

GROUPS = {
    "merging": [r"model merg", r"merging models", r"merge (?:multiple |different )?models", r"task vector",
                r"model soup", r"weight averaging", r"weight[- ]space (?:fusion|combination)"],
    "distillation": [r"knowledge distill", r"teacher[-– ]student", r"teacher model", r"student model",
                     r"on[- ]policy distill", r"policy distill", r"feature distill", r"logit distill"],
    "crossModel": [r"cross[- ]model", r"model[- ]to[- ]model", r"across model", r"between models",
                   r"different model families", r"across model families", r"cross[- ]family",
                   r"heterogeneous (?:foundation )?models?", r"model[- ]heterogeneous"],
    "crossArchitecture": [r"cross[- ]architecture", r"across (?:different )?architectures",
                          r"different architectures", r"heterogeneous architectures?", r"cross[- ]backbone",
                          r"different backbones?", r"heterogeneous backbones?"],
    "tokenizer": [r"cross[- ]tokenizer", r"tokenizer[- ]agnostic", r"tokenizer mismatch", r"different tokenizers?"],
    "interface": [r"model stitch", r"activation stitch", r"latent (?:interface|communication|transfer|bridge)",
                  r"KV cache (?:transfer|translation)", r"memory transfer", r"shared latent interface",
                  r"representation (?:mapping|alignment).{0,80}(?:models|architectures)"],
    "federated": [r"model[- ]heterogeneous federated", r"heterogeneous federated (?:learning|models)",
                  r"federat.{0,80}(?:heterogeneous models|different models|personal models)"],
    "transfer": [r"transfer.{0,100}(?:model families|models|backbones|architectures)",
                 r"from (?:a |the )?(?:larger|smaller|teacher|source) model.{0,100}(?:student|target) model"],
}
COMPILED = {key: [re.compile(x, re.I | re.S) for x in values] for key, values in GROUPS.items()}


def path(name: str) -> Path:
    return WORK / name


def load_context():
    snapshot = pipeline.load(pipeline.SNAPSHOT)
    taxonomy = pipeline.load(ROOT / "data/taxonomy.json")
    papers = pipeline.papers_from(snapshot)
    active = {ident: paper for ident, paper in papers.items() if paper["status"] == "active"}
    return snapshot, taxonomy, active, pipeline.annotations()


def recall_row(paper):
    text = " ".join([paper["title"], paper["abstract"], " ".join(paper["keywords"])])
    hits = {key: [r.pattern for r in rules if r.search(text)] for key, rules in COMPILED.items()}
    hit_groups = [key for key, values in hits.items() if values]
    if not hit_groups:
        return None
    title_hits = sum(bool(r.search(paper["title"])) for rules in COMPILED.values() for r in rules)
    strong = sum(key in hit_groups for key in ("merging", "crossModel", "crossArchitecture", "tokenizer", "interface", "federated"))
    return {"id": paper["id"], "fingerprint": paper["fingerprint"], "title": paper["title"],
            "abstract": paper["abstract"], "keywords": paper["keywords"], "primaryArea": paper["primaryArea"],
            "recallGroups": hit_groups, "matchedPatterns": {k: v for k, v in hits.items() if v},
            "recallScore": title_hits * 100 + strong * 10 + len(hit_groups)}


def decision_schema():
    return {"type": "object", "additionalProperties": False, "required": ["decisions"], "properties": {
        "decisions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["id", "tier", "heterogeneityDimensions", "transferForms", "reason"], "properties": {
                "id": {"type": "string"}, "tier": {"type": "string", "enum": sorted(TIERS)},
                "heterogeneityDimensions": {"type": "array", "minItems": 1, "maxItems": 5,
                    "items": {"type": "string", "enum": sorted(DIMENSIONS)}},
                "transferForms": {"type": "array", "minItems": 1, "maxItems": 5,
                    "items": {"type": "string", "enum": sorted(FORMS)}},
                "reason": {"type": "string", "minLength": 12, "maxLength": 280}}}}}}


def validate_decision(row):
    if row.get("tier") not in TIERS:
        raise ValueError(f"{row.get('id')}: tier 非法")
    if not isinstance(row.get("heterogeneityDimensions"), list) or not row["heterogeneityDimensions"] or not set(row["heterogeneityDimensions"]) <= DIMENSIONS:
        raise ValueError(f"{row.get('id')}: heterogeneityDimensions 非法")
    if not isinstance(row.get("transferForms"), list) or not row["transferForms"] or not set(row["transferForms"]) <= FORMS:
        raise ValueError(f"{row.get('id')}: transferForms 非法")
    if len(str(row.get("reason", ""))) < 12:
        raise ValueError(f"{row.get('id')}: reason 过短")


def collect(folder: str, field: str, expected: set[str]):
    return common.collect_results(path(folder), field, expected)


def prepare(args):
    snapshot, taxonomy, active, _ = load_context()
    rows = [row for paper in active.values() if (row := recall_row(paper))]
    rows.sort(key=lambda row: (-row["recallScore"], row["id"]))
    common.save(path("manifest.json"), {"schemaVersion": 1, "generatedAt": common.now(),
        "snapshotFinishedAt": snapshot.get("finishedAt"), "candidateCount": len(rows), "batchSize": args.size,
        "activeIdSetSha256": hashlib.sha256("\n".join(sorted(active)).encode()).hexdigest()})
    common.save(path("candidates.json"), rows)
    common.save(path("decision-schema.json"), decision_schema())
    common.save(path("annotation-schema.json"), common.annotation_schema(taxonomy))
    common.save(path("qa-schema.json"), common.qa_schema(taxonomy))
    common.write_batches(path("screen-batches"), rows, args.size, "screen")
    print(json.dumps({"candidates": len(rows), "batches": (len(rows) + args.size - 1) // args.size}, ensure_ascii=False))


def prepare_missing_screen(args):
    """Rebuild singleton/small batches only for candidates without a valid decision."""
    candidates = json.loads(path("candidates.json").read_text())
    expected = {row["id"] for row in candidates}
    seen = set()
    for result in path("screen-results").glob("*.json"):
        try:
            payload = json.loads(result.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("decisions", []):
            ident = row.get("id")
            if ident in expected:
                seen.add(ident)
    missing = [row for row in candidates if row["id"] not in seen]
    common.write_batches(path("screen-missing-batches"), missing, args.size, args.prefix)
    print(json.dumps({"expected": len(expected), "seen": len(seen), "missing": len(missing),
        "batches": (len(missing) + args.size - 1) // args.size}, ensure_ascii=False))


def consolidate_screen(args):
    candidates = json.loads(path("candidates.json").read_text())
    by_id = {row["id"]: row for row in candidates}
    decisions, files = collect("screen-results", "decisions", set(by_id))
    if set(decisions) != set(by_id):
        raise ValueError(f"初筛未覆盖全部候选：{len(decisions)} / {len(by_id)}")
    combined = []
    for ident, source in by_id.items():
        decision = decisions[ident]; validate_decision(decision)
        combined.append({"id": ident, "sourceFingerprint": source["fingerprint"], "title": source["title"],
            "primaryArea": source["primaryArea"], "recallGroups": source["recallGroups"],
            **{k: decision[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")},
            "screenedAt": common.now(), "nearMissAudit": False})
    common.save(path("initial-screening.json"), combined)
    excluded = [row for row in combined if row["tier"] == "exclude"]
    score = {row["id"]: row["recallScore"] for row in candidates}
    groups = defaultdict(list)
    for row in excluded:
        groups[(row["primaryArea"], tuple(row["recallGroups"]))].append(row)
    for rows in groups.values(): rows.sort(key=lambda row: (-score[row["id"]], row["id"]))
    sample = []
    while len(sample) < min(args.audit_size, len(excluded)) and any(groups.values()):
        for key in sorted(groups, key=str):
            if groups[key] and len(sample) < args.audit_size: sample.append(groups[key].pop(0))
    audit = [{**by_id[row["id"]], "initialDecision": row} for row in sample]
    common.save(path("audit-sample.json"), audit)
    common.write_batches(path("audit-batches"), audit, args.audit_batch_size, "audit")
    included = [{**by_id[row["id"]], "initialDecision": row} for row in combined if row["tier"] != "exclude"]
    common.write_batches(path("adjudication-batches"), included, args.adjudication_batch_size, "adjudication")
    print(json.dumps({"screened": len(combined), "tiers": dict(Counter(r["tier"] for r in combined)),
        "auditSample": len(audit), "adjudication": len(included), "resultFiles": len(files)}, ensure_ascii=False))


def apply_adjudication(_args):
    initial = json.loads(path("initial-screening.json").read_text()); by_id = {r["id"]: r for r in initial}
    expected = {i for i, r in by_id.items() if r["tier"] != "exclude"}
    decisions, files = collect("adjudication-results", "decisions", expected)
    if set(decisions) != expected: raise ValueError(f"独立裁决未覆盖完整：{len(decisions)} / {len(expected)}")
    for ident, decision in decisions.items():
        validate_decision(decision); row = by_id[ident]
        row["preAdjudication"] = {k: row[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")}
        row.update({k: decision[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")})
        row["adjudicatedAt"] = common.now()
    common.save(path("initial-screening.json"), list(by_id.values()))
    print(json.dumps({"adjudicated": len(decisions), "tiers": dict(Counter(r["tier"] for r in by_id.values())), "files": len(files)}, ensure_ascii=False))


def prepare_audit_adjudication(args):
    candidates = {r["id"]: r for r in json.loads(path("candidates.json").read_text())}
    sample = json.loads(path("audit-sample.json").read_text()); expected = {r["id"] for r in sample}
    audits, _ = collect("audit-results", "decisions", expected)
    if set(audits) != expected: raise ValueError(f"漏项抽查未覆盖完整：{len(audits)} / {len(expected)}")
    promoted = [{**candidates[i], "initialDecision": d} for i, d in audits.items() if d["tier"] != "exclude"]
    promoted.sort(key=lambda r: r["id"])
    common.write_batches(path("audit-adjudication-batches"), promoted, args.size, "audit-adjudication")
    print(json.dumps({"promoted": len(promoted), "batches": (len(promoted) + args.size - 1) // args.size}, ensure_ascii=False))


def finalize_screen(args):
    initial = json.loads(path("initial-screening.json").read_text()); by_id = {r["id"]: r for r in initial}
    sample = json.loads(path("audit-sample.json").read_text()); audit_ids = {r["id"] for r in sample}
    audits, audit_files = collect("audit-results", "decisions", audit_ids)
    if set(audits) != audit_ids: raise ValueError(f"漏项抽查未覆盖完整：{len(audits)} / {len(audit_ids)}")
    for ident, decision in audits.items():
        validate_decision(decision); row = by_id[ident]; row["nearMissAudit"] = True
        row["preAudit"] = {k: row[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")}
        row.update({k: decision[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")})
        row["auditedAt"] = common.now()
    promoted = {i for i, d in audits.items() if d["tier"] != "exclude"}
    strict, strict_files = collect("audit-adjudication-results", "decisions", promoted)
    if set(strict) != promoted: raise ValueError(f"漏项晋级裁决未覆盖完整：{len(strict)} / {len(promoted)}")
    for ident, decision in strict.items():
        validate_decision(decision); row = by_id[ident]
        row["preAuditAdjudication"] = {k: row[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")}
        row.update({k: decision[k] for k in ("tier", "heterogeneityDimensions", "transferForms", "reason")})
        row["auditAdjudicatedAt"] = common.now()
    final = sorted(by_id.values(), key=lambda r: ({"core": 0, "method-reference": 1, "exclude": 2}[r["tier"]], r["id"]))
    payload = {"schemaVersion": 1, "slug": "heterogeneous-model-transfer", "generatedAt": common.now(),
        "topic": "异构模型合并与迁移", "scopeNote": "不同模型之间的能力、知识或内部状态合并与迁移；不表示论文质量排序。",
        "candidateCount": len(final), "nearMissAuditCount": len(audit_ids),
        "counts": dict(Counter(r["tier"] for r in final)), "records": final}
    common.save(SCREENING, payload)
    _, taxonomy, active, records = load_context(); selected = [r for r in final if r["tier"] != "exclude"]
    inputs = []
    for row in selected:
        paper = active[row["id"]]; existing = records.get(row["id"]); valid = False
        if existing:
            try: pipeline.validate_annotation(existing, paper, taxonomy); valid = True
            except (ValueError, KeyError, TypeError): pass
        inputs.append({"screening": row, "paper": paper, "existingAnnotation": existing if valid else None,
            "instruction": "重新对照摘要，忠实才可复用。" if valid else "生成新记录。"})
    common.write_batches(path("annotation-batches"), inputs, args.annotation_batch_size, "annotate")
    print(json.dumps({"counts": payload["counts"], "selected": len(selected),
        "existingValid": sum(bool(r["existingAnnotation"]) for r in inputs),
        "annotationBatches": (len(inputs) + args.annotation_batch_size - 1) // args.annotation_batch_size,
        "auditFiles": len(audit_files), "strictAuditFiles": len(strict_files)}, ensure_ascii=False))


def consolidate_annotations(args):
    screening = json.loads(SCREENING.read_text()); expected = {r["id"] for r in screening["records"] if r["tier"] != "exclude"}
    raw, files = collect("annotation-results", "annotations", expected)
    if set(raw) != expected: raise ValueError(f"注释未覆盖完整：{len(raw)} / {len(expected)}")
    _, taxonomy, active, _ = load_context()
    annotations = [common.annotation_from_semantic(raw[i], active[i], taxonomy, args.model) for i in sorted(expected)]
    common.save(path("annotations-pre-qa.json"), annotations)
    by_screen = {r["id"]: r for r in screening["records"]}
    qa = [{"screening": by_screen[a["id"]], "paper": active[a["id"]], "annotation": a} for a in annotations]
    common.write_batches(path("qa-batches"), qa, args.qa_batch_size, "qa")
    print(json.dumps({"annotations": len(annotations), "files": len(files), "qaBatches": (len(qa) + args.qa_batch_size - 1) // args.qa_batch_size}, ensure_ascii=False))


def finalize_annotations(args):
    base = {r["id"]: r for r in json.loads(path("annotations-pre-qa.json").read_text())}
    reviews, files = collect("qa-results", "reviews", set(base))
    if set(reviews) != set(base): raise ValueError(f"质量复核未覆盖完整：{len(reviews)} / {len(base)}")
    _, taxonomy, active, old_records = load_context(); final = []; corrections = 0
    for ident in sorted(base):
        review = reviews[ident]; corrected = review.get("corrected")
        if review.get("verdict") == "pass" and corrected is not None: raise ValueError(f"{ident}: pass 不得修正")
        if review.get("verdict") == "corrected" and not isinstance(corrected, dict): raise ValueError(f"{ident}: 缺少修正")
        row = base[ident]
        if corrected is not None:
            row = common.annotation_from_semantic({"id": ident, **corrected}, active[ident], taxonomy, args.model); corrections += 1
        row["reviewedAt"] = common.now(); row["reviewNote"] = str(review.get("note", ""))
        pipeline.validate_annotation(row, active[ident], taxonomy); final.append(row)
    common.save(RESULT, final)
    screening = json.loads(SCREENING.read_text()); selected = {r["id"] for r in screening["records"] if r["tier"] != "exclude"}
    reused = sum(i in old_records for i in selected)
    common.save(REPORT, {"schemaVersion": 1, "generatedAt": common.now(), "screeningFile": "data/heterogeneous-transfer-screening.json",
        "candidateCount": screening["candidateCount"], "nearMissAuditCount": screening["nearMissAuditCount"],
        "tierCounts": screening["counts"], "selectedCount": len(final), "reusedValidCount": reused,
        "newlyClassifiedCount": len(final) - reused, "qaReviewedCount": len(reviews), "qaCorrections": corrections,
        "invalid": 0, "scope": "专题已逐篇复核；不代表全量分类完成或论文质量排序。"})
    print(json.dumps({"selected": len(final), "reused": reused, "new": len(final)-reused, "corrections": corrections, "qaFiles": len(files)}, ensure_ascii=False))


def verify(_args):
    screening = json.loads(SCREENING.read_text()); report = json.loads(REPORT.read_text())
    _, taxonomy, active, records = load_context(); selected = {r["id"] for r in screening["records"] if r["tier"] != "exclude"}; errors = []
    for ident in selected:
        try:
            pipeline.validate_annotation(records[ident], active[ident], taxonomy)
            if records[ident]["classification"] != "complete" or not records[ident].get("reviewedAt"): raise ValueError("未完成复核")
        except Exception as exc: errors.append({"id": ident, "error": str(exc)})
    if report["selectedCount"] != len(selected) or report["qaReviewedCount"] != len(selected): errors.append({"id": "report", "error": "计数错误"})
    if errors: print(json.dumps(errors[:20], ensure_ascii=False, indent=2), file=sys.stderr); return 1
    print(json.dumps({"candidateCount": screening["candidateCount"], "tiers": screening["counts"], "selectedCompleteAndReviewed": len(selected), "errors": 0}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--size", type=int, default=30); p.set_defaults(fn=prepare)
    p = sub.add_parser("prepare-missing-screen"); p.add_argument("--size", type=int, default=1)
    p.add_argument("--prefix", default="screen-retry"); p.set_defaults(fn=prepare_missing_screen)
    p = sub.add_parser("consolidate-screen"); p.add_argument("--audit-size", type=int, default=300); p.add_argument("--audit-batch-size", type=int, default=20); p.add_argument("--adjudication-batch-size", type=int, default=20); p.set_defaults(fn=consolidate_screen)
    p = sub.add_parser("apply-adjudication"); p.set_defaults(fn=apply_adjudication)
    p = sub.add_parser("prepare-audit-adjudication"); p.add_argument("--size", type=int, default=10); p.set_defaults(fn=prepare_audit_adjudication)
    p = sub.add_parser("finalize-screen"); p.add_argument("--annotation-batch-size", type=int, default=10); p.set_defaults(fn=finalize_screen)
    p = sub.add_parser("consolidate-annotations"); p.add_argument("--model", default="gpt-5.6-sol"); p.add_argument("--qa-batch-size", type=int, default=10); p.set_defaults(fn=consolidate_annotations)
    p = sub.add_parser("finalize-annotations"); p.add_argument("--model", default="gpt-5.6-sol"); p.set_defaults(fn=finalize_annotations)
    p = sub.add_parser("verify"); p.set_defaults(fn=verify)
    args = parser.parse_args()
    try: return args.fn(args) or 0
    except (ValueError, KeyError, TypeError, OSError) as exc: print(f"未完成：{exc}", file=sys.stderr); return 1


if __name__ == "__main__": sys.exit(main())
