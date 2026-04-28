"use client";

import { cn } from "@/lib/utils";

const CATEGORY_COLORS: Record<string, string> = {
  food: "bg-emerald-500",
  medicine: "bg-rose-500",
  shelter: "bg-amber-500",
  water: "bg-sky-500",
  rescue: "bg-violet-500",
  other: "bg-slate-400",
};

export type StockByCategory = Record<string, number>;

export function StockBars({ totals }: { totals: StockByCategory }) {
  const max = Math.max(1, ...Object.values(totals));
  const cats = Object.keys(CATEGORY_COLORS);
  return (
    <div className="space-y-1.5">
      {cats.map((cat) => {
        const v = totals[cat] ?? 0;
        const pct = (v / max) * 100;
        return (
          <div key={cat} className="flex items-center gap-3 text-xs">
            <span className="w-16 capitalize text-muted-foreground">{cat}</span>
            <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className={cn("absolute inset-y-0 left-0", CATEGORY_COLORS[cat])}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-12 text-right tabular-nums">{v.toLocaleString()}</span>
          </div>
        );
      })}
    </div>
  );
}
