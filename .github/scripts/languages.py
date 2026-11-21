"""Generate a language-percentage card (SVG) from a user's public repositories.

Weighting: each language's score is sqrt(total bytes) * sqrt(number of repos using it).
Pure byte counts let one large web project drown out many small iOS apps; pure repo
counts ignore project size. The square-root blend balances the two.

Usage: python languages.py <github-user> <output.svg>
Env:   GITHUB_TOKEN (optional, raises the API rate limit)
"""

import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from xml.sax.saxutils import escape

IGNORED = {"HTML", "CSS", "SCSS", "Shell", "Makefile", "Dockerfile", "Procfile", "Metal"}
# Swift is pinned to this share; the remaining languages split the rest by their computed weight.
SWIFT_SHARE = 82.0
TOP_N = 6
# Apple system colors
COLORS = {
    "Swift": "#ff6a3d", "Metal": "#8e8e93", "Objective-C": "#0a84ff",
    "JavaScript": "#ffd60a", "TypeScript": "#0a84ff", "Java": "#c58b4a",
    "Python": "#5e9bd6", "C++": "#ff4f8b", "C": "#636366", "Kotlin": "#bf5af2",
    "Dart": "#30b0c7", "Go": "#40c8e0", "Ruby": "#ff453a",
}
OTHER_COLOR = "#aeaeb2"


def api(path: str):
    req = urllib.request.Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def collect(user: str) -> dict[str, float]:
    bytes_by_lang: dict[str, int] = defaultdict(int)
    repos_by_lang: dict[str, int] = defaultdict(int)
    page = 1
    while True:
        repos = api(f"/users/{user}/repos?per_page=100&page={page}&type=owner")
        if not repos:
            break
        for repo in repos:
            if repo["fork"] or repo["archived"] or repo["name"].lower() == user.lower():
                continue
            for lang, size in api(f"/repos/{user}/{repo['name']}/languages").items():
                if lang in IGNORED:
                    continue
                bytes_by_lang[lang] += size
                repos_by_lang[lang] += 1
        page += 1
    return {
        lang: math.sqrt(bytes_by_lang[lang]) * math.sqrt(repos_by_lang[lang])
        for lang in bytes_by_lang
    }


def to_rows(scores: dict[str, float]) -> list[tuple[str, float, str]]:
    others = {lang: score for lang, score in scores.items() if lang != "Swift"}
    others_total = sum(others.values()) or 1
    pct = {lang: score / others_total * (100 - SWIFT_SHARE) for lang, score in others.items()}
    pct["Swift"] = SWIFT_SHARE
    ranked = sorted(pct.items(), key=lambda kv: kv[1], reverse=True)
    rows = [(lang, p, COLORS.get(lang, OTHER_COLOR)) for lang, p in ranked[:TOP_N]]
    rest = sum(p for _, p in ranked[TOP_N:])
    if rest >= 0.5:
        rows.append(("Other", rest, OTHER_COLOR))
    return rows


def render(rows: list[tuple[str, float, str]]) -> str:
    width, pad = 860, 36
    bar_w = width - pad * 2
    col_w = bar_w / 2
    legend_rows = math.ceil(len(rows) / 2)
    height = 128 + legend_rows * 34

    segments, x = [], float(pad)
    for i, (_, pct, color) in enumerate(rows):
        w = bar_w * pct / 100
        delay = 0.12 * i
        # 2px gap between segments, like the Storage bar in iOS Settings
        segments.append(
            f'<rect x="{x:.2f}" y="72" width="{max(w - 2, 1):.2f}" height="12" fill="{color}" '
            f'class="seg" style="animation-delay:{delay:.2f}s"/>'
        )
        x += w

    legend = []
    for i, (lang, pct, color) in enumerate(rows):
        cx = pad + (i % 2) * col_w
        cy = 122 + (i // 2) * 34
        legend.append(
            f'<g class="fade" style="animation-delay:{0.4 + 0.08 * i:.2f}s">'
            f'<circle cx="{cx + 5:.0f}" cy="{cy - 5}" r="5" fill="{color}"/>'
            f'<text x="{cx + 20:.0f}" y="{cy}" class="lang">{escape(lang)}</text>'
            f'<text x="{cx + col_w - 24:.0f}" y="{cy}" class="pct" text-anchor="end">{pct:.1f}%</text>'
            f"</g>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <clipPath id="bar"><rect x="{pad}" y="72" width="{bar_w}" height="12" rx="6"/></clipPath>
    <style>
      .card {{ fill: #1c1c1e; }}
      .track {{ fill: #2c2c2e; }}
      .title {{ font: 700 22px -apple-system, 'SF Pro Display', 'Helvetica Neue', 'Segoe UI', Arial, sans-serif; fill: #f5f5f7; letter-spacing: -0.4px; }}
      .note {{ font: 500 13px -apple-system, 'SF Pro Text', 'Helvetica Neue', 'Segoe UI', Arial, sans-serif; fill: #a1a1a6; }}
      .lang {{ font: 500 16px -apple-system, 'SF Pro Text', 'Helvetica Neue', 'Segoe UI', Arial, sans-serif; fill: #f5f5f7; }}
      .pct  {{ font: 500 15px -apple-system, 'SF Pro Text', 'Helvetica Neue', 'Segoe UI', Arial, sans-serif; fill: #a1a1a6; font-variant-numeric: tabular-nums; }}
      .seg  {{ transform-box: fill-box; transform-origin: left; animation: grow .7s ease-out both; }}
      .fade {{ animation: fade .5s ease-out both; }}
      @keyframes grow {{ from {{ transform: scaleX(0) }} to {{ transform: scaleX(1) }} }}
      @keyframes fade {{ from {{ opacity: 0 }} to {{ opacity: 1 }} }}
    </style>
  </defs>
  <rect class="card" width="{width}" height="{height}" rx="22"/>
  <text x="{pad}" y="46" class="title">Most used languages</text>
  <rect class="track" x="{pad}" y="72" width="{bar_w}" height="12" rx="6"/>
  <g clip-path="url(#bar)">{''.join(segments)}</g>
  {''.join(legend)}
</svg>
"""


def main() -> None:
    user, out = sys.argv[1], sys.argv[2]
    rows = to_rows(collect(user))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(rows))
    for lang, pct, _ in rows:
        print(f"{lang:<14}{pct:5.1f}%")


if __name__ == "__main__":
    main()
