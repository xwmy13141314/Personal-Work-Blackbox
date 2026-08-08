"""报告导出器：将报告 Markdown 渲染为自包含的单文件 HTML。

设计目标（契合用户偏好）：
- 单文件内联 CSS，无外部依赖，可离线打开、可直接微信/邮件发送；
- 卡片化布局 + 时间分布环形图（纯 SVG，无 JS 依赖，打印/PDF 友好）；
- 样式对齐前端报告卡片观感（白底卡片、系统字体、中文行距优化）；
- 带 @media print，浏览器直接 Ctrl+P 也能打出排版干净的 PDF。
"""

from __future__ import annotations

import html
import math
import re
from datetime import datetime

try:
    import markdown as _md  # type: ignore
except ImportError:  # pragma: no cover - 依赖缺失时给清晰报错
    _md = None


# 环形图扇形配色
_DONUT_PALETTE = [
    "#0071e3", "#34c759", "#ff9500", "#af52de", "#ff3b30",
    "#5856d6", "#00c7be", "#ffd60a", "#ff2d55", "#64d2ff",
]

# h2 章节标题 → emoji 图标（按关键词命中，未命中默认 📄）
_H2_ICONS = [
    ("概览", "📋"), ("总结", "📋"),
    ("成果", "🏆"), ("里程碑", "🏆"), ("关键", "🏆"),
    ("完成", "✅"), ("已办", "✅"),
    ("沟通", "💬"), ("会议", "💬"),
    ("待办", "📌"), ("跟进", "📌"), ("进行中", "📌"),
    ("计划", "🎯"), ("下周", "🎯"), ("下月", "🎯"), ("建议", "🎯"),
    ("时间分布", "📊"), ("时间", "📊"),
    ("效率", "⚡"), ("趋势", "📈"),
    ("进度", "🔄"),
]


def render_donut_svg(time_dist: list[dict], size: int = 220) -> str:
    """渲染时间分布环形图为自包含 SVG 字符串

    Args:
        time_dist: [{"category","minutes","percent"}, ...]
        size: 环形图正方形画布尺寸

    Returns:
        完整 <svg>...</svg> 字符串；空数据返回空字符串
    """
    items = [it for it in (time_dist or []) if it.get("percent", 0) > 0]
    if not items:
        return ""

    cx = size / 2
    cy = size / 2
    radius = size * 0.38
    stroke = size * 0.16
    circumference = 2 * math.pi * radius
    gap = max(0.5, circumference * 0.004)  # 扇形间留细缝

    total_pct = sum(it["percent"] for it in items)
    if total_pct <= 0:
        return ""

    slices = []
    offset = 0.0
    for i, it in enumerate(items):
        pct = it["percent"]
        length = circumference * pct / total_pct
        dash = max(length - gap, 0)
        color = _DONUT_PALETTE[i % len(_DONUT_PALETTE)]
        slices.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke:.1f}" '
            f'stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx:.1f} {cy:.1f})">'
            f'<title>{html.escape(it["category"])}: {pct:.0f}%</title></circle>'
        )
        offset += length

    # 中心：总时长
    total_min = sum(it.get("minutes", 0) for it in items)
    hours = total_min // 60
    mins = total_min % 60
    center_top = f"{hours}h{mins:02d}m" if hours > 0 else f"{mins}m"
    center_svg = (
        f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" '
        f'font-size="{size * 0.12:.0f}" font-weight="700" fill="#1d1d1f">{center_top}</text>'
        f'<text x="{cx:.1f}" y="{cy + size * 0.08:.1f}" text-anchor="middle" '
        f'font-size="{size * 0.05:.0f}" fill="#9a9a9f">总时长</text>'
    )

    # 图例（色块 + 类别 + 时长 + 占比）
    legend_w = size * 0.95
    legend_x = size + 24
    line_h = size * 0.135
    legend_items = []
    for i, it in enumerate(items):
        y = line_h / 2 + i * line_h
        color = _DONUT_PALETTE[i % len(_DONUT_PALETTE)]
        m = it.get("minutes", 0)
        dur = f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"
        legend_items.append(
            f'<rect x="{legend_x:.0f}" y="{y - 6:.0f}" width="12" height="12" rx="3" fill="{color}"/>'
            f'<text x="{legend_x + 20:.0f}" y="{y + 4:.0f}" font-size="{size * 0.058:.0f}" fill="#1d1d1f">'
            f'{html.escape(it["category"])}</text>'
            f'<text x="{legend_x + legend_w:.0f}" y="{y + 4:.0f}" text-anchor="end" '
            f'font-size="{size * 0.058:.0f}" fill="#6e6e73">{dur} · {it["percent"]:.0f}%</text>'
        )

    total_w = legend_x + legend_w
    total_h = max(size, len(items) * line_h)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'font-family="-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Microsoft YaHei\',sans-serif">'
        f'<g>{"".join(slices)}{center_svg}</g>'
        f'<g>{"".join(legend_items)}</g>'
        f'</svg>'
    )


def _inject_h2_icons(body_html: str) -> str:
    """给 markdown 渲染出的 h2 章节标题前注入 emoji 图标"""
    def repl(m: re.Match) -> str:
        text = m.group(1)
        icon = "📄"
        for kw, ico in _H2_ICONS:
            if kw in text:
                icon = ico
                break
        return f'<h2><span class="h2-ico">{icon}</span>{text}</h2>'
    return re.sub(r'<h2>(.*?)</h2>', repl, body_html, flags=re.DOTALL)


