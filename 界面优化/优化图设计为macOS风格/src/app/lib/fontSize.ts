// ==================== 界面字体大小（小/中/大） ====================
// 方案：以 document 根元素 zoom 整体缩放。小=14px 基准，中=16px，大=18px。
// 注：组件字号大量使用 px 任意值（text-[11px]），html font-size 的 rem 缩放对它们不生效，
// zoom 是等效的整体缩放实现（WebView2/Chromium 支持良好）。

export type FontSize = "small" | "medium" | "large";

const STORAGE_KEY = "wt-font-size";

// 缩放系数：中 = 16/14，大 = 18/14
const SCALE: Record<FontSize, number> = {
  small: 1,
  medium: 1.14,
  large: 1.29,
};

export const FONT_SIZE_OPTIONS: { key: FontSize; label: string }[] = [
  { key: "small", label: "小" },
  { key: "medium", label: "中" },
  { key: "large", label: "大" },
];

export function getFontSize(): FontSize {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "small" || v === "medium" || v === "large") return v;
  } catch {
    // localStorage 不可用时静默回退
  }
  return "medium"; // 默认中字体（2026-08 UI 优化定稿）
}

export function applyFontSize(size: FontSize) {
  try {
    localStorage.setItem(STORAGE_KEY, size);
  } catch {
    // 忽略持久化失败，仍即时生效
  }
  (document.documentElement.style as CSSStyleDeclaration & { zoom: string }).zoom = String(SCALE[size]);
}

/** 应用启动时恢复用户上次选择的字号 */
export function initFontSize() {
  applyFontSize(getFontSize());
}
