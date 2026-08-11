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

export interface TimeDistItem {
  category: string
  minutes: number
  percent: number
}

export interface TaskStatus {
  status: "pending" | "running" | "done" | "failed"
  result: { markdown?: string; saved_path?: string; extracted?: number; time_dist?: TimeDistItem[]; svg?: string } | null
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

export interface CategoryStatItem {
  category: string
  icon: string
  session_count: number
  active_seconds: number
  idle_seconds: number
}

export interface CategoryStats {
  range: { start: string; end: string; type: string }
  items: CategoryStatItem[]
  total_active: number
}

export interface CategoryItem {
  category: string
  icon: string
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
  segment_count?: number
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

// 待办事项
export type TodoStatus = "pending" | "in_progress" | "done" | "cancelled"
export type TodoPriority = "urgent" | "high" | "normal" | "low"

export interface Todo {
  id: number
  title: string
  status: TodoStatus
  priority: TodoPriority
  note: string
  due_date: string
  source_type: string // daily_report | weekly_report | monthly_report | manual
  source_ref: string
  is_draft: boolean
  created_at: string
  updated_at: string
  completed_at: string
  sort_order: number // 同列内手动排序（REAL，拖拽中间插值）
  progress: number // 完成进度 0-100（P2）；满 100 联动 status=done，可回退
}

// 待办统计（看板顶部 4 指标，PRD v4.3 §4.7）
export interface TodoStats {
  total: number // 全部已入库待办（is_draft=0）
  today_pending: number // 未完成且未逾期（无截止或 due_date >= 今天）
  overdue: number // 未完成且逾期（due_date < 今天）
  done: number // status=done
}

// 待办推进建议（AI 结合当日活动，P2 §4.6；只建议，用户采纳/忽略）
export interface TodoAdvice {
  id: number
  todo_id: number
  todo_title: string // 关联待办标题（待办已删除则显示「（待办已删除）」）
  suggestion_type: "start" | "progress" | "stall"
  reason: string
  suggested_status: string // start 建议的目标状态（in_progress）
  suggested_progress: number | null // progress 建议的目标进度 0-100
  status: "pending" | "applied" | "dismissed"
  source_date: string // 基于哪天的活动生成
  created_at: string
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
  export_data: (format: string, data_type: string, date?: string) => Promise<{ ok: boolean; path?: string; filename?: string; error?: string }>
  // 报告导出（html = 单文件；PDF 走前端 window.print，不经此接口）
  export_report: (format: string, report_type: string, date: string) => Promise<{ ok: boolean; path?: string; filename?: string; error?: string }>
  // 报告时间分布分析（task 模式，result 含 time_dist + 环形图 svg）
  analyze_report: (report_type: string, date: string) => Promise<{ task_id: string }>
  // 待办导出 CSV
  export_todos: (status?: string | null, include_drafts?: boolean) => Promise<{ ok: boolean; path?: string; filename?: string; count?: number; cancelled?: boolean; error?: string }>
  // 待办导出 JSON 全量备份（P4 §4.10，含 status/priority/sort_order/progress 全字段）
  export_todos_json: (status?: string | null, include_drafts?: boolean) => Promise<{ ok: boolean; path?: string; filename?: string; count?: number; cancelled?: boolean; error?: string }>
  // 待办导入 JSON 全量备份（P4 §4.10）；mode=append(同标题跳过) / merge(同标题更新)
  import_todos_json: (mode?: string) => Promise<{ ok: boolean; mode?: string; imported?: number; skipped?: number; updated?: number; errors?: string[]; cancelled?: boolean; error?: string }>
  save_api_config(provider: string, base_url: string, model: string, api_key: string): Promise<{ ok: boolean; restart_needed?: boolean; backup?: string; error?: string }>
  test_api_config(provider: string, base_url: string, model: string, api_key: string): Promise<{ ok: boolean; detail?: string; error?: string }>
  // 数据浏览
  get_app_stats(range_type: string, date: string): Promise<AppStats>
  get_sessions(date: string): Promise<SessionItem[]>
  get_session_detail(session_id: number): Promise<SessionDetail | null>
  search_text(keyword: string, limit?: number): Promise<{ keyword: string; results: SearchResult[] }>
  // 分类统计
  get_category_stats(range_type: string, date: string): Promise<CategoryStats>
  backfill_categories(): Promise<{ ok: boolean; updated?: number; error?: string }>
  get_categories(): Promise<CategoryItem[]>
  // 拼音转汉字
  convert_pinyin: (text: string) => Promise<{
    original: string;
    converted: string;
    has_pinyin: boolean;
    changed: boolean;
  }>
  // 隐私告知同意状态
  get_consent_status(): Promise<{ consented: boolean; window_only: boolean; timestamp: string }>
  set_consent(window_only: boolean): Promise<{ ok: boolean; error?: string }>
  // 专注模式
  start_focus_session: (goal: string, duration_minutes: number) => Promise<{ ok: boolean; session?: any; error?: string }>
  stop_focus_session: () => Promise<{ ok: boolean; session?: any }>
  get_focus_session: () => Promise<any | null>
  get_daily_efficiency: () => Promise<{
    work_seconds: number
    distraction_seconds: number
    total_seconds: number
    work_ratio: number
    distraction_ratio: number
    daily_goal_minutes: number
    goal_progress: number
    goal_achieved: boolean
    current_category: string
  }>
  set_daily_goal: (minutes: number) => Promise<{ ok: boolean; daily_goal_minutes?: number }>
  // 待办事项
  extract_todos: (report_type: string, date: string) => Promise<{ task_id: string }>
  get_todos: (status?: string | null, include_drafts?: boolean, source_ref?: string | null) => Promise<Todo[]>
  get_todo: (todo_id: number) => Promise<Todo | null>
  add_todo: (title: string, priority?: string, due_date?: string, note?: string) => Promise<{ ok: boolean; id?: number; error?: string }>
  update_todo: (todo_id: number, fields: Partial<Todo>) => Promise<{ ok: boolean; error?: string }>
  adopt_todos: (todo_ids: number[]) => Promise<{ ok: boolean; adopted?: number; error?: string }>
  delete_todo: (todo_id: number) => Promise<{ ok: boolean; error?: string }>
  // 看板拖拽：批量改 sort_order（前端算好新序后传入）
  reorder_todos: (items: { id: number; sort_order: number }[]) => Promise<{ ok: boolean; updated?: number; error?: string }>
  // 看板顶部统计（4 指标）
  get_todo_stats: () => Promise<TodoStats>
  // 待办推进建议（P2 §4.6）
  generate_todo_advices: (date?: string) => Promise<{ task_id: string }>
  get_todo_advices: () => Promise<TodoAdvice[]>
  apply_todo_advice: (advice_id: number) => Promise<{ ok: boolean; applied_type?: string; error?: string }>
  dismiss_todo_advice: (advice_id: number) => Promise<{ ok: boolean; error?: string }>
  // 待办提醒检查（手动触发，后端每小时自动；P3 §4.9）
  check_todo_notifications: () => Promise<{ ok: boolean; notified?: number; error?: string }>
  // 在资源管理器中定位导出的文件
  reveal_path: (path: string) => Promise<{ ok: boolean; error?: string }>
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

// 待办 mock 数据（浏览器 dev 预览用）
let mockTodoSeq = 100
const mockToday = new Date().toISOString().slice(0, 10)
let mockAdviceSeq = 50
let mockAdvices: TodoAdvice[] = []
let mockTodos: Todo[] = [
  { id: 1, title: "完成 GR1003 BOM 成本核算并提交采购评审", status: "in_progress", priority: "high", note: "", due_date: mockToday, source_type: "daily_report", source_ref: "2026-08-06", is_draft: false, created_at: "2026-08-06T18:00:00", updated_at: "2026-08-06T18:00:00", completed_at: "", sort_order: 1, progress: 60 },
  { id: 2, title: "跟进骨传导耳机样品交付期", status: "pending", priority: "normal", note: "", due_date: "", source_type: "daily_report", source_ref: "2026-08-06", is_draft: false, created_at: "2026-08-06T18:00:00", updated_at: "2026-08-06T18:00:00", completed_at: "", sort_order: 2, progress: 0 },
  { id: 3, title: "补充 MatePad 11.5 竞品对标表的续航数据", status: "pending", priority: "high", note: "", due_date: "2026-08-09", source_type: "daily_report", source_ref: "2026-08-05", is_draft: false, created_at: "2026-08-05T18:00:00", updated_at: "2026-08-05T18:00:00", completed_at: "", sort_order: 3, progress: 20 },
  { id: 4, title: "整理本周供应商邮件归档", status: "pending", priority: "low", note: "", due_date: "", source_type: "manual", source_ref: "", is_draft: false, created_at: "2026-08-05T10:00:00", updated_at: "2026-08-05T10:00:00", completed_at: "", sort_order: 4, progress: 0 },
  { id: 5, title: "对讲机 GH650 LTE 专网参数确认", status: "done", priority: "normal", note: "", due_date: "", source_type: "daily_report", source_ref: "2026-08-04", is_draft: false, created_at: "2026-08-04T18:00:00", updated_at: "2026-08-04T18:00:00", completed_at: "2026-08-04T17:30:00", sort_order: 5, progress: 100 },
  // 草稿区
  { id: 11, title: "整理 RugOne GR2002 PTT 骑行模式测试用例", status: "pending", priority: "normal", note: "", due_date: "", source_type: "daily_report", source_ref: mockToday, is_draft: true, created_at: "2026-08-07T09:00:00", updated_at: "2026-08-07T09:00:00", completed_at: "", sort_order: 11, progress: 0 },
  { id: 12, title: "本周五前回复客户报价单", status: "pending", priority: "high", note: "", due_date: "", source_type: "daily_report", source_ref: mockToday, is_draft: true, created_at: "2026-08-07T09:00:00", updated_at: "2026-08-07T09:00:00", completed_at: "", sort_order: 12, progress: 0 },
  { id: 13, title: "安排虚拟试衣 MVP 下周联调", status: "pending", priority: "low", note: "副业·可丢弃", due_date: "", source_type: "daily_report", source_ref: mockToday, is_draft: true, created_at: "2026-08-07T09:00:00", updated_at: "2026-08-07T09:00:00", completed_at: "", sort_order: 13, progress: 0 },
]

// 报告时间分布 mock（浏览器 dev 预览用）
const mockTimeDist: TimeDistItem[] = [
  { category: "开发编码", minutes: 180, percent: 45 },
  { category: "沟通会议", minutes: 120, percent: 30 },
  { category: "文档处理", minutes: 100, percent: 25 },
]
const mockDonutSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 460 150" font-family="-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif">
<circle cx="75" cy="75" r="55" fill="none" stroke="#0071e3" stroke-width="22" stroke-dasharray="154.9 191.3" stroke-dashoffset="0" transform="rotate(-90 75 75)"><title>开发编码: 45%</title></circle>
<circle cx="75" cy="75" r="55" fill="none" stroke="#34c759" stroke-width="22" stroke-dasharray="102.7 243.5" stroke-dashoffset="-155.5" transform="rotate(-90 75 75)"><title>沟通会议: 30%</title></circle>
<circle cx="75" cy="75" r="55" fill="none" stroke="#ff9500" stroke-width="22" stroke-dasharray="85.3 260.9" stroke-dashoffset="-258.8" transform="rotate(-90 75 75)"><title>文档处理: 25%</title></circle>
<text x="75" y="73" text-anchor="middle" font-size="20" font-weight="700" fill="#1d1d1f">5h20m</text>
<text x="75" y="89" text-anchor="middle" font-size="9" fill="#9a9a9f">总时长</text>
<rect x="180" y="22" width="10" height="10" rx="2" fill="#0071e3"/><text x="196" y="31" font-size="11" fill="#1d1d1f">开发编码</text><text x="450" y="31" text-anchor="end" font-size="11" fill="#6e6e73">180m · 45%</text>
<rect x="180" y="58" width="10" height="10" rx="2" fill="#34c759"/><text x="196" y="67" font-size="11" fill="#1d1d1f">沟通会议</text><text x="450" y="67" text-anchor="end" font-size="11" fill="#6e6e73">120m · 30%</text>
<rect x="180" y="94" width="10" height="10" rx="2" fill="#ff9500"/><text x="196" y="103" font-size="11" fill="#1d1d1f">文档处理</text><text x="450" y="103" text-anchor="end" font-size="11" fill="#6e6e73">100m · 25%</text>
</svg>`

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
  get_task_status: async (task_id?: string) => {
    if (task_id && task_id.startsWith("analyze")) {
      return { status: "done" as const, result: { time_dist: mockTimeDist, svg: mockDonutSvg }, error: null }
    }
    return {
      status: "done" as const,
      result: task_id && task_id.startsWith("extract") ? { extracted: 3 } : { markdown: "# 日报（mock）", saved_path: "" },
      error: null,
    }
  },
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
  export_data: async () => ({ ok: true, path: "mock/export.csv", filename: "export.csv" }),
  export_report: async (format: string, report_type: string, date: string) =>
    format === "html"
      ? { ok: true, path: `mock/${report_type}_${date}_report.html`, filename: `${report_type}_${date}_report.html` }
      : { ok: false, error: "PDF 请点「导出 PDF」用打印另存" },
  analyze_report: async () => ({ task_id: "analyze-mock" }),
  export_todos: async () => ({ ok: true, path: "mock/todos.csv", filename: "todos.csv", count: 8 }),
  export_todos_json: async () => ({ ok: true, path: "mock/todos.json", filename: "todos.json", count: 8 }),
  import_todos_json: async () => ({ ok: true, mode: "append", imported: 3, skipped: 5, updated: 0, errors: [] }),
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
  get_category_stats: async () => ({
    range: { start: "2026-07-02", end: "2026-07-02", type: "today" },
    total_active: 8700,
    items: [
      { category: "开发工具", icon: "💻", session_count: 12, active_seconds: 5200, idle_seconds: 300 },
      { category: "浏览器", icon: "🌐", session_count: 8, active_seconds: 2400, idle_seconds: 200 },
    ],
  }),
  backfill_categories: async () => ({ ok: true, updated: 0 }),
  get_categories: async () => [
    { category: "开发工具", icon: "💻" },
    { category: "浏览器", icon: "🌐" },
    { category: "通讯社交", icon: "💬" },
    { category: "办公文档", icon: "📄" },
    { category: "设计创作", icon: "🎨" },
    { category: "娱乐休闲", icon: "🎮" },
    { category: "系统工具", icon: "⚙️" },
    { category: "数据库", icon: "🗄️" },
    { category: "AI 工具", icon: "🤖" },
    { category: "其他", icon: "📦" },
  ],
  convert_pinyin: async (text: string) => ({ original: text, converted: text, has_pinyin: false, changed: false }),
  get_consent_status: async () => ({ consented: false, window_only: false, timestamp: "" }),
  set_consent: async () => ({ ok: true }),
  // 专注模式 mock
  start_focus_session: async (goal: string, duration_minutes: number) => ({
    ok: true,
    session: {
      goal,
      duration_minutes,
      start_time: new Date().toISOString(),
      end_time: new Date(Date.now() + duration_minutes * 60000).toISOString(),
      remaining_minutes: duration_minutes,
      elapsed_minutes: 0,
      distraction_seconds: 0,
      work_seconds: 0,
      distraction_ratio: 0,
      reminders_sent: 0,
      is_active: true,
    },
  }),
  stop_focus_session: async () => ({ ok: true, session: null }),
  get_focus_session: async () => null,
  get_daily_efficiency: async () => ({
    work_seconds: 14400,
    distraction_seconds: 1800,
    total_seconds: 16200,
    work_ratio: 0.889,
    distraction_ratio: 0.111,
    daily_goal_minutes: 480,
    goal_progress: 0.5,
    goal_achieved: false,
    current_category: "开发工具",
  }),
  set_daily_goal: async (minutes: number) => ({ ok: true, daily_goal_minutes: minutes }),
  // 待办 mock
  extract_todos: async () => {
    const now = new Date().toISOString()
    const seeds = ["整理 RugOne GR2002 测试用例", "回复客户报价单", "安排下周联调"]
    seeds.forEach((title) => {
      mockTodoSeq++
      mockTodos.push({ id: mockTodoSeq, title, status: "pending", priority: "normal", note: "", due_date: "", source_type: "daily_report", source_ref: mockToday, is_draft: true, created_at: now, updated_at: now, completed_at: "", sort_order: mockTodoSeq, progress: 0 })
    })
    return { task_id: "extract-mock" }
  },
  get_todos: async (status?: string | null, include_drafts = true, source_ref?: string | null) =>
    mockTodos.filter((t) => (!status || t.status === status) && (include_drafts || !t.is_draft) && (!source_ref || t.source_ref === source_ref)),
  get_todo: async (id: number) => mockTodos.find((t) => t.id === id) ?? null,
  add_todo: async (title: string, priority = "normal", due_date = "", note = "") => {
    mockTodoSeq++
    const now = new Date().toISOString()
    mockTodos.push({ id: mockTodoSeq, title, status: "pending", priority: priority as TodoPriority, note, due_date, source_type: "manual", source_ref: "", is_draft: false, created_at: now, updated_at: now, completed_at: "", sort_order: mockTodoSeq, progress: 0 })
    return { ok: true, id: mockTodoSeq }
  },
  update_todo: async (id: number, fields: Partial<Todo>) => {
    const t = mockTodos.find((x) => x.id === id)
    if (t) {
      const next = { ...fields } as Partial<Todo>
      // progress ↔ done 联动（模拟后端语义，dev 预览可见）
      if (next.progress !== undefined) {
        const p = Math.max(0, Math.min(100, Math.round(Number(next.progress) || 0)))
        next.progress = p
        if (p >= 100) next.status = "done"
        else if (t.status === "done") next.status = "in_progress"
      }
      Object.assign(t, next, { updated_at: new Date().toISOString() })
      if (next.status === "done") t.completed_at = new Date().toISOString()
      else if (next.status && next.status !== "done") t.completed_at = ""
    }
    return { ok: !!t }
  },
  adopt_todos: async (ids: number[]) => {
    let n = 0
    mockTodos.forEach((t) => {
      if (ids.includes(t.id) && t.is_draft) {
        t.is_draft = false
        t.updated_at = new Date().toISOString()
        n++
      }
    })
    return { ok: true, adopted: n }
  },
  delete_todo: async (id: number) => {
    const before = mockTodos.length
    mockTodos = mockTodos.filter((t) => t.id !== id)
    return { ok: mockTodos.length < before }
  },
  reorder_todos: async (items: { id: number; sort_order: number }[]) => {
    let n = 0
    items.forEach((it) => {
      const t = mockTodos.find((x) => x.id === it.id)
      if (t) {
        t.sort_order = it.sort_order
        n++
      }
    })
    return { ok: true, updated: n }
  },
  get_todo_stats: async () => {
    const today = new Date().toISOString().slice(0, 10)
    const real = mockTodos.filter((t) => !t.is_draft)
    let today_pending = 0
    let overdue = 0
    let done = 0
    real.forEach((t) => {
      if (t.status === "done") done++
      else if (t.status === "pending" || t.status === "in_progress") {
        if (t.due_date && t.due_date < today) overdue++
        else today_pending++
      }
    })
    return { total: real.length, today_pending, overdue, done }
  },
  generate_todo_advices: async (_date?: string) => {
    // dev 预览：为未完成正式待办造 1-2 条示例建议（去重：同 todo 已有 pending 跳过）
    const now = new Date().toISOString()
    const active = mockTodos.filter((t) => !t.is_draft && (t.status === "pending" || t.status === "in_progress"))
    active.slice(0, 2).forEach((t) => {
      if (mockAdvices.some((a) => a.todo_id === t.id && a.status === "pending")) return
      mockAdviceSeq++
      mockAdvices.push({
        id: mockAdviceSeq, todo_id: t.id, todo_title: t.title,
        suggestion_type: t.progress > 0 ? "progress" : "start",
        reason: "今日检测到相关应用活动，建议推进",
        suggested_status: t.progress > 0 ? "" : "in_progress",
        suggested_progress: t.progress > 0 ? Math.min(100, t.progress + 30) : null,
        status: "pending", source_date: mockToday, created_at: now,
      })
    })
    return { task_id: "advice-mock" }
  },
  get_todo_advices: async () => mockAdvices.filter((a) => a.status === "pending"),
  apply_todo_advice: async (advice_id: number) => {
    const a = mockAdvices.find((x) => x.id === advice_id)
    if (!a || a.status !== "pending") return { ok: false }
    const now = new Date().toISOString()
    if (a.suggestion_type === "start") {
      const t = mockTodos.find((x) => x.id === a.todo_id)
      if (t) { t.status = (a.suggested_status as TodoStatus) || "in_progress"; t.updated_at = now }
    } else if (a.suggestion_type === "progress") {
      const t = mockTodos.find((x) => x.id === a.todo_id)
      if (t && a.suggested_progress !== null) {
        const p = Math.min(100, a.suggested_progress)
        t.progress = p; t.updated_at = now
        if (p >= 100) { t.status = "done"; t.completed_at = now }
      }
    }
    // stall：不动待办
    a.status = "applied"
    return { ok: true, applied_type: a.suggestion_type }
  },
  dismiss_todo_advice: async (advice_id: number) => {
    const a = mockAdvices.find((x) => x.id === advice_id)
    if (a) a.status = "dismissed"
    return { ok: !!a }
  },
  check_todo_notifications: async () => ({ ok: true, notified: 0 }),
  reveal_path: async (_path: string) => ({ ok: true }),
}
