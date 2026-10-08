import { useState } from "react";
import { ShieldAlert, RefreshCw } from "lucide-react";

interface MacPermissionGuideProps {
  onRecheck: () => Promise<boolean>; // 返回授权状态；true=已授权可关闭
  onOpenSystemSettings: () => Promise<void>;
  onSkip: () => void;
}

/**
 * macOS 辅助功能权限引导
 *
 * macOS 键盘监听（CGEventTap）与窗口标题采集（AXUIElement）需辅助功能权限。
 * 首次启动未授权时显示，引导用户到「系统设置 > 隐私与安全性 > 辅助功能」授权。
 */
export function MacPermissionGuide({ onRecheck, onOpenSystemSettings, onSkip }: MacPermissionGuideProps) {
  const [checking, setChecking] = useState(false);
  const [tried, setTried] = useState(false);

  const handleRecheck = async () => {
    setChecking(true);
    const ok = await onRecheck();
    setChecking(false);
    setTried(true);
    if (ok) {
      // 已授权，App.tsx 会因 needs_permission=false 卸载本组件
    }
  };

  const handleOpenSystemSettings = async () => {
    setChecking(true);
    await onOpenSystemSettings();
    setChecking(false);
  };

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.35)", backdropFilter: "blur(6px)" }}
    >
      <div
        className="relative w-[480px] max-w-[92vw] max-h-[88vh] overflow-y-auto bg-white rounded-2xl shadow-2xl"
        style={{ boxShadow: "0 24px 80px rgba(0,0,0,0.28), 0 0 0 0.5px rgba(0,0,0,0.08)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部图标区 */}
        <div className="flex flex-col items-center pt-7 pb-3 px-6">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-3"
            style={{
              background: "linear-gradient(135deg, #ff9700, #ffb340)",
              boxShadow: "0 6px 20px rgba(255,151,0,0.3)",
            }}
          >
            <ShieldAlert className="w-7 h-7 text-white" strokeWidth={2} />
          </div>
          <h1 className="text-[19px] font-semibold text-[#1d1d1f] tracking-tight">
            需要辅助功能权限
          </h1>
          <p className="text-[12px] text-[#86868b] mt-1">键盘输入与窗口标题采集依赖此权限</p>
        </div>

        {/* 内容区 */}
        <div className="px-6 pb-4 space-y-3">
          <div className="rounded-xl border border-black/[0.06] bg-[#f5f5f7] p-3">
            <p className="text-[13px] font-semibold text-[#1d1d1f] mb-2">请按以下步骤授权：</p>
            <ol className="text-[12px] text-[#6e6e73] leading-relaxed space-y-1.5 list-decimal pl-4">
              <li>打开「系统设置」→「隐私与安全性」→「辅助功能」</li>
              <li>在列表中找到「职迹 WorkTrace」（不要选择旧的同名条目）</li>
              <li>勾选启用开关（可能需输入密码确认）</li>
              <li>返回本程序，点击下方「我已授权，重新检测」</li>
            </ol>
          </div>

          <div className="rounded-xl border border-orange-200 bg-orange-50/70 p-2.5">
            <p className="text-[11.5px] text-orange-700 leading-relaxed">
              未授权时：仅窗口应用名可采集，键盘输入与窗口标题将不可用。
              可暂不授权继续使用（功能受限），之后随时在设置中授权并重启。
            </p>
          </div>

          {tried && !checking && (
            <p className="text-[12px] text-[#ff3b30] text-center">
              仍未检测到当前 App 的权限；请在系统提示中打开设置，并勾选「职迹 WorkTrace」
            </p>
          )}
        </div>

        {/* 按钮区 */}
        <div className="flex gap-2.5 px-6 pb-6 pt-1">
          <button
            onClick={onSkip}
            className="flex-1 py-2 rounded-xl text-[13px] font-medium bg-black/[0.06] text-[#3a3a3c] hover:bg-black/[0.1] transition-all"
          >
            暂不授权
          </button>
          <button
            onClick={handleOpenSystemSettings}
            disabled={checking}
            className="flex-1 py-2 rounded-xl text-[13px] font-medium text-white hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-1.5"
            style={{ background: "#65b81e", boxShadow: "0 3px 12px rgba(101,184,30,0.28)" }}
          >
            {checking ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                检测中
              </>
            ) : (
              "打开系统设置"
            )}
          </button>
          <button
            onClick={handleRecheck}
            disabled={checking}
            className="flex-1 py-2 rounded-xl text-[13px] font-medium bg-black/[0.06] text-[#3a3a3c] hover:bg-black/[0.1] transition-all disabled:opacity-60"
          >
            重新检测
          </button>
        </div>
      </div>
    </div>
  );
}
