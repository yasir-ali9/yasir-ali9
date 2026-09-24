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
ASSET_VERSION = "v10"
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
    """Fetch the concise public GitHub statistics shown on the profile card."""
    token = os.getenv("GITHUB_TOKEN", "")
    user = request_json(f"{API}/users/{username}", token)
    repos = request_json(f"{API}/users/{username}/repos?type=owner&per_page=100", token)
    return {
        "repositories": int(user.get("public_repos", len(repos))),
        "stars": sum(int(repo.get("stargazers_count", 0)) for repo in repos),
    }


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
  <path d="M510 222H1170" stroke="{colors["border"]}"/>
  <text x="510" y="258" class="section">TOP OPEN-SOURCE REPOS</text>
  {linked_list(OPEN_SOURCE_REPOS, 292)}
  <path d="M510 438H1170" stroke="{colors["border"]}"/>
  <text x="510" y="474" class="section">SELECTED PROJECTS</text>
  {linked_list(SELECTED_PROJECTS, 508)}
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
