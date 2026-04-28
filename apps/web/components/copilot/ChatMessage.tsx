"use client";

import { Sparkles, User as UserIcon, Wrench } from "lucide-react";

import { Markdown } from "@/components/copilot/Markdown";
import { cn } from "@/lib/utils";

export type ToolEvent =
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: Record<string, unknown> };

export type Message = {
  role: "user" | "assistant";
  content: string;
  events?: ToolEvent[];
};

export function ChatMessage({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-2",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {msg.events?.map((ev, i) => <ToolBubble key={i} ev={ev} />)}
        {msg.content && (
          isUser ? (
            <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
          ) : (
            <Markdown>{msg.content}</Markdown>
          )
        )}
      </div>
      {isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary">
          <UserIcon className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}

function ToolBubble({ ev }: { ev: ToolEvent }) {
  if (ev.type === "tool_call") {
    return (
      <div className="mb-2 flex items-center gap-2 rounded-md border bg-amber-50 px-2 py-1 text-xs text-amber-900">
        <Wrench className="h-3.5 w-3.5" />
        <span className="font-mono">{ev.name}</span>
        <span className="font-mono text-amber-700/70">
          ({Object.keys(ev.args).length} args)
        </span>
      </div>
    );
  }
  const summary = summarizeResult(ev.name, ev.result);
  return (
    <div className="mb-2 rounded-md border bg-emerald-50 px-2 py-1 text-xs text-emerald-900">
      <span className="font-mono">↳ {ev.name}</span> · {summary}
    </div>
  );
}

function summarizeResult(name: string, r: Record<string, unknown>): string {
  if (r.ok === false) return `error: ${String(r.error ?? "unknown")}`;
  if (typeof r.count === "number") return `${r.count} row${r.count === 1 ? "" : "s"}`;
  if (Array.isArray(r.matches)) return `${(r.matches as unknown[]).length} matches`;
  if (Array.isArray((r as { items?: unknown[] }).items)) {
    return `${((r as { items: unknown[] }).items).length} items`;
  }
  if (typeof r.shipmentId === "string") return `shipment ${String(r.shipmentId).slice(0, 8)}…`;
  if (typeof r.disaster === "object" && r.disaster) return "disaster summary";
  return "ok";
}
