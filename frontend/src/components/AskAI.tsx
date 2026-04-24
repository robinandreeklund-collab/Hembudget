import { useEffect, useRef, useState } from "react";
import { HelpCircle, Loader2, Send, Sparkles, X } from "lucide-react";
import { api, ApiError } from "@/api/client";

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
 * Designval: vi håller det i en modal utan chat-historik. En fråga →
 * ett svar. Om eleven vill fråga vidare skriver hen om frågan. Detta
 * är medvetet för att hålla token-kostnaden nere och göra samtalen
 * lätta att bedöma pedagogiskt.
 */
export function AskAI({ moduleId, stepId, contextLabel }: Props) {
  const [visible, setVisible] = useState(false);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setVisible(Boolean(r.ai_enabled)))
      .catch(() => setVisible(false));
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  async function ask() {
    if (!q.trim() || busy) return;
    setBusy(true);
    setErr(null);
    setAnswer(null);
    try {
      const res = await api<{ answer: string }>("/ai/student/ask", {
        method: "POST",
        body: JSON.stringify({
          question: q.trim(),
          module_id: moduleId ?? null,
          step_id: stepId ?? null,
        }),
      });
      setAnswer(res.answer);
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setErr("AI-hjälpen är tyvärr inte tillgänglig just nu.");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
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
          onClick={() => setOpen(false)}
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
                onClick={() => setOpen(false)}
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
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  ask();
                }
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
            {answer && (
              <div className="bg-purple-50 border border-purple-200 rounded p-3 text-sm text-slate-800 whitespace-pre-wrap">
                {answer}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
