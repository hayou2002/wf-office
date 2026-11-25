#!/usr/bin/env python3
"""Insert a chart PNG into a DOCX with a caption and alt text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt


def find_anchor(document, text: str | None):
    if not text:
        return None
    for paragraph in document.paragraphs:
        if text in paragraph.text:
            return paragraph
    return None


def add_caption(document, caption: str):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(caption)
    run.italic = True
    run.font.size = Pt(9)
    try:
        paragraph.style = document.styles["Caption"]
    except KeyError:
        pass
    return paragraph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把 PNG 图表插入 DOCX")
    parser.add_argument("--docx", required=True, type=Path, help="输入 DOCX")
    parser.add_argument("--image", required=True, type=Path, help="PNG/JPG 图表")
    parser.add_argument("--output", required=True, type=Path, help="输出 DOCX（不要覆盖原稿）")
    parser.add_argument("--caption", required=True, help="图题，例如：图 1 各渠道收入")
    parser.add_argument("--alt", help="替代文本；默认使用图题")
    parser.add_argument("--width-cm", type=float, default=16.0, help="图片宽度（厘米）")
    parser.add_argument("--anchor", help="在包含这段文字的段落后插入；找不到则追加到文末")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.docx.exists():
            raise ValueError(f"找不到 DOCX：{args.docx}")
        if not args.image.exists():
            raise ValueError(f"找不到图片：{args.image}")
        if args.docx.resolve() == args.output.resolve():
            raise ValueError("输出不能覆盖原稿；请给 --output 一个不同的文件名")

        document = Document(str(args.docx))
        anchor = find_anchor(document, args.anchor)

        picture_paragraph = document.add_paragraph()
        picture_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = picture_paragraph.add_run()
        inline_shape = run.add_picture(str(args.image), width=Cm(max(1.0, args.width_cm)))
        alt_text = args.alt or args.caption
        doc_pr = inline_shape._inline.docPr
        doc_pr.set("descr", alt_text)
        doc_pr.set("title", args.caption)

        if anchor is not None:
            anchor._p.addnext(picture_paragraph._p)

        caption_paragraph = add_caption(document, args.caption)
        if anchor is not None:
            picture_paragraph._p.addnext(caption_paragraph._p)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(args.output))

        check = Document(str(args.output))
        inline_count = len(check.inline_shapes)
        if inline_count == 0:
            raise ValueError("输出文件没有可读的内联图片")

        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(args.output.resolve()),
                    "inline_shapes": inline_count,
                    "anchor_found": anchor is not None,
                    "caption": args.caption,
                    "alt": alt_text,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
