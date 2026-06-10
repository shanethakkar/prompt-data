"use client";

import { useCallback, useRef, useState } from "react";
import { apiUrl } from "@/lib/api";
import type { StageEvent, Turn } from "@/lib/types";

let counter = 0;
const nextId = () => `turn-${Date.now()}-${counter++}`;

const STREAM_URL = apiUrl("/ask/stream");

/** Parse a fetch ReadableStream of SSE `data: {json}` frames into StageEvents. */
async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<StageEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data: ")) {
          yield JSON.parse(line.slice(6)) as StageEvent;
        }
      }
    }
  }
}

/**
 * Owns the conversation thread and the streaming state machine. submit() appends a turn and
 * streams the trust pipeline into it; clarify() answers a prior clarifying question, which
 * re-runs the pipeline with the chosen option.
 */
export function useAsk() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const active = useRef<AbortController | null>(null);

  const patch = useCallback((id: string, update: Partial<Turn>) => {
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...update } : t)));
  }, []);

  const reset = useCallback(() => {
    active.current?.abort();
    active.current = null;
    setIsStreaming(false);
    setTurns([]);
  }, []);

  const run = useCallback(
    async (question: string, clarificationAnswer?: string, session?: string) => {
      const id = nextId();
      setTurns((prev) => [
        ...prev,
        { id, question, stages: [], status: "streaming" },
      ]);
      setIsStreaming(true);
      active.current?.abort();
      const controller = new AbortController();
      active.current = controller;

      try {
        const res = await fetch(STREAM_URL, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            session: session ?? null,
            question,
            clarification_answer: clarificationAnswer ?? null,
          }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);

        for await (const event of readSSE(res.body)) {
          if (event.type === "stage") {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === id
                  ? {
                      ...t,
                      stages: [
                        ...t.stages.map((s) => ({ ...s, done: true })),
                        { name: event.name, label: event.label, done: false },
                      ],
                    }
                  : t,
              ),
            );
          } else if (event.type === "clarification") {
            patch(id, {
              status: "done",
              kind: "clarification",
              clarification: event.clarification,
              stages: [],
            });
          } else if (event.type === "answer") {
            // The answer streams first with confidence null (scoring pill), then a second
            // answer event re-sends it with the scored confidence filled in.
            patch(id, {
              status: "done",
              kind: "answer",
              answer: event.answer,
              assumptions: event.assumptions,
              confidence: event.confidence,
              scoringConfidence: event.confidence == null,
              stages: [],
            });
          }
        }
        // Mark any turn still streaming (no terminal event) as done to clear spinners.
        setTurns((prev) =>
          prev.map((t) =>
            t.id === id && t.status === "streaming" ? { ...t, status: "done" } : t,
          ),
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          patch(id, { status: "error", error: (err as Error).message });
        }
      } finally {
        if (active.current === controller) {
          active.current = null;
          setIsStreaming(false);
        }
      }
    },
    [patch],
  );

  const submit = useCallback(
    (question: string, session?: string) => run(question, undefined, session),
    [run],
  );
  const clarify = useCallback(
    (question: string, choice: string, session?: string) => run(question, choice, session),
    [run],
  );

  return { turns, isStreaming, submit, clarify, reset };
}
