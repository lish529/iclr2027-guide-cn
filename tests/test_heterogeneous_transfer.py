import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import heterogeneous_transfer as h


class HeterogeneousTransferTests(unittest.TestCase):
    def paper(self, title="", abstract="", keywords=None):
        return {"id":"p", "fingerprint":"f", "title":title, "abstract":abstract,
                "keywords":keywords or [], "primaryArea":"x"}

    def test_recall_cross_architecture(self):
        row = h.recall_row(self.paper("Cross-Architecture Model Merging", "We transfer weights between distinct backbones."))
        self.assertIsNotNone(row)
        self.assertIn("crossArchitecture", row["recallGroups"])

    def test_recall_ordinary_distillation_for_semantic_screening(self):
        self.assertIsNotNone(h.recall_row(self.paper("Knowledge Distillation", "A teacher model supervises a student model.")))

    def test_validate_decision(self):
        h.validate_decision({"tier":"core", "heterogeneityDimensions":["architecture"],
            "transferForms":["weight-merging"], "reason":"研究不同架构之间的权重合并与接口对齐。"})
        with self.assertRaises(ValueError):
            h.validate_decision({"tier":"core", "heterogeneityDimensions":["bad"],
                "transferForms":["weight-merging"], "reason":"研究不同架构之间的权重合并与接口对齐。"})


if __name__ == "__main__": unittest.main()
