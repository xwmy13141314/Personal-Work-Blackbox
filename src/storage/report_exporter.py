"""报告导出器：将报告 Markdown 渲染为自包含的单文件 HTML。

设计目标（契合用户偏好）：
- 单文件内联 CSS，无外部依赖，可离线打开、可直接微信/邮件发送；
- 样式对齐前端报告卡片观感（白底卡片、系统字体、中文行距优化）；
- 带 @media print，浏览器直接 Ctrl+P 也能打出排版干净的 PDF。
"""

from __future__ import annotations

import html
from datetime import datetime

try:
    import markdown as _md  # type: ignore
except ImportError:  # pragma: no cover - 依赖缺失时给清晰报错
    _md = None


# 内联 CSS（对齐前端报告卡片观感）
_REPORT_CSS = """
:root{--fg:#1d1d1f;--fg-2:#6e6e73;--fg-3:#9a9a9f;--bg:#f5f5f7;--card:#fff;
  --border:rgba(0,0,0,.1);--accent:#0071e3;--code-bg:rgba(0,0,0,.05);}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px;line-height:1.7;padding:32px 16px;}
.paper{max-width:820px;margin:0 auto;background:var(--card);border-radius:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.06),0 8px 30px rgba(0,0,0,.06);padding:40px 48px 32px;}
.meta{color:var(--fg-2);font-size:12.5px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border);}
.report h1{font-size:22px;font-weight:600;margin:8px 0 12px;line-height:1.3;}
.report h2{font-size:17px;font-weight:600;margin:22px 0 8px;}
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
  .paper{box-shadow:none;border-radius:0;max-width:none;padding:0;}
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
{meta_html}  <article class="report">
{body}
  </article>
  <footer class="foot">由 职迹 WorkTrace 生成 · {generated_at}</footer>
</div>
</body>
</html>
"""


def render_report_html(markdown_text: str, title: str, subtitle: str = "") -> str:
    """把报告 Markdown 渲染成自包含的单文件 HTML。

    Args:
        markdown_text: 报告 Markdown 原文
        title: 浏览器标签标题（同时 <title>）
        subtitle: 顶部副标题行，如「模型 glm-4.5-flash · 生成于 2026-06-22 20:38」；空则不渲染

    Returns:
        完整 HTML 字符串（内联 CSS，无外部依赖）
    """
    if _md is None:
        raise RuntimeError("缺少 markdown 库，请运行: pip install markdown")

    body = _md.markdown(
        markdown_text or "",
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    meta_html = (
        f'  <div class="meta">{html.escape(subtitle)}</div>\n'
        if subtitle
        else ""
    )
    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        css=_REPORT_CSS,
        meta_html=meta_html,
        body=body,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
