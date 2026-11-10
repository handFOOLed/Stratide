"""Request a Codex review, without evaluating review or merge results."""

import json
import os
import re
import subprocess
import sys


REPOSITORY = "handFOOLed/Stratide"
OWNER = "handFOOLed"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def gh(*arguments):
    result = subprocess.run(
        ["gh", "api", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def eligible(pr, number, sha):
    return (
        pr["number"] == number
        and pr["state"] == "open"
        and pr["draft"] is False
        and pr["user"]["login"] == OWNER
        and pr["head"]["repo"] is not None
        and pr["head"]["repo"]["full_name"] == REPOSITORY
        and pr["base"]["repo"]["full_name"] == REPOSITORY
        and pr["base"]["ref"] == "main"
        and pr["head"]["sha"] == sha
    )


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
    comments_url = f"repos/{REPOSITORY}/issues/{number}/comments"
    for page in range(1, 101):
        comments = gh(f"{comments_url}?per_page=100&page={page}")
        if any(
            comment["user"]["login"] == "github-actions[bot]"
            and marker in comment["body"]
            for comment in comments
        ):
            print(f"Review already requested for {sha}; completion is unverified")
            return 0
        if len(comments) < 100:
            break
    else:
        raise ValueError("comment history exceeds safe pagination limit")

    if not eligible(gh(pr_url), number, sha):
        print("BLOCKED: PR changed before the review request")
        return 1
    gh(comments_url, "--method", "POST", "-f", f"body=@codex review\n\n{marker}")
    print(f"Requested review for {sha}; completion is unverified")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"BLOCKED: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
