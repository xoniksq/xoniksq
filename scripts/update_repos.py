#!/usr/bin/env python3
"""Regenerate the ~/repos block of the profile README.

Fetches the owner's public repositories, draws one SVG card per repository
into cards/, and rewrites the part of README.md between the repos markers.

Usage: update_repos.py [owner]   (owner defaults to $GITHUB_REPOSITORY_OWNER)
"""

import json
import os
import re
import sys
import textwrap
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CARDS = ROOT / "cards"
CONFIG = Path(__file__).resolve().parent / "config.json"

START, END = "<!-- repos:start -->", "<!-- repos:end -->"

WIDTH = 720
LINE_CHARS = 74  # description characters that fit on one card line
MAX_LINES = 2

EMOJI = re.compile("[☀-➿️‍\U0001f000-\U0001faff]")

DEFAULT_LANG_COLOR = "#8b949e"
LANG_COLORS = {
    "Batchfile": "#C1F12E",
    "C": "#555555",
    "C#": "#178600",
    "C++": "#f34b7d",
    "CSS": "#663399",
    "Dart": "#00B4AB",
    "Dockerfile": "#384d54",
    "Go": "#00ADD8",
    "HTML": "#e34c26",
    "Java": "#b07219",
    "JavaScript": "#f1e05a",
    "Jupyter Notebook": "#DA5B0B",
    "Kotlin": "#A97BFF",
    "Lua": "#000080",
    "PHP": "#4F5D95",
    "PowerShell": "#012456",
    "Python": "#3572A5",
    "Ruby": "#701516",
    "Rust": "#dea584",
    "Shell": "#89e051",
    "Svelte": "#ff3e00",
    "Swift": "#F05138",
    "TypeScript": "#3178c6",
    "Vue": "#41b883",
}


def fetch_repos(owner):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-readme-cards"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    repos, page = [], 1
    while True:
        url = f"https://api.github.com/users/{owner}/repos?type=owner&per_page=100&page={page}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as resp:
            batch = json.load(resp)
        repos += batch
        if len(batch) < 100:
            return repos
        page += 1


def select(repos, owner, config):
    exclude = {name.lower() for name in config.get("exclude", [])} | {owner.lower(), ".github"}
    picked = [
        r
        for r in repos
        if not (r["private"] or r["fork"] or r["archived"]) and r["name"].lower() not in exclude
    ]
    picked.sort(key=lambda r: r["pushed_at"] or "", reverse=True)
    picked.sort(key=lambda r: r["stargazers_count"], reverse=True)
    return picked[: config.get("max", 6)]


def describe(repo, config):
    """Description as card lines: config override first, then the GitHub description."""
    text = config.get("descriptions", {}).get(repo["name"]) or repo["description"] or ""
    lines = []
    for part in EMOJI.sub("", text).split("\n"):
        lines += textwrap.wrap(" ".join(part.split()), LINE_CHARS)
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = lines[-1][: LINE_CHARS - 1].rstrip(" .,;:") + "…"
    return lines


def visible(color):
    """Lighten colours that would vanish on the dark card background."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    if 0.2126 * r + 0.7152 * g + 0.0722 * b >= 60:
        return color
    return "#{:02x}{:02x}{:02x}".format(*((c + 255) // 2 for c in (r, g, b)))


def card(repo, lines):
    name = escape(repo["name"])
    height = 74 + 22 * len(lines) if lines else 66

    meta = ""
    if repo["stargazers_count"]:
        meta += f'★ {repo["stargazers_count"]}   '
    if repo["language"]:
        color = visible(LANG_COLORS.get(repo["language"], DEFAULT_LANG_COLOR))
        meta += f'<tspan fill="{color}">●</tspan> {escape(repo["language"])}'

    body = "".join(
        f'\n  <text x="28" y="{70 + 22 * i}">{escape(line)}</text>' for i, line in enumerate(lines)
    )
    summary = escape(" ".join(lines + [repo["language"] or ""]).strip())

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="t d">
  <title id="t">{name}</title>
  <desc id="d">{summary}</desc>
  <style>
    text {{
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", "DejaVu Sans Mono", monospace;
      font-size: 14px;
      fill: #c9d1d9;
    }}
    .dim {{ fill: #8b949e; }}
    .k {{ fill: #58a6ff; font-weight: 700; }}
  </style>

  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="8" fill="#0d1117" stroke="#30363d"/>

  <text x="28" y="40"><tspan class="dim">~/repos/</tspan><tspan class="k">{name}</tspan></text>
  <text x="{WIDTH - 28}" y="40" text-anchor="end" class="dim" xml:space="preserve">{meta}</text>
{body}
</svg>
"""


def link(repo, lines):
    alt = escape(f'{repo["name"]}: {" ".join(lines)}' if lines else repo["name"], quote=True)
    return (
        '<p align="center">\n'
        f'  <a href="{repo["html_url"]}"><img src="cards/{repo["name"]}.svg" width="{WIDTH}" alt="{alt}"></a>\n'
        "</p>"
    )


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    owner = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_REPOSITORY_OWNER")
    if not owner:
        sys.exit("usage: update_repos.py <owner>")

    readme = README.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        sys.exit(f"README.md must contain {START} and {END}")

    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    repos = select(fetch_repos(owner), owner, config)

    CARDS.mkdir(exist_ok=True)
    keep, links = set(), []
    for repo in repos:
        lines = describe(repo, config)
        path = CARDS / f'{repo["name"]}.svg'
        write(path, card(repo, lines))
        keep.add(path.name)
        links.append(link(repo, lines))
    for stale in CARDS.glob("*.svg"):
        if stale.name not in keep:
            stale.unlink()

    head, rest = readme.split(START, 1)
    tail = rest.split(END, 1)[1]
    write(README, f"{head}{START}\n" + "\n\n".join(links) + f"\n{END}{tail}")
    print(f"{len(repos)} repo card(s): " + ", ".join(r["name"] for r in repos))


if __name__ == "__main__":
    main()
