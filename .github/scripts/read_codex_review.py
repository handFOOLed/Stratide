"""Read a SHA-bound Codex review result without authorizing a merge."""

import json
import re
import subprocess
import sys

from request_codex_review import REPOSITORY, SHA_PATTERN, eligible, gh


BOT_LOGIN = "chatgpt-codex-connector[bot]"
BOT_ID = 199175422
APP_ID = 1144995
SUMMARY = "<!-- codex-pull-request-review-summary -->"
STATE = re.compile(r"<!-- codex-review-state:v1 (\{[^\n]*\}) -->")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


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
    current_pr = gh(pr_url)
    if not eligible(current_pr, number, sha, allow_draft=True):
        return "BLOCKED"
    if current_pr["base"]["sha"] != base_sha:
        return "BLOCKED"
    if gh(base_url)["object"]["sha"] != base_sha:
        return "BLOCKED"
    if result.get("commit_sha") != sha or result.get("status") != "completed":
        return "BLOCKED"
    if result.get("has_any_findings") is False and result.get("has_unresolved_findings") is False:
        return "CODE_REVIEW_NO_FINDINGS"
    if result.get("has_unresolved_findings") is True:
        return "CHANGES_REQUESTED"
    return "BLOCKED"


if __name__ == "__main__":
    try:
        state = review_state(int(sys.argv[1]), sys.argv[2])
        print(json.dumps({"review": state, "sha": sys.argv[2], "merge_eligible": False}))
        sys.exit(0 if state == "CODE_REVIEW_NO_FINDINGS" else 1)
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError):
        print(json.dumps({"review": "BLOCKED"}))
        sys.exit(1)