# 内联 CSS（对齐前端报告卡片观感）
_REPORT_CSS = """
:root{--fg:#1d1d1f;--fg-2:#6e6e73;--fg-3:#9a9a9f;--bg:#f5f5f7;--card:#fff;
  --border:rgba(0,0,0,.1);--accent:#0071e3;--accent-soft:rgba(0,113,227,.08);--code-bg:rgba(0,0,0,.05);}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px;line-height:1.7;padding:32px 16px;}
.paper{max-width:820px;margin:0 auto;background:var(--card);border-radius:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.06),0 8px 30px rgba(0,0,0,.06);padding:40px 48px 32px;}
/* Hero */
.hero{margin-bottom:4px;}
.hero .report-title{font-size:26px;font-weight:700;margin:6px 0;line-height:1.25;letter-spacing:-.01em;}
.meta-pill{display:inline-block;background:var(--accent-soft);color:var(--accent);font-size:12px;
  font-weight:600;padding:3px 10px;border-radius:999px;}
.meta{color:var(--fg-2);font-size:12.5px;margin-top:8px;}
/* 图表卡 */
.chart-card{margin:6px 0 20px;padding:20px 22px;background:linear-gradient(180deg,#fbfbfd,#f5f5f7);
  border:1px solid var(--border);border-radius:14px;}
.chart-card .chart-title{font-size:14px;font-weight:600;margin:0 0 14px;color:var(--fg);}
.chart-card svg{display:block;}
.divider{height:1px;background:var(--border);margin:24px 0 4px;border:none;}
/* 报告正文 */
.report h1{font-size:22px;font-weight:600;margin:8px 0 12px;line-height:1.3;}
.report h2{font-size:17px;font-weight:600;margin:22px 0 8px;padding-left:12px;border-left:3px solid var(--accent);}
.report h2 .h2-ico{margin-right:8px;font-style:normal;}
.report h3{font-size:15px;font-weight:600;margin:16px 0 6px;}
.report h4{font-size:14px;font-weight:600;margin:12px 0 4px;}
.report p{margin:8px 0;}
.report ul,.report ol{margin:8px 0;padding-left:22px;}
.report li{margin:3px 0;}
.report strong{font-weight:600;}
.report a{color:var(--accent);text-decoration:none;}
.report a:hover{text-decoration:underline;}
.report blockquote{margin:10px 0;padding:4px 14px;border-left:3px solid var(--border);color:var(--fg-2);}
.report code{font-family:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;font-size:13px;
  background:var(--code-bg);padding:1px 6px;border-radius:5px;}
.report pre{background:var(--code-bg);padding:12px 14px;border-radius:10px;overflow-x:auto;margin:10px 0;}
.report pre code{background:none;padding:0;font-size:13px;}
.report hr{border:none;border-top:1px solid var(--border);margin:18px 0;}
.report table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13.5px;}
.report th,.report td{border:1px solid var(--border);padding:7px 10px;text-align:left;}
.report th{background:var(--code-bg);font-weight:600;}
.report tr:nth-child(even) td{background:rgba(0,0,0,.015);}
.foot{margin-top:24px;padding-top:14px;border-top:1px solid var(--border);color:var(--fg-3);font-size:11.5px;text-align:center;}
@media print{
  body{background:#fff;padding:0;font-size:12pt;}
  .paper{box-shadow:none;border-radius:0;max-width:none;padding:24px;}
  .chart-card{background:#fff !important;border:1px solid #ccc;}
  .foot{display:none;}
  .report h1{font-size:18pt;}
}
"""

_HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="paper">
{hero_html}  <hr class="divider">
  <article class="report">
{body}
  </article>
{chart_html}  <footer class="foot">由 职迹 WorkTrace 生成 · {generated_at}</footer>
</div>
</body>
</html>
"""


def render_report_html(
    markdown_text: str,
    title: str,
    subtitle: str = "",
    time_dist: list[dict] | None = None,
) -> str:
    """把报告 Markdown 渲染成自包含的单文件 HTML（卡片化 + 可选时间分布环形图）。

    Args:
        markdown_text: 报告 Markdown 原文（日报/周报/月报）。
        title: 浏览器标签标题（同时作为 Hero 大标题）。
        subtitle: 顶部副标题行，如「模型 glm-4.5-flash · 生成于 2026-06-22 20:38」；空则不渲染。
        time_dist: 时间分布数据 [{"category","minutes","percent"}, ...]；非空时在正文上方插入环形图卡片。

    Returns:
        完整 HTML 字符串（内联 CSS/SVG，无外部依赖）。
    """
    if _md is None:
        raise RuntimeError("缺少 markdown 库，请运行: pip install markdown")

    body = _md.markdown(
        markdown_text or "",
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    body = _inject_h2_icons(body)

    # Hero：用 title 做大标题（div，避免与 markdown 的 h1 语义/样式冲突）
    hero_parts = [
        '  <div class="hero">',
        '    <span class="meta-pill">职迹报告</span>',
        f'    <div class="report-title">{html.escape(title)}</div>',
    ]
    if subtitle:
        hero_parts.append(f'    <div class="meta">{html.escape(subtitle)}</div>')
    hero_parts.append('  </div>')
    hero_html = "\n".join(hero_parts) + "\n"

    # 图表卡（time_dist 非空才渲染）
    chart_html = ""
    if time_dist:
        svg = render_donut_svg(time_dist)
        if svg:
            chart_html = (
                '  <div class="chart-card">\n'
                '    <div class="chart-title">📊 时间分布</div>\n'
                f'    {svg}\n'
                '  </div>\n'
            )

    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        css=_REPORT_CSS,
        hero_html=hero_html,
        chart_html=chart_html,
        body=body,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
