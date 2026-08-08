import React from "react";
import { Shield, Lock, Github, Mail, Database, EyeOff, Code2, Heart } from "lucide-react";
import logo from "@/assets/logo.png";

// ==================== 关于视图 ====================

const APP_VERSION = "4.2.0";
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
          <h1 className="text-[18px] font-semibold text-[var(--wt-text)] tracking-tight">职迹 WorkTrace</h1>
          <p className="text-[11px] text-[var(--wt-text-muted)] mt-0.5">{APP_TAGLINE}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[var(--wt-accent)]/10 text-[var(--wt-accent)]">
              v{APP_VERSION}
            </span>
            <span className="text-[10px] text-[var(--wt-text-tertiary)]">Windows · x64</span>
          </div>
        </div>
      </div>

      {/* ===== 隐私承诺卡 ===== */}
      <div
        className="rounded-2xl border border-black/[0.07] bg-white/70 p-4"
        style={{ backdropFilter: "blur(12px)" }}
      >
        <div className="flex items-center gap-1.5 mb-3">
          <Shield className="w-4 h-4 text-[var(--wt-accent)]" />
          <p className="text-[12px] font-semibold text-[var(--wt-text)]">隐私承诺</p>
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
          <p className="text-[12px] font-semibold text-[var(--wt-text)]">联系方式</p>
        </div>

        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-black/[0.04] transition-all group"
        >
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shrink-0 shadow-sm">
            <Mail className="w-3.5 h-3.5 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] text-[var(--wt-text-muted)] leading-tight">邮箱</p>
            <p className="text-[12px] font-medium text-[var(--wt-text)] truncate group-hover:text-[var(--wt-accent)] transition-colors">
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
            <p className="text-[10px] text-[var(--wt-text-muted)] leading-tight">GitHub</p>
            <p className="text-[12px] font-medium text-[var(--wt-text)] truncate group-hover:text-[var(--wt-accent)] transition-colors">
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
          <p className="text-[12px] font-semibold text-[var(--wt-text)]">技术栈</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {["Python", "pywebview", "React", "TypeScript", "SQLite", "Tailwind CSS"].map((tech) => (
            <span
              key={tech}
              className="px-2 py-0.5 rounded-md text-[10.5px] font-medium bg-black/[0.04] text-[var(--wt-text-secondary)] border border-black/[0.06]"
            >
              {tech}
            </span>
          ))}
        </div>
      </div>

      {/* ===== 版权信息 ===== */}
      <div className="flex items-center justify-center gap-1 pt-1 pb-2">
        <p className="text-[10px] text-[var(--wt-text-tertiary)]">
          © 2026 职迹 WorkTrace
        </p>
        <span className="text-[var(--wt-text-tertiary)] text-[10px]">·</span>
        <p className="text-[10px] text-[var(--wt-text-tertiary)] flex items-center gap-0.5">
          Made with <Heart className="w-2.5 h-2.5 text-red-400 fill-red-400" /> for productivity
        </p>
      </div>
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
        <p className="text-[11.5px] font-medium text-[var(--wt-text)] leading-tight">{title}</p>
        <p className="text-[10.5px] text-[var(--wt-text-muted)] mt-0.5 leading-relaxed">{desc}</p>
      </div>
    </div>
  );
}
