#!/usr/bin/env python3
# Written by Claude (Anthropic), 2026-10-07, at doc's request. Not doc's code.
"""lineup: put several versions of a source tree on one web page.

Each version is a folder or a git ref. The page has a tab per version with a
file drawer and highlighted code, a side-by-side view of files that the
versions share, and optional Markdown pages and extra file shelves. A version
can be marked as derived from a base version; it then gets "changes from
base" diffs per file and, when both are refs in one git repo, its commits.

The output is one self-contained HTML file. It loads highlight.js from
cdnjs; everything else is inline. Python 3.8+, standard library only. If the
'markdown' package is installed, Markdown is rendered with it; otherwise a
small built-in renderer handles headings, lists, tables, code and links.

  python3 lineup.py out.html \\
      main=git:~/onir@main  v4=git:~/onir@claude-dial-shine  v1=./onir_dial_v1 \\
      --base main --derived v4 \\
      --label v1="Sketches only" --blurb v1="Built from the four sketches alone." \\
      --notes v1=./onir_dial_v1/NOTES.md \\
      --only 'src/**' --only library.properties \\
      --page Overview=README.md --shelf Sketches=./sketches \\
      --title "onir dial versions" --byline "Written by Claude, 2026-10-07."
"""
import argparse, difflib, fnmatch, html, json, os, re, subprocess, sys

MAX_BYTES = 400_000      # skip files bigger than this
SAME_KIND = {".cpp": ".cc", ".cxx": ".cc", ".c++": ".cc", ".hpp": ".h", ".hh": ".h"}
LANGS = {
    ".c": "c", ".h": "cpp", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".ino": "cpp",
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".json": "json",
    ".html": "xml", ".xml": "xml", ".svg": "xml", ".css": "css", ".md": "markdown", ".sh": "bash",
    ".rs": "rust", ".go": "go", ".java": "java", ".rb": "ruby", ".el": "lisp", ".lisp": "lisp",
    ".scm": "scheme", ".yml": "yaml", ".yaml": "yaml", ".toml": "ini", ".ini": "ini", ".tex": "latex",
    ".m": "matlab", ".jl": "julia", ".lua": "lua", ".mk": "makefile", ".cmake": "cmake",
}


# ---- reading sources -------------------------------------------------------

class Source:
    """A version: a folder on disk, or a ref in a git repo."""

    def __init__(self, spec):
        self.repo = self.ref = self.root = None
        if spec.startswith("git:"):
            where, _, ref = spec[4:].rpartition("@")
            if not where:
                sys.exit(f"lineup: '{spec}' needs a ref, like git:path@main")
            self.repo, self.ref = os.path.expanduser(where), ref
        else:
            self.root = os.path.expanduser(spec)
            if not os.path.isdir(self.root):
                sys.exit(f"lineup: no folder at {self.root}")

    def git(self, *args):
        r = subprocess.run(["git", "-C", self.repo, *args], capture_output=True)
        if r.returncode:
            sys.exit(f"lineup: git {' '.join(args)} failed in {self.repo}: {r.stderr.decode().strip()}")
        return r.stdout

    def paths(self):
        if self.repo:
            return self.git("ls-tree", "-r", "--name-only", "-z", self.ref).decode().split("\0")[:-1]
        out = []
        for base, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                out.append(os.path.relpath(os.path.join(base, f), self.root).replace(os.sep, "/"))
        return out

    def read(self, path):
        if self.repo:
            data = self.git("show", f"{self.ref}:{path}")
        else:
            full = os.path.join(self.root, path)
            if os.path.getsize(full) > MAX_BYTES:
                return None
            with open(full, "rb") as f:
                data = f.read()
        if len(data) > MAX_BYTES or b"\0" in data[:8000]:
            return None   # too big, or binary
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")


def wanted(path, only, skip):
    if any(fnmatch.fnmatch(path, g) for g in skip):
        return False
    return not only or any(fnmatch.fnmatch(path, g) for g in only)


def lang(path):
    return LANGS.get(os.path.splitext(path)[1].lower(), "plaintext")


def key(path):
    """Files with the same key are lined up side by side."""
    p = path[4:] if path.startswith("src/") else path
    stem, ext = os.path.splitext(p)
    return stem + SAME_KIND.get(ext.lower(), ext.lower())


