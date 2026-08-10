import { useState, useEffect } from "react";
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
  Download,
} from "lucide-react";
import { Empty } from "@/app/lib/utils";
import type { BlackboxApi, Todo, TodoStatus, TodoPriority, TaskStatus } from "@/lib/pywebview";

// ==================== 待办视图 ====================

// 优先级 → 显示标签 + 配色（后端 4 级映射到 mockup 的 3 档视觉：urgent/high→高，normal→中，low→低）
const PRI_META: Record<TodoPriority, { label: string; cls: string }> = {
  urgent: { label: "紧急", cls: "text-[var(--wt-danger)] bg-[rgba(255,59,48,0.1)]" },
  high: { label: "高", cls: "text-[var(--wt-danger)] bg-[rgba(255,59,48,0.1)]" },
  normal: { label: "中", cls: "text-[#b76b00] bg-[rgba(255,159,10,0.12)]" },
  low: { label: "低", cls: "text-[var(--wt-text-muted)] bg-black/[0.06]" },
};

// 三态复选框循环：pending → in_progress → done → pending
const STATUS_CYCLE: Record<TodoStatus, TodoStatus> = {
  pending: "in_progress",
  in_progress: "done",
  done: "pending",
  cancelled: "pending",
};

// 来源标签
function sourceMeta(t: Todo): { label: string; manual: boolean } {
  if (t.source_type === "manual" || !t.source_type) return { label: "手动", manual: true };
  const map: Record<string, string> = { daily_report: "日报", weekly_report: "周报", monthly_report: "月报" };
  const name = map[t.source_type] ?? "报告";
  const ref = t.source_ref ? ` ${t.source_ref.slice(5).replace("-", "/")}` : ""; // MM-DD → MM/DD
  return { label: name + ref, manual: false };
}

// 截止日期显示
function dueLabel(due: string, today: string): string | null {
  if (!due) return null;
  if (due === today) return "今天";
  return due.slice(5).replace("-", "/"); // MM/DD
}

export function TodoView({ api, date }: { api: BlackboxApi | null; date: string }) {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [drafts, setDrafts] = useState<Todo[]>([]);
  const [filter, setFilter] = useState<"all" | TodoStatus>("all");
  const [loading, setLoading] = useState(true);
  const [draftOpen, setDraftOpen] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err" | null; msg: string }>({ kind: null, msg: "" });
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
    const all = await api.get_todos(null, true);
    setTodos(all.filter((t) => !t.is_draft && t.status !== "cancelled"));
    setDrafts(all.filter((t) => t.is_draft));
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
            msg: n > 0 ? `已提取 ${n} 条待办到草稿区，请确认` : "今日报告未提取到待办（可能当日日报尚未生成或无可执行项）",
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

  // 导出表格（按当前筛选，CSV；Excel / 飞书多维表格可直接打开）
  const exportCsv = async () => {
    if (!api) return;
    const status = filter === "all" ? null : filter;
    const r = await api.export_todos(status, true);
    setNotice(
      r.ok
        ? { kind: "ok", msg: `已导出 ${r.count ?? ""} 条待办：${r.filename}` }
        : { kind: "err", msg: r.error || "导出失败" },
    );
  };

  // 三态切换
  const cycleStatus = async (t: Todo) => {
    if (!api) return;
    await api.update_todo(t.id, { status: STATUS_CYCLE[t.status] });
    await reload();
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

  // 正式待办删除（hover 出现，直接删，可重建）
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

  // 计数
  const counts = {
    all: todos.length,
    pending: todos.filter((t) => t.status === "pending").length,
    in_progress: todos.filter((t) => t.status === "in_progress").length,
    done: todos.filter((t) => t.status === "done").length,
  };
  const filtered = filter === "all" ? todos : todos.filter((t) => t.status === filter);

  const TABS: { key: "all" | TodoStatus; label: string; cnt: number }[] = [
    { key: "all", label: "全部", cnt: counts.all },
    { key: "pending", label: "待办", cnt: counts.pending },
    { key: "in_progress", label: "进行中", cnt: counts.in_progress },
    { key: "done", label: "已完成", cnt: counts.done },
  ];

  return (
    <>
      {/* Toolbar */}
      <div
        className="flex items-center gap-2 px-5 h-11 shrink-0 border-b border-black/[0.07]"
        style={{ background: "rgba(245,245,247,0.8)", backdropFilter: "blur(20px)" }}
      >
        <div className="flex gap-0.5 bg-black/[0.06] rounded-full p-0.5">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setFilter(t.key)}
              className={`px-3 py-0.5 rounded-full text-[11px] font-medium transition-all ${
                filter === t.key
                  ? "bg-[var(--wt-accent)] text-white shadow-sm"
                  : "text-[var(--wt-text-tertiary)] hover:bg-black/[0.05]"
              }`}
            >
              {t.label}
              <span className={`ml-0.5 text-[10px] ${filter === t.key ? "opacity-80" : "opacity-70"}`}>{t.cnt}</span>
            </button>
          ))}
        </div>

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
          <Download className="w-3 h-3" /> 导出表格
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
        <div>
          <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">待办跟进</h1>
          <p className="text-[11px] text-[var(--wt-text-muted)] mt-0.5">
            从日报自动提取，状态由你掌控 · {counts.in_progress + counts.pending} 条进行中
            {drafts.length ? `，${drafts.length} 条待确认` : ""}
          </p>
        </div>

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
            <p className={`text-[11.5px] ${notice.kind === "ok" ? "text-green-700" : "text-orange-700"}`}>{notice.msg}</p>
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
                <p className="text-[12px] font-semibold text-[var(--wt-text)]">AI 提取了 {drafts.length} 条待办待确认</p>
                <p className="text-[11px] text-[var(--wt-text-muted)]">来源：{sourceMeta(drafts[0]).label} · 请确认后入库</p>
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

        {/* 待办列表标题 */}
        <div className="flex items-center gap-1.5 mt-4 mb-1 px-0.5">
          <p className="text-[12px] font-semibold text-[var(--wt-text-tertiary)]">进行中与待办</p>
          <span className="text-[10px] font-semibold text-[var(--wt-text-muted)] bg-black/[0.06] px-1.5 py-0.5 rounded-full">
            {counts.pending + counts.in_progress} 条
          </span>
        </div>

        <div className="flex flex-col gap-1.5">
          {loading ? (
            <p className="text-[12px] text-[var(--wt-text-muted)] py-8 text-center">加载中...</p>
          ) : filtered.length ? (
            filtered.map((t) => (
              <TodoRow
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
                onDelete={() => remove(t.id)}
              />
            ))
          ) : (
            <Empty icon={CheckSquare} text={filter === "all" ? "还没有待办，点「新建待办」或「从报告提取」开始" : "该分类暂无待办"} />
          )}
        </div>
      </div>
    </>
  );
}

