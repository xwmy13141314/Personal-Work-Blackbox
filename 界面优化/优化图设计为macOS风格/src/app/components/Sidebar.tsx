import React from "react";
import { Search, X, ChevronRight } from "lucide-react";
import { navItems, type ViewKey } from "@/app/lib/utils";
import type { Status } from "@/lib/pywebview";
import logo from "@/assets/logo.png";

// ==================== Sidebar ====================

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
      className="w-[200px] shrink-0 flex flex-col h-full border-r border-black/[0.07] select-none"
      style={{ background: "rgba(236,236,240,0.9)", backdropFilter: "blur(20px) saturate(1.8)" }}
    >
      <div className="px-4 pt-5 pb-3">
        <div className="flex items-center gap-2">
          <img src={logo} alt="WorkTrace" className="w-8 h-8 rounded-[8px] shrink-0 shadow-sm" />
          <div className="min-w-0">
            <p className="text-[12px] font-semibold text-[var(--wt-text)] leading-tight">职迹 WorkTrace</p>
            <p className="text-[10px] text-[var(--wt-text-muted)] leading-tight">您的私有工作黑盒</p>
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
          className="flex items-center gap-1.5 bg-black/[0.07] rounded-[7px] px-2.5 py-1.5 focus-within:bg-black/[0.1] focus-within:ring-1 focus-within:ring-[var(--wt-accent)]/40"
        >
          <Search className="w-3 h-3 text-[var(--wt-text-muted)] shrink-0" />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索历史输入..."
            className="bg-transparent outline-none text-[11px] text-[var(--wt-text)] flex-1 min-w-0 placeholder:text-[var(--wt-text-muted)]"
          />
          {search && (
            <button type="button" onClick={onClearSearch} className="text-[var(--wt-text-muted)] hover:text-[var(--wt-text)] shrink-0">
              <X className="w-3 h-3" />
            </button>
          )}
        </form>
      </div>

      <div className="px-3 mb-1">
        <p className="text-[10px] font-semibold text-[var(--wt-text-muted)] uppercase tracking-wider px-1 mb-1">导航</p>
      </div>
      <nav className="flex-1 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ key, icon: Icon, label }) => {
          const isActive = view === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-[7px] text-[12px] font-medium transition-all ${
                isActive ? "bg-white/70 text-[var(--wt-text)] shadow-sm" : "text-[var(--wt-text-secondary)] hover:bg-black/[0.05]"
              }`}
            >
              <Icon className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-[var(--wt-accent)]" : "text-[var(--wt-text-tertiary)]"}`} />
              {label}
              {isActive && <ChevronRight className="w-3 h-3 text-[var(--wt-text-muted)] ml-auto" />}
            </button>
          );
        })}
      </nav>
      <div className="px-3 py-3 border-t border-black/[0.07]">
        <div className="flex items-center gap-2">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-semibold shrink-0 ${status?.is_running ? "bg-gradient-to-br from-green-400 to-green-600" : "bg-gradient-to-br from-gray-300 to-gray-400"}`}>
            {status?.is_running ? "●" : "○"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-medium text-[var(--wt-text)] truncate">
              {status?.is_running ? "采集中" : "已停止"}
            </p>
            <p className="text-[10px] text-[var(--wt-text-muted)]">
              {status?.today ? status.today : "—"} · {status?.segment_count?.toLocaleString() ?? 0} 片段
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
