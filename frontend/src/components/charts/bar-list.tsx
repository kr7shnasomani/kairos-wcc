"use client";

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, SERIES, TONE_VAR, downsample, type ChartTone } from "../charts";
import { ChartTooltip } from "./chart-tooltip";
import { useReducedMotion } from "@/lib/motion";

export interface BarListItem {
  label: string;
  value: number;
  tone?: ChartTone;
}

/** Horizontal ranked bars — category labels left, values encoded as length.
 *  Long labels truncate on the axis; the tooltip shows the full label. */
export function BarList({
  data,
  height = 220,
  valueFormat,
  showPercentage = false,
}: {
  data: BarListItem[];
  height?: number;
  valueFormat?: (v: number) => string;
  /** Opt in only when the provided rows are a complete whole. */
  showPercentage?: boolean;
}) {
  const reduced = useReducedMotion();
  const rows = downsample(data);
  const total = data.reduce((sum, row) => sum + row.value, 0);
  const chartRows = rows.map((row) => ({
    ...row,
    displayValue: `${valueFormat ? valueFormat(row.value) : String(row.value)}${showPercentage && total > 0 ? ` (${Math.round((row.value / total) * 100)}%)` : ""}`,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartRows} layout="vertical" margin={{ top: 0, right: 64, bottom: 0, left: 0 }} barCategoryGap="24%">
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={120}
          {...AXIS}
          tickFormatter={(v: string) => (v.length > 16 ? `${v.slice(0, 15)}…` : v)}
        />
        <Tooltip content={<ChartTooltip valueFormat={valueFormat} />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar dataKey="value" name="Value" radius={[0, 4, 4, 0]} isAnimationActive={!reduced}>
          {chartRows.map((d) => (
            <Cell key={d.label} fill={d.tone ? TONE_VAR[d.tone] : SERIES[0]} />
          ))}
          <LabelList dataKey="displayValue" position="right" fill="var(--ink)" style={{ fontSize: 11, fontWeight: 600 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
