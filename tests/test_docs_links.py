"""Regression tests for documentation link validation."""

from pathlib import Path

from scripts.check_docs_links import active_markdown_files, inspect_markdown


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_resolves_valid_relative_link(tmp_path: Path) -> None:
    write(tmp_path / "docs" / "PROJECT.md", "# Project\n")
    file = write(tmp_path / "docs" / "weeks" / "README.md", "[Project](../PROJECT.md)\n")
    count, errors = inspect_markdown(file, tmp_path)
    assert (count, errors) == (1, [])


def test_rejects_broken_and_escaping_links(tmp_path: Path) -> None:
    file = write(tmp_path / "README.md", "[Missing](not-there.md)\n[Outside](../../outside.md)\n")
    count, errors = inspect_markdown(file, tmp_path)
    assert count == 2
    assert len(errors) == 2


def test_ignores_inline_code_and_fenced_links(tmp_path: Path) -> None:
    file = write(
        tmp_path / "README.md",
        "`[fake](does-not-exist.md)`\n"
        "```md\n[example](missing.md)\n```\n"
        "[External](https://example.com/)\n",
    )
    count, errors = inspect_markdown(file, tmp_path)
    assert count == 0
    assert errors == []


def test_single_line_and_multiline_html_comments(tmp_path: Path) -> None:
    write(tmp_path / "target.md", "# Target\n")
    file = write(
        tmp_path / "README.md",
        "<!-- [ignored](missing.md) -->\n"
        "<!--\n[ignored](missing-too.md)\n-->\n"
        "[Valid](target.md)\n"
        "[Invalid](not-here.md)\n",
    )
    count, errors = inspect_markdown(file, tmp_path)
    assert count == 2
    assert len(errors) == 1
    assert "not-here.md" in errors[0]


def test_archival_snapshots_excluded(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "# Main\n")
    write(tmp_path / "docs" / "README.md", "# Docs\n")
    write(tmp_path / "docs" / "archive" / "README.md", "# Archive\n")
    write(tmp_path / "docs" / "archive" / "2026-10-30" / "legacy" / "old.md", "[Bad](missing.md)\n")
    files = [p.relative_to(tmp_path).as_posix() for p in active_markdown_files(tmp_path)]
    assert len(files) == 3
    assert not any("legacy" in p for p in files)
