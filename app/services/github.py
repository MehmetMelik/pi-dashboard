"""GitHub activity via GitHub REST/GraphQL API (using gh CLI token)."""

import subprocess
import json

GH_USERNAME = "MehmetMelik"
CONTRIB_QUERY = '''
{ user(login: "%s") {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
  }
}
''' % GH_USERNAME


def _gh_api(endpoint: str) -> list | dict | None:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[github] API error: {e}")
        return None


def _gh_graphql(query: str) -> dict | None:
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[github] GraphQL error: {e}")
        return None


def _get_pr_title(repo: str, number: int) -> str:
    data = _gh_api(f"/repos/{repo}/pulls/{number}")
    if data and isinstance(data, dict):
        return data.get("title", "")
    return ""


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def get_contribution_graph() -> dict | None:
    """Fetch the GitHub contribution calendar (green squares)."""
    data = _gh_graphql(CONTRIB_QUERY)
    if not data:
        return None
    try:
        cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total = cal["totalContributions"]
        weeks = cal["weeks"]

        graph_weeks = []
        month_labels = []  # {index: week_index, name: "Jan"}
        seen_months = set()

        for wi, w in enumerate(weeks):
            days = []
            for d in w["contributionDays"]:
                count = d["contributionCount"]
                if count == 0:
                    level = 0
                elif count <= 3:
                    level = 1
                elif count <= 8:
                    level = 2
                elif count <= 15:
                    level = 3
                else:
                    level = 4
                days.append({
                    "date": d["date"],
                    "count": count,
                    "level": level,
                })

            # Detect month boundary: check first day of this week
            if days:
                first_date = days[0]["date"]  # "YYYY-MM-DD"
                month_num = int(first_date[5:7])
                year_month = first_date[:7]
                if year_month not in seen_months:
                    seen_months.add(year_month)
                    month_labels.append({
                        "index": wi,
                        "name": MONTH_NAMES[month_num - 1],
                    })

            graph_weeks.append(days)

        return {
            "total": total,
            "weeks": graph_weeks,
            "months": month_labels,
        }
    except (KeyError, TypeError) as e:
        print(f"[github] contribution parse error: {e}")
        return None


def get_activity() -> dict:
    """Fetch recent GitHub activity for the authenticated user."""
    activity = {
        "events": [],
        "notifications": [],
        "contributions": get_contribution_graph(),
    }

    events = _gh_api(f"/users/{GH_USERNAME}/events?per_page=5")
    if events and isinstance(events, list):
        for e in events[:5]:
            etype = e.get("type", "")
            repo = e.get("repo", {}).get("name", "")
            created = e.get("created_at", "")[:16].replace("T", " ")
            payload = e.get("payload", {})

            desc = ""
            icon = ""
            url = f"https://github.com/{repo}"

            if etype == "PushEvent":
                ref = payload.get("ref", "").replace("refs/heads/", "")
                head = payload.get("head", "")[:7]
                desc = f"Pushed to {ref}" if ref else "Pushed commits"
                if head:
                    desc += f" ({head})"
                icon = "push"

            elif etype == "CreateEvent":
                ref_type = payload.get("ref_type", "")
                ref = payload.get("ref", "")
                if ref_type == "branch":
                    desc = f"Created branch {ref}"
                elif ref_type == "tag":
                    desc = f"Created tag {ref}"
                elif ref_type == "repository":
                    desc = "Created repository"
                else:
                    desc = f"Created {ref_type} {ref}" if ref else f"Created {ref_type}"
                icon = "create"

            elif etype == "DeleteEvent":
                ref_type = payload.get("ref_type", "")
                ref = payload.get("ref", "")
                desc = f"Deleted {ref_type} {ref}"
                icon = "delete"

            elif etype == "PullRequestEvent":
                action = payload.get("action", "")
                number = payload.get("number", 0)
                pr = payload.get("pull_request", {})
                title = pr.get("title", "")
                if not title and pr.get("head", {}).get("ref"):
                    title = pr["head"]["ref"]
                if not title and number and repo:
                    title = _get_pr_title(repo, number)
                pr_url = pr.get("html_url") or pr.get("url", "")
                if pr_url and "api.github.com" in pr_url:
                    pr_url = pr_url.replace("api.github.com/repos", "github.com").replace("/pulls/", "/pull/")
                url = pr_url or url
                desc = f"{action.capitalize()} PR #{number}"
                if title:
                    desc += f": {title[:55]}"
                icon = "pr"

            elif etype == "IssuesEvent":
                action = payload.get("action", "")
                issue = payload.get("issue", {})
                title = issue.get("title", "")[:55]
                url = issue.get("html_url", url)
                desc = f"{action.capitalize()} issue: {title}"
                icon = "issue"

            elif etype == "WatchEvent":
                desc = "Starred repository"
                icon = "star"

            elif etype == "ForkEvent":
                forkee = payload.get("forkee", {})
                desc = f"Forked to {forkee.get('full_name', '')}" if forkee.get("full_name") else "Forked repository"
                icon = "fork"

            elif etype == "IssueCommentEvent":
                issue = payload.get("issue", {})
                title = issue.get("title", "")[:50]
                url = payload.get("comment", {}).get("html_url", url)
                desc = f"Commented on: {title}"
                icon = "comment"

            elif etype == "ReleaseEvent":
                action = payload.get("action", "")
                release = payload.get("release", {})
                tag = release.get("tag_name", "")
                desc = f"{action.capitalize()} release {tag}"
                icon = "release"
            else:
                desc = etype.replace("Event", "")
                icon = "other"

            if desc:
                activity["events"].append({
                    "type": icon,
                    "repo": repo,
                    "description": desc,
                    "time": created,
                    "url": url,
                })

    # Notifications
    notifs = _gh_api("/notifications?per_page=5")
    if notifs and isinstance(notifs, list):
        for n in notifs[:5]:
            subject = n.get("subject", {})
            repo = n.get("repository", {}).get("full_name", "")
            activity["notifications"].append({
                "title": subject.get("title", "")[:80],
                "type": subject.get("type", ""),
                "repo": repo,
                "reason": n.get("reason", ""),
                "unread": n.get("unread", False),
            })

    return activity