// ==================== 正式待办行 ====================

function TodoRow({
  todo,
  today,
  editing,
  editTitle,
  onStartEdit,
  onEditChange,
  onSaveEdit,
  onCancelEdit,
  onCycle,
  onDelete,
}: {
  todo: Todo;
  today: string;
  editing: boolean;
  editTitle: string;
  onStartEdit: () => void;
  onEditChange: (v: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onCycle: () => void;
  onDelete: () => void;
}) {
  const pm = PRI_META[todo.priority];
  const sm = sourceMeta(todo);
  const isDone = todo.status === "done";
  const isProg = todo.status === "in_progress";
  const due = dueLabel(todo.due_date, today);
  const overdue = !!todo.due_date && !isDone && todo.due_date < today;

  return (
    <div
      className={`group flex items-center gap-3 px-3.5 py-2.5 rounded-xl border border-black/10 bg-white/70 transition-all hover:border-[rgba(0,113,227,0.25)] ${
        isDone ? "opacity-70" : ""
      }`}
      style={{ backdropFilter: "blur(8px)" }}
    >
      {/* 三态复选框 */}
      <button
        onClick={onCycle}
        className="w-[18px] h-[18px] rounded-full border-[1.6px] flex items-center justify-center shrink-0 transition-all"
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
            className="w-full bg-transparent outline-none text-[12.5px] font-medium text-[var(--wt-text)] border-b border-[var(--wt-accent)]"
          />
        ) : (
          <p
            onClick={onStartEdit}
            className={`text-[12.5px] font-medium leading-snug cursor-text ${
              isDone ? "text-[var(--wt-text-muted)] line-through" : "text-[var(--wt-text)]"
            }`}
          >
            {todo.title}
          </p>
        )}
        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span className={`text-[9.5px] font-semibold px-1.5 py-0.5 rounded-full ${pm.cls}`}>{pm.label}</span>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              sm.manual ? "text-[var(--wt-text-muted)] bg-black/[0.05]" : "text-[var(--wt-accent)] bg-[var(--wt-accent-bg)]"
            }`}
          >
            {sm.label}
          </span>
          {isDone ? (
            <span className="text-[10px] inline-flex items-center gap-0.5" style={{ color: "var(--wt-success)" }}>
              <Check className="w-2.5 h-2.5" /> 已完成
            </span>
          ) : due ? (
            <span
              className={`text-[10px] inline-flex items-center gap-0.5 ${
                overdue ? "text-[var(--wt-danger)]" : "text-[var(--wt-text-muted)]"
              }`}
            >
              <Calendar className="w-2.5 h-2.5" /> {overdue ? "逾期 " : ""}
              {due}
            </span>
          ) : null}
          {todo.note && <span className="text-[10px] text-[var(--wt-text-faint)] truncate">{todo.note}</span>}
        </div>
      </div>

      {/* hover 操作 */}
      <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onStartEdit}
          className="p-1 rounded-md hover:bg-black/[0.06] text-[var(--wt-text-muted)]"
          title="编辑"
        >
          <Pencil className="w-3 h-3" />
        </button>
        <button
          onClick={onDelete}
          className="p-1 rounded-md hover:bg-[var(--wt-danger)] hover:text-white text-[var(--wt-text-muted)]"
          title="删除"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
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
