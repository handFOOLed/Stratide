"""Request a Codex review, without evaluating review or merge results."""

import json
import os
import re
import subprocess
import sys
import time


REPOSITORY = "handFOOLed/Stratide"
OWNER = "handFOOLed"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CODEX_BOT_ID = 199175422
ACTION_BOT_ID = 41898282


def gh(*arguments):
    result = subprocess.run(
        ["gh", "api", *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def eligible(pr, number, sha, allow_draft=False):
    return (
        pr["number"] == number
        and pr["state"] == "open"
        and (pr["draft"] is False or (allow_draft and pr["draft"] is True))
        and pr["user"]["login"] == OWNER
        and pr["head"]["repo"] is not None
        and pr["head"]["repo"]["full_name"] == REPOSITORY
        and pr["base"]["repo"]["full_name"] == REPOSITORY
        and pr["base"]["ref"] == "main"
        and pr["head"]["sha"] == sha
    )


def wait_for_acknowledgement(comment_id):
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("invalid request comment")
    url = f"repos/{REPOSITORY}/issues/comments/{comment_id}/reactions?per_page=100"
    for attempt in range(12):
        reactions = gh(url)
        if len(reactions) >= 100:
            raise ValueError("reaction history exceeds safe limit")
        if any(
            reaction.get("content") == "eyes"
            and (reaction.get("user") or {}).get("id") == CODEX_BOT_ID
            and (reaction.get("user") or {}).get("login") == "chatgpt-codex-connector[bot]"
            and (reaction.get("user") or {}).get("type") == "Bot"
            for reaction in reactions
        ):
            return True
        if attempt < 11:
            time.sleep(5)
    return False


def main():
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("unexpected repository")
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as event_file:
        event = json.load(event_file)
    number = event["number"]
    sha = event["pull_request"]["head"]["sha"]
    run_id = os.environ["GITHUB_RUN_ID"]
    if (
        type(number) is not int
        or number <= 0
        or not SHA_PATTERN.fullmatch(sha)
        or not re.fullmatch(r"[0-9]+", run_id)
    ):
        raise ValueError("invalid event identity")

    pr_url = f"repos/{REPOSITORY}/pulls/{number}"
    if not eligible(gh(pr_url), number, sha):
        print("BLOCKED: PR no longer matches the authorized event")
        return 1

    marker = f"<!-- stratide-codex-review-request:{run_id}:{sha} -->"
    body = f"@codex review\n\n{marker}"
    comments_url = f"repos/{REPOSITORY}/issues/{number}/comments"
    request_comment = None
    for page in range(1, 101):
        comments = gh(f"{comments_url}?per_page=100&page={page}")
        for comment in comments:
            actor = comment.get("user") or {}
            if actor.get("login") == "github-actions[bot]" and actor.get("id") == ACTION_BOT_ID and comment.get("body") == body:
                if request_comment is not None:
                    raise ValueError("duplicate request markers")
                request_comment = comment
        if len(comments) < 100:
            break
    else:
        raise ValueError("comment history exceeds safe pagination limit")

    if not eligible(gh(pr_url), number, sha):
        print("BLOCKED: PR changed before the review request")
        return 1
    if request_comment is None:
        request_comment = gh(comments_url, "--method", "POST", "-f", f"body={body}")
    if not wait_for_acknowledgement(request_comment["id"]):
        print(f"BLOCKED: Codex did not acknowledge the request for {sha}")
        return 1
    if not eligible(gh(pr_url), number, sha):
        print("BLOCKED: PR changed while awaiting acknowledgement")
        return 1
    print(f"Codex acknowledged the request for {sha}; completion is unverified")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"BLOCKED: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
