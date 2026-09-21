import { useEffect, useRef, useState } from "react";
import { Search, FileText, CheckSquare, StickyNote, Keyboard, CornerDownLeft } from "lucide-react";
import type { BlackboxApi, GlobalSearchResult } from "@/lib/pywebview";

interface Props {
  api: BlackboxApi | null
  open: boolean
  onClose: () => void
  onOpenReport: (type: string, date: string) => void
  onNavigateTodo: () => void
  onNavigateNote: (keyword: string) => void
  onSearchSegment: (text: string) => void
}

const EMPTY: GlobalSearchResult = { text_segments: [], notes: [], todos: [], reports: [] }

export function GlobalSearchModal({
  api, open, onClose,
  onOpenReport, onNavigateTodo, onNavigateNote, onSearchSegment,
}: Props) {
  const [keyword, setKeyword] = useState("")
  const [results, setResults] = useState<GlobalSearchResult>(EMPTY)
  const [searching, setSearching] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 打开时聚焦并重置
  useEffect(() => {
    if (open) {
      setKeyword("")
      setResults(EMPTY)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Esc 关闭
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  // 防抖搜索（350ms）
  useEffect(() => {
    if (!open) return
    if (timer.current) clearTimeout(timer.current)
    const kw = keyword.trim()
    if (!kw) {
      setResults(EMPTY)
      setSearching(false)
      return
    }
    setSearching(true)
    timer.current = setTimeout(async () => {
      try {
        const r = await api?.global_search(kw, 10)
        setResults(r ?? EMPTY)
      } catch {
        setResults(EMPTY)
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => {
      if (timer.current) clearTimeout(timer.current)
    }
  }, [keyword, api, open])

  if (!open) return null

  const kw = keyword.trim()
  const total = results.reports.length + results.todos.length + results.notes.length + results.text_segments.length

  const closeAnd = (fn: () => void) => () => {
    onClose()
    fn()
  }

  const Section = ({
    icon: Icon, title, color, children,
  }: { icon: typeof FileText; title: string; color: string; children: React.ReactNode }) => (
    <div className="mb-1">
      <div className="flex items-center gap-1.5 px-3 py-1.5 sticky top-0 bg-white z-10">
        <Icon className="w-3 h-3" style={{ color }} />
        <span className="text-[10px] font-semibold text-[var(--wt-text-muted)] uppercase tracking-wide">{title}</span>
      </div>
      {children}
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]" onMouseDown={onClose}>
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/25 backdrop-blur-[2px]" />

      {/* 面板 */}
      <div
        className="relative w-[560px] max-w-[90vw] rounded-2xl border border-[var(--wt-border)] bg-white shadow-2xl overflow-hidden"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* 输入框 */}
        <div className="flex items-center gap-2.5 px-4 h-12 border-b border-[var(--wt-border)]">
          <Search className="w-4 h-4 text-[var(--wt-text-muted)] shrink-0" />
          <input
            ref={inputRef}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索报告、待办、速记、输入记录..."
            className="flex-1 text-[13px] text-[var(--wt-text)] outline-none placeholder:text-[var(--wt-text-faint)] bg-transparent"
          />
          <kbd className="text-[10px] text-[var(--wt-text-faint)] border border-[var(--wt-border)] rounded px-1.5 py-0.5">Esc</kbd>
        </div>

        {/* 结果区 */}
        <div className="max-h-[380px] overflow-y-auto py-1.5">
          {!kw && (
            <div className="py-8 text-center">
              <p className="text-[11px] text-[var(--wt-text-muted)]">输入关键词，跨报告 / 待办 / 速记 / 输入记录搜索</p>
              <p className="text-[10px] text-[var(--wt-text-faint)] mt-1.5 flex items-center justify-center gap-1">
                <CornerDownLeft className="w-3 h-3" /> Ctrl + K 随时唤起
              </p>
            </div>
          )}
          {kw && searching && (
            <p className="py-8 text-center text-[11px] text-[var(--wt-text-muted)]">搜索中...</p>
          )}
          {kw && !searching && total === 0 && (
            <p className="py-8 text-center text-[11px] text-[var(--wt-text-muted)]">没有找到「{kw}」相关内容</p>
          )}

          {results.reports.length > 0 && (
            <Section icon={FileText} title="报告" color="#007aff">
              {results.reports.map((r, i) => (
                <button
                  key={`r${i}`}
                  onClick={closeAnd(() => onOpenReport(r.type, r.date))}
                  className="w-full text-left px-4 py-2 hover:bg-[var(--wt-bg)] transition-all"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium text-[var(--wt-text)]">
                      {r.type === "daily" ? "日报" : r.type === "weekly" ? "周报" : "月报"} · {r.date}
                    </span>
                  </div>
                  <p className="text-[10.5px] text-[var(--wt-text-muted)] mt-0.5 truncate">{r.excerpt.replace(/[#*\n]/g, " ").slice(0, 80)}</p>
                </button>
              ))}
            </Section>
          )}

          {results.todos.length > 0 && (
            <Section icon={CheckSquare} title="待办" color="#34c759">
              {results.todos.map((t) => (
                <button
                  key={`t${t.id}`}
                  onClick={closeAnd(onNavigateTodo)}
                  className="w-full text-left px-4 py-2 hover:bg-[var(--wt-bg)] transition-all"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-[var(--wt-text)] truncate">{t.title}</span>
                    <span className="ml-auto text-[10px] text-[var(--wt-text-faint)] shrink-0">
                      {t.status === "done" ? "已完成" : t.status === "in_progress" ? "进行中" : "待办"}
                    </span>
                  </div>
                </button>
              ))}
            </Section>
          )}

          {results.notes.length > 0 && (
            <Section icon={StickyNote} title="速记" color="#ff9500">
              {results.notes.map((n) => (
                <button
                  key={`n${n.id}`}
                  onClick={closeAnd(() => onNavigateNote(kw))}
                  className="w-full text-left px-4 py-2 hover:bg-[var(--wt-bg)] transition-all"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-[var(--wt-text)] truncate">{n.content}</span>
                    <span className="ml-auto text-[10px] text-[var(--wt-text-faint)] shrink-0">
                      {n.created_at.slice(5, 10)}
                    </span>
                  </div>
                </button>
              ))}
            </Section>
          )}

          {results.text_segments.length > 0 && (
            <Section icon={Keyboard} title="输入记录" color="#af52de">
              {results.text_segments.map((s) => (
                <button
                  key={`s${s.id}`}
                  onClick={closeAnd(() => onSearchSegment(s.text))}
                  className="w-full text-left px-4 py-2 hover:bg-[var(--wt-bg)] transition-all"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-[var(--wt-text)] truncate">{s.text}</span>
                    <span className="ml-auto text-[10px] text-[var(--wt-text-faint)] shrink-0">
                      {s.timestamp.slice(5, 16).replace("T", " ")}
                    </span>
                  </div>
                </button>
              ))}
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}
