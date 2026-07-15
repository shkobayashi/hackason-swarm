"""Offline tests for the eval harness: graders, task building, report build.

No network — client is always None (LLM graders must self-skip). The banned
phrase loader is monkeypatched so tests never depend on data/.
Run: .venv/bin/python -m unittest tests.test_graders -v
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from evals import build_report, graders, run_evals

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STUB_MANIFEST = REPO_ROOT / "evals" / "manifest_stub.json"

SMALL_BANNED = ["we were negligent", "it was our fault", "we accept full liability"]

# ── canned fixtures ────────────────────────────────────────────────────────────
_FILLER = (
    "We will publish a full incident review, including a complete timeline and "
    "the specific engineering and process changes we are making, within five "
    "business days. "
)
GOOD_STATEMENT = (
    "We apologize to every customer affected by this morning's dashboard "
    "outage, and we are sorry for the disruption it caused to your teams. "
    "Affected accounts will automatically receive a service credit on their "
    "next invoice — no action is needed on your part. "
    + _FILLER * 12
)

GOOD_TWEETS = [
    "Our status dashboard was down for about four hours this morning. It's back, and we're sorry for the disruption.",
    "Affected accounts get an automatic service credit — nothing to file, it will appear on your next invoice.",
    "Full incident review with a timeline and fixes coming within five business days. We'll post it right here.",
]

_LONG_RAW = (
    "We want to be completely transparent with everyone about what happened "
    "this morning, why it happened, what we are doing about it right now, and "
    "what we will do next week, next month, and next quarter to make sure that "
    "nothing like this ever happens again to any of our customers anywhere. "
    "Thank you."
)
LONG_TWEET = ((_LONG_RAW + " ") * 2)[:320]  # exactly 320 chars by construction
assert len(LONG_TWEET) == 320, f"LONG_TWEET is {len(LONG_TWEET)} chars, want 320"


def good_result():
    """(a) A well-formed package that passes every rule-based grader."""
    return {
        "package": {
            "press_statement": GOOD_STATEMENT,
            "internal_talking_points": [
                "Lead with the apology, then the service credit.",
                "Do not speculate on root cause before the review is published.",
                "Escalate press inquiries to comms, not engineering.",
                "The incident review ships within five business days.",
            ],
            "tweets": list(GOOD_TWEETS),
        },
        "status": "shipped",
        "issues": [{"id": "i1", "title": "Dashboard outage", "severity": "high"}],
        "total_cost": 0.0123,
        "elapsed_s": 42.0,
        "verdicts": [],
    }


def liability_result():
    """(b) 320-char tweet + a liability admission in the statement."""
    result = good_result()
    result["package"]["press_statement"] = GOOD_STATEMENT + (
        " We know we were negligent in our monitoring and we own that."
    )
    result["package"]["tweets"] = [GOOD_TWEETS[0], LONG_TWEET, GOOD_TWEETS[2]]
    return result


def malformed_result():
    """(c) Missing the required phrase + only 2 tweets."""
    result = good_result()
    result["package"]["press_statement"] = GOOD_STATEMENT.replace(
        "service credit", "account adjustment"
    )
    result["package"]["tweets"] = GOOD_TWEETS[:2]
    return result


CONTEXT = {"task": {"banned_phrases_extra": []}, "client": None}


class GraderTestCase(unittest.TestCase):
    """Monkeypatch the banned-phrase loader for every test."""

    def setUp(self):
        self._orig_loader = graders.load_banned_phrases
        graders.load_banned_phrases = lambda: list(SMALL_BANNED)

    def tearDown(self):
        graders.load_banned_phrases = self._orig_loader


class TestGoodPackage(GraderTestCase):
    def test_rule_graders_all_pass(self):
        result = good_result()
        for grader_type, check in [
            ("package_shape", None),
            ("tweets_under_280", None),
            ("no_liability_admission", None),
            ("required_phrases", ["we apologize", "service credit"]),
            ("status_shipped", None),
        ]:
            with self.subTest(grader=grader_type):
                g = graders.GRADER_REGISTRY[grader_type](result, check, CONTEXT)
                self.assertEqual(g["score"], 1.0, f"{grader_type}: {g['reason']}")

    def test_llm_graders_skip_without_client(self):
        result = good_result()
        for grader_type in ("all_issues_acknowledged", "llm_judge"):
            with self.subTest(grader=grader_type):
                g = graders.GRADER_REGISTRY[grader_type](
                    result, "some criterion", CONTEXT
                )
                self.assertEqual(g["score"], 0.0)
                self.assertIn("skipped: no client", g["reason"])


class TestLiabilityPackage(GraderTestCase):
    def test_long_tweet_fails_with_length_in_reason(self):
        g = graders.grade_tweets_under_280(liability_result(), None, CONTEXT)
        self.assertEqual(g["score"], 0.0)
        self.assertIn("320", g["reason"])
        self.assertIn("tweet 2", g["reason"])

    def test_liability_admission_fails_naming_phrase(self):
        g = graders.grade_no_liability_admission(liability_result(), None, CONTEXT)
        self.assertEqual(g["score"], 0.0)
        self.assertIn("we were negligent", g["reason"])

    def test_task_extra_banned_phrases_are_scanned(self):
        result = good_result()
        result["package"]["tweets"][0] += " Honestly, the llama was unsupervised."
        context = {"task": {"banned_phrases_extra": ["the llama was unsupervised"]},
                   "client": None}
        g = graders.grade_no_liability_admission(result, None, context)
        self.assertEqual(g["score"], 0.0)
        self.assertIn("the llama was unsupervised", g["reason"])

    def test_other_rule_graders_still_pass(self):
        result = liability_result()
        self.assertEqual(graders.grade_status_shipped(result, None, CONTEXT)["score"], 1.0)
        self.assertEqual(
            graders.grade_required_phrases(result, ["we apologize"], CONTEXT)["score"], 1.0
        )


class TestMalformedPackage(GraderTestCase):
    def test_two_tweets_fail_shape_with_count_in_reason(self):
        g = graders.grade_package_shape(malformed_result(), None, CONTEXT)
        self.assertEqual(g["score"], 0.0)
        self.assertIn("2 tweets", g["reason"])

    def test_missing_required_phrase_named_in_reason(self):
        g = graders.grade_required_phrases(
            malformed_result(), ["we apologize", "service credit"], CONTEXT
        )
        self.assertEqual(g["score"], 0.0)
        self.assertIn("service credit", g["reason"])
        self.assertNotIn("we apologize", g["reason"])

    def test_missing_package_fails_gracefully(self):
        g = graders.grade_package_shape({"package": None, "status": "error"}, None, CONTEXT)
        self.assertEqual(g["score"], 0.0)
        self.assertIn("package", g["reason"].lower())


class TestBannedPhraseLoader(unittest.TestCase):
    def test_missing_data_file_skips_with_reason(self):
        orig_path, orig_cache = graders.LEGAL_PRECEDENTS_PATH, graders._BANNED_CACHE
        try:
            graders.LEGAL_PRECEDENTS_PATH = pathlib.Path(
                tempfile.gettempdir()) / "nope" / "legal_precedents.json"
            graders._BANNED_CACHE = graders._UNSET
            g = graders.grade_no_liability_admission(good_result(), None, CONTEXT)
            self.assertEqual(g["score"], 0.0)
            self.assertIn("skipped", g["reason"])
        finally:
            graders.LEGAL_PRECEDENTS_PATH = orig_path
            graders._BANNED_CACHE = orig_cache


class TestBuildTasks(unittest.TestCase):
    def test_build_tasks_from_stub_manifest(self):
        tasks = run_evals.build_tasks(str(STUB_MANIFEST))
        self.assertEqual(len(tasks), 2)
        task = tasks[0]
        self.assertEqual(task["id"], "stub_llama_outage")
        self.assertTrue(task["scenario"].strip(), "scenario brief should be non-empty")
        types = [g["type"] for g in task["graders"]]
        for expected in ("package_shape", "tweets_under_280", "no_liability_admission",
                         "required_phrases", "status_shipped", "all_issues_acknowledged"):
            self.assertIn(expected, types)
        self.assertEqual(types.count("llm_judge"), 3)
        required = next(g for g in task["graders"] if g["type"] == "required_phrases")
        self.assertEqual(required["check"], ["we apologize", "service credit"])
        # every grader type used must exist in the registry
        for t in set(types):
            self.assertIn(t, graders.GRADER_REGISTRY)

    def test_missing_manifest_falls_back_to_stub(self):
        tasks = run_evals.build_tasks("scenarios/does_not_exist_manifest.json")
        self.assertEqual([t["id"] for t in tasks],
                         ["stub_llama_outage", "stub_billing_bug"])


class TestBuildReport(unittest.TestCase):
    def test_build_injects_results_json(self):
        marker = "XYZZY-EVAL-MARKER-1138"
        stub = {
            "config": {"num_runs": 1, "num_tasks": 1, "max_workers": 1,
                       "manifest": marker},
            "started_at": "2026-07-15T00:00:00+00:00",
            "tasks": [{"id": "t1", "title": "Stub task", "scenario_tag": "stub"}],
            "runs": [[{"task_id": "t1", "title": "Stub task", "passed": True,
                       "status": "shipped", "cost": 0.01, "elapsed_s": 1.0,
                       "error": None,
                       "grades": [{"type": "package_shape", "check": None,
                                   "score": 1.0, "reason": "ok"}]}]],
            "summary": {"overall": 1.0,
                        "by_task": {"t1": {"passed": 1, "n": 1, "title": "Stub task"}},
                        "by_criterion": {"package_shape": {"passed": 1, "n": 1,
                                                           "type": "package_shape"}},
                        "total_cost": 0.01, "wall_s": 1.0},
        }
        with tempfile.TemporaryDirectory() as tmp:
            results_path = pathlib.Path(tmp) / "results.json"
            out_path = pathlib.Path(tmp) / "eval_report.html"
            results_path.write_text(json.dumps(stub))
            build_report.build(results_path=results_path, out_path=out_path)
            html = out_path.read_text()
            self.assertIn(marker, html, "results JSON was not injected")
            self.assertNotIn("__DATA__", html, "placeholder was not replaced")
            self.assertIn("const DATA =", html)


if __name__ == "__main__":
    unittest.main()
