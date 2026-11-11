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
        + json.dumps({"code_review": result}) + ' -->\n| 📝 **Code Review** | Completed <relative-time datetime="2026-11-11T01:17:33Z">time</relative-time> |',
    }


def threads(*resolved, has_next=False, cursor=None):
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {
        "nodes": [{"isResolved": value} for value in resolved],
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
    }}}}}


class CodexReviewEvidenceTests(unittest.TestCase):
    def evaluate(self, comments, final_pr=None):
        base = {"object": {"sha": "c" * 40}}
        with patch.object(reader, "gh", side_effect=[pull_request(), base, comments, [], final_pr or pull_request(), base, [], threads()]):
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
                with patch.object(reader, "gh", side_effect=[pull_request(), {"object": {"sha": "c" * 40}}, comments]):
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

    def test_base_drift_blocks(self):
        changed = pull_request()
        changed["base"]["sha"] = "d" * 40
        self.assertEqual(self.evaluate([summary()], changed), "BLOCKED")

    def test_invalid_base_sha_blocks(self):
        pr = pull_request()
        pr["base"]["sha"] = "main"
        with patch.object(reader, "gh", return_value=pr):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_target_ref_stale_before_read_blocks(self):
        stale = {"object": {"sha": "d" * 40}}
        with patch.object(reader, "gh", side_effect=[pull_request(), stale]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_target_ref_changes_during_read_blocks(self):
        base = {"object": {"sha": "c" * 40}}
        changed = {"object": {"sha": "d" * 40}}
        with patch.object(reader, "gh", side_effect=[pull_request(), base, [summary()], [], pull_request(), changed]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_reopened_after_review_blocks_even_when_sha_is_unchanged(self):
        base = {"object": {"sha": "c" * 40}}
        events = [{"event": "reopened", "created_at": "2026-11-11T01:18:55Z"}]
        with patch.object(reader, "gh", side_effect=[pull_request(), base, [summary()], events]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_same_second_reopen_blocks_microsecond_review(self):
        comment = summary()
        comment["body"] = comment["body"].replace("01:17:33Z", "01:17:33.100000Z")
        base = {"object": {"sha": "c" * 40}}
        events = [{"event": "reopened", "created_at": "2026-11-11T01:17:33Z"}]
        with patch.object(reader, "gh", side_effect=[pull_request(), base, [comment], events]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_missing_completion_timestamp_blocks(self):
        comment = summary()
        comment["body"] = comment["body"].split("\n|")[0]
        base = {"object": {"sha": "c" * 40}}
        with patch.object(reader, "gh", side_effect=[pull_request(), base, [comment]]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_reopen_between_timeline_reads_blocks(self):
        base = {"object": {"sha": "c" * 40}}
        events = [{"event": "reopened", "created_at": "2026-11-11T01:18:55Z"}]
        with patch.object(reader, "gh", side_effect=[pull_request(), base, [summary()], [], pull_request(), base, events]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_malformed_state_blocks(self):
        malformed = summary()
        malformed["body"] = reader.SUMMARY + "\n<!-- codex-review-state:v1 nope -->"
        with patch.object(reader, "gh", side_effect=[pull_request(), {"object": {"sha": "c" * 40}}, [malformed]]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_duplicate_state_or_json_keys_block(self):
        for body in (
            reader.SUMMARY + '\n<!-- codex-review-state:v1 {"code_review":{},"code_review":{}} -->',
            summary()["body"] + '\n<!-- codex-review-state:v2 {} -->',
        ):
            comment = summary()
            comment["body"] = body
            with self.subTest(body=body):
                with patch.object(reader, "gh", side_effect=[pull_request(), {"object": {"sha": "c" * 40}}, [comment]]):
                    try:
                        result = reader.review_state(12, SHA)
                    except ValueError:
                        result = "BLOCKED"
                    self.assertEqual(result, "BLOCKED")

    def test_draft_review_can_be_inspected_without_merging(self):
        draft = pull_request()
        draft["draft"] = True
        base = {"object": {"sha": "c" * 40}}
        with patch.object(reader, "gh", side_effect=[draft, base, [summary()], [], draft, base, [], threads()]):
            self.assertEqual(reader.review_state(12, SHA), "CODE_REVIEW_NO_FINDINGS")

    def test_unresolved_outdated_thread_blocks_clean_summary(self):
        base = {"object": {"sha": "c" * 40}}
        with patch.object(reader, "gh", side_effect=[pull_request(), base, [summary()], [], pull_request(), base, [], threads(False)]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")

    def test_review_threads_pagination_and_unknown_state(self):
        with patch.object(reader, "gh", side_effect=[threads(True, has_next=True, cursor="next"), threads(True)]):
            self.assertTrue(reader.review_threads_clear(12))
        with patch.object(reader, "gh", return_value=threads(None)):
            self.assertFalse(reader.review_threads_clear(12))

    def test_review_threads_api_error_blocks(self):
        with patch.object(reader, "gh", return_value={"errors": [{"message": "unavailable"}]}):
            self.assertFalse(reader.review_threads_clear(12))

    def test_null_user_is_ignored(self):
        comment = summary()
        comment["user"] = None
        with patch.object(reader, "gh", side_effect=[pull_request(), {"object": {"sha": "c" * 40}}, [comment]]):
            self.assertEqual(reader.review_state(12, SHA), "BLOCKED")


if __name__ == "__main__":
    unittest.main()
