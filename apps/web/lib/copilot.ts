/**
 * SSE streaming chat client.
 *
 * The API endpoint /api/copilot/chat is POST + text/event-stream. We stream the
 * response body via fetch/getReader, split on `\n\n`, and parse each `data: …`
 * payload as JSON. Each event is delivered to onEvent.
 */
import { getIdToken } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";

export type StreamEvent =
  | { type: "text"; content: string }
  | { type: "tool_call"; content: { name: string; args: Record<string, unknown> } }
  | { type: "tool_result"; content: { name: string; result: Record<string, unknown> } }
  | { type: "conversation"; content: { id: string } }
  | { type: "error"; content: { message: string } }
  | { type: "done"; content: null };

export async function streamCopilot(
  message: string,
  conversationId: string | null,
  signal: AbortSignal,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const token = await getIdToken();
  if (!token) throw new Error("Not signed in.");

  const res = await fetch(`${API_BASE_URL}/api/copilot/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, conversationId }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice(6);
      try {
        const event = JSON.parse(payload) as StreamEvent;
        onEvent(event);
        if (event.type === "done") return;
      } catch {
        // ignore malformed event
      }
    }
  }
}
