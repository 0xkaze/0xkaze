#!/usr/bin/env python3
"""Renders dark_mode.svg and light_mode.svg, the neofetch-style card shown in README.md.

    python card.py                      # re-render with the cached stats
    ACCESS_TOKEN=ghp_... python card.py # refresh GitHub stats first (what the Action does)

No dependencies beyond the Python standard library.
"""
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request
from html import escape

ROOT = pathlib.Path(__file__).resolve().parent

# ─────────────────────────────── profile ───────────────────────────────
USER = "0xkaze"
TITLE = "guilherme@seguro"
BIRTHDAY = None               # "YYYY-MM-DD" turns Uptime into "24 years, 1 month, 10 days"
AGE = 24                      # shown while BIRTHDAY is None
TZ = dt.timezone(dt.timedelta(hours=-3))   # America/Sao_Paulo
EXCLUDE = {f"{USER}/{USER}"}  # this repo's daily auto-commits stay out of the totals

SECTIONS = [
    (None, [
        ("OS", "macOS"),
        ("Uptime", "{uptime}"),
        ("Host", "Curitiba, Brazil"),
        ("Kernel", "Full Stack Developer"),
        ("Focus", "AI & Web3 · Cloud Architecture"),
        ("Hobbies", "Cars, Football"),
    ]),
    ("Languages", [
        ("Programming", "Python, TypeScript, JavaScript, Solidity, Java, C#"),
        ("Computer", "HTML, CSS, SQL, JSON, YAML"),
        ("Real", "Portuguese, English, Japanese, Italian"),
    ]),
    ("Stack", [
        ("Frontend", "React, Next.js, Tailwind"),
        ("Backend", "Node.js, FastAPI, MySQL, Neo4j"),
        ("AI & Web3", "OpenAI, Ethereum, Web3.js"),
        ("Cloud", "GCP, Docker, Kubernetes"),
    ]),
    ("Education", [
        ("UFPR", "B.Sc. Information Management"),
        ("Descomplica", "B.Sc. Computer Engineering"),
    ]),
    ("Contact", [
        ("Email", "guilherme.seguro00@gmail.com"),
        ("WhatsApp", "+55 41 98415-2304"),
    ]),
    ("GitHub Stats", "STATS"),
]

# ─────────────────────────────── layout ────────────────────────────────
FONT = 16
CW = FONT * 0.6               # monospace advance; every run is pinned to its column
LH = 20
PAD_X, PAD_Y = 22, 24
GAP = 2                       # columns between portrait and panel
PANEL = 68                    # panel width in columns
ART_COLS = 46                 # portrait width in columns (both themes share the geometry)
MONO = "ConsolasFallback, Consolas, ui-monospace, SFMono-Regular, 'SF Mono', Menlo, 'DejaVu Sans Mono', monospace"

