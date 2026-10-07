**Written by Claude (Anthropic), 2026-10-07, at doc's request. The code and this README are Claude's.**

# lineup

lineup puts several versions of a source tree on one web page. Use it to compare rewrites of a library, or a branch against the code it came from.

    python3 lineup.py page.html  main=git:~/onir@main  mine=git:~/onir@my-branch  theirs=./their-copy \
        --base main --derived mine

The result is a single HTML file. It has these parts:

- **A tab for each version.** Each tab has a file drawer and syntax-highlighted code with line numbers.
- **Changes from the base.** A version marked `--derived` shows its changed files first. Each changed file can switch between its diff and the whole file. When the version and the base are both refs in one git repo, the tab also lists the version's commits, with messages and diffs.
- **Side by side.** Every file that two or more versions share, where the copies differ, shown in columns. Files line up by name and kind, so `dial.cc` and `dial.cpp` sit together, and so do `src/x.h` and `x.h`.
- **Pages and shelves.** `--page` adds Markdown tabs, such as an overview or notes. `--shelf` adds a tab of files that isn't a version, such as examples or test scripts.

The page works offline except for highlight.js, which it loads from cdnjs, and three web fonts from Google Fonts. Without them it still works, with plain code and system fonts. The page makes no other network requests. It remembers your last tab, file and view in the browser's local storage, and nothing else.

## Versions

A version is `name=source`, where the source is either

- a folder, `v1=./onir_dial_v1`, or
- a git ref, `main=git:~/onir@main`. The ref can be anything `git show` accepts: a branch, tag or commit. lineup reads it from the repository without checking anything out.

Versions appear in the order given.

## Options

| option | what it does |
|---|---|
| `--base NAME` | the version others are measured against |
| `--derived NAME` | a version built on the base: show its changes (and commits, for two refs in one repo). Repeatable. |
| `--label NAME=TEXT` | tab label for a version |
| `--blurb NAME=TEXT` | one line under a version's heading |
| `--notes NAME=FILE.md` | Markdown notes shown in a version's Notes tab |
| `--only GLOB` | keep only paths matching one of these globs, e.g. `'src/**'`. Repeatable. |
| `--skip GLOB` | leave out matching paths. Repeatable. |
| `--page NAME=FILE.md` | a Markdown page. The first opens the page; the rest come last. |
| `--shelf NAME=FOLDER` | an extra tab of files |
| `--title TEXT` | the page's name |
| `--byline TEXT` | a line under the title, such as who wrote what |
| `--fragment` | leave out `<html>`, `<head>` and `<body>`, for hosts that wrap the page themselves |

Files over 400 KB and binary files are left out. `.git` folders are skipped.

## Requirements

Python 3.8 or later, standard library only, plus `git` for git sources. If the `markdown` package is installed, lineup uses it; otherwise a small built-in renderer handles headings, lists, tables, code blocks, emphasis and links.

## Example

This command built the page comparing four versions of the dial code in doc's [onir](https://github.com/saccade/onir) Arduino library against its main branch:

    python3 lineup.py onir-dial-versions.html \
      main=git:~/onir@main v1=./onir_dial_v1 v2=./onir_dial_v2 v3=./onir_dial_v3 \
      v4=git:~/onir@claude-dial-shine \
      --base main --derived v4 --only 'src/**' --only library.properties \
      --label v1="Sketches only" --label v4="Your code, moved forward" \
      --notes v1=./onir_dial_v1/NOTES.md \
      --page Overview=overview.md --shelf Sketches=./sketches \
      --title "onir Dial Versions"
