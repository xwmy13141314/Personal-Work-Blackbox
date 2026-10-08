import React from "react";
import { Shield, Lock, Github, Mail, Database, EyeOff, Code2, Heart, History } from "lucide-react";
import logo from "@/assets/logo.png";

// ==================== 关于视图 ====================

const APP_VERSION = "V5.79.0914";
const APP_TAGLINE = "您的私有工作黑盒";
const CONTACT_EMAIL = "xwmy1314@gmail.com";
const GITHUB_URL = "https://github.com/xwmy13141314/Personal-Work-Blackbox";

export function AboutView() {
  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
      {/* ===== 应用信息卡 ===== */}
      <div
        className="rounded-2xl border border-black/[0.07] bg-white/70 p-5 flex items-center gap-4"
        style={{ backdropFilter: "blur(12px)" }}
      >
        <img src={logo} alt="WorkTrace" className="w-14 h-14 rounded-[12px] shrink-0 shadow-sm" />
        <div className="min-w-0">
          <h1 className="text-[19px] font-semibold text-[var(--wt-text)] tracking-tight">职迹 WorkTrace</h1>
          <p className="text-[12px] text-[var(--wt-text-muted)] mt-0.5">{APP_TAGLINE}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-[var(--wt-accent)]/10 text-[var(--wt-accent)]">
              {APP_VERSION}
            </span>
            <span className="text-[11px] text-[var(--wt-text-tertiary)]">macOS · Apple Silicon</span>
          </div>
        </div>
      </div>

      {/* ===== 版本更新记录 ===== */}
      <div
        className="rounded-2xl border border-black/[0.07] bg-white/70 p-4"
        style={{ backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-1.5 mb-3">
          <History className="w-4 h-4 text-[var(--wt-accent)]" />
          <div>
            <p className="text-[13px] font-semibold text-[var(--wt-text)]">版本更新记录</p>
            <p className="text-[11px] text-[var(--wt-text-muted)]">版本格式：V5.主更新号.日期；每次更新主更新号加 1</p>
          </div>
        </div>
        <div
          className="max-h-[430px] space-y-3 overflow-y-auto overscroll-contain pr-2"
          title="更新记录超过当前高度时可在此区域滚动查看"
        >
          <VersionEntry version="V5.79.0914" date="2026-09-14" items={["腾讯文档定时识别支持错过 09:00 后当日补跑", "仅在提取完成后标记成功，失败会显示状态并在 5 分钟后重试"]} />
          <VersionEntry version="V5.78.0909" date="2026-09-09" items={["AI 提取待确认区支持多选、全选、批量采纳和批量丢弃", "批量操作仅作用于草稿，丢弃项可在已删除中恢复"]} />
          <VersionEntry version="V5.77.0907" date="2026-09-07" items={["键盘回退状态改为真实监听状态，避免把尚未收到按键误报为未授权", "录制初期加快键盘状态刷新"]} />
          <VersionEntry version="V5.76.0907" date="2026-09-07" items={["修复权限探测异常导致另一项权限被误报未授权", "修复 macOS 桌面前端构建脚本兼容性"]} />
          <VersionEntry version="V5.75.0826" date="2026-08-26" items={["降低本地 Vision OCR 后台频率，减少持续 CPU 与发热", "跳过 WorkTrace 自身 OCR，并减少 OCR 状态日志写入"]} />
          <VersionEntry version="V5.74.0825" date="2026-08-25" items={["外部 App 屏幕 OCR 改按实际窗口边界抓图", "修复微信等窗口使用空矩形截图时返回空图像的问题"]} />
          <VersionEntry version="V5.73.0825" date="2026-08-25" items={["修复辅助功能未识别时屏幕 OCR 回退被提前拦截", "已授权屏幕录制时外部 App 可继续使用本地 OCR 备用采集"]} />
          <VersionEntry version="V5.72.0825" date="2026-08-25" items={["屏幕录制授权改为以实际窗口图像可用性判定", "避免 macOS 权限预检缓存导致已授权仍被错误拦截"]} />
          <VersionEntry version="V5.71.0825" date="2026-08-25" items={["修复 Cocoa WebView 先创建空桥接对象、后挂载方法造成的连接失败", "状态与启动按钮仅在真实桥接方法可调用后启用"]} />
          <VersionEntry version="V5.70.0825" date="2026-08-25" items={["修复 macOS WebView 桥接事件早于页面加载时导致状态永久加载中的问题", "启动录制改为可明确提示本地服务连接状态，不再静默无响应", "状态读取与非关键配置读取拆分，配置错误不再阻塞录制控制"]} />
          <VersionEntry version="V5.69.0824" date="2026-08-24" items={["输入法文本按产生当刻的前台 App 归属，避免切换窗口后错记", "新增输入监控授权入口与按键接收计数，键盘回退可真实验收", "明确区分辅助功能、输入监控和屏幕录制三项独立 macOS 权限"]} />
          <VersionEntry version="V5.67.0820" date="2026-08-20" items={["键盘回退改为直接读取物理按键码", "中文输入法未公开文本时仍按当前 App 保存拼音、英文和数字", "快捷键、密码上下文和隐私过滤继续生效"]} />
          <VersionEntry version="V5.66.0820" date="2026-08-20" items={["外部 App 输入新增键盘事件兜底", "无法读取输入框时仍保存实际键入的拼音、英文和数字", "快捷键、密码上下文和隐私过滤继续生效"]} />
          <VersionEntry version="V5.65.0818" date="2026-08-18" items={["设置页新增屏幕录制权限入口", "明确区分辅助功能和外部 App 本地屏幕识别所需的权限"]} />
          <VersionEntry version="V5.64.0817" date="2026-08-17" items={["空辅助功能输入值也会进入外部 App 本地屏幕识别回退", "新增不含输入内容的识别状态诊断，便于确认权限、窗口与 OCR 是否正常"]} />
          <VersionEntry version="V5.63.0817" date="2026-08-17" items={["新增微信等外部 App 的本地屏幕识别兼容模式", "仅识别前台窗口底部输入区域，截图不落盘、不上传"]} />
          <VersionEntry version="V5.62.0817" date="2026-08-17" items={["修正辅助功能状态判定，不再把键盘钩子当作外部文本读取权限", "新增系统级焦点回退，并明确提示当前 App 是否公开输入框"]} />
          <VersionEntry version="V5.61.0817" date="2026-08-17" items={["补充 compositionend 最终上屏监听，覆盖搜狗/豆包 WebKit 输入", "最终输入源读取改为即时刷新，避免轮询延迟丢失记录"]} />
          <VersionEntry version="V5.60.0814" date="2026-08-14" items={["修复 WebView 输入框无法读取搜狗/豆包最终上屏文本", "增加系统级焦点回退，过滤未确认拼音片段"]} />
          <VersionEntry version="V5.59.0814" date="2026-08-14" items={["HTML 报告导出后自动使用默认浏览器打开"]} />
          <VersionEntry version="V5.58.0814" date="2026-08-14" items={["腾讯文档链接库按第 1、2、3 条清晰记录，支持新增、切换与删除"]} />
          <VersionEntry version="V5.57.0814" date="2026-08-14" items={["修复 HTML 导出缺少 Markdown fenced_code / sane_lists 扩展导致的报错"]} />
          <VersionEntry version="V5.56.0814" date="2026-08-14" items={["腾讯文档重复导入会明确提示已识别但无新增，不再误报为导入失败"]} />
          <VersionEntry version="V5.55.0814" date="2026-08-14" items={["修复输入法乱码回退误记；扩展 ChatGPT、钉钉、微信等网页/Electron 编辑器的确认文本读取"]} />
          <VersionEntry version="V5.54.0814" date="2026-08-14" items={["腾讯文档链接库支持命名、保存、切换、更新与删除；每日 09:00 自动识别当前选中链接"]} />
          <VersionEntry version="V5.53.0814" date="2026-08-14" items={["辅助功能授权提示改为仅在设置中手动打开；重新检测不再触发系统授权入口或影响原有授权条目"]} />
          <VersionEntry version="V5.52.0814" date="2026-08-14" items={["修复输入法确认文本可能归属到上一应用的问题，补充 Electron/网页编辑器的文本属性读取"]} />
          <VersionEntry version="V5.51.0814" date="2026-08-14" items={["右侧录制状态、使用提示与日历改为侧边栏按钮按需展开，默认释放主工作区"]} />
          <VersionEntry version="V5.50.0814" date="2026-08-14" items={["修复腾讯智能表动态画布数据未被读取的问题，公开表格可正确识别待办列并导入草稿区"]} />
          <VersionEntry version="V5.49.0814" date="2026-08-14" items={["腾讯智能表按项目、待办、状态、安排对象等字段导入草稿区，支持每日 09:00 自动识别"]} />
          <VersionEntry version="V5.48.0814" date="2026-08-14" items={["待办状态圆圈改为左键选择状态、右键直接切换状态"]} />
          <VersionEntry version="V5.47.0814" date="2026-08-14" items={["修复已授权但被辅助功能提示误拦截的问题，监听器已正常运行时不再阻塞使用"]} />
          <VersionEntry version="V5.46.0814" date="2026-08-14" items={["进度备注支持编号事项，AI 识别会将待办拆分为最多 4 项可执行事项"]} />
          <VersionEntry version="V5.45.0814" date="2026-08-14" items={["待办状态圆圈支持长按，直接选择待办、进行中、已完成或删除"]} />
          <VersionEntry version="V5.44.0814" date="2026-08-14" items={["新增按需展开的已删除模块，支持恢复或彻底删除"]} />
          <VersionEntry version="V5.43.0814" date="2026-08-14" items={["移除待办卡片进度条，解决拖拽图标与编辑按钮重叠"]} />
          <VersionEntry version="V5.42.0814" date="2026-08-14" items={["待办卡片新增可直接编辑的对接人"]} />
          <VersionEntry version="V5.41.0814" date="2026-08-14" items={["移除侧边栏待办导航的“新”标记"]} />
          <VersionEntry version="V5.40.0814" date="2026-08-14" items={["补齐关于页版本更新记录，最新版本与更新内容同步显示"]} />
          <VersionEntry version="V5.39.0814" date="2026-08-14" items={["待办卡片新增独立进度备注，可直接编辑保存", "卡片统一展示标题、内容、备注、重要程度与计划时间"]} />
          <VersionEntry version="V5.38.0813" date="2026-08-13" items={["修复豆包/搜狗语音转文字漏记，增加系统 Unicode 文本后备采集", "AX 监听与系统事件自动去重"]} />
          <VersionEntry version="V5.37.0813" date="2026-08-13" items={["活动明细改为按 App 切换分组，同一 App 连续输入合并显示"]} />
          <VersionEntry version="V5.36.0813" date="2026-08-13" items={["待办卡片的重要程度和计划完成日期支持直接修改"]} />
          <VersionEntry version="V5.35.0813" date="2026-08-13" items={["修复新建待办文本识别失败，AI 不可用时自动用本地规则整理"]} />
          <VersionEntry version="V5.34.0813" date="2026-08-13" items={["黄色便签图标移除外侧白边，完整铺满 App 图标"]} />
          <VersionEntry version="V5.33.0813" date="2026-08-13" items={["待办卡片改为标题和内容分离展示、编辑"]} />
          <VersionEntry version="V5.32.0813" date="2026-08-13" items={["新建待办可通过 AI 识别标题、内容、优先级和计划完成日"]} />
          <VersionEntry version="V5.31.0813" date="2026-08-13" items={["腾讯文档按表格逐行识别任务、状态、优先级和日期"]} />
          <VersionEntry version="V5.30.0813" date="2026-08-13" items={["豆包/搜狗确认文本和语音转文字即时写入本地记录"]} />
          <VersionEntry version="V5.29.0813" date="2026-08-13" items={["修复 macOS 空文本框首次输入的 AXValue 识别问题"]} />
          <VersionEntry version="V5.28.0813" date="2026-08-13" items={["修复空输入框首次豆包/搜狗确认内容漏记"]} />
          <VersionEntry version="V5.27.0813" date="2026-08-13" items={["应用内与 Dock/Finder 统一使用黄色便签品牌图标"]} />
          <VersionEntry version="V5.26.0813" date="2026-08-13" items={["输入法确认文字即时保存，语音中的数字、英文与标点完整保留"]} />
          <VersionEntry version="V5.25.0813" date="2026-08-13" items={["统一 WorkTrace 品牌图标资源"]} />
          <VersionEntry version="V5.24.0813" date="2026-08-13" items={["修复腾讯文档 HTTPS 证书路径和网络错误提示"]} />
          <VersionEntry version="V5.23.0813" date="2026-08-13" items={["修复 API 配置异步回填与重启显示问题"]} />
          <VersionEntry version="V5.22.0813" date="2026-08-13" items={["修复关闭窗口后的 Dock 恢复与退出逻辑"]} />
          <VersionEntry
            version="V5.21.0813"
            date="2026-08-13"
            items={["每次启动都会安全检查旧版 API 配置迁移", "旧版有效 Key 会自动迁移，已有永久配置不会被覆盖"]}
          />
          <VersionEntry
            version="V5.20.0813"
            date="2026-08-13"
            items={["修复 py2app 启动时应用路径识别失败", "已有 API Key 将自动迁移到永久用户配置目录"]}
          />
          <VersionEntry
            version="V5.19.0813"
            date="2026-08-13"
            items={["修复旧版 API Key 自动迁移遗漏模板占位配置的问题", "强化 App 路径识别，确保配置始终存入永久用户目录"]}
          />
          <VersionEntry
            version="V5.18.0813"
            date="2026-08-13"
            items={["API 配置改存用户 Application Support 目录，更新不覆盖", "首次升级自动迁移已有 API Key，无需重新输入"]}
          />
          <VersionEntry
            version="V5.17.0813"
            date="2026-08-13"
            items={["红色关闭按钮改为隐藏窗口到 Dock", "应用继续运行与采集，可从 Dock 再次打开窗口"]}
          />
          <VersionEntry
            version="V5.16.0813"
            date="2026-08-13"
            items={["关闭窗口立即响应，不再等待采集器和日志导出", "退出收尾在后台完成后自动结束应用进程"]}
          />
          <VersionEntry
            version="V5.15.0813"
            date="2026-08-13"
            items={["补齐 AI 网络请求所需的 anyio 等运行依赖", "修复“测试连接”提示 anyio._backends 缺失的问题"]}
          />
          <VersionEntry
            version="V5.14.0813"
            date="2026-08-13"
            items={["修复 py2app 环境未加载证书配置的问题", "每个 AI HTTPS 请求都明确使用 App 内置根证书"]}
          />
          <VersionEntry
            version="V5.13.0813"
            date="2026-08-13"
            items={["修复 macOS 打包版缺少 HTTPS 根证书导致 AI 测试连接失败的问题", "日报与智能待办将使用 App 内置证书建立加密连接"]}
          />
          <VersionEntry
            version="V5.12.0813"
            date="2026-08-13"
            items={["文字输入仅记录豆包输入法和搜狗输入法的最终确认内容", "剪贴板图片在本机识别文字后记录，原图不保存"]}
          />
          <VersionEntry
            version="V5.11.0813"
            date="2026-08-13"
            items={["新建待办支持本地选图和剪贴板图片识别", "本机识别文字后自动补全任务信息，确认后再添加"]}
          />
          <VersionEntry
            version="V5.10.0813"
            date="2026-08-13"
            items={["移除 WorkTrace 自己的麦克风与系统语音识别功能", "记录豆包输入法提交的最终文本，并在活动中标记来源"]}
          />
          <VersionEntry
            version="V5.9.0813"
            date="2026-08-13"
            items={["语音输入改为按需开启，普通录制不占用麦克风", "暂停或停止录制时立即释放麦克风"]}
          />
          <VersionEntry
            version="V5.8.0813"
            date="2026-08-13"
            items={["恢复上一版品牌图标视觉", "页面内 Logo 与 macOS App 图标统一使用原始 512px 品牌图"]}
          />
          <VersionEntry
            version="V5.7.0813"
            date="2026-08-13"
            items={["版本更新记录限制为固定可视高度", "新增版本可在记录区域内向上滚动查看"]}
          />
          <VersionEntry
            version="V5.6.0813"
            date="2026-08-13"
            items={["统一 macOS App 与应用内界面的蓝色无限符号 Logo", "Finder、Dock 和页面内标识使用同一源图"]}
          />
          <VersionEntry
            version="V5.5.0813"
            date="2026-08-13"
            items={["优化大字体下待办工具栏的自适应布局", "按钮不再逐字换行，空间不足时会自然整齐分行"]}
          />
          <VersionEntry
            version="V5.4.0813"
            date="2026-08-13"
            items={["修复字体大小设置未实际影响界面文字的问题", "13–17px 设置现在即时缩放全应用文字与行高"]}
          />
          <VersionEntry
            version="V5.3.0813"
            date="2026-08-13"
            items={["新建待办新增可选对接人字段", "对接人独立本地保存，并显示在待办卡片中"]}
          />
          <VersionEntry
            version="V5.2.0813"
            date="2026-08-13"
            items={[
              "新增本地文档批量导入（TXT、Markdown、CSV、Word、PDF）",
              "逐份智能识别待办并进入待确认草稿区",
            ]}
          />
          <VersionEntry
            version="V5.1.0813"
            date="2026-08-13"
            items={[
              "完成 macOS 原生打包与启动稳定性修复",
              "日历中文化、满宽显示与高对比度优化",
              "新增语音转文字记录与智能新建待办",
              "新增腾讯文档待办提取与辅助功能权限误报修复",
            ]}
          />
          <VersionEntry
            version="V5.0.0812"
            date="2026-08-12"
            items={["建立 macOS 版基线，完成本地工作记录、报告与待办看板迁移"]}
          />
        </div>
      </div>

      {/* ===== 隐私承诺卡 ===== */}
      <div
        className="rounded-2xl border border-black/[0.07] bg-white/70 p-4"
        style={{ backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-1.5 mb-3">
          <Shield className="w-4 h-4 text-[var(--wt-accent)]" />
          <p className="text-[13px] font-semibold text-[var(--wt-text)]">隐私承诺</p>
        </div>
        <div className="grid grid-cols-1 gap-2.5">
          <PrivacyItem
            icon={Database}
            title="本地存储"
            desc="所有数据存储在本地 SQLite 数据库，绝不上传到云端"
          />
          <PrivacyItem
            icon={EyeOff}
            title="三层隐私过滤"
            desc="密码、敏感信息、隐私模式三层过滤，自动识别并屏蔽"
          />
          <PrivacyItem
            icon={Code2}
            title="开源可审计"
            desc="核心代码完全开源，任何人可审查数据处理流程"
          />
          <PrivacyItem
            icon={Lock}
            title="可选数据库加密"
            desc="支持 SQLCipher 加密，数据文件即使被复制也无法读取"
          />
        </div>
      </div>

      {/* ===== 联系方式卡 ===== */}
      <div
        className="rounded-2xl border border-black/[0.07] bg-white/70 p-4 space-y-2"
        style={{ backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-1.5 mb-2">
          <Mail className="w-4 h-4 text-[var(--wt-accent)]" />
          <p className="text-[13px] font-semibold text-[var(--wt-text)]">联系方式</p>
        </div>

        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-black/[0.04] transition-all group"
        >
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-lime-300 to-lime-600 flex items-center justify-center shrink-0 shadow-sm">
            <Mail className="w-3.5 h-3.5 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] text-[var(--wt-text-muted)] leading-tight">邮箱</p>
            <p className="text-[13px] font-medium text-[var(--wt-text)] truncate group-hover:text-[var(--wt-accent)] transition-colors">
              {CONTACT_EMAIL}
            </p>
          </div>
        </a>

        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-black/[0.04] transition-all group"
        >
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-gray-700 to-gray-900 flex items-center justify-center shrink-0 shadow-sm">
            <Github className="w-3.5 h-3.5 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] text-[var(--wt-text-muted)] leading-tight">GitHub</p>
            <p className="text-[13px] font-medium text-[var(--wt-text)] truncate group-hover:text-[var(--wt-accent)] transition-colors">
              Personal-Work-Blackbox
            </p>
          </div>
        </a>
      </div>

      {/* ===== 技术栈卡 ===== */}
      <div
        className="rounded-2xl border border-black/[0.07] bg-white/70 p-4"
        style={{ backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-1.5 mb-2">
          <Code2 className="w-4 h-4 text-[var(--wt-accent)]" />
          <p className="text-[13px] font-semibold text-[var(--wt-text)]">技术栈</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {["Python", "pywebview", "React", "TypeScript", "SQLite", "Tailwind CSS"].map((tech) => (
            <span
              key={tech}
              className="px-2 py-0.5 rounded-md text-[11.5px] font-medium bg-black/[0.04] text-[var(--wt-text-secondary)] border border-black/[0.06]"
            >
              {tech}
            </span>
          ))}
        </div>
      </div>

      {/* ===== 版权信息 ===== */}
      <div className="flex items-center justify-center gap-1 pt-1 pb-2">
        <p className="text-[11px] text-[var(--wt-text-tertiary)]">
          © 2026 职迹 WorkTrace
        </p>
        <span className="text-[var(--wt-text-tertiary)] text-[11px]">·</span>
        <p className="text-[11px] text-[var(--wt-text-tertiary)] flex items-center gap-0.5">
          Made with <Heart className="w-2.5 h-2.5 text-red-400 fill-red-400" /> for productivity
        </p>
      </div>
    </div>
  );
}

function VersionEntry({ version, date, items }: { version: string; date: string; items: string[] }) {
  return (
    <div className="border-l-2 border-[var(--wt-accent)]/40 pl-3">
      <div className="flex items-baseline gap-2">
        <span className="text-[12px] font-semibold text-[var(--wt-text)]">{version}</span>
        <span className="text-[11px] text-[var(--wt-text-muted)]">{date}</span>
      </div>
      <ul className="mt-1 space-y-0.5 text-[11.5px] leading-relaxed text-[var(--wt-text-secondary)]">
        {items.map((item) => <li key={item}>· {item}</li>)}
      </ul>
    </div>
  );
}

// ==================== 子组件 ====================

function PrivacyItem({
  icon: Icon,
  title,
  desc,
}: {
  icon: typeof Shield;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="w-7 h-7 rounded-lg bg-[var(--wt-accent)]/10 flex items-center justify-center shrink-0 mt-0.5">
        <Icon className="w-3.5 h-3.5 text-[var(--wt-accent)]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[12.5px] font-medium text-[var(--wt-text)] leading-tight">{title}</p>
        <p className="text-[11.5px] text-[var(--wt-text-muted)] mt-0.5 leading-relaxed">{desc}</p>
      </div>
    </div>
  );
}
