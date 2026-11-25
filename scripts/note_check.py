#!/usr/bin/env python3
"""Check structured Markdown notes before delivery.

退出码：0（通过）/ 1（命中：有阻断项）。
最后验证：2026-11-14，self-test 与真实笔记各跑一次。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PLACEHOLDER_PATTERNS = (
    (re.compile(r"lorem ipsum", re.IGNORECASE), "还留着 Lorem ipsum 假文字"),
    (re.compile(r"\bTODO\b"), "还留着 TODO 标记"),
    (re.compile(r"\bplaceholder\b", re.IGNORECASE), "还留着 placeholder 字样"),
    (re.compile(r"待补充|此处填写|请填写|点击这里编辑|示例文本"), "还留着没人替换的占位文案"),
    (re.compile(r"\bxxx+\b", re.IGNORECASE), "还留着 xxx 占位"),
)

LOCAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]+Use" + "rs[\\/]+[A-Za-z0-9._ -]+[\\/]+"),
    re.compile(r"/Use" + "rs/(?!Shared(?:/|$))[A-Za-z0-9._-]+/"),
    re.compile(r"/hom" + r"e/[A-Za-z0-9._-]+/"),
    re.compile(r"/ro" + r"ot(?:/|$)"),
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
FENCE_RE = re.compile(r"^\s*```")
TABLE_RE = re.compile(r"^\s*\|")


def iter_markdown(target: Path):
    if target.is_file():
        if target.suffix.lower() == ".md":
            yield target
        return
    for path in sorted(target.rglob("*.md")):
        if any(part in {"node_modules", ".git", "_temp"} for part in path.parts):
            continue
        yield path


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def add(findings: list[dict], level: str, code: str, path: Path, message: str, line: int = 0) -> None:
    findings.append(
        {
            "level": level,
            "code": code,
            "file": str(path),
            "line": line,
            "message": message,
        }
    )


def check_header(path: Path, lines: list[str], findings: list[dict]) -> None:
    head = [(i + 1, line.strip()) for i, line in enumerate(lines[:16]) if line.strip()]
    if not any(line.startswith(">") and "来源" in line for _, line in head):
        add(findings, "error", "note.source", path, "前 16 行没有「> 来源」行；补上作者、标题、日期或链接")
    if not any(line.startswith(">") and "一句话" in line for _, line in head):
        add(findings, "error", "note.summary", path, "前 16 行没有「> 一句话」总结；用一句话说清这篇要记住什么")


def check_fences(path: Path, lines: list[str], findings: list[dict]) -> None:
    open_line = 0
    open_fence = False
    for number, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            if open_fence:
                open_fence = False
            else:
                open_fence = True
                open_line = number
    if open_fence:
        add(findings, "error", "note.fence", path, "代码围栏没有闭合", open_line)


def check_tables(path: Path, lines: list[str], findings: list[dict]) -> None:
    block: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal block
        if not block:
            return
        if len(block) < 2:
            add(findings, "error", "note.table", path, "表格只有一行，缺少表头分隔行", block[0][0])
            block = []
            return
        separator = block[1][1]
        if not re.match(r"^\s*\|(?:\s*:?---:?\s*\|)+\s*$", separator):
            add(findings, "error", "note.table", path, "表格第二行不是表头分隔行", block[1][0])
        widths = {row.count("|") - 1 for _, row in block if row.strip()}
        if len(widths) > 1:
            add(findings, "warn", "note.table", path, f"表格列数不一致：{sorted(widths)}", block[0][0])
        block = []

    for number, line in enumerate(lines, 1):
        if TABLE_RE.match(line):
            block.append((number, line.rstrip()))
        else:
            flush()
    flush()


def check_images(path: Path, lines: list[str], findings: list[dict]) -> None:
    current_h2 = ""
    h2_image_count = 0
    for number, line in enumerate(lines, 1):
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) == 2:
            current_h2 = heading.group(2).strip()
            h2_image_count = 0
        for match in IMAGE_RE.finditer(line):
            alt = match.group(1).strip()
            target = match.group(2).strip().split(" ")[0].strip("<>")
            if not alt:
                add(findings, "error", "note.image-alt", path, "图片没有 alt 说明", number)
            if target.startswith(("http://", "https://", "data:", "#")):
                add(findings, "info", "note.image-remote", path, f"图片引用外部资源：{target[:80]}", number)
                continue
            local = (path.parent / target.split("?")[0].split("#")[0]).resolve()
            if not local.exists():
                add(findings, "error", "note.image-missing", path, f"图片不存在：{target}", number)
            if current_h2:
                h2_image_count += 1
                if h2_image_count == 2:
                    add(findings, "warn", "note.image-density", path, f"H2「{current_h2}」配了多张图；默认每个 H2 最多一张", number)


def check_headings(path: Path, lines: list[str], findings: list[dict]) -> None:
    headings: list[tuple[int, int, str]] = []
    for number, line in enumerate(lines, 1):
        match = HEADING_RE.match(line)
        if match:
            headings.append((number, len(match.group(1)), match.group(2).strip()))
    if not headings:
        add(findings, "error", "note.heading", path, "没有标题；至少要有 H2 分节")
        return
    first = headings[0]
    if first[1] == 1:
        add(findings, "error", "note.heading-h1", path, "正文不要写 H1；标题由文档标题承担", first[0])
    elif first[1] > 2:
        add(findings, "error", "note.heading-first", path, f"第一个标题是 H{first[1]}；应该从 H2 开始", first[0])
    previous = first
    seen: set[tuple[int, str]] = set()
    for current in headings[1:]:
        if current[1] > 3:
            add(findings, "error", "note.heading-depth", path, f"标题层级到 H{current[1]}；笔记最多用 H3", current[0])
        if current[1] - previous[1] > 1:
            add(findings, "error", "note.heading-jump", path, f"从 H{previous[1]} 跳到 H{current[1]}", current[0])
        key = (current[1], current[2])
        if key in seen:
            add(findings, "error", "note.heading-duplicate", path, f"重复标题：{current[2]}", current[0])
        seen.add(key)
        previous = current
    for index, heading in enumerate(headings):
        body_start = heading[0]
        body_end = headings[index + 1][0] - 1 if index + 1 < len(headings) else len(lines)
        body = "\n".join(lines[body_start:body_end]).strip()
        next_level = headings[index + 1][1] if index + 1 < len(headings) else 0
        if not body and (next_level == 0 or next_level <= heading[1]):
            add(findings, "error", "note.heading-empty", path, f"空章节：{heading[2]}", heading[0])


def check_paths_and_placeholders(path: Path, text: str, findings: list[dict]) -> None:
    for pattern, message in PLACEHOLDER_PATTERNS:
        match = pattern.search(text)
        if match:
            add(findings, "error", "note.placeholder", path, message, line_of(text, match.start()))
    for pattern in LOCAL_PATH_PATTERNS:
        match = pattern.search(text)
        if match:
            add(
                findings,
                "error",
                "note.local-path",
                path,
                f"写死了本机绝对路径：{match.group(0)}；改成相对路径",
                line_of(text, match.start()),
            )


def check_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        add(findings, "error", "note.encoding", path, "不是 UTF-8 文本")
        return findings
    except OSError as exc:
        add(findings, "error", "note.read", path, f"读不出来：{exc}")
        return findings
    lines = text.splitlines()
    check_header(path, lines, findings)
    check_fences(path, lines, findings)
    check_headings(path, lines, findings)
    check_images(path, lines, findings)
    check_tables(path, lines, findings)
    check_paths_and_placeholders(path, text, findings)
    return findings


def self_test() -> int:
    good = """> 来源：测试文章 · 2026-01-01
