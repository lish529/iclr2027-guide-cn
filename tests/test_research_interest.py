import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("research_interest", SCRIPTS / "research_interest.py")
ri = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ri)


def paper(text):
    return {"id": "p", "fingerprint": "f", "title": text, "abstract": text, "keywords": [], "primaryArea": "a"}


class ResearchInterestTests(unittest.TestCase):
    def test_recall_needs_core_and_support_or_two_core_groups(self):
        self.assertIsNotNone(ri.recall_row(paper("Task vector geometry after reinforcement learning")))
        self.assertIsNotNone(ri.recall_row(paper("Cross-architecture model alignment for model merging")))
        self.assertIsNone(ri.recall_row(paper("Ordinary reinforcement learning benchmark")))

    def test_decision_protocol(self):
        ri.validate_decision({"id": "p", "tier": "core", "researchQuestions": ["update-subspace"], "reason": "直接研究后训练更新子空间的结构。"})
        with self.assertRaises(ValueError):
            ri.validate_decision({"id": "p", "tier": "maybe", "researchQuestions": ["update-subspace"], "reason": "足够长的理由文字。"})
        with self.assertRaises(ValueError):
            ri.validate_decision({"id": "p", "tier": "core", "researchQuestions": ["invented"], "reason": "足够长的理由文字。"})

    def test_annotation_enforces_complete_and_pipeline_validation(self):
        taxonomy = {"version": "v1", "subcategories": ["模型合并", "待复核"], "tags": ["LLM"]}
        source = {"id": "p", "fingerprint": "f"}
        raw = {"id": "p", "titleZh": "标题", "summaryZh": "本研究分析后训练更新的几何结构以及不同模型之间的对齐关系，并据此解释能力变化与任务向量迁移的条件和局限。", "subcategory": "模型合并", "tags": ["LLM"], "reason": "研究任务向量对齐与迁移。"}
        with patch.object(ri.pipeline, "validate_annotation") as validate:
            row = ri.annotation_from_semantic(raw, source, taxonomy, "model")
        self.assertEqual(row["classification"], "complete")
        validate.assert_called_once()
        with patch.object(ri.pipeline, "validate_annotation"):
            with self.assertRaises(ValueError):
                ri.annotation_from_semantic({**raw, "subcategory": "待复核"}, source, taxonomy, "model")


if __name__ == "__main__":
    unittest.main()
