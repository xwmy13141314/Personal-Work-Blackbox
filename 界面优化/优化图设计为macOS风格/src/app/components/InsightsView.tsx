import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, RefreshCw, AlertTriangle, TrendingUp, Target, Brain } from "lucide-react";
import type { BlackboxApi, InsightItem, InsightsData } from "@/lib/pywebview";
import { Badge } from "@/app/lib/utils";

const TYPE_META: Record<string, { icon: typeof Sparkles; color: string; label: string }> = {
  best_time: { icon: Sparkles, color: "#af52de", label: "最佳时段" },
  warning: { icon: AlertTriangle, color: "#ff9500", label: "注意" },
  wow: { icon: TrendingUp, color: "#34c759", label: "周环比" },
  goal: { icon: Target, color: "#007aff", label: "目标" },
}

type Phase = "loading" | "generating" | "done" | "error"

export function InsightsView({ api }: { api: BlackboxApi | null }) {
  const [data, setData] = useState<InsightsData | null>(null)
  const [phase, setPhase] = useState<Phase>("loading")
  const [error, setError] = useState("")
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current)
    }
  }, [])

  const pollTask = useCallback(
    (taskId: string, attempt = 1) => {
      if (!api) return
      pollTimer.current = setTimeout(async () => {
        try {
          const t = await api.get_task_status(taskId)
          if (!t) {
            setPhase("error")
            setError("任务状态丢失，请重试")
            return
          }
          if (t.status === "done" && t.result?.insights_data) {
            setData(t.result.insights_data)
            setPhase("done")
            return
          }
          if (t.status === "failed") {
            setPhase("error")
            setError(t.error || "生成失败")
            return
          }
          if (attempt > 60) {
            setPhase("error")
            setError("生成超时，请稍后重试")
            return
          }
          pollTask(taskId, attempt + 1)
        } catch {
          setPhase("error")
          setError("轮询任务状态失败")
        }
      }, 1500)
    },
    [api],
  )

  const generate = useCallback(async () => {
    if (!api) return
    setPhase("generating")
    setError("")
    try {
      const { task_id } = await api.generate_weekly_insights()
      pollTask(task_id)
    } catch (e) {
      setPhase("error")
      setError(String(e))
    }
  }, [api, pollTask])

  useEffect(() => {
    if (!api) return
    ;(async () => {
      try {
        const cached = await api.get_weekly_insights()
        if (cached?.ok && cached.cached && cached.insights?.length) {
          setData(cached)
          setPhase("done")
        } else {
          generate()
        }
      } catch {
        setPhase("error")
        setError("读取洞察失败")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api])

  const busy = phase === "loading" || phase === "generating"

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      {/* 洞察卡片 */}
      <div className="rounded-xl border border-[var(--wt-border)] bg-white p-5 shadow-sm"
           style={{ background: "linear-gradient(135deg, rgba(232,93,93,0.04), rgba(0,122,255,0.03))" }}>
        <div className="flex items-center gap-2 mb-4">
          <Brain className="w-5 h-5 text-[var(--wt-accent)]" />
          <span className="text-[14px] font-semibold text-[var(--wt-text)]">AI 周度洞察</span>
          {data?.week_label && <Badge variant="blue">第 {data.week_label.split("W")[1]} 周</Badge>}
          {data?.source === "llm" && <Badge variant="green">AI 生成</Badge>}
          {data?.source === "local" && <Badge variant="yellow">本地统计</Badge>}
          <button
            onClick={generate}
            disabled={busy}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-[var(--wt-border)] px-3 py-1.5 text-[12px] text-[var(--wt-text-secondary)] hover:bg-black/[0.04] transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${busy ? "animate-spin" : ""}`} />
            {phase === "generating" ? "生成中..." : "重新生成"}
          </button>
        </div>

        {busy && (
          <div className="py-12 text-center text-[12px] text-[var(--wt-text-muted)]">
            {phase === "generating" ? "正在分析本周与上周活动数据..." : "加载中..."}
          </div>
        )}

        {phase === "error" && (
          <div className="py-10 text-center">
            <p className="text-[12px] text-[var(--wt-danger)] mb-2">{error || "生成失败"}</p>
            <button
              onClick={generate}
              className="rounded-lg bg-[var(--wt-accent)] text-white px-4 py-1.5 text-[12px] font-medium"
            >
              重试
            </button>
          </div>
        )}

        {phase === "done" && data && (
          data.insights.length === 0 ? (
            <p className="py-10 text-center text-[12px] text-[var(--wt-text-muted)]">
              本周暂无足够数据生成洞察
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3.5">
              {data.insights.map((ins: InsightItem, i: number) => {
                const meta = TYPE_META[ins.type] ?? TYPE_META.wow
                const Icon = meta.icon
                return (
                  <div key={i} className="rounded-lg border border-[var(--wt-border)] bg-white/70 p-3.5">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: meta.color }} />
                      <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: meta.color }}>
                        {ins.title || meta.label}
                      </span>
                    </div>
                    <p className="text-[12px] leading-relaxed text-[var(--wt-text-secondary)]">{ins.body}</p>
                  </div>
                )
              })}
            </div>
          )
        )}

        {phase === "done" && data && (
          <div className="mt-3.5 pt-3.5 border-t border-[var(--wt-border)] flex items-center gap-2">
            <span className="text-[11px] text-[var(--wt-text-muted)]">
              💡 基于本周采集数据{data.source === "llm" ? " + LLM 分析" : "统计规则"}自动生成 · {data.week_start.slice(5)} ~ {data.week_end.slice(5)}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
