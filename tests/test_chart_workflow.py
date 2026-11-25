from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        png = temp / "chart.png"
        html = temp / "chart.html"
        source = temp / "source.docx"
        output = temp / "output.docx"

        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "render_chart.py"),
                "--spec",
                str(SCRIPTS / "sample-chart.json"),
                "--out",
                str(png),
                "--html",
                str(html),
            ],
            check=True,
        )
        assert png.exists() and png.stat().st_size > 1000
        assert html.exists()

        sample_spec = json.loads((SCRIPTS / "sample-chart.json").read_text(encoding="utf-8"))
        for chart_type in ("line", "stacked_bar"):
            variant = dict(sample_spec)
            variant["type"] = chart_type
            variant_path = temp / f"{chart_type}.json"
            variant_path.write_text(json.dumps(variant, ensure_ascii=False), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_chart.py"),
                    "--spec",
                    str(variant_path),
                    "--out",
                    str(temp / f"{chart_type}.png"),
                    "--html",
                    str(temp / f"{chart_type}.html"),
                    "--html-only",
                ],
                check=True,
            )

        document = Document()
        document.add_heading("测试报告", 0)
        document.add_paragraph("这是一段用于测试图表插入的正文。")
        document.save(source)

        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "insert_chart.py"),
                "--docx",
                str(source),
                "--image",
                str(png),
                "--output",
                str(output),
                "--caption",
                "图 1 测试图表",
                "--alt",
                "测试图表：三个类别的柱状图",
            ],
            check=True,
        )
        assert output.exists()
        check = Document(output)
        assert len(check.inline_shapes) == 1
        assert check.inline_shapes[0]._inline.docPr.get("descr") == "测试图表：三个类别的柱状图"

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
