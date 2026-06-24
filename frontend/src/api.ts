import type { ChatMessage, PipelineOptions } from "./types";

const base = "/api";
/** In dev, bypass Vite proxy for SSE — browser streaming through the proxy often buffers until EOF. */
const streamBase = import.meta.env.DEV ? "http://127.0.0.1:8000/api" : base;
const DEFAULT_TIMEOUT_MS = 12_000;

async function json<T>(url: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${base}${url}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: controller.signal,
      ...init,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    return res.json();
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("API request timed out — is the backend running on port 8000?");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function parseSseChunk(
  buffer: string,
  onEvent: (data: Record<string, unknown>) => void
): { rest: string; count: number } {
  let count = 0;
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() || "";
  for (const part of parts) {
    if (!part.trim() || part.startsWith(":")) continue;
    const dataLine = part.split("\n").find((l) => l.startsWith("data:"));
    if (!dataLine) continue;
    const payload = dataLine.replace(/^data:\s?/, "");
    try {
      const parsed = JSON.parse(payload) as Record<string, unknown>;
      count += 1;
      onEvent(parsed);
    } catch {
      /* skip malformed SSE payload */
    }
  }
  return { rest, count };
}

function consumeSseBuffer(
  buffer: string,
  onEvent: (data: Record<string, unknown>) => void
): string {
  const parsed = parseSseChunk(buffer, onEvent);
  return parsed.rest;
}

function streamPipelineViaXhr(
  options: PipelineOptions,
  onEvent: (data: Record<string, unknown>) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    let buffer = "";
    let offset = 0;
    let settled = false;

    const finish = () => {
      if (settled) return;
      settled = true;
      resolve();
    };

    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      reject(err);
    };

    const ingest = (chunk: string) => {
      if (!chunk) return;
      buffer = consumeSseBuffer(buffer + chunk, onEvent);
    };

    const drain = () => {
      ingest(xhr.responseText.slice(offset));
      offset = xhr.responseText.length;
    };

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${streamBase}/pipeline/stream`);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Accept", "text/event-stream");

    xhr.onreadystatechange = () => {
      if (xhr.readyState === XMLHttpRequest.LOADING || xhr.readyState === XMLHttpRequest.DONE) {
        drain();
      }
      if (xhr.readyState === XMLHttpRequest.DONE) {
        if (xhr.status < 200 || xhr.status >= 300) {
          fail(new Error(`Pipeline stream failed (${xhr.status})`));
          return;
        }
        if (buffer.trim()) {
          consumeSseBuffer(`${buffer}\n\n`, onEvent);
        }
        finish();
      }
    };

    xhr.onerror = () => fail(new Error("Pipeline stream failed (XHR network error)"));
    xhr.onabort = () => fail(new Error("Pipeline stream aborted"));
    xhr.ontimeout = () => fail(new Error("Pipeline stream timed out"));
    xhr.timeout = 0;
    xhr.send(JSON.stringify(options));
  });
}

export const api = {
  health: () => json<{ status: string }>("/health"),
  dashboard: () => json<{ metrics: Record<string, number>; env: { name: string; configured: boolean; label: string }[]; runs: unknown[] }>("/dashboard"),
  agents: (completed = "", active = "") =>
    json<{ catalog: unknown[]; steps: import("./types").AgentStep[] }>(
      `/agents?completed=${completed}&active=${active}`
    ),
  migrations: () => json<import("./types").MigrationRun[]>("/migrations"),
  migration: (id: number) => json<Record<string, unknown>>(`/migrations/${id}`),
  sqlFiles: () => json<string[]>("/sql/files"),
  sqlFile: (name: string) => json<{ filename: string; content: string }>(`/sql/files/${encodeURIComponent(name)}`),
  transpile: (body: { filename?: string; sql?: string }) =>
    json<{ sql: string; status: string }>("/sql/transpile", { method: "POST", body: JSON.stringify(body) }),
  reports: () => json<{ label: string; path: string; exists: boolean; updated: string | null }[]>("/reports"),
  reportPreview: (path: string) => json<{ path: string; content: string }>(`/reports/preview?path=${encodeURIComponent(path)}`),
  chat: (message: string, history: ChatMessage[], options: PipelineOptions) =>
    json<{ reply: string; events: unknown[]; source: string }>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, options }),
    }),
  streamPipeline: (options: PipelineOptions, onEvent: (data: Record<string, unknown>) => void) =>
    streamPipelineViaXhr(options, onEvent),
};