def order(paths):
    return sorted(paths, key=lambda p: (p.count("/"), p.lower()))


def load(source, only, skip):
    files = []
    for p in order(source.paths()):
        if not wanted(p, only, skip):
            continue
        text = source.read(p)
        if text is not None:
            files.append({"path": p, "lang": lang(p), "text": text})
    return files


# ---- Markdown ---------------------------------------------------------------

def markdown_html(text):
    try:
        import markdown
        return markdown.markdown(text, extensions=["tables", "fenced_code"])
    except ImportError:
        return small_markdown(text)


def small_markdown(text):
    """Enough Markdown for notes and READMEs: headings, lists, tables, code, emphasis, links."""
    def inline(s):
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
        return s
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
        elif re.match(r"#{1,6} ", line):
            n = len(line) - len(line.lstrip("#"))
            out.append(f"<h{n}>{inline(line[n:].strip())}</h{n}>")
            i += 1
        elif line.startswith("|") and i + 1 < len(lines) and re.match(r"\|[\s:|-]+\|?\s*$", lines[i + 1]):
            row = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]
            t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in row(line)) + "</tr></thead><tbody>"]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row(lines[i])) + "</tr>")
                i += 1
            out.append("".join(t) + "</tbody></table>")
        elif re.match(r"\s*([-*]|\d+\.) ", line):
            tag = "ol" if re.match(r"\s*\d+\.", line) else "ul"
            items = []
            while i < len(lines) and (re.match(r"\s*([-*]|\d+\.) ", lines[i]) or (lines[i].startswith("  ") and items)):
                if re.match(r"\s*([-*]|\d+\.) ", lines[i]):
                    items.append(re.sub(r"^\s*([-*]|\d+\.) ", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        elif line.startswith("    "):
            j = i
            while j < len(lines) and (lines[j].startswith("    ") or not lines[j].strip()):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(l[4:] for l in lines[i:j]).rstrip()) + "</code></pre>")
            i = j
        elif not line.strip():
            i += 1
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not re.match(r"(#{1,6} |```|\||\s*([-*]|\d+\.) )", lines[j]):
                j += 1
            out.append("<p>" + inline(" ".join(lines[i:j])) + "</p>")
            i = max(j, i + 1)
    return "\n".join(out)


def read_text(path):
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        return f.read()


# ---- putting the page together ---------------------------------------------

def pairs(items, what):
    out = {}
    for item in items or []:
        name, eq, value = item.partition("=")
        if not eq:
            sys.exit(f"lineup: {what} '{item}' should look like name=value")
        out[name] = value
    return out


def unified(a, b, path):
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{path}", f"b/{path}", n=3))


def commits(base, src):
    if not (base.repo and src.repo and os.path.realpath(base.repo) == os.path.realpath(src.repo)):
        return None
    out = []
    for h in src.git("rev-list", "--reverse", f"{base.ref}..{src.ref}").decode().split():
        msg = src.git("log", "-1", "--format=%an%x00%ad%x00%B", "--date=short", h).decode()
        author, date, msg = msg.split("\0", 2)
        msg = re.sub(r"\n(Co-Authored-By|Signed-off-by|Claude-Session):.*", "", msg).strip()
        subject, _, body = msg.partition("\n")
        out.append({"hash": h[:7], "subject": subject, "body": body.strip(), "author": author, "date": date,
                    "diff": src.git("show", "--format=", h).decode("utf-8", "replace")})
    return out


