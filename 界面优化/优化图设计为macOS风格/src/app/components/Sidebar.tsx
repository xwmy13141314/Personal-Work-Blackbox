import React from "react";
import { Search, X, ChevronRight } from "lucide-react";
import { navGroups, type ViewKey } from "@/app/lib/utils";
import type { Status } from "@/lib/pywebview";
import logo from "@/assets/logo.png";

// ==================== Sidebar（浅色左导航：分组结构，驾驶舱+速记新增） ====================

export function Sidebar({
  view,
  onNavigate,
  search,
  onSearchChange,
  onSearchSubmit,
  onClearSearch,
  status,
}: {
  view: ViewKey;
  onNavigate: (k: ViewKey) => void;
  search: string;
  onSearchChange: (v: string) => void;
  onSearchSubmit: () => void;
  onClearSearch: () => void;
  status: Status | null;
}) {
  return (
    <aside
      className="w-[240px] shrink-0 flex flex-col h-full border-r border-black/[0.07] select-none"
      style={{ background: "rgba(236,236,240,0.9)", backdropFilter: "blur(20px) saturate(1.8)" }}
    >
      <div className="px-4 pt-5 pb-3">
        <div className="flex items-center gap-3">
          <img src={logo} alt="WorkTrace" className="w-9 h-9 rounded-lg shrink-0 shadow-sm" />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-[var(--wt-text)] leading-tight">职迹 WorkTrace</p>
            <p className="text-[11px] text-[var(--wt-text-muted)] leading-tight">您的私有工作黑盒</p>
          </div>
        </div>
      </div>

      {/* 搜索框：真实 input，回车跳转到活动视图显示结果 */}
      <div className="px-3 pb-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSearchSubmit();
          }}
          className="flex items-center gap-2 rounded-lg px-3 py-2 focus-within:bg-black/[0.1] focus-within:ring-1 focus-within:ring-[var(--wt-accent)]/40"
          style={{ background: "rgba(0,0,0,0.07)" }}
        >
          <Search className="w-3.5 h-3.5 text-[var(--wt-text-muted)] shrink-0" />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索..."
            className="bg-transparent outline-none text-[12px] text-[var(--wt-text)] flex-1 min-w-0 placeholder:text-[var(--wt-text-muted)]"
          />
          {search && (
            <button type="button" onClick={onClearSearch} className="text-[var(--wt-text-muted)] hover:text-[var(--wt-text)] shrink-0">
              <X className="w-3 h-3" />
            </button>
          )}
        </form>
      </div>

      <nav className="flex-1 px-3 space-y-2 overflow-y-auto">
        {navGroups.map((grp) => (
          <div key={grp.group}>
            <p className="text-[10px] font-semibold text-[var(--wt-text-muted)] uppercase tracking-wider px-3 mb-1 mt-1">
              {grp.group}
            </p>
            <div className="space-y-0.5">
              {grp.items.map(({ key, icon: Icon, label }) => {
                const isActive = view === key;
                return (
                  <button
                    key={key}
                    onClick={() => onNavigate(key)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[12.5px] font-medium transition-all ${
                      isActive
                        ? "bg-white/70 text-[var(--wt-text)] shadow-sm"
                        : "text-[var(--wt-text-secondary)] hover:bg-black/[0.05]"
                    }`}
                  >
                    <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-[var(--wt-accent)]" : "text-[var(--wt-text-tertiary)]"}`} />
                    {label}
                    {isActive && <ChevronRight className="w-3.5 h-3.5 text-[var(--wt-text-muted)] ml-auto" />}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="px-4 py-3.5 border-t border-black/[0.07]">
        <div className="flex items-center gap-2.5">
          <span
            className={`w-2.5 h-2.5 rounded-full shrink-0 ${status?.is_running ? "" : "bg-black/20"}`}
            style={status?.is_running ? { background: "var(--wt-success)" } : undefined}
          />
          <div className="flex-1 min-w-0">
            <p className="text-[12px] font-medium text-[var(--wt-text)] leading-tight">
              {status?.is_running ? (status.is_paused ? "已暂停" : "采集中") : "已停止"}
            </p>
            <p className="text-[11px] text-[var(--wt-text-muted)] leading-tight mt-0.5">
              {status?.today ? status.today : "—"} · {status?.segment_count?.toLocaleString() ?? 0} 片段
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
