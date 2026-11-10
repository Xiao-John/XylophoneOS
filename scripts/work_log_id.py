#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate an 8-hex-digit worklog id seeded by the title.

Sequential worklog numbers collide whenever parallel lines pick the same
free number (0216 happened twice this way). New worklogs instead use a
pseudo-random id derived only from the title:

    id = sha256(normalized_title_utf8)[:8]      # 8 lowercase hex digits

A salt loop (title + NUL + counter) guarantees the id is absent from the
target directory, whose filenames remain the registry of record. Legacy
4-digit ids are never rewritten and keep their existing citation style.

Usage:
    python3 scripts/work_log_id.py "标题"                 # id + file + cite
    python3 scripts/work_log_id.py "标题" --slug my_topic  # explicit filename slug
    python3 scripts/work_log_id.py "标题" --create         # scaffold the stub file
    python3 scripts/work_log_id.py "标题" --dir /path/to/worklog  # alternate directory (tests)
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "docs/work_log"
NEW_ID = re.compile(r"^[0-9a-f]{8}$")
LEGACY_ID = re.compile(r"^\d{4}$")


def normalize(title):
    """Trim and collapse whitespace so pasted titles hash stably."""
    return " ".join(title.split())


def derive(title, salt=""):
    seed = title if not salt else title + "\x00" + salt
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


def taken_ids(directory):
    """Ids already claimed by filenames in the directory (new or legacy)."""
    taken = set()
    if directory.is_dir():
        for path in directory.iterdir():
            prefix = path.name.split("_", 1)[0]
            if NEW_ID.match(prefix) or LEGACY_ID.match(prefix):
                taken.add(prefix)
    return taken


def allocate(title, directory):
    """Deterministic id for title, re-hashed until unique in directory."""
    taken = taken_ids(directory)
    salt = 0
    while True:
        ident = derive(title, "" if salt == 0 else str(salt))
        if ident not in taken:
            return ident
        salt += 1


def slugify(title, explicit=None):
    if explicit is not None:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", explicit).strip("_")
    else:
        # Best effort: ASCII words from the title; pass --slug for others.
        ascii_part = title.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "_", ascii_part).strip("_")[:48].strip("_")
    return slug


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="worklog title; the only seed")
    parser.add_argument("--slug", help="filename topic slug (default: ASCII from title)")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR,
                        help="worklog directory to check for collisions")
    parser.add_argument("--create", action="store_true",
                        help="scaffold the stub file instead of only printing")
    args = parser.parse_args()

    title = normalize(args.title)
    if not title:
        raise SystemExit("title is empty after normalization")
    directory = args.dir.resolve()
    if not directory.is_dir():
        raise SystemExit(f"worklog directory missing: {directory}")

    ident = allocate(title, directory)
    slug = slugify(title, args.slug)
    name = f"{ident}_{slug}.md" if slug else f"{ident}.md"
    path = directory / name

    print(f"id:      {ident}")
    print(f"file:    docs/work_log/{name}")
    print(f"cite:    {ident}")

    if args.create:
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing file: {path}")
        body = (
            f"# {ident} {title}\n\n"
            "> 草稿占位。按 docs/Discipline.md 交接要求补全：任务范围与改动、\n"
            "> 选择与原因、构建/运行命令与证据、通过/失败/未运行项、下一步。\n"
        )
        path.write_text(body, encoding="utf-8")
        print(f"created: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


if __name__ == "__main__":
    main()