def build(args):
    labels, blurbs, notes = pairs(args.label, "--label"), pairs(args.blurb, "--blurb"), pairs(args.notes, "--notes")
    specs = pairs(args.versions, "version")
    if not specs:
        sys.exit("lineup: give at least one version, like v1=./folder or main=git:./repo@main")
    for name in [args.base, *args.derived]:
        if name and name not in specs:
            sys.exit(f"lineup: '{name}' isn't one of the versions ({', '.join(specs)})")

    sources = {n: Source(s) for n, s in specs.items()}
    files = {n: load(src, args.only, args.skip) for n, src in sources.items()}

    versions = []
    for n, src in sources.items():
        v = {"id": n, "label": labels.get(n, n), "blurb": blurbs.get(n, ""), "files": files[n],
             "notes": markdown_html(read_text(notes[n])) if n in notes else ""}
        if n in args.derived and args.base:
            by_key = {key(f["path"]): f for f in files[args.base]}
            for f in v["files"]:
                old = by_key.get(key(f["path"]))
                if old is None:
                    f["changed"], f["diff"] = True, unified("", f["text"], f["path"])
                elif old["text"] != f["text"]:
                    f["changed"], f["diff"] = True, unified(old["text"], f["text"], f["path"])
            v["derived"] = True
            v["commits"] = commits(sources[args.base], src)
        versions.append(v)

    # side by side: every key that two or more versions share, unless they all match
    shared = {}
    for v in versions:
        for f in v["files"]:
            shared.setdefault(key(f["path"]), {})[v["id"]] = {"path": f["path"], "text": f["text"], "lang": f["lang"]}
    compare = []
    for k in order(shared):
        cells = shared[k]
        if len(cells) >= 2 and len({c["text"] for c in cells.values()}) > 1:
            compare.append({"name": k, "cells": cells})
    compare.sort(key=lambda c: -len(c["cells"]))   # most widely shared first (stable, so paths stay in order)

    pages = []
    for item in args.page or []:
        name, eq, path = item.partition("=")
        if not eq:
            sys.exit(f"lineup: --page '{item}' should look like Name=file.md")
        pages.append({"id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "page",
                      "label": name, "html": markdown_html(read_text(path))})
    shelves = []
    for item in args.shelf or []:
        name, eq, spec = item.partition("=")
        if not eq:
            sys.exit(f"lineup: --shelf '{item}' should look like Name=folder")
        shelves.append({"id": "shelf-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
                        "label": name, "files": load(Source(spec), [], args.skip)})

    return {"title": args.title, "byline": args.byline or "", "base": args.base,
            "versions": versions, "compare": compare, "pages": pages, "shelves": shelves}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Put several versions of a source tree on one web page.",
        epilog="A version is name=folder or name=git:repo@ref. Globs match paths relative to each version's root.")
    ap.add_argument("out", help="the HTML file to write")
    ap.add_argument("versions", nargs="+", metavar="name=source", help="a version: name=folder or name=git:repo@ref")
    ap.add_argument("--title", default="Source lineup", help="page title (keep it a short name)")
    ap.add_argument("--byline", help="a line under the title, e.g. who wrote what")
    ap.add_argument("--base", help="the version others are measured against")
    ap.add_argument("--derived", action="append", default=[], metavar="NAME",
                    help="a version built on the base: show its changes and commits (repeatable)")
    ap.add_argument("--label", action="append", metavar="NAME=TEXT", help="tab label for a version")
    ap.add_argument("--blurb", action="append", metavar="NAME=TEXT", help="one line under a version's heading")
    ap.add_argument("--notes", action="append", metavar="NAME=FILE.md", help="Markdown notes for a version")
    ap.add_argument("--only", action="append", default=[], metavar="GLOB", help="keep only matching paths (repeatable)")
    ap.add_argument("--skip", action="append", default=[], metavar="GLOB", help="leave out matching paths (repeatable)")
    ap.add_argument("--page", action="append", metavar="NAME=FILE.md",
                    help="a Markdown page; the first one opens the page, the rest come last")
    ap.add_argument("--shelf", action="append", metavar="NAME=FOLDER", help="an extra tab of files that isn't a version")
    ap.add_argument("--fragment", action="store_true",
                    help="write the page without <html>/<head>/<body>, for hosts that wrap it themselves")
    args = ap.parse_args(argv)

    data = build(args)
    blob = json.dumps(data).replace("</", "<\\/")
    page = TEMPLATE.replace("{{TITLE}}", html.escape(args.title)).replace("/*DATA*/null", blob)
    if args.fragment:
        page = page.replace("<!--BODY-->\n", "")
    else:
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + page.replace("<!--BODY-->", "</head>\n<body>") + "</body>\n</html>\n")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    n = sum(len(v["files"]) for v in data["versions"])
    print(f"lineup: wrote {args.out} ({len(page):,} bytes; {len(data['versions'])} versions, {n} files, "
          f"{len(data['compare'])} side-by-side pieces)")


