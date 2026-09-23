import { useState, useEffect, useRef } from "react";
import {
  Pin,
  PinOff,
  Trash2,
  Send,
  StickyNote,
  Search,
  Link2,
  Tag,
  FolderOpen,
  Inbox,
  Check,
  X,
} from "lucide-react";
import type { BlackboxApi, Note, NoteTag, NoteStats, InboxStatus } from "@/lib/pywebview";
import { Empty } from "@/app/lib/utils";

export function QuickNoteView({
  api,
  initialKeyword = "",
}: {
  api: BlackboxApi | null;
  initialKeyword?: string;
}) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [tagCloud, setTagCloud] = useState<NoteTag[]>([]);
  const [stats, setStats] = useState<NoteStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [inputTags, setInputTags] = useState("");
  const [keyword, setKeyword] = useState(initialKeyword);
  const [activeTag, setActiveTag] = useState("");
  const [filterPinned, setFilterPinned] = useState(false);
  const [showInboxCfg, setShowInboxCfg] = useState(false);
  const [inboxInput, setInboxInput] = useState("");
  const [inboxStatus, setInboxStatus] = useState<InboxStatus | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const tagInputRef = useRef<HTMLInputElement>(null);

  const loadNotes = async (tag = activeTag) => {
    if (!api) return;
    setLoading(true);
    const list = await api.get_notes(200, 0, tag);
    setNotes(list);
    setLoading(false);
  };

  const loadMeta = async () => {
    if (!api) return;
    try {
      const [tags, st] = await Promise.all([api.get_note_tags(), api.get_note_stats()]);
      setTagCloud(tags || []);
      setStats(st || null);
      if (st?.inbox_dir !== undefined) setInboxInput(st.inbox_dir || "");
      if (st?.inbox) setInboxStatus(st.inbox);
    } catch {
      /* 元信息失败不影响主列表 */
    }
  };

  useEffect(() => {
    loadNotes();
    loadMeta();
  }, [api]);

  // Ctrl+Alt+I 全局快捷键：后端派发事件 → 聚焦速记输入框（视图切换由 App 负责）
  useEffect(() => {
    const focus = () => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    };
    window.addEventListener("wt:open-note-capture", focus);
    return () => window.removeEventListener("wt:open-note-capture", focus);
  }, []);

  const addNote = async () => {
    if (!api || !input.trim()) return;
    const r = await api.add_note(input.trim(), "manual", "", null, false, inputTags);
    if (r?.ok === false) {
      setNotice({ kind: "err", msg: r.error || "保存失败" });
      return;
    }
    setInput("");
    setInputTags("");
    setNotice(
      r?.inbox_path
        ? { kind: "ok", msg: "已保存并落盘洞察收件箱" }
        : { kind: "ok", msg: "已保存" },
    );
    setTimeout(() => setNotice(null), 2200);
    await loadNotes();
    await loadMeta();
    inputRef.current?.focus();
  };

  const togglePin = async (note: Note) => {
    if (!api) return;
    await api.update_note(note.id, { pinned: !note.pinned });
    await loadNotes();
    await loadMeta();
  };

  const deleteNote = async (note: Note) => {
    if (!api) return;
    await api.delete_note(note.id);
    await loadNotes();
    await loadMeta();
  };

  const pickTag = async (tag: string) => {
    const next = activeTag === tag ? "" : tag;
    setActiveTag(next);
    await loadNotes(next);
  };

  const saveInbox = async () => {
    if (!api) return;
    const r = await api.save_insight_config(inboxInput.trim());
    if (r?.ok === false) {
      setNotice({ kind: "err", msg: r.error || "保存失败" });
      return;
    }
    setInboxStatus((r?.status as InboxStatus) || null);
    setNotice({ kind: "ok", msg: r?.inbox_dir ? "收件箱已配置" : "已关闭落盘" });
    setTimeout(() => setNotice(null), 2200);
    await loadMeta();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      addNote();
    }
  };

  // 过滤显示
  let display = notes;
  if (filterPinned) display = display.filter((n) => n.pinned);
  if (keyword.trim()) {
    const kw = keyword.toLowerCase();
    display = display.filter(
      (n) => n.content.toLowerCase().includes(kw) || (n.tags || "").toLowerCase().includes(kw),
    );
  }

  const pinnedCount = notes.filter((n) => n.pinned).length;
  const inbox = inboxStatus || stats?.inbox;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* 页头 */}
      <div className="px-6 pt-5 pb-2 shrink-0">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">速记</h1>
            <p className="text-[11px] text-[var(--wt-text-muted)] mt-0.5">
              快速记录灵感 · Ctrl+Alt+I 随处呼出 · 回车保存 · 支持标签
            </p>
          </div>
          {/* 指标（v5.4） */}
          {stats && (
            <div className="flex items-center gap-1.5 shrink-0">
              {[
                { label: "今日", value: stats.today },
                { label: "本周", value: stats.week },
                { label: "累计", value: stats.total },
                { label: "置顶", value: stats.pinned },
              ].map((m) => (
                <div
                  key={m.label}
                  className="px-2.5 py-1 rounded-lg bg-white border border-[var(--wt-border)] text-center min-w-[52px]"
                >
                  <div className="text-[13px] font-semibold text-[var(--wt-text)] leading-tight">
                    {m.value}
                  </div>
                  <div className="text-[9px] text-[var(--wt-text-muted)]">{m.label}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 输入区 */}
      <div className="px-6 pb-2 shrink-0">
        <div className="rounded-xl border border-[var(--wt-border)] bg-white p-3 shadow-sm focus-within:ring-1 focus-within:ring-[var(--wt-accent)]/30">
          <div className="flex items-end gap-2">
            <StickyNote className="w-4 h-4 text-[var(--wt-text-muted)] shrink-0 mb-1.5" />
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="快速记录一条速记...（Enter 保存 · Shift+Enter 换行）"
              rows={1}
              className="flex-1 resize-none outline-none text-[13px] text-[var(--wt-text)] placeholder:text-[var(--wt-text-muted)] bg-transparent leading-relaxed"
              style={{ minHeight: "24px", maxHeight: "80px" }}
            />
            <button
              onClick={addNote}
              disabled={!input.trim()}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 disabled:opacity-40 transition-all shrink-0"
            >
              <Send className="w-3 h-3" />
              保存
            </button>
          </div>
          {/* 标签输入（v5.4） */}
          <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-[var(--wt-border)]/60">
            <Tag className="w-3.5 h-3.5 text-[var(--wt-text-muted)] shrink-0" />
            <input
              ref={tagInputRef}
              value={inputTags}
              onChange={(e) => setInputTags(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addNote();
                }
              }}
              placeholder="标签（可选，逗号分隔，如：客户,竞品）"
              className="flex-1 bg-transparent outline-none text-[11px] text-[var(--wt-text)] placeholder:text-[var(--wt-text-muted)]"
            />
            {notice && (
              <span
                className={`text-[10px] flex items-center gap-0.5 shrink-0 ${
                  notice.kind === "ok" ? "text-[var(--wt-success)]" : "text-[var(--wt-danger)]"
                }`}
              >
                {notice.kind === "ok" ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                {notice.msg}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 工具栏 */}
      <div className="px-6 pb-2 flex items-center gap-2 flex-wrap shrink-0">
        <div className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 bg-white border border-[var(--wt-border)]">
          <Search className="w-3.5 h-3.5 text-[var(--wt-text-muted)]" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索速记/标签..."
            className="bg-transparent outline-none text-[11px] text-[var(--wt-text)] w-36 placeholder:text-[var(--wt-text-muted)]"
          />
        </div>
        <button
          onClick={() => setFilterPinned((v) => !v)}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all border ${
            filterPinned
              ? "bg-[var(--wt-warning)] text-white border-transparent"
              : "bg-white text-[var(--wt-text-secondary)] border-[var(--wt-border)] hover:bg-[var(--wt-bg)]"
          }`}
        >
          <Pin className="w-3 h-3" />
          仅看置顶
        </button>

        {/* 收件箱状态 + 配置入口（v5.4） */}
        <button
          onClick={() => setShowInboxCfg((v) => !v)}
          title={inbox?.dir || "未配置收件箱"}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all border ${
            showInboxCfg
              ? "bg-[var(--wt-accent)] text-white border-transparent"
              : "bg-white text-[var(--wt-text-secondary)] border-[var(--wt-border)] hover:bg-[var(--wt-bg)]"
          }`}
        >
          <Inbox className="w-3 h-3" />
          洞察收件箱
          {inbox?.configured && inbox.writable ? (
            <span className="text-[9px] opacity-80">· {inbox.count} 待处理</span>
          ) : (
            <span className="text-[9px] opacity-60">· 未配置</span>
          )}
        </button>

        <span className="text-[10px] text-[var(--wt-text-muted)] ml-auto">
          {activeTag && <span className="mr-2">标签：{activeTag}</span>}
          {display.length} 条显示 · {pinnedCount} 条置顶
        </span>
      </div>

      {/* 标签云（v5.4） */}
      {tagCloud.length > 0 && (
        <div className="px-6 pb-2 flex items-center gap-1.5 flex-wrap shrink-0">
          <Tag className="w-3 h-3 text-[var(--wt-text-muted)] shrink-0" />
          {tagCloud.slice(0, 24).map((t) => (
            <button
              key={t.tag}
              onClick={() => pickTag(t.tag)}
              className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border ${
                activeTag === t.tag
                  ? "bg-[var(--wt-accent)] text-white border-transparent"
                  : "bg-white text-[var(--wt-text-secondary)] border-[var(--wt-border)] hover:bg-[var(--wt-bg)]"
              }`}
            >
              {t.tag}
              <span className="ml-1 opacity-60">{t.count}</span>
            </button>
          ))}
          {activeTag && (
            <button
              onClick={() => pickTag(activeTag)}
              className="text-[10px] text-[var(--wt-text-muted)] hover:text-[var(--wt-text)] underline ml-1"
            >
              清除筛选
            </button>
          )}
        </div>
      )}

      {/* 收件箱配置面板（v5.4） */}
      {showInboxCfg && (
        <div className="mx-6 mb-2 rounded-xl border border-[var(--wt-border)] bg-white p-3 shrink-0">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-3.5 h-3.5 text-[var(--wt-accent)] shrink-0" />
            <span className="text-[11px] font-medium text-[var(--wt-text)]">
              洞察收件箱目录
            </span>
            <span className="text-[10px] text-[var(--wt-text-muted)]">
              速记保存时同步落盘为 Markdown，供「每日洞察」AI 蒸馏消费；留空 = 仅入库
            </span>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <input
              value={inboxInput}
              onChange={(e) => setInboxInput(e.target.value)}
              placeholder="例如：D:\AI 学习\AI 蒸馏\每日洞察\00_收件箱"
              className="flex-1 px-2.5 py-1.5 rounded-lg border border-[var(--wt-border)] bg-[var(--wt-bg)] outline-none text-[11px] text-[var(--wt-text)] placeholder:text-[var(--wt-text-muted)] focus:ring-1 focus:ring-[var(--wt-accent)]/30"
            />
            <button
              onClick={saveInbox}
              className="px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 transition-all shrink-0"
            >
              保存
            </button>
          </div>
          <div className="flex items-center gap-3 mt-2 text-[10px]">
            <span
              className={
                inbox?.configured && inbox.writable
                  ? "text-[var(--wt-success)]"
                  : "text-[var(--wt-text-muted)]"
              }
            >
              {!inbox?.configured
                ? "未配置（速记仅入库）"
                : inbox.writable
                  ? `已连接 · ${inbox.count} 个待处理文件`
                  : inbox.exists
                    ? "目录不可写，请检查权限"
                    : "目录不存在，保存时会自动创建"}
            </span>
            {inbox?.dir && (
              <span className="text-[var(--wt-text-muted)] truncate">· {inbox.dir}</span>
            )}
          </div>
        </div>
      )}

      {/* 速记列表 */}
      <div className="flex-1 overflow-y-auto px-6 pb-5">
        {loading ? (
          <p className="text-[12px] text-[var(--wt-text-muted)] py-8 text-center">加载中...</p>
        ) : display.length === 0 ? (
          <Empty
            icon={StickyNote}
            text={activeTag || keyword ? "没有匹配的速记" : "暂无速记"}
            hint={activeTag || keyword ? "换个关键词或清除标签筛选" : "在上方输入框快速记录一条"}
          />
        ) : (
          <div className="space-y-1.5">
            {display.map((note) => (
              <div
                key={note.id}
                className={`group flex items-start gap-2.5 rounded-xl border p-3 transition-all ${
                  note.pinned
                    ? "border-[var(--wt-warning)]/30 bg-[rgba(245,158,11,0.04)]"
                    : "border-[var(--wt-border)] bg-white hover:shadow-sm"
                }`}
              >
                {/* 置顶/操作按钮列 */}
                <div className="flex flex-col gap-1 shrink-0 pt-0.5">
                  <button
                    onClick={() => togglePin(note)}
                    className={`w-5 h-5 flex items-center justify-center rounded transition-all ${
                      note.pinned
                        ? "text-[var(--wt-warning)]"
                        : "text-[var(--wt-text-muted)] opacity-0 group-hover:opacity-100 hover:text-[var(--wt-warning)]"
                    }`}
                    title={note.pinned ? "取消置顶" : "置顶"}
                  >
                    {note.pinned ? <Pin className="w-3.5 h-3.5" /> : <PinOff className="w-3.5 h-3.5" />}
                  </button>
                </div>

                {/* 内容区 */}
                <div className="flex-1 min-w-0">
                  <p className="text-[12.5px] text-[var(--wt-text)] leading-relaxed whitespace-pre-wrap break-words">
                    {note.content}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className="text-[10px] text-[var(--wt-text-muted)]">
                      {note.created_at.slice(0, 16).replace("T", " ")}
                    </span>
                    {note.source === "hotkey" && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[var(--wt-accent-bg)] text-[var(--wt-accent)] font-medium">
                        快捷键
                      </span>
                    )}
                    {note.source === "report" && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-[rgba(175,82,222,0.1)] text-[#af52de] font-medium">
                        报告 {note.source_ref.slice(5)}
                      </span>
                    )}
                    {note.linked_todo_id && (
                      <span className="flex items-center gap-0.5 text-[9px] text-[var(--wt-text-muted)]">
                        <Link2 className="w-2.5 h-2.5" />
                        关联待办
                      </span>
                    )}
                    {/* 标签（v5.4） */}
                    {(note.tags || "")
                      .split(",")
                      .map((t) => t.trim())
                      .filter(Boolean)
                      .map((t) => (
                        <button
                          key={t}
                          onClick={() => pickTag(t)}
                          className={`text-[9px] px-1.5 py-0.5 rounded font-medium transition-all ${
                            activeTag === t
                              ? "bg-[var(--wt-accent)] text-white"
                              : "bg-black/[0.05] text-[var(--wt-text-secondary)] hover:bg-black/[0.09]"
                          }`}
                        >
                          #{t}
                        </button>
                      ))}
                  </div>
                </div>

                {/* 删除按钮 */}
                <button
                  onClick={() => deleteNote(note)}
                  className="w-5 h-5 flex items-center justify-center rounded text-[var(--wt-text-muted)] opacity-0 group-hover:opacity-100 hover:text-[var(--wt-danger)] transition-all shrink-0 pt-0.5"
                  title="删除"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
