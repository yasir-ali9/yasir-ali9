#!/usr/bin/env python3
"""Build the light and dark profile cards from portrait SVGs and GitHub data."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets"
ASSET_VERSION = "v11"
API = "https://api.github.com"

OPEN_SOURCE_REPOS = (
    ("resend-mail", "https://github.com/yasir-ali9/resend-mail"),
    ("minimal", "https://github.com/yasir-ali9/minimal"),
    ("claude-code-line", "https://github.com/yasir-ali9/claude-code-line"),
    ("pixels-to-text", "https://github.com/yasir-ali9/pixels-to-text"),
)

SELECTED_PROJECTS = (
    ("feppel.com", "https://feppel.com"),
    ("leebai.com", "https://leebai.com"),
    ("osho.pk", "https://osho.pk"),
    ("enviroconsulting.co", "https://enviroconsulting.co"),
)


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


def github_statistics(username: str) -> dict[str, int]:
    """Fetch concise public and 52-week code statistics for the profile card."""
    token = os.getenv("GITHUB_TOKEN", "")
    user = request_json(f"{API}/users/{username}", token)
    repos = request_json(f"{API}/users/{username}/repos?type=owner&per_page=100", token)
    additions, deletions = code_changes_last_year(repos, token)
    return {
        "repositories": int(user.get("public_repos", len(repos))),
        "stars": sum(int(repo.get("stargazers_count", 0)) for repo in repos),
        "additions": additions,
        "deletions": deletions,
        "net": additions - deletions,
    }


def code_changes_last_year(repos: dict | list, token: str) -> tuple[int, int]:
    """Sum additions and deletions over the last 52 weeks for owned repositories."""
    if not isinstance(repos, list):
        return 0, 0

    earliest = int((datetime.now(timezone.utc) - timedelta(weeks=52)).timestamp())
    additions = 0
    deletions = 0
    for repo in repos:
        if repo.get("fork") or repo.get("size", 0) == 0:
            continue
        frequency = repository_code_frequency(repo["full_name"], token)
        for timestamp, added, deleted in frequency:
            if timestamp >= earliest:
                additions += added
                deletions += abs(deleted)
    return additions, deletions


def repository_code_frequency(full_name: str, token: str) -> list[list[int]]:
    """Return weekly [timestamp, additions, deletions] data for one repository."""
    url = f"{API}/repos/{full_name}/stats/code_frequency"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "yasir-ali9-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 202:
                    time.sleep(2 * (attempt + 1))
                    continue
                data = json.load(response)
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as error:
            if error.code == 202:
                time.sleep(2 * (attempt + 1))
                continue
            if error.code in (204, 409, 422):
                return []
            raise
    return []


def portrait_contents(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"<svg\b[^>]*>(.*)</svg>\s*$", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not read SVG contents from {path}")
    return match.group(1)


def linked_list(items: tuple[tuple[str, str], ...], y_start: int) -> str:
    """Render a short, clickable terminal-style list."""
    return "".join(
        f'<a href="{escape(url, quote=True)}"><text x="510" y="{y_start + index * 34}" class="line link">› {escape(label)}</text></a>'
        for index, (label, url) in enumerate(items)
    )


def signed_number(number: int) -> str:
    sign = "−" if number < 0 else "+" if number > 0 else ""
    return f"{sign}{abs(number):,}"


def render(theme: str, profile: dict, statistics: dict[str, int], portrait: str) -> str:
    dark = theme == "dark"
    colors = {
        "background": "#151b24" if dark else "#f3f4f6",
        "panel": "#151b24" if dark else "#f3f4f6",
        "border": "#374358" if dark else "#d1d5db",
        "text": "#c9d1d9" if dark else "#3f4752",
        "muted": "#c9d1d9" if dark else "#3f4752",
        "accent": "#c9d1d9" if dark else "#3f4752",
        "value": "#c9d1d9" if dark else "#3f4752",
        "green": "#c9d1d9" if dark else "#3f4752",
        "dot": "#c9d1d9" if dark else "#3f4752",
    }
    portrait = re.sub(r'fill="(?:#f5f5f5|#000000)"', f'fill="{colors["text"]}"', portrait)

    updated = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" role="img" aria-labelledby="title description">
  <title id="title">{escape(profile["display_name"])}'s GitHub profile</title>
  <desc id="description">An ASCII portrait with GitHub statistics, open-source repositories, and selected projects.</desc>
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
    .growth {{ fill: {colors["green"]}; }}
    .accent {{ fill: {colors["accent"]}; }}
    .link {{ fill: {colors["text"]}; text-decoration: underline; }}
  </style>
  <rect width="1200" height="720" rx="12" fill="{colors["background"]}"/>
  <circle cx="25" cy="24" r="6" fill="{colors["dot"]}"/>
  <circle cx="45" cy="24" r="6" fill="{colors["dot"]}"/>
  <circle cx="65" cy="24" r="6" fill="{colors["dot"]}"/>
  <g transform="translate(4 18) scale(1.08)">{portrait}</g>
  <text x="510" y="64" class="section">GITHUB STATISTICS</text>
  <text x="510" y="100" class="line">PUBLIC REPOSITORIES <tspan class="value">{statistics["repositories"]:,}</tspan></text>
  <text x="510" y="130" class="line">TOTAL STARS        <tspan class="value">{statistics["stars"]:,}</tspan></text>
  <text x="510" y="160" class="line">NET CODE · 52 WEEKS <tspan class="value">{signed_number(statistics["net"])}</tspan></text>
  <text x="510" y="190" class="line">ADDITIONS          <tspan class="value">+{statistics["additions"]:,}</tspan></text>
  <text x="510" y="220" class="line">DELETIONS          <tspan class="value">−{statistics["deletions"]:,}</tspan></text>
  <path d="M510 252H1170" stroke="{colors["border"]}"/>
  <text x="510" y="288" class="section">TOP OPEN-SOURCE REPOS</text>
  {linked_list(OPEN_SOURCE_REPOS, 322)}
  <path d="M510 468H1170" stroke="{colors["border"]}"/>
  <text x="510" y="504" class="section">SELECTED PROJECTS</text>
  {linked_list(SELECTED_PROJECTS, 538)}
  <text x="1170" y="682" text-anchor="end" class="footer">{escape(updated)} SYNCED</text>
</svg>
'''


def main() -> None:
    profile = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
    try:
        statistics = github_statistics(profile["username"])
    except (urllib.error.URLError, TimeoutError, KeyError, TypeError) as error:
        print(f"warning: GitHub data unavailable ({error}); using fallback values")
        statistics = {
            "repositories": 0,
            "stars": 0,
            "additions": 0,
            "deletions": 0,
            "net": 0,
        }

    OUTPUT_DIR.mkdir(exist_ok=True)
    themes = {
        "dark": ROOT / "white.svg",
        "light": ROOT / "black.svg",
    }
    for theme, portrait_path in themes.items():
        output = OUTPUT_DIR / f"{theme}-{ASSET_VERSION}.svg"
        output.write_text(render(theme, profile, statistics, portrait_contents(portrait_path)), encoding="utf-8")
        print(f"wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
