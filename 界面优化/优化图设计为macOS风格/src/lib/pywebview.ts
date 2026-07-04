// pywebview JS 桥接封装
// 提供 waitForApi() 等待桥接就绪；非 pywebview 环境（纯浏览器 dev）返回 mock API

export type ReportType = "daily" | "weekly" | "monthly"

export interface Status {
  is_running: boolean
  is_paused: boolean
  is_privacy: boolean
  started_at: string | null
  recording_seconds: number
  segment_count: number
  today: string
}

export interface Report {
  report_type: string
  date: string
  markdown: string
  model_used: string
  generated_at: string
  token_count: number
}

export interface TaskStatus {
  status: "pending" | "running" | "done" | "failed"
  result: { markdown: string; saved_path: string } | null
  error: string | null
}

export interface ApiConfig {
  provider: string
  base_url: string
  model: string
  has_key: boolean
  key_masked: string
  ai_available: boolean
}

export interface AppStatItem {
  process_name: string
  session_count: number
  active_seconds: number
  idle_seconds: number
}

export interface AppStats {
  range: { start: string; end: string; type: string }
  items: AppStatItem[]
  total_active: number
}

export interface SessionItem {
  id: number
  start_time: string
  end_time: string | null
  process_name: string
  window_title: string
  active_seconds: number
  idle_seconds: number
  is_filtered: boolean
}

export interface SessionDetail {
  session: {
    id: number
    start_time: string
    end_time: string | null
    process_name: string
    window_title: string
    active_seconds: number
    idle_seconds: number
  }
  segments: {
    timestamp: string
    raw_text: string
    source: string
    is_filtered: boolean
    char_count: number
  }[]
}

export interface SearchResult {
  id: number
  session_id: number
  timestamp: string
  text: string
  source: string
  is_filtered: boolean
  process_name: string
  window_title: string
  date: string
}

export interface BlackboxApi {
  ping(): Promise<{ ready: boolean; version: string }>
  get_status(): Promise<Status>
  start_recording(): Promise<{ ok: boolean; started_at?: string }>
  stop_recording(): Promise<{ ok: boolean }>
  pause_recording(): Promise<{ ok: boolean; is_paused?: boolean; error?: string }>
  resume_recording(): Promise<{ ok: boolean; is_paused?: boolean; error?: string }>
  toggle_privacy(): Promise<{ ok: boolean; is_privacy: boolean }>
  get_available_dates(limit?: number): Promise<string[]>
  get_reported_dates(limit?: number): Promise<string[]>
  get_report(report_type: string, date: string): Promise<Report | null>
  has_data_for_date(date: string): Promise<boolean>
  generate_report(report_type: string, date: string): Promise<{ task_id: string }>
  get_task_status(task_id: string): Promise<TaskStatus | null>
  get_api_config(): Promise<ApiConfig>
  open_report_file(report_type: string, date: string): Promise<{ ok: boolean; path?: string; error?: string }>
  open_data_dir(): Promise<{ ok: boolean }>
  save_api_config(provider: string, base_url: string, model: string, api_key: string): Promise<{ ok: boolean; restart_needed?: boolean; backup?: string; error?: string }>
  test_api_config(provider: string, base_url: string, model: string, api_key: string): Promise<{ ok: boolean; detail?: string; error?: string }>
  // 数据浏览
  get_app_stats(range_type: string, date: string): Promise<AppStats>
  get_sessions(date: string): Promise<SessionItem[]>
  get_session_detail(session_id: number): Promise<SessionDetail | null>
  search_text(keyword: string, limit?: number): Promise<{ keyword: string; results: SearchResult[] }>
}

declare global {
  interface Window {
    pywebview?: { api: BlackboxApi }
  }
}

let apiPromise: Promise<BlackboxApi> | null = null

export function waitForApi(): Promise<BlackboxApi> {
  if (apiPromise) return apiPromise
  apiPromise = new Promise((resolve) => {
    let resolved = false
    const finish = (api: BlackboxApi) => {
      if (!resolved) {
        resolved = true
        resolve(api)
      }
    }
    // pywebview 环境：pywebviewready 事件后真实 api 可用
    window.addEventListener(
      "pywebviewready",
      () => finish(window.pywebview!.api),
      { once: true },
    )
    // 纯浏览器 dev：3 秒内仍无 pywebview 则降级 mock
    setTimeout(() => {
      if (!window.pywebview?.api) finish(mockApi)
    }, 3000)
  })
  return apiPromise
}

// 浏览器 dev 调试用 mock（pywebview 环境下不使用）
const mockApi: BlackboxApi = {
  ping: async () => ({ ready: true, version: "mock" }),
  get_status: async () => ({
    is_running: true,
    is_paused: false,
    is_privacy: false,
    started_at: new Date().toISOString(),
    recording_seconds: 8700,
    segment_count: 5542,
    today: new Date().toISOString().slice(0, 10),
  }),
  start_recording: async () => ({ ok: true, started_at: new Date().toISOString() }),
  stop_recording: async () => ({ ok: true }),
  pause_recording: async () => ({ ok: true, is_paused: true }),
  resume_recording: async () => ({ ok: true, is_paused: false }),
  toggle_privacy: async () => ({ ok: true, is_privacy: false }),
  get_available_dates: async () => ["2026-07-02", "2026-05-27", "2026-05-26"],
  get_reported_dates: async () => ["2026-07-02", "2026-05-27"],
  get_report: async () => ({
    report_type: "daily",
    date: "2026-07-02",
    markdown: "# 日报（mock）\n\n浏览器 dev 预览模式，无真实数据。",
    model_used: "glm-4.5-flash",
    generated_at: new Date().toISOString(),
    token_count: 0,
  }),
  has_data_for_date: async () => true,
  generate_report: async () => ({ task_id: "mock-1" }),
  get_task_status: async () => ({ status: "done", result: { markdown: "# 日报（mock）", saved_path: "" }, error: null }),
  get_api_config: async () => ({
    provider: "glm",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4.5-flash",
    has_key: true,
    key_masked: "***LOJK",
    ai_available: true,
  }),
  open_report_file: async () => ({ ok: false, error: "mock" }),
  open_data_dir: async () => ({ ok: true }),
  save_api_config: async () => ({ ok: true, restart_needed: true }),
  test_api_config: async () => ({ ok: true, detail: "mock 连接成功" }),
  get_app_stats: async () => ({
    range: { start: "2026-07-02", end: "2026-07-02", type: "today" },
    total_active: 8700,
    items: [
      { process_name: "Code.exe", session_count: 12, active_seconds: 5200, idle_seconds: 300 },
      { process_name: "chrome.exe", session_count: 8, active_seconds: 2400, idle_seconds: 200 },
    ],
  }),
  get_sessions: async () => [
    { id: 1, start_time: "2026-07-02T09:00:00", end_time: "2026-07-02T10:30:00", process_name: "Code.exe", window_title: "main.py", active_seconds: 5400, idle_seconds: 300, is_filtered: false },
  ],
  get_session_detail: async () => ({
    session: { id: 1, start_time: "2026-07-02T09:00:00", end_time: "2026-07-02T10:30:00", process_name: "Code.exe", window_title: "main.py", active_seconds: 5400, idle_seconds: 300 },
    segments: [{ timestamp: "2026-07-02T09:05:00", raw_text: "示例输入内容（mock）", source: "keyboard", is_filtered: false, char_count: 12 }],
  }),
  search_text: async (keyword) => ({ keyword, results: [] }),
}