THEMES = {
    "dark": dict(bg="#161b22", fg="#c9d1d9", art="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 cc="#616e7f", add="#3fb950", dele="#f85149"),
    "light": dict(bg="#f6f8fa", fg="#24292f", art="#24292f", key="#953800", value="#0a3069",
                  cc="#c2cfde", add="#1a7f37", dele="#cf222e"),
}

# ─────────────────────────────── stats ─────────────────────────────────
# ACCESS_TOKEN (a personal token) also counts private repos; without it the Action's
# built-in GITHUB_TOKEN still covers everything public
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
STATS_FILE = ROOT / "cache" / "stats.json"
LOC_FILE = ROOT / "cache" / "loc.json"


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch_stats():
    u = gql("""query($login:String!){ user(login:$login){ id followers{ totalCount }
        owned: repositories(ownerAffiliations: OWNER){ totalCount }
        all: repositories(ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]){ totalCount } } }""",
            login=USER)["user"]

    repos, cursor = [], None
    while True:
        page = gql("""query($login:String!,$cursor:String){ user(login:$login){
            repositories(first:100, after:$cursor, ownerAffiliations:[OWNER, COLLABORATOR, ORGANIZATION_MEMBER]){
              nodes{ nameWithOwner stargazerCount owner{ login }
                     defaultBranchRef{ target{ ... on Commit { oid } } } }
              pageInfo{ hasNextPage endCursor } } } }""", login=USER, cursor=cursor)
        conn = page["user"]["repositories"]
        repos += conn["nodes"]
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]

    cache = json.loads(LOC_FILE.read_text()) if LOC_FILE.exists() else {}
    fresh = {}
    for r in repos:
        name = r["nameWithOwner"]
        head = (r.get("defaultBranchRef") or {}).get("target") or {}
        if name in EXCLUDE or not head.get("oid"):
            continue
        if cache.get(name, {}).get("oid") == head["oid"]:
            fresh[name] = cache[name]
            continue
        owner, repo = name.split("/")
        commits = add = dele = 0
        cursor = None
        while True:
            h = gql("""query($owner:String!,$name:String!,$id:ID!,$cursor:String){ repository(owner:$owner,name:$name){
                defaultBranchRef{ target{ ... on Commit { history(first:100, after:$cursor, author:{id:$id}){
                  nodes{ additions deletions } pageInfo{ hasNextPage endCursor } } } } } } }""",
                    owner=owner, name=repo, id=u["id"], cursor=cursor)
            hist = h["repository"]["defaultBranchRef"]["target"]["history"]
            for c in hist["nodes"]:
                commits += 1
                add += c["additions"]
                dele += c["deletions"]
            if not hist["pageInfo"]["hasNextPage"]:
                break
            cursor = hist["pageInfo"]["endCursor"]
        fresh[name] = {"oid": head["oid"], "commits": commits, "add": add, "del": dele}

    LOC_FILE.parent.mkdir(exist_ok=True)
    LOC_FILE.write_text(json.dumps(fresh, indent=1, sort_keys=True) + "\n")
    add = sum(v["add"] for v in fresh.values())
    dele = sum(v["del"] for v in fresh.values())
    return {
        "repos": u["owned"]["totalCount"],
        "contributed": u["all"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos if r["owner"]["login"].lower() == USER.lower()),
        "followers": u["followers"]["totalCount"],
        "commits": sum(v["commits"] for v in fresh.values()),
        "loc_add": add,
        "loc_del": dele,
    }


def load_stats():
    cached = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    if not TOKEN:
        return cached
    try:
        stats = fetch_stats()
    except Exception as e:  # keep the card rendering (uptime still moves) and flag it in the run
        print(f"::warning::GitHub stats not refreshed, using cache: {e}", file=sys.stderr)
        return cached
    STATS_FILE.parent.mkdir(exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=1) + "\n")
    return stats


def uptime(today):
    if not BIRTHDAY:
        return f"{AGE} years"
    b = dt.date.fromisoformat(BIRTHDAY)
    y, m, d = today.year - b.year, today.month - b.month, today.day - b.day
    if d < 0:
        m -= 1
        d += (today.replace(day=1) - dt.timedelta(days=1)).day
    if m < 0:
        y, m = y - 1, m + 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{plural(y, 'year')}, {plural(m, 'month')}, {plural(d, 'day')}"


# ─────────────────────────────── rows ──────────────────────────────────
# a row is a list of (column, text, css class); every run is pinned to its column

def num(v):
    return "—" if v is None else f"{v:,}"


def leader(key, value_len, width, start=0, bullet=True):
    """'. Key: ....... ' sized so a value of value_len ends exactly at start+width."""
    pre = ". " if bullet else ""
    head = f"{pre}{key}:"
    dots = width - len(head) - value_len - 2
    runs = [(start, pre, "cc"), (start + len(pre), f"{key}:", "key"),
            (start + len(head) + 1, "." * max(dots, 1), "cc")]
    return runs, start + width - value_len


def kv(key, value, width=PANEL, start=0, bullet=True):
    runs, vcol = leader(key, len(value), width, start, bullet)
    return runs + [(vcol, value, "value")]


def rule(label):
    text = f"- {label} "
    return [(0, text, "fg"), (len(text), "—" * (PANEL - len(text)), "cc")]


