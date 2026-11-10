import json
import unittest
from unittest.mock import patch

import read_codex_review as reader
from test_request_codex_review import SHA, pull_request


def summary(**overrides):
    result = {
        "commit_sha": SHA,
        "has_any_findings": False,
        "has_unresolved_findings": False,
        "status": "completed",
    }
    result.update(overrides)
    return {
        "user": {"id": reader.BOT_ID, "login": reader.BOT_LOGIN, "type": "Bot"},
        "performed_via_github_app": {"id": reader.APP_ID, "slug": "chatgpt-codex-connector"},
        "body": reader.SUMMARY + "\n<!-- codex-review-state:v1 "
        + json.dumps({"code_review": result}) + " -->",
    }


class CodexReviewEvidenceTests(unittest.TestCase):
    def evaluate(self, comments, final_pr=None):
        with patch.object(reader, "gh", side_effect=[pull_request(), comments, final_pr or pull_request()]):
            return reader.review_state(12, SHA)

    def test_completed_review_on_exact_sha(self):
        self.assertEqual(self.evaluate([summary()]), "CODE_REVIEW_NO_FINDINGS")

    def test_missing_forged_or_ambiguous_summary_blocks(self):
        forged = summary()
        forged["user"]["id"] = 1
        wrong_app = summary()
        wrong_app["performed_via_github_app"]["id"] = 1
        for comments in ([], [forged], [wrong_app], [summary(), summary()]):
            with self.subTest(comments=comments):
                with patch.object(reader, "gh", side_effect=[pull_request(), comments]):
                    self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_old_sha_or_incomplete_review_blocks(self):
        for result in (summary(commit_sha="b" * 40), summary(status="running"), summary(has_any_findings=None)):
            with self.subTest(result=result):
                self.assertEqual(self.evaluate([result]), "BLOCKED")

    def test_unresolved_findings_request_changes(self):
        self.assertEqual(self.evaluate([summary(has_any_findings=True, has_unresolved_findings=True)]), "CHANGES_REQUESTED")

    def test_resolved_findings_do_not_imply_clean_review(self):
        self.assertEqual(self.evaluate([summary(has_any_findings=True)]), "BLOCKED")

    def test_head_drift_blocks(self):
        changed = pull_request()
        changed["head"]["sha"] = "b" * 40
        self.assertEqual(self.evaluate([summary()], changed), "BLOCKED")

    def test_malformed_state_blocks(self):
        malformed = summary()
        malformed["body"] = reader.SUMMARY + "\n<!-- codex-review-state:v1 nope -->"
        with patch.object(reader, "gh", side_effect=[pull_request(), [malformed]]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_duplicate_state_or_json_keys_block(self):
        for body in (
            reader.SUMMARY + '\n<!-- codex-review-state:v1 {"code_review":{},"code_review":{}} -->',
            summary()["body"] + '\n<!-- codex-review-state:v2 {} -->',
        ):
            comment = summary()
            comment["body"] = body
            with self.subTest(body=body):
                with patch.object(reader, "gh", side_effect=[pull_request(), [comment]]):
                    try:
                        result = reader.review_state(12, SHA)
                    except ValueError:
                        result = "BLOCKED"
                    self.assertEqual(result, "BLOCKED")

    def test_draft_review_can_be_inspected_without_merging(self):
        draft = pull_request()
        draft["draft"] = True
        with patch.object(reader, "gh", side_effect=[draft, [summary()], draft]):
            self.assertEqual(reader.review_state(12, SHA), "CODE_REVIEW_NO_FINDINGS")

    def test_null_user_is_ignored(self):
        comment = summary()
        comment["user"] = None
        with patch.object(reader, "gh", side_effect=[pull_request(), [comment]]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")


if __name__ == "__main__":
    unittest.main()
