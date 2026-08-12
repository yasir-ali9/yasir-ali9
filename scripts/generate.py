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
ASSET_VERSION = "v7"
API = "https://api.github.com"


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


def github_code_growth(username: str) -> dict[str, object]:
    """Aggregate real weekly additions and deletions across owned public repos."""
    token = os.getenv("GITHUB_TOKEN", "")
    repos = request_json(f"{API}/users/{username}/repos?type=owner&per_page=100", token)
    now = datetime.now(timezone.utc)
    days_since_sunday = (now.weekday() + 1) % 7
    current_sunday = (now - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_seconds = 7 * 24 * 60 * 60
    weeks = [int(current_sunday.timestamp()) - week_seconds * offset for offset in range(51, -1, -1)]
    weekly = {week: [0, 0] for week in weeks}
    repositories = 0

    for repo in repos:
        if repo.get("fork") or repo.get("size", 0) == 0 or repo.get("name") == username:
            continue
        frequency = repository_code_frequency(repo["full_name"], token)
        if not frequency:
            continue
        repositories += 1
        for timestamp, additions, deletions in frequency:
            if timestamp in weekly:
                weekly[timestamp][0] += additions
                weekly[timestamp][1] += abs(deletions)

    additions = sum(values[0] for values in weekly.values())
    deletions = sum(values[1] for values in weekly.values())
    cumulative: list[int] = []
    running = 0
    for week in weeks:
        running += weekly[week][0] - weekly[week][1]
        cumulative.append(running)

    return {
        "series": cumulative,
        "additions": additions,
        "deletions": deletions,
        "net": additions - deletions,
        "repositories": repositories,
        "start": datetime.fromtimestamp(weeks[0], timezone.utc),
        "end": datetime.fromtimestamp(weeks[-1], timezone.utc),
    }


def portrait_contents(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"<svg\b[^>]*>(.*)</svg>\s*$", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not read SVG contents from {path}")
    return match.group(1)


def compact_number(number: int) -> str:
    absolute = abs(number)
    if absolute >= 1_000_000:
        result = f"{absolute / 1_000_000:.1f}m"
    elif absolute >= 1_000:
        result = f"{absolute / 1_000:.1f}k"
    else:
        result = str(absolute)
    return ("−" if number < 0 else "+" if number > 0 else "") + result


def signed_number(number: int) -> str:
    sign = "−" if number < 0 else "+" if number > 0 else ""
    return f"{sign}{abs(number):,}"


def ascii_chart(series: list[int], width: int = 52, height: int = 15) -> list[tuple[str, str]]:
    """Create an ASCII area chart as (axis label, plot) rows."""
    if not series:
        series = [0] * width
    if len(series) != width:
        series = [series[round(index * (len(series) - 1) / (width - 1))] for index in range(width)]

    minimum = min(0, min(series))
    maximum = max(0, max(series))
    if minimum == maximum:
        maximum = minimum + 1

    grid = [[" " for _ in range(width)] for _ in range(height)]
    for column, point in enumerate(series):
        row = round((maximum - point) * (height - 1) / (maximum - minimum))
        grid[row][column] = "●" if column == width - 1 else "•"
        for fill_row in range(row + 1, height):
            grid[fill_row][column] = "░"

    middle = height // 2
    rows: list[tuple[str, str]] = []
    for row in range(height):
        axis_value = round(maximum - row * (maximum - minimum) / (height - 1))
        label = f"{compact_number(axis_value):>7}" if row in (0, middle, height - 1) else " " * 7
        axis = "┼" if row == height - 1 else "┤"
        rows.append((f"{label} {axis}", "".join(grid[row])))
    return rows


def chart_markup(growth: dict[str, object]) -> str:
    lines = []
    for index, (axis, plot) in enumerate(ascii_chart(growth["series"])):
        y = 145 + index * 21
        lines.append(
            f'<text x="510" y="{y}" class="chart">'
            f'<tspan class="muted">{escape(axis)}</tspan>'
            f'<tspan class="chart-area">{escape(plot)}</tspan></text>'
        )
    return "".join(lines)


def render(theme: str, profile: dict, growth: dict[str, object], portrait: str) -> str:
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

    net_class = "growth" if growth["net"] >= 0 else "accent"
    start_label = growth["start"].strftime("%b '%y")
    end_label = growth["end"].strftime("%b '%y")
    updated = datetime.now(timezone.utc).strftime("%d %b %Y")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="585" viewBox="0 0 1200 585" role="img" aria-labelledby="title description">
  <title id="title">{escape(profile["display_name"])}'s GitHub profile</title>
  <desc id="description">An ASCII portrait and a real 52-week graph of net line changes across owned public GitHub repositories.</desc>
  <style>
    .line, .section, .header, .footer, .chart {{ font-family: Consolas, "Liberation Mono", Menlo, monospace; }}
    .header {{ font-size: 21px; font-weight: 700; fill: {colors["text"]}; }}
    .section {{ font-size: 17px; font-weight: 600; fill: {colors["text"]}; }}
    .line {{ font-size: 16px; fill: {colors["text"]}; }}
    .footer {{ font-size: 12px; fill: {colors["muted"]}; }}
    .chart {{ font-size: 14px; white-space: pre; }}
    .chart-area {{ fill: {colors["value"]}; }}
    .key {{ fill: {colors["accent"]}; }}
    .value {{ fill: {colors["value"]}; }}
    .muted {{ fill: {colors["muted"]}; }}
    .prompt {{ fill: {colors["green"]}; }}
    .growth {{ fill: {colors["green"]}; }}
    .accent {{ fill: {colors["accent"]}; }}
  </style>
  <rect width="1200" height="585" rx="12" fill="{colors["background"]}"/>
  <circle cx="25" cy="24" r="6" fill="{colors["dot"]}"/>
  <circle cx="45" cy="24" r="6" fill="{colors["dot"]}"/>
  <circle cx="65" cy="24" r="6" fill="{colors["dot"]}"/>
  <text x="510" y="51" class="header">{escape(profile["display_name"])}</text>
  <line x1="490" y1="62" x2="490" y2="573" stroke="{colors["border"]}"/>
  <g transform="translate(4 18) scale(1.08)">{portrait}</g>
  <text x="510" y="91" class="section"><tspan class="prompt">╭─</tspan> CODE GROWTH <tspan class="muted">· LAST 52 WEEKS ─────────────</tspan></text>
  <text x="510" y="119" class="line"><tspan class="key">NET CHANGE</tspan><tspan class="muted">  ···················  </tspan><tspan class="{net_class}">{escape(signed_number(growth["net"]))} lines</tspan></text>
  {chart_markup(growth)}
  <text x="585" y="477" class="footer">{escape(start_label)}<tspan dx="350">{escape(end_label)}</tspan></text>
  <text x="510" y="515" class="line"><tspan class="growth">+{growth["additions"]:,}</tspan><tspan class="muted"> added</tspan><tspan dx="28" class="accent">−{growth["deletions"]:,}</tspan><tspan class="muted"> removed</tspan></text>
  <text x="510" y="548" class="footer">{growth["repositories"]} owned public repositories · refreshed {escape(updated)}</text>
</svg>
'''


def main() -> None:
    profile = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
    try:
        growth = github_code_growth(profile["username"])
    except (urllib.error.URLError, TimeoutError, KeyError, TypeError) as error:
        print(f"warning: GitHub data unavailable ({error}); using fallback values")
        now = datetime.now(timezone.utc)
        growth = {
            "series": [0] * 52,
            "additions": 0,
            "deletions": 0,
            "net": 0,
            "repositories": 0,
            "start": now - timedelta(weeks=51),
            "end": now,
        }

    OUTPUT_DIR.mkdir(exist_ok=True)
    themes = {
        "dark": ROOT / "white.svg",
        "light": ROOT / "black.svg",
    }
    for theme, portrait_path in themes.items():
        output = OUTPUT_DIR / f"{theme}-{ASSET_VERSION}.svg"
        output.write_text(render(theme, profile, growth, portrait_contents(portrait_path)), encoding="utf-8")
        print(f"wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
