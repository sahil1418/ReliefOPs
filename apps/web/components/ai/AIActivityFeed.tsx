"use client";

/**
 * AI Activity feed — tail of recent Gemini-attributed events.
 *
 * Sources: audit_logs (demand classifications, damage assessments) +
 * ai_conversations (copilot turns). Refreshes every 30s.
 */
import { useEffect, useState } from "react";
import { Sparkles, MessageSquare, Image as ImageIcon, Brain } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, ApiCallError } from "@/lib/api";

type Activity = {
  id: string;
  kind: "classify" | "vision" | "chat" | "embed";
  label: string;
  detail: string | null;
  model: string;
  actorUid: string | null;
  ts: string;
};

const KIND_META: Record<Activity["kind"], { icon: typeof Sparkles; tint: string; label: string }> = {
  classify: { icon: Brain, tint: "bg-blue-100 text-blue-700", label: "Classify" },
  vision: { icon: ImageIcon, tint: "bg-amber-100 text-amber-700", label: "Vision" },
  chat: { icon: MessageSquare, tint: "bg-violet-100 text-violet-700", label: "Chat" },
  embed: { icon: Sparkles, tint: "bg-emerald-100 text-emerald-700", label: "Embed" },
};

export function AIActivityFeed() {
  const [items, setItems] = useState<Activity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.get<Activity[]>("/api/ai/activity?limit=10");
        if (!cancelled) {
          setItems(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiCallError ? err.message : "Failed to load");
      }
    }
    void load();
    const id = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-violet-500" />
          AI activity
          <span className="ml-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
        </CardTitle>
        <CardDescription className="text-xs">
          Live tail of Gemini calls — classifications, vision assessments, copilot turns.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 pb-4">
        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-2 text-xs text-destructive">
            {error}
          </div>
        )}

        {!items && !error && (
          <>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </>
        )}

        {items && items.length === 0 && (
          <p className="py-6 text-center text-xs text-muted-foreground">
            No AI activity yet. Classify a demand request or run a damage assessment to populate this feed.
          </p>
        )}

        {items && items.length > 0 && (
          <ul className="-mx-2 max-h-[420px] divide-y overflow-y-auto">
            {items.map((it) => {
              const meta = KIND_META[it.kind];
              const Icon = meta.icon;
              return (
                <li key={it.id} className="flex items-start gap-3 px-2 py-2.5">
                  <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${meta.tint}`}>
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-sm font-medium">{it.label}</span>
                      <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                        {formatAge(it.ts)}
                      </span>
                    </div>
                    {it.detail && (
                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{it.detail}</p>
                    )}
                    <p className="mt-0.5 font-mono text-[10px] text-muted-foreground/80">{it.model}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function formatAge(iso: string): string {
  const sec = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}
