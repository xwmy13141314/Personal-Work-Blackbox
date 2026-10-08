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
  ImagePlus,
  ClipboardPaste,
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
  TencentDocLink,
  TencentDocSchedule,
} from "@/lib/pywebview";
import { fmtDuration } from "@/app/lib/utils";
import { MiniDonut } from "@/app/components/MiniDonut";

// ==================== 待办看板视图（v4.3） ====================

// 优先级 → 标签 + 左色条（PRD §4.4：urgent 红 / high 橙 / normal 蓝 / low 灰）
const PRI_META: Record<TodoPriority, { label: string; chip: string; bar: string }> = {
  urgent: { label: "紧急", chip: "text-[var(--wt-danger)] bg-[rgba(255,59,48,0.1)]", bar: "#ff3b30" },
  high: { label: "高", chip: "text-[#b76b00] bg-[rgba(255,200,0,0.14)]", bar: "#ff9700" },
  normal: { label: "中", chip: "text-[var(--wt-accent)] bg-[var(--wt-accent-bg)]", bar: "#65b81e" },
  low: { label: "低", chip: "text-[var(--wt-text-muted)] bg-black/[0.06]", bar: "#8e8e93" },
};

// 看板三列
const COLUMNS: { key: TodoStatus; label: string; dot: string }[] = [
  { key: "pending", label: "待办", dot: "#8e8e93" },
  { key: "in_progress", label: "进行中", dot: "#65b81e" },
  { key: "done", label: "已完成", dot: "#73ce22" },
];

// 来源维度列（P4-B 多维视图；只读分组，不可拖拽改来源）
const SOURCE_COLUMNS: { key: string; label: string; dot: string }[] = [
  { key: "manual", label: "手动", dot: "#8e8e93" },
  { key: "daily_report", label: "日报", dot: "#65b81e" },
  { key: "weekly_report", label: "周报", dot: "#ffe600" },
  { key: "monthly_report", label: "月报", dot: "#ff9700" },
  { key: "tencent_doc", label: "腾讯文档", dot: "#3182ce" },
  { key: "local_document", label: "本地文档", dot: "#4f9d2a" },
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
  if (t.source_type === "tencent_doc")
    return { label: "腾讯文档", manual: true, reportType: null, ref: "" };
  if (t.source_type === "local_document")
    return { label: `本地文档${t.source_ref ? ` · ${t.source_ref}` : ""}`, manual: true, reportType: null, ref: "" };
  const map: Record<string, { name: string; rt: ReportType }> = {
    daily_report: { name: "日报", rt: "daily" },
    weekly_report: { name: "周报", rt: "weekly" },
    monthly_report: { name: "月报", rt: "monthly" },
  };
  const m = map[t.source_type] ?? { name: "报告", rt: "daily" as ReportType };
  const ref = t.source_ref ? ` ${t.source_ref.slice(5).replace("-", "/")}` : ""; // MM-DD → MM/DD
  return { label: m.name + ref, manual: false, reportType: m.rt, ref: t.source_ref };
}

/** 手动待办会附加系统元数据；卡片内容区只展示用户或 AI 识别出的正文。 */
function todoContent(note: string): string {
  return (note || "")
    .split("\n")
    .filter((line) => !/^(任务类型|记录日期)：/.test(line.trim()))
    .join("\n")
    .trim();
}

// 截止日期显示
function dueLabel(due: string, today: string): string | null {
  if (!due) return null;
  if (due === today) return "今天";
  return due.slice(5).replace("-", "/"); // MM/DD
}

type TodoType = "沟通跟进" | "交付执行" | "评审决策" | "规划设计" | "研究学习" | "行政整理";

const TODO_TYPE_HINTS: Record<TodoType, string[]> = {
  "沟通跟进": ["跟进", "回复", "联系", "沟通", "客户", "供应商", "会议", "邮件"],
  "交付执行": ["交付", "提交", "上线", "发布", "完成", "测试", "开发", "制作"],
  "评审决策": ["评审", "审批", "确认", "报价", "合同", "决策"],
  "规划设计": ["计划", "方案", "设计", "规划", "排期", "预算"],
  "研究学习": ["调研", "研究", "学习", "分析", "对标", "复盘"],
  "行政整理": ["整理", "归档", "登记", "报销", "填写", "文档"],
};

