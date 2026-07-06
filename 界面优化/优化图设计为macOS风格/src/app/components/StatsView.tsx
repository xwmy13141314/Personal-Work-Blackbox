import React, { useState, useEffect } from "react";
import { BarChart3 } from "lucide-react";
import { fmtDuration, Empty } from "@/app/lib/utils";
import type { BlackboxApi, AppStats } from "@/lib/pywebview";

// ==================== 统计视图 ====================

export function StatsView({ api, date }: { api: BlackboxApi | null; date: string }) {
  const [rangeType, setRangeType] = useState<"today" | "week" | "month">("today");
  const [data, setData] = useState<AppStats | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!api || !date) return;
    setLoading(true);
    api.get_app_stats(rangeType, date).then((d) => {
      setData(d);
      setLoading(false);
    });
  }, [api, date, rangeType]);

  const maxActive = data && data.items.length ? Math.max(...data.items.map((i) => i.active_seconds), 1) : 1;

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">应用统计</h1>
        <div className="flex gap-1 bg-black/[0.06] rounded-full p-0.5">
          {(["today", "week", "month"] as const).map((rt) => (
            <button
              key={rt}
              onClick={() => setRangeType(rt)}
              className={`px-3 py-0.5 rounded-full text-[11px] font-medium transition-all ${
                rangeType === rt ? "bg-[var(--wt-accent)] text-white shadow-sm" : "text-[var(--wt-text-secondary)] hover:bg-black/[0.06]"
              }`}
            >
              {rt === "today" ? "今日" : rt === "week" ? "本周" : "本月"}
            </button>
          ))}
        </div>
      </div>
      {data && (
        <p className="text-[11px] text-[var(--wt-text-muted)]">
          {data.range.start} ~ {data.range.end} · 总活跃 {fmtDuration(data.total_active)} · {data.items.length} 个应用
        </p>
      )}

      <div className="rounded-xl border border-black/10 bg-white/70 p-4 space-y-3" style={{ backdropFilter: "blur(8px)" }}>
        {loading ? (
          <p className="text-[12px] text-[var(--wt-text-muted)] py-8 text-center">加载中...</p>
        ) : data && data.items.length ? (
          data.items.map((it, i) => (
            <div key={i}>
              <div className="flex justify-between items-center text-[11px]">
                <span className="font-medium text-[var(--wt-text)] truncate">{it.process_name || "未知应用"}</span>
                <span className="text-[var(--wt-text-tertiary)] shrink-0 ml-2">
                  {fmtDuration(it.active_seconds)} · {it.session_count} 次
                </span>
              </div>
              <div className="h-1.5 bg-black/[0.06] rounded-full mt-1 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${(it.active_seconds / maxActive) * 100}%`, background: "linear-gradient(90deg,#0071e3,#34A0FF)" }}
                />
              </div>
            </div>
          ))
        ) : (
          <Empty icon={BarChart3} text="该区间暂无使用数据" />
        )}
      </div>
    </div>
  );
}
