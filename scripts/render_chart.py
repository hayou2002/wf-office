#!/usr/bin/env python3
"""Render a small, deterministic office chart from a JSON spec.

The chart is drawn as inline SVG, then optionally captured as a 2x PNG with
Playwright. This keeps the visual result reproducible without requiring a
plotting library in the host runtime.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Any


PALETTE = [
    "#4C72B0",
    "#DD8452",
    "#55A868",
    "#C44E52",
    "#8172B3",
    "#937860",
    "#DA8BC3",
    "#8C8C8C",
]
FONT = "Microsoft YaHei, PingFang SC, Segoe UI, sans-serif"
SUPPORTED_TYPES = {"bar", "line", "stacked_bar"}


def number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须是数字")
    number_value = float(value)
    if not math.isfinite(number_value):
        raise ValueError(f"{label} 必须是有限数字")
    return number_value


def load_spec(path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"找不到规格文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"规格文件不是有效 JSON：{exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("规格文件顶层必须是对象")
    return spec


def validate_spec(spec: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]]]:
    chart_type = str(spec.get("type", "bar"))
    if chart_type not in SUPPORTED_TYPES:
        raise ValueError(f"不支持的图表类型：{chart_type}")

    categories = spec.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("categories 必须是非空数组")
    categories = [str(item) for item in categories]

    raw_series = spec.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise ValueError("series 必须是非空数组")

    series: list[dict[str, Any]] = []
    for index, item in enumerate(raw_series):
        if not isinstance(item, dict):
            raise ValueError(f"series[{index}] 必须是对象")
        name = str(item.get("name", f"系列 {index + 1}"))
        values = item.get("values")
        if not isinstance(values, list) or len(values) != len(categories):
            raise ValueError(f"series[{index}].values 长度必须等于 categories 长度")
        parsed = [number(value, f"series[{index}].values[{i}]") for i, value in enumerate(values)]
        if chart_type == "stacked_bar" and any(value < 0 for value in parsed):
            raise ValueError("stacked_bar 暂不支持负值")
        color = str(item.get("color") or PALETTE[index % len(PALETTE)])
        series.append({"name": name, "values": parsed, "color": color})

    return chart_type, categories, series


def format_value(value: float, spec: dict[str, Any]) -> str:
    fmt = str(spec.get("value_format", "number"))
    decimals = spec.get("decimals")
    if decimals is None:
        decimals = 1 if fmt == "percent" else 0
    decimals = max(0, min(4, int(decimals)))
    if fmt == "percent":
        return f"{value:.{decimals}f}%"
    if fmt == "currency":
        return f"{str(spec.get('currency_symbol', '¥'))}{value:,.{decimals}f}"
    return f"{value:,.{decimals}f}"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def build_svg(spec: dict[str, Any]) -> str:
    chart_type, categories, series = validate_spec(spec)
    width = max(720, min(2400, int(spec.get("width", 1200))))
    height = max(480, min(1600, int(spec.get("height", 720))))
    left, right, top, bottom = 96, 48, 156, 94
    plot_width = width - left - right
    plot_height = height - top - bottom
    if plot_width <= 0 or plot_height <= 0:
        raise ValueError("画布太小，放不下图表")

    if chart_type == "stacked_bar":
        values_for_bounds = [sum(item["values"][i] for item in series) for i in range(len(categories))]
    else:
        values_for_bounds = [value for item in series for value in item["values"]]
    data_min = min([0.0, *values_for_bounds])
    data_max = max([0.0, *values_for_bounds])
    if data_max == data_min:
        data_max = data_min + 1.0
    padding = (data_max - data_min) * 0.08
    axis_min = data_min - padding if data_min < 0 else 0.0
    axis_max = data_max + padding
    if axis_min == axis_max:
        axis_max = axis_min + 1.0

    def y_for(value: float) -> float:
        return top + plot_height * (axis_max - value) / (axis_max - axis_min)

    zero_y = y_for(0)
    title = str(spec.get("title", "办公图表"))
    subtitle = str(spec.get("subtitle", "")).strip()
    x_label = str(spec.get("x_label", "")).strip()
    y_label = str(spec.get("y_label", "")).strip()
    source = str(spec.get("source", "")).strip()

    parts: list[str] = [
        f'<svg id="chart" xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="54" font-family="{FONT}" font-size="28" font-weight="700" fill="#111827">{esc(title)}</text>',
    ]
    if subtitle:
        parts.append(
            f'<text x="{left}" y="86" font-family="{FONT}" font-size="16" fill="#4B5563">{esc(subtitle)}</text>'
        )

    legend_x = left
    legend_y = 118 if subtitle else 106
    legend_font = 13 if len(series) <= 5 else 12
    for item in series:
        label_width = max(44, len(item["name"]) * legend_font * 0.9 + 28)
        if legend_x + label_width > width - right:
            legend_x = left
            legend_y += 22
        parts.append(f'<rect x="{legend_x:.1f}" y="{legend_y - 11}" width="12" height="12" rx="2" fill="{esc(item["color"])}"/>')
        parts.append(
            f'<text x="{legend_x + 18:.1f}" y="{legend_y}" font-family="{FONT}" font-size="{legend_font}" fill="#374151">{esc(item["name"])}</text>'
        )
        legend_x += label_width

    for tick_index in range(5):
        value = axis_min + (axis_max - axis_min) * tick_index / 4
        y = y_for(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#E5E7EB" stroke-width="1"/>')
        parts.append(
            f'<text x="{left - 14}" y="{y + 5:.1f}" text-anchor="end" font-family="{FONT}" font-size="12" fill="#6B7280">{esc(format_value(value, spec))}</text>'
        )

    parts.append(f'<line x1="{left}" y1="{zero_y:.1f}" x2="{width - right}" y2="{zero_y:.1f}" stroke="#9CA3AF" stroke-width="1.5"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#9CA3AF" stroke-width="1.5"/>')

    group_width = plot_width / len(categories)
    rotate_labels = len(categories) > 8 or any(len(category) > 8 for category in categories)
    for index, category in enumerate(categories):
        center_x = left + group_width * (index + 0.5)
        label_y = height - 54
        if rotate_labels:
            parts.append(
                f'<text transform="translate({center_x:.1f} {label_y}) rotate(-28)" text-anchor="end" '
                f'font-family="{FONT}" font-size="12" fill="#374151">{esc(category)}</text>'
            )
        else:
            parts.append(
                f'<text x="{center_x:.1f}" y="{label_y}" text-anchor="middle" '
                f'font-family="{FONT}" font-size="13" fill="#374151">{esc(category)}</text>'
            )

    if chart_type == "bar":
        inner_width = group_width * 0.72
        bar_width = inner_width / len(series)
        for index, category in enumerate(categories):
            start_x = left + group_width * index + (group_width - inner_width) / 2
            for series_index, item in enumerate(series):
                value = item["values"][index]
                x = start_x + bar_width * series_index + max(1.0, bar_width * 0.06)
                y = y_for(value)
                rect_y = min(y, zero_y)
                rect_height = max(1.0, abs(y - zero_y))
                parts.append(
                    f'<rect x="{x:.1f}" y="{rect_y:.1f}" width="{max(1.0, bar_width * 0.88):.1f}" height="{rect_height:.1f}" '
                    f'rx="3" fill="{esc(item["color"])}"><title>{esc(category)} · {esc(item["name"])}：{esc(format_value(value, spec))}</title></rect>'
                )
                if len(categories) * len(series) <= 12:
                    label_y = y - 8 if value >= 0 else y + 16
                    parts.append(
                        f'<text x="{x + bar_width * 0.44:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                        f'font-family="{FONT}" font-size="11" fill="#374151">{esc(format_value(value, spec))}</text>'
                    )

    elif chart_type == "line":
        for item in series:
            points = []
            for index, value in enumerate(item["values"]):
                center_x = left + group_width * (index + 0.5)
                points.append((center_x, y_for(value), value))
            point_string = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
            parts.append(
                f'<polyline points="{point_string}" fill="none" stroke="{esc(item["color"])}" stroke-width="3" '
                f'stroke-linejoin="round" stroke-linecap="round"/>'
            )
            for center_x, y, value in points:
                parts.append(
                    f'<circle cx="{center_x:.1f}" cy="{y:.1f}" r="5" fill="#ffffff" stroke="{esc(item["color"])}" stroke-width="3">'
                    f'<title>{esc(item["name"])}：{esc(format_value(value, spec))}</title></circle>'
                )

    else:
        bar_width = group_width * 0.56
        for index, category in enumerate(categories):
            x = left + group_width * index + (group_width - bar_width) / 2
            cumulative = 0.0
            for item in series:
                value = item["values"][index]
                y_top = y_for(cumulative + value)
                y_bottom = y_for(cumulative)
                parts.append(
                    f'<rect x="{x:.1f}" y="{min(y_top, y_bottom):.1f}" width="{bar_width:.1f}" '
                    f'height="{max(1.0, abs(y_bottom - y_top)):.1f}" fill="{esc(item["color"])}">'
                    f'<title>{esc(category)} · {esc(item["name"])}：{esc(format_value(value, spec))}</title></rect>'
                )
                cumulative += value
            total = cumulative
            if len(categories) <= 12:
                parts.append(
                    f'<text x="{x + bar_width / 2:.1f}" y="{y_for(total) - 8:.1f}" text-anchor="middle" '
                    f'font-family="{FONT}" font-size="11" fill="#374151">{esc(format_value(total, spec))}</text>'
                )

    if x_label:
        parts.append(
            f'<text x="{left + plot_width / 2:.1f}" y="{height - 18}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="13" fill="#4B5563">{esc(x_label)}</text>'
        )
    if y_label:
        parts.append(
            f'<text transform="translate(28 {top + plot_height / 2:.1f}) rotate(-90)" text-anchor="middle" '
            f'font-family="{FONT}" font-size="13" fill="#4B5563">{esc(y_label)}</text>'
        )
    if source:
        parts.append(
            f'<text x="{left}" y="{height - 4}" font-family="{FONT}" font-size="12" fill="#6B7280">{esc(source)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def build_html(svg: str, width: int, height: int) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<style>html,body{margin:0;background:#fff}#chart{display:block}</style>"
        f"</head><body>{svg}</body></html>"
    )


def render_png(html_path: Path, png_path: Path, width: int, height: int) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("需要 Playwright 才能生成 PNG；安装后再运行，或先使用 --html-only") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=2,
        )
        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(200)
        page.locator("#chart").screenshot(path=str(png_path))
        browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 JSON 规格生成办公图表 PNG/HTML")
    parser.add_argument("--spec", required=True, type=Path, help="图表 JSON 规格")
    parser.add_argument("--out", required=True, type=Path, help="输出 PNG")
    parser.add_argument("--html", type=Path, help="输出 HTML（默认与 PNG 同名）")
    parser.add_argument("--html-only", action="store_true", help="只生成 HTML，不启动浏览器")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec = load_spec(args.spec)
        svg = build_svg(spec)
        width = int(spec.get("width", 1200))
        height = int(spec.get("height", 720))
        html_path = args.html or args.out.with_suffix(".html")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(build_html(svg, width, height), encoding="utf-8")
        if not args.html_only:
            render_png(html_path, args.out, width, height)
        print(
            json.dumps(
                {
                    "ok": True,
                    "html": str(html_path.resolve()),
                    "png": None if args.html_only else str(args.out.resolve()),
                    "type": spec.get("type", "bar"),
                    "series": len(spec.get("series", [])),
                    "categories": len(spec.get("categories", [])),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
