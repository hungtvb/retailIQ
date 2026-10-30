"""Validate local Markdown links in active RetailIQ documentation.

Historical files in docs/archive/2026-10-30/legacy are intentionally excluded:
their paths and relative links are preserved exactly as a migration snapshot.
This check uses only the Python standard library.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r'!?\[[^\]\n]*\]\((<[^>]+>|[^)\s]+)(?:\s+["\'][^"\']*["\'])?\)')
CODE_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
INLINE_CODE_RE = re.compile(r'`+[^\`\n]*`+')


def active_markdown_files(root: Path) -> list[Path]:
    files = [root / "README.md", *(root / "docs").rglob("*.md")]
    return sorted(
        path
        for path in files
        if path.is_file()
        and not path.relative_to(root).as_posix().startswith(
            "docs/archive/2026-10-30/legacy/"
        )
    )


def inspect_markdown(path: Path, root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    fence_char: str | None = None
    in_comment = False

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        marker = CODE_FENCE_RE.match(line)
        if marker:
            char = marker.group(1)[0]
            if fence_char is None:
                fence_char = char
            elif fence_char == char:
                fence_char = None
            continue
        if fence_char is not None:
            continue

        # Ignore links in HTML comments and inline code.
        if in_comment:
            if "-->" not in line:
                continue
            line = line.split("-->", 1)[1]
            in_comment = False
        while "<!--" in line:
            before, comment = line.split("<!--", 1)
            if "-->" in comment:
                line = before + comment.split("-->", 1)[1]
            else:
                line = before
                in_comment = True
                break
        line = INLINE_CODE_RE.sub("", line)

        for match in LINK_RE.finditer(line):
            uri = match.group(1).strip("<>")
            parsed = urlsplit(uri)
            if parsed.scheme or parsed.netloc or uri.startswith(("#", "//")):
                continue
            link_path = unquote(parsed.path)
            if not link_path:
                continue
            count += 1
            target = (root / link_path.lstrip("/")) if link_path.startswith("/") else (path.parent / link_path)
            target = target.resolve()
            if not target.is_relative_to(root) or not target.exists():
                errors.append(
                    f"{path.relative_to(root)}:{line_number}: {uri} -> missing/unsafe path"
                )
    return count, errors


def main() -> int:
    count = 0
    errors: list[str] = []
    files = active_markdown_files(ROOT)
    for path in files:
        checked, found = inspect_markdown(path, ROOT)
        count += checked
        errors.extend(found)

    for error in errors:
        print(error, file=sys.stderr)
    print(f"Documentation link check: {len(files)} active Markdown files, {count} local links, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
