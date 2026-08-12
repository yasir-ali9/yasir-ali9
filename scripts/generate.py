#!/usr/bin/env python3
"""Build the light and dark profile cards from portrait SVGs and GitHub data."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets"
API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"


def request_json(url: str, token: str = "", payload: dict | None = None) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "yasir-ali9-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def github_stats(username: str) -> dict[str, str | int]:
    token = os.getenv("GITHUB_TOKEN", "")
    user = request_json(f"{API}/users/{username}", token)
    repos = request_json(f"{API}/users/{username}/repos?type=owner&per_page=100", token)

    stats: dict[str, str | int] = {
        "repos": user.get("public_repos", 0),
        "stars": sum(repo.get("stargazers_count", 0) for repo in repos),
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "account_age": account_age(user["created_at"]),
        "contributions": "—",
    }

    if token:
        year = datetime.now(timezone.utc).year
        query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar { totalContributions }
            }
          }
        }
        """
        payload = {
            "query": query,
            "variables": {
                "login": username,
                "from": f"{year}-01-01T00:00:00Z",
                "to": f"{year}-12-31T23:59:59Z",
            },
        }
        result = request_json(GRAPHQL, token, payload)
        try:
            stats["contributions"] = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        except (KeyError, TypeError):
            pass
    return stats


def account_age(created_at: str) -> str:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    years = now.year - created.year
    months = now.month - created.month
    if now.day < created.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12
    return f"{years}y {months}m"


def portrait_contents(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"<svg\b[^>]*>(.*)</svg>\s*$", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not read SVG contents from {path}")
    return match.group(1)


def value(value: object) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def row(y: int, label: str, data: object, *, x: int = 510) -> str:
    label_text = escape(label)
    data_text = escape(value(data))
    return (
        f'<text x="{x}" y="{y}" class="line">'
        f'<tspan class="prompt">›</tspan> '
        f'<tspan class="key">{label_text}</tspan>'
        f'<tspan class="muted">  {"·" * max(3, 27 - len(label) - len(data_text))}  </tspan>'
        f'<tspan class="value">{data_text}</tspan></text>'
    )


def section(y: int, title: str) -> str:
    rule = "─" * max(8, 43 - len(title))
    return (
        f'<text x="510" y="{y}" class="section">'
        f'<tspan class="prompt">╭─</tspan> {escape(title)} '
        f'<tspan class="muted">{rule}</tspan></text>'
    )


def render(theme: str, profile: dict, stats: dict, portrait: str) -> str:
    dark = theme == "dark"
    colors = {
        "background": "#151b24" if dark else "#f3f4f6",
        "panel": "#151b24" if dark else "#f3f4f6",
        "border": "#374358" if dark else "#d1d5db",
        "text": "#e6edf3" if dark else "#1f2328",
        "muted": "#6e7681" if dark else "#8c959f",
        "accent": "#ffa657" if dark else "#bc4c00",
        "value": "#79c0ff" if dark else "#0969da",
        "green": "#3fb950" if dark else "#1a7f37",
        "dot": "#374358" if dark else "#aeb4bd",
    }

    info_rows = [
        row(114, "Role", profile["role"]),
        row(142, "Location", profile["location"]),
        row(170, "OS", profile["os"]),
        row(198, "Terminal", profile["terminal"]),
        row(226, "Editor", profile["editor"]),
    ]
    stack_rows = [
        row(294, "Focus", profile["focus"]),
        row(322, "Languages", profile["languages"]),
        row(350, "Tools", profile["tools"]),
        row(378, "Interests", profile["interests"]),
    ]
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="640" viewBox="0 0 1200 640" role="img" aria-labelledby="title description">
  <title id="title">{escape(profile["display_name"])}'s GitHub profile</title>
  <desc id="description">A terminal-style profile card with an ASCII portrait and GitHub statistics.</desc>
  <style>
    .line, .section, .header, .footer {{ font-family: Consolas, "Liberation Mono", Menlo, monospace; }}
    .header {{ font-size: 21px; font-weight: 700; fill: {colors["text"]}; }}
    .section {{ font-size: 17px; font-weight: 600; fill: {colors["text"]}; }}
    .line {{ font-size: 16px; fill: {colors["text"]}; }}
    .footer {{ font-size: 12px; fill: {colors["muted"]}; }}
    .key {{ fill: {colors["accent"]}; }}
    .value {{ fill: {colors["value"]}; }}
    .muted {{ fill: {colors["muted"]}; }}
    .prompt {{ fill: {colors["green"]}; }}
  </style>
  <rect width="1200" height="640" rx="12" fill="{colors["background"]}"/>
  <circle cx="25" cy="24" r="6" fill="{colors["dot"]}"/>
  <circle cx="45" cy="24" r="6" fill="{colors["dot"]}"/>
  <circle cx="65" cy="24" r="6" fill="{colors["dot"]}"/>
  <text x="510" y="51" class="header">{escape(profile["display_name"])}</text>
  <line x1="490" y1="62" x2="490" y2="608" stroke="{colors["border"]}"/>
  <g transform="translate(4 30) scale(1.08)">{portrait}</g>
  {section(86, "SYSTEM")}
  {''.join(info_rows)}
  {section(266, "STACK")}
  {''.join(stack_rows)}
</svg>
'''


def main() -> None:
    profile = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
    try:
        stats = github_stats(profile["username"])
    except (urllib.error.URLError, TimeoutError, KeyError) as error:
        print(f"warning: GitHub data unavailable ({error}); using fallback values")
        stats = {
            "repos": "—",
            "stars": "—",
            "followers": "—",
            "following": "—",
            "contributions": "—",
            "account_age": "—",
        }

    OUTPUT_DIR.mkdir(exist_ok=True)
    themes = {
        "dark": ROOT / "white.svg",
        "light": ROOT / "black.svg",
    }
    for theme, portrait_path in themes.items():
        output = OUTPUT_DIR / f"{theme}.svg"
        output.write_text(render(theme, profile, stats, portrait_contents(portrait_path)), encoding="utf-8")
        print(f"wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
