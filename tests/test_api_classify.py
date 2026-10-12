import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("api_classify", SCRIPTS / "api_classify.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def taxonomy():
    return {"version": "v1", "subcategories": ["优化", "其他", "待复核"], "tags": ["LLM", "优化"]}


def paper(ident="p1", fingerprint="fp"):
    return {"id": ident, "title": "T", "abstract": "A", "keywords": [], "primaryArea": "optimization", "fingerprint": fingerprint}


def semantic(**changes):
    result = {
        "titleZh": "标题", "summaryZh": "本研究针对优化问题提出一种结构化训练方法，并通过摘要所述实验进行系统分析，以说明其适用条件、核心机制、主要作用与相关限制。",
        "subcategory": "优化", "tags": ["优化"], "reason": "主要问题是优化", "confidence": "high", "candidateCategories": ["优化"],
    }
    result.update(changes)
    return result


def batch_line(custom_id="draft-1-p1", value=None, status=200, usage=None):
    body = {
        "output": [{"content": [{"type": "output_text", "text": json.dumps(value or semantic(), ensure_ascii=False)}]}],
        "usage": usage or {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    }
    return json.dumps({"custom_id": custom_id, "response": {"status_code": status, "body": body}, "error": None}, ensure_ascii=False).encode()


class ValidationTests(unittest.TestCase):
    def test_valid_structured_output(self):
        with patch.object(api.pipeline, "validate_annotation"):
            row = api.validate_semantic(semantic(), paper(), taxonomy(), "gpt-5-mini")
        self.assertEqual(row["id"], "p1")
        self.assertEqual(row["classification"], "complete")
        self.assertEqual(row["method"], "model-read-full-abstract")

    def test_summary_length_and_tag_whitelist(self):
        with patch.object(api.pipeline, "validate_annotation"):
            with self.assertRaisesRegex(ValueError, "50–100"):
                api.validate_semantic(semantic(summaryZh="太短"), paper(), taxonomy(), "gpt-5-mini")
            with self.assertRaisesRegex(ValueError, "白名单"):
                api.validate_semantic(semantic(tags=["非法"]), paper(), taxonomy(), "gpt-5-mini")

    def test_duplicate_and_unknown_request_ids(self):
        expected = {"draft-1-p1": paper()}
        content = batch_line() + b"\n" + batch_line() + b"\n" + batch_line("draft-1-unknown")
        with patch.object(api.pipeline, "validate_annotation"):
            successes, failures, _ = api.parse_batch_lines(content, expected, taxonomy(), "gpt-5-mini")
        self.assertEqual(set(successes), {"draft-1-p1"})
        self.assertTrue(any("重复或未知" in value for value in failures.values()))

    def test_partial_batch_failure_is_isolated(self):
        expected = {"draft-1-p1": paper(), "draft-1-p2": paper("p2")}
        bad = json.dumps({"custom_id": "draft-1-p2", "response": {"status_code": 500, "body": {}}, "error": None}).encode()
        with patch.object(api.pipeline, "validate_annotation"):
            successes, failures, usage = api.parse_batch_lines(batch_line() + b"\n" + bad, expected, taxonomy(), "gpt-5-mini")
        self.assertEqual(list(successes), ["draft-1-p1"])
        self.assertEqual(list(failures), ["draft-1-p2"])
        self.assertEqual(usage["totalTokens"], 150)

    def test_missing_output_is_failure_not_review(self):
        _, failures, _ = api.parse_batch_lines(b"", {"draft-1-p1": paper()}, taxonomy(), "gpt-5-mini")
        self.assertEqual(failures, {"draft-1-p1": "Batch output missing request"})


class PriceAndBudgetTests(unittest.TestCase):
    def test_price_parser_requires_official_batch_discount(self):
        page = "GPT-5 mini Input $0.25 Cached input $0.025 Output $2.00 GPT-5 Input $1.25 Cached input $0.125 Output $10.00 GPT-5 nano Input $0.05 Cached input $0.005 Output $0.40"
        with self.assertRaisesRegex(ValueError, "50%"):
            api.parse_prices(page, "https://developers.openai.com/api/docs/pricing")

    def test_price_parser_extracts_models_without_confusing_gpt5_mini(self):
        page = "Batch API save 50% on inputs and outputs. GPT-5 mini Input $0.25 Cached input $0.025 Output $2.00 GPT-5 Input $1.25 Cached input $0.125 Output $10.00 GPT-5 nano Input $0.05 Cached input $0.005 Output $0.40"
        prices = api.parse_prices(page, "https://developers.openai.com/api/docs/pricing")
        self.assertEqual(prices["models"]["gpt-5-mini"]["outputPerMillion"], 1.0)
        self.assertEqual(prices["models"]["gpt-5"]["inputPerMillion"], 0.625)
        self.assertEqual(prices["models"]["gpt-5-nano"]["outputPerMillion"], 0.2)

    def test_budget_gate_stops_before_upload(self):
        state = api.default_state()
        state.update({
            "budgetUsd": 0.000001,
            "pricing": {"models": {"gpt-5-mini": {"inputPerMillion": 1, "outputPerMillion": 1}}},
        })
        client = unittest.mock.Mock()
        with tempfile.TemporaryDirectory() as folder, patch.object(api, "JOBS", Path(folder)), patch.object(api, "save_state"):
            with patch.object(api, "protocol_text", return_value="protocol"):
                with self.assertRaises(api.SafeStop) as stopped:
                    api.submit_job(client, state, "draft", [paper()], "gpt-5-mini", taxonomy())
        self.assertEqual(stopped.exception.phase, "budget_exhausted")
        client.upload.assert_not_called()


class ResumeAndFaultTests(unittest.TestCase):
    def test_fingerprint_change_stops_existing_batch(self):
        job = {"batchId": "b", "requestIds": ["draft-1-p1"], "paperIds": ["p1"], "fingerprints": {"p1": "old"}}
        with self.assertRaisesRegex(api.SafeStop, "指纹已变化"):
            api.job_expected(job, {"p1": paper(fingerprint="new")})

    def test_active_job_reuses_submitted_batch(self):
        state = api.default_state()
        state["jobs"] = [
            {"batchId": "done", "status": "completed", "finishedAt": "now"},
            {"batchId": "pending", "status": "in_progress", "finishedAt": None},
        ]
        self.assertEqual(api.active_job(state)["batchId"], "pending")

    def test_atomic_checkpoint_survives_repeat_write(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "state.json"
            api.atomic_json(target, {"phase": "draft"})
            api.atomic_json(target, {"phase": "review"})
            self.assertEqual(json.loads(target.read_text()), {"phase": "review"})
            self.assertFalse(target.with_name("state.json.tmp").exists())

    def test_http_retries_429_and_network_error(self):
        client = api.OpenAIHTTP("not-a-real-key")
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        effects = [
            urllib.error.HTTPError("u", 429, "rate", {}, None),
            urllib.error.URLError("offline"),
            response,
        ]
        with patch.object(api.urllib.request, "urlopen", side_effect=effects), patch.object(api.time, "sleep"):
            self.assertEqual(client.request("GET", "/models"), {"ok": True})

    def test_process_termination_checkpoint_has_remote_ids(self):
        state = api.default_state()
        state["pricing"] = {"models": {"gpt-5-mini": {"inputPerMillion": 0.1, "outputPerMillion": 0.1}}}
        client = unittest.mock.Mock()
        client.upload.return_value = {"id": "file-1"}
        client.request.return_value = {"id": "batch-1", "status": "validating"}
        with tempfile.TemporaryDirectory() as folder, patch.object(api, "ROOT", Path(folder)), patch.object(api, "JOBS", Path(folder)), patch.object(api, "save_state") as save:
            with patch.object(api, "protocol_text", return_value="protocol"), patch.object(api, "log"):
                job = api.submit_job(client, state, "draft", [paper()], "gpt-5-mini", taxonomy())
        self.assertEqual(job["batchId"], "batch-1")
        self.assertEqual(job["inputFileId"], "file-1")
        save.assert_called()

    def test_failed_attempt_limit_leaves_record_unprocessed(self):
        state = api.default_state()
        state["failedAttempts"] = {"p1": 3}
        pending = [paper()]
        retryable = [p for p in pending if state["failedAttempts"].get(p["id"], 0) < 3]
        self.assertEqual(retryable, [])


if __name__ == "__main__":
    unittest.main()
