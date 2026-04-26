import { useEffect, useRef, useState } from "react";
import { HelpCircle, Loader2, Plus, Send, Sparkles, X } from "lucide-react";
import { api, ApiError, getApiBase, getToken, getAsStudent } from "@/api/client";

type Props = {
  moduleId?: number;
  stepId?: number;
  contextLabel?: string;
};

type Msg = {
  id: number;
  role: "user" | "assistant";
  content: string;
  transient?: boolean;
};

/** "Fråga Ekon" — multi-turn chat mot Claude.
 *
 * Trådar sparas i master-DB (AskAiThread/AskAiMessage) så eleven kan
 * återkomma till samma samtal senare. Systempromtpten får elevens
 * mastery-översikt så Sonnet kan anpassa språknivån (låg mastery →
 * mer socratic, hög mastery → rakt svar).
 */
export function AskAI({ moduleId, stepId, contextLabel }: Props) {
  const [visible, setVisible] = useState(false);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [threadId, setThreadId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const nextIdRef = useRef(1);

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setVisible(Boolean(r.ai_enabled)))
      .catch(() => setVisible(false));
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  function resetThread() {
    abortRef.current?.abort();
    setMessages([]);
    setThreadId(null);
    setQ("");
    setErr(null);
  }

  async function send() {
    if (!q.trim() || busy) return;
    const question = q.trim();
    setQ("");
    setErr(null);

    const userId = nextIdRef.current++;
    const asstId = nextIdRef.current++;
    setMessages((m) => [
      ...m,
      { id: userId, role: "user", content: question },
      { id: asstId, role: "assistant", content: "", transient: true },
    ]);

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    try {
      const token = getToken();
      const asStudent = getAsStudent();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      if (asStudent) headers["X-As-Student"] = String(asStudent);
      const res = await fetch(
        `${getApiBase()}/ai/student/threads/message/stream`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({
            question,
            thread_id: threadId,
            module_id: moduleId ?? null,
            step_id: stepId ?? null,
          }),
          signal: ctrl.signal,
        },
      );
      if (!res.ok || !res.body) {
        if (res.status === 503) throw new ApiError(503, "AI-hjälpen är inte tillgänglig just nu.");
        if (res.status === 429) throw new ApiError(429, "För många frågor.");
        throw new ApiError(res.status, `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const evt = JSON.parse(line.slice(5).trim()) as
              | { type: "thread"; thread_id: number }
              | { type: "delta"; text: string }
              | { type: "done" }
              | { type: "error"; message: string };
            if (evt.type === "thread") {
              setThreadId(evt.thread_id);
            } else if (evt.type === "delta") {
              setMessages((m) =>
                m.map((msg) =>
                  msg.id === asstId
                    ? { ...msg, content: msg.content + evt.text }
                    : msg,
                ),
              );
            } else if (evt.type === "error") {
              setErr(evt.message);
            }
          } catch {
            /* ignorera trasiga frames */
          }
        }
      }
      // När strömmen är klar, rensa transient-flaggan
      setMessages((m) =>
        m.map((msg) =>
          msg.id === asstId ? { ...msg, transient: false } : msg,
        ),
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      if (e instanceof ApiError && e.status === 503)
        setErr("AI-hjälpen är tyvärr inte tillgänglig just nu.");
      else if (e instanceof ApiError && e.status === 429)
        setErr("För många frågor. Vänta en stund.");
      else setErr(e instanceof Error ? e.message : String(e));
      // Ta bort asst-platshållaren vid fel
      setMessages((m) => m.filter((msg) => msg.id !== asstId || msg.content));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function close() {
    abortRef.current?.abort();
    setOpen(false);
  }

  if (!visible) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-20 bg-purple-600 hover:bg-purple-700 text-white rounded-full shadow-lg px-4 py-3 flex items-center gap-2 text-sm font-medium"
        aria-label="Fråga AI"
      >
        <HelpCircle className="w-4 h-4" />
        Fråga Ekon
      </button>

      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 flex items-end md:items-center justify-center p-0 md:p-4"
          onClick={close}
        >
          <div
            className="bg-white w-full md:max-w-lg md:rounded-xl rounded-t-2xl shadow-xl flex flex-col max-h-[90vh]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 pt-4 pb-2 border-b">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-600" />
                <h3 className="font-semibold text-slate-900">Fråga Ekon</h3>
                {threadId && (
                  <span className="text-xs text-slate-400">
                    (tråd #{threadId})
                  </span>
                )}
              </div>
              <div className="flex gap-1">
                {messages.length > 0 && (
                  <button
                    onClick={resetThread}
                    className="p-1.5 rounded text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                    title="Starta nytt samtal"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                )}
                <button
                  onClick={close}
                  className="p-1.5 rounded text-slate-500 hover:text-slate-700 hover:bg-slate-100"
                  aria-label="Stäng"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            {contextLabel && messages.length === 0 && (
              <div className="px-5 py-2 text-xs text-slate-500 border-b">
                {contextLabel}
              </div>
            )}

            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto px-5 py-4 space-y-3 min-h-0"
              style={{ minHeight: "160px" }}
            >
              {messages.length === 0 ? (
                <p className="text-sm text-slate-600">
                  Ekon förklarar på lätt svenska. Den ger inte personliga
                  råd om vad du ska köpa — bara hjälper dig förstå.
                </p>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={`text-sm whitespace-pre-wrap rounded-lg p-3 ${
                      m.role === "user"
                        ? "bg-slate-100 ml-6"
                        : "bg-purple-50 border border-purple-200 mr-6"
                    }`}
                  >
                    {m.content}
                    {m.transient && busy && (
                      <span className="inline-block w-2 h-4 ml-0.5 bg-purple-400 animate-pulse align-baseline" />
                    )}
                  </div>
                ))
              )}
              {err && (
                <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded p-2">
                  {err}
                </div>
              )}
            </div>

            <div className="px-5 py-3 border-t">
              <textarea
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                rows={2}
                placeholder="Skriv din fråga…"
                className="w-full border rounded p-2 text-sm resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
                }}
              />
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-slate-500">
                  Ctrl/Cmd+Enter skickar
                </span>
                <button
                  onClick={send}
                  disabled={busy || !q.trim()}
                  className="bg-purple-600 hover:bg-purple-700 text-white rounded px-4 py-2 text-sm font-medium flex items-center gap-2 disabled:opacity-50"
                >
                  {busy ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  Skicka
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
