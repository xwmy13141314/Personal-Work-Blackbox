import { useState, useEffect } from "react";
import {
  Clock,
  FileText,
  CheckSquare,
  StickyNote,
  ChevronRight,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  Settings,
} from "lucide-react";
import type { BlackboxApi, DashboardSummary } from "@/lib/pywebview";
import { type ViewKey } from "@/app/lib/utils";

export function DashboardView({
  api,
  onNavigate,
}: {
  api: BlackboxApi | null;
  onNavigate: (k: ViewKey) => void;
}) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!api) return;
    (async () => {
      setLoading(true);
      const s = await api.get_dashboard_summary();
      setSummary(s);
      setLoading(false);
    })();
    const id = setInterval(async () => {
      if (api) setSummary(await api.get_dashboard_summary());
    }, 30000);
    return () => clearInterval(id);
  }, [api]);

  if (loading || !summary) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--wt-text-muted)] text-[13px]">
        加载中...
      </div>
    );
  }

  const todayH = Math.floor(summary.today_seconds / 3600);
  const todayM = Math.floor((summary.today_seconds % 3600) / 60);
  const todayDuration = todayH > 0 ? `${todayH}h ${todayM}m` : `${todayM}m`;

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
      {/* 页头 */}
      <div>
        <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">驾驶舱</h1>
        <p className="text-[11px] text-[var(--wt-text-muted)] mt-0.5">
          {new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })} · 工作全景概览
        </p>
      </div>

      {/* 指标卡片网格 */}
      <div className="grid grid-cols-4 gap-3">
        {/* 今日采集 */}
        <button
          onClick={() => onNavigate("activity")}
          className="rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm hover:shadow-md transition-all text-left"
        >
          <div className="flex items-center justify-between mb-2">
            <Clock className="w-4 h-4 text-[var(--wt-accent)]" />
            <span className="text-[10px] text-[var(--wt-text-muted)]">今日采集</span>
          </div>
          <p className="text-[22px] font-bold text-[var(--wt-text)] leading-tight">{todayDuration}</p>
          <p className="text-[10px] text-[var(--wt-text-muted)] mt-1">
            {summary.today_segments.toLocaleString()} 个文本片段
          </p>
        </button>

        {/* 待办 */}
        <button
          onClick={() => onNavigate("todo")}
          className="rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm hover:shadow-md transition-all text-left"
        >
          <div className="flex items-center justify-between mb-2">
            <CheckSquare className="w-4 h-4 text-[var(--wt-success)]" />
            <span className="text-[10px] text-[var(--wt-text-muted)]">待办</span>
          </div>
          <p className="text-[22px] font-bold text-[var(--wt-text)] leading-tight">{summary.todo_pending}</p>
          <p className="text-[10px] text-[var(--wt-text-muted)] mt-1">
            待处理 · {summary.todo_done} 已完成
          </p>
        </button>

        {/* 逾期 */}
        <button
          onClick={() => onNavigate("todo")}
          className="rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm hover:shadow-md transition-all text-left"
        >
          <div className="flex items-center justify-between mb-2">
            <AlertCircle className="w-4 h-4 text-[var(--wt-danger)]" />
            <span className="text-[10px] text-[var(--wt-text-muted)]">逾期</span>
          </div>
          <p className="text-[22px] font-bold text-[var(--wt-text)] leading-tight">{summary.todo_overdue}</p>
          <p className="text-[10px] text-[var(--wt-text-muted)] mt-1">
            需关注 · 共 {summary.todo_total} 项
          </p>
        </button>

        {/* 速记 */}
        <button
          onClick={() => onNavigate("quicknote")}
          className="rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm hover:shadow-md transition-all text-left"
        >
          <div className="flex items-center justify-between mb-2">
            <StickyNote className="w-4 h-4 text-[var(--wt-warning)]" />
            <span className="text-[10px] text-[var(--wt-text-muted)]">速记</span>
          </div>
          <p className="text-[22px] font-bold text-[var(--wt-text)] leading-tight">{summary.note_count}</p>
          <p className="text-[10px] text-[var(--wt-text-muted)] mt-1">
            {summary.note_pinned} 条置顶
          </p>
        </button>
      </div>

      {/* 中间区域：左列快捷入口 + 右列最近报告 */}
      <div className="grid grid-cols-3 gap-3">
        {/* 快捷入口 */}
        <div className="col-span-2 rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm">
          <p className="text-[12px] font-semibold text-[var(--wt-text)] mb-3">快捷入口</p>
          <div className="grid grid-cols-4 gap-2">
            {[
              { key: "report" as ViewKey, label: "生成报告", icon: FileText, color: "var(--wt-accent)" },
              { key: "stats" as ViewKey, label: "效率统计", icon: TrendingUp, color: "var(--wt-success)" },
              { key: "todo" as ViewKey, label: "待办看板", icon: CheckSquare, color: "var(--wt-warning)" },
              { key: "quicknote" as ViewKey, label: "速记", icon: StickyNote, color: "var(--wt-danger)" },
              { key: "activity" as ViewKey, label: "活动浏览", icon: Clock, color: "#af52de" },
              { key: "settings" as ViewKey, label: "设置", icon: Settings, color: "#8e8e93" },
            ].map(({ key, label, icon: Icon, color }) => (
              <button
                key={key}
                onClick={() => onNavigate(key)}
                className="flex flex-col items-center gap-1.5 rounded-lg border border-[var(--wt-border)] p-3 hover:bg-[var(--wt-bg)] transition-all"
              >
                <Icon className="w-4 h-4" style={{ color }} />
                <span className="text-[11px] text-[var(--wt-text-secondary)] font-medium">{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 最近报告 */}
        <div className="rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm">
          <p className="text-[12px] font-semibold text-[var(--wt-text)] mb-3">最近报告</p>
          {summary.recent_reports.length === 0 ? (
            <p className="text-[11px] text-[var(--wt-text-muted)] py-4 text-center">暂无报告</p>
          ) : (
            <div className="space-y-1.5">
              {summary.recent_reports.map((r, i) => (
                <button
                  key={i}
                  onClick={() => onNavigate("report")}
                  className="w-full flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-[var(--wt-bg)] transition-all"
                >
                  <FileText className="w-3.5 h-3.5 text-[var(--wt-accent)] shrink-0" />
                  <span className="text-[11px] text-[var(--wt-text)] flex-1 text-left">
                    {r.type === "daily" ? "日报" : r.type === "weekly" ? "周报" : "月报"} · {r.date.slice(5)}
                  </span>
                  <ChevronRight className="w-3 h-3 text-[var(--wt-text-muted)]" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 今日进度条 */}
      <div className="rounded-xl border border-[var(--wt-border)] bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[12px] font-semibold text-[var(--wt-text)]">今日工作进度</p>
          <span className="text-[11px] text-[var(--wt-text-muted)]">
            {summary.todo_done} / {summary.todo_total} 完成
          </span>
        </div>
        <div className="h-2 rounded-full bg-[var(--wt-bg)] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${summary.todo_total > 0 ? (summary.todo_done / summary.todo_total) * 100 : 0}%`,
              background: "linear-gradient(90deg, var(--wt-success), #34c759)",
            }}
          />
        </div>
        <div className="flex items-center gap-4 mt-2 text-[10px] text-[var(--wt-text-muted)]">
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-[var(--wt-success)]" />
            {summary.todo_done} 已完成
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-[var(--wt-accent)]" />
            {summary.todo_pending} 待处理
          </span>
          {summary.todo_overdue > 0 && (
            <span className="flex items-center gap-1">
              <AlertCircle className="w-3 h-3 text-[var(--wt-danger)]" />
              {summary.todo_overdue} 逾期
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
