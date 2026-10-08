"""腾讯文档公开链接的只读文本提取。

仅接受 docs.qq.com 的 HTTPS 链接；不携带浏览器 Cookie，也不支持需要登录的文档。
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import re

import httpx

_ALLOWED_HOST = "docs.qq.com"
_MAX_BYTES = 2 * 1024 * 1024
_MAX_CHARS = 120_000


class TencentDocError(ValueError):
    pass


_TITLE_HEADERS = {"待办", "待办事项", "任务", "任务名称", "任务内容", "事项", "工作内容", "工作事项", "内容"}
_PROJECT_HEADERS = {"项目名称", "项目", "项目名", "产品名称"}
_STATUS_HEADERS = {"状态", "进度", "完成状态"}
_PRIORITY_HEADERS = {"优先级", "重要程度", "紧急程度"}
_DUE_HEADERS = {"截止日期", "计划完成日期", "完成日期", "截止时间", "计划完成时间", "到期日", "交付日期"}
_NOTE_HEADERS = {"备注", "说明", "任务说明", "详细说明"}
_ASSIGNEE_HEADERS = {"安排给了谁", "安排给谁", "对接人", "负责人", "执行人"}
_EMAIL_DATE_HEADERS = {"邮件日期", "邮件时间", "日期"}
_SENDER_HEADERS = {"发件人", "发送人"}
_RECIPIENT_HEADERS = {"收件人", "接收人"}
_DONE_VALUES = {"已完成", "完成", "done", "closed", "取消", "已取消"}
_PRIORITY_MAP = {
    "紧急": "urgent", "非常高": "urgent", "urgent": "urgent",
    "高": "high", "重要": "high", "high": "high",
    "低": "low", "不重要": "low", "low": "low",
}


def validate_tencent_doc_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST or not parsed.path:
        raise TencentDocError("请输入公开的 https://docs.qq.com/... 腾讯文档链接")
    return value


def fetch_public_text(url: str) -> str:
    """获取公开文档页面中的可见文本，不发送账号 Cookie。"""
    current = validate_tencent_doc_url(url)
    headers = {"User-Agent": "WorkTrace/4.3 TencentDocImporter"}
    with httpx.Client(timeout=15, follow_redirects=False, headers=headers) as client:
        for _ in range(4):
            response = client.get(current)
            if response.is_redirect:
                target = response.headers.get("location", "")
                current = validate_tencent_doc_url(urljoin(current, target))
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "html" not in content_type and "text" not in content_type:
                raise TencentDocError("该链接未返回可读取的文档页面")
            body = response.content
            if len(body) > _MAX_BYTES:
                raise TencentDocError("文档过大，最多支持读取 2 MB")
            html = body.decode(response.encoding or "utf-8", errors="replace")
            # 腾讯智能表把单元格绘制在前端画布中，普通可见文本不包含表头和数据。
            # 同时保留两种来源，兼容普通文档与智能表。
            text = _html_to_text(html)
            canvas_text = _smart_sheet_canvas_to_text(html)
            if canvas_text:
                text = f"{text}\n{canvas_text}".strip()
            if len(text) < 20:
                raise TencentDocError("未能读取文档正文；请确认链接公开且无需登录")
            return text[:_MAX_CHARS]
    raise TencentDocError("腾讯文档重定向次数过多")


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1
        elif tag in {"p", "div", "li", "br", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag in {"td", "th"}:
            # 让静态公开表格保留列边界，后续可按表头逐行导入，而不是交给 AI 猜测。
            self.parts.append("\t")

    def handle_data(self, data):
        if not self._hidden_depth:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def _smart_sheet_canvas_to_text(html: str) -> str:
    """将腾讯智能表的画布绘制指令还原为带制表符的表格文本。

    公开智能表会把每个单元格的文字和坐标嵌在页面脚本里，例如
    ``[\"q\",[\"待办\",714,19]]``。这不是完整 JSON，因此按文本和坐标
    轻量解析；只有找到任务列时才返回，避免把无关页面文案误当表格。
    """
    points: list[tuple[str, int, int]] = []
    pattern = re.compile(r'\["((?:\\.|[^"\\])*)",\s*(-?\d+),\s*(-?\d+)\]')
    for raw, x, y in pattern.findall(html):
        value = raw.replace(r"\\\"", '"').replace(r"\\n", " ").replace(r"\\t", " ").strip()
        if value:
            points.append((value, int(x), int(y)))

    if not points:
        return ""

    normalized_titles = {re.sub(r"\s+", "", name).lower() for name in _TITLE_HEADERS}
    header_aliases = normalized_titles | _PROJECT_HEADERS | _STATUS_HEADERS | _PRIORITY_HEADERS | _DUE_HEADERS | _NOTE_HEADERS | _ASSIGNEE_HEADERS | _EMAIL_DATE_HEADERS | _SENDER_HEADERS | _RECIPIENT_HEADERS
    headers = [
        (value, x, y)
        for value, x, y in points
        if re.sub(r"\s+", "", value).lower() in header_aliases
    ]
    if not any(re.sub(r"\s+", "", value).lower() in normalized_titles for value, _, _ in headers):
        return ""

    # 同名字段优先用最上方的一组，随后按横坐标确定列顺序。
    header_by_name: dict[str, tuple[str, int, int]] = {}
    for header in sorted(headers, key=lambda item: (item[2], item[1])):
        key = re.sub(r"\s+", "", header[0]).lower()
        header_by_name.setdefault(key, header)
    columns = sorted(header_by_name.values(), key=lambda item: item[1])
    if len(columns) < 2:
        return ""

    header_points = {(value, x, y) for value, x, y in columns}
    row_cells: dict[int, dict[int, list[str]]] = {}
    for value, x, y in points:
        if (value, x, y) in header_points:
            continue
        nearest = min(range(len(columns)), key=lambda index: abs(x - columns[index][1]))
        # 文字的绘制起点相对列起点会有十几像素偏移；超出范围的不属于该表。
        if abs(x - columns[nearest][1]) > 40:
            continue
        row_cells.setdefault(y, {}).setdefault(nearest, []).append(value)

    lines = ["\t".join(value for value, _, _ in columns)]
    for y in sorted(row_cells):
        cells = row_cells[y]
        if not any(cells.values()):
            continue
        lines.append("\t".join(" ".join(cells.get(index, [])) for index in range(len(columns))))
    # 至少要有一行内容，避免只有表头时被视为成功导入。
    return "\n".join(lines) if len(lines) > 1 else ""


def extract_todo_table(text: str) -> tuple[list[dict], dict]:
    """从带表头的腾讯表格文本确定性提取待办。

    返回 ``(todos, diagnostics)``。只有识别到任务列才返回待办，避免把正文或
    看板标题误当任务。已完成/取消行跳过；日期只接受 YYYY-MM-DD（可兼容
    YYYY/MM/DD、YYYY.MM.DD）。
    """
    rows = []
    for raw in (text or "").splitlines():
        cells = [cell.strip() for cell in re.split(r"\t+", raw.strip())]
        if len(cells) >= 2 and any(cells):
            rows.append(cells)
    diagnostics = {"table_rows": max(0, len(rows) - 1), "recognized_columns": [], "skipped_completed": 0}
    if len(rows) < 2:
        return [], diagnostics

    headers = [re.sub(r"\s+", "", cell).lower() for cell in rows[0]]

    def find_index(aliases: set[str]) -> int | None:
        for index, header in enumerate(headers):
            if header in aliases:
                return index
        return None

    title_index = find_index(_TITLE_HEADERS)
    if title_index is None:
        return [], diagnostics
    status_index = find_index(_STATUS_HEADERS)
    priority_index = find_index(_PRIORITY_HEADERS)
    due_index = find_index(_DUE_HEADERS)
    note_index = find_index(_NOTE_HEADERS)
    project_index = find_index(_PROJECT_HEADERS)
    assignee_index = find_index(_ASSIGNEE_HEADERS)
    email_date_index = find_index(_EMAIL_DATE_HEADERS)
    sender_index = find_index(_SENDER_HEADERS)
    recipient_index = find_index(_RECIPIENT_HEADERS)
    columns = {"任务": title_index, "项目": project_index, "状态": status_index, "优先级": priority_index, "截止日期": due_index, "备注": note_index, "安排对象": assignee_index}
    diagnostics["recognized_columns"] = [name for name, index in columns.items() if index is not None]

    def cell(row: list[str], index: int | None) -> str:
        return row[index].strip() if index is not None and index < len(row) else ""

    todos = []
    for row in rows[1:]:
        title = cell(row, title_index)
        if not title:
            continue
        status = cell(row, status_index)
        if status.lower() in _DONE_VALUES or ("已完成" in status and "待" not in status) or ("已验证通过" in status and "待" not in status):
            diagnostics["skipped_completed"] += 1
            continue
        due = cell(row, due_index).replace("/", "-").replace(".", "-")
        if not re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", due):
            due = ""
        elif due:
            year, month, day = due.split("-")
            due = f"{year}-{int(month):02d}-{int(day):02d}"
        priority = _PRIORITY_MAP.get(cell(row, priority_index).lower(), "normal")
        context = []
        for label, value in (("项目", cell(row, project_index)), ("邮件日期", cell(row, email_date_index)), ("状态", status), ("备注", cell(row, note_index)), ("发件人", cell(row, sender_index)), ("收件人", cell(row, recipient_index))):
            if value:
                context.append(f"{label}：{value}")
        todos.append({"title": title[:200], "priority": priority, "due_date": due, "note": "\n".join(context), "contact_person": cell(row, assignee_index)[:100]})
    return todos, diagnostics
