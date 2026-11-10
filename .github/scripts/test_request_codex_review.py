import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import mock_open, patch


SCRIPT = Path(__file__).with_name("request_codex_review.py")
SPEC = importlib.util.spec_from_file_location("request_codex_review", SCRIPT)
request = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(request)
SHA = "a" * 40


def pull_request():
    return {
        "number": 12,
        "state": "open",
        "draft": False,
        "user": {"login": "handFOOLed"},
        "head": {"sha": SHA, "repo": {"full_name": request.REPOSITORY}},
        "base": {"ref": "main", "repo": {"full_name": request.REPOSITORY}},
    }


class RequestReviewTests(unittest.TestCase):
    def setUp(self):
        event = json.dumps({"number": 12, "pull_request": pull_request()})
        self.event_file = patch("builtins.open", mock_open(read_data=event))
        self.event_file.start()
        self.addCleanup(self.event_file.stop)
        self.environment = patch.dict(
            os.environ,
            {"GITHUB_REPOSITORY": request.REPOSITORY, "GITHUB_EVENT_PATH": "event.json", "GITHUB_RUN_ID": "41"},
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_requests_review_for_current_head(self):
        with patch.object(request, "gh", side_effect=[pull_request(), [], pull_request(), {}]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 4)
        self.assertIn(SHA, gh.call_args.args[-1])
        self.assertIn("@codex review", gh.call_args.args[-1])

    def test_existing_request_is_idempotent(self):
        comments = [{"user": {"login": "github-actions[bot]"}, "body": f"<!-- stratide-codex-review-request:41:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 2)

    def test_untrusted_marker_does_not_suppress_request(self):
        comments = [{"user": {"login": "other"}, "body": f"<!-- stratide-codex-review-request:41:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments, pull_request(), {}]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 4)

    def test_new_event_for_same_sha_starts_a_new_review(self):
        comments = [{"user": {"login": "github-actions[bot]"}, "body": f"<!-- stratide-codex-review-request:40:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments, pull_request(), {}]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 4)
        self.assertIn(f"41:{SHA}", gh.call_args.args[-1])

    def test_changed_head_prevents_request(self):
        changed = pull_request()
        changed["head"]["sha"] = "b" * 40
        with patch.object(request, "gh", side_effect=[pull_request(), [], changed]) as gh:
            self.assertEqual(request.main(), 1)
        self.assertEqual(gh.call_count, 3)

    def test_unauthorized_pr_prevents_request(self):
        for field, value in (("user", {"login": "other"}), ("draft", True), ("state", "closed")):
            with self.subTest(field=field):
                pr = pull_request()
                pr[field] = value
                with patch.object(request, "gh", return_value=pr) as gh:
                    self.assertEqual(request.main(), 1)
                self.assertEqual(gh.call_count, 1)

    def test_fork_and_wrong_base_prevent_request(self):
        for part in ("head", "base"):
            with self.subTest(part=part):
                pr = pull_request()
                pr[part]["repo"]["full_name"] = "other/repository"
                with patch.object(request, "gh", return_value=pr) as gh:
                    self.assertEqual(request.main(), 1)
                self.assertEqual(gh.call_count, 1)

    def test_api_failure_prevents_request(self):
        error = subprocess.CalledProcessError(1, "gh")
        with patch.object(request, "gh", side_effect=error) as gh:
            with self.assertRaises(subprocess.CalledProcessError):
                request.main()
        self.assertEqual(gh.call_count, 1)

    def test_wrong_repository_prevents_api_access(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "other/repository"}):
            with patch.object(request, "gh") as gh:
                with self.assertRaises(ValueError):
                    request.main()
        gh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
