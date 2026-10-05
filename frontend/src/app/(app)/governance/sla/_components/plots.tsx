"use client";

// Recharts plot elements for the SLA dashboard. Each helper returns a RAW
// chart element — ChartContainer supplies the ResponsiveContainer, so these
// must not wrap themselves (bar-list.tsx/donut.tsx are the standalone,
// self-wrapping variants and cannot sit in the ChartContainer plot slot).
import { Bar, BarChart, Cell, Legend, Pie, PieChart, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, SERIES, TONE_VAR, type ChartTone } from "@/components/charts";
import { ChartTooltip } from "@/components/charts/chart-tooltip";
import { fmtCompact, fmtNum } from "@/lib/format";

export interface CountRow {
  label: string;
  value: number;
  tone?: ChartTone;
}

/** Horizontal bars — used for both the category ranking and the fixed
 *  days-overdue buckets (rows render in the order given, never re-sorted). */
export function rankedBars(data: CountRow[], animate: boolean) {
  return (
    <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }} barCategoryGap="24%">
      <XAxis type="number" hide />
      <YAxis
        type="category"
        dataKey="label"
        width={120}
        {...AXIS}
        tickFormatter={(v: string) => (v.length > 16 ? `${v.slice(0, 15)}…` : v)}
      />
      <Tooltip content={<ChartTooltip valueFormat={(v) => fmtNum(v)} />} cursor={{ fill: "var(--surface-2)" }} />
      <Bar dataKey="value" name="Items" radius={[0, 4, 4, 0]} isAnimationActive={animate}>
        {data.map((d) => (
          <Cell key={d.label} fill={d.tone ? TONE_VAR[d.tone] : SERIES[0]} />
        ))}
      </Bar>
    </BarChart>
  );
}

/** Conflicts-vs-quarantine composition donut, grand total in the center. */
export function mixDonut(data: CountRow[], animate: boolean) {
  const total = data.reduce((s, d) => s + d.value, 0);
  return (
    <PieChart>
      <Pie
        data={data}
        dataKey="value"
        nameKey="label"
        cy="45%"
        innerRadius={60}
        outerRadius={90}
        paddingAngle={2}
        stroke="none"
        isAnimationActive={animate}
      >
        {data.map((d, i) => (
          <Cell key={d.label} fill={d.tone ? TONE_VAR[d.tone] : SERIES[i % SERIES.length]} />
        ))}
      </Pie>
      <text x="50%" y="45%" dy={-4} textAnchor="middle" dominantBaseline="middle" className="tabular" style={{ fill: "var(--ink)", fontSize: 22, fontWeight: 600 }}>
        {fmtCompact(total)}
      </text>
      <text x="50%" y="45%" dy={16} textAnchor="middle" dominantBaseline="middle" style={{ fill: "var(--muted)", fontSize: 11 }}>
        overdue
      </text>
      <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
      <Tooltip content={<ChartTooltip />} />
    </PieChart>
  );
}