def stats_rows(s):
    left = 40                 # left half width; " | " then the right half
    right = PANEL - left - 3
    repos = f"{num(s.get('repos'))} {{Contributed: {num(s.get('contributed'))}}}"
    r1 = kv("Repos", repos, left) + [(left, " | ", "cc")] + \
        kv("Stars", num(s.get("stars")), right, left + 3, bullet=False)
    r2 = kv("Commits", num(s.get("commits")), left) + [(left, " | ", "cc")] + \
        kv("Followers", num(s.get("followers")), right, left + 3, bullet=False)
    total = None if s.get("loc_add") is None else s["loc_add"] - s["loc_del"]
    parts = [(num(total), "value"), (" ( ", "cc"), (f"{num(s.get('loc_add'))}++", "add"),
             (", ", "cc"), (f"{num(s.get('loc_del'))}--", "dele"), (" )", "cc")]
    vlen = sum(len(t) for t, _ in parts)
    runs, col = leader("Lines of Code on GitHub", vlen, PANEL)
    for t, c in parts:
        runs.append((col, t, c))
        col += len(t)
    return [r1, r2, runs]


def panel_rows(stats, today):
    rows = [[(0, TITLE, "fg"), (len(TITLE), " " + "—" * (PANEL - len(TITLE) - 1), "cc")]]
    for label, items in SECTIONS:
        if label:
            rows += [[], rule(label)]
        if items == "STATS":
            rows += stats_rows(stats)
            continue
        for k, v in items:
            rows.append(kv(k, v.format(uptime=uptime(today))))
    return rows


# ─────────────────────────────── svg ───────────────────────────────────

def render(theme, rows):
    T = THEMES[theme]
    art = (ROOT / "ascii" / f"{theme}.txt").read_text().rstrip("\n").split("\n")
    art = art[:len(rows)]     # the panel sets the card height; extra shirt rows are cropped
    art_cols = max(ART_COLS, *map(len, art))
    n = len(rows)
    px = PAD_X + (art_cols + GAP) * CW
    W = PAD_X * 2 + (art_cols + GAP + PANEL) * CW
    H = PAD_Y * 2 + n * LH
    base = lambda r: PAD_Y + (r + 1) * LH - 5

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
         f'font-family="{MONO}" font-size="{FONT}px" role="img" aria-label="{escape(TITLE)} — {USER}">',
         "<style>@font-face{font-family:ConsolasFallback;src:local('Consolas');size-adjust:109%}"
         f"text,tspan{{white-space:pre}}.fg{{fill:{T['fg']}}}.art{{fill:{T['art']}}}.key{{fill:{T['key']}}}"
         f".value{{fill:{T['value']}}}.cc{{fill:{T['cc']}}}.add{{fill:{T['add']}}}.dele{{fill:{T['dele']}}}</style>",
         f'<rect width="{W:.0f}" height="{H:.0f}" rx="15" fill="{T["bg"]}"/>']

    def run(x, text, cls):
        return (f'<tspan x="{x:.1f}" class="{cls}" textLength="{len(text) * CW:.1f}" '
                f'lengthAdjust="spacingAndGlyphs">{escape(text)}</tspan>')

    for r, line in enumerate(art):
        spans, c = [], 0
        while c < len(line):
            if line[c] == " ":
                c += 1
                continue
            s = c
            while c < len(line) and line[c] != " ":
                c += 1
            spans.append(run(PAD_X + s * CW, line[s:c], "art"))
        if spans:
            o.append(f'<text y="{base(r):.0f}">{"".join(spans)}</text>')

    for r, segs in enumerate(rows):
        if segs:
            o.append(f'<text y="{base(r):.0f}">' +
                     "".join(run(px + col * CW, t, cls) for col, t, cls in segs if t) + "</text>")
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main():
    stats = load_stats()
    rows = panel_rows(stats, dt.datetime.now(TZ).date())
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, rows))
    print("rendered", ", ".join(f"{t}_mode.svg" for t in THEMES), "|", json.dumps(stats))


if __name__ == "__main__":
    main()
