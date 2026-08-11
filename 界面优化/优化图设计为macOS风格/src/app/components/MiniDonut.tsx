import type { ReactNode } from "react";

// ==================== 迷你环形图（纯 SVG，stroke-dasharray 法，无需算 arc path） ====================
// 数据驱动：segments 按传入顺序占环；与报告页后端 SVG 视觉统一，但脱离异步 LLM 链路。

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
  icon?: string;
}

export function MiniDonut({
  segments,
  size = 72,
  stroke = 10,
  center,
}: {
  segments: DonutSegment[];
  size?: number;
  stroke?: number;
  center?: ReactNode;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = (size - stroke) / 2;
  const c = size / 2;
  const C = 2 * Math.PI * r; // 周长
  let offset = 0;

  return (
    <div className="relative inline-flex items-center justify-center shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* 底环 */}
        <circle cx={c} cy={c} r={r} fill="none" stroke="rgba(0,0,0,0.06)" strokeWidth={stroke} />
        {/* 各段：dasharray=[段长, 周长-段长]，dashoffset 累积负偏移让段接续 */}
        {total > 0 &&
          segments.map((s, i) => {
            const len = (s.value / total) * C;
            const el = (
              <circle
                key={i}
                cx={c}
                cy={c}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={stroke}
                strokeDasharray={`${len} ${C - len}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
              />
            );
            offset += len;
            return el;
          })}
      </svg>
      {center && <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{center}</div>}
    </div>
  );
}
