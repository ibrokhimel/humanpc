#!/usr/bin/env python3
"""Build the humanpc documentation website.

Reads the Markdown docs (README + docs/*.md) and bundles them into a single,
self-contained static site at ``docs/site/index.html``. The site renders the
Markdown client-side (see ``docs/site/markdown.js``), so there are **no runtime
dependencies** — just open ``index.html`` in a browser.

Single source of truth: edit the ``.md`` files, then re-run::

    python scripts/build_docs.py

Stdlib only, matching the project's zero-dependency ethos.
"""

from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs" / "site"

# (page id, sidebar title, path relative to repo root, source basename for links)
PAGES = [
    ("introduction", "Introduction", "README.md", "README.md"),
    ("flow-language", "Flow Language", "docs/FLOW_LANGUAGE.md", "FLOW_LANGUAGE.md"),
    ("python-api", "Python API", "docs/PYTHON_API.md", "PYTHON_API.md"),
    ("changelog", "Changelog", "CHANGELOG.md", "CHANGELOG.md"),
]

SHELL = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>humanpc — documentation</title>
<meta name="description" content="Human-like PC automation framework for Windows — full documentation.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#129302;</text></svg>">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<div id="overlay"></div>
<header class="topbar">
  <button id="menu" class="icon-btn" aria-label="Toggle navigation">&#9776;</button>
  <a class="brand" href="#introduction">
    <span class="logo">&#129302;</span>
    <span class="brand-name">humanpc</span>
    <span class="brand-sub">docs</span>
  </a>
  <div class="search">
    <input id="search" type="search" placeholder="Search the docs…" autocomplete="off" spellcheck="false">
    <kbd>/</kbd>
  </div>
  <div class="spacer"></div>
  <a class="icon-btn ghost" href="https://github.com/" title="Source" aria-label="Source">&lt;/&gt;</a>
  <button id="theme" class="icon-btn" aria-label="Toggle light/dark">&#9789;</button>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar"><nav id="nav" aria-label="Docs navigation"></nav></aside>
  <main id="content" class="content" tabindex="-1"></main>
</div>
{pages}
<script src="markdown.js"></script>
<script src="app.js"></script>
</body>
</html>
"""


def main() -> int:
    SITE.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    included: list[str] = []
    for pid, title, rel, basename in PAGES:
        src = ROOT / rel
        if not src.exists():
            print(f"  skip  {rel} (not found)")
            continue
        md = src.read_text(encoding="utf-8")
        blocks.append(
            f'<script type="text/markdown" '
            f'data-id="{html.escape(pid, quote=True)}" '
            f'data-title="{html.escape(title, quote=True)}" '
            f'data-file="{html.escape(basename, quote=True)}">\n{md}\n</script>'
        )
        included.append(title)

    out = SITE / "index.html"
    out.write_text(SHELL.format(pages="\n".join(blocks)), encoding="utf-8")
    print(f"  built {out.relative_to(ROOT)}  ({len(included)} pages: {', '.join(included)})")
    print(f"  open  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
