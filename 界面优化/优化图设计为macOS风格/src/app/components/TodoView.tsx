import { useState, useEffect } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  closestCorners,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Check,
  Plus,
  Zap,
  ChevronDown,
  Pencil,
  Trash2,
  Calendar,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  CheckSquare,
  Bell,
  Download,
  FolderOpen,
  GripVertical,
  ExternalLink,
} from "lucide-react";
import type {
  BlackboxApi,
  Todo,
  TodoStatus,
  TodoPriority,
  TaskStatus,
  TodoStats,
  TodoAdvice,
  CategoryStats,
  ReportType,
} from "@/lib/pywebview";
import { fmtDuration } from "@/app/lib/utils";
import { MiniDonut } from "@/app/components/MiniDonut";

// ==================== 待办看板视图（v4.3） ====================

// 优先级 → 标签 + 左色条（PRD §4.4：urgent 红 / high 橙 / normal 蓝 / low 灰）
const PRI_META: Record<TodoPriority, { label: string; chip: string; bar: string }> = {
  urgent: { label: "紧急", chip: "text-[var(--wt-danger)] bg-[rgba(255,59,48,0.1)]", bar: "#ff3b30" },
  high: { label: "高", chip: "text-[#b76b00] bg-[rgba(255,159,10,0.14)]", bar: "#ff9500" },
  normal: { label: "中", chip: "text-[var(--wt-accent)] bg-[var(--wt-accent-bg)]", bar: "#0071e3" },
  low: { label: "低", chip: "text-[var(--wt-text-muted)] bg-black/[0.06]", bar: "#8e8e93" },
};

// 优先级排序权重（PRD §4.4：优先级 高→中→低 主序，同优先级按 sort_order 微调）
const PRIORITY_RANK: Record<TodoPriority, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
const byPriorityThenOrder = (a: Todo, b: Todo) =>
  (PRIORITY_RANK[a.priority] ?? 2) - (PRIORITY_RANK[b.priority] ?? 2) || a.sort_order - b.sort_order;

// 看板三列
const COLUMNS: { key: TodoStatus; label: string; dot: string }[] = [
  { key: "pending", label: "待办", dot: "#8e8e93" },
  { key: "in_progress", label: "进行中", dot: "#0071e3" },
  { key: "done", label: "已完成", dot: "#34c759" },
];

// 来源维度列（P4-B 多维视图；只读分组，不可拖拽改来源）
const SOURCE_COLUMNS: { key: string; label: string; dot: string }[] = [
  { key: "manual", label: "手动", dot: "#8e8e93" },
  { key: "daily_report", label: "日报", dot: "#0071e3" },
  { key: "weekly_report", label: "周报", dot: "#af52de" },
  { key: "monthly_report", label: "月报", dot: "#ff9500" },
];

// 三态复选框循环：pending → in_progress → done → pending
const STATUS_CYCLE: Record<TodoStatus, TodoStatus> = {
  pending: "in_progress",
  in_progress: "done",
  done: "pending",
  cancelled: "pending",
};

// 来源标签 + 报告下钻映射
function sourceMeta(t: Todo): {
  label: string;
  manual: boolean;
  reportType: ReportType | null;
  ref: string;
} {
  if (t.source_type === "manual" || !t.source_type)
    return { label: "手动", manual: true, reportType: null, ref: "" };
  const map: Record<string, { name: string; rt: ReportType }> = {
    daily_report: { name: "日报", rt: "daily" },
    weekly_report: { name: "周报", rt: "weekly" },
    monthly_report: { name: "月报", rt: "monthly" },
  };
  const m = map[t.source_type] ?? { name: "报告", rt: "daily" as ReportType };
  const ref = t.source_ref ? ` ${t.source_ref.slice(5).replace("-", "/")}` : ""; // MM-DD → MM/DD
  return { label: m.name + ref, manual: false, reportType: m.rt, ref: t.source_ref };
}

// 截止日期显示
function dueLabel(due: string, today: string): string | null {
  if (!due) return null;
  if (due === today) return "今天";
  return due.slice(5).replace("-", "/"); // MM/DD
}

