"""Build safe static documentation and a repository-subpath-friendly landing page."""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def inline(text: str) -> str:
    """Escape source HTML and allow only explicit safe link schemes."""
    tokens: list[str] = []

    def token(value: str) -> str:
        tokens.append(value)
        return f"\x00{len(tokens) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: token(f"<code>{html.escape(m[1])}</code>"), text)

    def link(match: re.Match[str]) -> str:
        label, target = match[1], match[2]
        parsed = urlsplit(target)
        if parsed.scheme not in {"", "https", "http"} or target.startswith("//"):
            return label
        if not parsed.scheme:
            target = re.sub(r"\.md(?=($|#))", ".html", target)
            target = target.replace("../IMPLEMENTATION_STATUS.html", "../status.html")
            target = target.replace("../NOTICE.html", "../notice.html")
        return token(f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>')

    text = re.sub(r"\[([^\]]+)\]\(([^\s)]+)\)", link, text)
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    for i, value in enumerate(tokens):
        text = text.replace(f"\x00{i}\x00", value)
    return text


def markdown(source: str) -> str:
    """A deliberately small Markdown renderer: no raw HTML or execution."""
    output: list[str] = []
    paragraph: list[str] = []
    code: list[str] | None = None
    list_open = False
    table_open = False

    def flush_paragraph() -> None:
        if paragraph:
            output.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            output.append("</ul>")
            list_open = False

    def close_table() -> None:
        nonlocal table_open
        if table_open:
            output.append("</tbody></table></div>")
            table_open = False

    for line in source.splitlines():
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            close_table()
            if code is None:
                code = []
            else:
                output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if line.startswith("|") and line.rstrip().endswith("|"):
            flush_paragraph()
            close_list()
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in cells):
                continue
            if not table_open:
                output.append('<div class="table-wrap"><table><tbody>')
                table_open = True
            output.append("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in cells) + "</tr>")
            continue
        close_table()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading[1])
            output.append(f"<h{level}>{inline(heading[2])}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            flush_paragraph()
            if not list_open:
                output.append("<ul>")
                list_open = True
            output.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif not line.strip():
            flush_paragraph()
            close_list()
        else:
            close_list()
            paragraph.append(line.strip())
    flush_paragraph()
    close_list()
    close_table()
    if code is not None:
        output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    return "\n".join(output)


def document_page(title: str, body: str, depth: int) -> str:
    prefix = "../" * depth
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Hypothesis Lab local research documentation">
<title>{html.escape(title)} | Hypothesis Lab</title><link rel="stylesheet" href="{prefix}styles.css"></head>
<body class="documentation"><header class="doc-nav"><a class="brand" href="{prefix}index.html"><span class="mark">h.</span> Hypothesis Lab</a><nav><a href="{prefix}docs/quickstart.html">Quickstart</a><a href="{prefix}docs/api/index.html">Python API</a><a href="{prefix}audit.html">Audit</a><a href="{prefix}status.html">Status</a></nav></header>
<main class="doc-content">{body}</main><footer class="doc-footer">Local-first research. Synthetic examples. No real-money execution. <a href="{prefix}index.html">Home</a></footer></body></html>'''


def build(destination: Path) -> int:
    destination = destination.resolve()
    source = (ROOT / "site").resolve()
    if (
        destination == ROOT
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("Choose a dedicated build directory outside the site source")
    destination.mkdir(parents=True, exist_ok=True)
    for asset in source.rglob("*"):
        if asset.is_file() and asset.suffix.lower() in {".html", ".css", ".js", ".svg", ".png"}:
            target = destination / asset.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(asset, target)
    count = 0
    for document in (ROOT / "docs").rglob("*.md"):
        relative = document.relative_to(ROOT).with_suffix(".html")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = document.read_text(encoding="utf-8")
        title = next(
            (line.lstrip("# ") for line in text.splitlines() if line.startswith("# ")),
            document.stem,
        )
        target.write_text(
            document_page(title, markdown(text), len(relative.parts) - 1), encoding="utf-8"
        )
        count += 1
    for name, output in (
        ("AUDIT.md", "audit.html"),
        ("IMPLEMENTATION_STATUS.md", "status.html"),
        ("NOTICE.md", "notice.html"),
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        (destination / output).write_text(
            document_page(name[:-3], markdown(text), 0), encoding="utf-8"
        )
        count += 1
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    if not (destination / "index.html").is_file():
        raise ValueError("Landing page is missing")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "site")
    args = parser.parse_args()
    count = build(args.output)
    print(f"Built {count} documentation pages and bundled site assets in {args.output.resolve()}")


if __name__ == "__main__":
    main()