function inferTodo(title: string, today: string): { type: TodoType; priority: TodoPriority; due: string } {
  const lower = title.toLowerCase();
  const type = (Object.entries(TODO_TYPE_HINTS).find(([, words]) => words.some((word) => lower.includes(word)))?.[0] ?? "交付执行") as TodoType;
  const urgent = ["紧急", "立即", "马上", "今天", "故障", "投诉", "阻塞"].some((word) => lower.includes(word));
  const high = ["客户", "交付", "上线", "评审", "审批", "报价", "合同", "截止", "本周"].some((word) => lower.includes(word));
  const priority: TodoPriority = urgent ? "urgent" : high ? "high" : type === "行政整理" ? "low" : "normal";
  const offset = urgent ? 0 : high ? 2 : type === "研究学习" || type === "规划设计" ? 7 : 3;
  const target = new Date(`${today}T12:00:00`);
  target.setDate(target.getDate() + offset);
  return { type, priority, due: target.toISOString().slice(0, 10) };
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
  const [showTencentImport, setShowTencentImport] = useState(false);
  const [tencentDocUrl, setTencentDocUrl] = useState("");
  const [tencentDocName, setTencentDocName] = useState("");
  const [tencentDocuments, setTencentDocuments] = useState<TencentDocLink[]>([]);
  const [selectedTencentDocumentId, setSelectedTencentDocumentId] = useState("");
  const [tencentAutoEnabled, setTencentAutoEnabled] = useState(false);
  const [advices, setAdvices] = useState<TodoAdvice[]>([]);
  const [generating, setGenerating] = useState(false);
  const [catStats, setCatStats] = useState<CategoryStats | null>(null);
  const [overdueDismissed, setOverdueDismissed] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err" | null; msg: string; path?: string }>({ kind: null, msg: "" });
  const [draggingId, setDraggingId] = useState<number | null>(null);
  // 多维视图（P4-B §4.1）：status=按状态三列（可拖）/ source=按来源四列（只读分组）
  const [viewMode, setViewMode] = useState<"status" | "source">("status");
  const [showDeleted, setShowDeleted] = useState(false);
  // 新建表单
  const [showAdd, setShowAdd] = useState(false);
  const [addTitle, setAddTitle] = useState("");
  const [addNote, setAddNote] = useState("");
  const [addPri, setAddPri] = useState<TodoPriority>("normal");
  const [addDue, setAddDue] = useState("");
  const [addType, setAddType] = useState<TodoType>("交付执行");
  const [addRecordDate, setAddRecordDate] = useState("");
  const [addContactPerson, setAddContactPerson] = useState("");
  const [recognizingImage, setRecognizingImage] = useState(false);
  const [recognizingText, setRecognizingText] = useState(false);
  // inline 编辑（草稿与正式共用，按 id 锁定当前编辑行）
  const [editId, setEditId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editNote, setEditNote] = useState("");
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<number>>(new Set());

  const today = date;

  const reload = async () => {
    if (!api) return;
    const [all, s, ad, cat] = await Promise.all([
      api.get_todos(null, true),
      api.get_todo_stats().catch(() => ({ total: 0, today_pending: 0, overdue: 0, done: 0 })),
      api.get_todo_advices().catch(() => [] as TodoAdvice[]),
      api.get_category_stats("today", today).catch(() => null),
    ]);
    // 已删除任务保留在本地，仅在“已删除”模块打开时展示。
    setTodos(all.filter((t) => !t.is_draft));
    const nextDrafts = all.filter((t) => t.is_draft && t.status !== "cancelled");
    setDrafts(nextDrafts);
    // 刷新后只保留仍存在的选择，防止批量处理后显示过期计数。
    setSelectedDraftIds((previous) => new Set([...previous].filter((id) => nextDrafts.some((t) => t.id === id))));
    setStats(s);
    setAdvices(ad);
    setCatStats(cat);
    setLoading(false);
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  const applyTencentSchedule = (schedule: TencentDocSchedule) => {
    const selected = schedule.documents.find((item) => item.id === schedule.selected_id);
    setTencentDocuments(schedule.documents || []);
    setSelectedTencentDocumentId(schedule.selected_id || "");
    setTencentDocUrl(selected?.url || schedule.url || "");
    setTencentDocName(selected?.name || "");
    setTencentAutoEnabled(Boolean(selected?.enabled ?? schedule.enabled));
  };

  const loadTencentSchedule = async () => {
    if (!api) return;
    try {
      applyTencentSchedule(await api.get_tencent_doc_schedule());
    } catch {
      // 链接库不可用不影响手动新建待办。
    }
  };

  useEffect(() => {
    if (!api || !showTencentImport) return;
    void loadTencentSchedule();
    const refreshTimer = window.setInterval(() => { void loadTencentSchedule(); }, 30_000);
    return () => window.clearInterval(refreshTimer);
  }, [api, showTencentImport]);

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

  const extractTencentDoc = async () => {
    if (!api || extracting) return;
    const url = tencentDocUrl.trim();
    if (!/^https:\/\/docs\.qq\.com\//.test(url)) {
      setNotice({ kind: "err", msg: "请输入公开的 https://docs.qq.com/... 腾讯文档链接" });
      return;
    }
    setExtracting(true);
    setNotice({ kind: null, msg: "" });
    try {
      const { task_id } = await api.extract_todos_from_tencent_doc(url);
      const poll = async (attempt: number) => {
        if (attempt >= 120) {
          setExtracting(false);
          setNotice({ kind: "err", msg: "提取超时：已等待超过 2 分钟仍未完成" });
          return;
        }
        const task = await api.get_task_status(task_id);
        if (!task) {
          setExtracting(false);
          setNotice({ kind: "err", msg: "任务不存在" });
        } else if (task.status === "done") {
          await reload();
          setExtracting(false);
          setDraftOpen(true);
          setShowTencentImport(false);
          const count = task.result?.extracted ?? 0;
          const recognized = task.result?.recognized ?? 0;
          const duplicates = task.result?.skipped_duplicates ?? 0;
          const detail = task.result?.diagnostics;
          const columns = detail?.recognized_columns?.length ? `识别列：${detail.recognized_columns.join("、")}。` : "未读取到表格列。";
          const skipped = detail?.skipped_completed ? `已跳过 ${detail.skipped_completed} 条已完成/取消事项。` : "";
          const noNewTasks = recognized > 0 && duplicates === recognized;
          setNotice({
            kind: count || noNewTasks ? "ok" : "err",
            msg: count
              ? `已读取 ${detail?.table_rows ?? 0} 行表格，导入 ${count} 条待办到草稿区。${columns}${skipped}`
              : noNewTasks
                ? `已识别 ${recognized} 条待办，但它们已在看板或已删除列表中，因此未重复创建。${columns}${skipped}`
                : `未识别到可执行待办。${columns}请确认“待办”列是否包含未完成任务。${skipped}`,
          });
        } else if (task.status === "failed") {
          setExtracting(false);
          setNotice({ kind: "err", msg: task.error || "腾讯文档提取失败" });
        } else {
          setTimeout(() => poll(attempt + 1), 1000);
        }
      };
      setTimeout(() => poll(1), 1000);
    } catch (error) {
      setExtracting(false);
      setNotice({ kind: "err", msg: String(error) });
    }
  };

  const saveTencentSchedule = async () => {
    if (!api) return;
    const result = await api.save_tencent_doc_schedule(tencentDocUrl.trim(), tencentAutoEnabled, tencentDocName.trim(), selectedTencentDocumentId);
    if (result.ok && result.schedule) {
      applyTencentSchedule(result.schedule);
      setNotice({ kind: "ok", msg: tencentAutoEnabled ? "已保存到腾讯文档链接库；每天 09:00 自动识别当前选中链接并进入待确认草稿区" : "已保存到腾讯文档链接库，自动识别当前关闭" });
    }
    else setNotice({ kind: "err", msg: result.error || "保存腾讯文档设置失败" });
  };

  const selectTencentDocument = async (document: TencentDocLink) => {
    if (!api) return;
    const result = await api.select_tencent_doc_schedule(document.id);
    if (result.ok && result.schedule) applyTencentSchedule(result.schedule);
    else setNotice({ kind: "err", msg: result.error || "切换腾讯文档失败" });
  };

  const deleteTencentDocument = async (document: TencentDocLink) => {
    if (!api) return;
    const result = await api.delete_tencent_doc_schedule(document.id);
    if (result.ok && result.schedule) {
      applyTencentSchedule(result.schedule);
      setNotice({ kind: "ok", msg: `已删除链接记录「${document.name}」，已导入的待办不会受影响` });
    } else setNotice({ kind: "err", msg: result.error || "删除腾讯文档链接失败" });
  };

  const addTencentDocument = () => {
    setSelectedTencentDocumentId("");
    setTencentDocName("");
    setTencentDocUrl("");
    setTencentAutoEnabled(false);
    setNotice({ kind: null, msg: "" });
  };

  const importLocalDocuments = async () => {
    if (!api || extracting) return;
    setExtracting(true);
    setNotice({ kind: null, msg: "" });
    try {
      const response = await api.import_local_documents();
      if (response.cancelled || !response.task_id) {
        setExtracting(false);
        return;
      }
      const poll = async (attempt: number) => {
        if (attempt >= 120) {
          setExtracting(false);
          setNotice({ kind: "err", msg: "导入超时：已等待超过 2 分钟仍未完成" });
          return;
        }
        const task = await api.get_task_status(response.task_id!);
        if (!task) {
          setExtracting(false);
          setNotice({ kind: "err", msg: "导入任务不存在" });
        } else if (task.status === "done") {
          await reload();
          setExtracting(false);
          setDraftOpen(true);
          const count = task.result?.extracted ?? 0;
          const failed = task.result?.failed_files?.length ?? 0;
          const suffix = failed ? `，${failed} 个文件未能导入` : "";
          setNotice({ kind: count ? "ok" : "err", msg: count ? `已识别 ${count} 条待办到草稿区${suffix}` : `未提取到可执行待办${suffix}` });
        } else if (task.status === "failed") {
          setExtracting(false);
          setNotice({ kind: "err", msg: task.error || "本地文档导入失败" });
        } else {
          setTimeout(() => poll(attempt + 1), 1000);
        }
      };
      setTimeout(() => poll(1), 1000);
    } catch (error) {
      setExtracting(false);
      setNotice({ kind: "err", msg: String(error) });
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

  const setCardStatus = async (t: Todo, status: TodoStatus) => {
    if (!api) return;
    await api.update_todo(t.id, { status });
    await reload();
  };

  // 调进度（100% 自动联动完成由后端处理）
  const setProgress = async (t: Todo, v: number) => {
    if (!api) return;
    await api.update_todo(t.id, { progress: v });
    await reload();
  };

  // 卡片上的重要程度、计划时间、进度备注、对接人可直接修改。
  const updateCardMeta = async (t: Todo, fields: Pick<Partial<Todo>, "priority" | "due_date" | "progress_note" | "contact_person">) => {
    if (!api) return;
    const result = await api.update_todo(t.id, fields);
    if (!result.ok) {
      setNotice({ kind: "err", msg: result.error || "待办信息保存失败" });
      return;
    }
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
    const result = await api.adopt_todos([id]);
    if (!result.ok) setNotice({ kind: "err", msg: result.error || "采纳失败" });
    await reload();
  };
  const adoptAll = async () => {
    if (!api || !drafts.length) return;
    const result = await api.adopt_todos(drafts.map((d) => d.id));
    if (!result.ok) setNotice({ kind: "err", msg: result.error || "全部采纳失败" });
    await reload();
  };
  const drop = async (id: number) => {
    if (!api) return;
    const result = await api.discard_todos([id]);
    if (!result.ok) setNotice({ kind: "err", msg: result.error || "丢弃失败" });
    await reload();
  };
  const toggleDraftSelection = (id: number) => {
    setSelectedDraftIds((previous) => {
      const next = new Set(previous);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  const toggleAllDrafts = () => {
    setSelectedDraftIds((previous) => previous.size === drafts.length ? new Set() : new Set(drafts.map((d) => d.id)));
  };
  const adoptSelectedDrafts = async () => {
    if (!api || selectedDraftIds.size === 0) return;
    const result = await api.adopt_todos([...selectedDraftIds]);
    if (!result.ok) {
      setNotice({ kind: "err", msg: result.error || "批量采纳失败" });
      return;
    }
    setNotice({ kind: "ok", msg: `已采纳 ${result.adopted || 0} 条待办` });
    await reload();
  };
  const discardSelectedDrafts = async () => {
    if (!api || selectedDraftIds.size === 0) return;
    const result = await api.discard_todos([...selectedDraftIds]);
    if (!result.ok) {
      setNotice({ kind: "err", msg: result.error || "批量丢弃失败" });
      return;
    }
    setNotice({ kind: "ok", msg: `已丢弃 ${result.discarded || 0} 条草稿，可在“已删除”中恢复` });
    await reload();
  };

  // 卡片删除：移入已删除，默认不显示。
  const remove = async (id: number) => {
    if (!api) return;
    await api.update_todo(id, { status: "cancelled" });
    await reload();
  };

  const restoreDeleted = async (id: number) => {
    if (!api) return;
    await api.update_todo(id, { status: "pending" });
    await reload();
  };

  const permanentlyDelete = async (id: number) => {
    if (!api) return;
    await api.delete_todo(id);
    await reload();
  };

  // 新建
  const submitAdd = async () => {
    if (!api || !addTitle.trim()) return;
    const note = `${addNote.trim()}${addNote.trim() ? "\n" : ""}任务类型：${addType}\n记录日期：${addRecordDate || today}`;
    await api.add_todo(addTitle.trim(), addPri, addDue, note, addRecordDate || today, addContactPerson.trim());
    setAddTitle("");
    setAddNote("");
    setAddPri("normal");
    setAddDue("");
    setAddType("交付执行");
    setAddRecordDate(today);
    setAddContactPerson("");
    setShowAdd(false);
    await reload();
  };

  const applyImageText = (text: string) => {
    const title = text.replace(/\s+/g, " ").trim().slice(0, 200);
    if (!title) return;
    const inferred = inferTodo(title, today);
    setAddTitle(title);
    setAddNote(text);
    setAddType(inferred.type);
    setAddPri(inferred.priority);
    setAddDue(inferred.due);
    setNotice({ kind: "ok", msg: "已从图片识别内容并自动补全任务信息，请确认后添加" });
  };

  const recognizeTodoText = async () => {
    if (!api || recognizingText || !addTitle.trim()) return;
    setRecognizingText(true);
    try {
      const result = await api.recognize_todo_text(addTitle);
      if (!result.ok || !result.todo) {
        setNotice({ kind: "err", msg: result.error || "AI 未能识别待办信息" });
        return;
      }
      const todo = result.todo;
      setAddTitle(todo.title);
      const steps = todo.steps?.filter((step) => step.trim()) ?? [];
      setAddNote(steps.length
        ? `${todo.note.trim()}${todo.note.trim() ? "\n\n" : ""}执行事项：\n${steps.map((step, index) => `${index + 1}. ${step.trim()}`).join("\n")}`
        : todo.note);
      setAddPri(todo.priority);
      setAddType(inferTodo(todo.title, today).type);
      if (todo.due_date) setAddDue(todo.due_date);
      setNotice({ kind: "ok", msg: result.local_fallback ? "AI 当前不可用，已用本地规则整理标题和内容，请确认后添加" : "AI 已识别标题和内容，请确认后添加" });
    } catch (error) {
      setNotice({ kind: "err", msg: String(error) });
    } finally {
      setRecognizingText(false);
    }
  };

  const recognizeTodoImage = async (clipboard = false) => {
    if (!api || recognizingImage) return;
    setRecognizingImage(true);
    try {
      const result = clipboard ? await api.recognize_todo_clipboard_image() : await api.recognize_todo_image();
      if (result.cancelled) return;
      if (!result.ok || !result.text) {
        setNotice({ kind: "err", msg: result.error || "未识别到图片文字" });
        return;
      }
      applyImageText(result.text);
    } catch (error) {
      setNotice({ kind: "err", msg: String(error) });
    } finally {
      setRecognizingImage(false);
    }
  };

  // inline 编辑保存
  const startEdit = (t: Todo) => {
    setEditId(t.id);
    setEditTitle(t.title);
    setEditNote(todoContent(t.note));
  };
  const saveEdit = async () => {
    if (!api || editId == null) return;
    if (editTitle.trim()) await api.update_todo(editId, { title: editTitle.trim(), note: editNote.trim() });
    setEditId(null);
    setEditTitle("");
    setEditNote("");
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
      .sort((a, b) => a.sort_order - b.sort_order);

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
  const colOf = (key: string) => todos.filter((t) => colKeyOf(t) === key).sort((a, b) => a.sort_order - b.sort_order);
  const deletedTodos = todos.filter((t) => t.status === "cancelled").sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  // 统计卡片
  const statCards: { label: string; value: number; color: string }[] = [
    { label: "总任务", value: stats.total, color: "var(--wt-text)" },
    { label: "今日待办", value: stats.today_pending, color: "var(--wt-accent)" },
    { label: "已延期", value: stats.overdue, color: "var(--wt-danger)" },
    { label: "已完成", value: stats.done, color: "var(--wt-success)" },
  ];

  // 今日工作实况（P3 §4.7：复用 category_stats，纯 DB 无 LLM；与任务统计同屏看「该做什么 + 实际做了什么」）
  const DONUT_PALETTE = ["#65b81e", "#73ce22", "#ff9700", "#ffe600", "#ff3b30", "#b7ed00"];
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
        className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-5 py-1.5 min-h-11 shrink-0 border-b border-black/[0.07]"
        style={{ background: "rgba(245,245,247,0.8)", backdropFilter: "blur(20px)" }}
      >
        <div className="flex items-center gap-2 shrink-0">
          <p className="text-[14px] font-semibold text-[var(--wt-text)]">待办看板</p>
          <span className="text-[11px] text-[var(--wt-text-muted)] whitespace-nowrap">
            {stats.today_pending + stats.overdue} 条未完成
            {drafts.length ? `，${drafts.length} 条待确认` : ""}
          </span>
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">

        {/* 待确认（草稿）按钮 */}
        <button
          onClick={() => drafts.length && setDraftOpen((v) => !v)}
          disabled={drafts.length === 0}
          className={`shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium transition-all disabled:opacity-50 ${
            drafts.length
              ? "bg-[rgba(255,200,0,0.12)] text-[#b76b00] hover:bg-[rgba(255,200,0,0.2)]"
              : "bg-black/[0.06] text-[var(--wt-text-muted)]"
          }`}
        >
          待确认
          {drafts.length > 0 && (
            <span className="bg-[var(--wt-danger)] text-white text-[10px] px-1 rounded-full font-bold leading-[1.4]">
              {drafts.length}
            </span>
          )}
        </button>

        {/* 从报告提取 */}
        <button
          onClick={extract}
          disabled={extracting}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-60 transition-all"
        >
          {extracting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
          {extracting ? "提取中" : "从报告提取"}
        </button>

        <button
          onClick={() => setShowTencentImport((value) => !value)}
          disabled={extracting}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-60 transition-all"
          title="粘贴公开腾讯文档链接，提取待办到草稿区"
        >
          <ExternalLink className="w-3 h-3" /> 腾讯文档导入
        </button>

        <button
          onClick={importLocalDocuments}
          disabled={extracting}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-60 transition-all"
          title="选择多个本地文档，智能提取待办到草稿区"
        >
          {extracting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <FolderOpen className="w-3 h-3" />}
          {extracting ? "导入中" : "本地文档导入"}
        </button>

        {/* AI 推进建议（P2 §4.6） */}
        <button
          onClick={generateAdvices}
          disabled={generating}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-[rgba(255,200,0,0.2)] text-[#805300] hover:bg-[rgba(255,200,0,0.3)] disabled:opacity-60 transition-all"
          title="结合当日活动，AI 为未完成待办提出推进建议"
        >
          {generating ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
          {generating ? "生成中" : "AI 建议"}
        </button>

        {/* 待办提醒检查（P3 §4.9，手动触发；后端每小时自动） */}
        <button
          onClick={notifyCheck}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] transition-all"
          title="检查逾期/即将到期待办并发桌面提醒"
        >
          <Bell className="w-3 h-3" /> 提醒
        </button>

        {/* 新建 */}
        <button
          onClick={() => {
            if (!showAdd) setAddRecordDate(today);
            setShowAdd((v) => !v);
          }}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 transition-all"
        >
          <Plus className="w-3 h-3" /> 新建待办
        </button>

        {/* 导出表格 */}
        <button
          onClick={exportCsv}
          className="shrink-0 whitespace-nowrap flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] transition-all"
          title="导出为 CSV（Excel / 飞书多维表格可用）"
        >
          <Download className="w-3 h-3" /> 导出
        </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        {showTencentImport && (
          <div className="rounded-xl border border-[var(--wt-border-light)] bg-white/70 p-3">
            <p className="text-[13px] font-semibold text-[var(--wt-text)]">从腾讯文档提取待办</p>
            <p className="mt-1 text-[12px] text-[var(--wt-text-muted)]">链接会保存在本机链接库，可命名、切换、删除和整理。已适配智能表字段：项目名称、邮件日期、待办、状态、安排给了谁、备注、发件人、收件人。</p>
            <div className="mt-2 flex gap-2">
              <input
                value={tencentDocName}
                onChange={(event) => setTencentDocName(event.target.value)}
                placeholder="文档名称"
                className="w-32 shrink-0 rounded-lg border border-[var(--wt-border-input)] bg-white px-3 py-1.5 text-[12px] outline-none focus:border-[var(--wt-accent)]"
              />
              <input
                value={tencentDocUrl}
                onChange={(event) => { setTencentDocUrl(event.target.value); setSelectedTencentDocumentId(""); }}
                placeholder="https://docs.qq.com/..."
                className="min-w-0 flex-1 rounded-lg border border-[var(--wt-border-input)] bg-white px-3 py-1.5 text-[12px] outline-none focus:border-[var(--wt-accent)]"
              />
              <button onClick={extractTencentDoc} disabled={extracting || !tencentDocUrl.trim()} className="shrink-0 rounded-lg bg-[var(--wt-accent)] px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50">
                {extracting ? "提取中" : "提取"}
              </button>
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--wt-text-muted)]">
              <label className="inline-flex items-center gap-1.5 cursor-pointer"><input type="checkbox" checked={tencentAutoEnabled} onChange={(event) => setTencentAutoEnabled(event.target.checked)} /> 每天 09:00 自动识别当前链接</label>
              <button onClick={saveTencentSchedule} disabled={!tencentDocUrl.trim()} className="rounded-md bg-black/[0.06] px-2 py-1 font-medium text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-50">保存到链接库</button>
              <button onClick={addTencentDocument} className="rounded-md border border-[var(--wt-border-light)] bg-white px-2 py-1 font-medium text-[var(--wt-text-secondary)] hover:bg-black/[0.04]">新增一条链接</button>
            </div>
            <div className="mt-3 border-t border-black/[0.06] pt-2">
                <p className="mb-1.5 text-[11px] font-medium text-[var(--wt-text-secondary)]">腾讯文档链接记录（{tencentDocuments.length} 条）</p>
                {tencentDocuments.length === 0 ? (
                  <p className="rounded-md bg-black/[0.03] px-2 py-1.5 text-[11px] text-[var(--wt-text-muted)]">当前还没有保存的链接。填写上方名称和链接后，点击“保存到链接库”；第 2、3 条可点“新增一条链接”后继续添加。</p>
                ) : (
                <div className="max-h-28 space-y-1 overflow-y-auto pr-1">
                  {tencentDocuments.map((document, index) => (
                    <div key={document.id} className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] ${document.id === selectedTencentDocumentId ? "bg-[var(--wt-accent-bg)]" : "bg-black/[0.03]"}`}>
                      <button onClick={() => selectTencentDocument(document)} className="min-w-0 flex-1 text-left" title={document.url}>
                        <span className="font-medium text-[var(--wt-text)]">第 {index + 1} 条 · {document.name}</span>
                        <span className="ml-1 text-[var(--wt-text-muted)]">{document.enabled ? "· 每日 09:00" : "· 手动"}</span>
                        {document.last_run_status && (
                          <span className={`ml-1 ${document.last_run_status === "failed" ? "text-[var(--wt-danger)]" : document.last_run_status === "done" ? "text-[var(--wt-success)]" : "text-[var(--wt-text-muted)]"}`} title={document.last_run_message || ""}>
                            · {document.last_run_status === "running" ? "识别中" : document.last_run_status === "done" ? `已完成${document.last_run_at ? ` ${document.last_run_at.slice(11, 16)}` : ""}` : "上次失败"}
                          </span>
                        )}
                      </button>
                      <button onClick={() => deleteTencentDocument(document)} className="shrink-0 text-[var(--wt-text-muted)] hover:text-[var(--wt-danger)]" title="删除此链接记录"><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                  ))}
                </div>
                )}
              </div>
          </div>
        )}
        {/* 逾期待办提示 + 一键顺延（P3 §4.8） */}
        {overdueTodos.length > 0 && !overdueDismissed && (
          <div className="rounded-xl border border-[rgba(255,59,48,0.25)] bg-[rgba(255,59,48,0.05)] p-3 flex items-center gap-3">
            <AlertTriangle className="w-4 h-4 text-[var(--wt-danger)] shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-semibold text-[var(--wt-text)]">{overdueTodos.length} 项待办已逾期，带入今日继续跟进</p>
              <p className="text-[12px] text-[var(--wt-text-secondary)] truncate">
                {overdueTodos.slice(0, 3).map((t) => t.title).join("、")}
                {overdueTodos.length > 3 ? " 等" : ""}
              </p>
            </div>
            <button
              onClick={postponeOverdue}
              className="shrink-0 px-3 py-1 rounded-full text-[12px] font-medium text-white bg-[var(--wt-danger)] hover:brightness-110 transition-all"
            >
              顺延到今日
            </button>
            <button
              onClick={() => setOverdueDismissed(true)}
              className="shrink-0 px-2 py-1 rounded-full text-[12px] font-medium text-[var(--wt-text-muted)] hover:bg-black/[0.06] transition-all"
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
              <p className="text-[11.5px] text-[var(--wt-text-muted)]">{c.label}</p>
              <p className="text-[23px] font-semibold leading-tight mt-0.5" style={{ color: c.color }}>
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
                  <p className="text-[14px] font-bold text-[var(--wt-text)] leading-none">{fmtDuration(totalActive).replace(" ", "")}</p>
                  <p className="text-[10px] text-[var(--wt-text-muted)] mt-0.5">活跃</p>
                </>
              ) : (
                <p className="text-[11px] text-[var(--wt-text-muted)]">暂无</p>
              )
            }
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-[13px] font-semibold text-[var(--wt-text)]">今日工作实况</p>
              <span className="text-[11px] text-[var(--wt-text-muted)]">{catSegments.length} 个类别</span>
            </div>
            {catSegments.length > 0 ? (
              <div className="space-y-1">
                {catSegments.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-[12px]">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
                    <span className="shrink-0 text-[12px]">{s.icon}</span>
                    <span className="text-[var(--wt-text-secondary)] truncate flex-1">{s.label}</span>
                    <span className="text-[var(--wt-text-muted)] shrink-0 tabular-nums">{fmtDuration(s.value)}</span>
                    <span className="text-[var(--wt-text-muted)] shrink-0 w-9 text-right tabular-nums">{Math.round((s.value / totalActive) * 100)}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-[var(--wt-text-muted)] py-1.5">今日暂无采集活动</p>
            )}
          </div>
        </div>

        {/* AI 推进建议（P2 §4.6；日报后自动生成，也可手动触发） */}
        {advices.length > 0 && (
          <div className="rounded-xl border border-[rgba(255,230,0,0.2)] bg-[rgba(255,230,0,0.04)] p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-[#ffe600]" />
              <p className="text-[13px] font-semibold text-[var(--wt-text)]">推进建议</p>
              <span className="text-[11px] text-[var(--wt-text-muted)]">基于当日活动，可采纳或忽略</span>
            </div>
            {advices.map((a) => (
              <div key={a.id} className="flex items-start gap-2.5 rounded-lg bg-white/70 px-3 py-2">
                <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10.5px] font-semibold ${
                  a.suggestion_type === "start" ? "bg-[var(--wt-accent-bg)] text-[var(--wt-accent)]"
                  : a.suggestion_type === "progress" ? "bg-[rgba(115,206,34,0.14)] text-[#1d9b3e]"
                  : "bg-black/[0.06] text-[var(--wt-text-muted)]"
                }`}>
                  {a.suggestion_type === "start" ? "开始" : a.suggestion_type === "progress" ? "推进" : "卡住"}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] font-medium text-[var(--wt-text)] truncate">{a.todo_title}</p>
                  <p className="text-[12px] text-[var(--wt-text-secondary)] break-words">
                    {a.reason}
                    {a.suggestion_type === "progress" && a.suggested_progress !== null
                      && `（建议进度 ${a.suggested_progress}%）`}
                  </p>
                </div>
                <button
                  onClick={() => applyAdvice(a.id)}
                  className="shrink-0 px-2 py-0.5 rounded-full text-[11.5px] font-medium text-white bg-[var(--wt-accent)] hover:brightness-110 transition-all"
                >
                  采纳
                </button>
                <button
                  onClick={() => dismissAdvice(a.id)}
                  className="shrink-0 px-2 py-0.5 rounded-full text-[11.5px] font-medium text-[var(--wt-text-muted)] hover:bg-black/[0.06] transition-all"
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
            <p className={`text-[12.5px] break-all ${notice.kind === "ok" ? "text-green-700" : "text-orange-700"}`}>
              {notice.msg}
            </p>
            {notice.kind === "ok" && notice.path && (
              <button
                onClick={openFolder}
                className="ml-auto shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-full text-[12px] font-medium text-green-700 border border-green-300 bg-white hover:bg-green-50 transition-all"
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
            onPaste={(event) => {
              const hasImage = Array.from(event.clipboardData.items).some((item) => item.type.startsWith("image/"));
              if (hasImage) {
                event.preventDefault();
                void recognizeTodoImage(true);
              }
            }}
          >
            <input
              autoFocus
              value={addTitle}
              onChange={(e) => {
                const title = e.target.value;
                setAddTitle(title);
                if (title.trim()) {
                  const inferred = inferTodo(title, today);
                  setAddType(inferred.type);
                  setAddPri(inferred.priority);
                  setAddDue((current) => current || inferred.due);
                }
              }}
              onKeyDown={(e) => e.key === "Enter" && submitAdd()}
              placeholder="输入待办内容..."
              className="w-full bg-transparent outline-none text-[13px] text-[var(--wt-text)] placeholder:text-[var(--wt-text-muted)]"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={recognizeTodoText}
                disabled={recognizingText || !addTitle.trim()}
                className="inline-flex items-center gap-1 rounded-full bg-[rgba(255,200,0,0.16)] px-2.5 py-1 text-[12px] font-medium text-[#8a5a00] hover:bg-[rgba(255,200,0,0.25)] disabled:opacity-50"
                title="通过当前 AI 配置识别标题和内容并回填表单"
              >
                <Sparkles className="h-3.5 w-3.5" /> {recognizingText ? "AI 识别中" : "AI 识别标题和内容"}
              </button>
              <span className="text-[11px] text-[var(--wt-text-muted)]">输入完整事项后点击识别，结果可继续修改。</span>
            </div>
            {addNote && (
              <textarea
                value={addNote}
                onChange={(e) => setAddNote(e.target.value)}
                rows={2}
                placeholder="待办内容 / 备注"
                className="w-full resize-y rounded-lg bg-black/[0.04] px-2.5 py-1.5 text-[12px] text-[var(--wt-text)] outline-none placeholder:text-[var(--wt-text-muted)]"
              />
            )}
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                onClick={() => recognizeTodoImage(false)}
                disabled={recognizingImage}
                className="inline-flex items-center gap-1 rounded-full bg-[var(--wt-accent-bg)] px-2.5 py-1 text-[12px] font-medium text-[var(--wt-accent)] hover:brightness-95 disabled:opacity-50"
                title="选择本地图片，在本机识别文字并生成待办"
              >
                <ImagePlus className="h-3.5 w-3.5" /> {recognizingImage ? "识别中" : "添加图片识别"}
              </button>
              <button
                onClick={() => recognizeTodoImage(true)}
                disabled={recognizingImage}
                className="inline-flex items-center gap-1 rounded-full bg-black/[0.06] px-2.5 py-1 text-[12px] font-medium text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-50"
                title="直接识别剪贴板中已复制的图片"
              >
                <ClipboardPaste className="h-3.5 w-3.5" /> 识别粘贴图片
              </button>
              <span className="text-[11px] text-[var(--wt-text-muted)]">可直接在此处按 ⌘V 粘贴图片；图片仅在本机识别，不上传。</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={addType}
                onChange={(e) => setAddType(e.target.value as TodoType)}
                className="text-[12px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none"
                title="任务类型"
              >
                {(Object.keys(TODO_TYPE_HINTS) as TodoType[]).map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
              <select
                value={addPri}
                onChange={(e) => setAddPri(e.target.value as TodoPriority)}
                className="text-[12px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none"
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
                className="text-[12px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none text-[var(--wt-text-secondary)]"
                title="计划完成日期"
              />
              <input
                type="date"
                value={addRecordDate}
                onChange={(e) => setAddRecordDate(e.target.value)}
                className="text-[12px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none text-[var(--wt-text-secondary)]"
                title="记录日期"
              />
              <input
                value={addContactPerson}
                onChange={(e) => setAddContactPerson(e.target.value)}
                maxLength={100}
                placeholder="对接人（选填）"
                className="w-28 text-[12px] bg-black/[0.06] rounded-full px-2 py-0.5 outline-none placeholder:text-[var(--wt-text-muted)]"
                title="对接人（选填）"
              />
              <div className="flex-1" />
              <button onClick={() => setShowAdd(false)} className="text-[12px] text-[var(--wt-text-muted)] px-2 py-0.5">
                取消
              </button>
              <button
                onClick={submitAdd}
                className="text-[12px] bg-[var(--wt-accent)] text-white px-3 py-0.5 rounded-full hover:brightness-110"
              >
                添加
              </button>
            </div>
            <p className="text-[11px] text-[var(--wt-text-muted)]">已根据任务内容自动识别类型、优先级和计划完成日；对接人可选填，所有字段均可手动修改。</p>
          </div>
        )}

        {/* 草稿确认区（仅有草稿时显示） */}
        {drafts.length > 0 && (
          <div
            className="rounded-xl border"
            style={{ borderColor: "rgba(255,200,0,0.35)", background: "rgba(255,200,0,0.06)" }}
          >
            <div
              className="flex items-center gap-2 px-3.5 py-2.5 cursor-pointer"
              onClick={() => setDraftOpen((v) => !v)}
            >
              <div
                className="w-[18px] h-[18px] rounded-md flex items-center justify-center shrink-0"
                style={{ background: "linear-gradient(135deg,#65b81e,#ffe600)" }}
              >
                <Sparkles className="w-2.5 h-2.5 text-white" />
              </div>
              <div className="min-w-0">
                <p className="text-[13px] font-semibold text-[var(--wt-text)]">
                  AI 提取了 {drafts.length} 条待办待确认
                </p>
                <p className="text-[12px] text-[var(--wt-text-muted)]">
                  来源：{sourceMeta(drafts[0]).label} · 请确认后入库
                </p>
              </div>
              <div className="ml-auto flex items-center gap-1 text-[12px] text-[var(--wt-text-muted)]">
                {draftOpen ? "收起" : "展开"}
                <ChevronDown className={`w-3 h-3 transition-transform ${draftOpen ? "rotate-180" : ""}`} />
              </div>
            </div>
            {draftOpen && (
              <div className="px-3.5 pb-3 flex flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-1.5 pb-1">
                  <button
                    type="button"
                    onClick={toggleAllDrafts}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-text-secondary)] border border-black/10 bg-white hover:bg-black/[0.05]"
                  >
                    <CheckSquare className="w-3 h-3" />
                    {selectedDraftIds.size === drafts.length ? "取消全选" : "全选"}
                  </button>
                  {selectedDraftIds.size > 0 && <span className="text-[11.5px] text-[var(--wt-text-muted)]">已选 {selectedDraftIds.size} 条</span>}
                  <button
                    type="button"
                    disabled={selectedDraftIds.size === 0}
                    onClick={adoptSelectedDrafts}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-success)] border border-[rgba(115,206,34,0.4)] bg-white hover:bg-[var(--wt-success)] hover:text-white disabled:opacity-40 disabled:hover:bg-white disabled:hover:text-[var(--wt-success)]"
                  >
                    <Check className="w-3 h-3" /> 批量采纳
                  </button>
                  <button
                    type="button"
                    disabled={selectedDraftIds.size === 0}
                    onClick={discardSelectedDrafts}
                    className="px-2 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-danger)] border border-red-200 bg-white hover:bg-[var(--wt-danger)] hover:text-white disabled:opacity-40 disabled:hover:bg-white disabled:hover:text-[var(--wt-danger)]"
                  >
                    批量丢弃
                  </button>
                </div>
                {drafts.map((d) => (
                  <DraftRow
                    key={d.id}
                    todo={d}
                    selected={selectedDraftIds.has(d.id)}
                    editing={editId === d.id}
                    editTitle={editTitle}
                    editNote={editNote}
                    onStartEdit={() => startEdit(d)}
                    onEditChange={setEditTitle}
                    onEditNoteChange={setEditNote}
                    onSaveEdit={saveEdit}
                    onCancelEdit={() => setEditId(null)}
                    onAdopt={() => adopt(d.id)}
                    onDrop={() => drop(d.id)}
                    onToggleSelected={() => toggleDraftSelection(d.id)}
                  />
                ))}
                <button
                  onClick={adoptAll}
                  className="self-start flex items-center gap-1 px-3 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-success)] border border-[rgba(115,206,34,0.4)] hover:bg-[var(--wt-success)] hover:text-white transition-all"
                >
                  <Check className="w-2.5 h-2.5" /> 全部采纳
                </button>
              </div>
            )}
          </div>
        )}

        {/* 视图维度切换（P4-B §4.1） */}
        <div className="flex items-center gap-1 mt-2">
          <span className="text-[12px] text-[var(--wt-text-muted)] mr-1">视图</span>
          {([["status", "按状态"], ["source", "按来源"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setViewMode(k)}
              className={`px-2.5 py-0.5 rounded-full text-[12px] font-medium transition-all ${
                viewMode === k
                  ? "bg-[var(--wt-accent)] text-white"
                  : "bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1]"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            onClick={() => setShowDeleted(!showDeleted)}
            className={`ml-1 px-2.5 py-0.5 rounded-full text-[12px] font-medium transition-all ${
              showDeleted ? "bg-[var(--wt-text-secondary)] text-white" : "bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1]"
            }`}
          >
            已删除{deletedTodos.length ? ` ${deletedTodos.length}` : ""}
          </button>
        </div>

        {/* 看板 */}
        {loading ? (
          <p className="text-[13px] text-[var(--wt-text-muted)] py-12 text-center">加载中...</p>
        ) : showDeleted ? (
          <div className="mt-2 rounded-xl border border-black/[0.07] bg-black/[0.015] p-3 space-y-2">
            <p className="text-[12px] text-[var(--wt-text-muted)]">已删除任务默认隐藏；可恢复，或彻底删除。</p>
            {deletedTodos.length ? deletedTodos.map((t) => (
              <div key={t.id} className="flex items-center gap-3 rounded-lg border border-black/[0.07] bg-white/70 px-3 py-2">
                <div className="min-w-0 flex-1"><p className="text-[13px] font-medium truncate">{t.title}</p><p className="text-[11px] text-[var(--wt-text-muted)]">删除于 {t.updated_at.slice(0, 10)}</p></div>
                <button onClick={() => restoreDeleted(t.id)} className="text-[11px] font-medium text-[var(--wt-accent)]">恢复</button>
                <button onClick={() => permanentlyDelete(t.id)} className="text-[11px] text-[var(--wt-danger)]">彻底删除</button>
              </div>
            )) : <p className="py-8 text-center text-[12px] text-[var(--wt-text-faint)]">暂无已删除待办</p>}
          </div>
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
                            editNote={editNote}
                            onStartEdit={() => startEdit(t)}
                            onEditChange={setEditTitle}
                            onEditNoteChange={setEditNote}
                            onSaveEdit={saveEdit}
                            onCancelEdit={() => setEditId(null)}
                            onCycle={() => cycleStatus(t)}
                            onSetStatus={(status) => setCardStatus(t, status)}
                            onProgressChange={(v) => setProgress(t, v)}
                            onUpdateMeta={(fields) => updateCardMeta(t, fields)}
                            onDelete={() => remove(t.id)}
                            onOpenReport={onOpenReport}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="py-6 text-center text-[12px] text-[var(--wt-text-faint)]">
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
                  editNote=""
                  onStartEdit={() => {}}
                  onEditChange={() => {}}
                  onEditNoteChange={() => {}}
                  onSaveEdit={() => {}}
                  onCancelEdit={() => {}}
                  onCycle={() => {}}
                  onSetStatus={() => {}}
                  onProgressChange={() => {}}
                  onUpdateMeta={() => {}}
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
        isOver ? "border-[rgba(101,184,30,0.4)] bg-[rgba(101,184,30,0.04)]" : "border-black/[0.07] bg-black/[0.015]"
      }`}
    >
      <div className="flex items-center gap-1.5 px-1 pb-2">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: col.dot }} />
        <p className="text-[13px] font-semibold text-[var(--wt-text-secondary)]">{col.label}</p>
        <span className="text-[11px] font-semibold text-[var(--wt-text-muted)] bg-black/[0.06] px-1.5 py-0.5 rounded-full">
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
  editNote: string;
  onStartEdit: () => void;
  onEditChange: (v: string) => void;
  onEditNoteChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onCycle: () => void;
  onSetStatus: (status: TodoStatus) => void;
  onProgressChange: (v: number) => void;
  onUpdateMeta: (fields: Pick<Partial<Todo>, "priority" | "due_date" | "progress_note" | "contact_person">) => void;
  onDelete: () => void;
  onOpenReport: (reportType: ReportType, date: string) => void;
  overlay?: boolean;
};

/** 状态圆圈：左键选择目标状态；右键沿用快捷状态切换。 */
function StatusPicker({
  status,
  onCycle,
  onSetStatus,
}: {
  status: TodoStatus;
  onCycle: () => void;
  onSetStatus: (status: TodoStatus) => void;
}) {
  const [open, setOpen] = useState(false);
  const choose = (next: TodoStatus) => {
    setOpen(false);
    onSetStatus(next);
  };

  const isDone = status === "done";
  const isProg = status === "in_progress";
  return (
    <div className="relative shrink-0 mt-0.5" onPointerDown={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((current) => !current); }}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(false); onCycle(); }}
        title="左键选择状态；右键直接切换状态"
        className={`w-4.5 h-4.5 rounded-full flex items-center justify-center transition-colors ${
          isDone
            ? "bg-[var(--wt-accent)] text-white"
            : isProg
              ? "border-2 border-[var(--wt-accent)] bg-[conic-gradient(var(--wt-accent)_50%,transparent_0)]"
              : "border-2 border-[var(--wt-text-faint)]"
        }`}
        aria-label="修改待办状态"
      >
        {isDone && <Check className="w-3 h-3" />}
      </button>
      {open && (
        <div
          className="absolute left-0 top-6 z-30 grid w-40 grid-cols-2 gap-1 rounded-lg border border-black/10 bg-white p-1.5 shadow-lg"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <p className="col-span-2 px-1 pb-0.5 text-[10px] text-[var(--wt-text-muted)]">选择状态</p>
          <button type="button" onClick={() => choose("pending")} className="rounded-md px-2 py-1 text-[11px] hover:bg-black/[0.05]">待办</button>
          <button type="button" onClick={() => choose("in_progress")} className="rounded-md px-2 py-1 text-[11px] hover:bg-black/[0.05]">进行中</button>
          <button type="button" onClick={() => choose("done")} className="rounded-md px-2 py-1 text-[11px] text-[var(--wt-accent)] hover:bg-[var(--wt-accent-bg)]">已完成</button>
          <button type="button" onClick={() => choose("cancelled")} className="rounded-md px-2 py-1 text-[11px] text-[var(--wt-danger)] hover:bg-red-50">删除</button>
        </div>
      )}
    </div>
  );
}

function TodoCardContent({
  todo,
  today,
  editing,
  editTitle,
  editNote,
  onStartEdit,
  onEditChange,
  onEditNoteChange,
  onSaveEdit,
  onCancelEdit,
  onCycle,
  onSetStatus,
  onProgressChange,
  onUpdateMeta,
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
      className={`group relative rounded-xl border bg-white/80 overflow-hidden transition-all hover:border-[rgba(101,184,30,0.3)] hover:shadow-sm ${
        overlay ? "shadow-xl rotate-1 cursor-grabbing" : ""
      } ${isDone ? "border-black/[0.06]" : "border-black/10"}`}
      style={{ backdropFilter: "blur(8px)" }}
    >
      {/* 优先级左色条 */}
      <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: pm.bar }} />

      <div className="flex items-start gap-2 pl-2.5 pr-2 py-2.5">
        <StatusPicker status={todo.status} onCycle={onCycle} onSetStatus={onSetStatus} />

        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="space-y-1.5" onPointerDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
              <input autoFocus value={editTitle} onChange={(e) => onEditChange(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") onCancelEdit(); }} placeholder="标题" className="w-full bg-transparent outline-none text-[13px] font-medium text-[var(--wt-text)] border-b border-[var(--wt-accent)]" />
              <textarea value={editNote} onChange={(e) => onEditNoteChange(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") onCancelEdit(); }} rows={3} placeholder="内容 / 备注" className="w-full resize-y rounded-md bg-black/[0.04] px-2 py-1 text-[12px] leading-relaxed outline-none text-[var(--wt-text-secondary)]" />
              <div className="flex justify-end gap-1.5"><button onClick={onCancelEdit} className="px-2 py-0.5 text-[11px] text-[var(--wt-text-muted)]">取消</button><button onClick={onSaveEdit} className="rounded-md bg-[var(--wt-accent)] px-2 py-0.5 text-[11px] font-medium text-white">保存</button></div>
            </div>
          ) : (
            <p
              onClick={onStartEdit}
              className={`text-[13px] font-medium leading-snug cursor-text ${
                isDone ? "text-[var(--wt-text-muted)] line-through" : "text-[var(--wt-text)]"
              }`}
            >
              {todo.title}
            </p>
          )}

          {!editing && todoContent(todo.note) && (
            <p onClick={onStartEdit} className="mt-1 text-[11.5px] leading-relaxed text-[var(--wt-text-secondary)] whitespace-pre-wrap cursor-text">
              {todoContent(todo.note)}
            </p>
          )}

          {!editing && (
            <ProgressNote
              value={todo.progress_note || ""}
              onSave={(progress_note) => onUpdateMeta({ progress_note })}
            />
          )}

          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <select
              value={todo.priority}
              onChange={(e) => onUpdateMeta({ priority: e.target.value as TodoPriority })}
              onPointerDown={(e) => e.stopPropagation()}
              title="修改重要程度"
              className={`appearance-none cursor-pointer text-[10.5px] font-semibold px-1.5 py-0.5 rounded-full outline-none ${pm.chip}`}
            >
              <option value="urgent">紧急</option>
              <option value="high">高</option>
              <option value="normal">中</option>
              <option value="low">低</option>
            </select>
            {/* 来源（可下钻到对应报告） */}
            {sm.manual ? (
              <span className="text-[11px] px-1.5 py-0.5 rounded-full font-medium text-[var(--wt-text-muted)] bg-black/[0.05]">
                {sm.label}
              </span>
            ) : (
              <button
                onClick={() => sm.reportType && onOpenReport(sm.reportType, sm.ref)}
                onPointerDown={(e) => e.stopPropagation()}
                title="查看来源报告"
                className="text-[11px] px-1.5 py-0.5 rounded-full font-medium text-[var(--wt-accent)] bg-[var(--wt-accent-bg)] hover:underline inline-flex items-center gap-0.5"
              >
                {sm.label}
                <ExternalLink className="w-2.5 h-2.5" />
              </button>
            )}
            {isDone ? (
              <span className="text-[11px] inline-flex items-center gap-0.5" style={{ color: "var(--wt-success)" }}>
                <Check className="w-2.5 h-2.5" /> 已完成
              </span>
            ) : (
              <label
                className={`text-[11px] inline-flex items-center gap-0.5 ${
                  overdue ? "text-[var(--wt-danger)] font-semibold" : "text-[var(--wt-text-muted)]"
                }`}
                title="修改计划完成日期"
              >
                <Calendar className="w-2.5 h-2.5" />
                <input
                  type="date"
                  value={todo.due_date || ""}
                  onChange={(e) => onUpdateMeta({ due_date: e.target.value })}
                  onPointerDown={(e) => e.stopPropagation()}
                  className="w-[68px] cursor-pointer bg-transparent text-[11px] outline-none [color-scheme:light]"
                  aria-label="计划完成日期"
                />
                {overdue && <span className="text-[10px]">逾期</span>}
              </label>
            )}
            <ContactPerson
              value={todo.contact_person || ""}
              onSave={(contact_person) => onUpdateMeta({ contact_person })}
            />
          </div>
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

function ContactPerson({ value, onSave }: { value: string; onSave: (value: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1" onPointerDown={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { onSave(draft.trim()); setEditing(false); }
            if (e.key === "Escape") setEditing(false);
          }}
          placeholder="对接人"
          className="w-20 rounded border border-[var(--wt-accent)] bg-white px-1 py-0.5 text-[11px] outline-none"
        />
        <button onClick={() => { onSave(draft.trim()); setEditing(false); }} className="text-[10px] font-medium text-[var(--wt-accent)]">保存</button>
      </span>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      onPointerDown={(e) => e.stopPropagation()}
      title="编辑对接人"
      className={`text-[11px] truncate ${value ? "text-[var(--wt-text-secondary)]" : "text-[var(--wt-text-faint)] hover:text-[var(--wt-accent)]"}`}
    >
      {value ? `对接：${value}` : "+ 添加对接人"}
    </button>
  );
}

function ProgressNote({ value, onSave }: { value: string; onSave: (value: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);

  if (editing) {
    return (
      <div className="mt-1.5 space-y-1" onPointerDown={(e) => e.stopPropagation()}>
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
          }}
          placeholder="逐项填写进度，例如：\n1. 已确认需求范围\n2. 等待客户回复"
          rows={3}
          className="w-full resize-y rounded-md border border-[var(--wt-accent)] bg-[var(--wt-accent-bg)] px-1.5 py-1 text-[11px] leading-relaxed outline-none"
        />
        <div className="flex items-center gap-2">
          <button onClick={() => setDraft((current) => `${current.trimEnd()}${current.trim() ? "\n" : ""}${progressItems(current).length + 1}. `)} className="text-[10px] text-[var(--wt-text-muted)] hover:text-[var(--wt-accent)]">+ 添加事项</button>
          <button onClick={() => { onSave(formatProgressItems(draft)); setEditing(false); }} className="text-[10px] font-medium text-[var(--wt-accent)]">保存</button>
        </div>
      </div>
    );
  }

  const items = progressItems(value);
  return (
    <button
      onClick={() => setEditing(true)}
      onPointerDown={(e) => e.stopPropagation()}
      className={`mt-1.5 block max-w-full text-left text-[11px] leading-relaxed ${
        value ? "text-[var(--wt-text-secondary)]" : "text-[var(--wt-text-faint)] hover:text-[var(--wt-accent)]"
      }`}
      title="编辑进度备注"
    >
      {items.length ? (
        <span className="block"><span className="mr-1 text-[var(--wt-text-muted)]">进度备注：</span>{items.map((item, index) => <span key={`${item}-${index}`} className="block pl-1">{index + 1}. {item}</span>)}</span>
      ) : "+ 添加进度备注"}
    </button>
  );
}

function progressItems(value: string): string[] {
  return (value || "")
    .split("\n")
    .map((line) => line.replace(/^\s*(?:\d+[.、]|[-•])\s*/, "").trim())
    .filter(Boolean);
}

function formatProgressItems(value: string): string {
  return progressItems(value).map((item, index) => `${index + 1}. ${item}`).join("\n");
}

// ==================== 草稿行 ====================

function DraftRow({
  todo,
  selected,
  editing,
  editTitle,
  editNote,
  onStartEdit,
  onEditChange,
  onEditNoteChange,
  onSaveEdit,
  onCancelEdit,
  onAdopt,
  onDrop,
  onToggleSelected,
}: {
  todo: Todo;
  selected: boolean;
  editing: boolean;
  editTitle: string;
  editNote: string;
  onStartEdit: () => void;
  onEditChange: (v: string) => void;
  onEditNoteChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onAdopt: () => void;
  onDrop: () => void;
  onToggleSelected: () => void;
}) {
  return (
    <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-white/60 border border-black/[0.07]">
      <button
        type="button"
        aria-label={selected ? "取消选择该待办" : "选择该待办"}
        aria-pressed={selected}
        onClick={onToggleSelected}
        className={`w-4 h-4 rounded border-[1.5px] shrink-0 flex items-center justify-center ${selected ? "bg-[var(--wt-accent)] border-[var(--wt-accent)] text-white" : "border-[var(--wt-text-faint)] hover:border-[var(--wt-accent)]"}`}
      >
        {selected && <Check className="w-3 h-3" />}
      </button>
      <div className="flex-1 min-w-0">
        {editing ? (
          <div className="space-y-1"><input autoFocus value={editTitle} onChange={(e) => onEditChange(e.target.value)} placeholder="标题" className="w-full bg-transparent outline-none text-[13px] text-[var(--wt-text)] border-b border-[var(--wt-accent)]" /><textarea value={editNote} onChange={(e) => onEditNoteChange(e.target.value)} rows={2} placeholder="内容 / 备注" className="w-full resize-y rounded bg-black/[0.04] px-2 py-1 text-[12px] outline-none" /><div className="flex justify-end gap-1"><button onClick={onCancelEdit} className="text-[11px] text-[var(--wt-text-muted)]">取消</button><button onClick={onSaveEdit} className="text-[11px] text-[var(--wt-accent)]">保存</button></div></div>
        ) : (
          <><p className="text-[13px] font-medium leading-snug text-[var(--wt-text)]">{todo.title}</p>{todoContent(todo.note) && <p className="mt-0.5 text-[11.5px] leading-relaxed text-[var(--wt-text-secondary)] whitespace-pre-wrap">{todoContent(todo.note)}</p>}</>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={onStartEdit}
          className="flex items-center gap-0.5 px-2 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-text-secondary)] border border-black/10 bg-white hover:bg-black/[0.06]"
        >
          <Pencil className="w-2.5 h-2.5" /> 编辑
        </button>
        <button
          onClick={onDrop}
          className="px-2 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-text-muted)] border border-black/10 bg-white hover:bg-[var(--wt-danger)] hover:text-white hover:border-[var(--wt-danger)]"
        >
          丢弃
        </button>
        <button
          onClick={onAdopt}
          className="flex items-center gap-0.5 px-2 py-1 rounded-md text-[11.5px] font-medium text-[var(--wt-success)] border border-[rgba(115,206,34,0.4)] bg-white hover:bg-[var(--wt-success)] hover:text-white"
        >
          <Check className="w-2.5 h-2.5" /> 采纳
        </button>
      </div>
    </div>
  );
}
