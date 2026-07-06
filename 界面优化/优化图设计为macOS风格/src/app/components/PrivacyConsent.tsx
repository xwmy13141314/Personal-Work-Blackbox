import React, { useState } from "react";
import { CheckCircle2, Keyboard, AppWindow, Clipboard, EyeOff, HardDrive, ShieldCheck } from "lucide-react";

interface PrivacyConsentProps {
  onConsent: (windowOnly: boolean) => void;
  onDecline: () => void;
}

export function PrivacyConsent({ onConsent, onDecline }: PrivacyConsentProps) {
  const [windowOnly, setWindowOnly] = useState(false);

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.35)", backdropFilter: "blur(6px)" }}
      onClick={(e) => {
        // 点击遮罩不关闭，必须选择"同意"或"暂不使用"
        e.stopPropagation();
      }}
    >
      <div
        className="relative w-[460px] max-w-[92vw] max-h-[88vh] overflow-y-auto bg-white rounded-2xl shadow-2xl"
        style={{ boxShadow: "0 24px 80px rgba(0,0,0,0.28), 0 0 0 0.5px rgba(0,0,0,0.08)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部图标区 */}
        <div className="flex flex-col items-center pt-7 pb-3 px-6">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-3"
            style={{
              background: "linear-gradient(135deg, #0071e3, #34A0FF)",
              boxShadow: "0 6px 20px rgba(0,113,227,0.3)",
            }}
          >
            <ShieldCheck className="w-7 h-7 text-white" strokeWidth={2} />
          </div>
          <h1 className="text-[18px] font-semibold text-[#1d1d1f] tracking-tight">
            隐私告知与使用须知
          </h1>
          <p className="text-[11px] text-[#86868b] mt-1">首次使用前请阅读以下说明</p>
        </div>

        {/* 内容区 */}
        <div className="px-6 pb-4 space-y-4">
          {/* 采集内容说明 */}
          <div>
            <p className="text-[12px] font-semibold text-[#1d1d1f] mb-2">本工具将记录以下内容</p>
            <div className="space-y-1.5">
              <ConsentItem icon={Keyboard} title="输入活动" desc="记录键盘输入文本（按回车/Tab 提交时保存）" />
              <ConsentItem icon={AppWindow} title="窗口切换" desc="记录前台应用名称与窗口标题、使用时长" />
              <ConsentItem icon={Clipboard} title="剪贴板内容" desc="记录复制/剪切的文本片段" />
            </div>
          </div>

          {/* 数据存储说明 */}
          <div className="rounded-xl border border-black/[0.06] bg-[#f5f5f7] p-3">
            <div className="flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-green-50 flex items-center justify-center shrink-0 mt-0.5">
                <HardDrive className="w-3.5 h-3.5 text-green-600" />
              </div>
              <div className="min-w-0">
                <p className="text-[11.5px] font-medium text-[#1d1d1f]">数据仅存储在本地</p>
                <p className="text-[10.5px] text-[#6e6e73] leading-relaxed mt-0.5">
                  所有采集数据保存在本机 SQLite 数据库中，不上传任何服务器，不联网传输。
                </p>
              </div>
            </div>
          </div>

          {/* 隐私过滤说明 */}
          <div className="rounded-xl border border-black/[0.06] bg-[#f5f5f7] p-3">
            <div className="flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-orange-50 flex items-center justify-center shrink-0 mt-0.5">
                <EyeOff className="w-3.5 h-3.5 text-orange-500" />
              </div>
              <div className="min-w-0">
                <p className="text-[11.5px] font-medium text-[#1d1d1f]">三层隐私脱敏机制</p>
                <div className="text-[10.5px] text-[#6e6e73] leading-relaxed mt-1 space-y-0.5">
                  <p>1. 关键词过滤：密码、Token、身份证等敏感词自动屏蔽</p>
                  <p>2. 隐私模式：一键暂停所有文本采集，仅保留窗口活动</p>
                  <p>3. 本地加密：数据仅本机可读，AI 报告生成时再次脱敏</p>
                </div>
              </div>
            </div>
          </div>

          {/* 仅记录窗口活动选项 */}
          <label className="flex items-start gap-2.5 cursor-pointer rounded-xl border border-black/[0.08] bg-white p-3 hover:bg-black/[0.015] transition-colors">
            <div className="relative flex items-center justify-center w-[18px] h-[18px] shrink-0 mt-0.5">
              <input
                type="checkbox"
                checked={windowOnly}
                onChange={(e) => setWindowOnly(e.target.checked)}
                className="appearance-none w-[18px] h-[18px] rounded-[5px] border-2 border-[#d2d2d7] checked:border-[#0071e3] checked:bg-[#0071e3] cursor-pointer transition-colors"
              />
              {windowOnly && (
                <CheckCircle2
                  className="absolute w-3.5 h-3.5 text-white pointer-events-none"
                  strokeWidth={3}
                />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-[11.5px] font-medium text-[#1d1d1f]">仅记录窗口活动</p>
              <p className="text-[10.5px] text-[#86868b] leading-relaxed mt-0.5">
                勾选后不记录键盘输入与剪贴板内容，仅记录应用窗口切换与使用时长。
              </p>
            </div>
          </label>
        </div>

        {/* 按钮区 */}
        <div className="flex gap-2.5 px-6 pb-6 pt-1">
          <button
            onClick={() => onDecline()}
            className="flex-1 py-2 rounded-xl text-[12px] font-medium bg-black/[0.06] text-[#3a3a3c] hover:bg-black/[0.1] transition-all"
          >
            暂不使用
          </button>
          <button
            onClick={() => onConsent(windowOnly)}
            className="flex-[1.4] py-2 rounded-xl text-[12px] font-medium text-white hover:brightness-110 transition-all"
            style={{ background: "#0071e3", boxShadow: "0 3px 12px rgba(0,113,227,0.28)" }}
          >
            我已了解并同意
          </button>
        </div>
      </div>
    </div>
  );
}

// ==================== 子组件 ====================

function ConsentItem({
  icon: Icon,
  title,
  desc,
}: {
  icon: typeof Keyboard;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="w-7 h-7 rounded-lg bg-[#0071e3]/[0.08] flex items-center justify-center shrink-0 mt-0.5">
        <Icon className="w-3.5 h-3.5 text-[#0071e3]" />
      </div>
      <div className="min-w-0">
        <p className="text-[11.5px] font-medium text-[#1d1d1f]">{title}</p>
        <p className="text-[10.5px] text-[#86868b] leading-relaxed mt-0.5">{desc}</p>
      </div>
    </div>
  );
}
