import React, { useState, useEffect } from "react";
import { Activity, Search } from "lucide-react";
import { fmtDuration, Empty } from "@/app/lib/utils";
import type { BlackboxApi, SessionItem, SessionDetail, SearchResult } from "@/lib/pywebview";

// ==================== 活动明细视图（含搜索结果） ====================

export function ActivityView({
  api,
  date,
  search,
  onClearSearch,
  onPickDate,
}: {
  api: BlackboxApi | null;
  date: string;
  search: string;
  onClearSearch: () => void;
  onPickDate: (d: string) => void;
}) {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const q = search.trim();
  const mode: "search" | "list" = q ? "search" : "list";

  useEffect(() => {
    if (!api) return;
    setLoading(true);
    setExpanded(null);
    setDetail(null);
    const t = setTimeout(() => {
      if (q) {
        api.search_text(q).then((r) => {
          setResults(r.results);
          setLoading(false);
        });
      } else {
        api.get_sessions(date).then((s) => {
          setSessions(s);
          setLoading(false);
        });
      }
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, date, q]);

  const openDetail = async (id: number) => {
    if (!api) return;
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    setDetail(null);
    const d = await api.get_session_detail(id);
    setDetail(d);
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">
          {mode === "search" ? `搜索“${q}”` : `活动明细 · ${date}`}
        </h1>
        {mode === "search" && (
          <button onClick={onClearSearch} className="text-[11px] text-[var(--wt-accent)] hover:underline">
            清除搜索
          </button>
        )}
      </div>

      <div className="space-y-2">
        {loading ? (
          <p className="text-[12px] text-[var(--wt-text-muted)] py-8 text-center">加载中...</p>
        ) : mode === "search" ? (
          results.length ? (
            results.map((r) => (
              <div key={r.id} className="rounded-xl border border-black/10 bg-white/70 p-3">
                <div className="flex justify-between text-[10px] text-[var(--wt-text-muted)]">
                  <button onClick={() => onPickDate(r.date)} className="text-[var(--wt-accent)] hover:underline">
                    {r.date}
                  </button>
                  <span>
                    {r.process_name || "未知"} · {r.source === "clipboard" ? "剪贴板" : "输入"}
                  </span>
                </div>
                <p className="text-[12px] mt-1 text-[var(--wt-text)] line-clamp-2 break-all">
                  {r.is_filtered ? "（已隐私过滤）" : r.text}
                </p>
                {r.window_title && <p className="text-[10px] text-[var(--wt-text-faint)] truncate mt-0.5">{r.window_title}</p>}
              </div>
            ))
          ) : (
            <Empty icon={Search} text={`未找到“${q}”相关记录`} hint="试试其他关键词，或清除搜索查看当日活动" />
          )
        ) : sessions.length ? (
          sessions.map((s) => (
            <div key={s.id} className="rounded-xl border border-black/10 bg-white/70 overflow-hidden">
              <button onClick={() => openDetail(s.id)} className="w-full flex items-center justify-between p-3 text-left hover:bg-black/[0.02]">
                <div className="min-w-0">
                  <p className="text-[12px] font-medium text-[var(--wt-text)] truncate flex items-center gap-1.5">
                    {s.process_name || "未知应用"}
                    {s.segment_count != null && s.segment_count > 0 && (
                      <span className="inline-block text-[9px] bg-[var(--wt-accent)] text-white px-1.5 py-0.5 rounded-full leading-none">
                        {s.segment_count} 条输入
                      </span>
                    )}
                  </p>
                  <p className="text-[10px] text-[var(--wt-text-muted)] truncate">{s.window_title || "（无窗口标题）"}</p>
                </div>
                <div className="text-right shrink-0 ml-2">
                  <p className="text-[11px] font-medium text-[var(--wt-text)]">{fmtDuration(s.active_seconds)}</p>
                  <p className="text-[10px] text-[var(--wt-text-muted)]">{s.start_time.slice(11, 16)}</p>
                </div>
              </button>
              {expanded === s.id && (
                <div className="px-3 pb-3 pt-2 border-t border-black/[0.06] space-y-1 max-h-52 overflow-y-auto">
                  {detail === null ? (
                    <p className="text-[11px] text-[var(--wt-text-muted)]">加载中...</p>
                  ) : detail.segments.length ? (
                    detail.segments.map((seg, i) => (
                      <p key={i} className="text-[11px] text-[var(--wt-text-secondary)] break-all">
                        <span className="text-[var(--wt-text-muted)] mr-1">{seg.timestamp.slice(11, 16)}</span>
                        {seg.is_filtered ? "（已隐私过滤）" : seg.raw_text}
                      </p>
                    ))
                  ) : (
                    <p className="text-[11px] text-[var(--wt-text-muted)]">该应用期间无文本输入记录（仅有窗口活动时长）。可能原因：未按回车/Tab提交、输入被隐私过滤、或在此窗口中仅浏览未输入。</p>
                  )}
                </div>
              )}
            </div>
          ))
        ) : (
          <Empty icon={Activity} text={`${date} 无会话记录`} hint="启动录制后，这里会展示各应用的输入明细" />
        )}
      </div>
    </div>
  );
}