>
> 一句话：先看结论，再看细节。

## 一、结论

- **先给判断。** 再解释原因。

### 1. 细节

| 项 | 值 |
| --- | --- |
| A | 1 |
"""
    bad = """# 测试

## 一、没有来源

### 1. 空章节

## 一、没有来源

#### 跳级

![](missing.svg)

```text
没有闭合
"""
    findings = check_text(good)
    if any(item["level"] == "error" for item in findings):
        print("FAIL  good sample")
        for item in findings:
            print(f"      {item['code']}: {item['message']}")
        print("结论：命中（退出码 1：self-test 失败——好样被误报）")
        return 1
    bad_findings = check_text(bad)
    codes = {item["code"] for item in bad_findings if item["level"] == "error"}
    expected = {"note.source", "note.summary", "note.heading-empty", "note.heading-duplicate", "note.heading-jump", "note.image-alt", "note.image-missing", "note.fence"}
    missing = expected - codes
    if missing:
        print(f"FAIL  bad sample missing: {sorted(missing)}")
        for item in bad_findings:
            print(f"      {item['code']}: {item['message']}")
        print("结论：命中（退出码 1：self-test 失败——坏样没被抓全）")
        return 1
    print("PASS  note check self-test")
    print("结论：通过（退出码 0：self-test 全部通过）")
    return 0


def check_text(text: str) -> list[dict]:
    findings: list[dict] = []
    path = Path("<self-test>")
    lines = text.splitlines()
    check_header(path, lines, findings)
    check_fences(path, lines, findings)
    check_headings(path, lines, findings)
    check_images(path, lines, findings)
    check_tables(path, lines, findings)
    check_paths_and_placeholders(path, text, findings)
    return findings


def cmd_check(args) -> int:
    findings: list[dict] = []
    found = False
    for raw in args.paths:
        target = Path(raw)
        if not target.exists():
            findings.append(
                {"level": "error", "code": "note.target", "file": str(target), "line": 0, "message": "路径不存在"}
            )
            continue
        for path in iter_markdown(target):
            found = True
            findings.extend(check_file(path))
    if not found:
        findings.append(
            {"level": "error", "code": "note.empty", "file": args.paths[0], "line": 0, "message": "这里没有 .md 文件"}
        )
    if args.json:
        print(json.dumps({"findings": findings}, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            location = f"{item['file']}:{item['line']}" if item["line"] else item["file"]
            print(f"{item['level'].upper():5} {item['code']}: {location}: {item['message']}")
        errors = sum(1 for item in findings if item["level"] == "error")
        warnings = sum(1 for item in findings if item["level"] == "warn")
        print(f"\n{errors} error(s), {warnings} warning(s)")
        if errors:
            print(f"结论：命中（退出码 1：{errors} 个阻断先改再交）")
        else:
            print(f"结论：通过（退出码 0：0 个阻断，{warnings} 个提示）")
    return 1 if any(item["level"] == "error" for item in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="note_check.py", description="知识笔记结构自检")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="检查 Markdown 笔记")
    check.add_argument("paths", nargs="+", help="笔记文件或目录")
    check.add_argument("--json", action="store_true", help="输出 JSON")
    check.set_defaults(func=cmd_check)
    test = sub.add_parser("self-test", help="跑内置样例")
    test.set_defaults(func=lambda args: self_test())
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
