#!/usr/bin/env python3
"""
Generates two SVGs from a GitHub user's real contribution data:
  - streak.svg          (total / current streak / longest streak card)
  - activity-graph.svg  (last 31 days bar graph)

Data comes straight from GitHub's GraphQL contributionsCollection API —
the same data source that powers the user's actual profile contribution
graph — so there is no caching layer and no third-party service involved.
Run on a schedule via GitHub Actions and commit the output.
"""

import os
import sys
import json
import datetime
import urllib.request

USERNAME = os.environ.get("GH_USERNAME", "MugandaJames")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT_DIR = os.environ.get("OUT_DIR", "profile-assets")

# ---- palette (matches the tokyonight-ish theme used in the README) ----
BG = "#0d1117"
ACCENT = "#7C3AED"
ACCENT_DIM = "#3d2166"
TEXT = "#c9d1d9"
SUBTEXT = "#8b949e"
FIRE = "#FF6B35"


def fetch_contributions(username: str, token: str) -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    body = json.dumps({"query": query, "variables": {"login": username}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "readme-stats-script",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())

    if "errors" in payload:
        raise RuntimeError(f"GitHub API error: {payload['errors']}")

    calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append(
                {
                    "date": datetime.date.fromisoformat(day["date"]),
                    "count": day["contributionCount"],
                }
            )
    days.sort(key=lambda d: d["date"])
    return {"total": calendar["totalContributions"], "days": days}


def compute_streaks(days: list) -> tuple:
    """Returns (current_streak, longest_streak)."""
    today = datetime.date.today()
    # only consider days up to and including today (calendar can include future placeholder days)
    past = [d for d in days if d["date"] <= today]

    longest = 0
    running = 0
    for d in past:
        if d["count"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    current = 0
    for d in reversed(past):
        if d["count"] > 0:
            current += 1
        elif d["date"] == today:
            # today having zero contributions yet doesn't break an existing streak
            continue
        else:
            break

    return current, longest


def render_streak_svg(total: int, current: int, longest: int) -> str:
    return f"""<svg width="495" height="195" viewBox="0 0 495 195" xmlns="http://www.w3.org/2000/svg">
  <rect width="495" height="195" rx="10" fill="{BG}"/>
  <text x="247" y="30" text-anchor="middle" fill="{TEXT}" font-family="Segoe UI, sans-serif" font-size="14">
    Generated {datetime.date.today().isoformat()} · from live GitHub data
  </text>

  <g transform="translate(60,60)">
    <text x="0" y="0" text-anchor="middle" fill="{ACCENT}" font-family="Segoe UI, sans-serif" font-size="34" font-weight="bold">{total}</text>
    <text x="0" y="26" text-anchor="middle" fill="{SUBTEXT}" font-family="Segoe UI, sans-serif" font-size="12">Total Contributions</text>
  </g>

  <g transform="translate(247,60)">
    <circle cx="0" cy="-10" r="46" fill="none" stroke="{FIRE}" stroke-width="4"/>
    <text x="0" y="0" text-anchor="middle" fill="{FIRE}" font-family="Segoe UI, sans-serif" font-size="34" font-weight="bold">{current}</text>
    <text x="0" y="26" text-anchor="middle" fill="{SUBTEXT}" font-family="Segoe UI, sans-serif" font-size="12">Current Streak</text>
  </g>

  <g transform="translate(434,60)">
    <text x="0" y="0" text-anchor="middle" fill="{ACCENT}" font-family="Segoe UI, sans-serif" font-size="34" font-weight="bold">{longest}</text>
    <text x="0" y="26" text-anchor="middle" fill="{SUBTEXT}" font-family="Segoe UI, sans-serif" font-size="12">Longest Streak</text>
  </g>
</svg>"""


def render_activity_svg(days: list) -> str:
    last_31 = days[-31:]
    max_count = max((d["count"] for d in last_31), default=1) or 1

    width = 900
    height = 220
    left_pad = 30
    right_pad = 30
    top_pad = 40
    bottom_pad = 40
    plot_w = width - left_pad - right_pad
    plot_h = height - top_pad - bottom_pad
    bar_gap = 4
    bar_w = (plot_w / len(last_31)) - bar_gap

    bars = []
    for i, d in enumerate(last_31):
        bar_h = 0 if d["count"] == 0 else max(4, (d["count"] / max_count) * plot_h)
        x = left_pad + i * (bar_w + bar_gap)
        y = top_pad + (plot_h - bar_h)
        color = ACCENT if d["count"] > 0 else ACCENT_DIM
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="2" fill="{color}"><title>{d["date"]}: {d["count"]} contributions</title></rect>'
        )

    first_label = last_31[0]["date"].strftime("%b %d")
    last_label = last_31[-1]["date"].strftime("%b %d")

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" rx="10" fill="{BG}"/>
  <text x="{width/2}" y="24" text-anchor="middle" fill="{TEXT}" font-family="Segoe UI, sans-serif" font-size="16" font-weight="bold">
    Contribution Activity — Last 31 Days
  </text>
  {''.join(bars)}
  <text x="{left_pad}" y="{height-12}" fill="{SUBTEXT}" font-family="Segoe UI, sans-serif" font-size="11">{first_label}</text>
  <text x="{width-right_pad}" y="{height-12}" text-anchor="end" fill="{SUBTEXT}" font-family="Segoe UI, sans-serif" font-size="11">{last_label}</text>
</svg>"""


def main():
    if not TOKEN:
        print("ERROR: GH_TOKEN (or GITHUB_TOKEN) env var not set.", file=sys.stderr)
        sys.exit(1)

    data = fetch_contributions(USERNAME, TOKEN)
    current, longest = compute_streaks(data["days"])

    os.makedirs(OUT_DIR, exist_ok=True)

    with open(os.path.join(OUT_DIR, "streak.svg"), "w") as f:
        f.write(render_streak_svg(data["total"], current, longest))

    with open(os.path.join(OUT_DIR, "activity-graph.svg"), "w") as f:
        f.write(render_activity_svg(data["days"]))

    print(f"OK: total={data['total']} current_streak={current} longest_streak={longest}")


if __name__ == "__main__":
    main()
