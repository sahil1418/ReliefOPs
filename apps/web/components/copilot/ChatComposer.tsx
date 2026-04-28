"use client";

import { Send } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";

const STARTERS = [
  "Show me all critical shipments in this disaster",
  "Summarize disaster Cyclone Remal status",
  "What insulin do we have at Cox's Bazar?",
  "Find playbooks similar to flood evacuation in Kerala",
];

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  const ta = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!ta.current) return;
    ta.current.style.height = "auto";
    ta.current.style.height = `${Math.min(180, ta.current.scrollHeight)}px`;
  }, [value]);

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSubmit();
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {STARTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onChange(s)}
            disabled={disabled}
            className="rounded-full border bg-background px-3 py-1 text-xs hover:bg-accent disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!disabled && value.trim()) onSubmit();
        }}
        className="flex gap-2"
      >
        <textarea
          ref={ta}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask the copilot — try one of the chips above"
          disabled={disabled}
          className="flex min-h-10 w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
        <Button type="submit" disabled={disabled || !value.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
