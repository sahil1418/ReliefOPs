"use client";

import { useEffect, useRef, useState } from "react";

import { AdminTopbar } from "@/components/admin/AdminTopbar";
import { ChatComposer } from "@/components/copilot/ChatComposer";
import { ChatMessage, type Message, type ToolEvent } from "@/components/copilot/ChatMessage";
import { PhotoAssess } from "@/components/copilot/PhotoAssess";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { streamCopilot } from "@/lib/copilot";

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const cid = url.searchParams.get("c");
    if (cid) setConversationId(cid);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setInput("");
    setBusy(true);

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    // Reserve an assistant slot — we'll mutate it as events stream in.
    setMessages((prev) => [...prev, { role: "assistant", content: "", events: [] }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamCopilot(text, conversationId, controller.signal, (e) => {
        if (e.type === "conversation") {
          setConversationId(e.content.id);
          if (typeof window !== "undefined") {
            const url = new URL(window.location.href);
            url.searchParams.set("c", e.content.id);
            window.history.replaceState({}, "", url.toString());
          }
        } else if (e.type === "text") {
          setMessages((prev) => {
            const next = prev.slice();
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              next[next.length - 1] = { ...last, content: last.content + e.content };
            }
            return next;
          });
        } else if (e.type === "tool_call" || e.type === "tool_result") {
          const ev = (
            e.type === "tool_call"
              ? { type: "tool_call", name: e.content.name, args: e.content.args }
              : { type: "tool_result", name: e.content.name, result: e.content.result }
          ) as ToolEvent;
          setMessages((prev) => {
            const next = prev.slice();
            const last = next[next.length - 1];
            if (last && last.role === "assistant") {
              next[next.length - 1] = { ...last, events: [...(last.events ?? []), ev] };
            }
            return next;
          });
        } else if (e.type === "error") {
          setError(e.content.message);
        }
      });
    } catch (err) {
      if ((err as { name?: string }).name !== "AbortError") {
        setError(String(err instanceof Error ? err.message : err));
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  function newConversation() {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("c");
      window.history.replaceState({}, "", url.toString());
    }
  }

  return (
    <>
      <AdminTopbar title="AI Copilot" />
      <main className="flex-1 space-y-6 p-6">
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <Card className="flex h-[640px] flex-col xl:col-span-2">
            <CardHeader className="border-b">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">Operational copilot</CardTitle>
                  <CardDescription>
                    Gemini 2.5 Pro · 5 function-calling tools · streamed via SSE
                  </CardDescription>
                </div>
                <button
                  type="button"
                  onClick={newConversation}
                  className="text-xs text-muted-foreground underline-offset-2 hover:underline"
                  disabled={busy}
                >
                  New conversation
                </button>
              </div>
            </CardHeader>

            <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
              {messages.length === 0 && (
                <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
                  <div>
                    <p className="font-medium">Try one of the suggestion chips below.</p>
                    <p className="mt-1 text-xs">
                      The copilot can query shipments, summarize disasters, dispatch volunteers,
                      look up warehouse stock, and search past-disaster playbooks.
                    </p>
                  </div>
                </div>
              )}
              {messages.map((m, i) => (
                <ChatMessage key={i} msg={m} />
              ))}
              {busy && (
                <div className="text-xs text-muted-foreground">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary mr-2" />
                  Streaming…
                </div>
              )}
            </div>

            <CardContent className="border-t pt-4">
              {error && (
                <div className="mb-2 rounded-md border border-destructive/50 bg-destructive/5 p-2 text-xs text-destructive">
                  {error}
                </div>
              )}
              <ChatComposer
                value={input}
                onChange={setInput}
                onSubmit={send}
                disabled={busy}
              />
            </CardContent>
          </Card>

          <PhotoAssess />
        </div>
      </main>
    </>
  );
}
