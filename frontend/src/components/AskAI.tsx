import { useEffect, useRef, useState } from "react";
import { HelpCircle, Loader2, Send, Sparkles, X } from "lucide-react";
import { api, ApiError, getApiBase, getToken, getAsStudent } from "@/api/client";

type Props = {
  moduleId?: number;
  stepId?: number;
  /** Kort förklaring av kontexten, visas i modalens header. */
  contextLabel?: string;
};

/** "Fråga Ekon" — öppnar en flytande chat-dialog där eleven kan ställa
 * en fråga till Claude om det hen jobbar med. Är bara synlig om lärarens
 * AI-funktioner är aktiverade (kollar /admin/ai/me vid mount).
 *
 * Svaret strömmas via Server-Sent-Events (POST /ai/student/ask/stream).
 * Första token kommer inom ~800 ms istället för 2–5 s när man väntade
 * på hela Sonnet-svaret.
 */
export function AskAI({ moduleId, stepId, contextLabel }: Props) {
  const [visible, setVisible] = useState(false);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setVisible(Boolean(r.ai_enabled)))
      .catch(() => setVisible(false));
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  async function ask() {
    if (!q.trim() || busy) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    setErr(null);
    setAnswer("");
    try {
      const token = getToken();
      const asStudent = getAsStudent();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      if (asStudent) headers["X-As-Student"] = String(asStudent);

      const res = await fetch(`${getApiBase()}/ai/student/ask/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          question: q.trim(),
          module_id: moduleId ?? null,
          step_id: stepId ?? null,
        }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        if (res.status === 503) {
          throw new ApiError(503, "AI-hjälpen är tyvärr inte tillgänglig just nu.");
        }
        if (res.status === 429) {
          throw new ApiError(429, "För många frågor. Vänta en stund.");
        }
        throw new ApiError(res.status, `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      // Server skickar rader på formen "data: {...}\n\n" per SSE-spec.
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          try {
            const evt = JSON.parse(payload) as
              | { type: "delta"; text: string }
              | { type: "done"; input_tokens: number; output_tokens: number }
              | { type: "error"; message: string };
            if (evt.type === "delta") {
              setAnswer((a) => a + evt.text);
            } else if (evt.type === "error") {
              setErr(evt.message);
            }
          } catch {
            // Ignorera trasiga frames — de kan komma vid nätverks-hickas.
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      if (e instanceof ApiError && e.status === 503) {
        setErr("AI-hjälpen är tyvärr inte tillgänglig just nu.");
      } else if (e instanceof ApiError && e.status === 429) {
        setErr("För många frågor. Vänta en stund.");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
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
            className="bg-white w-full md:max-w-lg md:rounded-xl rounded-t-2xl shadow-xl p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-600" />
                <h3 className="font-semibold text-slate-900">Fråga Ekon</h3>
              </div>
              <button
                onClick={close}
                className="text-slate-500 hover:text-slate-700"
                aria-label="Stäng"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {contextLabel && (
              <div className="text-xs text-slate-500">{contextLabel}</div>
            )}
            <p className="text-xs text-slate-600">
              Ekon är en AI-coach som förklarar på lätt svenska. Den ger
              inte personliga råd om vad du ska köpa eller spara — bara
              hjälper dig förstå.
            </p>
            <textarea
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              rows={3}
              placeholder="Ex: 'Vad betyder ränta-på-ränta?' eller 'Varför lönar sig buffertsparande?'"
              className="w-full border rounded p-2 text-sm"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
              }}
            />
            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500">
                Tryck Ctrl/Cmd+Enter för att skicka
              </div>
              <button
                onClick={ask}
                disabled={busy || !q.trim()}
                className="bg-purple-600 hover:bg-purple-700 text-white rounded px-4 py-2 text-sm font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {busy ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                Fråga
              </button>
            </div>
            {err && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded p-2">
                {err}
              </div>
            )}
            {(answer || busy) && (
              <div className="bg-purple-50 border border-purple-200 rounded p-3 text-sm text-slate-800 whitespace-pre-wrap min-h-[3rem]">
                {answer}
                {busy && (
                  <span className="inline-block w-2 h-4 ml-0.5 bg-purple-400 animate-pulse" />
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
