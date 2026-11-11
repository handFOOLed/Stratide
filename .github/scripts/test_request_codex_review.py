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
ACK = [{"content": "eyes", "user": {"id": request.CODEX_BOT_ID, "login": "chatgpt-codex-connector[bot]", "type": "Bot"}}]


def pull_request():
    return {
        "number": 12,
        "state": "open",
        "draft": False,
        "user": {"login": "handFOOLed"},
        "head": {"sha": SHA, "repo": {"full_name": request.REPOSITORY}},
        "base": {"ref": "main", "sha": "c" * 40, "repo": {"full_name": request.REPOSITORY}},
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
        with patch.object(request, "gh", side_effect=[pull_request(), [], pull_request(), {"id": 1}, ACK, pull_request()]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 6)
        self.assertIn(SHA, gh.call_args_list[3].args[-1])
        self.assertIn("@codex review", gh.call_args_list[3].args[-1])

    def test_existing_request_is_idempotent(self):
        comments = [{"id": 1, "user": {"login": "github-actions[bot]", "id": request.ACTION_BOT_ID}, "body": f"@codex review\n\n<!-- stratide-codex-review-request:41:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments, pull_request(), ACK, pull_request()]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 5)

    def test_untrusted_marker_does_not_suppress_request(self):
        comments = [{"user": {"login": "other"}, "body": f"<!-- stratide-codex-review-request:41:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments, pull_request(), {"id": 1}, ACK, pull_request()]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 6)

    def test_other_bot_command_is_not_a_review_request(self):
        comments = [{"id": 7, "user": {"login": "github-actions[bot]", "id": request.ACTION_BOT_ID}, "body": f"@codex fix test\n\n<!-- stratide-codex-review-request:41:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments, pull_request(), {"id": 8}, ACK, pull_request()]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertIn("body=@codex review", gh.call_args_list[3].args[-1])
        self.assertIn("/comments/8/reactions", gh.call_args_list[4].args[0])

    def test_new_event_for_same_sha_starts_a_new_review(self):
        comments = [{"user": {"login": "github-actions[bot]", "id": request.ACTION_BOT_ID}, "body": f"<!-- stratide-codex-review-request:40:{SHA} -->"}]
        with patch.object(request, "gh", side_effect=[pull_request(), comments, pull_request(), {"id": 1}, ACK, pull_request()]) as gh:
            self.assertEqual(request.main(), 0)
        self.assertEqual(gh.call_count, 6)
        self.assertIn(f"41:{SHA}", gh.call_args_list[3].args[-1])

    def test_missing_acknowledgement_blocks_without_reposting(self):
        with patch.object(request, "gh", side_effect=[pull_request(), [], pull_request(), {"id": 1}] + [[]] * 12) as gh:
            with patch.object(request.time, "sleep"):
                self.assertEqual(request.main(), 1)
        self.assertEqual(gh.call_count, 16)
        self.assertEqual(sum("--method" in call.args for call in gh.call_args_list), 1)

    def test_forged_acknowledgement_blocks(self):
        forged = [{"content": "eyes", "user": {"id": 1, "login": "chatgpt-codex-connector[bot]", "type": "Bot"}}]
        with patch.object(request, "gh", return_value=forged):
            with patch.object(request.time, "sleep"):
                self.assertFalse(request.wait_for_acknowledgement(1))

    def test_head_drift_after_acknowledgement_blocks(self):
        changed = pull_request()
        changed["head"]["sha"] = "b" * 40
        with patch.object(request, "gh", side_effect=[pull_request(), [], pull_request(), {"id": 1}, ACK, changed]):
            self.assertEqual(request.main(), 1)

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
