import React from "react";
import { FileText, BarChart3, Activity, Settings } from "lucide-react";
import type { ReportType } from "@/lib/pywebview";

// ==================== 视图键 ====================
export type ViewKey = "report" | "stats" | "activity" | "settings";

export const navItems: { key: ViewKey; icon: typeof FileText; label: string }[] = [
  { key: "report", icon: FileText, label: "报告" },
  { key: "stats", icon: BarChart3, label: "统计" },
  { key: "activity", icon: Activity, label: "活动" },
  { key: "settings", icon: Settings, label: "设置" },
];

export const REPORT_TABS: { key: ReportType; label: string; title: string }[] = [
  { key: "daily", label: "日", title: "日报" },
  { key: "weekly", label: "周", title: "周报" },
  { key: "monthly", label: "月", title: "月报" },
];

// ==================== 通用组件 ====================

export function StatusDot({ status }: { status: "ok" | "warn" | "error" | "idle" }) {
  const colors = {
    ok: "var(--wt-success)",
    warn: "var(--wt-warning)",
    error: "var(--wt-danger)",
    idle: "#8E8E93",
  };
  return <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: colors[status] }} />;
}

export function Badge({
  children,
  variant = "default",
}: {
  children: React.ReactNode;
  variant?: "default" | "blue" | "green" | "yellow" | "red";
}) {
  const styles = {
    default: "bg-black/[0.06] text-[var(--wt-text)]",
    blue: "bg-blue-50 text-blue-600",
    green: "bg-green-50 text-green-700",
    yellow: "bg-orange-50 text-orange-600",
    red: "bg-red-50 text-red-600",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${styles[variant]}`}>
      {children}
    </span>
  );
}

// ==================== 工具函数 ====================

export function fmtDuration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${Math.floor(sec)}s`;
}

// 日期工具：与后端 _week_range/_month_range 对齐（周一为周首）
export function pad(n: number) {
  return String(n).padStart(2, "0");
}
export function parseDate(s: string): Date {
  return new Date(s + "T00:00:00");
}
export function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
export function weekRange(s: string): [string, string] {
  const d = parseDate(s);
  const day = (d.getDay() + 6) % 7; // 周一=0 … 周日=6
  const mon = new Date(d);
  mon.setDate(d.getDate() - day);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  return [toDateStr(mon), toDateStr(sun)];
}
export function addDays(s: string, n: number): string {
  const d = parseDate(s);
  d.setDate(d.getDate() + n);
  return toDateStr(d);
}
export function addMonths(s: string, n: number): string {
  const d = parseDate(s);
  d.setMonth(d.getMonth() + n);
  return toDateStr(d);
}

// ==================== 通用展示组件 ====================

export function Empty({ icon: Icon, text, hint }: { icon: typeof FileText; text: string; hint?: string }) {
  return (
    <div className="py-10 text-center">
      <Icon className="w-8 h-8 text-[#d2d2d7] mx-auto mb-2" />
      <p className="text-[12px] text-[var(--wt-text-muted)]">{text}</p>
      {hint && <p className="text-[11px] text-[var(--wt-text-faint)] mt-1">{hint}</p>}
    </div>
  );
}

export function LabelText({ children }: { children: React.ReactNode }) {
  return <label className="text-[10px] text-[var(--wt-text-muted)]">{children}</label>;
}
