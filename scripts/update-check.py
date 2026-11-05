"""Read-only GitHub release lookup for the version card.

Public metadata only: no credentials, no account data, no telemetry.
"""
import json
import urllib.request

API = "https://api.github.com/repos/handFOOLed/Stratide/releases?per_page=10"


def main():
    request = urllib.request.Request(
        API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Stratide-UpdateCheck",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            releases = json.load(response)
    except Exception:
        print(json.dumps({"state": "UNAVAILABLE"}))
        return 2
    if not isinstance(releases, list) or not releases:
        print(json.dumps({"state": "NO_RELEASE"}))
        return 0
    latest = next((item for item in releases if not item.get("draft")), None)
    if latest is None:
        print(json.dumps({"state": "NO_RELEASE"}))
        return 0
    print(json.dumps({
        "state": "OK",
        "tag": latest.get("tag_name"),
        "name": latest.get("name"),
        "published_at": latest.get("published_at"),
        "url": latest.get("html_url"),
        "prerelease": bool(latest.get("prerelease")),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
