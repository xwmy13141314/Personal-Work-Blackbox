import { useEffect, useState } from "react";
import {
  Settings,
  ChevronRight,
  Activity,
  BarChart3,
  FileText,
  Search,
  Zap,
  Play,
  Pause,
  Square,
  Lock,
  RefreshCw,
  ChevronLeft,
  AlertTriangle,
  CheckCircle2,
  FileDown,
  Printer,
  PanelRightOpen,
  PanelRightClose,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { zhCN } from "date-fns/locale";
import { Calendar } from "@/app/components/ui/calendar";
import {
  waitForApi,
  type BlackboxApi,
  type Status,
  type ApiConfig,
  type Report,
  type ReportType,
  type TaskStatus,
  type AppStats,
  type SessionItem,
  type SessionDetail,
  type SearchResult,
} from "@/lib/pywebview";
import logo from "@/assets/logo.png";

// 导入拆分后的组件和工具
import {
  type ViewKey,
  navItems,
  REPORT_TABS,
  fmtDuration,
  weekRange,
  addDays,
  addMonths,
  parseDate,
  toDateStr,
  Badge,
  Empty,
} from "@/app/lib/utils";
import { Sidebar } from "@/app/components/Sidebar";
import { StatsView } from "@/app/components/StatsView";
import { ActivityView } from "@/app/components/ActivityView";
import { SettingsView } from "@/app/components/SettingsView";
import { AboutView } from "@/app/components/AboutView";
import { TodoView } from "@/app/components/TodoView";
import { MacPermissionGuide } from "@/app/components/MacPermissionGuide";

// ==================== 主应用 ====================

export default function App() {
  const [api, setApi] = useState<BlackboxApi | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [bridgeError, setBridgeError] = useState("");
  const [apiConfig, setApiConfig] = useState<ApiConfig | null>(null);
  const [reportType, setReportType] = useState<ReportType>("daily");
  const [selectedDate, setSelectedDate] = useState("");
  const [dates, setDates] = useState<string[]>([]);

  // 字体偏好保存在本机，进入任意页面前即应用，避免重启后短暂跳回默认字号。
  useEffect(() => {
    const saved = Number(window.localStorage.getItem("worktrace-font-size"));
    if (Number.isFinite(saved) && saved >= 13 && saved <= 17) {
      document.documentElement.style.setProperty("--font-size", `${saved}px`);
      document.documentElement.style.setProperty("--wt-font-scale", String(saved / 14));
    }
  }, []);
  const [reportedDates, setReportedDates] = useState<string[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [genState, setGenState] = useState<{ status: "idle" | "running" | "done" | "failed"; msg: string }>({
    status: "idle",
    msg: "",
  });
  const [exportNotice, setExportNotice] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [chartSvg, setChartSvg] = useState("");
  const [chartState, setChartState] = useState<"idle" | "loading" | "done">("idle");
  // macOS 辅助功能权限引导
  const [perm, setPerm] = useState<{ platform: string; accessibility_granted: boolean; needs_permission: boolean; collector_active?: boolean } | null>(null);
  const [permGuide, setPermGuide] = useState(false);
  // 右侧信息栏按需展开，默认收起，让待办和报告获得完整工作区域。
  const [rightPanelOpen, setRightPanelOpen] = useState(false);

  // 导出报告为 HTML（后端渲染单文件，可离线/微信发送）
  const exportHtml = async () => {
    if (!api || !report) return;
    const r = await api.export_report("html", reportType, selectedDate);
    setExportNotice(r.ok ? { kind: "ok", msg: `已导出并在默认浏览器打开：${r.filename}` } : { kind: "err", msg: r.error || "导出失败" });
    setTimeout(() => setExportNotice(null), 4000);
  };

  // 导出 PDF：注入打印样式（仅报告正文可见）→ 浏览器/pywebview 打印 → 另存为 PDF
  const exportPdf = () => {
    if (!report) return;
    const style = document.createElement("style");
    style.id = "wt-print-report";
    style.textContent =
      "body *{visibility:hidden}.wt-print-area,.wt-print-area *{visibility:visible}.wt-print-area{position:absolute;left:0;top:0;width:100%;padding:32px;box-sizing:border-box}";
    document.head.appendChild(style);
    const cleanup = () => {
      style.remove();
      window.removeEventListener("afterprint", cleanup);
    };
    window.addEventListener("afterprint", cleanup);
    window.print();
    setTimeout(() => style.remove(), 2000); // 兜底：部分 webview 不触发 afterprint
  };

  // 分析时间分布（轮询任务，LLM 提取后返回环形图 SVG）
  const analyze = async () => {
    if (!api) return;
    setChartState("loading");
    setChartSvg("");
    try {
      const { task_id } = await api.analyze_report(reportType, selectedDate);
      const MAX_POLL = 60;
      const poll = async (attempt: number) => {
        if (attempt >= MAX_POLL) {
          setChartState("idle");
          return;
        }
        const t = await api.get_task_status(task_id);
        if (!t) {
          setChartState("idle");
          return;
        }
        if (t.status === "done") {
          const svg = t.result?.svg || "";
          if (svg) {
            setChartSvg(svg);
            setChartState("done");
          } else {
            setChartState("idle"); // 无时间分布数据，静默隐藏
          }
        } else if (t.status === "failed") {
          setChartState("idle"); // 失败静默降级，不报错
        } else {
          setTimeout(() => poll(attempt + 1), 1000);
        }
      };
      setTimeout(() => poll(1), 500);
    } catch {
      setChartState("idle");
    }
  };

  // 视图与搜索状态
  const [view, setView] = useState<ViewKey>("report");
  const [search, setSearch] = useState("");

  // 初始化：等待桥接 + 拉取初始数据
  useEffect(() => {
    (async () => {
      try {
        const a = await waitForApi();
        setApi(a);
        // 状态接口独立读取：某个非关键配置失败也不能让录制按钮失效。
        const s = await a.get_status();
        setStatus(s);
        const [c, ds, rd, p] = await Promise.all([
          a.get_api_config(),
          a.get_available_dates(30),
          a.get_reported_dates(90),
          a.check_permissions(),
        ]);
        setApiConfig(c);
        setDates(ds);
        setReportedDates(rd);
        setPerm(p);
        setBridgeError("");
        setPermGuide(false);
      } catch (error) {
        setBridgeError(`本地服务连接失败：${String(error)}`);
      }
    })();
  }, []);

  // 每天首次打开（或应用跨天仍在后台运行后再次激活）时，日历回到当天；
  // 同一天内用户手动切换的日期不会再被状态轮询覆盖。
  useEffect(() => {
    const today = status?.today;
    if (!today) return;
    const calendarKey = "worktrace-calendar-auto-date";
    if (window.localStorage.getItem(calendarKey) !== today) {
      setSelectedDate(today);
      window.localStorage.setItem(calendarKey, today);
    }
  }, [status?.today]);

  // 录制刚启动且尚未收到首个按键时快速刷新，避免用户已授权后仍长时间
  // 看到旧的“未收到按键”状态；稳定后恢复低频刷新以减少开销。
  useEffect(() => {
    if (!api || !status?.is_running) return;
    const refresh = () => api.get_status().then(setStatus).catch(() => {});
    const awaitingFirstKey = status.keyboard_listener?.active && status.keyboard_listener.event_count === 0;
    const id = setInterval(() => {
      refresh();
    }, awaitingFirstKey ? 1000 : 5000);
    return () => clearInterval(id);
  }, [api, status?.is_running, status?.keyboard_listener?.active, status?.keyboard_listener?.event_count]);

  // WebView 内的输入框在部分 macOS 版本不会通过 AXValue 暴露最终上屏文字。
  // 这里只发送 InputEvent.data 的最终增量，组合中的拼音、密码框和完整字段值
  // 都不会发送；后端还会再次确认当前来源必须是豆包或搜狗。
  useEffect(() => {
    if (!api) return;
    const recordFinalImeText = (data: unknown) => {
      if (typeof data !== "string" || !data.trim()) return;
      void api.record_webview_ime_text(data).then((result) => {
        if (result.ok) api.get_status().then(setStatus).catch(() => {});
      }).catch(() => {});
    };
    const onInput = (event: Event) => {
      const input = event as InputEvent;
      const target = event.target;
      if (input.isComposing || typeof input.data !== "string" || !input.data.trim()) return;
      if (target instanceof HTMLInputElement && target.type === "password") return;
      recordFinalImeText(input.data);
    };
    // 搜狗/豆包在 WebKit 中有时只在 compositionend 携带最终候选文字，
    // 未必触发可用的 input.data；两个事件同时出现时由后端 1.5 秒去重。
    const onCompositionEnd = (event: CompositionEvent) => recordFinalImeText(event.data);
    document.addEventListener("input", onInput, true);
    document.addEventListener("compositionend", onCompositionEnd, true);
    return () => {
      document.removeEventListener("input", onInput, true);
      document.removeEventListener("compositionend", onCompositionEnd, true);
    };
  }, [api]);

  // 切换报告类型/日期时加载报告
  useEffect(() => {
    if (!api || !selectedDate) return;
    let cancelled = false;
    (async () => {
      setReportLoading(true);
      setReport(null);
      setGenState({ status: "idle", msg: "" });
      const r = await api.get_report(reportType, selectedDate);
      if (!cancelled) {
        setReport(r);
        setReportLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, reportType, selectedDate]);

  // 报告加载成功后分析时间分布（generate 生成新报告后也会重跑）
  useEffect(() => {
    if (!api || !report?.markdown) {
      setChartState("idle");
      setChartSvg("");
      return;
    }
    analyze();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, reportType, selectedDate, report?.markdown]);

  const refreshStatus = async () => {
    if (api) setStatus(await api.get_status());
  };

  // 重新检测 macOS 辅助功能权限（授权引导页"我已授权"按钮回调）
  const recheckPerm = async (): Promise<boolean> => {
    if (!api) return false;
    const p = await api.check_permissions();
    setPerm(p);
    if (!p.needs_permission) setPermGuide(false);
    return !p.needs_permission;
  };

  const openAccessibilitySettings = async (): Promise<void> => {
    if (!api) return;
    // 仅在用户明确点击“打开系统设置”时才调用 macOS 授权入口；“重新检测”
    // 只是读取状态，绝不会修改或重置系统授权条目。
    await api.request_accessibility_permission().catch(() => null);
  };

  const rec = {
    start: async () => {
      if (!api) {
        alert("本地服务仍在连接中，请等待几秒后重试；若持续显示加载中，请退出并重新打开 WorkTrace。");
        return;
      }
      try {
        const result = await api.start_recording();
        if (!result.ok) throw new Error(result.error || "启动失败");
        await refreshStatus();
      } catch (e) {
        alert("启动录制失败：" + String(e));
        await refreshStatus().catch(() => {});
      }
    },
    stop: async () => {
      if (api) {
        try {
          await api.stop_recording();
          await refreshStatus();
        } catch (e) {
          alert("停止录制失败：" + String(e));
          await refreshStatus();
        }
      }
    },
    pause: async () => {
      if (api) {
        try {
          await api.pause_recording();
          await refreshStatus();
        } catch (e) {
          alert("暂停录制失败：" + String(e));
          await refreshStatus();
        }
      }
    },
    resume: async () => {
      if (api) {
        try {
          await api.resume_recording();
          await refreshStatus();
        } catch (e) {
          alert("恢复录制失败：" + String(e));
          await refreshStatus();
        }
      }
    },
    privacy: async () => {
      if (api) {
        try {
          await api.toggle_privacy();
          await refreshStatus();
        } catch (e) {
          alert("切换隐私模式失败：" + String(e));
          await refreshStatus();
        }
      }
    },
  };

  // 生成报告（轮询任务状态，最多轮询 120 次 = 2 分钟）
  const generate = async () => {
    if (!api) return;
    setGenState({ status: "running", msg: "生成中..." });
    try {
      const { task_id } = await api.generate_report(reportType, selectedDate);
      const MAX_POLL = 120; // 最大轮询次数（每次间隔 1s，共 2 分钟）
      const poll = async (attempt: number) => {
        if (attempt >= MAX_POLL) {
          setGenState({ status: "failed", msg: "生成超时：已等待超过 2 分钟仍未完成，请稍后重试或在「活动」中查看" });
          return;
        }
        const t: TaskStatus | null = await api.get_task_status(task_id);
        if (!t) {
          setGenState({ status: "failed", msg: "任务不存在" });
          return;
        }
        if (t.status === "done") {
          setGenState({ status: "done", msg: "生成成功" });
          setReport(await api.get_report(reportType, selectedDate));
          setReportedDates(await api.get_reported_dates(90));
          await refreshStatus();
        } else if (t.status === "failed") {
          setGenState({ status: "failed", msg: t.error || "生成失败" });
        } else {
          setTimeout(() => poll(attempt + 1), 1000);
        }
      };
      setTimeout(() => poll(1), 1000);
    } catch (e) {
      setGenState({ status: "failed", msg: String(e) });
    }
  };

  // 日期显示随报告类型变化：日=单日，周=周一~周日范围，月=yyyy-MM
  const dateLabel =
    reportType === "weekly"
      ? (() => {
          const [s, e] = weekRange(selectedDate);
          return `${s.slice(5)} ~ ${e.slice(5)}`;
        })()
      : reportType === "monthly"
      ? selectedDate.slice(0, 7)
      : selectedDate;

  const navDate = (dir: -1 | 1) => {
    if (reportType === "weekly") setSelectedDate(addDays(selectedDate, dir * 7));
    else if (reportType === "monthly") setSelectedDate(addMonths(selectedDate, dir));
    else {
      const idx = dates.indexOf(selectedDate);
      const ni = idx + dir;
      if (ni >= 0 && ni < dates.length) setSelectedDate(dates[ni]);
    }
  };
  const navDisabled = (dir: -1 | 1): boolean => {
    if (reportType !== "daily") return false;
    const idx = dates.indexOf(selectedDate);
    return dir === 1 ? idx >= dates.length - 1 : idx <= 0;
  };

  // 搜索：提交后跳到活动视图显示结果
  const submitSearch = () => {
    if (search.trim()) setView("activity");
  };
  const navigate = (k: ViewKey) => {
    setView(k);
    if (k !== "activity") setSearch("");
  };

  const tabTitle = REPORT_TABS.find((t) => t.key === reportType)?.title ?? "报告";
  const recBadge = (() => {
    if (!api) return { text: "连接中", variant: "default" as const };
    if (!status) return { text: bridgeError ? "连接失败" : "加载中", variant: "default" as const };
    if (status.is_privacy) return { text: "隐私模式", variant: "yellow" as const };
    if (status.is_paused) return { text: "已暂停", variant: "yellow" as const };
    if (status.is_running) return { text: "运行中", variant: "green" as const };
    return { text: "未启动", variant: "default" as const };
  })();

  return (
    <div className="size-full flex flex-col bg-[var(--wt-bg)]">
      {/* macOS 辅助功能权限引导（未授权时显示） */}
      {permGuide && (
        <MacPermissionGuide
          onRecheck={recheckPerm}
          onOpenSystemSettings={openAccessibilitySettings}
          onSkip={() => setPermGuide(false)}
        />
      )}
      {/* 日历标记样式：有采集=蓝点，有日报=底色（选中日 day_selected 优先高亮） */}
      <style>{`
        .rdp-has-data{position:relative}
        .rdp-has-data::after{content:"";position:absolute;bottom:2px;left:50%;transform:translateX(-50%);width:4px;height:4px;border-radius:9999px;background:#5b9f19;pointer-events:none}
        .rdp-has-report:not(.day_selected){background:#e6f7c7;font-weight:600}
      `}</style>

      {/* 三栏布局直接铺满窗口（Windows 原生标题栏） */}
      <div className="flex flex-1 min-h-0">
        <Sidebar
          view={view}
          onNavigate={navigate}
          search={search}
          onSearchChange={setSearch}
          onSearchSubmit={submitSearch}
          onClearSearch={() => setSearch("")}
          status={status}
        />

        {/* ===== Main ===== */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[var(--wt-bg)]">
          {view === "report" && (
            <>
              {/* Toolbar */}
              <div
                className="flex items-center gap-2 px-5 h-11 shrink-0 border-b border-black/[0.07]"
                style={{ background: "rgba(245,245,247,0.8)", backdropFilter: "blur(20px)" }}
              >
                <div className="flex gap-1 bg-black/[0.06] rounded-full p-0.5">
                  {REPORT_TABS.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setReportType(t.key)}
                      className={`px-3 py-0.5 rounded-full text-[12px] font-medium transition-all ${
                        reportType === t.key ? "bg-[var(--wt-accent)] text-white shadow-sm" : "text-[var(--wt-text-secondary)] hover:bg-black/[0.06]"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => navDate(1)}
                  disabled={navDisabled(1)}
                  className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-black/[0.06] disabled:opacity-30 text-[var(--wt-text-tertiary)]"
                  title="上一个"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>

                {/* 日期显示（日历常驻在右栏，这里只显示） */}
                <span className="px-2 py-0.5 text-[12px] font-medium text-[var(--wt-text)] min-w-[110px] text-center select-none">
                  {dateLabel}
                </span>

                <button
                  onClick={() => navDate(-1)}
                  disabled={navDisabled(-1)}
                  className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-black/[0.06] disabled:opacity-30 text-[var(--wt-text-tertiary)]"
                  title="下一个"
                >
                  <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
                </button>

                <div className="flex-1" />

                <button
                  onClick={exportHtml}
                  disabled={!report}
                  className="flex items-center gap-1 px-3 py-1 rounded-full text-[12px] font-medium text-[var(--wt-text-secondary)] hover:bg-black/[0.06] disabled:opacity-40 transition-all"
                  title="导出为 HTML 单文件（可离线 / 微信发送）"
                >
                  <FileDown className="w-3 h-3" />
                  HTML
                </button>
                <button
                  onClick={exportPdf}
                  disabled={!report}
                  className="flex items-center gap-1 px-3 py-1 rounded-full text-[12px] font-medium text-[var(--wt-text-secondary)] hover:bg-black/[0.06] disabled:opacity-40 transition-all"
                  title="打印 / 另存为 PDF"
                >
                  <Printer className="w-3 h-3" />
                  PDF
                </button>

                <button
                  onClick={generate}
                  disabled={genState.status === "running"}
                  className="flex items-center gap-1 px-3 py-1 rounded-full text-[12px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 disabled:opacity-60 transition-all"
                >
                  {genState.status === "running" ? (
                    <RefreshCw className="w-3 h-3 animate-spin" />
                  ) : (
                    <Zap className="w-3 h-3" />
                  )}
                  {genState.status === "running" ? "生成中" : "生成报告"}
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                <div>
                  <h1 className="text-[21px] font-semibold text-[var(--wt-text)] tracking-tight">
                    {tabTitle} · {dateLabel}
                  </h1>
                  <p className="text-[12px] text-[var(--wt-text-muted)] mt-0.5">
                    {report
                      ? `模型 ${report.model_used} · 生成于 ${report.generated_at.slice(0, 16).replace("T", " ")}`
                      : "暂无报告，点击「生成报告」"}
                  </p>
                </div>

                {genState.status === "failed" && (
                  <div className="flex items-start gap-2 rounded-xl border border-orange-200 bg-orange-50/70 p-3">
                    <AlertTriangle className="w-3.5 h-3.5 text-orange-500 mt-0.5 shrink-0" />
                    <p className="text-[12.5px] text-orange-700">{genState.msg}</p>
                  </div>
                )}
                {genState.status === "done" && (
                  <div className="flex items-center gap-2 rounded-xl border border-green-200 bg-green-50/70 p-3">
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0" />
                    <p className="text-[12.5px] text-green-700">报告已生成并保存</p>
                  </div>
                )}
                {exportNotice && (
                  <div className={`flex items-start gap-2 rounded-xl border p-3 ${exportNotice.kind === "ok" ? "border-green-200 bg-green-50/70" : "border-orange-200 bg-orange-50/70"}`}>
                    {exportNotice.kind === "ok" ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle className="w-3.5 h-3.5 text-orange-500 shrink-0 mt-0.5" />
                    )}
                    <p className={`text-[12.5px] ${exportNotice.kind === "ok" ? "text-green-700" : "text-orange-700"}`}>{exportNotice.msg}</p>
                  </div>
                )}

                <div className="wt-print-area rounded-xl border border-black/10 bg-white/70 p-4" style={{ backdropFilter: "blur(8px)" }}>
                  {reportLoading ? (
                    <p className="text-[13px] text-[var(--wt-text-muted)] py-8 text-center">加载中...</p>
                  ) : report?.markdown ? (
                    <>
                    <div
                      className="text-[13.5px] text-[var(--wt-text)] leading-relaxed
                        [&_h1]:text-[18px] [&_h1]:font-semibold [&_h1]:mt-1 [&_h1]:mb-2
                        [&_h2]:text-[15px] [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1.5
                        [&_h3]:text-[14px] [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
                        [&_p]:my-1.5
                        [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1.5
                        [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1.5
                        [&_li]:my-0.5
                        [&_strong]:font-semibold
                        [&_code]:bg-black/5 [&_code]:px-1 [&_code]:rounded [&_code]:text-[12.5px]
                        [&_pre]:bg-black/5 [&_pre]:p-2.5 [&_pre]:rounded-lg [&_pre]:my-2 [&_pre]:overflow-x-auto
                        [&_hr]:my-3 [&_hr]:border-black/10
                        [&_a]:text-[var(--wt-accent)] [&_a]:underline
                        [&_blockquote]:border-l-2 [&_blockquote]:border-black/15 [&_blockquote]:pl-3 [&_blockquote]:text-[var(--wt-text-tertiary)]"
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.markdown}</ReactMarkdown>
                    </div>
                    {chartState === "loading" && (
                      <div className="mt-4 pt-4 border-t border-black/10 flex items-center gap-2 text-[12.5px] text-[var(--wt-text-muted)]">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        正在分析时间分布...
                      </div>
                    )}
                    {chartState === "done" && chartSvg && (
                      <div className="mt-4 pt-4 border-t border-black/10">
                        <p className="text-[13px] font-semibold text-[var(--wt-text)] mb-2 flex items-center gap-1.5">
                          <BarChart3 className="w-3.5 h-3.5 text-[var(--wt-accent)]" />
                          时间分布
                        </p>
                        <div dangerouslySetInnerHTML={{ __html: chartSvg }} className="max-w-[480px]" />
                      </div>
                    )}
                    </>
                  ) : (
                    <Empty icon={FileText} text={`该${tabTitle}暂无内容`} hint="点击右上角「生成报告」创建" />
                  )}
                </div>
              </div>
            </>
          )}

          {view === "stats" && <StatsView api={api} date={selectedDate || status?.today || ""} />}
          {view === "activity" && (
            <ActivityView
              api={api}
              date={selectedDate || status?.today || ""}
              search={search}
              onClearSearch={() => setSearch("")}
              onPickDate={(d) => {
                if (dates.indexOf(d) < 0) setDates((prev) => [d, ...prev]);
                setSelectedDate(d);
                setSearch("");
              }}
            />
          )}
          {view === "todo" && (
            <TodoView
              api={api}
              date={selectedDate || status?.today || ""}
              onOpenReport={(rt, d) => {
                setReportType(rt)
                setSelectedDate(d)
                navigate("report")
              }}
            />
          )}
          {view === "settings" && <SettingsView api={api} apiConfig={apiConfig} onOpenPermissions={() => setPermGuide(true)} />}
          {view === "about" && <AboutView />}
        </main>

        {/* ===== Right panel: 默认收起，按需展开 ===== */}
        {!rightPanelOpen && (
          <div className="w-10 shrink-0 flex justify-center border-l border-black/[0.07] bg-[var(--wt-bg-sidebar)] pt-3">
            <button
              onClick={() => setRightPanelOpen(true)}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-[var(--wt-text-secondary)] hover:bg-black/[0.07] hover:text-[var(--wt-text)] transition-colors"
              title="展开右侧信息栏"
              aria-label="展开右侧信息栏"
            >
              <PanelRightOpen className="w-4 h-4" />
            </button>
          </div>
        )}
        {rightPanelOpen && <aside className="w-[300px] shrink-0 flex flex-col h-full overflow-y-auto border-l border-black/[0.07] bg-[var(--wt-bg-sidebar)] px-3 py-3 space-y-3">
          <div className="flex justify-end -mb-1">
            <button
              onClick={() => setRightPanelOpen(false)}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-[var(--wt-text-secondary)] hover:bg-black/[0.07] hover:text-[var(--wt-text)] transition-colors"
              title="收起右侧信息栏"
              aria-label="收起右侧信息栏"
            >
              <PanelRightClose className="w-4 h-4" />
            </button>
          </div>
          {/* 录制状态 */}
          <div className="rounded-xl border border-black/[0.07] bg-white/60 p-3" style={{ backdropFilter: "blur(12px)" }}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[12px] font-semibold text-[var(--wt-text)]">录制状态</p>
              <Badge variant={recBadge.variant}>{recBadge.text}</Badge>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px] py-0.5">
                <span className="text-[var(--wt-text-muted)]">今日时长</span>
                <span className="text-[var(--wt-text)] font-medium">{status ? fmtDuration(status.recording_seconds) : "-"}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] py-0.5">
                <span className="text-[var(--wt-text-muted)]">片段数</span>
                <span className="text-[var(--wt-text)] font-medium">{status?.segment_count?.toLocaleString() ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] py-0.5">
                <span className="text-[var(--wt-text-muted)]">启动时间</span>
                <span className="text-[var(--wt-text)] font-medium">{status?.started_at ? status.started_at.slice(11, 16) : "--:--"}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] py-0.5 gap-2">
                <span className="text-[var(--wt-text-muted)] shrink-0">最近输入法记录</span>
                <span className="text-[var(--wt-text)] font-medium text-right">
                  {status?.last_ime_record
                    ? `${status.last_ime_record.source === "doubao_ime" ? "豆包" : "搜狗"} · ${status.last_ime_record.char_count} 字 · ${status.last_ime_record.recorded_at.slice(11, 16)}`
                    : "暂无"}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] py-0.5 gap-2">
                <span className="text-[var(--wt-text-muted)] shrink-0">最近采集策略</span>
                <span className="text-[var(--wt-text)] font-medium text-right">
                  {status?.last_capture_record
                    ? `${status.last_capture_record.strategy === "text" ? "完整文本" : "键盘回退"} · ${status.last_capture_record.char_count} 字 · ${status.last_capture_record.recorded_at.slice(11, 16)}`
                    : "等待输入"}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] py-0.5 gap-2">
                <span className="text-[var(--wt-text-muted)] shrink-0">输入法监听</span>
                <span className="text-[var(--wt-text)] font-medium text-right">
                  {status?.ime_listener?.state === "not_trusted"
                    ? "需重新开启辅助功能"
                    : status?.ime_listener?.state === "screen_permission_required"
                      ? "需开启屏幕录制权限"
                    : status?.ime_listener?.source
                      ? `${status.ime_listener.source === "doubao_ime" ? "豆包" : "搜狗"}${status.ime_listener.state === "ready" ? " · 就绪" : status.ime_listener.state === "screen_ocr" ? " · 本地屏幕识别" : ` · ${status.ime_listener.target || "系统"}未公开输入框`}`
                      : status?.ime_listener?.state === "other_input_method" ? "请切换豆包或搜狗" : "等待焦点输入框"}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] py-0.5 gap-2">
                <span className="text-[var(--wt-text-muted)] shrink-0">键盘回退</span>
                <span className="text-[var(--wt-text)] font-medium text-right">
                  {!status?.keyboard_listener?.active
                    ? "未启动"
                    : status.keyboard_listener.event_count > 0
                    ? `已收到 ${status.keyboard_listener.event_count} 个按键`
                      : "监听已启动，等待首个按键"}
                </span>
              </div>
            </div>

            <div className="mt-2.5 pt-2.5 border-t border-black/[0.06] space-y-1.5">
              {!status?.is_running ? (
                <button
                  onClick={rec.start}
                  title={api ? "启动录制" : bridgeError || "正在连接本地服务"}
                  className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[12px] font-medium bg-[var(--wt-success)] text-white hover:brightness-110 transition-all"
                >
                  <Play className="w-3 h-3" />
                  启动录制
                </button>
              ) : status.is_paused ? (
                <div className="flex gap-1.5">
                  <button
                    onClick={rec.resume}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[12px] font-medium bg-[var(--wt-success)] text-white hover:brightness-110 transition-all"
                  >
                    <Play className="w-3 h-3" /> 恢复
                  </button>
                  <button
                    onClick={rec.stop}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[12px] font-medium bg-[var(--wt-danger)] text-white hover:brightness-110 transition-all"
                  >
                    <Square className="w-3 h-3" /> 停止
                  </button>
                </div>
              ) : (
                <div className="flex gap-1.5">
                  <button
                    onClick={rec.pause}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[12px] font-medium bg-[var(--wt-warning)] text-white hover:brightness-110 transition-all"
                  >
                    <Pause className="w-3 h-3" /> 暂停
                  </button>
                  <button
                    onClick={rec.stop}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[12px] font-medium bg-[var(--wt-danger)] text-white hover:brightness-110 transition-all"
                  >
                    <Square className="w-3 h-3" /> 停止
                  </button>
                </div>
              )}
              <button
                onClick={rec.privacy}
                className={`w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[12px] font-medium transition-all ${
                  status?.is_privacy ? "bg-[var(--wt-warning)] text-white" : "bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1]"
                }`}
              >
                <Lock className="w-3 h-3" />
                {status?.is_privacy ? "隐私模式开" : "隐私模式"}
              </button>
            </div>
          </div>

          {/* 提示卡 */}
          <div className="rounded-xl border border-black/[0.07] bg-white/60 p-3" style={{ backdropFilter: "blur(12px)" }}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Activity className="w-3.5 h-3.5 text-[var(--wt-text-muted)]" />
              <p className="text-[12px] font-semibold text-[var(--wt-text)]">使用提示</p>
            </div>
            <p className="text-[11px] text-[var(--wt-text-muted)] leading-relaxed">
              右栏日历点选日期，蓝点=有采集、底色=有日报。周/月模式用左右箭头按周月切换。
            </p>
          </div>

          {/* 日历（常驻）：点选日期，标记有采集/有日报 */}
          <div className="rounded-xl border border-black/[0.07] bg-white/60 overflow-hidden" style={{ backdropFilter: "blur(12px)" }}>
            <Calendar
              mode="single"
              locale={zhCN}
              weekStartsOn={1}
              selected={selectedDate ? parseDate(selectedDate) : undefined}
              onSelect={(d) => {
                if (d) setSelectedDate(toDateStr(d));
              }}
              modifiers={{ hasData: dates.map(parseDate), hasReport: reportedDates.map(parseDate) }}
              modifiersClassNames={{ hasData: "rdp-has-data", hasReport: "rdp-has-report" }}
              classNames={{
                head_cell: "text-[var(--wt-text-muted)] w-full rounded-md text-center font-normal text-[0.8rem]",
                day: "inline-flex h-9 w-full items-center justify-center p-0 font-normal aria-selected:opacity-100 rounded-md bg-transparent hover:bg-black/[0.05] text-[var(--wt-text)]",
                day_today: "bg-[#e6f7c7] text-[#365f12]",
                day_selected: "!bg-[#5b9f19] !text-white hover:!bg-[#4d8915] focus:!bg-[#4d8915]",
              }}
            />
            <div className="flex items-center justify-center gap-3 pb-2 text-[11px] text-[var(--wt-text-tertiary)]">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#5b9f19]" />
                有采集
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-[#d6f3a4] ring-1 ring-[#8fbd4d]" />
                有日报
              </span>
            </div>
          </div>
        </aside>}
      </div>
    </div>
  );
}
