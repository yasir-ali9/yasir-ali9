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
ASSET_VERSION = "v9"
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


def active_window(growth: dict[str, object]) -> tuple[list[int], datetime]:
    """Trim empty leading weeks while retaining one week of visual context."""
    series = growth["series"]
    changes = [series[0]] + [series[index] - series[index - 1] for index in range(1, len(series))]
    first_active = next((index for index, change in enumerate(changes) if change), len(series) - 1)
    start_index = max(0, first_active - 1)
    return series[start_index:], growth["start"] + timedelta(weeks=start_index)


def ascii_chart(series: list[int], width: int = 62, height: int = 18) -> list[tuple[str, str]]:
    """Create a connected ASCII line chart as (axis label, plot) rows."""
    if not series:
        series = [0] * width
    if len(series) == 1:
        samples = series * width
    else:
        samples = []
        for column in range(width):
            position = column * (len(series) - 1) / (width - 1)
            left = int(position)
            right = min(left + 1, len(series) - 1)
            fraction = position - left
            samples.append(round(series[left] * (1 - fraction) + series[right] * fraction))

    minimum = min(0, min(samples))
    maximum = max(0, max(samples))
    if minimum == maximum:
        maximum = minimum + 1

    grid = [[" " for _ in range(width)] for _ in range(height)]
    point_rows = [round((maximum - point) * (height - 1) / (maximum - minimum)) for point in samples]
    grid[point_rows[0]][0] = "●"
    for column in range(1, width):
        previous = point_rows[column - 1]
        current = point_rows[column]
        if current == previous:
            grid[current][column] = "─"
        elif current < previous:
            grid[current][column] = "╱"
            for row in range(current + 1, previous + 1):
                grid[row][column] = "│"
        else:
            grid[current][column] = "╲"
            for row in range(previous, current):
                grid[row][column] = "│"
    grid[point_rows[-1]][-1] = "●"

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
    series, _ = active_window(growth)
    for index, (axis, plot) in enumerate(ascii_chart(series)):
        y = 158 + index * 21
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
        "text": "#c9d1d9" if dark else "#3f4752",
        "muted": "#c9d1d9" if dark else "#3f4752",
        "accent": "#c9d1d9" if dark else "#3f4752",
        "value": "#c9d1d9" if dark else "#3f4752",
        "green": "#c9d1d9" if dark else "#3f4752",
        "dot": "#c9d1d9" if dark else "#3f4752",
    }
    portrait = re.sub(r'fill="(?:#f5f5f5|#000000)"', f'fill="{colors["text"]}"', portrait)

    active_series, active_start = active_window(growth)
    start_label = active_start.strftime("%b '%y")
    end_label = growth["end"].strftime("%b '%y")
    updated = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    window_weeks = len(active_series)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="585" viewBox="0 0 1200 585" role="img" aria-labelledby="title description">
  <title id="title">{escape(profile["display_name"])}'s GitHub profile</title>
  <desc id="description">An ASCII portrait and a real active-window graph of net line changes across owned public GitHub repositories.</desc>
  <style>
    .line, .section, .header, .footer, .chart {{ font-family: Consolas, "Liberation Mono", Menlo, monospace; }}
    .header {{ font-size: 21px; font-weight: 700; fill: {colors["text"]}; }}
    .section {{ font-size: 17px; font-weight: 600; fill: {colors["text"]}; }}
    .line {{ font-size: 16px; fill: {colors["text"]}; }}
    .footer {{ font-size: 12px; fill: {colors["muted"]}; }}
    .chart {{ font-size: 14px; white-space: pre; }}
    .chart-area {{ fill: {colors["text"]}; }}
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
  <g transform="translate(4 18) scale(1.08)">{portrait}</g>
  <text x="510" y="64" class="section">CODE GROWTH <tspan class="muted">· ACTIVE {window_weeks} WEEKS</tspan></text>
  <text x="510" y="98" class="line">NET {escape(signed_number(growth["net"]))}</text>
  <text x="1170" y="98" text-anchor="end" class="line">+{growth["additions"]:,}<tspan dx="28">−{growth["deletions"]:,}</tspan></text>
  <text x="1170" y="128" text-anchor="end" class="footer">{growth["repositories"]} REPOSITORIES  •  {escape(updated)} SYNCED</text>
  {chart_markup(growth)}
  <text x="585" y="548" class="footer">{escape(start_label)}</text>
  <text x="1115" y="548" text-anchor="end" class="footer">{escape(end_label)}</text>
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
