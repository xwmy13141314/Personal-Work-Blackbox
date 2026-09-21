import { useState, useEffect, useRef } from "react";
import {
  Pin,
  PinOff,
  Trash2,
  Send,
  StickyNote,
  Search,
  Link2,
} from "lucide-react";
import type { BlackboxApi, Note } from "@/lib/pywebview";
import { Empty } from "@/app/lib/utils";

export function QuickNoteView({
  api,
  initialKeyword = "",
}: {
  api: BlackboxApi | null;
  initialKeyword?: string;
}) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [keyword, setKeyword] = useState(initialKeyword);
  const [filterPinned, setFilterPinned] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const loadNotes = async () => {
    if (!api) return;
    setLoading(true);
    const list = await api.get_notes(200);
    setNotes(list);
    setLoading(false);
  };

  useEffect(() => {
    loadNotes();
  }, [api]);

  const addNote = async () => {
    if (!api || !input.trim()) return;
    await api.add_note(input.trim(), "manual");
    setInput("");
    await loadNotes();
    inputRef.current?.focus();
  };

  const togglePin = async (note: Note) => {
    if (!api) return;
    await api.update_note(note.id, { pinned: !note.pinned });
    await loadNotes();
  };

  const deleteNote = async (note: Note) => {
    if (!api) return;
    await api.delete_note(note.id);
    await loadNotes();
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
    display = display.filter((n) => n.content.toLowerCase().includes(kw));
  }

  const pinnedCount = notes.filter((n) => n.pinned).length;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* 页头 */}
      <div className="px-6 pt-5 pb-3 shrink-0">
        <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">速记</h1>
        <p className="text-[11px] text-[var(--wt-text-muted)] mt-0.5">
          快速记录灵感 · 回车保存 · 置顶重要 · {notes.length} 条速记 · {pinnedCount} 条置顶
        </p>
      </div>

      {/* 输入区 */}
      <div className="px-6 pb-3 shrink-0">
        <div className="flex items-end gap-2 rounded-xl border border-[var(--wt-border)] bg-white p-3 shadow-sm focus-within:ring-1 focus-within:ring-[var(--wt-accent)]/30">
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
      </div>

      {/* 工具栏 */}
      <div className="px-6 pb-2 flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 bg-white border border-[var(--wt-border)]">
          <Search className="w-3.5 h-3.5 text-[var(--wt-text-muted)]" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索速记..."
            className="bg-transparent outline-none text-[11px] text-[var(--wt-text)] w-40 placeholder:text-[var(--wt-text-muted)]"
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
        <span className="text-[10px] text-[var(--wt-text-muted)] ml-auto">
          {display.length} 条显示
        </span>
      </div>

      {/* 速记列表 */}
      <div className="flex-1 overflow-y-auto px-6 pb-5">
        {loading ? (
          <p className="text-[12px] text-[var(--wt-text-muted)] py-8 text-center">加载中...</p>
        ) : display.length === 0 ? (
          <Empty icon={StickyNote} text="暂无速记" hint="在上方输入框快速记录一条" />
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
                  <div className="flex items-center gap-2 mt-1.5">
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
