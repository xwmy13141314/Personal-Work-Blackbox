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
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

// ==================== 视图键 ====================
type ViewKey = "report" | "stats" | "activity" | "settings";

const navItems: { key: ViewKey; icon: typeof FileText; label: string }[] = [
  { key: "report", icon: FileText, label: "报告" },
  { key: "stats", icon: BarChart3, label: "统计" },
  { key: "activity", icon: Activity, label: "活动" },
  { key: "settings", icon: Settings, label: "设置" },
];

const REPORT_TABS: { key: ReportType; label: string; title: string }[] = [
  { key: "daily", label: "日", title: "日报" },
  { key: "weekly", label: "周", title: "周报" },
  { key: "monthly", label: "月", title: "月报" },
];

// ==================== 通用组件 ====================

function StatusDot({ status }: { status: "ok" | "warn" | "error" | "idle" }) {
  const colors = { ok: "#34C759", warn: "#FF9F0A", error: "#FF3B30", idle: "#8E8E93" };
  return <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: colors[status] }} />;
}

function Badge({
  children,
  variant = "default",
}: {
  children: React.ReactNode;
  variant?: "default" | "blue" | "green" | "yellow" | "red";
}) {
  const styles = {
    default: "bg-black/[0.06] text-[#1d1d1f]",
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

function fmtDuration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${Math.floor(sec)}s`;
}

// 日期工具：与后端 _week_range/_month_range 对齐（周一为周首）
function pad(n: number) {
  return String(n).padStart(2, "0");
}
function parseDate(s: string): Date {
  return new Date(s + "T00:00:00");
}
function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function weekRange(s: string): [string, string] {
  const d = parseDate(s);
  const day = (d.getDay() + 6) % 7; // 周一=0 … 周日=6
  const mon = new Date(d);
  mon.setDate(d.getDate() - day);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  return [toDateStr(mon), toDateStr(sun)];
}
function addDays(s: string, n: number): string {
  const d = parseDate(s);
  d.setDate(d.getDate() + n);
  return toDateStr(d);
}
function addMonths(s: string, n: number): string {
  const d = parseDate(s);
  d.setMonth(d.getMonth() + n);
  return toDateStr(d);
}

function Empty({ icon: Icon, text, hint }: { icon: typeof FileText; text: string; hint?: string }) {
  return (
    <div className="py-10 text-center">
      <Icon className="w-8 h-8 text-[#d2d2d7] mx-auto mb-2" />
      <p className="text-[12px] text-[#86868b]">{text}</p>
      {hint && <p className="text-[11px] text-[#a1a1a6] mt-1">{hint}</p>}
    </div>
  );
}

function LabelText({ children }: { children: React.ReactNode }) {
  return <label className="text-[10px] text-[#86868b]">{children}</label>;
}

// ==================== Sidebar ====================

function Sidebar({
  view,
  onNavigate,
  search,
  onSearchChange,
  onSearchSubmit,
  onClearSearch,
}: {
  view: ViewKey;
  onNavigate: (k: ViewKey) => void;
  search: string;
  onSearchChange: (v: string) => void;
  onSearchSubmit: () => void;
  onClearSearch: () => void;
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
            <p className="text-[12px] font-semibold text-[#1d1d1f] leading-tight">职迹 WorkTrace</p>
            <p className="text-[10px] text-[#86868b] leading-tight">您的私有工作黑盒</p>
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
          className="flex items-center gap-1.5 bg-black/[0.07] rounded-[7px] px-2.5 py-1.5 focus-within:bg-black/[0.1] focus-within:ring-1 focus-within:ring-[#0071e3]/40"
        >
          <Search className="w-3 h-3 text-[#86868b] shrink-0" />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索历史输入..."
            className="bg-transparent outline-none text-[11px] text-[#1d1d1f] flex-1 min-w-0 placeholder:text-[#86868b]"
          />
          {search && (
            <button type="button" onClick={onClearSearch} className="text-[#86868b] hover:text-[#1d1d1f] shrink-0">
              <X className="w-3 h-3" />
            </button>
          )}
        </form>
      </div>

      <div className="px-3 mb-1">
        <p className="text-[10px] font-semibold text-[#86868b] uppercase tracking-wider px-1 mb-1">导航</p>
      </div>
      <nav className="flex-1 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ key, icon: Icon, label }) => {
          const isActive = view === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-[7px] text-[12px] font-medium transition-all ${
                isActive ? "bg-white/70 text-[#1d1d1f] shadow-sm" : "text-[#3a3a3c] hover:bg-black/[0.05]"
              }`}
            >
              <Icon className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-[#0071e3]" : "text-[#6e6e73]"}`} />
              {label}
              {isActive && <ChevronRight className="w-3 h-3 text-[#86868b] ml-auto" />}
            </button>
          );
        })}
      </nav>
      <div className="px-3 py-3 border-t border-black/[0.07]">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-white text-[10px] font-semibold shrink-0">
            U
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-medium text-[#1d1d1f] truncate">用户</p>
            <p className="text-[10px] text-[#86868b]">本地账户</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

// ==================== 统计视图 ====================

function StatsView({ api, date }: { api: BlackboxApi | null; date: string }) {
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
        <h1 className="text-[20px] font-semibold text-[#1d1d1f] tracking-tight">应用统计</h1>
        <div className="flex gap-1 bg-black/[0.06] rounded-full p-0.5">
          {(["today", "week", "month"] as const).map((rt) => (
            <button
              key={rt}
              onClick={() => setRangeType(rt)}
              className={`px-3 py-0.5 rounded-full text-[11px] font-medium transition-all ${
                rangeType === rt ? "bg-[#0071e3] text-white shadow-sm" : "text-[#3a3a3c] hover:bg-black/[0.06]"
              }`}
            >
              {rt === "today" ? "今日" : rt === "week" ? "本周" : "本月"}
            </button>
          ))}
        </div>
      </div>
      {data && (
        <p className="text-[11px] text-[#86868b]">
          {data.range.start} ~ {data.range.end} · 总活跃 {fmtDuration(data.total_active)} · {data.items.length} 个应用
        </p>
      )}

      <div className="rounded-xl border border-black/10 bg-white/70 p-4 space-y-3" style={{ backdropFilter: "blur(8px)" }}>
        {loading ? (
          <p className="text-[12px] text-[#86868b] py-8 text-center">加载中...</p>
        ) : data && data.items.length ? (
          data.items.map((it, i) => (
            <div key={i}>
              <div className="flex justify-between items-center text-[11px]">
                <span className="font-medium text-[#1d1d1f] truncate">{it.process_name || "未知应用"}</span>
                <span className="text-[#6e6e73] shrink-0 ml-2">
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

// ==================== 活动明细视图（含搜索结果） ====================

function ActivityView({
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
        <h1 className="text-[20px] font-semibold text-[#1d1d1f] tracking-tight">
          {mode === "search" ? `搜索“${q}”` : `活动明细 · ${date}`}
        </h1>
        {mode === "search" && (
          <button onClick={onClearSearch} className="text-[11px] text-[#0071e3] hover:underline">
            清除搜索
          </button>
        )}
      </div>

      <div className="space-y-2">
        {loading ? (
          <p className="text-[12px] text-[#86868b] py-8 text-center">加载中...</p>
        ) : mode === "search" ? (
          results.length ? (
            results.map((r) => (
              <div key={r.id} className="rounded-xl border border-black/10 bg-white/70 p-3">
                <div className="flex justify-between text-[10px] text-[#86868b]">
                  <button onClick={() => onPickDate(r.date)} className="text-[#0071e3] hover:underline">
                    {r.date}
                  </button>
                  <span>
                    {r.process_name || "未知"} · {r.source === "clipboard" ? "剪贴板" : "键盘"}
                  </span>
                </div>
                <p className="text-[12px] mt-1 text-[#1d1d1f] line-clamp-2 break-all">
                  {r.is_filtered ? "（已隐私过滤）" : r.text}
                </p>
                {r.window_title && <p className="text-[10px] text-[#a1a1a6] truncate mt-0.5">{r.window_title}</p>}
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
                  <p className="text-[12px] font-medium text-[#1d1d1f] truncate">{s.process_name || "未知应用"}</p>
                  <p className="text-[10px] text-[#86868b] truncate">{s.window_title || "（无窗口标题）"}</p>
                </div>
                <div className="text-right shrink-0 ml-2">
                  <p className="text-[11px] font-medium text-[#1d1d1f]">{fmtDuration(s.active_seconds)}</p>
                  <p className="text-[10px] text-[#86868b]">{s.start_time.slice(11, 16)}</p>
                </div>
              </button>
              {expanded === s.id && (
                <div className="px-3 pb-3 pt-2 border-t border-black/[0.06] space-y-1 max-h-52 overflow-y-auto">
                  {detail === null ? (
                    <p className="text-[11px] text-[#86868b]">加载中...</p>
                  ) : detail.segments.length ? (
                    detail.segments.map((seg, i) => (
                      <p key={i} className="text-[11px] text-[#3a3a3c] break-all">
                        <span className="text-[#86868b] mr-1">{seg.timestamp.slice(11, 16)}</span>
                        {seg.is_filtered ? "（已隐私过滤）" : seg.raw_text}
                      </p>
                    ))
                  ) : (
                    <p className="text-[11px] text-[#86868b]">无文本片段（仅窗口活动）</p>
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

// ==================== 设置视图 ====================

// 提供商预设（均为 OpenAI 兼容协议，新增厂商只需加一条）
const PROVIDER_PRESETS: { key: string; label: string; baseUrl: string; model: string }[] = [
  { key: "glm", label: "智谱GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4.5-flash" },
  { key: "qwen", label: "阿里通义", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { key: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { key: "moonshot", label: "Kimi", baseUrl: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  { key: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { key: "custom", label: "自定义", baseUrl: "", model: "" },
];

function SettingsView({ api, apiConfig }: { api: BlackboxApi | null; apiConfig: ApiConfig | null }) {
  const initialKey = PROVIDER_PRESETS.some((p) => p.key === apiConfig?.provider) ? apiConfig!.provider : "custom";
  const [presetKey, setPresetKey] = useState(initialKey);
  const [baseUrl, setBaseUrl] = useState(apiConfig?.base_url ?? "");
  const [model, setModel] = useState(apiConfig?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const selectPreset = (key: string) => {
    setPresetKey(key);
    const p = PROVIDER_PRESETS.find((x) => x.key === key);
    if (p && key !== "custom") {
      setBaseUrl(p.baseUrl);
      setModel(p.model);
    }
  };

  const doTest = async () => {
    if (!api) return;
    setTesting(true);
    setTestResult(null);
    const r = await api.test_api_config(presetKey, baseUrl, model, apiKey);
    setTestResult({ ok: r.ok, msg: r.ok ? r.detail || "连接成功" : r.error || "测试失败" });
    setTesting(false);
  };

  const doSave = async () => {
    if (!api) return;
    setSaving(true);
    setSaveResult(null);
    const r = await api.save_api_config(presetKey, baseUrl, model, apiKey);
    setSaveResult({ ok: r.ok, msg: r.ok ? "已保存到 config.yaml，重启应用后生效" : r.error || "保存失败" });
    setSaving(false);
  };

  const inputCls =
    "w-full px-2.5 py-1.5 rounded-lg border border-black/10 bg-white/80 text-[11.5px] text-[#1d1d1f] outline-none focus:border-[#0071e3] focus:ring-1 focus:ring-[#0071e3]/30";

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
      <h1 className="text-[20px] font-semibold text-[#1d1d1f] tracking-tight">设置</h1>

      {/* AI 配置（可编辑表单） */}
      <div className="rounded-xl border border-black/10 bg-white/70 p-4 space-y-2.5" style={{ backdropFilter: "blur(8px)" }}>
        <div className="flex items-center justify-between">
          <p className="text-[12px] font-semibold text-[#1d1d1f]">AI 配置</p>
          <Badge variant={apiConfig?.ai_available ? "blue" : "default"}>{apiConfig?.ai_available ? "当前可用" : "未配置"}</Badge>
        </div>

        <div>
          <LabelText>选择提供商</LabelText>
          <div className="flex flex-wrap gap-1 mt-1">
            {PROVIDER_PRESETS.map((p) => (
              <button
                key={p.key}
                onClick={() => selectPreset(p.key)}
                className={`px-2.5 py-1 rounded-full text-[10.5px] font-medium transition-all ${
                  presetKey === p.key ? "bg-[#0071e3] text-white" : "bg-black/[0.06] text-[#3a3a3c] hover:bg-black/[0.1]"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <LabelText>Base URL</LabelText>
          <input className={`${inputCls} mt-1`} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://..." />
        </div>

        <div>
          <LabelText>模型</LabelText>
          <input className={`${inputCls} mt-1`} value={model} onChange={(e) => setModel(e.target.value)} placeholder="如 glm-4.5-flash" />
        </div>

        <div>
          <LabelText>
            API Key
            {apiConfig?.has_key && !apiKey && <span className="text-[#a1a1a6]"> （已配置 {apiConfig.key_masked}，留空保持不变）</span>}
          </LabelText>
          <input className={`${inputCls} mt-1`} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />
        </div>

        {testResult && (
          <div className={`flex items-start gap-2 rounded-lg p-2 text-[11px] ${testResult.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
            {testResult.ok ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
            <span className="break-all">{testResult.msg}</span>
          </div>
        )}
        {saveResult && (
          <div className={`flex items-start gap-2 rounded-lg p-2 text-[11px] ${saveResult.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
            {saveResult.ok ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
            <span>{saveResult.msg}</span>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <button
            onClick={doTest}
            disabled={testing || !baseUrl || !model || !apiKey}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-black/[0.06] text-[#3a3a3c] hover:bg-black/[0.1] disabled:opacity-50 transition-all"
          >
            {testing ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
            {testing ? "测试中" : "测试连接"}
          </button>
          <button
            onClick={doSave}
            disabled={saving || !baseUrl || !model}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[#0071e3] text-white hover:brightness-110 disabled:opacity-60 transition-all"
          >
            {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
            {saving ? "保存中" : "保存配置"}
          </button>
        </div>
        <p className="text-[10px] text-[#a1a1a6]">保存写入 config/config.yaml（自动备份 .bak），需重启应用后生效。</p>
      </div>

      <div className="rounded-xl border border-black/10 bg-white/70 p-4" style={{ backdropFilter: "blur(8px)" }}>
        <p className="text-[12px] font-semibold text-[#1d1d1f] mb-1">数据目录</p>
        <p className="text-[11px] text-[#86868b] mb-2.5">在文件资源管理器中打开本地数据文件夹（数据库与 Markdown 报告）</p>
        <button
          onClick={() => api?.open_data_dir()}
          className="px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[#0071e3] text-white hover:brightness-110 transition-all"
        >
          打开数据目录
        </button>
      </div>

      <div className="rounded-xl border border-black/10 bg-white/70 p-4 space-y-1" style={{ backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-2 mb-1">
          <img src={logo} alt="WorkTrace" className="w-5 h-5 rounded" />
          <p className="text-[12px] font-semibold text-[#1d1d1f]">职迹 WorkTrace</p>
          <Badge variant="green">Local Only</Badge>
        </div>
        <p className="text-[11px] text-[#1d1d1f] leading-relaxed">让每一分努力都有迹可循。</p>
        <p className="text-[11px] text-[#86868b] leading-relaxed">
          采集键盘输入 + 窗口上下文 + 剪贴板，通过 LLM 生成日报 / 周报 / 月报。
        </p>
        <p className="text-[10px] text-[#a1a1a6] leading-relaxed">纯本地运行 · 数据不出本机</p>
      </div>
    </div>
  );
}

// ==================== 主应用 ====================

export default function App() {
  const [api, setApi] = useState<BlackboxApi | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [apiConfig, setApiConfig] = useState<ApiConfig | null>(null);
  const [reportType, setReportType] = useState<ReportType>("daily");
  const [selectedDate, setSelectedDate] = useState("");
  const [dates, setDates] = useState<string[]>([]);
  const [reportedDates, setReportedDates] = useState<string[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [genState, setGenState] = useState<{ status: "idle" | "running" | "done" | "failed"; msg: string }>({
    status: "idle",
    msg: "",
  });

  // 视图与搜索状态
  const [view, setView] = useState<ViewKey>("report");
  const [search, setSearch] = useState("");

  // 初始化：等待桥接 + 拉取初始数据
  useEffect(() => {
    (async () => {
      const a = await waitForApi();
      setApi(a);
      const [s, c, ds, rd] = await Promise.all([
        a.get_status(),
        a.get_api_config(),
        a.get_available_dates(30),
        a.get_reported_dates(90),
      ]);
      setStatus(s);
      setApiConfig(c);
      setDates(ds);
      setReportedDates(rd);
      setSelectedDate(s.today);
    })();
  }, []);

  // 录制中每 5s 刷新状态
  useEffect(() => {
    if (!api || !status?.is_running) return;
    const id = setInterval(() => {
      api.get_status().then(setStatus).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [api, status?.is_running]);

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

  const refreshStatus = async () => {
    if (api) setStatus(await api.get_status());
  };

  const rec = {
    start: async () => {
      if (api) {
        await api.start_recording();
        await refreshStatus();
      }
    },
    stop: async () => {
      if (api) {
        await api.stop_recording();
        await refreshStatus();
      }
    },
    pause: async () => {
      if (api) {
        await api.pause_recording();
        await refreshStatus();
      }
    },
    resume: async () => {
      if (api) {
        await api.resume_recording();
        await refreshStatus();
      }
    },
    privacy: async () => {
      if (api) {
        await api.toggle_privacy();
        await refreshStatus();
      }
    },
  };

  // 生成报告（轮询任务状态）
  const generate = async () => {
    if (!api) return;
    setGenState({ status: "running", msg: "生成中..." });
    try {
      const { task_id } = await api.generate_report(reportType, selectedDate);
      const poll = async () => {
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
          setTimeout(poll, 1000);
        }
      };
      setTimeout(poll, 1000);
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
    if (!status) return { text: "加载中", variant: "default" as const };
    if (status.is_privacy) return { text: "隐私模式", variant: "yellow" as const };
    if (status.is_paused) return { text: "已暂停", variant: "yellow" as const };
    if (status.is_running) return { text: "运行中", variant: "green" as const };
    return { text: "未启动", variant: "default" as const };
  })();

  return (
    <div className="size-full flex flex-col bg-[#f5f5f7]">
      {/* 日历标记样式：有采集=蓝点，有日报=底色（选中日 day_selected 优先高亮） */}
      <style>{`
        .rdp-has-data{position:relative}
        .rdp-has-data::after{content:"";position:absolute;bottom:2px;left:50%;transform:translateX(-50%);width:4px;height:4px;border-radius:9999px;background:#34A0FF;pointer-events:none}
        .rdp-has-report:not(.day_selected){background:rgba(0,113,227,0.15);font-weight:600}
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
        />

        {/* ===== Main ===== */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#f5f5f7]">
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
                      className={`px-3 py-0.5 rounded-full text-[11px] font-medium transition-all ${
                        reportType === t.key ? "bg-[#0071e3] text-white shadow-sm" : "text-[#3a3a3c] hover:bg-black/[0.06]"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => navDate(1)}
                  disabled={navDisabled(1)}
                  className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-black/[0.06] disabled:opacity-30 text-[#6e6e73]"
                  title="上一个"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>

                {/* 日期显示（日历常驻在右栏，这里只显示） */}
                <span className="px-2 py-0.5 text-[11px] font-medium text-[#1d1d1f] min-w-[110px] text-center select-none">
                  {dateLabel}
                </span>

                <button
                  onClick={() => navDate(-1)}
                  disabled={navDisabled(-1)}
                  className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-black/[0.06] disabled:opacity-30 text-[#6e6e73]"
                  title="下一个"
                >
                  <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
                </button>

                <div className="flex-1" />

                <button
                  onClick={generate}
                  disabled={genState.status === "running"}
                  className="flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-medium bg-[#0071e3] text-white hover:brightness-110 disabled:opacity-60 transition-all"
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
                  <h1 className="text-[20px] font-semibold text-[#1d1d1f] tracking-tight">
                    {tabTitle} · {dateLabel}
                  </h1>
                  <p className="text-[11px] text-[#86868b] mt-0.5">
                    {report
                      ? `模型 ${report.model_used} · 生成于 ${report.generated_at.slice(0, 16).replace("T", " ")}`
                      : "暂无报告，点击「生成报告」"}
                  </p>
                </div>

                {genState.status === "failed" && (
                  <div className="flex items-start gap-2 rounded-xl border border-orange-200 bg-orange-50/70 p-3">
                    <AlertTriangle className="w-3.5 h-3.5 text-orange-500 mt-0.5 shrink-0" />
                    <p className="text-[11.5px] text-orange-700">{genState.msg}</p>
                  </div>
                )}
                {genState.status === "done" && (
                  <div className="flex items-center gap-2 rounded-xl border border-green-200 bg-green-50/70 p-3">
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0" />
                    <p className="text-[11.5px] text-green-700">报告已生成并保存</p>
                  </div>
                )}

                <div className="rounded-xl border border-black/10 bg-white/70 p-4" style={{ backdropFilter: "blur(8px)" }}>
                  {reportLoading ? (
                    <p className="text-[12px] text-[#86868b] py-8 text-center">加载中...</p>
                  ) : report?.markdown ? (
                    <div
                      className="text-[12.5px] text-[#1d1d1f] leading-relaxed
                        [&_h1]:text-[17px] [&_h1]:font-semibold [&_h1]:mt-1 [&_h1]:mb-2
                        [&_h2]:text-[14px] [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1.5
                        [&_h3]:text-[13px] [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
                        [&_p]:my-1.5
                        [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1.5
                        [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1.5
                        [&_li]:my-0.5
                        [&_strong]:font-semibold
                        [&_code]:bg-black/5 [&_code]:px-1 [&_code]:rounded [&_code]:text-[11.5px]
                        [&_pre]:bg-black/5 [&_pre]:p-2.5 [&_pre]:rounded-lg [&_pre]:my-2 [&_pre]:overflow-x-auto
                        [&_hr]:my-3 [&_hr]:border-black/10
                        [&_a]:text-[#0071e3] [&_a]:underline
                        [&_blockquote]:border-l-2 [&_blockquote]:border-black/15 [&_blockquote]:pl-3 [&_blockquote]:text-[#6e6e73]"
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.markdown}</ReactMarkdown>
                    </div>
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
          {view === "settings" && <SettingsView api={api} apiConfig={apiConfig} />}
        </main>

        {/* ===== Right panel ===== */}
        <aside className="w-[300px] shrink-0 flex flex-col h-full overflow-y-auto border-l border-black/[0.07] bg-[#f0f0f5] px-3 py-3 space-y-3">
          {/* 录制状态 */}
          <div className="rounded-xl border border-black/[0.07] bg-white/60 p-3" style={{ backdropFilter: "blur(12px)" }}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11px] font-semibold text-[#1d1d1f]">录制状态</p>
              <Badge variant={recBadge.variant}>{recBadge.text}</Badge>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[10px] py-0.5">
                <span className="text-[#86868b]">今日时长</span>
                <span className="text-[#1d1d1f] font-medium">{status ? fmtDuration(status.recording_seconds) : "-"}</span>
              </div>
              <div className="flex items-center justify-between text-[10px] py-0.5">
                <span className="text-[#86868b]">片段数</span>
                <span className="text-[#1d1d1f] font-medium">{status?.segment_count?.toLocaleString() ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between text-[10px] py-0.5">
                <span className="text-[#86868b]">启动时间</span>
                <span className="text-[#1d1d1f] font-medium">{status?.started_at ? status.started_at.slice(11, 16) : "--:--"}</span>
              </div>
            </div>

            <div className="mt-2.5 pt-2.5 border-t border-black/[0.06] space-y-1.5">
              {!status?.is_running ? (
                <button
                  onClick={rec.start}
                  className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] font-medium bg-[#34C759] text-white hover:brightness-110 transition-all"
                >
                  <Play className="w-3 h-3" />
                  启动录制
                </button>
              ) : status.is_paused ? (
                <div className="flex gap-1.5">
                  <button
                    onClick={rec.resume}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-medium bg-[#34C759] text-white hover:brightness-110 transition-all"
                  >
                    <Play className="w-3 h-3" /> 恢复
                  </button>
                  <button
                    onClick={rec.stop}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-medium bg-[#FF3B30] text-white hover:brightness-110 transition-all"
                  >
                    <Square className="w-3 h-3" /> 停止
                  </button>
                </div>
              ) : (
                <div className="flex gap-1.5">
                  <button
                    onClick={rec.pause}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-medium bg-[#FF9F0A] text-white hover:brightness-110 transition-all"
                  >
                    <Pause className="w-3 h-3" /> 暂停
                  </button>
                  <button
                    onClick={rec.stop}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-medium bg-[#FF3B30] text-white hover:brightness-110 transition-all"
                  >
                    <Square className="w-3 h-3" /> 停止
                  </button>
                </div>
              )}
              <button
                onClick={rec.privacy}
                className={`w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] font-medium transition-all ${
                  status?.is_privacy ? "bg-[#FF9F0A] text-white" : "bg-black/[0.06] text-[#3a3a3c] hover:bg-black/[0.1]"
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
              <Activity className="w-3.5 h-3.5 text-[#86868b]" />
              <p className="text-[11px] font-semibold text-[#1d1d1f]">使用提示</p>
            </div>
            <p className="text-[10px] text-[#86868b] leading-relaxed">
              右栏日历点选日期，蓝点=有采集、底色=有日报。周/月模式用左右箭头按周月切换。
            </p>
          </div>

          {/* 日历（常驻）：点选日期，标记有采集/有日报 */}
          <div className="rounded-xl border border-black/[0.07] bg-white/60 overflow-hidden" style={{ backdropFilter: "blur(12px)" }}>
            <Calendar
              mode="single"
              weekStartsOn={1}
              selected={selectedDate ? parseDate(selectedDate) : undefined}
              onSelect={(d) => {
                if (d) setSelectedDate(toDateStr(d));
              }}
              modifiers={{ hasData: dates.map(parseDate), hasReport: reportedDates.map(parseDate) }}
              modifiersClassNames={{ hasData: "rdp-has-data", hasReport: "rdp-has-report" }}
              classNames={{
                head_cell: "text-[#86868b] rounded-md w-9 text-center font-normal text-[0.8rem]",
                day: "inline-flex items-center justify-center size-9 p-0 font-normal aria-selected:opacity-100 rounded-md bg-transparent hover:bg-black/[0.05] text-[#1d1d1f]",
              }}
            />
            <div className="flex items-center justify-center gap-3 pb-2 text-[10px] text-[#6e6e73]">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#34A0FF]" />
                有采集
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full" style={{ background: "rgba(0,113,227,0.15)" }} />
                有日报
              </span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
