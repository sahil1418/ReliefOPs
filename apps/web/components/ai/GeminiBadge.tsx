"use client";

import { Sparkles } from "lucide-react";

/**
 * Tiny "Powered by Gemini" pill, used across AI-generated UI surfaces so
 * judges can see which fields are model output vs. operator-entered data.
 */
export function GeminiBadge({
  model = "Gemini 2.5 Flash",
  detail,
  className = "",
}: {
  model?: string;
  detail?: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-violet-700 ${className}`}
      title={detail ? `${model} · ${detail}` : model}
    >
      <Sparkles className="h-2.5 w-2.5" />
      <span>{model}</span>
      {detail && <span className="font-mono normal-case tracking-normal text-violet-500">· {detail}</span>}
    </span>
  );
}
