import React, { useState } from "react";
import { Zap, RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { Badge, LabelText } from "@/app/lib/utils";
import type { BlackboxApi, ApiConfig } from "@/lib/pywebview";
import logo from "@/assets/logo.png";

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

export function SettingsView({ api, apiConfig }: { api: BlackboxApi | null; apiConfig: ApiConfig | null }) {
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
    try {
      const r = await api.test_api_config(presetKey, baseUrl, model, apiKey);
      setTestResult({ ok: r.ok, msg: r.ok ? r.detail || "连接成功" : r.error || "测试失败" });
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
      alert("测试连接异常：" + String(e));
    } finally {
      setTesting(false);
    }
  };

  const doSave = async () => {
    if (!api) return;
    setSaving(true);
    setSaveResult(null);
    try {
      const r = await api.save_api_config(presetKey, baseUrl, model, apiKey);
      setSaveResult({ ok: r.ok, msg: r.ok ? "已保存到 config.yaml，重启应用后生效" : r.error || "保存失败" });
    } catch (e) {
      setSaveResult({ ok: false, msg: String(e) });
      alert("保存配置异常：" + String(e));
    } finally {
      setSaving(false);
    }
  };

  const inputCls =
    "w-full px-2.5 py-1.5 rounded-lg border border-black/10 bg-white/80 text-[11.5px] text-[var(--wt-text)] outline-none focus:border-[var(--wt-accent)] focus:ring-1 focus:ring-[var(--wt-accent)]/30";

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
      <h1 className="text-[20px] font-semibold text-[var(--wt-text)] tracking-tight">设置</h1>

      {/* AI 配置（可编辑表单） */}
      <div className="rounded-xl border border-black/10 bg-white/70 p-4 space-y-2.5" style={{ backdropFilter: "blur(8px)" }}>
        <div className="flex items-center justify-between">
          <p className="text-[12px] font-semibold text-[var(--wt-text)]">AI 配置</p>
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
                  presetKey === p.key ? "bg-[var(--wt-accent)] text-white" : "bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1]"
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
            {apiConfig?.has_key && !apiKey && <span className="text-[var(--wt-text-faint)]"> （已配置 {apiConfig.key_masked}，留空保持不变）</span>}
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
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-black/[0.06] text-[var(--wt-text-secondary)] hover:bg-black/[0.1] disabled:opacity-50 transition-all"
          >
            {testing ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
            {testing ? "测试中" : "测试连接"}
          </button>
          <button
            onClick={doSave}
            disabled={saving || !baseUrl || !model}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 disabled:opacity-60 transition-all"
          >
            {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
            {saving ? "保存中" : "保存配置"}
          </button>
        </div>
        <p className="text-[10px] text-[var(--wt-text-faint)]">保存写入 config/config.yaml（自动备份 .bak），需重启应用后生效。</p>
      </div>

      <div className="rounded-xl border border-black/10 bg-white/70 p-4" style={{ backdropFilter: "blur(8px)" }}>
        <p className="text-[12px] font-semibold text-[var(--wt-text)] mb-1">数据目录</p>
        <p className="text-[11px] text-[var(--wt-text-muted)] mb-2.5">在文件资源管理器中打开本地数据文件夹（数据库与 Markdown 报告）</p>
        <button
          onClick={() => api?.open_data_dir()}
          className="px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[var(--wt-accent)] text-white hover:brightness-110 transition-all"
        >
          打开数据目录
        </button>
      </div>

      <div className="rounded-xl border border-black/10 bg-white/70 p-4 space-y-1" style={{ backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-2 mb-1">
          <img src={logo} alt="WorkTrace" className="w-5 h-5 rounded" />
          <p className="text-[12px] font-semibold text-[var(--wt-text)]">职迹 WorkTrace</p>
          <Badge variant="green">Local Only</Badge>
        </div>
        <p className="text-[11px] text-[var(--wt-text)] leading-relaxed">让每一分努力都有迹可循。</p>
        <p className="text-[11px] text-[var(--wt-text-muted)] leading-relaxed">
          采集输入活动 + 窗口上下文 + 剪贴板，通过 LLM 生成日报 / 周报 / 月报。
        </p>
        <p className="text-[10px] text-[var(--wt-text-faint)] leading-relaxed">纯本地运行 · 数据不出本机</p>
      </div>
    </div>
  );
}
