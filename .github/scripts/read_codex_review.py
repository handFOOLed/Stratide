"""Read a SHA-bound Codex review result without authorizing a merge."""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone

from request_codex_review import REPOSITORY, SHA_PATTERN, eligible, gh


BOT_LOGIN = "chatgpt-codex-connector[bot]"
BOT_ID = 199175422
APP_ID = 1144995
SUMMARY = "<!-- codex-pull-request-review-summary -->"
STATE = re.compile(r"<!-- codex-review-state:v1 (\{[^\n]*\}) -->")
COMPLETED_AT = re.compile(r'^\|[^\n]*\*\*Code Review\*\*[^\n]*<relative-time datetime="([^"]+)"', re.MULTILINE)
THREADS_QUERY = """query($owner:String!,$repo:String!,$number:Int!,$after:String) {
  repository(owner:$owner,name:$repo) {
    pullRequest(number:$number) {
      reviewThreads(first:100,after:$after) {
        nodes { isResolved }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}"""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def utc_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def no_later_lifecycle_change(number, body):
    matches = COMPLETED_AT.findall(body)
    if len(matches) != 1:
        return False
    completed_at = utc_time(matches[0]).replace(microsecond=0)
    timeline_url = f"repos/{REPOSITORY}/issues/{number}/timeline"
    for page in range(1, 101):
        events = gh(f"{timeline_url}?per_page=100&page={page}")
        for event in events:
            if event.get("event") in {"ready_for_review", "reopened"}:
                if utc_time(event["created_at"]) >= completed_at:
                    return False
        if len(events) < 100:
            return True
    return False


def review_threads_clear(number):
    cursor = None
    seen_cursors = set()
    owner, repository = REPOSITORY.split("/", 1)
    for _ in range(100):
        arguments = [
            "graphql", "-f", f"query={THREADS_QUERY}", "-f", f"owner={owner}",
            "-f", f"repo={repository}", "-F", f"number={number}",
        ]
        if cursor is not None:
            arguments.extend(["-f", f"after={cursor}"])
        response = gh(*arguments)
        if "errors" in response and response["errors"] != []:
            return False
        threads = response["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes = threads["nodes"]
        if not isinstance(nodes, list):
            return False
        if any(not isinstance(thread, dict) or thread.get("isResolved") is not True for thread in nodes):
            return False
        page = threads["pageInfo"]
        if page["hasNextPage"] is False:
            return True
        cursor = page["endCursor"]
        if page["hasNextPage"] is not True or not nodes or not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            return False
        seen_cursors.add(cursor)
    return False


def review_state(number, sha):
    if type(number) is not int or number <= 0 or not SHA_PATTERN.fullmatch(sha):
        raise ValueError("invalid PR or SHA")
    pr_url = f"repos/{REPOSITORY}/pulls/{number}"
    initial_pr = gh(pr_url)
    if not eligible(initial_pr, number, sha, allow_draft=True):
        return "BLOCKED"
    base_sha = initial_pr["base"]["sha"]
    if not isinstance(base_sha, str) or not SHA_PATTERN.fullmatch(base_sha):
        return "BLOCKED"
    base_url = f"repos/{REPOSITORY}/git/ref/heads/main"
    if gh(base_url)["object"]["sha"] != base_sha:
        return "BLOCKED"

    summaries = []
    comments_url = f"repos/{REPOSITORY}/issues/{number}/comments"
    for page in range(1, 101):
        comments = gh(f"{comments_url}?per_page=100&page={page}")
        summaries.extend(
            comment for comment in comments
            if (comment.get("user") or {}).get("id") == BOT_ID
            and (comment.get("user") or {}).get("login") == BOT_LOGIN
            and (comment.get("user") or {}).get("type") == "Bot"
            and (comment.get("performed_via_github_app") or {}).get("id") == APP_ID
            and (comment.get("performed_via_github_app") or {}).get("slug") == "chatgpt-codex-connector"
            and SUMMARY in (comment.get("body") or "")
        )
        if len(comments) < 100:
            break
    else:
        return "BLOCKED"

    if len(summaries) != 1:
        return "BLOCKED"
    body = summaries[0]["body"]
    matches = STATE.findall(body)
    if len(matches) != 1 or body.count(SUMMARY) != 1 or body.count("<!-- codex-review-state:") != 1:
        return "BLOCKED"
    result = json.loads(matches[0], object_pairs_hook=unique_object, parse_constant=reject_constant)["code_review"]
    if not isinstance(result, dict):
        return "BLOCKED"
    if result.get("commit_sha") != sha or result.get("status") != "completed":
        return "BLOCKED"
    if not no_later_lifecycle_change(number, body):
        return "BLOCKED"
    clean = result.get("has_any_findings") is False and result.get("has_unresolved_findings") is False
    if clean and not review_threads_clear(number):
        return "BLOCKED"
    current_pr = gh(pr_url)
    if not eligible(current_pr, number, sha, allow_draft=True):
        return "BLOCKED"
    if current_pr["base"]["sha"] != base_sha:
        return "BLOCKED"
    if gh(base_url)["object"]["sha"] != base_sha:
        return "BLOCKED"
    if not no_later_lifecycle_change(number, body):
        return "BLOCKED"
    if clean:
        return "CODE_REVIEW_NO_FINDINGS"
    if result.get("has_any_findings") is True and result.get("has_unresolved_findings") is True:
        return "CHANGES_REQUESTED"
    return "BLOCKED"


if __name__ == "__main__":
    try:
        state = review_state(int(sys.argv[1]), sys.argv[2])
        print(json.dumps({"review": state, "sha": sys.argv[2], "event_verified": False, "merge_eligible": False}))
        sys.exit(0 if state == "CODE_REVIEW_NO_FINDINGS" else 1)
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError):
        print(json.dumps({"review": "BLOCKED", "event_verified": False, "merge_eligible": False}))
        sys.exit(1)