TEMPLATE = r"""<title>{{TITLE}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=JetBrains+Mono:wght@400;600&family=Spectral:wght@500;700&display=swap">
<style>
/* Layout: a workbench. Tab rail across the top, then a file drawer beside a long code sheet. */
:root {
  --bg: #f3f4f6; --sheet: #ffffff; --fg: #1c2230; --muted: #5b6475; --line: #d9dde4;
  --brown: #6b3f22; --cobalt: #1f4fa8; --red: #b3202a;
  --add-bg: #e6edfb; --del-bg: #fbe8e9; --hunk: #6b3f22; --code-bg: #fafbfc;
  --kw: #1f4fa8; --str: #8a5a12; --com: #6f7787; --num: #9a2f7a; --ty: #11706b; --pre: #6b3f22;
  --display: "Spectral", Georgia, "Times New Roman", serif;
  --body: "Atkinson Hyperlegible", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #14161b; --sheet: #1c1f26; --fg: #e3e6ec; --muted: #9aa2b1; --line: #2e333d;
  --brown: #d19a6e; --cobalt: #86a9f2; --red: #f07b7f;
  --add-bg: #1d2a45; --del-bg: #3d1f23; --hunk: #d19a6e; --code-bg: #181b21;
  --kw: #86a9f2; --str: #e0b36a; --com: #7f8897; --num: #e08cc9; --ty: #5fc7bd; --pre: #d19a6e;
  color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #14161b; --sheet: #1c1f26; --fg: #e3e6ec; --muted: #9aa2b1; --line: #2e333d;
  --brown: #d19a6e; --cobalt: #86a9f2; --red: #f07b7f;
  --add-bg: #1d2a45; --del-bg: #3d1f23; --hunk: #d19a6e; --code-bg: #181b21;
  --kw: #86a9f2; --str: #e0b36a; --com: #7f8897; --num: #e08cc9; --ty: #5fc7bd; --pre: #d19a6e;
  color-scheme: dark }

* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { -webkit-text-size-adjust: 100%; }
body { background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 15px; line-height: 1.5; margin: 0; padding: 0 16px; }
.wrap { max-width: 92rem; margin: 0 auto; padding-block: 18px 48px; display: grid; gap: 14px; }

header.top { display: grid; gap: 6px; }
h1 { font-family: var(--display); font-weight: 700; color: var(--brown); font-size: 1.9rem; line-height: 1.15; margin: 0; text-wrap: balance; }
.byline { margin: 0; color: var(--fg); font-size: 0.95rem; border-left: 3px solid var(--brown); padding: 2px 0 2px 10px; max-width: 70ch; }

nav.tabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 2px solid var(--brown); position: sticky; top: env(safe-area-inset-top, 0px); background: var(--bg); z-index: 5; padding-top: 6px; }
nav.tabs button { font: inherit; font-size: 0.92rem; background: none; border: 1px solid transparent; border-bottom: none; color: var(--muted); padding: 6px 12px; border-radius: 6px 6px 0 0; cursor: pointer; }
nav.tabs button:hover { color: var(--fg); }
nav.tabs button[aria-selected="true"] { background: var(--brown); color: var(--bg); font-weight: 700; }
nav.tabs button .tag { font-family: var(--mono); font-size: 0.8em; margin-right: 4px; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--cobalt); outline-offset: 2px; }

.panel { display: grid; gap: 14px; min-width: 0; }
.prose { background: var(--sheet); border: 1px solid var(--line); border-radius: 8px; padding: 18px 22px; min-width: 0; }
.prose > * { max-width: 72ch; }
.prose h1, .prose h2, .prose h3 { font-family: var(--display); color: var(--brown); line-height: 1.2; text-wrap: balance; }
.prose h1 { font-size: 1.5rem; } .prose h2 { font-size: 1.25rem; margin-top: 1.4em; } .prose h3 { font-size: 1.08rem; }
.prose table { border-collapse: collapse; font-size: 0.9rem; font-variant-numeric: tabular-nums; }
.prose .tablebox { overflow-x: auto; max-width: 100%; }
.prose th, .prose td { border-bottom: 1px solid var(--line); padding: 5px 10px; text-align: left; vertical-align: top; }
.prose th { color: var(--brown); font-weight: 700; }
.prose code { font-family: var(--mono); font-size: 0.86em; background: var(--code-bg); border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; }
.prose pre { background: var(--code-bg); border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; overflow-x: auto; max-width: 100%; }
.prose pre code { border: none; padding: 0; background: none; }
.prose a { color: var(--cobalt); }

.vhead { display: grid; gap: 4px; }
.vhead h2 { font-family: var(--display); color: var(--brown); font-size: 1.45rem; margin: 0; }
.vhead p { margin: 0; color: var(--muted); max-width: 72ch; }
.subtabs, .comparebar { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font: inherit; font-size: 0.85rem; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--sheet); color: var(--fg); cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--cobalt); color: var(--cobalt); font-weight: 700; }
.comparebar .chip { font-family: var(--mono); font-size: 0.8rem; }

.bench { display: grid; grid-template-columns: minmax(12rem, 18rem) minmax(0, 1fr); gap: 14px; align-items: start; }
.drawer { background: var(--sheet); border: 1px solid var(--line); border-radius: 8px; padding: 6px; display: grid; gap: 2px; position: sticky; top: calc(env(safe-area-inset-top, 0px) + 52px); max-height: calc(100vh - 80px); overflow-y: auto; }
.drawer .group { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--brown); padding: 8px 8px 2px; font-weight: 700; }
.drawer button { font-family: var(--mono); font-size: 0.8rem; text-align: left; background: none; border: none; color: var(--fg); padding: 4px 8px; border-radius: 4px; cursor: pointer; display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.drawer button > span:first-child { overflow-wrap: anywhere; }
.drawer button:hover { background: var(--code-bg); }
.drawer button[aria-current="true"] { background: var(--add-bg); color: var(--cobalt); font-weight: 600; }
.drawer .lines { color: var(--muted); font-size: 0.72rem; font-variant-numeric: tabular-nums; }
.dot { color: var(--red); font-weight: 700; }

.sheet { background: var(--sheet); border: 1px solid var(--line); border-radius: 8px; min-width: 0; display: grid; }
.sheethead { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--line); }
.path { font-family: var(--mono); font-size: 0.85rem; color: var(--brown); font-weight: 600; overflow-wrap: anywhere; }
.meta { color: var(--muted); font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.tools { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }

.code { overflow-x: auto; background: var(--code-bg); border-radius: 0 0 8px 8px; }
.code table { border-collapse: collapse; font-family: var(--mono); font-size: 0.8rem; line-height: 1.55; width: 100%; }
.code td { padding: 0 12px; white-space: pre; vertical-align: top; }
.code td.n { color: var(--muted); text-align: right; user-select: none; width: 1%; padding-right: 10px; border-right: 1px solid var(--line); font-variant-numeric: tabular-nums; }
.code tr.add td.c { background: var(--add-bg); }
.code tr.del td.c { background: var(--del-bg); }
.code tr.add td.n::after { content: " +"; color: var(--cobalt); }
.code tr.del td.n::after { content: " \2212"; color: var(--red); }
.code tr.hunk td { color: var(--hunk); background: var(--sheet); font-style: italic; padding-top: 4px; padding-bottom: 4px; }
.code tr.metaline td { color: var(--brown); background: var(--sheet); font-weight: 600; padding-top: 8px; }

.hljs-keyword, .hljs-built_in, .hljs-literal { color: var(--kw); }
.hljs-string, .hljs-char, .hljs-regexp { color: var(--str); }
.hljs-comment, .hljs-quote { color: var(--com); font-style: italic; }
.hljs-number { color: var(--num); }
.hljs-type, .hljs-title, .hljs-section { color: var(--ty); }
.hljs-meta, .hljs-meta .hljs-keyword, .hljs-meta .hljs-string { color: var(--pre); }

.commits { display: grid; gap: 12px; }
.commit { background: var(--sheet); border: 1px solid var(--line); border-radius: 8px; min-width: 0; }
.commit summary { cursor: pointer; padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; list-style: none; }
.commit summary::-webkit-details-marker { display: none; }
.commit summary .h { font-family: var(--mono); font-size: 0.8rem; color: var(--muted); }
.commit summary .s { font-weight: 700; }
.commit summary .k { margin-left: auto; color: var(--cobalt); font-size: 0.8rem; white-space: nowrap; }
.commit[open] summary .k::before { content: "hide "; }
.commit:not([open]) summary .k::before { content: "show "; }
.commit .body { padding: 0 14px 10px; white-space: pre-wrap; max-width: 78ch; font-size: 0.92rem; }

.cols { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(30rem, 1fr); gap: 10px; overflow-x: auto; padding-bottom: 6px; }
.col { min-width: 0; align-content: start; }
.col .sheethead { display: grid; gap: 2px; }
.col .who { font-family: var(--display); color: var(--brown); font-weight: 700; }
.col .code { max-height: 75vh; overflow: auto; }
.empty { color: var(--muted); padding: 14px; font-style: italic; }
footer { color: var(--muted); font-size: 0.8rem; }

@media (max-width: 760px) {
  h1 { font-size: 1.5rem; }
  .bench { grid-template-columns: minmax(0, 1fr); }
  .drawer { position: static; max-height: none; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); }
  .drawer .group { grid-column: 1 / -1; }
  .cols { grid-auto-columns: minmax(85vw, 1fr); }
  .prose { padding: 14px; }
}
</style>
<!--BODY-->
<div class="wrap">
  <header class="top">
    <h1 id="title"></h1>
    <p class="byline" id="byline" hidden></p>
  </header>
  <nav class="tabs" id="tabs" aria-label="Sections"></nav>
  <main id="main" class="panel"></main>
  <footer>Made with lineup.</footer>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>
const D = /*DATA*/null;

const $ = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) el.append(k);
  return el;
};
const store = {
  get(k) { try { return localStorage.getItem("lineup:" + D.title + ":" + k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem("lineup:" + D.title + ":" + k, v); } catch (e) {} },
};
const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const lineCount = t => t.replace(/\n$/, "").split("\n").length;
const byId = Object.fromEntries(D.versions.map(v => [v.id, v]));

// ---- code ------------------------------------------------------------------
function highlighted(text, lang) {
  if (window.hljs && lang && lang !== "plaintext" && hljs.getLanguage(lang)) {
    try { return hljs.highlight(text, { language: lang, ignoreIllegals: true }).value; } catch (e) {}
  }
  return esc(text);
}
// split highlighted HTML into lines, carrying open spans across line breaks
function splitLines(htmlText) {
  const out = [], open = [];
  for (const raw of htmlText.split("\n")) {
    let line = open.join("") + raw;
    const re = /<span[^>]*>|<\/span>/g;
    let m;
    while ((m = re.exec(raw))) { if (m[0] === "</span>") open.pop(); else open.push(m[0]); }
    out.push(line + "</span>".repeat(open.length));
  }
  return out;
}
function codeTable(text, lang) {
  const tb = $("tbody");
  splitLines(highlighted(text.replace(/\n$/, ""), lang)).forEach((l, i) =>
    tb.append($("tr", {}, $("td", { class: "n" }, String(i + 1)), $("td", { class: "c", html: l || " " }))));
  return $("div", { class: "code" }, $("table", {}, tb));
}
function diffTable(diff, lang) {
  const tb = $("tbody");
  let oldN = 0, newN = 0, fileLang = lang;
  for (const l of diff.replace(/\n$/, "").split("\n")) {
    if (/^(index |--- |\+\+\+ |new file|deleted file|similarity|rename |old mode|new mode)/.test(l)) continue;
    if (l.startsWith("diff --git")) {
      const p = l.replace(/^diff --git a\/(\S+).*/, "$1");
      fileLang = guess(p) || lang;
      tb.append($("tr", { class: "metaline" }, $("td", { class: "n" }, ""), $("td", { class: "c" }, p)));
      continue;
    }
    if (l.startsWith("@@")) {
      const m = l.match(/-(\d+)(?:,\d+)? \+(\d+)/);
      if (m) { oldN = +m[1]; newN = +m[2]; }
      tb.append($("tr", { class: "hunk" }, $("td", { class: "n" }, "⋯"), $("td", { class: "c" }, l.replace(/^@@[^@]*@@ ?/, "") || "…")));
      continue;
    }
    if (l.startsWith("\\")) continue;  // "\ No newline at end of file"
    const t = l[0], body = l.slice(1);
    const cls = t === "+" ? "add" : t === "-" ? "del" : "";
    const num = t === "-" ? oldN++ : t === "+" ? newN++ : (oldN++, newN++);
    tb.append($("tr", { class: cls }, $("td", { class: "n" }, String(num)), $("td", { class: "c", html: highlighted(body, fileLang) || " " })));
  }
  return $("div", { class: "code" }, $("table", {}, tb));
}
const EXT = { c: "c", h: "cpp", cc: "cpp", cpp: "cpp", ino: "cpp", py: "python", js: "javascript", ts: "typescript", md: "markdown", sh: "bash", json: "json", html: "xml", css: "css" };
function guess(path) { const m = path.match(/\.([^./]+)$/); return m && EXT[m[1].toLowerCase()]; }

function sheet(file, startMode) {
  const box = $("section", { class: "sheet" });
  let mode = startMode;
  const render = () => {
    const tools = $("div", { class: "tools" });
    if (file.diff) {
      for (const [m, label] of [["diff", "Changes from " + D.base], ["file", "Whole file"]]) {
        tools.append($("button", { class: "chip", "aria-pressed": String(mode === m), onclick: () => { mode = m; render(); } }, label));
      }
    }
    box.replaceChildren(
      $("div", { class: "sheethead" },
        $("div", {}, $("div", { class: "path" }, file.path),
          $("div", { class: "meta" }, `${lineCount(file.text)} lines${file.changed ? " · changed from " + D.base : ""}`)),
        tools),
      mode === "diff" && file.diff ? diffTable(file.diff, file.lang) : codeTable(file.text, file.lang));
  };
  render();
  return box;
}

function workbench(key, groups) {
  groups = groups.filter(g => g.files.length);
  const all = groups.flatMap(g => g.files);
  if (!all.length) return $("p", { class: "empty" }, "No files here.");
  let current = store.get("file:" + key);
  if (!all.some(f => f.path === current)) current = all[0].path;
  const drawer = $("nav", { class: "drawer", "aria-label": "Files" });
  const holder = $("div", { style: "min-width:0" });
  const draw = () => {
    drawer.replaceChildren();
    for (const g of groups) {
      if (g.label) drawer.append($("div", { class: "group" }, g.label));
      for (const f of g.files) {
        drawer.append($("button", {
          "aria-current": String(f.path === current), title: f.path,
          onclick: () => { current = f.path; store.set("file:" + key, current); draw(); },
        }, $("span", {}, f.changed ? $("span", { class: "dot", title: "changed" }, "● ") : null, f.path),
           $("span", { class: "lines" }, String(lineCount(f.text)))));
      }
    }
    const f = all.find(x => x.path === current);
    holder.replaceChildren(sheet(f, f.diff ? "diff" : "file"));
  };
  draw();
  return $("div", { class: "bench" }, drawer, holder);
}

function prose(htmlText) {
  const p = $("article", { class: "prose", html: htmlText });
  p.querySelectorAll("table").forEach(t => { const b = $("div", { class: "tablebox" }); t.replaceWith(b); b.append(t); });
  p.querySelectorAll("a[href]").forEach(a => { a.target = "_blank"; a.rel = "noopener"; });
  return p;
}

// ---- views ---------------------------------------------------------------------
function versionView(v) {
  const head = $("div", { class: "vhead" },
    $("h2", {}, v.label === v.id ? v.id : `${v.id} · ${v.label}`), v.blurb ? $("p", {}, v.blurb) : null);
  const views = [["files", "Files"]];
  if (v.commits && v.commits.length) views.push(["commits", `Commits (${v.commits.length})`]);
  if (v.notes) views.push(["notes", "Notes"]);
  let view = store.get("view:" + v.id);
  if (!views.some(x => x[0] === view)) view = "files";
  const bar = $("div", { class: "subtabs" });
  const body = $("div", { class: "panel" });
  const render = () => {
    bar.replaceChildren(...(views.length > 1 ? views : []).map(([k, label]) =>
      $("button", { class: "chip", "aria-pressed": String(view === k), onclick: () => { view = k; store.set("view:" + v.id, k); render(); } }, label)));
    body.replaceChildren();
    if (view === "notes") body.append(prose(v.notes));
    if (view === "files") {
      const groups = v.derived
        ? [{ label: "Changed from " + D.base, files: v.files.filter(f => f.changed) }, { label: "Same as " + D.base, files: v.files.filter(f => !f.changed) }]
        : [{ label: "", files: v.files }];
      body.append(workbench(v.id, groups));
    }
    if (view === "commits") {
      body.append($("div", { class: "commits" }, v.commits.map((c, i) => {
        const d = $("details", { class: "commit" },
          $("summary", {}, $("span", { class: "h" }, `${i + 1} · ${c.hash} · ${c.author}, ${c.date}`), $("span", { class: "s" }, c.subject), $("span", { class: "k" }, "diff")),
          c.body ? $("div", { class: "body" }, c.body) : null);
        d.addEventListener("toggle", () => { if (d.open && !d.querySelector(".code")) d.append(diffTable(c.diff)); });
        return d;
      })));
    }
  };
  render();
  return [head, bar, body];
}

function compareView() {
  if (!D.compare.length) return [$("p", { class: "empty" }, "The versions don't share any files that differ.")];
  let pick = store.get("compare");
  if (!D.compare.some(c => c.name === pick)) pick = D.compare[0].name;
  const bar = $("div", { class: "comparebar" });
  const cols = $("div", { class: "cols" });
  const render = () => {
    bar.replaceChildren(...D.compare.map(c => $("button", { class: "chip", "aria-pressed": String(c.name === pick), onclick: () => { pick = c.name; store.set("compare", pick); render(); } }, c.name)));
    const piece = D.compare.find(c => c.name === pick);
    cols.replaceChildren(...D.versions.map(v => {
      const cell = piece.cells[v.id];
      return $("section", { class: "sheet col" },
        $("div", { class: "sheethead" },
          $("div", { class: "who" }, v.label === v.id ? v.id : `${v.id} · ${v.label}`),
          $("div", { class: "path" }, cell ? cell.path : "—"),
          $("div", { class: "meta" }, cell ? `${lineCount(cell.text)} lines` : "")),
        cell ? codeTable(cell.text, cell.lang) : $("div", { class: "empty" }, "Not in this version."));
    }));
  };
  render();
  return [$("div", { class: "vhead" }, $("h2", {}, "Side by side"),
    $("p", {}, "Files that two or more versions share, where they differ. Files with the same name and kind line up even when the extension differs (.cc and .cpp). Scroll sideways for more columns.")), bar, cols];
}

// ---- tabs ------------------------------------------------------------------------
document.getElementById("title").textContent = D.title;
if (D.byline) { const b = document.getElementById("byline"); b.textContent = D.byline; b.hidden = false; }
const sections = [
  ...D.pages.slice(0, 1).map(p => ({ id: p.id, label: p.label, build: () => [prose(p.html)] })),
  ...D.versions.map(v => ({ id: v.id, label: v.label === v.id ? "" : v.label, tag: v.id, build: () => versionView(v) })),
  ...(D.versions.length > 1 ? [{ id: "side-by-side", label: "Side by side", build: compareView }] : []),
  ...D.shelves.map(s => ({ id: s.id, label: s.label, build: () => [$("div", { class: "vhead" }, $("h2", {}, s.label)), workbench(s.id, [{ label: "", files: s.files }])] })),
  ...D.pages.slice(1).map(p => ({ id: p.id, label: p.label, build: () => [prose(p.html)] })),
];
const tabs = document.getElementById("tabs"), main = document.getElementById("main");
function show(id) {
  const s = sections.find(x => x.id === id) || sections[0];
  [...tabs.children].forEach(b => b.setAttribute("aria-selected", String(b.dataset.id === s.id)));
  main.replaceChildren(...s.build());
  store.set("tab", s.id);
  try { if (location.hash.slice(1) !== s.id) history.replaceState(null, "", "#" + s.id); } catch (e) {}
}
for (const s of sections) tabs.append($("button", { "data-id": s.id, role: "tab", onclick: () => show(s.id) }, s.tag ? $("span", { class: "tag" }, s.tag) : null, s.label));
show(location.hash.slice(1) || store.get("tab") || sections[0].id);
window.addEventListener("hashchange", () => show(location.hash.slice(1)));
</script>
"""

if __name__ == "__main__":
    main()