export function TodoView({
  api,
  date,
  onOpenReport,
}: {
  api: BlackboxApi | null;
  date: string;
  onOpenReport: (reportType: ReportType, date: string) => void;
}) {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [drafts, setDrafts] = useState<Todo[]>([]);
  const [stats, setStats] = useState<TodoStats>({ total: 0, today_pending: 0, overdue: 0, done: 0 });
  const [loading, setLoading] = useState(true);
  const [draftOpen, setDraftOpen] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [advices, setAdvices] = useState<TodoAdvice[]>([]);
  const [generating, setGenerating] = useState(false);
  const [catStats, setCatStats] = useState<CategoryStats | null>(null);
  const [overdueDismissed, setOverdueDismissed] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err" | null; msg: string; path?: string }>({ kind: null, msg: "" });
  const [draggingId, setDraggingId] = useState<number | null>(null);
  // 多维视图（P4-B §4.1）：status=按状态三列（可拖）/ source=按来源四列（只读分组）
  const [viewMode, setViewMode] = useState<"status" | "source">("status");
  // 新建表单
  const [showAdd, setShowAdd] = useState(false);
  const [addTitle, setAddTitle] = useState("");
  const [addPri, setAddPri] = useState<TodoPriority>("normal");
  const [addDue, setAddDue] = useState("");
  // inline 编辑（草稿与正式共用，按 id 锁定当前编辑行）
  const [editId, setEditId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const today = date;

  const reload = async () => {
    if (!api) return;
    const [all, s, ad, cat] = await Promise.all([
      api.get_todos(null, true),
      api.get_todo_stats().catch(() => ({ total: 0, today_pending: 0, overdue: 0, done: 0 })),
      api.get_todo_advices().catch(() => [] as TodoAdvice[]),
      api.get_category_stats("today", today).catch(() => null),
    ]);
    // cancelled 默认隐藏（PRD §4.1），不进看板
    setTodos(all.filter((t) => !t.is_draft && t.status !== "cancelled"));
    setDrafts(all.filter((t) => t.is_draft));
    setStats(s);
    setAdvices(ad);
    setCatStats(cat);
    setLoading(false);
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  // 从当前日期日报提取待办（任务模式 + 轮询）
  const extract = async () => {
    if (!api || extracting) return;
    setExtracting(true);
    setNotice({ kind: null, msg: "" });
    try {
      const { task_id } = await api.extract_todos("daily", today);
      const MAX_POLL = 120;
      const poll = async (attempt: number) => {
        if (attempt >= MAX_POLL) {
          setExtracting(false);
          setNotice({ kind: "err", msg: "提取超时：已等待超过 2 分钟仍未完成" });
          return;
        }
        const t: TaskStatus | null = await api.get_task_status(task_id);
        if (!t) {
          setExtracting(false);
          setNotice({ kind: "err", msg: "任务不存在" });
          return;
        }
        if (t.status === "done") {
          await reload();
          setExtracting(false);
          setDraftOpen(true);
          const n = t.result?.extracted ?? 0;
          setNotice({
            kind: n > 0 ? "ok" : "err",
            msg:
              n > 0
                ? `已提取 ${n} 条待办到草稿区，请确认`
                : "今日报告未提取到待办（可能当日日报尚未生成或无可执行项）",
          });
        } else if (t.status === "failed") {
          setExtracting(false);
          setNotice({ kind: "err", msg: t.error || "提取失败" });
        } else {
          setTimeout(() => poll(attempt + 1), 1000);
        }
      };
      setTimeout(() => poll(1), 1000);
    } catch (e) {
      setExtracting(false);
      setNotice({ kind: "err", msg: String(e) });
    }
  };

  // AI 推进建议：结合当日活动给未完成待办提建议（任务模式 + 轮询，P2 §4.6）
  const generateAdvices = async () => {
    if (!api || generating) return;
    setGenerating(true);
    setNotice({ kind: null, msg: "" });
    try {
      const { task_id } = await api.generate_todo_advices(today);
      const MAX_POLL = 120;
      const poll = async (attempt: number) => {
        if (attempt >= MAX_POLL) {
          setGenerating(false);
          setNotice({ kind: "err", msg: "生成建议超时" });
          return;
        }
        const t: TaskStatus | null = await api.get_task_status(task_id);
        if (!t) { setGenerating(false); return; }
        if (t.status === "done") {
          await reload();
          setGenerating(false);
          const n = t.result?.generated ?? 0;
          setNotice({
            kind: n > 0 ? "ok" : "err",
            msg: n > 0 ? `已生成 ${n} 条推进建议` : "暂无新的推进建议（当日活动不足以判断）",
          });
        } else if (t.status === "failed") {
          setGenerating(false);
          setNotice({ kind: "err", msg: t.error || "生成失败" });
        } else {
          setTimeout(() => poll(attempt + 1), 1000);
        }
      };
      setTimeout(() => poll(1), 1000);
    } catch (e) {
      setGenerating(false);
      setNotice({ kind: "err", msg: String(e) });
    }
  };

  // 采纳建议：start→进行中 / progress→推进进度（联动 done）/ stall→仅标记
  const applyAdvice = async (id: number) => {
    if (!api) return;
    const r = await api.apply_todo_advice(id);
    if (r.ok) {
      await reload();
      setNotice({ kind: "ok", msg: "已采纳建议并更新待办" });
    } else {
      setNotice({ kind: "err", msg: r.error || "采纳失败" });
    }
  };

  const dismissAdvice = async (id: number) => {
    if (!api) return;
    await api.dismiss_todo_advice(id);
    setAdvices((prev) => prev.filter((a) => a.id !== id));
  };

  // 待办提醒检查（手动触发；后端每小时自动跑一次，P3 §4.9）
  const notifyCheck = async () => {
    if (!api) return;
    setNotice({ kind: null, msg: "" });
    try {
      const r = await api.check_todo_notifications();
      if (r.ok) {
        setNotice({ kind: "ok", msg: r.notified && r.notified > 0 ? `已发送 ${r.notified} 条桌面提醒` : "暂无逾期/即将到期的待办" });
      } else {
        setNotice({ kind: "err", msg: r.error || "检查失败" });
      }
    } catch (e) {
      setNotice({ kind: "err", msg: String(e) });
    }
  };

  // 导出表格（CSV；弹保存对话框选位置，Excel / 飞书多维表格可直接打开）
  const exportCsv = async () => {
    if (!api) return;
    setNotice({ kind: null, msg: "" });
    const r = await api.export_todos(null, true);
    if (r.cancelled) return; // 用户取消保存对话框，静默
    setNotice(
      r.ok
        ? { kind: "ok", msg: `已导出 ${r.count ?? ""} 条待办到：${r.path}`, path: r.path }
        : { kind: "err", msg: r.error || "导出失败" },
    );
  };
  // 在资源管理器中定位导出的文件
  const openFolder = async () => {
    if (!api || !notice.path) return;
    await api.reveal_path(notice.path);
  };

  // 三态切换（点卡片复选框）
  const cycleStatus = async (t: Todo) => {
    if (!api) return;
    await api.update_todo(t.id, { status: STATUS_CYCLE[t.status] });
    await reload();
  };

  // 调进度（100% 自动联动完成由后端处理）
  const setProgress = async (t: Todo, v: number) => {
    if (!api) return;
    await api.update_todo(t.id, { progress: v });
    await reload();
  };

  // 逾期待办：due_date < 今天 且 pending（P3 §4.8，带入今日继续跟进）
  const overdueTodos = todos.filter((t) => t.status === "pending" && t.due_date && t.due_date < today);
  const postponeOverdue = async () => {
    if (!api || overdueTodos.length === 0) return;
    await Promise.all(overdueTodos.map((t) => api.update_todo(t.id, { due_date: today })));
    setOverdueDismissed(true);
    await reload();
    setNotice({ kind: "ok", msg: `已将 ${overdueTodos.length} 项逾期待办顺延到今日` });
  };

  // 草稿：采纳 / 丢弃 / 全部采纳
  const adopt = async (id: number) => {
    if (!api) return;
    await api.adopt_todos([id]);
    await reload();
  };
  const adoptAll = async () => {
    if (!api || !drafts.length) return;
    await api.adopt_todos(drafts.map((d) => d.id));
    await reload();
  };
  const drop = async (id: number) => {
    if (!api) return;
    await api.delete_todo(id);
    await reload();
  };

  // 卡片删除
  const remove = async (id: number) => {
    if (!api) return;
    await api.delete_todo(id);
    await reload();
  };

  // 新建
  const submitAdd = async () => {
    if (!api || !addTitle.trim()) return;
    await api.add_todo(addTitle.trim(), addPri, addDue, "");
    setAddTitle("");
    setAddPri("normal");
    setAddDue("");
    setShowAdd(false);
    await reload();
  };

  // inline 编辑保存
  const startEdit = (t: Todo) => {
    setEditId(t.id);
    setEditTitle(t.title);
  };
  const saveEdit = async () => {
    if (!api || editId == null) return;
    if (editTitle.trim()) await api.update_todo(editId, { title: editTitle.trim() });
    setEditId(null);
    setEditTitle("");
    await reload();
  };

  // ===== 拖拽 =====
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  // 来源视图为只读分组，禁用拖拽（P4-B）
  const dragSensors = viewMode === "status" ? sensors : [];

  const onDragStart = (e: DragStartEvent) => setDraggingId(e.active.id as number);

  const onDragEnd = async (e: DragEndEvent) => {
    const { active, over } = e;
    setDraggingId(null);
    if (viewMode !== "status" || !api || !over) return;
    const activeId = active.id as number;
    const overId = over.id;
    const activeTodo = todos.find((t) => t.id === activeId);
    if (!activeTodo) return;

    // 确定 over 所在列 status：over 为列容器 id（空列/列空白）或某卡片 id
    let newStatus: TodoStatus;
    if (COLUMNS.some((c) => c.key === overId)) {
      newStatus = overId as TodoStatus;
    } else {
      const overTodo = todos.find((t) => t.id === overId);
      if (!overTodo) return;
      newStatus = overTodo.status;
    }

    // 目标列其余卡片（排除被拖项），按 sort_order 排
    const colItems = todos
      .filter((t) => t.status === newStatus && t.id !== activeId)
      .sort(byPriorityThenOrder);

    // 插入位置：over 为列容器 → 末尾；否则 over 在 colItems 中的索引
    let insertIdx = colItems.length;
    if (!COLUMNS.some((c) => c.key === overId)) {
      const overIdx = colItems.findIndex((t) => t.id === overId);
      if (overIdx >= 0) insertIdx = overIdx;
    }

    // 组新列顺序，按 1..N 重排 sort_order（整数重排，简单可靠；本地数据量小无性能问题）
    const newCol = [...colItems];
    newCol.splice(insertIdx, 0, activeTodo);
    const updates = newCol.map((t, i) => ({ id: t.id, sort_order: i + 1 }));

    const crossCol = newStatus !== activeTodo.status;
    if (crossCol) await api.update_todo(activeId, { status: newStatus });
    if (updates.length) await api.reorder_todos(updates);
    await reload();
  };

  const draggingTodo = draggingId != null ? todos.find((t) => t.id === draggingId) ?? null : null;

  // 多维视图（P4-B）：状态视图按 status 分列（可拖），来源视图按 source_type 分列（只读）
  const activeColumns = viewMode === "status" ? COLUMNS : SOURCE_COLUMNS;
  const colKeyOf = (t: Todo) => (viewMode === "status" ? t.status : t.source_type) as string;
  // 列内卡片（按 sort_order）
  const colOf = (key: string) => todos.filter((t) => colKeyOf(t) === key).sort(byPriorityThenOrder);

  // 统计卡片
  const statCards: { label: string; value: number; color: string }[] = [
    { label: "总任务", value: stats.total, color: "var(--wt-text)" },
    { label: "今日待办", value: stats.today_pending, color: "var(--wt-accent)" },
    { label: "已延期", value: stats.overdue, color: "var(--wt-danger)" },
    { label: "已完成", value: stats.done, color: "var(--wt-success)" },
  ];

  // 今日工作实况（P3 §4.7：复用 category_stats，纯 DB 无 LLM；与任务统计同屏看「该做什么 + 实际做了什么」）
  const DONUT_PALETTE = ["#0071e3", "#34c759", "#ff9500", "#af52de", "#ff3b30", "#5856d6"];
  const totalActive = catStats?.total_active ?? 0;
  const catSegments = (catStats && totalActive > 0)
    ? [...catStats.items]
        .sort((a, b) => b.active_seconds - a.active_seconds)
        .slice(0, 5)
        .map((c, i) => ({ label: c.category, icon: c.icon, value: c.active_seconds, color: DONUT_PALETTE[i % DONUT_PALETTE.length] }))
    : [];

  return (
    <>
      {/* Toolbar */}
      <div
        className="flex items-center gap-2 px-5 h-11 shrink-0 border-b border-black/[0.07]"
        style={{ background: "rgba(245,245,247,0.8)", backdropFilter: "blur(20px)" }}
      >
        <p className="text-[13px] font-semibold text-[var(--wt-text)]">待办看板</p>
        <span className="text-[10px] text-[var(--wt-text-muted)]">
          {stats.today_pending + stats.overdue} 条未完成
          {drafts.length ? `，${drafts.length} 条待确认` : ""}
        </span>

        <div className="flex-1" />

        {/* 待确认（草稿）按钮 */}
        <button
          onClick={() => drafts.length && setDraftOpen((v) => !v)}
          disabled={drafts.length === 0}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all disabled:opacity-50 ${
            drafts.length
              ? "bg-[rgba(255,159,10,0.12)] text-[#b76b00] hover:bg-[rgba(255,159,10,0.2)]"
              : "bg-black/[0.06] text-[var(--wt-text-muted)]"
          }`}
        >
          待确认
          {drafts.length > 0 && (
            <span className="bg-[var(--wt-danger)] text-white text-[9px] px-1 rounded-full font-bold leading-[1.4]">
              {drafts.length}
            </span>
          )}
        </button>

        {/* 从报告提取 */}
        <button
          onClick={extract}
          disabled={extracting}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-60 transition-all"
        >
          {extracting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
          {extracting ? "提取中" : "从报告提取"}
        </button>

        {/* AI 推进建议（P2 §4.6） */}
        <button
          onClick={generateAdvices}
          disabled={generating}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-[rgba(175,82,222,0.12)] text-[#af52de] hover:bg-[rgba(175,82,222,0.2)] disabled:opacity-60 transition-all"
          title="结合当日活动，AI 为未完成待办提出推进建议"
        >
          {generating ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
          {generating ? "生成中" : "AI 建议"}
        </button>

        {/* 待办提醒检查（P3 §4.9，手动触发；后端每小时自动） */}
        <button
          onClick={notifyCheck}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] transition-all"
          title="检查逾期/即将到期待办并发桌面提醒"
        >
          <Bell className="w-3 h-3" /> 提醒
        </button>

        {/* 新建 */}
        <button
          onClick={() => setShowAdd((v) => !v)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 transition-all"
        >
          <Plus className="w-3 h-3" /> 新建待办
        </button>

        {/* 导出表格 */}
        <button
          onClick={exportCsv}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] transition-all"
          title="导出为 CSV（Excel / 飞书多维表格可用）"
        >
          <Download className="w-3 h-3" /> 导出
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {/* 逾期待办提示 + 一键顺延（P3 §4.8） */}
        {overdueTodos.length > 0 && !overdueDismissed && (
          <div className="rounded-xl border border-[rgba(255,59,48,0.25)] bg-[rgba(255,59,48,0.05)] p-3 flex items-center gap-3">
            <AlertTriangle className="w-4 h-4 text-[var(--wt-danger)] shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-semibold text-[var(--wt-text)]">{overdueTodos.length} 项待办已逾期，带入今日继续跟进</p>
              <p className="text-[11px] text-[var(--wt-text-secondary)] truncate">
                {overdueTodos.slice(0, 3).map((t) => t.title).join("、")}
                {overdueTodos.length > 3 ? " 等" : ""}
              </p>
            </div>
            <button
              onClick={postponeOverdue}
              className="shrink-0 px-3 py-1 rounded-full text-[11px] font-medium text-white bg-[var(--wt-danger)] hover:brightness-110 transition-all"
            >
              顺延到今日
            </button>
            <button
              onClick={() => setOverdueDismissed(true)}
              className="shrink-0 px-2 py-1 rounded-full text-[11px] font-medium text-[var(--wt-text-muted)] hover:bg-black/[0.06] transition-all"
            >
              稍后
            </button>
          </div>
        )}

        {/* 统计卡片栏（4 指标，PRD §4.7） */}
        <div className="grid grid-cols-4 gap-2.5">
          {statCards.map((c) => (
            <div
              key={c.label}
              className="rounded-xl border border-black/[0.07] bg-white/70 px-3.5 py-2.5"
              style={{ backdropFilter: "blur(8px)" }}
            >
              <p className="text-[10.5px] text-[var(--wt-text-muted)]">{c.label}</p>
              <p className="text-[22px] font-semibold leading-tight mt-0.5" style={{ color: c.color }}>
                {c.value}
              </p>
            </div>
          ))}
        </div>

        {/* 今日工作实况（P3 §4.7：任务统计旁叠加当日采集活动） */}
        <div className="rounded-xl border border-black/[0.07] bg-white/70 p-3 flex items-center gap-4" style={{ backdropFilter: "blur(8px)" }}>
          <MiniDonut
            segments={catSegments}
            size={72}
            stroke={10}
            center={
              totalActive > 0 ? (
                <>
                  <p className="text-[13px] font-bold text-[var(--wt-text)] leading-none">{fmtDuration(totalActive).replace(" ", "")}</p>
                  <p className="text-[9px] text-[var(--wt-text-muted)] mt-0.5">活跃</p>
                </>
              ) : (
                <p className="text-[10px] text-[var(--wt-text-muted)]">暂无</p>
              )
            }
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-[12px] font-semibold text-[var(--wt-text)]">今日工作实况</p>
              <span className="text-[10px] text-[var(--wt-text-muted)]">{catSegments.length} 个类别</span>
            </div>
            {catSegments.length > 0 ? (
              <div className="space-y-1">
                {catSegments.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
                    <span className="shrink-0 text-[11px]">{s.icon}</span>
                    <span className="text-[var(--wt-text-secondary)] truncate flex-1">{s.label}</span>
                    <span className="text-[var(--wt-text-muted)] shrink-0 tabular-nums">{fmtDuration(s.value)}</span>
                    <span className="text-[var(--wt-text-muted)] shrink-0 w-9 text-right tabular-nums">{Math.round((s.value / totalActive) * 100)}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-[var(--wt-text-muted)] py-1.5">今日暂无采集活动</p>
            )}
          </div>
        </div>

        {/* AI 推进建议（P2 §4.6；日报后自动生成，也可手动触发） */}
        {advices.length > 0 && (
          <div className="rounded-xl border border-[rgba(175,82,222,0.2)] bg-[rgba(175,82,222,0.04)] p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-[#af52de]" />
              <p className="text-[12px] font-semibold text-[var(--wt-text)]">推进建议</p>
              <span className="text-[10px] text-[var(--wt-text-muted)]">基于当日活动，可采纳或忽略</span>
            </div>
            {advices.map((a) => (
              <div key={a.id} className="flex items-start gap-2.5 rounded-lg bg-white/70 px-3 py-2">
                <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[9.5px] font-semibold ${
                  a.suggestion_type === "start" ? "bg-[var(--wt-accent-bg)] text-[var(--wt-accent)]"
                  : a.suggestion_type === "progress" ? "bg-[rgba(52,199,89,0.14)] text-[#1d9b3e]"
                  : "bg-black/[0.06] text-[var(--wt-text-muted)]"
                }`}>
                  {a.suggestion_type === "start" ? "开始" : a.suggestion_type === "progress" ? "推进" : "卡住"}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-medium text-[var(--wt-text)] truncate">{a.todo_title}</p>
                  <p className="text-[11px] text-[var(--wt-text-secondary)] break-words">
                    {a.reason}
                    {a.suggestion_type === "progress" && a.suggested_progress !== null
                      && `（建议进度 ${a.suggested_progress}%）`}
                  </p>
                </div>
                <button
                  onClick={() => applyAdvice(a.id)}
                  className="shrink-0 px-2 py-0.5 rounded-full text-[10.5px] font-medium text-white bg-[var(--wt-accent)] hover:brightness-110 transition-all"
                >
                  采纳
                </button>
                <button
                  onClick={() => dismissAdvice(a.id)}
                  className="shrink-0 px-2 py-0.5 rounded-full text-[10.5px] font-medium text-[var(--wt-text-muted)] hover:bg-black/[0.06] transition-all"
                >
                  忽略
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 提取结果提示 */}
        {notice.kind && (
          <div
            className={`flex items-center gap-2 rounded-xl border p-3 ${
              notice.kind === "ok" ? "border-green-200 bg-green-50/70" : "border-orange-200 bg-orange-50/70"
            }`}
          >
            {notice.kind === "ok" ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5 text-orange-500 shrink-0" />
            )}
            <p className={`text-[11.5px] break-all ${notice.kind === "ok" ? "text-green-700" : "text-orange-700"}`}>
              {notice.msg}
            </p>
            {notice.kind === "ok" && notice.path && (
              <button
                onClick={openFolder}
                className="ml-auto shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium text-green-700 border border-green-300 bg-white hover:bg-green-50 transition-all"
              >
                <FolderOpen className="w-3 h-3" /> 打开文件夹
              </button>
            )}
          </div>
        )}

        {/* 新建表单（inline 展开） */}
        {showAdd && (
          <div
            className="rounded-xl border border-black/10 bg-white/70 p-3 space-y-2"
            style={{ backdropFilter: "blur(8px)" }}
          >
            <input
              autoFocus
              value={addTitle}
              onChange={(e) => setAddTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitAdd()}
              placeholder="输入待办内容..."
              className="w-full bg-transparent outline-none text-[12px] text-[var(--wt-text)] placeholder:text-[var(--wt-text-muted)]"
            />
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={addPri}
                onChange={(e) => setAddPri(e.target.value as TodoPriority)}
                className="text-[11px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none"
              >
                <option value="urgent">紧急</option>
                <option value="high">高</option>
                <option value="normal">中</option>
                <option value="low">低</option>
              </select>
              <input
                type="date"
                value={addDue}
                onChange={(e) => setAddDue(e.target.value)}
                className="text-[11px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none text-[var(--wt-text-secondary)]"
              />
              <div className="flex-1" />
              <button onClick={() => setShowAdd(false)} className="text-[11px] text-[var(--wt-text-muted)] px-2 py-0.5">
                取消
              </button>
              <button
                onClick={submitAdd}
                className="text-[11px] bg-[var(--wt-accent)] text-white px-3 py-0.5 rounded-full hover:brightness-110"
              >
                添加
              </button>
            </div>
          </div>
        )}

        {/* 草稿确认区（仅有草稿时显示） */}
        {drafts.length > 0 && (
          <div
            className="rounded-xl border"
            style={{ borderColor: "rgba(255,159,10,0.35)", background: "rgba(255,159,10,0.06)" }}
          >
            <div
              className="flex items-center gap-2 px-3.5 py-2.5 cursor-pointer"
              onClick={() => setDraftOpen((v) => !v)}
            >
              <div
                className="w-[18px] h-[18px] rounded-md flex items-center justify-center shrink-0"
                style={{ background: "linear-gradient(135deg,#0071e3,#af52de)" }}
              >
                <Sparkles className="w-2.5 h-2.5 text-white" />
              </div>
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-[var(--wt-text)]">
                  AI 提取了 {drafts.length} 条待办待确认
                </p>
                <p className="text-[11px] text-[var(--wt-text-muted)]">
                  来源：{sourceMeta(drafts[0]).label} · 请确认后入库
                </p>
              </div>
              <div className="ml-auto flex items-center gap-1 text-[11px] text-[var(--wt-text-muted)]">
                {draftOpen ? "收起" : "展开"}
                <ChevronDown className={`w-3 h-3 transition-transform ${draftOpen ? "rotate-180" : ""}`} />
              </div>
            </div>
            {draftOpen && (
              <div className="px-3.5 pb-3 flex flex-col gap-1.5">
                {drafts.map((d) => (
                  <DraftRow
                    key={d.id}
                    todo={d}
                    editing={editId === d.id}
                    editTitle={editTitle}
                    onStartEdit={() => startEdit(d)}
                    onEditChange={setEditTitle}
                    onSaveEdit={saveEdit}
                    onCancelEdit={() => setEditId(null)}
                    onAdopt={() => adopt(d.id)}
                    onDrop={() => drop(d.id)}
                  />
                ))}
                <button
                  onClick={adoptAll}
                  className="self-start flex items-center gap-1 px-3 py-1 rounded-md text-[10.5px] font-medium text-[var(--wt-success)] border border-[rgba(52,199,89,0.4)] hover:bg-[var(--wt-success)] hover:text-white transition-all"
                >
                  <Check className="w-2.5 h-2.5" /> 全部采纳
                </button>
              </div>
            )}
          </div>
        )}

        {/* 视图维度切换（P4-B §4.1） */}
        <div className="flex items-center gap-1 mt-2">
          <span className="text-[11px] text-[var(--wt-text-muted)] mr-1">视图</span>
          {([["status", "按状态"], ["source", "按来源"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setViewMode(k)}
              className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium transition-all ${
                viewMode === k
                  ? "bg-[var(--wt-accent)] text-white"
                  : "bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* 看板 */}
        {loading ? (
          <p className="text-[12px] text-[var(--wt-text-muted)] py-12 text-center">加载中...</p>
        ) : (
          <DndContext
            sensors={dragSensors}
            collisionDetection={closestCorners}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
          >
            <div className={`grid gap-3 mt-2 ${viewMode === "status" ? "grid-cols-3" : "grid-cols-4"}`}>
              {activeColumns.map((col) => (
                <KanbanColumn key={col.key} col={col} count={colOf(col.key).length}>
                  <SortableContext items={colOf(col.key).map((t) => t.id)} strategy={verticalListSortingStrategy}>
                    {colOf(col.key).length ? (
                      <div className="flex flex-col gap-2">
                        {colOf(col.key).map((t) => (
                          <SortableTodoCard
                            key={t.id}
                            todo={t}
                            today={today}
                            editing={editId === t.id}
                            editTitle={editTitle}
                            onStartEdit={() => startEdit(t)}
                            onEditChange={setEditTitle}
                            onSaveEdit={saveEdit}
                            onCancelEdit={() => setEditId(null)}
                            onCycle={() => cycleStatus(t)}
                            onProgressChange={(v) => setProgress(t, v)}
                            onDelete={() => remove(t.id)}
                            onOpenReport={onOpenReport}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="py-6 text-center text-[11px] text-[var(--wt-text-faint)]">
                        拖入或新建
                      </div>
                    )}
                  </SortableContext>
                </KanbanColumn>
              ))}
            </div>

            <DragOverlay dropAnimation={{ duration: 180, easing: "cubic-bezier(0.18,0.67,0.6,1.22)" }}>
              {draggingTodo ? (
                <TodoCardContent
                  todo={draggingTodo}
                  today={today}
                  editing={false}
                  editTitle=""
                  onStartEdit={() => {}}
                  onEditChange={() => {}}
                  onSaveEdit={() => {}}
                  onCancelEdit={() => {}}
                  onCycle={() => {}}
                  onProgressChange={() => {}}
                  onDelete={() => {}}
                  onOpenReport={onOpenReport}
                  overlay
                />
              ) : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </>
  );
}

// ==================== 看板列容器（可 drop，含空列支持） ====================

function KanbanColumn({
  col,
  count,
  children,
}: {
  col: { key: string; label: string; dot: string };
  count: number;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: col.key });
  return (
    <div
      ref={setNodeRef}
      className={`rounded-xl border p-2.5 min-h-[160px] transition-colors ${
        isOver ? "border-[rgba(0,113,227,0.4)] bg-[rgba(0,113,227,0.04)]" : "border-black/[0.07] bg-black/[0.015]"
      }`}
    >
      <div className="flex items-center gap-1.5 px-1 pb-2">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: col.dot }} />
        <p className="text-[12px] font-semibold text-[var(--wt-text-secondary)]">{col.label}</p>
        <span className="text-[10px] font-semibold text-[var(--wt-text-muted)] bg-black/[0.06] px-1.5 py-0.5 rounded-full">
          {count}
        </span>
      </div>
      {children}
    </div>
  );
}

// ==================== 可拖拽卡片（useSortable 包装） ====================

function SortableTodoCard(props: TodoCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: props.todo.id,
  });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <TodoCardContent {...props} />
    </div>
  );
}

// ==================== 卡片内容（纯展示，DragOverlay 复用） ====================

type TodoCardProps = {
  todo: Todo;
  today: string;
  editing: boolean;
  editTitle: string;
  onStartEdit: () => void;
  onEditChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onCycle: () => void;
  onProgressChange: (v: number) => void;
  onDelete: () => void;
  onOpenReport: (reportType: ReportType, date: string) => void;
  overlay?: boolean;
};

function TodoCardContent({
  todo,
  today,
  editing,
  editTitle,
  onStartEdit,
  onEditChange,
  onSaveEdit,
  onCancelEdit,
  onCycle,
  onProgressChange,
  onDelete,
  onOpenReport,
  overlay,
}: TodoCardProps) {
  const pm = PRI_META[todo.priority];
  const sm = sourceMeta(todo);
  const isDone = todo.status === "done";
  const isProg = todo.status === "in_progress";
  const due = dueLabel(todo.due_date, today);
  const overdue = !!todo.due_date && !isDone && todo.due_date < today;

  return (
    <div
      className={`group relative rounded-xl border bg-white/80 overflow-hidden transition-all hover:border-[rgba(0,113,227,0.3)] hover:shadow-sm ${
        overlay ? "shadow-xl rotate-1 cursor-grabbing" : ""
      } ${isDone ? "border-black/[0.06]" : "border-black/10"}`}
      style={{ backdropFilter: "blur(8px)" }}
    >
      {/* 优先级左色条 */}
      <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: pm.bar }} />

      <div className="flex items-start gap-2 pl-2.5 pr-2 py-2.5">
        {/* 三态复选框 */}
        <button
          onClick={onCycle}
          onPointerDown={(e) => e.stopPropagation()}
          className="w-[18px] h-[18px] rounded-full border-[1.6px] flex items-center justify-center shrink-0 mt-0.5 transition-all"
          style={
            isProg
              ? { borderColor: "var(--wt-accent)", background: "conic-gradient(var(--wt-accent) 50%, transparent 50%)" }
              : isDone
              ? { background: "var(--wt-success)", borderColor: "var(--wt-success)" }
              : { borderColor: "var(--wt-text-faint)", background: "transparent" }
          }
          title={`状态：${todo.status}（点击切换）`}
        >
          {isDone && <Check className="w-2.5 h-2.5 text-white" strokeWidth={3} />}
        </button>

        <div className="flex-1 min-w-0">
          {/* 拖拽手柄（视觉提示） */}
          {!editing && (
            <GripVertical
              className="w-3 h-3 text-[var(--wt-text-faint)] opacity-0 group-hover:opacity-60 transition-opacity absolute right-1.5 top-1.5"
              strokeWidth={2.5}
            />
          )}

          {editing ? (
            <input
              autoFocus
              value={editTitle}
              onChange={(e) => onEditChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSaveEdit();
                if (e.key === "Escape") onCancelEdit();
              }}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
              onBlur={onSaveEdit}
              className="w-full bg-transparent outline-none text-[12px] font-medium text-[var(--wt-text)] border-b border-[var(--wt-accent)]"
            />
          ) : (
            <p
              onClick={onStartEdit}
              className={`text-[12px] font-medium leading-snug cursor-text ${
                isDone ? "text-[var(--wt-text-muted)] line-through" : "text-[var(--wt-text)]"
              }`}
            >
              {todo.title}
            </p>
          )}

          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <span className={`text-[9.5px] font-semibold px-1.5 py-0.5 rounded-full ${pm.chip}`}>{pm.label}</span>
            {/* 来源（可下钻到对应报告） */}
            {sm.manual ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium text-[var(--wt-text-muted)] bg-black/[0.05]">
                {sm.label}
              </span>
            ) : (
              <button
                onClick={() => sm.reportType && onOpenReport(sm.reportType, sm.ref)}
                onPointerDown={(e) => e.stopPropagation()}
                title="查看来源报告"
                className="text-[10px] px-1.5 py-0.5 rounded-full font-medium text-[var(--wt-accent)] bg-[var(--wt-accent-bg)] hover:underline inline-flex items-center gap-0.5"
              >
                {sm.label}
                <ExternalLink className="w-2.5 h-2.5" />
              </button>
            )}
            {isDone ? (
              <span className="text-[10px] inline-flex items-center gap-0.5" style={{ color: "var(--wt-success)" }}>
                <Check className="w-2.5 h-2.5" /> 已完成
              </span>
            ) : due ? (
              <span
                className={`text-[10px] inline-flex items-center gap-0.5 ${
                  overdue ? "text-[var(--wt-danger)] font-semibold" : "text-[var(--wt-text-muted)]"
                }`}
              >
                <Calendar className="w-2.5 h-2.5" /> {overdue ? "逾期 " : ""}
                {due}
              </span>
            ) : null}
            {todo.note && <span className="text-[10px] text-[var(--wt-text-faint)] truncate">{todo.note}</span>}
          </div>
          {/* 进度条（P2 §4.5；非 done 显示，100% 自动联动完成由后端处理） */}
          {!isDone && <TodoProgress value={todo.progress} onChange={onProgressChange} />}
        </div>

        {/* hover 操作 */}
        <div className="flex flex-col items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={onStartEdit}
            onPointerDown={(e) => e.stopPropagation()}
            className="p-1 rounded-md hover:bg-black/[0.06] text-[var(--wt-text-muted)]"
            title="编辑"
          >
            <Pencil className="w-3 h-3" />
          </button>
          <button
            onClick={onDelete}
            onPointerDown={(e) => e.stopPropagation()}
            className="p-1 rounded-md hover:bg-[var(--wt-danger)] hover:text-white text-[var(--wt-text-muted)]"
            title="删除"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ==================== 进度条（P2 §4.5，可点击调节） ====================

function TodoProgress({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  // 编辑态：拖动 range，点确定才提交（防拖动中途频繁请求后端）
  if (editing) {
    return (
      <div className="flex items-center gap-1.5 mt-1.5" onPointerDown={(e) => e.stopPropagation()}>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={draft}
          onChange={(e) => setDraft(Number(e.target.value))}
          className="flex-1 h-1 cursor-pointer"
          style={{ accentColor: "var(--wt-accent)" }}
        />
        <span className="text-[10px] font-semibold text-[var(--wt-accent)] w-[28px] text-right">{draft}%</span>
        <button
          onClick={() => {
            onChange(draft);
            setEditing(false);
          }}
          className="text-[10px] font-medium text-[var(--wt-accent)] px-1.5 py-0.5 rounded-full bg-[var(--wt-accent-bg)] hover:brightness-95"
        >
          确定
        </button>
      </div>
    );
  }
  // 展示态：细进度条 + 百分比，点击进入编辑
  return (
    <button
      onClick={() => setEditing(true)}
      onPointerDown={(e) => e.stopPropagation()}
      title="点击调节进度（100% 自动标记完成）"
      className="flex items-center gap-1.5 mt-1.5 w-full"
    >
      <div className="flex-1 h-[3px] bg-black/[0.08] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${value}%`, background: value > 0 ? "var(--wt-accent)" : "transparent" }}
        />
      </div>
      <span className={`text-[10px] w-[28px] text-right ${value > 0 ? "font-semibold text-[var(--wt-accent)]" : "text-[var(--wt-text-faint)]"}`}>
        {value}%
      </span>
    </button>
  );
}

// ==================== 草稿行 ====================

function DraftRow({
  todo,
  editing,
  editTitle,
  onStartEdit,
  onEditChange,
  onSaveEdit,
  onCancelEdit,
  onAdopt,
  onDrop,
}: {
  todo: Todo;
  editing: boolean;
  editTitle: string;
  onStartEdit: () => void;
  onEditChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onAdopt: () => void;
  onDrop: () => void;
}) {
  return (
    <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-white/60 border border-black/[0.07]">
      <div className="w-4 h-4 rounded-full border-[1.5px] border-[var(--wt-text-faint)] shrink-0" />
      <div className="flex-1 min-w-0">
        {editing ? (
          <input
            autoFocus
            value={editTitle}
            onChange={(e) => onEditChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSaveEdit();
              if (e.key === "Escape") onCancelEdit();
            }}
            onBlur={onSaveEdit}
            className="w-full bg-transparent outline-none text-[12px] text-[var(--wt-text)] border-b border-[var(--wt-accent)]"
          />
        ) : (
          <p className="text-[12px] leading-snug text-[var(--wt-text)]">
            {todo.title}
            {todo.note && <span className="text-[10px] text-[var(--wt-text-faint)] ml-1">（{todo.note}）</span>}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={onStartEdit}
          className="flex items-center gap-0.5 px-2 py-1 rounded-md text-[10.5px] font-medium text-[var(--wt-text-secondary)] border border-black/10 bg-white hover:bg-black/[0.06]"
        >
          <Pencil className="w-2.5 h-2.5" /> 编辑
        </button>
        <button
          onClick={onDrop}
          className="px-2 py-1 rounded-md text-[10.5px] font-medium text-[var(--wt-text-muted)] border border-black/10 bg-white hover:bg-[var(--wt-danger)] hover:text-white hover:border-[var(--wt-danger)]"
        >
          丢弃
        </button>
        <button
          onClick={onAdopt}
          className="flex items-center gap-0.5 px-2 py-1 rounded-md text-[10.5px] font-medium text-[var(--wt-success)] border border-[rgba(52,199,89,0.4)] bg-white hover:bg-[var(--wt-success)] hover:text-white"
        >
          <Check className="w-2.5 h-2.5" /> 采纳
        </button>
      </div>
    </div>
  );
}
